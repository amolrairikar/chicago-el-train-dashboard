from unittest import mock

import pytest

from common import secrets

SECRET_NAME = "projects/test/secrets/cta-api-key/versions/latest"


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
    return client


def test_get_api_key_reads_and_strips(secret):
    assert secrets.get_api_key(SECRET_NAME) == "test-key"
    secret.access_secret_version.assert_called_once_with(name=SECRET_NAME)


def test_get_api_key_is_cached(secret):
    secrets.get_api_key(SECRET_NAME)
    secrets.get_api_key(SECRET_NAME)
    assert secret.access_secret_version.call_count == 1


def test_get_api_key_does_not_cache_failures(secret):
    secret.access_secret_version.side_effect = [RuntimeError("boom"), mock.DEFAULT]
    with pytest.raises(RuntimeError):
        secrets.get_api_key(SECRET_NAME)
    assert secrets.get_api_key(SECRET_NAME) == "test-key"


def test_get_api_key_global_secret_uses_default_endpoint(secret):
    secrets.get_api_key(SECRET_NAME)
    assert secret.init_kwargs == [{"client_options": None}]


def test_get_api_key_regional_secret_uses_regional_endpoint(secret):
    name = "projects/test/locations/us-central1/secrets/cta-api-key/versions/latest"
    secrets.get_api_key(name)
    assert secret.init_kwargs == [
        {
            "client_options": {
                "api_endpoint": "secretmanager.us-central1.rep.googleapis.com"
            }
        }
    ]
    secret.access_secret_version.assert_called_once_with(name=name)
