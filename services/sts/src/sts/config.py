"""STS configuration."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STS_",
        env_file=".env",
        extra="ignore",
    )

    participant_did: str = "did:web:provider.dataspaces.localhost"
    # Path to the JWK private key file (JSON)
    private_key_path: str = "/config/provider-key.json"
    # OAuth2 client ID and secret for connector → STS requests
    client_id: str = Field(default="did:web:provider.dataspaces.localhost")
    client_secret: str = Field(default="insecure-dev-secret")
    # JWT validity in seconds
    token_ttl: int = 300
    debug: bool = False

    @property
    def private_key_jwk(self) -> dict:
        return json.loads(Path(self.private_key_path).read_text())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
