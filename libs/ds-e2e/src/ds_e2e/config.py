from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class E2ESettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service URLs
    connector_url: str = Field(
        "http://172.17.0.1:30001", validation_alias="CONNECTOR_URL"
    )
    consumer_connector_url: str = Field(
        "http://172.17.0.1:31001", validation_alias="CATALOG_CONNECTOR_URL"
    )
    dataset_api_url: str = Field(
        "http://172.17.0.1:30002", validation_alias="CONNECTOR_DATASET_API_URL"
    )
    provenance_url: str = Field(
        "http://172.17.0.1:30000", validation_alias="CONNECTOR_PROVENANCE_URL_PROVIDER"
    )
    consumer_provenance_url: str = Field(
        "http://172.17.0.1:31000", validation_alias="CONNECTOR_PROVENANCE_URL_CONSUMER"
    )
    identity_registry_url: str = Field(
        "http://172.17.0.1:30005", validation_alias="CONNECTOR_IDENTITY_REGISTRY_URL"
    )

    # Counter-party DSP address — where the consumer EDC reaches the provider
    # EDC's protocol endpoint. Uses 172.17.0.1 so it works both when EDCs run
    # locally (task dev) and from Docker containers (host gateway).
    counter_party_address: str = Field(
        "http://172.17.0.1:19194/protocol/2025-1",
        validation_alias="E2E_COUNTER_PARTY_ADDRESS",
    )

    # Auth
    keycloak_token_url: str = Field(
        "http://localhost:9080/realms/dataspaces/protocol/openid-connect/token",
        validation_alias="KEYCLOAK_TOKEN_URL",
    )
    service_client_id: str = Field(
        "svc-ds-portal", validation_alias="SVC_DS_PORTAL_ID"
    )
    service_client_secret: str = Field(
        "svc-ds-portal", validation_alias="SVC_DS_PORTAL_SECRET"
    )

    # Identity
    provider_did: str = Field(
        "did:web:provider.dataspaces.localhost",
        validation_alias="CONNECTOR_PARTICIPANT_DID",
    )
    consumer_did: str = Field(
        "did:web:consumer.dataspaces.localhost",
        validation_alias="CONNECTOR_CONSUMER_PARTICIPANT_DID",
    )

    # Test subjects
    consumer_subject_id: str = "did:web:users.dataspaces.localhost:consumer-user"
    consumer_email: str = "consumer@example.test"
    data_subject_id: str = "did:web:users.dataspaces.localhost:data-subject"
    data_subject_email: str = "subject@example.test"
    asset_id: str = "datasets.silver.meters_15m"

    # Timeouts
    poll_timeout: int = 120
    poll_interval: float = 2.0
    request_timeout: int = 30

    # DB (for cleanup — plain psycopg, not asyncpg)
    database_url: str = Field(
        "postgresql://postgres:postgres@172.17.0.1:35432",
        validation_alias="SMOKE_DATABASE_URL",
    )


@lru_cache(maxsize=1)
def get_settings() -> E2ESettings:
    return E2ESettings()
