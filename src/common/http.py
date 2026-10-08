import requests
from requests.adapters import DEFAULT_POOLSIZE, HTTPAdapter
from urllib3.util.retry import Retry


def build_session(pool_maxsize: int = DEFAULT_POOLSIZE) -> requests.Session:
    """Builds a session that retries GETs on connection errors and 429/5xx.

    pool_maxsize should cover the number of threads sharing the session so
    parallel requests reuse connections.
    """
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        # Return the final response instead of raising so its status can be reported.
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_maxsize)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
