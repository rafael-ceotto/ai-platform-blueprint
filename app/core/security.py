"""API key authentication for the document endpoints.

See docs/adr/0003-api-key-auth-and-rate-limiting.md for why API keys (not
OAuth2) were chosen: the platform's current consumers are services
integrating over the API, not end users authenticating interactively.
"""

from fastapi.security import APIKeyHeader

from app.core.config import Settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(candidate: str | None, settings: Settings) -> bool:
    """Return True if `candidate` is one of the configured API keys.

    An empty `settings.API_KEYS` fails closed: nothing matches, so every
    request to a protected endpoint is rejected.
    """
    return candidate is not None and candidate in settings.API_KEYS
