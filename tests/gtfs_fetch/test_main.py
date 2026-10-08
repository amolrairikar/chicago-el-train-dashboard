import io
import zipfile
from unittest import mock

import main
import pytest
import requests
from flask import Flask
from google.api_core.exceptions import Forbidden

OLDER_TIME = "Mon, 01 Sep 2025 12:00:00 GMT"
NEWER_TIME = "Wed, 01 Oct 2025 12:00:00 GMT"
TEST_BUCKET = "test-bucket"
GTFS_FILES = {
    "stops.txt": b"stop_id,stop_name\n1,Clark/Lake\n",
    "routes.txt": b"route_id\nRed\n",
}


def make_zip(files=GTFS_FILES, dirs=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for d in dirs:
            archive.writestr(zipfile.ZipInfo(d), b"")
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


def gtfs_key(name):
    return f"{main.GTFS_PREFIX}/{name}"


# --- fakes -------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for a streaming requests.Response."""

    def __init__(self, status_code, body=b"", last_modified="", error=None):
        self.status_code = status_code
        self._error = error
        self.reason = "reason"
        self.headers = {"Last-Modified": last_modified} if last_modified else {}
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size):
        yield self._body
        if self._error:
            raise self._error

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeWriter:
    def __init__(self, blob):
        self._blob = blob
        self._data = b""

    def write(self, data):
        self._data += data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Mirrors BlobWriter: an exception cancels the upload instead of committing it.
        if exc_type is None:
            self._blob.commit(self._data)


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name
        self.metadata = None
        self.data = b""
        self.content_type = None

    def open(self, mode, content_type=None):
        assert mode == "wb"
        self._pending_content_type = content_type
        return FakeWriter(self)

    def commit(self, data):
        self.bucket.uploads += 1
        failing = self.bucket.upload_error_names
        if self.bucket.upload_error and (failing is None or self.name in failing):
            raise self.bucket.upload_error
        self.data = data
        self.content_type = self._pending_content_type
        self.bucket.objects[self.name] = self


class FakeBucket:
    def __init__(self):
        self.objects = {}
        self.get_error = None
        self.upload_error = None
        # None fails every upload; otherwise only uploads to these object names.
        self.upload_error_names = None
        self.uploads = 0

    def blob(self, name):
        return FakeBlob(self, name)

    def get_blob(self, name):
        if self.get_error:
            raise self.get_error
        return self.objects.get(name)

    def put(self, name, data=b"", metadata=None):
        blob = FakeBlob(self, name)
        blob.data = data
        blob.metadata = metadata
        self.objects[name] = blob


@pytest.fixture
def bucket(monkeypatch):
    fake = FakeBucket()
    client = mock.Mock()
    client.bucket.return_value = fake
    monkeypatch.setattr(main.storage, "Client", lambda: client)
    monkeypatch.setenv("GCS_BUCKET", TEST_BUCKET)
    return fake


@pytest.fixture
def stub_gtfs(monkeypatch):
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


# --- is_gtfs_updated ---------------------------------------------------------


@pytest.mark.parametrize(
    ("fetched", "stored", "want"),
    [
        (NEWER_TIME, OLDER_TIME, True),
        (OLDER_TIME, NEWER_TIME, False),
        (OLDER_TIME, OLDER_TIME, False),
        ("Mon, 01 Sep 2025 12:00:01 GMT", OLDER_TIME, True),
        ("not a date", OLDER_TIME, True),
        (NEWER_TIME, "garbage", True),
        ("", OLDER_TIME, True),
        (NEWER_TIME, "", True),
        ("", "", True),
        ("Wednesday, 01-Oct-25 12:00:00 GMT", OLDER_TIME, True),
        ("Mon Sep  1 12:00:00 2025", NEWER_TIME, False),
        ("Mon Sep  1 12:00:00 2025", OLDER_TIME, False),
    ],
)
def test_is_gtfs_updated(fetched, stored, want):
    assert main.is_gtfs_updated(fetched, stored) is want


# --- fetch_gtfs_data ---------------------------------------------------------


def test_fetch_request_shape(stub_gtfs):
    calls = stub_gtfs(lambda: FakeResponse(200, b"zip", NEWER_TIME))
    main.fetch_gtfs_data("")
    assert len(calls) == 1
    assert calls[0]["url"] == main.GTFS_URL
    assert calls[0]["stream"] is True
    assert calls[0]["timeout"] == main.REQUEST_TIMEOUT


def test_fetch_no_if_modified_since(stub_gtfs):
    resp = FakeResponse(200, b"zip-bytes", NEWER_TIME)
    calls = stub_gtfs(lambda: resp)

    got, last_modified = main.fetch_gtfs_data("")
    assert got is resp
    assert "If-Modified-Since" not in calls[0]["headers"]
    assert last_modified == NEWER_TIME
    assert not resp.closed


def test_fetch_sends_if_modified_since(stub_gtfs):
    calls = stub_gtfs(lambda: FakeResponse(304))
    main.fetch_gtfs_data(OLDER_TIME)
    assert calls[0]["headers"]["If-Modified-Since"] == OLDER_TIME


def test_fetch_not_modified(stub_gtfs):
    resp = FakeResponse(304)
    stub_gtfs(lambda: resp)
    assert main.fetch_gtfs_data(OLDER_TIME) == (None, "")
    assert resp.closed


@pytest.mark.parametrize(
    ("stored", "fetched", "want_body", "want_last_mod"),
    [
        (OLDER_TIME, NEWER_TIME, True, NEWER_TIME),
        (OLDER_TIME, OLDER_TIME, False, ""),
        (NEWER_TIME, OLDER_TIME, False, ""),
        (OLDER_TIME, "", True, ""),
        ("garbage", NEWER_TIME, True, NEWER_TIME),
    ],
)
def test_fetch_server_ignores_if_modified_since(
    stub_gtfs, stored, fetched, want_body, want_last_mod
):
    resp = FakeResponse(200, b"zip", fetched)
    stub_gtfs(lambda: resp)

    got, last_modified = main.fetch_gtfs_data(stored)
    assert (got is not None) is want_body
    assert last_modified == want_last_mod
    assert resp.closed is not want_body


@pytest.mark.parametrize("status", [404, 403, 500, 503, 206])
def test_fetch_unexpected_status(stub_gtfs, status):
    resp = FakeResponse(status, b"error page")
    stub_gtfs(lambda: resp)

    with pytest.raises(requests.HTTPError, match=str(status)):
        main.fetch_gtfs_data("")
    assert resp.closed


def test_fetch_transport_error(stub_gtfs):
    def fail():
        raise requests.ConnectionError("connection refused")

    stub_gtfs(fail)
    with pytest.raises(requests.ConnectionError):
        main.fetch_gtfs_data("")


# --- get_last_modified -------------------------------------------------------


def test_get_last_modified_object_missing(bucket):
    assert main.get_last_modified(bucket.blob(main.GTFS_OBJECT_KEY)) == ""


@pytest.mark.parametrize(
    ("metadata", "want"),
    [
        ({main.LAST_MODIFIED_KEY: OLDER_TIME, "other": "x"}, OLDER_TIME),
        (None, ""),
        ({"foo": "bar"}, ""),
    ],
)
def test_get_last_modified_existing_object(bucket, metadata, want):
    bucket.put(main.GTFS_OBJECT_KEY, metadata=metadata)
    assert main.get_last_modified(bucket.blob(main.GTFS_OBJECT_KEY)) == want


def test_get_last_modified_storage_error(bucket):
    bucket.get_error = Forbidden("denied")
    with pytest.raises(Forbidden):
        main.get_last_modified(bucket.blob(main.GTFS_OBJECT_KEY))


# --- upload_to_gcs -----------------------------------------------------------


def test_upload_body_content_type_and_metadata(bucket):
    main.upload_to_gcs(
        bucket.blob(main.GTFS_OBJECT_KEY), io.BytesIO(b"zip-bytes"), NEWER_TIME
    )
    got = bucket.objects[main.GTFS_OBJECT_KEY]
    assert got.data == b"zip-bytes"
    assert got.content_type == "application/zip"
    assert got.metadata == {main.LAST_MODIFIED_KEY: NEWER_TIME}


def test_upload_omits_metadata_when_last_modified_empty(bucket):
    main.upload_to_gcs(bucket.blob(main.GTFS_OBJECT_KEY), io.BytesIO(b"zip"), "")
    assert not bucket.objects[main.GTFS_OBJECT_KEY].metadata


def test_upload_partial_body_error_leaves_existing_object(bucket):
    bucket.put(main.GTFS_OBJECT_KEY, b"old-zip", {main.LAST_MODIFIED_KEY: OLDER_TIME})

    class FailingFile(io.BytesIO):
        def read(self, *args):
            if self.tell():
                raise OSError("read failed")
            return super().read(*args)

    with pytest.raises(OSError):
        main.upload_to_gcs(
            bucket.blob(main.GTFS_OBJECT_KEY), FailingFile(b"partial"), NEWER_TIME
        )
    assert bucket.uploads == 0
    assert bucket.objects[main.GTFS_OBJECT_KEY].data == b"old-zip"


# --- download_to_file --------------------------------------------------------


def test_download_to_file_writes_chunks_and_rewinds():
    file = io.BytesIO()
    main.download_to_file([b"zip-", b"bytes"], file)
    assert file.tell() == 0
    assert file.read() == b"zip-bytes"


# --- extract_to_gcs ----------------------------------------------------------


def test_extract_writes_each_file_under_prefix(bucket):
    names = main.extract_to_gcs(bucket, io.BytesIO(make_zip()), main.GTFS_PREFIX)

    assert sorted(names) == sorted(gtfs_key(n) for n in GTFS_FILES)
    for name, data in GTFS_FILES.items():
        got = bucket.objects[gtfs_key(name)]
        assert got.data == data
        assert got.content_type == "text/plain"


def test_extract_skips_directories_and_keeps_nested_paths(bucket):
    archive = make_zip({"sub/shapes.txt": b"shape_id\n"}, dirs=["sub/"])
    names = main.extract_to_gcs(bucket, io.BytesIO(archive), main.GTFS_PREFIX)

    assert names == [gtfs_key("sub/shapes.txt")]
    assert set(bucket.objects) == {gtfs_key("sub/shapes.txt")}


def test_extract_unknown_extension_uses_octet_stream(bucket):
    archive = make_zip({"feed_info": b"x"})
    main.extract_to_gcs(bucket, io.BytesIO(archive), main.GTFS_PREFIX)
    assert bucket.objects[gtfs_key("feed_info")].content_type == (
        "application/octet-stream"
    )


def test_extract_invalid_zip_raises(bucket):
    with pytest.raises(zipfile.BadZipFile):
        main.extract_to_gcs(bucket, io.BytesIO(b"not a zip"), main.GTFS_PREFIX)
    assert bucket.uploads == 0


def test_extract_upload_error_raises(bucket):
    bucket.upload_error = Forbidden("denied")
    with pytest.raises(Forbidden):
        main.extract_to_gcs(bucket, io.BytesIO(make_zip()), main.GTFS_PREFIX)
    assert bucket.objects == {}


# --- handler -----------------------------------------------------------------


def _fail_if_called():
    raise AssertionError("GTFS source should not be called")


def test_handler_missing_bucket_env(bucket, stub_gtfs, monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "")
    calls = stub_gtfs(_fail_if_called)
    assert serve() == ("Misconfigured GCS_BUCKET", 500)
    assert calls == []


def test_handler_attrs_error(bucket, stub_gtfs):
    bucket.get_error = Forbidden("denied")
    calls = stub_gtfs(_fail_if_called)
    assert serve() == ("Failed to read GCS object attributes", 500)
    assert calls == []


def test_handler_first_run_uploads(bucket, stub_gtfs):
    body = make_zip()
    resp = FakeResponse(200, body, NEWER_TIME)
    calls = stub_gtfs(lambda: resp)

    assert serve() == ("", 200)
    assert "If-Modified-Since" not in calls[0]["headers"]
    got = bucket.objects[main.GTFS_OBJECT_KEY]
    assert got.data == body
    assert got.metadata == {main.LAST_MODIFIED_KEY: NEWER_TIME}
    for name, data in GTFS_FILES.items():
        assert bucket.objects[gtfs_key(name)].data == data
    assert resp.closed


def test_handler_updated_data_uploads(bucket, stub_gtfs):
    bucket.put(main.GTFS_OBJECT_KEY, b"old-zip", {main.LAST_MODIFIED_KEY: OLDER_TIME})
    bucket.put(gtfs_key("stops.txt"), b"old-stops")
    body = make_zip()
    calls = stub_gtfs(lambda: FakeResponse(200, body, NEWER_TIME))

    assert serve() == ("", 200)
    assert calls[0]["headers"]["If-Modified-Since"] == OLDER_TIME
    assert bucket.objects[main.GTFS_OBJECT_KEY].data == body
    assert bucket.objects[gtfs_key("stops.txt")].data == GTFS_FILES["stops.txt"]


@pytest.mark.parametrize(
    "response",
    [
        lambda: FakeResponse(304),
        lambda: FakeResponse(200, b"zip", OLDER_TIME),
    ],
    ids=["server returns 304", "server returns 200 with same Last-Modified"],
)
def test_handler_not_modified_skips_upload(bucket, stub_gtfs, response):
    bucket.put(main.GTFS_OBJECT_KEY, b"old-zip", {main.LAST_MODIFIED_KEY: OLDER_TIME})
    stub_gtfs(response)

    assert serve() == ("", 200)
    assert bucket.uploads == 0
    assert bucket.objects[main.GTFS_OBJECT_KEY].data == b"old-zip"


def _transport_error():
    raise requests.ConnectionError("no such host")


@pytest.mark.parametrize(
    ("response", "want_status"),
    [
        (lambda: FakeResponse(503), 502),
        (lambda: FakeResponse(404), 502),
        (_transport_error, 500),
    ],
    ids=["upstream 503", "upstream 404", "transport error"],
)
def test_handler_fetch_errors(bucket, stub_gtfs, response, want_status):
    stub_gtfs(response)
    assert serve() == ("Failed to fetch GTFS data", want_status)
    assert bucket.uploads == 0


def test_handler_download_error(bucket, stub_gtfs):
    resp = FakeResponse(
        200, b"partial", NEWER_TIME, error=requests.ConnectionError("reset")
    )
    stub_gtfs(lambda: resp)

    assert serve() == ("Failed to download GTFS data", 500)
    assert bucket.uploads == 0
    assert resp.closed


@pytest.mark.parametrize(
    ("body", "fail_names"),
    [
        (b"not a zip", None),
        (make_zip(), None),
        (make_zip(), {gtfs_key("routes.txt")}),
    ],
    ids=["invalid zip", "all uploads fail", "one file fails"],
)
def test_handler_extract_error_keeps_old_marker(bucket, stub_gtfs, body, fail_names):
    bucket.put(main.GTFS_OBJECT_KEY, b"old-zip", {main.LAST_MODIFIED_KEY: OLDER_TIME})
    bucket.upload_error = Forbidden("denied")
    bucket.upload_error_names = fail_names
    resp = FakeResponse(200, body, NEWER_TIME)
    stub_gtfs(lambda: resp)

    assert serve() == ("Failed to extract GTFS data", 500)
    # The zip (and its Last-Modified marker) is untouched so the next run retries.
    got = bucket.objects[main.GTFS_OBJECT_KEY]
    assert got.data == b"old-zip"
    assert got.metadata == {main.LAST_MODIFIED_KEY: OLDER_TIME}
    assert resp.closed


def test_handler_zip_upload_error(bucket, stub_gtfs):
    bucket.upload_error = Forbidden("denied")
    bucket.upload_error_names = {main.GTFS_OBJECT_KEY}
    resp = FakeResponse(200, make_zip(), NEWER_TIME)
    stub_gtfs(lambda: resp)

    assert serve() == ("Failed to upload GTFS data", 500)
    assert main.GTFS_OBJECT_KEY not in bucket.objects
    assert resp.closed
