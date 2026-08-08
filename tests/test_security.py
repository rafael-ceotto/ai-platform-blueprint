"""Tests for API key verification."""

from app.core.config import Settings
from app.core.security import verify_api_key


def _settings(api_keys: list[str]) -> Settings:
    return Settings(API_KEYS=api_keys)


def test_valid_key_is_accepted() -> None:
    settings = _settings(["abc123"])
    assert verify_api_key("abc123", settings) is True


def test_invalid_key_is_rejected() -> None:
    settings = _settings(["abc123"])
    assert verify_api_key("wrong-key", settings) is False


def test_missing_key_is_rejected() -> None:
    settings = _settings(["abc123"])
    assert verify_api_key(None, settings) is False


def test_empty_key_list_fails_closed() -> None:
    settings = _settings([])
    assert verify_api_key("abc123", settings) is False
