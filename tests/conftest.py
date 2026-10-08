import sys
from pathlib import Path

import pytest

# Each function's zip ships src/common as a top-level `common` package, so src/
# goes on the path to make it importable the same way.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common import bigquery, secrets


@pytest.fixture(autouse=True)
def clear_common_caches():
    secrets.get_api_key.cache_clear()
    bigquery.get_write_client.cache_clear()
    bigquery.get_project_id.cache_clear()
    yield
    secrets.get_api_key.cache_clear()
    bigquery.get_write_client.cache_clear()
    bigquery.get_project_id.cache_clear()
