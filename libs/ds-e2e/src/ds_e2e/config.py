from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def describe_data_plane(url: str) -> str:
    """`"dataset-api mock (docker-compose.rec.yml) at http://…:30022"`.

    Derived from the **port**, never configured, so a run cannot claim a backend
    it did not use — the property `E2E-13` earned in its first hour, when it
    revealed `.env.local` overriding the harness to a port nothing served.
    """
    port = url.rsplit(":", 1)[-1].split("/")[0]
    known = {
        "30022": "dataset-api mock (docker-compose.rec.yml)",
        "30002": "real celine dataset-api (docker-compose.dataset-api.yml)",
    }
    return f"{known.get(port, 'unrecognised data plane')} at {url}"


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
    #: Comma-separated data-plane URLs the query flows exercise (`T-1`). Both by
    #: default: the mock on :30022 and the real celine `dataset-api` on :30002.
    #: Set to one URL to run against one, and the output still names which.
    #: Whether a data plane is *expected* to expose `POST
    #: /catalogue/{id}/conformance` (`M-15`).
    #:
    #: False by default, matching the dataset-api's own `CONFORMANCE_ENABLED`:
    #: the check is off unless a deployment turns it on, and the mock does not
    #: implement it at all. `smoke` detects the endpoint from the plane's OpenAPI
    #: document and exercises it wherever it is present, so the default still
    #: verifies conformance on a plane that has it.
    #:
    #: **Set this true once a deployment has turned the feature on.** Otherwise
    #: switching it off by accident reads as a green suite — the endpoint simply
    #: stops being probed — and *a green check is not a check that ran*.
    require_conformance: bool = Field(
        False, validation_alias="E2E_REQUIRE_CONFORMANCE"
    )
    e2e_data_planes: str = Field(
        "http://172.17.0.1:30022,http://172.17.0.1:30002",
        validation_alias="E2E_DATA_PLANES",
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
    # The onboarding service's own client, and the `onboarding-seam` flow uses it
    # rather than `svc-ds-e2e` **on purpose**. The service is out of this
    # repository, so what ds can assert about the seam is that the eight scopes
    # `services/keycloak/clients.yaml` grants this client are sufficient for the
    # calls that seam makes — which is only an assertion if the flow authenticates
    # as the client and not as a harness identity that holds more. Both halves of
    # `plans/onboarding-seam.md` were 403s and 404s reachable no other way.
    onboarding_client_id: str = Field(
        "svc-ds-onboarding", validation_alias="SVC_DS_ONBOARDING_ID"
    )
    onboarding_client_secret: str = Field(
        "svc-ds-onboarding", validation_alias="SVC_DS_ONBOARDING_SECRET"
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
    # `owning_org`'s **alias**, which is not its id. The distinction is the whole
    # of Phase 1: `GET /admin/owners/{owner_id}` matches on `Owner.id` and 404s on
    # an alias, which a caller holding only the alias reads as *no such
    # organisation* — a startup-refusing error for a correctly configured
    # deployment. `GET /owners/resolve` is the route that answers both.
    owning_org_alias: str = "example"
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

    #: How long to wait for a withdrawn consent to terminate a running transfer
    #: before the `consent-withdrawal` flow calls it a failure.
    #:
    #: **A harness deadline, not a platform window**, and the distinction is the
    #: whole of what was learned writing that flow. EDC's policy monitor has a
    #: `edc.policy.monitor.period` that defaults to `PT1H`, and the obvious
    #: reading — *that is how long a withdrawal takes to bite* — is **wrong**:
    #: measured on 2026-08-09 with the period at both `PT1M` and `PT1H`, four
    #: minutes after boot so no start-up pass was in play, termination landed
    #: **3s** after withdrawal both times. Whatever schedules that evaluation, it
    #: is not that setting.
    #:
    #: So this is generous on purpose: it bounds a wait, and a value near the
    #: measured latency would turn ordinary jitter into a red flow. If a run ever
    #: does exhaust it, the finding is real and belongs in the ledger — do not
    #: raise the number to make it pass.
    consent_withdrawal_timeout_seconds: float = Field(
        120.0, validation_alias="E2E_CONSENT_WITHDRAWAL_TIMEOUT_SECONDS"
    )

    #: The container serving the PDP the fail-closed flow stops (`E2E-06`).
    #:
    #: The **REC's**, and it must stay the connector `connector_url` addresses:
    #: the flow proves the container it stopped is the one that went silent by
    #: watching that URL, so a mismatch fails the flow rather than producing a
    #: refusal from a service nobody stopped.
    #:
    #: It was the grid operator's, chosen because that exchange has no consent
    #: gate and so costs one call to baseline. That convenience deleted the
    #: subject of the test: the grid operator's offer carries only
    #: `odrl:purpose`, which the EDC evaluates in-process, so its negotiation
    #: never asks a PDP and stopping one cannot refuse it. See
    #: `flows/fail_closed.py`.
    #:
    #: A setting rather than a literal because the compose project name is
    #: configurable, and a flow that stops the wrong container — or silently
    #: stops nothing — is worse than one that fails.
    pdp_container: str = Field(
        "dataspaces-ds-connector-rec-1",
        validation_alias="E2E_PDP_CONTAINER",
    )

    #: The dataset the fail-closed flow negotiates for (`E2E-06`).
    #:
    #: Membership-gated and **not** consent-gated, which is the pair of
    #: properties the flow needs: `{ns}Membership` is evaluated by
    #: `AccessScopeFunction`, which calls `GET /internal/participants/check` on
    #: ds-connector — so there is a PDP to be unreachable — while the absence of
    #: a consent constraint means the baseline needs no prior grant.
    #:
    #: Not `asset_id`: `datasets.silver.meters_15m` is consent-gated, and its
    #: baseline is `consent-request`'s property, not this flow's.
    fail_closed_asset_id: str = Field(
        "datasets.gold.om_weather_features",
        validation_alias="E2E_FAIL_CLOSED_ASSET_ID",
    )

    #: `ds.access.scope.cache.ttl.seconds` — how long the EDC's constraint
    #: functions reuse a decision ds-connector gave them (`E2E-06`).
    #:
    #: **The window in which the platform cannot fail closed**, because there is
    #: nothing to ask. Measured on the running stack: a negotiation at ~10s of
    #: PDP downtime reached VERIFIED off a cached `true`; the same one at ~75s
    #: TERMINATED on the unfulfilled membership constraint. So the flow waits it
    #: out, and reads the same variable the EDC containers are given, or the
    #: harness would wait a number the platform is not using.
    pdp_cache_ttl_s: int = Field(
        60, validation_alias="DS_ACCESS_SCOPE_CACHE_TTL_SECONDS"
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
        return describe_data_plane(self.dataset_api_url)

    #: Every data plane a run should exercise — `T-1`'s remaining half.
    #:
    #: **The platform has two implementations of the query surface and a run used
    #: to exercise exactly one.** `services/dataset-api-mock` is a stand-in; the
    #: real one is the celine `dataset-api`. The root guide states the
    #: consequence: *"Both must be run, and each run must name its backend. Until
    #: that is wired, a change to either data plane needs its own check."*
    #:
    #: **One exchange covers both, measured 2026-08-09 rather than assumed.** A
    #: single EDR presented to `:30002` and `:30022` was accepted by both — 200
    #: from each, five rows and two — because both verify the same bearer and both
    #: ask the same connector's `/internal/dataplane/authorize`. So this needs no
    #: second negotiation, no second transfer and no doubled suite: the flows that
    #: query iterate this list with the credential they already hold.
    #:
    #: Absent, it falls back to the single configured plane, so a deployment
    #: running only one is unaffected and says which.
    @property
    def data_planes(self) -> tuple[tuple[str, str], ...]:
        raw = (self.e2e_data_planes or "").strip()
        urls = [u.strip() for u in raw.split(",") if u.strip()] or [self.dataset_api_url]
        # Order-preserving de-duplication: a deployment where the real plane holds
        # :30002 and the mock is absent would otherwise probe one URL twice and
        # report it as two backends.
        seen: dict[str, None] = dict.fromkeys(urls)
        return tuple((describe_data_plane(u), u) for u in seen)


@lru_cache(maxsize=1)
def get_settings() -> E2ESettings:
    return E2ESettings()
