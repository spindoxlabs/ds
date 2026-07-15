"""ds-federated-catalog configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ds-connector base URL — all DSP catalog calls go through it
    connector_url: str = "http://172.17.0.1:30001"

    # Identity-registry URL for fetching participant list
    identity_registry_url: str = "http://identity-registry:30005"

    # Fallback: Path to participants.yaml (used only if identity_registry_url is empty)
    participants_yaml: str = ""

    # Crawl interval in seconds
    crawl_interval: int = 300

    # Seconds to wait after startup before first crawl (allows connector to be ready)
    startup_delay: int = 10

    # Maximum datasets to store per provider (prevents memory bloat)
    max_datasets_per_provider: int = 500

    # Service identity
    base_url: str = "https://federated-catalog.dataspaces.localhost"

    # Path to catalogues.yaml — DCAT-AP sources to crawl
    dcat_sources_yaml: str = ""

    port: int = 30003
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
