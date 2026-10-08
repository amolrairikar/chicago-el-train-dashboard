import pytest
import requests

from common import cta

URL = "https://example.com/api"
TIMEOUT = (3, 8)


class FakeResponse:
    """Minimal stand-in for requests.Response used as a context manager."""

    def __init__(self, status_code, body=None, json_error=None):
        self.status_code = status_code
        self.reason = "reason"
        self._body = body
        self._json_error = json_error
        self.closed = False

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._body

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.resp


def fetch(session, key="test-key"):
    return cta.fetch_ctatt(session, URL, {"key": key}, TIMEOUT, "widgets")


# --- fetch_ctatt -------------------------------------------------------------


def test_fetch_request_shape():
    session = FakeSession(FakeResponse(200, {"ctatt": {}}))
    fetch(session)
    assert session.calls == [
        {"url": URL, "params": {"key": "test-key"}, "timeout": TIMEOUT}
    ]


def test_fetch_returns_ctatt_and_closes():
    resp = FakeResponse(200, {"ctatt": {"tmst": "x"}})
    assert fetch(FakeSession(resp)) == {"tmst": "x"}
    assert resp.closed


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
def test_fetch_unexpected_status(status):
    resp = FakeResponse(status)
    with pytest.raises(requests.HTTPError, match="fetching widgets") as exc_info:
        fetch(FakeSession(resp))
    assert exc_info.value.response is resp
    assert resp.closed


def test_fetch_error_does_not_expose_api_key():
    with pytest.raises(requests.HTTPError) as exc_info:
        fetch(FakeSession(FakeResponse(500)), key="super-secret-key")
    assert "super-secret-key" not in str(exc_info.value)


def test_fetch_missing_ctatt():
    with pytest.raises(KeyError):
        fetch(FakeSession(FakeResponse(200, {"unexpected": {}})))


def test_fetch_invalid_json():
    with pytest.raises(ValueError):
        fetch(FakeSession(FakeResponse(200, json_error=ValueError("not json"))))


# --- as_list -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "want"),
    [
        (None, []),
        ([], []),
        ({}, []),
        ({"a": 1}, [{"a": 1}]),
        ([{"a": 1}, {"a": 2}], [{"a": 1}, {"a": 2}]),
    ],
)
def test_as_list(value, want):
    assert cta.as_list(value) == want


# --- to_str / to_utc_iso -----------------------------------------------------


@pytest.mark.parametrize(("value", "want"), [(None, ""), (0, "0"), ("x", "x")])
def test_to_str(value, want):
    assert cta.to_str(value) == want


@pytest.mark.parametrize(
    ("local", "want"),
    [
        # Central Daylight Time (UTC-5)
        ("2026-10-06T17:01:23", "2026-10-06T22:01:23+00:00"),
        # Central Standard Time (UTC-6)
        ("2026-01-15T08:00:00", "2026-01-15T14:00:00+00:00"),
        # Rolls over to the next UTC day
        ("2026-10-06T23:30:00", "2026-10-07T04:30:00+00:00"),
    ],
)
def test_to_utc_iso(local, want):
    assert cta.to_utc_iso(local) == want


def test_to_utc_iso_invalid():
    with pytest.raises(ValueError):
        cta.to_utc_iso("not a timestamp")
