"""ds-connector configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONNECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    role: Literal["provider", "consumer"] = Field(
        ...,
        description="Participant role — determines which EDC client and routers are loaded",
    )

    participant_id: str = "provider"
    participant_base_url: str = "https://provider.dataspaces.localhost"
    participant_did: str = "did:web:provider.dataspaces.localhost"
    consumer_participant_did: str = "did:web:consumer.dataspaces.localhost"

    # EDC Management API — env vars use EDC_ prefix (no CONNECTOR_ prefix)
    edc_provider_management_url: str = Field(
        default="http://localhost:19193/management",
        validation_alias="EDC_PROVIDER_MANAGEMENT_URL",
    )
    edc_provider_protocol_url: str = Field(
        default="http://localhost:19194/protocol/2025-1",
        validation_alias="EDC_PROVIDER_PROTOCOL_URL",
    )
    edc_consumer_management_url: str = Field(
        default="http://localhost:29193/management",
        validation_alias="EDC_CONSUMER_MANAGEMENT_URL",
    )
    edc_consumer_protocol_url: str = Field(
        default="http://localhost:29194/protocol/2025-1",
        validation_alias="EDC_CONSUMER_PROTOCOL_URL",
    )
    edc_api_key: str = Field(
        default="insecure-dev-key",
        validation_alias="EDC_API_KEY",
    )
    edc_api_key_file: str | None = Field(
        default=None,
        validation_alias="EDC_API_KEY_FILE",
    )

    dataset_api_url: str = "http://localhost:30002"
    provenance_url: str = "http://localhost:30000"

    negotiation_poll_interval: float = 2.0
    negotiation_timeout: float = 120.0
    transfer_poll_interval: float = 2.0
    transfer_timeout: float = 120.0

    identity_registry_url: str = "http://identity-registry:30005"
    participant_registry_cache_ttl: float = 60.0
    participants_registry_path: str | None = None
    governance_yaml_path: str = "governance/governance.yaml"
    governance_overlay_name: str | None = None
    owners_registry_cache_ttl: float = 60.0
    odrl_profile_path: str | None = None
    trust_anchor_did: str = "did:web:trust-anchor.dataspaces.localhost"
    trust_anchor_key_path: str | None = None
    credential_status_path: str | None = None
    credential_status_url: str | None = None
    allow_unknown_participants: bool = False

    oidc_issuer_url: str | None = Field(
        default=None,
        description="OIDC issuer URL for JWT verification (Keycloak realm URL)",
    )
    oidc_insecure_dev: bool = Field(
        default=True,
        description=(
            "When True AND no issuer is configured, tokens are accepted WITHOUT "
            "signature/audience verification (local dev only). Production MUST set "
            "the issuer URL, which enforces verification regardless of this flag."
        ),
    )
    service_client_id: str = Field(
        default="svc-ds-connector",
        description="Keycloak client ID for this service (used as JWT audience)",
    )
    admin_scope: str = "connector.admin"
    internal_scope: str = "connector.internal"
    webhook_scope: str = "connector.webhook"

    database_url: str = "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/connector"
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

    @model_validator(mode="after")
    def load_file_secrets(self):
        if self.edc_api_key_file:
            self.edc_api_key = Path(self.edc_api_key_file).read_text().strip()
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
