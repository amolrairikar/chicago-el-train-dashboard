import csv
import functools
import io
import itertools
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import functions_framework
from flask import Request
from google.cloud import storage

from common.bigquery import RowSchema, write_to_bigquery
from common.cta import as_list, fetch_ctatt, to_str, to_utc_iso
from common.http import build_session
from common.logging_setup import configure_logging
from common.secrets import get_api_key

ARRIVALS_URL = "https://lapi.transitchicago.com/api/1.0/ttarrivals.aspx"
DEFAULT_BQ_TABLE = "raw.arrivals"
STOPS_OBJECT_KEY = "gtfs/stops.txt"
# Parent stations (the API's mapid) use 4xxxx IDs; platforms use 3xxxx.
MIN_STATION_ID = 40000
MAX_STATION_ID = 50000
BATCH_SIZE = 4  # The API accepts at most four mapids per request.
MAX_WORKERS = 10
REQUEST_TIMEOUT = (3, 8)  # (connect, read) timeouts in seconds
# With retries a single request can take ~50s, so a slow API could push all the
# batches past the 120s function timeout. Stopping at 90s leaves time to write
# the rows that did arrive.
FETCH_DEADLINE_SECONDS = 90
ETA_FIELDS = (
    "staId",
    "stpId",
    "staNm",
    "stpDe",
    "rn",
    "rt",
    "destSt",
    "destNm",
    "trDr",
    "prdt",
    "arrT",
    "isApp",
    "isSch",
    "isDly",
    "isFlt",
    "flags",
    "lat",
    "lon",
    "heading",
)
ROW_SCHEMA = RowSchema("ArrivalRow", ("errCd", "errNm", *ETA_FIELDS))

configure_logging()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# The pool is sized to the worker count so parallel requests reuse connections.
http_session = build_session(pool_maxsize=MAX_WORKERS)


@functools.cache
def get_storage_client() -> storage.Client:
    """Builds the GCS client once per instance so warm invocations reuse it."""
    return storage.Client()


@functions_framework.http
def handler(request: Request):
    logger.info("Beginning train arrivals fetch execution")

    secret_name = os.environ.get("CTA_API_KEY_SECRET")
    if not secret_name:
        logger.error("CTA_API_KEY_SECRET environment variable is not set")
        return "Misconfigured CTA_API_KEY_SECRET", 500
    bucket_name = os.environ.get("GCS_BUCKET")
    if not bucket_name:
        logger.error("GCS_BUCKET environment variable is not set")
        return "Misconfigured GCS_BUCKET", 500
    table = os.environ.get("BQ_TABLE", DEFAULT_BQ_TABLE)

    try:
        api_key = get_api_key(secret_name)
    except Exception:
        logger.exception("Error reading CTA API key from Secret Manager")
        return "Failed to read CTA API key", 500

    try:
        station_ids = get_station_ids(bucket_name)
    except Exception:
        logger.exception("Error reading station IDs from GTFS stops")
        return "Failed to read station IDs", 500
    if not station_ids:
        logger.error(
            "No station IDs found in gs://%s/%s", bucket_name, STOPS_OBJECT_KEY
        )
        return "No station IDs found", 500

    rows, failed_batches = fetch_all(api_key, station_ids)

    if rows:
        try:
            write_to_bigquery(rows, table, ROW_SCHEMA)
        except Exception:
            logger.exception("Error writing train arrivals to BigQuery")
            return "Failed to write train arrivals", 500
        logger.info("Inserted %d train arrivals into %s", len(rows), table)
    else:
        logger.info("No arrivals returned - skipping insert")

    if failed_batches:
        logger.error("%d arrival batches failed", len(failed_batches))
        return "Failed to fetch some train arrivals", 502
    return "", 200


def get_station_ids(bucket_name: str) -> list[str]:
    blob = get_storage_client().bucket(bucket_name).get_blob(STOPS_OBJECT_KEY)
    if blob is None:
        raise FileNotFoundError(f"gs://{bucket_name}/{STOPS_OBJECT_KEY} not found")
    return _load_station_ids(bucket_name, blob.generation)


@functools.cache
def _load_station_ids(bucket_name: str, generation: int) -> list[str]:
    """Parses station IDs from stops.txt, cached per object generation.

    The generation key lets warm instances skip the download until gtfs_fetch
    publishes a new stops.txt.
    """
    blob = (
        get_storage_client()
        .bucket(bucket_name)
        .blob(STOPS_OBJECT_KEY, generation=generation)
    )
    reader = csv.DictReader(io.StringIO(blob.download_as_text()))
    station_ids = {
        stop_id
        for row in reader
        if (stop_id := (row.get("stop_id") or "").strip()).isdigit()
        and MIN_STATION_ID <= int(stop_id) < MAX_STATION_ID
    }
    return sorted(station_ids, key=int)


def fetch_arrivals(api_key: str, map_ids: tuple[str, ...]) -> dict:
    """Returns the `ctatt` body of the arrivals response for up to four stations."""
    params = {"mapid": list(map_ids), "key": api_key, "outputType": "JSON"}
    return fetch_ctatt(
        http_session, ARRIVALS_URL, params, REQUEST_TIMEOUT, "train arrivals"
    )


def fetch_all(
    api_key: str, station_ids: list[str], deadline: float = FETCH_DEADLINE_SECONDS
) -> tuple[list[dict], list[tuple[str, ...]]]:
    """Fetches every batch of stations in parallel.

    Returns the flattened rows from successful batches and the failed batches.
    Batches still unfinished after `deadline` seconds count as failed.
    """
    rows = []
    failed_batches = []
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = {
        executor.submit(fetch_arrivals, api_key, batch): batch
        for batch in itertools.batched(station_ids, BATCH_SIZE)
    }
    pending = dict(futures)
    try:
        for future in as_completed(futures, timeout=deadline):
            batch = pending.pop(future)
            try:
                ctatt = future.result()
                # The API reports errors in the body with an HTTP 200, so errCd must be checked.
                if str(ctatt.get("errCd")) != "0":
                    logger.error(
                        "CTA API error %s for mapids %s: %s",
                        ctatt.get("errCd"),
                        ",".join(batch),
                        ctatt.get("errNm"),
                    )
                    failed_batches.append(batch)
                    continue
                rows.extend(flatten_arrivals(ctatt))
            except Exception:
                logger.exception(
                    "Error fetching train arrivals for mapids %s", ",".join(batch)
                )
                failed_batches.append(batch)
    except TimeoutError:
        logger.error(
            "Timed out after %ss with %d arrival batches unfinished",
            deadline,
            len(pending),
        )
        failed_batches.extend(pending.values())
    finally:
        # Don't block on in-flight requests past the deadline; queued batches
        # are cancelled and running ones finish in the background.
        executor.shutdown(wait=False, cancel_futures=True)
    return rows, failed_batches


def flatten_arrivals(ctatt: dict) -> list[dict]:
    """Produces one row per arrival prediction, matching the raw.arrivals schema."""
    snapshot = {
        "tmst": to_utc_iso(ctatt["tmst"]),
        "errCd": to_str(ctatt.get("errCd")),
        "errNm": to_str(ctatt.get("errNm")),
    }
    return [
        {**snapshot, **{field: to_str(eta.get(field)) for field in ETA_FIELDS}}
        for eta in as_list(ctatt.get("eta"))
    ]
