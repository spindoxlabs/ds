"""ds-connector configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONNECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    participant_id: str = "provider"
    participant_base_url: str = "https://provider.dataspaces.localhost"
    participant_did: str = "did:web:provider.dataspaces.localhost"

    # EDC Management API — env vars use EDC_ prefix (no CONNECTOR_ prefix)
    edc_provider_management_url: str = Field(
        default="http://localhost:19193/management",
        validation_alias="EDC_PROVIDER_MANAGEMENT_URL",
    )
    edc_provider_protocol_url: str = Field(
        default="http://localhost:19194/protocol",
        validation_alias="EDC_PROVIDER_PROTOCOL_URL",
    )
    edc_consumer_management_url: str = Field(
        default="http://localhost:29193/management",
        validation_alias="EDC_CONSUMER_MANAGEMENT_URL",
    )
    edc_consumer_protocol_url: str = Field(
        default="http://localhost:29194/protocol",
        validation_alias="EDC_CONSUMER_PROTOCOL_URL",
    )
    edc_api_key: str = Field(
        default="insecure-dev-key",
        validation_alias="EDC_API_KEY",
    )

    dataset_api_url: str = "http://localhost:30002"
    provenance_url: str = "http://localhost:30000"

    negotiation_poll_interval: float = 2.0
    negotiation_timeout: float = 120.0
    transfer_poll_interval: float = 2.0
    transfer_timeout: float = 120.0

    participants_registry_path: str = "governance/participants.yaml"
    governance_yaml_path: str = "governance/governance.yaml"

    database_url: str = "postgresql+asyncpg://postgres:postgres@host.docker.internal:35432/connector"
    debug: bool = False

    # Notification backends — comma-separated: smtp, webhook (default: empty → null)
    notify_backends: str = ""
    notify_portal_base_url: str = "https://portal.dataspaces.localhost"

    # SMTP settings (required when notify_backends contains "smtp")
    notify_smtp_host: str | None = None
    notify_smtp_port: int = 587
    notify_smtp_user: str | None = None
    notify_smtp_password: str | None = None
    notify_smtp_from: str | None = None
    notify_smtp_tls: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
