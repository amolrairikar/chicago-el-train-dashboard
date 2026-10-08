import logging
import os

import functions_framework
import requests
from flask import Request

from common.bigquery import RowSchema, write_to_bigquery
from common.cta import as_list, fetch_ctatt, to_str, to_utc_iso
from common.http import build_session
from common.logging_setup import configure_logging
from common.secrets import get_api_key

POSITIONS_URL = "https://lapi.transitchicago.com/api/1.0/ttpositions.aspx"
ROUTES = ["Blue", "Red", "Brn", "G", "Org", "P", "Pink", "Y"]
DEFAULT_BQ_TABLE = "raw.positions"
REQUEST_TIMEOUT = (3, 8)  # (connect, read) timeouts in seconds
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
ROW_SCHEMA = RowSchema("PositionRow", ("errCd", "errNm", "name", *TRAIN_FIELDS))

configure_logging()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        write_to_bigquery(rows, table, ROW_SCHEMA)
    except Exception:
        logger.exception("Error writing train positions to BigQuery")
        return "Failed to write train positions", 500
    logger.info("Inserted %d train positions into %s", len(rows), table)
    return "", 200


def fetch_positions(api_key: str) -> dict:
    """Returns the `ctatt` body of the train positions response."""
    params = {"rt": ROUTES, "key": api_key, "outputType": "JSON"}
    return fetch_ctatt(
        http_session, POSITIONS_URL, params, REQUEST_TIMEOUT, "train positions"
    )


def flatten_positions(ctatt: dict) -> list[dict]:
    """Produces one row per train, matching the raw.positions schema."""
    snapshot = {
        "tmst": to_utc_iso(ctatt["tmst"]),
        "errCd": to_str(ctatt.get("errCd")),
        "errNm": to_str(ctatt.get("errNm")),
    }

    rows = []
    for route in as_list(ctatt.get("route")):
        for train in as_list(route.get("train")):
            row = {**snapshot, "name": to_str(route.get("@name"))}
            row.update({field: to_str(train.get(field)) for field in TRAIN_FIELDS})
            rows.append(row)
    return rows
