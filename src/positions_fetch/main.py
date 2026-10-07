import functools
import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import functions_framework
import requests
from flask import Request
from google.cloud import bigquery, secretmanager
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

POSITIONS_URL = "https://lapi.transitchicago.com/api/1.0/ttpositions.aspx"
ROUTES = ["Blue", "Red", "Brn", "G", "Org", "P", "Pink", "Y"]
DEFAULT_BQ_TABLE = "raw.positions"
REQUEST_TIMEOUT = (3, 8)  # (connect, read) timeouts in seconds
# CTA timestamps are Chicago local time with no UTC offset.
CTA_TZ = ZoneInfo("America/Chicago")
TRAIN_FIELDS = (
    "rn",
    "destSt",
    "destNm",
    "trDr",
    "nextStaId",
    "nextStpId",
    "nextStaNm",
    "prdt",
    "arrT",
    "isApp",
    "isDly",
    "flags",
    "lat",
    "lon",
    "heading",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


http_session = build_session()


@functions_framework.http
def handler(request: Request):
    logger.info("Beginning train positions fetch execution")

    secret_name = os.environ.get("CTA_API_KEY_SECRET")
    if not secret_name:
        logger.error("CTA_API_KEY_SECRET environment variable is not set")
        return "Misconfigured CTA_API_KEY_SECRET", 500
    table = os.environ.get("BQ_TABLE", DEFAULT_BQ_TABLE)

    try:
        api_key = get_api_key(secret_name)
    except Exception:
        logger.exception("Error reading CTA API key from Secret Manager")
        return "Failed to read CTA API key", 500

    try:
        ctatt = fetch_positions(api_key)
    except requests.HTTPError:
        logger.exception("Error fetching train positions")
        return "Failed to fetch train positions", 502
    except Exception:
        logger.exception("Error fetching train positions")
        return "Failed to fetch train positions", 500

    # The API reports errors in the body with an HTTP 200, so errCd must be checked.
    if str(ctatt.get("errCd")) != "0":
        logger.error("CTA API error %s: %s", ctatt.get("errCd"), ctatt.get("errNm"))
        return "CTA API returned an error", 502

    try:
        rows = flatten_positions(ctatt)
    except Exception:
        logger.exception("Error parsing train positions response")
        return "Failed to parse train positions", 500
    if not rows:
        logger.info("No trains returned at %s - skipping insert", ctatt.get("tmst"))
        return "", 200

    try:
        write_to_bigquery(rows, table)
    except Exception:
        logger.exception("Error writing train positions to BigQuery")
        return "Failed to write train positions", 500
    logger.info("Inserted %d train positions into %s", len(rows), table)
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


def fetch_positions(api_key: str) -> dict:
    """Returns the `ctatt` body of the train positions response."""
    params = {"rt": ROUTES, "key": api_key, "outputType": "JSON"}
    # The request URL carries the API key, so we must not log it
    with http_session.get(
        POSITIONS_URL, params=params, timeout=REQUEST_TIMEOUT
    ) as resp:
        if resp.status_code != 200:
            raise requests.HTTPError(
                f"unexpected status fetching train positions: "
                f"{resp.status_code} {resp.reason}",
                response=resp,
            )
        return resp.json()["ctatt"]


def _to_str(value) -> str:
    return "" if value is None else str(value)


def _to_utc_iso(cta_timestamp: str) -> str:
    local = datetime.fromisoformat(cta_timestamp).replace(tzinfo=CTA_TZ)
    return local.astimezone(UTC).isoformat()


def flatten_positions(ctatt: dict) -> list[dict]:
    """Produces one row per train, matching the raw.positions schema."""
    snapshot = {
        "tmst": _to_utc_iso(ctatt["tmst"]),
        "errCd": _to_str(ctatt.get("errCd")),
        "errNm": _to_str(ctatt.get("errNm")),
    }

    routes = ctatt.get("route") or []
    # The JSON output is converted from XML, so a single element is returned as
    # an object rather than a one-item list.
    if isinstance(routes, dict):
        routes = [routes]

    rows = []
    for route in routes:
        trains = route.get("train") or []
        if isinstance(trains, dict):
            trains = [trains]
        for train in trains:
            row = {**snapshot, "name": _to_str(route.get("@name"))}
            row.update({field: _to_str(train.get(field)) for field in TRAIN_FIELDS})
            rows.append(row)
    return rows


def write_to_bigquery(rows: list[dict], table: str) -> None:
    # Row IDs give best-effort dedupe if the same snapshot is inserted twice.
    row_ids = [f"{row['tmst']}-{row['name']}-{row['rn']}" for row in rows]
    errors = bigquery.Client().insert_rows_json(table, rows, row_ids=row_ids)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
