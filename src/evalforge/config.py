"""Validated runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: str
    api_keys: dict[str, str]
    environment: str = "development"

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("EVALFORGE_ENV", "development").strip().lower()
        raw_keys = os.getenv("EVALFORGE_API_KEYS", "portfolio:local-development-key")
        keys: dict[str, str] = {}
        for entry in raw_keys.split(","):
            tenant, separator, key = entry.strip().partition(":")
            if not separator or not tenant or len(key) < 12:
                raise ValueError("EVALFORGE_API_KEYS must contain tenant:long-secret pairs")
            if key in keys:
                raise ValueError("API keys must be unique")
            keys[key] = tenant
        if environment == "production" and "local-development-key" in keys:
            raise ValueError("the development API key is forbidden in production")
        return cls(
            database_path=os.getenv("EVALFORGE_DB", "evalforge.db"),
            api_keys=keys,
            environment=environment,
        )
