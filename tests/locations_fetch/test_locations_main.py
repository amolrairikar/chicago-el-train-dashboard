import json
import re
from pathlib import Path
from unittest import mock

import locations_main as main
import pytest
import requests
from flask import Flask
from google.cloud.bigquery_storage_v1 import types as bq_types
from google.protobuf import descriptor_pb2

from common import bigquery, secrets

TF_PATH = Path(__file__).resolve().parents[2] / "infrastructure" / "main.tf"
PROJECT = "test-project"
DEFAULT_STREAM = f"projects/{PROJECT}/datasets/raw/tables/positions/streams/_default"
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
class FakeWriteClient:
    """Stands in for BigQueryWriteClient; records each append as decoded rows."""

    def __init__(self):
        self.calls = []
        self.response = bq_types.AppendRowsResponse()
        self.error = None

    def append_rows(self, requests, metadata=()):
        if self.error:
            raise self.error
        for request in requests:
            rows = [decode_row(row) for row in request.proto_rows.rows.serialized_rows]
            self.calls.append(
                {
                    "stream": request.write_stream,
                    "schema": request.proto_rows.writer_schema.proto_descriptor,
                    "rows": rows,
                    "metadata": metadata,
                }
            )
        return iter([self.response])

    def last(self):
        call = self.calls[-1]
        return call["stream"], call["rows"]


def decode_row(serialized: bytes) -> dict:
    message = main.ROW_SCHEMA.message_class.FromString(serialized)
    return {
        field.name: getattr(message, field.name) for field in message.DESCRIPTOR.fields
    }


def row_error_response():
    return bq_types.AppendRowsResponse(
        row_errors=[bq_types.RowError(index=0, message="bad row")]
    )


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


@pytest.fixture
def secret(monkeypatch):
    """Fakes Secret Manager; the returned client records access calls."""
    client = mock.Mock()
    client.access_secret_version.return_value.payload.data = b"test-key\n"
    client.init_kwargs = []

    def make_client(**kwargs):
        client.init_kwargs.append(kwargs)
        return client

    monkeypatch.setattr(
        secrets.secretmanager, "SecretManagerServiceClient", make_client
    )
    monkeypatch.setenv("CTA_API_KEY_SECRET", SECRET_NAME)
    return client


@pytest.fixture
def bq(monkeypatch):
    """Fakes the Storage Write API; the returned client records appends."""
    client = FakeWriteClient()
    monkeypatch.setattr(bigquery, "get_write_client", lambda: client)
    monkeypatch.setattr(bigquery.google.auth, "default", lambda: (None, PROJECT))
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


def test_write_appends_rows_to_default_stream(bq):
    rows = main.flatten_positions(make_ctatt())
    main.write_to_bigquery(rows, "raw.positions", main.ROW_SCHEMA)
    (call,) = bq.calls
    assert call["stream"] == DEFAULT_STREAM
    # The routing header must name the stream for the bidirectional append.
    assert call["metadata"] == (
        ("x-goog-request-params", f"write_stream={DEFAULT_STREAM}"),
    )
    assert call["schema"] == main.ROW_SCHEMA.descriptor
    want = [{**row, "tmst": bigquery.to_epoch_micros(row["tmst"])} for row in rows]
    assert call["rows"] == want


def test_row_descriptor_matches_table_schema():
    fields = {field.name: field.type for field in main.ROW_SCHEMA.descriptor.field}
    assert sorted(fields) == sorted(positions_schema_columns())
    # TIMESTAMP columns take int64 epoch microseconds; the rest are STRING.
    int64 = descriptor_pb2.FieldDescriptorProto.TYPE_INT64
    assert {name for name, kind in fields.items() if kind == int64} == {"tmst"}


# --- handler -----------------------------------------------------------------


def test_handler_success(secret, bq, stub_cta):
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("", 200)
    assert calls[0]["params"]["key"] == "test-key"
    stream, rows = bq.last()
    assert stream == DEFAULT_STREAM
    assert len(rows) == 3


def test_handler_uses_bq_table_env(secret, bq, stub_cta, monkeypatch):
    monkeypatch.setenv("BQ_TABLE", "proj.other.positions")
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("", 200)
    assert bq.last()[0] == (
        "projects/proj/datasets/other/tables/positions/streams/_default"
    )


def test_handler_missing_secret_env(bq, stub_cta, monkeypatch):
    monkeypatch.delenv("CTA_API_KEY_SECRET", raising=False)
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Misconfigured CTA_API_KEY_SECRET", 500)
    assert calls == []
    assert bq.calls == []


def test_handler_secret_error(secret, bq, stub_cta):
    secret.access_secret_version.side_effect = RuntimeError("denied")
    calls = stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to read CTA API key", 500)
    assert calls == []
    assert bq.calls == []


def test_handler_http_error(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(503))
    assert serve() == ("Failed to fetch train positions", 502)
    assert bq.calls == []


def test_handler_connection_error(secret, bq, stub_cta):
    def fail():
        raise requests.ConnectionError("unreachable")

    stub_cta(fail)
    assert serve() == ("Failed to fetch train positions", 500)
    assert bq.calls == []


def test_handler_invalid_json(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, json_error=ValueError("not json")))
    assert serve() == ("Failed to fetch train positions", 500)
    assert bq.calls == []


@pytest.mark.parametrize("err_cd", ["101", 500])
def test_handler_cta_api_error(secret, bq, stub_cta, err_cd):
    ctatt = make_ctatt(routes=[], err_cd=err_cd, err_nm="Invalid API key")
    stub_cta(lambda: FakeResponse(200, {"ctatt": ctatt}))
    assert serve() == ("CTA API returned an error", 502)
    assert bq.calls == []


def test_handler_accepts_integer_zero_err_cd(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(err_cd=0)}))
    assert serve() == ("", 200)
    assert len(bq.calls) == 1


def test_handler_parse_error(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(tmst="garbage")}))
    assert serve() == ("Failed to parse train positions", 500)
    assert bq.calls == []


def test_handler_no_trains(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt(routes=[])}))
    assert serve() == ("", 200)
    assert bq.calls == []


def test_handler_bigquery_error(secret, bq, stub_cta):
    bq.response = row_error_response()
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to write train positions", 500)


def test_handler_bigquery_client_error(secret, bq, stub_cta):
    bq.error = RuntimeError("quota exceeded")
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    assert serve() == ("Failed to write train positions", 500)


def test_handler_reuses_cached_api_key(secret, bq, stub_cta):
    stub_cta(lambda: FakeResponse(200, {"ctatt": make_ctatt()}))
    serve()
    serve()
    assert secret.access_secret_version.call_count == 1
