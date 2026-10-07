import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import arrivals_main as main
import pytest
import requests
from flask import Flask
from google.cloud.bigquery_storage_v1 import types as bq_types

TF_PATH = Path(__file__).resolve().parents[2] / "infrastructure" / "main.tf"
PROJECT = "test-project"
DEFAULT_STREAM = f"projects/{PROJECT}/datasets/raw/tables/arrivals/streams/_default"
SECRET_NAME = "projects/test/secrets/cta-api-key/versions/latest"
BUCKET = "test-bucket"
STOPS_TXT = """stop_id,stop_code,stop_name,stop_desc,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding
1,1,Jackson & Austin Terminal,,41.876,-87.774,0,,1
30022,,35th/Archer (Loop-bound),,41.829,-87.680,0,40120,1
40830,,18th,,41.857,-87.669,1,,1
40120,,35th/Archer,,41.829,-87.680,1,,1
41080,,47th,,41.810,-87.618,1,,1
41120,,35th-Bronzeville-IIT,,41.831,-87.625,1,,1
40120,,35th/Archer,,41.829,-87.680,1,,1
39999,,Below threshold,,41.0,-87.0,0,,1
50000,,Above threshold,,41.0,-87.0,0,,1
abc,,Not numeric,,41.0,-87.0,0,,1
"""


def make_eta(sta_id="40120", stp_id="30022", rn="723", **overrides):
    eta = {
        "staId": sta_id,
        "stpId": stp_id,
        "staNm": "35th/Archer",
        "stpDe": "Service toward Loop",
        "rn": rn,
        "rt": "Org",
        "destSt": "30182",
        "destNm": "Loop",
        "trDr": "1",
        "prdt": "2026-10-06T21:39:48",
        "arrT": "2026-10-06T21:43:48",
        "isApp": "0",
        "isSch": "0",
        "isDly": "0",
        "isFlt": "0",
        "flags": None,
        "lat": "41.80468",
        "lon": "-87.68402",
        "heading": "88",
    }
    eta.update(overrides)
    return eta


def make_ctatt(etas=None, tmst="2026-10-06T21:40:29", err_cd="0", err_nm=None):
    if etas is None:
        etas = [make_eta(rn="723"), make_eta(stp_id="30023", rn="723")]
    return {"tmst": tmst, "errCd": err_cd, "errNm": err_nm, "eta": etas}


def ctatt_for(map_ids):
    """Builds a response with one arrival per requested station."""
    return make_ctatt(etas=[make_eta(sta_id=map_id) for map_id in map_ids])


def arrivals_schema_columns():
    """Reads the column names of the raw.arrivals table from Terraform."""
    tf = TF_PATH.read_text()
    match = re.search(
        r'resource "google_bigquery_table" "arrivals_table".*?schema = <<EOF\n(.*?)\nEOF',
        tf,
        re.DOTALL,
    )
    assert match, "arrivals_table schema not found in main.tf"
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
    message = main.RowMessage.FromString(serialized)
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


@pytest.fixture(autouse=True)
def clear_caches():
    main.get_api_key.cache_clear()
    main._load_station_ids.cache_clear()
    main.get_write_client.cache_clear()
    main.get_project_id.cache_clear()
    main.get_storage_client.cache_clear()
    yield
    main.get_api_key.cache_clear()
    main._load_station_ids.cache_clear()
    main.get_write_client.cache_clear()
    main.get_project_id.cache_clear()
    main.get_storage_client.cache_clear()


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
def gcs(monkeypatch):
    """Fakes GCS serving STOPS_TXT; the returned client records blob calls."""
    client = mock.Mock()
    bucket = client.bucket.return_value
    bucket.get_blob.return_value.generation = 1
    bucket.blob.return_value.download_as_text.return_value = STOPS_TXT
    monkeypatch.setattr(main.storage, "Client", lambda: client)
    monkeypatch.setenv("GCS_BUCKET", BUCKET)
    return client


@pytest.fixture
def bq(monkeypatch):
    """Fakes the Storage Write API; the returned client records appends."""
    client = FakeWriteClient()
    monkeypatch.setattr(main, "get_write_client", lambda: client)
    monkeypatch.setattr(main.google.auth, "default", lambda: (None, PROJECT))
    monkeypatch.delenv("BQ_TABLE", raising=False)
    return client


@pytest.fixture
def stub_cta(monkeypatch):
    """Replaces http_session.get; returns the list of recorded request kwargs.

    The installed fn is called with the requested mapids.
    """

    def install(fn):
        calls = []

        def get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return fn(tuple(kwargs["params"]["mapid"]))

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
        adapter = session.get_adapter(prefix + "example.com")
        retry = adapter.max_retries
        assert retry.total == 3
        assert retry.backoff_factor == 1
        assert {500, 502, 503, 504, 429} <= set(retry.status_forcelist)
        assert "GET" in retry.allowed_methods
        assert retry.raise_on_status is False
        assert adapter._pool_maxsize == main.MAX_WORKERS


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


# --- get_station_ids ---------------------------------------------------------


def test_station_ids_filtered_deduped_and_sorted(gcs):
    assert main.get_station_ids(BUCKET) == ["40120", "40830", "41080", "41120"]
    gcs.bucket.assert_called_with(BUCKET)
    gcs.bucket.return_value.get_blob.assert_called_once_with(main.STOPS_OBJECT_KEY)
    gcs.bucket.return_value.blob.assert_called_once_with(
        main.STOPS_OBJECT_KEY, generation=1
    )


def test_station_ids_cached_per_generation(gcs):
    download = gcs.bucket.return_value.blob.return_value.download_as_text
    main.get_station_ids(BUCKET)
    main.get_station_ids(BUCKET)
    assert download.call_count == 1

    gcs.bucket.return_value.get_blob.return_value.generation = 2
    main.get_station_ids(BUCKET)
    assert download.call_count == 2


def test_station_ids_missing_blob(gcs):
    gcs.bucket.return_value.get_blob.return_value = None
    with pytest.raises(FileNotFoundError):
        main.get_station_ids(BUCKET)


def test_station_ids_empty_file(gcs):
    gcs.bucket.return_value.blob.return_value.download_as_text.return_value = (
        "stop_id,stop_name\n"
    )
    assert main.get_station_ids(BUCKET) == []


# --- fetch_arrivals ----------------------------------------------------------


def test_fetch_request_shape(stub_cta):
    calls = stub_cta(lambda ids: FakeResponse(200, {"ctatt": make_ctatt()}))
    main.fetch_arrivals("test-key", ("40120", "40830"))
    assert len(calls) == 1
    assert calls[0]["url"] == main.ARRIVALS_URL
    assert calls[0]["params"] == {
        "mapid": ["40120", "40830"],
        "key": "test-key",
        "outputType": "JSON",
    }
    assert calls[0]["timeout"] == main.REQUEST_TIMEOUT


def test_fetch_returns_ctatt_and_closes(stub_cta):
    ctatt = make_ctatt()
    resp = FakeResponse(200, {"ctatt": ctatt})
    stub_cta(lambda ids: resp)
    assert main.fetch_arrivals("test-key", ("40120",)) == ctatt
    assert resp.closed


@pytest.mark.parametrize("status", [400, 403, 500, 503])
def test_fetch_unexpected_status(stub_cta, status):
    resp = FakeResponse(status)
    stub_cta(lambda ids: resp)
    with pytest.raises(requests.HTTPError) as exc_info:
        main.fetch_arrivals("test-key", ("40120",))
    assert exc_info.value.response is resp
    assert resp.closed


def test_fetch_error_does_not_expose_api_key(stub_cta):
    stub_cta(lambda ids: FakeResponse(500))
    with pytest.raises(requests.HTTPError) as exc_info:
        main.fetch_arrivals("super-secret-key", ("40120",))
    assert "super-secret-key" not in str(exc_info.value)


def test_fetch_missing_ctatt(stub_cta):
    stub_cta(lambda ids: FakeResponse(200, {"unexpected": {}}))
    with pytest.raises(KeyError):
        main.fetch_arrivals("test-key", ("40120",))


# --- fetch_all ---------------------------------------------------------------


STATION_IDS = [str(40000 + i) for i in range(10)]


def test_fetch_all_batches_of_four(stub_cta):
    calls = stub_cta(lambda ids: FakeResponse(200, {"ctatt": ctatt_for(ids)}))
    rows, failed = main.fetch_all("test-key", STATION_IDS)
    batches = sorted(call["params"]["mapid"] for call in calls)
    assert batches == [STATION_IDS[0:4], STATION_IDS[4:8], STATION_IDS[8:10]]
    assert sorted(row["staId"] for row in rows) == STATION_IDS
    assert failed == []


def test_fetch_all_records_exception_batches(stub_cta):
    def respond(ids):
        if "40004" in ids:
            raise requests.ConnectionError("unreachable")
        if "40008" in ids:
            return FakeResponse(503)
        return FakeResponse(200, {"ctatt": ctatt_for(ids)})

    stub_cta(respond)
    rows, failed = main.fetch_all("test-key", STATION_IDS)
    assert sorted(row["staId"] for row in rows) == STATION_IDS[0:4]
    assert sorted(failed) == [tuple(STATION_IDS[4:8]), tuple(STATION_IDS[8:10])]


@pytest.mark.parametrize("err_cd", ["101", 500])
def test_fetch_all_records_cta_error_batches(stub_cta, err_cd):
    def respond(ids):
        if "40000" in ids:
            ctatt = make_ctatt(etas=[], err_cd=err_cd, err_nm="Invalid mapid")
            return FakeResponse(200, {"ctatt": ctatt})
        return FakeResponse(200, {"ctatt": ctatt_for(ids)})

    stub_cta(respond)
    rows, failed = main.fetch_all("test-key", STATION_IDS)
    assert sorted(row["staId"] for row in rows) == STATION_IDS[4:]
    assert failed == [tuple(STATION_IDS[0:4])]


def test_fetch_all_accepts_integer_zero_err_cd(stub_cta):
    stub_cta(lambda ids: FakeResponse(200, {"ctatt": make_ctatt(err_cd=0)}))
    rows, failed = main.fetch_all("test-key", ["40120"])
    assert len(rows) == 2
    assert failed == []


def test_fetch_all_records_parse_errors(stub_cta):
    stub_cta(lambda ids: FakeResponse(200, {"ctatt": make_ctatt(tmst="garbage")}))
    rows, failed = main.fetch_all("test-key", ["40120"])
    assert rows == []
    assert failed == [("40120",)]


def test_fetch_all_deadline_keeps_finished_batches(stub_cta):
    release = threading.Event()

    def respond(ids):
        if "40004" in ids:
            release.wait(timeout=5)  # Simulates a request hung past the deadline.
        return FakeResponse(200, {"ctatt": ctatt_for(ids)})

    stub_cta(respond)
    try:
        start = time.monotonic()
        rows, failed = main.fetch_all("test-key", STATION_IDS, deadline=0.2)
        elapsed = time.monotonic() - start
    finally:
        release.set()
    assert elapsed < 1  # Returned at the deadline without joining the hung request.
    assert sorted(row["staId"] for row in rows) == STATION_IDS[0:4] + STATION_IDS[8:]
    assert failed == [tuple(STATION_IDS[4:8])]


def test_fetch_all_deadline_cancels_queued_batches(stub_cta, monkeypatch):
    monkeypatch.setattr(main, "MAX_WORKERS", 1)
    release = threading.Event()

    def respond(ids):
        release.wait(timeout=5)  # Holds the only worker past the deadline.
        return FakeResponse(200, {"ctatt": ctatt_for(ids)})

    calls = stub_cta(respond)
    try:
        rows, failed = main.fetch_all("test-key", STATION_IDS, deadline=0.2)
    finally:
        release.set()
    assert rows == []
    assert sorted(failed) == [
        tuple(STATION_IDS[0:4]),
        tuple(STATION_IDS[4:8]),
        tuple(STATION_IDS[8:10]),
    ]
    assert len(calls) == 1  # The queued batches never started.


# --- _to_utc_iso -------------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "want"),
    [
        # Central Daylight Time (UTC-5)
        ("2026-10-06T21:40:29", "2026-10-07T02:40:29+00:00"),
        # Central Standard Time (UTC-6)
        ("2026-01-15T08:00:00", "2026-01-15T14:00:00+00:00"),
    ],
)
def test_to_utc_iso(local, want):
    assert main._to_utc_iso(local) == want


# --- flatten_arrivals --------------------------------------------------------


def test_flatten_rows_match_table_schema():
    rows = main.flatten_arrivals(make_ctatt())
    columns = arrivals_schema_columns()
    for row in rows:
        assert sorted(row) == sorted(columns)


def test_flatten_values():
    (row,) = main.flatten_arrivals(make_ctatt(etas=[make_eta()]))
    assert row == {
        "tmst": "2026-10-07T02:40:29+00:00",
        "errCd": "0",
        "errNm": "",
        "staId": "40120",
        "stpId": "30022",
        "staNm": "35th/Archer",
        "stpDe": "Service toward Loop",
        "rn": "723",
        "rt": "Org",
        "destSt": "30182",
        "destNm": "Loop",
        "trDr": "1",
        "prdt": "2026-10-06T21:39:48",
        "arrT": "2026-10-06T21:43:48",
        "isApp": "0",
        "isSch": "0",
        "isDly": "0",
        "isFlt": "0",
        "flags": "",
        "lat": "41.80468",
        "lon": "-87.68402",
        "heading": "88",
    }


def test_flatten_scheduled_arrival_nulls_become_empty_strings():
    (row,) = main.flatten_arrivals(
        make_ctatt(etas=[make_eta(isSch="1", lat=None, lon=None, heading=None)])
    )
    assert row["isSch"] == "1"
    assert (row["lat"], row["lon"], row["heading"]) == ("", "", "")


def test_flatten_values_are_strings():
    (row,) = main.flatten_arrivals(
        make_ctatt(etas=[make_eta(rn=723, trDr=1, lat=41.8)], err_cd=0)
    )
    assert all(isinstance(value, str) for value in row.values())
    assert row["rn"] == "723"
    assert row["errCd"] == "0"


def test_flatten_single_eta_object():
    rows = main.flatten_arrivals(make_ctatt(etas=make_eta(rn="501")))
    assert [row["rn"] for row in rows] == ["501"]


@pytest.mark.parametrize("etas", [[], None])
def test_flatten_no_etas(etas):
    ctatt = make_ctatt()
    ctatt["eta"] = etas
    assert main.flatten_arrivals(ctatt) == []


def test_flatten_no_eta_key():
    ctatt = make_ctatt()
    del ctatt["eta"]
    assert main.flatten_arrivals(ctatt) == []


def test_flatten_drops_fields_not_in_schema():
    (row,) = main.flatten_arrivals(make_ctatt(etas=[make_eta(extra="x")]))
    assert "extra" not in row


# --- write_to_bigquery -------------------------------------------------------


def test_write_appends_rows_to_default_stream(bq):
    rows = main.flatten_arrivals(make_ctatt())
    main.write_to_bigquery(rows, "raw.arrivals")
    (call,) = bq.calls
    assert call["stream"] == DEFAULT_STREAM
    # The routing header must name the stream for the bidirectional append.
    assert call["metadata"] == (
        ("x-goog-request-params", f"write_stream={DEFAULT_STREAM}"),
    )
    assert call["schema"] == main.ROW_DESCRIPTOR
    want = [{**row, "tmst": main._to_epoch_micros(row["tmst"])} for row in rows]
    assert call["rows"] == want


def test_write_raises_on_row_errors(bq):
    bq.response = row_error_response()
    with pytest.raises(RuntimeError, match="bad row"):
        main.write_to_bigquery(main.flatten_arrivals(make_ctatt()), "raw.arrivals")


def test_write_raises_on_append_error(bq):
    bq.response = bq_types.AppendRowsResponse(
        error={"code": 3, "message": "bad schema"}
    )
    with pytest.raises(RuntimeError, match="bad schema"):
        main.write_to_bigquery(main.flatten_arrivals(make_ctatt()), "raw.arrivals")


def test_row_descriptor_matches_table_schema():
    fields = {field.name: field.type for field in main.ROW_DESCRIPTOR.field}
    assert sorted(fields) == sorted(arrivals_schema_columns())
    # TIMESTAMP columns take int64 epoch microseconds; the rest are STRING.
    int64 = main._FIELD.TYPE_INT64
    assert {name for name, kind in fields.items() if kind == int64} == {"tmst"}


def test_to_epoch_micros():
    assert main._to_epoch_micros("2026-10-07T02:40:29+00:00") == 1791340829000000


@pytest.mark.parametrize(
    ("table", "want"),
    [
        ("raw.arrivals", f"projects/{PROJECT}/datasets/raw/tables/arrivals"),
        ("proj.other.arrivals", "projects/proj/datasets/other/tables/arrivals"),
    ],
)
def test_table_path(bq, table, want):
    assert main.table_path(table) == want


@pytest.mark.parametrize("table", ["arrivals", "a.b.c.d"])
def test_table_path_rejects_invalid_names(bq, table):
    with pytest.raises(ValueError, match="Invalid BigQuery table name"):
        main.table_path(table)


def test_get_project_id_requires_project(monkeypatch):
    monkeypatch.setattr(main.google.auth, "default", lambda: (None, None))
    with pytest.raises(RuntimeError, match="project"):
        main.get_project_id()


# --- handler -----------------------------------------------------------------


def ok(ids):
    return FakeResponse(200, {"ctatt": ctatt_for(ids)})


def test_handler_success(secret, gcs, bq, stub_cta):
    calls = stub_cta(ok)
    assert serve() == ("", 200)
    assert len(calls) == 1
    assert calls[0]["params"]["key"] == "test-key"
    assert calls[0]["params"]["mapid"] == ["40120", "40830", "41080", "41120"]
    stream, rows = bq.last()
    assert stream == DEFAULT_STREAM
    assert len(rows) == 4


def test_handler_uses_bq_table_env(secret, gcs, bq, stub_cta, monkeypatch):
    monkeypatch.setenv("BQ_TABLE", "proj.other.arrivals")
    stub_cta(ok)
    assert serve() == ("", 200)
    assert bq.last()[0] == (
        "projects/proj/datasets/other/tables/arrivals/streams/_default"
    )


def test_handler_missing_secret_env(gcs, bq, stub_cta, monkeypatch):
    monkeypatch.delenv("CTA_API_KEY_SECRET", raising=False)
    calls = stub_cta(ok)
    assert serve() == ("Misconfigured CTA_API_KEY_SECRET", 500)
    assert calls == []


def test_handler_missing_bucket_env(secret, bq, stub_cta, monkeypatch):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    calls = stub_cta(ok)
    assert serve() == ("Misconfigured GCS_BUCKET", 500)
    assert calls == []


def test_handler_secret_error(secret, gcs, bq, stub_cta):
    secret.access_secret_version.side_effect = RuntimeError("denied")
    calls = stub_cta(ok)
    assert serve() == ("Failed to read CTA API key", 500)
    assert calls == []


def test_handler_stops_error(secret, gcs, bq, stub_cta):
    gcs.bucket.return_value.get_blob.side_effect = RuntimeError("forbidden")
    calls = stub_cta(ok)
    assert serve() == ("Failed to read station IDs", 500)
    assert calls == []


def test_handler_no_station_ids(secret, gcs, bq, stub_cta):
    gcs.bucket.return_value.blob.return_value.download_as_text.return_value = (
        "stop_id\n1\n"
    )
    calls = stub_cta(ok)
    assert serve() == ("No station IDs found", 500)
    assert calls == []


def test_handler_partial_failure_writes_successes(secret, gcs, bq, stub_cta):
    gcs.bucket.return_value.blob.return_value.download_as_text.return_value = (
        "stop_id\n" + "\n".join(STATION_IDS) + "\n"
    )

    def respond(ids):
        if "40004" in ids:
            return FakeResponse(503)
        return ok(ids)

    stub_cta(respond)
    assert serve() == ("Failed to fetch some train arrivals", 502)
    _, rows = bq.last()
    assert sorted(row["staId"] for row in rows) == STATION_IDS[0:4] + STATION_IDS[8:]


def test_handler_all_batches_fail(secret, gcs, bq, stub_cta):
    stub_cta(lambda ids: FakeResponse(503))
    assert serve() == ("Failed to fetch some train arrivals", 502)
    assert bq.calls == []


def test_handler_no_arrivals(secret, gcs, bq, stub_cta):
    stub_cta(lambda ids: FakeResponse(200, {"ctatt": make_ctatt(etas=[])}))
    assert serve() == ("", 200)
    assert bq.calls == []


def test_handler_bigquery_error(secret, gcs, bq, stub_cta):
    bq.response = row_error_response()
    stub_cta(ok)
    assert serve() == ("Failed to write train arrivals", 500)


def test_handler_reuses_caches(secret, gcs, bq, stub_cta):
    stub_cta(ok)
    serve()
    serve()
    assert secret.access_secret_version.call_count == 1
    download = gcs.bucket.return_value.blob.return_value.download_as_text
    assert download.call_count == 1


def _format(message: str, exc_info=None) -> str:
    record = logging.LogRecord(
        "urllib3.connectionpool", logging.WARNING, __file__, 1, message, None, exc_info
    )
    return main.RedactingFormatter(logging.BASIC_FORMAT).format(record)


def test_redacting_formatter_masks_key_in_retry_warning():
    url = "/api/1.0/ttarrivals.aspx?mapid=40120&key=secret-key&outputType=JSON"
    out = _format(f"Retrying (Retry(total=2)) after connection broken by 'x': {url}")
    assert "secret-key" not in out
    assert "key=[REDACTED]&outputType=JSON" in out


def test_redacting_formatter_masks_key_in_traceback():
    try:
        raise requests.ConnectionError(
            "Max retries exceeded with url: /api/1.0/ttarrivals.aspx?key=secret-key "
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
