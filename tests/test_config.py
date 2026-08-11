from __future__ import annotations

import pytest

from evalforge.config import Settings


def test_development_defaults(monkeypatch) -> None:
    monkeypatch.delenv("EVALFORGE_ENV", raising=False)
    monkeypatch.delenv("EVALFORGE_API_KEYS", raising=False)
    settings = Settings.from_env()
    assert settings.api_keys["local-development-key"] == "portfolio"
    assert settings.environment == "development"


def test_multiple_tenant_keys(monkeypatch) -> None:
    monkeypatch.setenv("EVALFORGE_API_KEYS", "a:abcdefghijkl,b:mnopqrstuvwx")
    settings = Settings.from_env()
    assert settings.api_keys["abcdefghijkl"] == "a"
    assert settings.api_keys["mnopqrstuvwx"] == "b"


@pytest.mark.parametrize("value", ["missing-separator", ":abcdefghijkl", "tenant:short"])
def test_malformed_keys_rejected(monkeypatch, value: str) -> None:
    monkeypatch.setenv("EVALFORGE_API_KEYS", value)
    with pytest.raises(ValueError, match="tenant"):
        Settings.from_env()


def test_duplicate_key_rejected(monkeypatch) -> None:
    monkeypatch.setenv("EVALFORGE_API_KEYS", "a:abcdefghijkl,b:abcdefghijkl")
    with pytest.raises(ValueError, match="unique"):
        Settings.from_env()


def test_development_key_rejected_in_production(monkeypatch) -> None:
    monkeypatch.setenv("EVALFORGE_ENV", "production")
    monkeypatch.setenv("EVALFORGE_API_KEYS", "portfolio:local-development-key")
    with pytest.raises(ValueError, match="forbidden"):
        Settings.from_env()
