import json
import re
from pathlib import Path
from unittest import mock

import locations_main as main
import pytest
import requests
from flask import Flask

TF_PATH = Path(__file__).resolve().parents[2] / "infrastructure" / "main.tf"
SECRET_NAME = "projects/test/secrets/cta-api-key/versions/latest"


def make_train(rn="801", **overrides):
    train = {
        "rn": rn,
        "destSt": "30089",
        "destNm": "95th/Dan Ryan",
        "trDr": "5",
        "nextStaId": "41450",
        "nextStpId": "30282",
        "nextStaNm": "Chicago",
        "prdt": "2026-10-06T17:00:58",
        "arrT": "2026-10-06T17:02:58",
        "isApp": "0",
        "isDly": "0",
        "flags": None,
        "lat": "41.89681",
        "lon": "-87.62838",
        "heading": "178",
    }
    train.update(overrides)
    return train


def make_ctatt(routes=None, tmst="2026-10-06T17:01:23", err_cd="0", err_nm=None):
    if routes is None:
        routes = [
            {"@name": "red", "train": [make_train("801"), make_train("802")]},
            {"@name": "blue", "train": [make_train("101")]},
        ]
    return {"tmst": tmst, "errCd": err_cd, "errNm": err_nm, "route": routes}


def positions_schema_columns():
    """Reads the column names of the raw.positions table from Terraform."""
    tf = TF_PATH.read_text()
    match = re.search(
        r'resource "google_bigquery_table" "positions_table".*?schema = <<EOF\n(.*?)\nEOF',
        tf,
        re.DOTALL,
    )
    assert match, "positions_table schema not found in main.tf"
    return [column["name"] for column in json.loads(match.group(1))]


# --- fakes -------------------------------------------------------------------


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


@pytest.fixture(autouse=True)
def clear_api_key_cache():
    main.get_api_key.cache_clear()
    yield
    main.get_api_key.cache_clear()


@pytest.fixture
def secret(monkeypatch):
    """Fakes Secret Manager; the returned client records access calls."""
    client = mock.Mock()
    client.access_secret_version.return_value.payload.data = b"test-key\n"
    client.init_kwargs = []

    def make_client(**kwargs):
        client.init_kwargs.append(kwargs)
        return client

    monkeypatch.setattr(main.secretmanager, "SecretManagerServiceClient", make_client)
    monkeypatch.setenv("CTA_API_KEY_SECRET", SECRET_NAME)
    return client


@pytest.fixture
def bq(monkeypatch):
    """Fakes BigQuery; the returned client records insert calls."""
    client = mock.Mock()
    client.insert_rows_json.return_value = []
    monkeypatch.setattr(main.bigquery, "Client", lambda: client)
    monkeypatch.delenv("BQ_TABLE", raising=False)
    return client


@pytest.fixture
def stub_cta(monkeypatch):
    """Replaces http_session.get; returns the list of recorded request kwargs."""

    def install(fn):
        calls = []

        def get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return fn()

        monkeypatch.setattr(main.http_session, "get", get)
        return calls

    return install


def serve():
    app = Flask(__name__)
    with app.test_request_context("/", method="POST"):
        from flask import request

        return main.handler(request)


# --- build_session -----------------------------------------------------------


def test_session_has_retries_configured():
    session = main.build_session()
    for prefix in ("https://", "http://"):
        retry = session.get_adapter(prefix + "example.com").max_retries
        assert retry.total == 3
        assert retry.backoff_factor == 1
        assert {500, 502, 503, 504, 429} <= set(retry.status_forcelist)
        assert "GET" in retry.allowed_methods
        assert retry.raise_on_status is False


# --- get_api_key -------------------------------------------------------------


def test_get_api_key_reads_and_strips(secret):
    assert main.get_api_key(SECRET_NAME) == "test-key"
    secret.access_secret_version.assert_called_once_with(name=SECRET_NAME)


def test_get_api_key_is_cached(secret):
    main.get_api_key(SECRET_NAME)
    main.get_api_key(SECRET_NAME)
    assert secret.access_secret_version.call_count == 1


def test_get_api_key_does_not_cache_failures(secret):
    secret.access_secret_version.side_effect = [RuntimeError("boom"), mock.DEFAULT]
    with pytest.raises(RuntimeError):
        main.get_api_key(SECRET_NAME)
    assert main.get_api_key(SECRET_NAME) == "test-key"


def test_get_api_key_global_secret_uses_default_endpoint(secret):
    main.get_api_key(SECRET_NAME)
    assert secret.init_kwargs == [{"client_options": None}]


def test_get_api_key_regional_secret_uses_regional_endpoint(secret):
    name = "projects/test/locations/us-central1/secrets/cta-api-key/versions/latest"
    main.get_api_key(name)
    assert secret.init_kwargs == [
        {
            "client_options": {
                "api_endpoint": "secretmanager.us-central1.rep.googleapis.com"
            }
        }
    ]
    secret.access_secret_version.assert_called_once_with(name=name)


# --- fetch_positions ---------------------------------------------------------


def test_fetch_request_shape(stub_cta):
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    main.fetch_positions("test-key")
    assert len(calls) == 1
    assert calls[0]["url"] == main.POSITIONS_URL
    assert calls[0]["params"] == {
        "rt": ["Blue", "Red", "Brn", "G", "Org", "P", "Pink", "Y"],
        "key": "test-key",
        "outputType": "JSON",
    }
    assert calls[0]["timeout"] == main.REQUEST_TIMEOUT


def test_fetch_returns_ctatt_and_closes(stub_cta):
    ctatt = make_ctatt()
    resp = FakeResponse(200, {"ctatt": ctatt})
    stub_cta(lambda: resp)
    assert main.fetch_positions("test-key") == ctatt
    assert resp.closed


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
def test_fetch_unexpected_status(stub_cta, status):
    resp = FakeResponse(status)
    stub_cta(lambda: resp)
    with pytest.raises(requests.HTTPError) as exc_info:
        main.fetch_positions("test-key")
    assert exc_info.value.response is resp
    assert resp.closed


def test_fetch_error_does_not_expose_api_key(stub_cta):
    stub_cta(lambda: FakeResponse(500))
    with pytest.raises(requests.HTTPError) as exc_info:
        main.fetch_positions("super-secret-key")
    assert "super-secret-key" not in str(exc_info.value)


def test_fetch_missing_ctatt(stub_cta):
    stub_cta(lambda: FakeResponse(200, {"unexpected": {}}))
    with pytest.raises(KeyError):
        main.fetch_positions("test-key")


# --- _to_utc_iso -------------------------------------------------------------


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
    assert main._to_utc_iso(local) == want


def test_to_utc_iso_invalid():
    with pytest.raises(ValueError):
        main._to_utc_iso("not a timestamp")


# --- flatten_positions -------------------------------------------------------


def test_flatten_rows_match_table_schema():
    rows = main.flatten_positions(make_ctatt())
    columns = positions_schema_columns()
    for row in rows:
        assert sorted(row) == sorted(columns)


def test_flatten_one_row_per_train():
    rows = main.flatten_positions(make_ctatt())
    assert [(r["name"], r["rn"]) for r in rows] == [
        ("red", "801"),
        ("red", "802"),
        ("blue", "101"),
    ]


def test_flatten_values():
    (row,) = main.flatten_positions(
        make_ctatt(routes=[{"@name": "red", "train": [make_train("801")]}])
    )
    assert row == {
        "tmst": "2026-10-06T22:01:23+00:00",
        "errCd": "0",
        "errNm": "",
        "name": "red",
        "rn": "801",
        "destSt": "30089",
        "destNm": "95th/Dan Ryan",
        "trDr": "5",
        "nextStaId": "41450",
        "nextStpId": "30282",
        "nextStaNm": "Chicago",
        "prdt": "2026-10-06T17:00:58",
        "arrT": "2026-10-06T17:02:58",
        "isApp": "0",
        "isDly": "0",
        "flags": "",
        "lat": "41.89681",
        "lon": "-87.62838",
        "heading": "178",
    }


def test_flatten_single_train_object():
    rows = main.flatten_positions(
        make_ctatt(routes=[{"@name": "y", "train": make_train("501")}])
    )
    assert [(r["name"], r["rn"]) for r in rows] == [("y", "501")]


def test_flatten_single_route_object():
    rows = main.flatten_positions(
        make_ctatt(routes={"@name": "p", "train": [make_train("501")]})
    )
    assert [(r["name"], r["rn"]) for r in rows] == [("p", "501")]


@pytest.mark.parametrize(
    "route",
    [{"@name": "p"}, {"@name": "p", "train": None}, {"@name": "p", "train": []}],
)
def test_flatten_route_without_trains(route):
    rows = main.flatten_positions(
        make_ctatt(routes=[route, {"@name": "red", "train": make_train("801")}])
    )
    assert [(r["name"], r["rn"]) for r in rows] == [("red", "801")]


@pytest.mark.parametrize("routes", [[], None])
def test_flatten_no_routes(routes):
    ctatt = make_ctatt()
    ctatt["route"] = routes
    assert main.flatten_positions(ctatt) == []


def test_flatten_no_route_key():
    ctatt = make_ctatt()
    del ctatt["route"]
    assert main.flatten_positions(ctatt) == []


def test_flatten_nulls_and_missing_fields_become_empty_strings():
    (row,) = main.flatten_positions(
        make_ctatt(routes=[{"@name": "red", "train": {"rn": "801", "lat": None}}])
    )
    assert row["rn"] == "801"
    assert row["lat"] == ""
    assert row["destNm"] == ""
    assert row["flags"] == ""


def test_flatten_values_are_strings():
    (row,) = main.flatten_positions(
        make_ctatt(
            routes=[{"@name": "red", "train": make_train(801, trDr=5, lat=41.9)}],
            err_cd=0,
        )
    )
    assert all(isinstance(value, str) for value in row.values())
    assert row["rn"] == "801"
    assert row["errCd"] == "0"


def test_flatten_drops_fields_not_in_schema():
    (row,) = main.flatten_positions(
        make_ctatt(routes=[{"@name": "red", "train": make_train(extra="x")}])
    )
    assert row["nextStpId"] == "30282"
    assert "extra" not in row


# --- write_to_bigquery -------------------------------------------------------


def test_write_inserts_rows_with_ids(bq):
    rows = main.flatten_positions(make_ctatt())
    main.write_to_bigquery(rows, "raw.positions")
    bq.insert_rows_json.assert_called_once_with(
        "raw.positions",
        rows,
        row_ids=[
            "2026-10-06T22:01:23+00:00-red-801",
            "2026-10-06T22:01:23+00:00-red-802",
            "2026-10-06T22:01:23+00:00-blue-101",
        ],
    )


def test_write_raises_on_insert_errors(bq):
    bq.insert_rows_json.return_value = [{"index": 0, "errors": ["bad row"]}]
    with pytest.raises(RuntimeError, match="bad row"):
        main.write_to_bigquery(main.flatten_positions(make_ctatt()), "raw.positions")


# --- handler -----------------------------------------------------------------


def test_handler_success(secret, bq, stub_cta):
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("", 200)
    assert calls[0]["params"]["key"] == "test-key"
    table, rows = bq.insert_rows_json.call_args.args
    assert table == main.DEFAULT_BQ_TABLE
    assert len(rows) == 3


def test_handler_uses_bq_table_env(secret, bq, stub_cta, monkeypatch):
    monkeypatch.setenv("BQ_TABLE", "proj.other.positions")
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("", 200)
    assert bq.insert_rows_json.call_args.args[0] == "proj.other.positions"


def test_handler_missing_secret_env(bq, stub_cta, monkeypatch):
    monkeypatch.delenv("CTA_API_KEY_SECRET", raising=False)
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Misconfigured CTA_API_KEY_SECRET", 500)
    assert calls == []
    bq.insert_rows_json.assert_not_called()


def test_handler_secret_error(secret, bq, stub_cta):
    secret.access_secret_version.side_effect = RuntimeError("denied")
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to read CTA API key", 500)
    assert calls == []
    bq.insert_rows_json.assert_not_called()


def test_handler_http_error(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(503))
    assert serve() == ("Failed to fetch train positions", 502)
    bq.insert_rows_json.assert_not_called()


def test_handler_connection_error(secret, bq, stub_cta):
    def fail():
        raise requests.ConnectionError("unreachable")

    stub_cta(fail)
    assert serve() == ("Failed to fetch train positions", 500)
    bq.insert_rows_json.assert_not_called()


def test_handler_invalid_json(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, json_error=ValueError("not json")))
    assert serve() == ("Failed to fetch train positions", 500)
    bq.insert_rows_json.assert_not_called()


@pytest.mark.parametrize("err_cd", ["101", 500])
def test_handler_cta_api_error(secret, bq, stub_cta, err_cd):
    ctatt = make_ctatt(routes=[], err_cd=err_cd, err_nm="Invalid API key")
    stub_cta(lambda: FakeResponse(200, {"ctatt": ctatt}))
    assert serve() == ("CTA API returned an error", 502)
    bq.insert_rows_json.assert_not_called()


def test_handler_accepts_integer_zero_err_cd(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(err_cd=0)}))
    assert serve() == ("", 200)
    bq.insert_rows_json.assert_called_once()


def test_handler_parse_error(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(tmst="garbage")}))
    assert serve() == ("Failed to parse train positions", 500)
    bq.insert_rows_json.assert_not_called()


def test_handler_no_trains(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(routes=[])}))
    assert serve() == ("", 200)
    bq.insert_rows_json.assert_not_called()


def test_handler_bigquery_error(secret, bq, stub_cta):
    bq.insert_rows_json.return_value = [{"index": 0, "errors": ["bad row"]}]
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to write train positions", 500)


def test_handler_bigquery_client_error(secret, bq, stub_cta):
    bq.insert_rows_json.side_effect = RuntimeError("quota exceeded")
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to write train positions", 500)


def test_handler_reuses_cached_api_key(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    serve()
    serve()
    assert secret.access_secret_version.call_count == 1
