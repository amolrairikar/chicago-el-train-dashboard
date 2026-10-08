import functools

from google.cloud import secretmanager


@functools.cache
def get_api_key(secret_name: str) -> str:
    """Reads the CTA API key, cached so warm instances skip Secret Manager."""
    # Regional secrets are only served from their region's endpoint, e.g.
    # projects/<p>/locations/us-central1/secrets/<s>/versions/<v>.
    parts = secret_name.split("/")
    client_options = None
    if len(parts) > 3 and parts[2] == "locations":
        client_options = {
            "api_endpoint": f"secretmanager.{parts[3]}.rep.googleapis.com"
        }
    client = secretmanager.SecretManagerServiceClient(client_options=client_options)
    response = client.access_secret_version(name=secret_name)
    return response.payload.data.decode("utf-8").strip()
