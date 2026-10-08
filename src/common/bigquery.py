import functools
from datetime import UTC, datetime, timedelta

import google.auth
from google.cloud import bigquery_storage_v1
from google.cloud.bigquery_storage_v1 import types as bq_types
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_FIELD = descriptor_pb2.FieldDescriptorProto


class RowSchema:
    """A table row for the Storage Write API: a "tmst" TIMESTAMP plus STRINGs.

    TIMESTAMP columns are sent as int64 microseconds since the epoch; every other
    column is a STRING.
    """

    def __init__(self, message_name: str, string_columns: tuple[str, ...]):
        self.string_columns = string_columns
        self.descriptor = descriptor_pb2.DescriptorProto(name=message_name)
        for number, name in enumerate(("tmst", *string_columns), start=1):
            self.descriptor.field.add(
                name=name,
                number=number,
                type=_FIELD.TYPE_INT64 if name == "tmst" else _FIELD.TYPE_STRING,
                label=_FIELD.LABEL_OPTIONAL,
            )
        # A private pool keeps this message from clashing with other modules' types.
        pool = descriptor_pool.DescriptorPool()
        pool.Add(
            descriptor_pb2.FileDescriptorProto(
                name=f"{message_name}.proto",
                syntax="proto2",
                message_type=[self.descriptor],
            )
        )
        self.message_class = message_factory.GetMessageClass(
            pool.FindMessageTypeByName(message_name)
        )

    def serialize(self, row: dict) -> bytes:
        message = self.message_class(tmst=to_epoch_micros(row["tmst"]))
        for column in self.string_columns:
            setattr(message, column, row[column])
        return message.SerializeToString()


def to_epoch_micros(iso_timestamp: str) -> int:
    return (datetime.fromisoformat(iso_timestamp) - EPOCH) // timedelta(microseconds=1)


@functools.cache
def get_write_client() -> bigquery_storage_v1.BigQueryWriteClient:
    """Builds the Storage Write client once per instance so warm invocations reuse it."""
    return bigquery_storage_v1.BigQueryWriteClient()


@functools.cache
def get_project_id() -> str:
    """Resolves the project for table names given without one, e.g. raw.positions."""
    _, project = google.auth.default()
    if not project:
        raise RuntimeError("Could not determine the Google Cloud project")
    return project


def table_path(table: str) -> str:
    """Expands "dataset.table" or "project.dataset.table" to a resource path."""
    parts = table.split(".")
    if len(parts) == 2:
        parts.insert(0, get_project_id())
    if len(parts) != 3:
        raise ValueError(f"Invalid BigQuery table name: {table!r}")
    return bigquery_storage_v1.BigQueryWriteClient.table_path(*parts)


def write_to_bigquery(rows: list[dict], table: str, schema: RowSchema) -> None:
    """Appends rows through the Storage Write API's default stream.

    The default stream commits each append immediately with at-least-once
    semantics. It is billed far below legacy streaming inserts and has a 2 TiB
    monthly free tier.
    """
    stream = f"{table_path(table)}/streams/_default"
    request = bq_types.AppendRowsRequest(
        write_stream=stream,
        proto_rows=bq_types.AppendRowsRequest.ProtoData(
            writer_schema=bq_types.ProtoSchema(proto_descriptor=schema.descriptor),
            rows=bq_types.ProtoRows(
                serialized_rows=[schema.serialize(r) for r in rows]
            ),
        ),
    )
    # append_rows is a bidirectional stream, so the client can't derive the
    # routing header from the request; it has to be supplied here.
    responses = get_write_client().append_rows(
        iter([request]),
        metadata=(("x-goog-request-params", f"write_stream={stream}"),),
    )
    for response in responses:
        if response.row_errors:
            raise RuntimeError(f"BigQuery row errors: {list(response.row_errors)}")
        if response.error.code:
            raise RuntimeError(f"BigQuery append error: {response.error.message}")
