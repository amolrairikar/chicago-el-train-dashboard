from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

CTA_TZ = ZoneInfo("America/Chicago")


def fetch_ctatt(
    session: requests.Session,
    url: str,
    params: dict,
    timeout: tuple[float, float],
    description: str,
) -> dict:
    """Returns the `ctatt` body of a Train Tracker API response.

    description names the data in error messages, e.g. "train positions".
    """
    # The request URL carries the API key; RedactingFormatter masks it in logs.
    with session.get(url, params=params, timeout=timeout) as resp:
        if resp.status_code != 200:
            raise requests.HTTPError(
                f"unexpected status fetching {description}: "
                f"{resp.status_code} {resp.reason}",
                response=resp,
            )
        return resp.json()["ctatt"]


def as_list(value) -> list:
    """Normalizes a repeated element of the API's JSON output to a list.

    The JSON output is converted from XML, so a single element is returned as
    an object rather than a one-item list, and an absent one as None.
    """
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    return value


def to_str(value) -> str:
    return "" if value is None else str(value)


def to_utc_iso(cta_timestamp: str) -> str:
    local = datetime.fromisoformat(cta_timestamp).replace(tzinfo=CTA_TZ)
    return local.astimezone(UTC).isoformat()
