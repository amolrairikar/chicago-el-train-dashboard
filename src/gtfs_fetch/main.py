import logging
import mimetypes
import os
import posixpath
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import functions_framework
import requests
from flask import Request
from google.cloud import storage
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GTFS_URL = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
GTFS_OBJECT_KEY = "gtfs/google_transit.zip"
# Unzipped files are written alongside the zip, e.g. gtfs/stops.txt.
GTFS_PREFIX = posixpath.dirname(GTFS_OBJECT_KEY)
LAST_MODIFIED_KEY = "source-last-modified"
REQUEST_TIMEOUT = (10, 60)  # (connect, read) timeouts in seconds
CHUNK_SIZE = 1024 * 1024  # 1 MB chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        # Return the final response instead of raising so its status can be reported.
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


http_session = build_session()


@functions_framework.http
def handler(request: Request):
    logger.info("Beginning GTFS data fetch execution")

    bucket_name = os.environ.get("GCS_BUCKET")
    if not bucket_name:
        logger.error("GCS_BUCKET environment variable is not set")
        return "Misconfigured GCS_BUCKET", 500
    blob = storage.Client().bucket(bucket_name).blob(GTFS_OBJECT_KEY)

    try:
        prev_last_modified = get_last_modified(blob)
    except Exception:
        logger.exception("Error reading GCS object attributes")
        return "Failed to read GCS object attributes", 500

    try:
        resp, last_modified = fetch_gtfs_data(prev_last_modified)
    except requests.HTTPError:
        logger.exception("Error fetching GTFS data")
        return "Failed to fetch GTFS data", 502
    except Exception:
        logger.exception("Error fetching GTFS data")
        return "Failed to fetch GTFS data", 500
    if resp is None:
        logger.info(
            "GTFS data not modified since %s - skipping upload", prev_last_modified
        )
        return "", 200

    # zipfile needs a seekable file, so the body is buffered locally before
    # extraction rather than streamed straight through.
    with resp, tempfile.TemporaryFile() as zip_file:
        try:
            download_to_file(resp.iter_content(CHUNK_SIZE), zip_file)
        except Exception:
            logger.exception("Error downloading GTFS data")
            return "Failed to download GTFS data", 500

        try:
            names = extract_to_gcs(blob.bucket, zip_file, GTFS_PREFIX)
        except Exception:
            logger.exception("Error extracting GTFS data to GCS")
            return "Failed to extract GTFS data", 500
        logger.info(
            "Extracted %d GTFS files to gs://%s/%s/",
            len(names),
            bucket_name,
            GTFS_PREFIX,
        )

        # The zip carries the Last-Modified marker, so it is uploaded last: if
        # extraction fails, the next run sees the old marker and retries.
        try:
            zip_file.seek(0)
            upload_to_gcs(blob, zip_file, last_modified)
        except Exception:
            logger.exception("Error uploading GTFS data to GCS")
            return "Failed to upload GTFS data", 500
    logger.info("Uploaded GTFS data to gs://%s/%s", bucket_name, GTFS_OBJECT_KEY)
    return "", 200


def fetch_gtfs_data(
    if_modified_since: str,
) -> tuple[requests.Response | None, str]:
    """Fetches the GTFS zip, returning (None, "") if it hasn't changed.

    On success the returned response is streaming and the caller must close it.
    """
    headers = {}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since

    resp = http_session.get(
        GTFS_URL, headers=headers, stream=True, timeout=REQUEST_TIMEOUT
    )

    if resp.status_code == 304:
        resp.close()
        return None, ""
    if resp.status_code != 200:
        resp.close()
        raise requests.HTTPError(
            f"unexpected status fetching GTFS data: {resp.status_code} {resp.reason}",
            response=resp,
        )

    last_modified = resp.headers.get("Last-Modified", "")
    logger.info("Fetched Last-Modified: %s", last_modified)

    # Fallback in case the server ignores If-Modified-Since and returns a full 200.
    if if_modified_since and not is_gtfs_updated(last_modified, if_modified_since):
        resp.close()
        return None, ""
    return resp, last_modified


def _parse_http_date(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    # ANSI C asctime dates carry no zone; HTTP dates are always GMT.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def is_gtfs_updated(fetched_last_modified: str, stored_last_modified: str) -> bool:
    # If either fetched or stored last modified value can't be parsed, treat the file as changed
    try:
        fetched_mod_time = _parse_http_date(fetched_last_modified)
        stored_mod_time = _parse_http_date(stored_last_modified)
    except (TypeError, ValueError):
        return True
    return fetched_mod_time > stored_mod_time


def get_last_modified(blob: storage.Blob) -> str:
    existing = blob.bucket.get_blob(blob.name)
    if existing is None:
        logger.info("No existing GTFS object in GCS; fetching for the first time")
        return ""
    last_modified = (existing.metadata or {}).get(LAST_MODIFIED_KEY, "")
    logger.info("Stored Last-Modified: %s", last_modified)
    return last_modified


def download_to_file(chunks, file) -> None:
    for chunk in chunks:
        file.write(chunk)
    file.seek(0)


def extract_to_gcs(bucket: storage.Bucket, zip_file, prefix: str) -> list[str]:
    """Streams each file in the zip to gs://<bucket>/<prefix>/<name>.

    Returns the object names written.
    """
    written = []
    with zipfile.ZipFile(zip_file) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            object_name = f"{prefix}/{info.filename}"
            content_type = (
                mimetypes.guess_type(info.filename)[0] or "application/octet-stream"
            )
            with (
                archive.open(info) as src,
                bucket.blob(object_name).open("wb", content_type=content_type) as dst,
            ):
                shutil.copyfileobj(src, dst, CHUNK_SIZE)
            written.append(object_name)
    return written


def upload_to_gcs(blob: storage.Blob, file, last_modified: str) -> None:
    """Streams file to blob, recording last_modified as custom metadata."""
    if last_modified:
        blob.metadata = {LAST_MODIFIED_KEY: last_modified}
    # Exiting the writer with an exception cancels the resumable upload, so a
    # partial body is never committed.
    with blob.open("wb", content_type="application/zip") as writer:
        shutil.copyfileobj(file, writer, CHUNK_SIZE)
