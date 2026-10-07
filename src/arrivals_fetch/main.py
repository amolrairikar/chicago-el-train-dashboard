import csv
import functools
import io
import itertools
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import functions_framework
import google.auth
import requests
from flask import Request
from google.cloud import bigquery_storage_v1, secretmanager, storage
from google.cloud.bigquery_storage_v1 import types as bq_types
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ARRIVALS_URL = "https://lapi.transitchicago.com/api/1.0/ttarrivals.aspx"
DEFAULT_BQ_TABLE = "raw.arrivals"
STOPS_OBJECT_KEY = "gtfs/stops.txt"
# Parent stations (the API's mapid) use 4xxxx IDs; platforms use 3xxxx.
MIN_STATION_ID = 40000
MAX_STATION_ID = 50000  # Exclusive; IDs at or above this aren't stations.
BATCH_SIZE = 4  # The API accepts at most four mapids per request.
MAX_WORKERS = 10
REQUEST_TIMEOUT = (3, 8)  # (connect, read) timeouts in seconds
# With retries a single request can take ~50s, so a slow API could push all the
# batches past the 120s function timeout. Stopping at 90s leaves time to write
# the rows that did arrive.
FETCH_DEADLINE_SECONDS = 90
# CTA timestamps are Chicago local time with no UTC offset.
CTA_TZ = ZoneInfo("America/Chicago")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
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

# Matches the API key in a request URL's query string, e.g. "?mapid=1&key=abc".
API_KEY_PATTERN = re.compile(r"(?<![A-Za-z])(key=)[^&\s'\"]+")


class RedactingFormatter(logging.Formatter):
    """Masks the CTA API key in log output.

    The key must be sent as a query parameter, so request URLs carrying it can
    surface in urllib3 retry warnings and in connection error tracebacks.
    """

    def format(self, record: logging.LogRecord) -> str:
        return API_KEY_PATTERN.sub(r"\1[REDACTED]", super().format(record))


_log_handler = logging.StreamHandler()
_log_handler.setFormatter(RedactingFormatter(logging.BASIC_FORMAT))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _build_row_descriptor() -> descriptor_pb2.DescriptorProto:
    """Describes a raw.arrivals row for the Storage Write API.

    TIMESTAMP columns are sent as int64 microseconds since the epoch; every other
    column is a STRING.
    """
    descriptor = descriptor_pb2.DescriptorProto(name="ArrivalRow")
    for number, name in enumerate(("tmst", *STRING_COLUMNS), start=1):
        descriptor.field.add(
            name=name,
            number=number,
            type=_FIELD.TYPE_INT64 if name == "tmst" else _FIELD.TYPE_STRING,
            label=_FIELD.LABEL_OPTIONAL,
        )
    return descriptor


def _build_row_class(descriptor: descriptor_pb2.DescriptorProto) -> type:
    # A private pool keeps this message from clashing with other modules' types.
    pool = descriptor_pool.DescriptorPool()
    pool.Add(
        descriptor_pb2.FileDescriptorProto(
            name="arrivals_row.proto", syntax="proto2", message_type=[descriptor]
        )
    )
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("ArrivalRow"))


_FIELD = descriptor_pb2.FieldDescriptorProto
STRING_COLUMNS = ("errCd", "errNm", *ETA_FIELDS)
ROW_DESCRIPTOR = _build_row_descriptor()
RowMessage = _build_row_class(ROW_DESCRIPTOR)


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        # Return the final response instead of raising so its status can be reported.
        raise_on_status=False,
    )
    session = requests.Session()
    # The pool is sized to the worker count so parallel requests reuse connections.
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=MAX_WORKERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http_session = build_session()


@functools.cache
def get_write_client() -> bigquery_storage_v1.BigQueryWriteClient:
    """Builds the Storage Write client once per instance so warm invocations reuse it."""
    return bigquery_storage_v1.BigQueryWriteClient()


@functools.cache
def get_project_id() -> str:
    """Resolves the project for table names given without one, e.g. raw.arrivals."""
    _, project = google.auth.default()
    if not project:
        raise RuntimeError("Could not determine the Google Cloud project")
    return project


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
            write_to_bigquery(rows, table)
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


@functools.cache
def get_api_key(secret_name: str) -> str:
    """Reads the CTA API key, cached so warm instances skip Secret Manager."""
    # Regional secrets are only served from their region's endpoint, e.g.
    # projects/<p>/locations/us-central1/secrets/<s>/versions/<v>.
    parts = secret_name.split("/")
    client_options = None
    if len(parts) > 3 and parts[2] == "locations":
        client_options = {
            "api_endpoint": f"secretmanager.{parts[3]}.rep.googleapis.com"
        }
    client = secretmanager.SecretManagerServiceClient(client_options=client_options)
    response = client.access_secret_version(name=secret_name)
    return response.payload.data.decode("utf-8").strip()


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
    # The request URL carries the API key; RedactingFormatter masks it in logs.
    with http_session.get(ARRIVALS_URL, params=params, timeout=REQUEST_TIMEOUT) as resp:
        if resp.status_code != 200:
            raise requests.HTTPError(
                f"unexpected status fetching train arrivals: "
                f"{resp.status_code} {resp.reason}",
                response=resp,
            )
        return resp.json()["ctatt"]


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


def _to_str(value) -> str:
    return "" if value is None else str(value)


def _to_utc_iso(cta_timestamp: str) -> str:
    local = datetime.fromisoformat(cta_timestamp).replace(tzinfo=CTA_TZ)
    return local.astimezone(UTC).isoformat()


def flatten_arrivals(ctatt: dict) -> list[dict]:
    """Produces one row per arrival prediction, matching the raw.arrivals schema."""
    snapshot = {
        "tmst": _to_utc_iso(ctatt["tmst"]),
        "errCd": _to_str(ctatt.get("errCd")),
        "errNm": _to_str(ctatt.get("errNm")),
    }

    etas = ctatt.get("eta") or []
    # The JSON output is converted from XML, so a single element is returned as
    # an object rather than a one-item list.
    if isinstance(etas, dict):
        etas = [etas]

    return [
        {**snapshot, **{field: _to_str(eta.get(field)) for field in ETA_FIELDS}}
        for eta in etas
    ]


def _to_epoch_micros(iso_timestamp: str) -> int:
    return (datetime.fromisoformat(iso_timestamp) - EPOCH) // timedelta(microseconds=1)


def serialize_row(row: dict) -> bytes:
    message = RowMessage(tmst=_to_epoch_micros(row["tmst"]))
    for column in STRING_COLUMNS:
        setattr(message, column, row[column])
    return message.SerializeToString()


def table_path(table: str) -> str:
    """Expands "dataset.table" or "project.dataset.table" to a resource path."""
    parts = table.split(".")
    if len(parts) == 2:
        parts.insert(0, get_project_id())
    if len(parts) != 3:
        raise ValueError(f"Invalid BigQuery table name: {table!r}")
    return bigquery_storage_v1.BigQueryWriteClient.table_path(*parts)


def write_to_bigquery(rows: list[dict], table: str) -> None:
    """Appends rows through the Storage Write API's default stream.

    The default stream commits each append immediately with at-least-once
    semantics. It is billed far below legacy streaming inserts and has a 2 TiB
    monthly free tier.
    """
    stream = f"{table_path(table)}/streams/_default"
    request = bq_types.AppendRowsRequest(
        write_stream=stream,
        proto_rows=bq_types.AppendRowsRequest.ProtoData(
            writer_schema=bq_types.ProtoSchema(proto_descriptor=ROW_DESCRIPTOR),
            rows=bq_types.ProtoRows(serialized_rows=[serialize_row(r) for r in rows]),
        ),
    )
    # append_rows is a bidirectional stream, so the client can't derive the
    # routing header from the request; it has to be supplied here.
    responses = get_write_client().append_rows(
        iter([request]),
        metadata=(("x-goog-request-params", f"write_stream={stream}"),),
    )
    for response in responses:
        if response.row_errors:
            raise RuntimeError(f"BigQuery row errors: {list(response.row_errors)}")
        if response.error.code:
            raise RuntimeError(f"BigQuery append error: {response.error.message}")
