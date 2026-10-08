import pytest
from google.cloud.bigquery_storage_v1 import types as bq_types
from google.protobuf import descriptor_pb2

from common import bigquery

PROJECT = "test-project"
SCHEMA = bigquery.RowSchema("TestRow", ("a", "b"))
DEFAULT_STREAM = f"projects/{PROJECT}/datasets/raw/tables/t/streams/_default"
ROWS = [
    {"tmst": "2026-10-07T02:40:29+00:00", "a": "1", "b": ""},
    {"tmst": "2026-10-07T02:40:30+00:00", "a": "2", "b": "x"},
]


class FakeWriteClient:
    """Stands in for BigQueryWriteClient; records each append request."""

    def __init__(self):
        self.calls = []
        self.response = bq_types.AppendRowsResponse()

    def append_rows(self, requests, metadata=()):
        for request in requests:
            self.calls.append((request, metadata))
        return iter([self.response])


@pytest.fixture
def bq(monkeypatch):
    client = FakeWriteClient()
    monkeypatch.setattr(bigquery, "get_write_client", lambda: client)
    monkeypatch.setattr(bigquery.google.auth, "default", lambda: (None, PROJECT))
    return client


# --- RowSchema ---------------------------------------------------------------


def test_row_schema_descriptor():
    fields = [(f.name, f.number, f.type) for f in SCHEMA.descriptor.field]
    string = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    int64 = descriptor_pb2.FieldDescriptorProto.TYPE_INT64
    assert fields == [("tmst", 1, int64), ("a", 2, string), ("b", 3, string)]


def test_row_schema_serialize_round_trips():
    message = SCHEMA.message_class.FromString(SCHEMA.serialize(ROWS[1]))
    assert message.tmst == bigquery.to_epoch_micros(ROWS[1]["tmst"])
    assert (message.a, message.b) == ("2", "x")


def test_row_schemas_with_same_name_do_not_clash():
    other = bigquery.RowSchema("TestRow", ("c",))
    message = other.message_class.FromString(
        other.serialize({"tmst": ROWS[0]["tmst"], "c": "z"})
    )
    assert message.c == "z"


def test_to_epoch_micros():
    assert bigquery.to_epoch_micros("2026-10-07T02:40:29+00:00") == 1791340829000000


# --- table_path / get_project_id ---------------------------------------------


@pytest.mark.parametrize(
    ("table", "want"),
    [
        ("raw.t", f"projects/{PROJECT}/datasets/raw/tables/t"),
        ("proj.other.t", "projects/proj/datasets/other/tables/t"),
    ],
)
def test_table_path(bq, table, want):
    assert bigquery.table_path(table) == want


@pytest.mark.parametrize("table", ["t", "a.b.c.d"])
def test_table_path_rejects_invalid_names(bq, table):
    with pytest.raises(ValueError, match="Invalid BigQuery table name"):
        bigquery.table_path(table)


def test_get_project_id_requires_project(monkeypatch):
    monkeypatch.setattr(bigquery.google.auth, "default", lambda: (None, None))
    with pytest.raises(RuntimeError, match="project"):
        bigquery.get_project_id()


# --- write_to_bigquery -------------------------------------------------------


def test_write_appends_rows_to_default_stream(bq):
    bigquery.write_to_bigquery(ROWS, "raw.t", SCHEMA)
    ((request, metadata),) = bq.calls
    assert request.write_stream == DEFAULT_STREAM
    # The routing header must name the stream for the bidirectional append.
    assert metadata == (("x-goog-request-params", f"write_stream={DEFAULT_STREAM}"),)
    assert request.proto_rows.writer_schema.proto_descriptor == SCHEMA.descriptor
    assert list(request.proto_rows.rows.serialized_rows) == [
        SCHEMA.serialize(row) for row in ROWS
    ]


def test_write_raises_on_row_errors(bq):
    bq.response = bq_types.AppendRowsResponse(
        row_errors=[bq_types.RowError(index=0, message="bad row")]
    )
    with pytest.raises(RuntimeError, match="bad row"):
        bigquery.write_to_bigquery(ROWS, "raw.t", SCHEMA)


def test_write_raises_on_append_error(bq):
    bq.response = bq_types.AppendRowsResponse(
        error={"code": 3, "message": "bad schema"}
    )
    with pytest.raises(RuntimeError, match="bad schema"):
        bigquery.write_to_bigquery(ROWS, "raw.t", SCHEMA)
