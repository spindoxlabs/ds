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
    # The second provider (`D-54`, `DID-15`): a DSO that shares its own grid data
    # and has no members. Its presence is what makes "which provider" a question.
    grid_operator_connector_url: str = Field(
        "http://172.17.0.1:32001", validation_alias="CONNECTOR_URL_GRID_OPERATOR"
    )
    grid_operator_provenance_url: str = Field(
        "http://172.17.0.1:32000",
        validation_alias="CONNECTOR_PROVENANCE_URL_GRID_OPERATOR",
    )
    grid_operator_did: str = Field(
        "did:web:grid-operator.dataspaces.localhost",
        validation_alias="CONNECTOR_PARTICIPANT_DID_GRID_OPERATOR",
    )
    # Its own registry, reached **directly**. `/users/{did}/credentials` is an
    # internal-scope route and is deliberately not on the public participant
    # host — the host publishes DID documents, not credential stores.
    grid_operator_identity_registry_url: str = Field(
        "http://172.17.0.1:30008",
        validation_alias="IDENTITY_REGISTRY_URL_GRID_OPERATOR",
    )
    grid_operator_asset_id: str = Field(
        "datasets.gold.grid_capacity", validation_alias="E2E_GRID_OPERATOR_ASSET_ID"
    )
    grid_operator_counter_party_address: str = Field(
        "http://172.17.0.1:39194/protocol/2025-1",
        validation_alias="E2E_GRID_OPERATOR_COUNTER_PARTY_ADDRESS",
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

    # Identity.
    #
    # **These name roles in an exchange, not organisations** (`DID-15`). The
    # fixtures behind them are `rec` and `third-party`; the fields stay
    # role-shaped because every flow is written as "the provider side" and "the
    # consumer side". Where a flow needs to say *which* provider — there are two
    # — it names one explicitly, as `two_providers` does with
    # `grid_operator_did`.
    provider_did: str = Field(
        "did:web:rec.dataspaces.localhost",
        validation_alias="CONNECTOR_PARTICIPANT_DID",
    )
    consumer_did: str = Field(
        "did:web:third-party.dataspaces.localhost",
        validation_alias="CONNECTOR_CONSUMER_PARTICIPANT_DID",
    )
    # The issuer every participant enrols with. Named as a DID rather than a URL
    # because that is the only thing a joining organisation is given: it resolves
    # the document and reads the `IssuerService` entry out of it (`DID-14`).
    trust_anchor_did: str = Field(
        "did:web:trust-anchor.dataspaces.localhost",
        validation_alias="CONNECTOR_TRUST_ANCHOR_DID",
    )
    # The provider's STS client secret. **Its own** — the trust anchor mints no
    # STS secret for a participant (`D-51`), so this is a value the provider's
    # deployment chose and matches `IR_REC_STS_SECRET`.
    #
    # It now carries the dev default rather than empty. Empty made the positive
    # token-issuance assertion *skip*, and a security flow whose only positive
    # leg is skipped by default proves the refusals and nothing else: the whole
    # STS could be a function returning 401 and the flow would still be
    # green.
    provider_sts_client_secret: str = Field(
        "insecure-dev-secret", validation_alias="E2E_PROVIDER_STS_SECRET"
    )
    # StatusList2021 list id. The identity-registry provisions "1" on first use
    # (services/identity-registry/.../org_onboarding.py).
    status_list_id: str = Field("1", validation_alias="E2E_STATUS_LIST_ID")

    # The OIDC client humans log in through — oauth2-proxy's. The user-authority
    # flow needs a *user* token: every other flow uses client_credentials, so
    # until it existed nothing proved that a human's groups authorise anything.
    # `directAccessGrantsEnabled` is set on this client in the **dev** realm only,
    # which is how a test obtains a real user token without driving a browser.
    user_client_id: str = Field("oauth2_proxy", validation_alias="OAUTH2_PROXY_CLIENT_ID")
    user_client_secret: str = Field(
        "oauth2_proxy", validation_alias="OAUTH2_PROXY_CLIENT_SECRET"
    )
    # Dev fixtures: password equals username (services/keycloak/realm-*-dev.json).
    admin_email: str = "admin@example.test"
    admin_password: str = "admin"
    provider_email: str = "provider@example.test"
    provider_password: str = "provider"
    # A second participant's operator, holding `ds-participant-admin` **only inside
    # the `grid-operator` organisation** and no realm groups at all. It is the one
    # dev seat that can demonstrate a cross-owner refusal: every other operator
    # carries a realm-level grant, which is deployment-wide by design.
    grid_operator_email: str = "gridops@example.test"
    grid_operator_password: str = "gridops"
    # A seat whose only realm group is `legacy-provider-admin` — a deliberately
    # foreign-looking name that is **not** a ds bundle and therefore grants nothing
    # on its own. Its authority exists only if the Layer B alias map translated it,
    # which is what makes this an assertion about the wiring rather than about the
    # bundle table.
    legacy_operator_email: str = "legacy@example.test"
    legacy_operator_password: str = "legacy"
    # The owner that owns `asset_id` in the dev governance file, and one that does
    # not. The perimeter compares canonical `Owner.id`s, so both must be real
    # owners in the registry.
    owning_org: str = "example-org"
    other_org: str = "grid-operator"
    consumer_password: str = "consumer"
    data_subject_password: str = "subject"

    # Test subjects
    consumer_subject_id: str = (
        "did:web:third-party.dataspaces.localhost:users:consumer-user"
    )
    consumer_email: str = "consumer@example.test"
    data_subject_id: str = "did:web:rec.dataspaces.localhost:users:data-subject"
    data_subject_email: str = "subject@example.test"
    asset_id: str = "datasets.silver.meters_15m"

    # Organisation onboarding (Block D). The agreement must be seeded via
    # `ir-cli agreement import` at bootstrap; the flow asserts it exists.
    org_e2e_alias: str = "org-e2e"
    org_e2e_legal_name: str = "E2E Test Organisation"
    org_e2e_did: str = "did:web:org-e2e.dataspaces.localhost"
    org_agreement_id: str = "dataspace-participation"
    org_agreement_version: str = "1.0"

    # Consent vocabulary — must match services/connector/governance-rec/
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
