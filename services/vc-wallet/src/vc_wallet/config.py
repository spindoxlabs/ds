"""VC Wallet configuration."""
from __future__ import annotations

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VC_WALLET_",
        env_file=".env",
        extra="ignore",
    )

    participant_did: str = "did:web:provider.dataspaces.localhost"
    # Directory containing pre-issued VC JSON-LD files
    credentials_path: str = "/credentials"
    private_key_path: str | None = None
    credential_status_path: str | None = None
    credential_status_url: str | None = None
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
