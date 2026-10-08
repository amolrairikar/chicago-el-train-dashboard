from common.http import build_session


def test_session_has_retries_configured():
    session = build_session()
    for prefix in ("https://", "http://"):
        retry = session.get_adapter(prefix + "example.com").max_retries
        assert retry.total == 3
        assert retry.backoff_factor == 1
        assert {500, 502, 503, 504, 429} <= set(retry.status_forcelist)
        assert "GET" in retry.allowed_methods
        assert retry.raise_on_status is False


def test_session_pool_maxsize():
    session = build_session(pool_maxsize=25)
    for prefix in ("https://", "http://"):
        assert session.get_adapter(prefix + "example.com")._pool_maxsize == 25
