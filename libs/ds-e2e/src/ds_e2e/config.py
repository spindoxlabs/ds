from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class E2ESettings(BaseSettings):
    # **No `env_file`** (`E2E-07`). It declared `(".env", ".env.local")`, which
    # pydantic resolves relative to the process's working directory — and the
    # harness runs from `libs/ds-e2e/`, which holds neither file. So the
    # declaration loaded nothing, ever, while reading as the thing that
    # configured the harness.
    #
    # The root files are already in the environment when it matters: the root
    # `Taskfile.yml` declares `dotenv: [".env", ".env.local"]`, so every `e2e:*`
    # task exports them before this runs. Pointing `env_file` at the repo root
    # would have made the same values arrive twice by two mechanisms with
    # different precedence — the harder thing to reason about, for no gain.
    model_config = SettingsConfigDict(
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
    # **30022, not 30002** (`E2E-13`). The default has to name what
    # `task docker:restart` actually starts, and that is the mock: `9a8e3e5`
    # gave it its own port permanently, because 30002 belongs to the real celine
    # `dataset-api` in `docker-compose.dataset-api.yml` — a stack `build` and
    # `docker:restart` **both skip by name**, since it builds sibling checkouts
    # whose paths are optional.
    #
    # So the sequence the root guide calls *"this must pass before e2e means
    # anything"* dialled a port nothing was listening on, and the run did not
    # fail a flow: it raised `ConnectError` out of `run_all` and produced zero
    # results.
    #
    # Running against the real data plane stays one variable away — that is
    # `T-1`, and `data_plane_label` below is the other half of it.
    dataset_api_url: str = Field(
        "http://172.17.0.1:30022", validation_alias="CONNECTOR_DATASET_API_URL"
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
    # `172.17.0.1`, not `localhost` (`E2E-07`). This was the **only** default in
    # this file on `localhost`, against the host-binding rule the root guide
    # states: `172.17.0.1` is the Docker host gateway and resolves identically
    # from the host and from a container, which is what lets a service be
    # stopped in Docker and restarted on the host with nothing else changing.
    # `localhost` resolves to two different things depending on where the
    # harness runs, so this default worked from a laptop and not from a
    # container — and the failure reads as "Keycloak is down".
    keycloak_token_url: str = Field(
        "http://172.17.0.1:9080/realms/dataspaces/protocol/openid-connect/token",
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
    # `E2E_ASSET_ID`, the name `Taskfile.yml:1064` already sets when it waits for
    # the federated catalogue to list the asset (`E2E-08`). `E2ESettings`
    # declares no `env_prefix`, so an un-aliased field is read from the **bare**
    # name — `ASSET_ID` — and the variable the Taskfile exports reached nothing.
    # The readiness gate and the flows could therefore wait for one asset and
    # assert on another, and agree only because both were left at the default.
    asset_id: str = Field(
        "datasets.silver.meters_15m", validation_alias="E2E_ASSET_ID"
    )

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

    # EDC control planes, for `ds-e2e clean` (`E2E-07`).
    #
    # These were module constants in `cleanup.py`, so a stack whose EDC key or
    # ports differed could not be cleaned — and the clean reported success
    # having deleted nothing, since a 401 on a delete was not checked. Same dev
    # defaults, now overridable like every other address the harness uses.
    edc_api_key: str = Field("insecure-dev-key", validation_alias="EDC_API_KEY")
    edc_provider_management_url: str = Field(
        "http://172.17.0.1:19193/management",
        validation_alias="E2E_EDC_PROVIDER_MANAGEMENT_URL",
    )
    edc_consumer_management_url: str = Field(
        "http://172.17.0.1:29193/management",
        validation_alias="E2E_EDC_CONSUMER_MANAGEMENT_URL",
    )
    edc_grid_operator_management_url: str = Field(
        "http://172.17.0.1:39193/management",
        validation_alias="E2E_EDC_GRID_OPERATOR_MANAGEMENT_URL",
    )

    #: The container serving the provider's `/internal/*` PDP, for the
    #: fail-closed flow (`E2E-06`), which stops it to prove the enforcement
    #: points deny. A setting rather than a literal because the compose project
    #: name is configurable, and a flow that stops the wrong container — or
    #: silently stops nothing — is worse than one that fails.
    #: The container serving the PDP the fail-closed flow stops (`E2E-06`).
    #:
    #: The **grid operator's**, because that is the exchange whose baseline can
    #: be established in one call: `two-providers` proves this consumer
    #: negotiates for `grid_operator_asset_id` with no consent gate, while both
    #: REC datasets terminate the negotiation without a prior grant — a
    #: different property, tested by `consent-request`.
    #:
    #: A setting rather than a literal because the compose project name is
    #: configurable, and a flow that stops the wrong container — or silently
    #: stops nothing — is worse than one that fails.
    pdp_container: str = Field(
        "dataspaces-ds-connector-grid-operator-1",
        validation_alias="E2E_PDP_CONTAINER",
    )

    # Timeouts
    poll_timeout: int = 120
    poll_interval: float = 2.0
    request_timeout: int = 30

    # DB (for cleanup — plain psycopg, not asyncpg)
    database_url: str = Field(
        "postgresql://postgres:postgres@172.17.0.1:35432",
        validation_alias="SMOKE_DATABASE_URL",
    )

    #: Which data plane this run exercised, in words (`T-1`).
    #:
    #: The data plane has two implementations and a run exercises exactly one,
    #: while *nothing in the output said which*. A green suite against the mock
    #: and a green suite against the real celine `dataset-api` are different
    #: evidence, and they were indistinguishable after the fact — which is the
    #: root guide's own warning, *a green run is only evidence about the thing
    #: that actually ran*, at the layer that costs the most to re-run.
    #:
    #: Derived from the port rather than configured, so it cannot be set to
    #: something the run did not do.
    @property
    def data_plane_label(self) -> str:
        port = self.dataset_api_url.rsplit(":", 1)[-1].split("/")[0]
        known = {
            "30022": "dataset-api mock (docker-compose.rec.yml)",
            "30002": "real celine dataset-api (docker-compose.dataset-api.yml)",
        }
        return f"{known.get(port, 'unrecognised data plane')} at {self.dataset_api_url}"


@lru_cache(maxsize=1)
def get_settings() -> E2ESettings:
    return E2ESettings()
