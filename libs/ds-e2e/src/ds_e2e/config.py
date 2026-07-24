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
    federated_catalog_url: str = Field(
        "http://172.17.0.1:30003", validation_alias="FEDERATED_CATALOG_URL"
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
    # The harness has its own Keycloak client. It drives endpoints belonging to
    # several different callers (provider console, onboarding service,
    # dataset-api), and borrowing svc-ds-portal for that meant the portal had to
    # carry connector.admin — which is a superset, so it silently held every
    # connector permission including the machine-identity ones. A dedicated
    # client keeps those grants visible as a test identity. Dev/CI realms only.
    service_client_id: str = Field("svc-ds-e2e", validation_alias="SVC_DS_E2E_ID")
    service_client_secret: str = Field(
        "svc-ds-e2e", validation_alias="SVC_DS_E2E_SECRET"
    )
    # An identity-registry.admin-capable client, for the org-onboarding flow —
    # the portal client above only holds read/resolve scopes.
    ir_admin_client_id: str = Field(
        "svc-ds-identity-registry", validation_alias="SVC_DS_IDENTITY_REGISTRY_ID"
    )
    ir_admin_client_secret: str = Field(
        "svc-ds-identity-registry",
        validation_alias="SVC_DS_IDENTITY_REGISTRY_SECRET",
    )
    # A deliberately *under-privileged* client, for the 403 half of the contract
    # sweep. svc-ds-federated-catalog holds only catalog.read and
    # identity-registry.read (services/keycloak/clients.yaml), so it authenticates
    # everywhere and is authorised almost nowhere — exactly what a wrong-scope
    # probe needs. Using a real client rather than a forged token means the
    # assertion exercises the same JWKS verification path production uses.
    low_priv_client_id: str = Field(
        "svc-ds-federated-catalog", validation_alias="SVC_DS_FEDERATED_CATALOG_ID"
    )
    low_priv_client_secret: str = Field(
        "svc-ds-federated-catalog", validation_alias="SVC_DS_FEDERATED_CATALOG_SECRET"
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
    # The provider's STS client secret, if the deployment exposes it to the test
    # environment. Absent, the dcp-trust flow still asserts every refusal path
    # and only skips the positive token-issuance assertion — a missing secret
    # must never turn a security assertion into a silent pass.
    provider_sts_client_secret: str = Field(
        "", validation_alias="E2E_PROVIDER_STS_SECRET"
    )
    # StatusList2021 list id. The identity-registry provisions "1" on first use
    # (services/identity-registry/.../org_onboarding.py).
    status_list_id: str = Field("1", validation_alias="E2E_STATUS_LIST_ID")

    # Test subjects
    consumer_subject_id: str = "did:web:users.dataspaces.localhost:consumer-user"
    consumer_email: str = "consumer@example.test"
    data_subject_id: str = "did:web:users.dataspaces.localhost:data-subject"
    data_subject_email: str = "subject@example.test"
    asset_id: str = "datasets.silver.meters_15m"

    # Organisation onboarding (Block D). The agreement must be seeded via
    # `ir-cli agreement import` at bootstrap; the flow asserts it exists.
    org_e2e_alias: str = "org-e2e"
    org_e2e_legal_name: str = "E2E Test Organisation"
    org_e2e_did: str = "did:web:org-e2e.dataspaces.localhost"
    org_agreement_id: str = "dataspace-participation"
    org_agreement_version: str = "1.0"

    # Consent vocabulary — must match services/connector/governance/
    # sharing-offers.yaml and the ODRL profile taxonomy.
    sharing_offer_id: str = "household-energy-flexibility"
    consented_purpose: str = "FlexibilityResearch"
    # A purpose the dataset is offered for but this subject never agreed to —
    # the negative case that proves the purpose chain is enforced.
    unconsented_purpose: str = "IncentiveCalculation"

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
