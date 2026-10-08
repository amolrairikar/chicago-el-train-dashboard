import logging
import sys

import requests

from common.logging_setup import RedactingFormatter


def _format(message: str, exc_info=None) -> str:
    record = logging.LogRecord(
        "urllib3.connectionpool", logging.WARNING, __file__, 1, message, None, exc_info
    )
    return RedactingFormatter(logging.BASIC_FORMAT).format(record)


def test_redacting_formatter_masks_key_in_retry_warning():
    url = "/api/1.0/ttarrivals.aspx?mapid=40120&key=secret-key&outputType=JSON"
    out = _format(f"Retrying (Retry(total=2)) after connection broken by 'x': {url}")
    assert "secret-key" not in out
    assert "key=[REDACTED]&outputType=JSON" in out


def test_redacting_formatter_masks_key_in_traceback():
    try:
        raise requests.ConnectionError(
            "Max retries exceeded with url: /api/1.0/ttpositions.aspx?key=secret-key "
            "(Caused by ReadTimeoutError())"
        )
    except requests.ConnectionError:
        out = _format("Error fetching", exc_info=sys.exc_info())
    assert "secret-key" not in out
    assert "key=[REDACTED] (Caused by" in out


def test_redacting_formatter_leaves_other_text_alone():
    assert _format("monkey=banana key-free") == (
        "WARNING:urllib3.connectionpool:monkey=banana key-free"
    )
