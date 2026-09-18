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

    role: Literal["provider", "consumer", "both"] = Field(
        ...,
        description=(
            "Which routers this process mounts: provider, consumer, or both. "
            "One participant runs one EDC runtime, so both roles talk to the "
            "same management API."
        ),
    )

    participant_id: str = "provider"
    participant_base_url: str = "https://rec.dataspaces.localhost"
    participant_did: str = "did:web:rec.dataspaces.localhost"
    consumer_participant_did: str = "did:web:third-party.dataspaces.localhost"

    # EDC Management API — env vars use the EDC_ prefix (no CONNECTOR_ prefix).
    #
    # **One EDC runtime per participant**, whichever roles this process plays:
    # the provider and consumer clients are the same management API. It used to
    # be two settings (`EDC_PROVIDER_MANAGEMENT_URL`, `EDC_CONSUMER_MANAGEMENT_URL`)
    # selected by role, which a both-roles process could not express.
    #
    # Management only, deliberately. The *protocol* (DSP) URLs are not here: this
    # connector never dials its own EDC's protocol endpoint, and a counter-party's
    # is looked up by DSP address in the participant registry
    # (`registry/participants.py`). The EDC's own callback address is
    # `edc.dsp.callback.address`, set in the ds-edc chart and in
    # `services/connector/config/*.properties`.
    edc_management_url: str = Field(
        default="http://localhost:19193/management",
        validation_alias="EDC_MANAGEMENT_URL",
    )
    # The path segment of EDC's v5 management API: `v5beta` at EDC 0.18.0,
    # `v5` from 0.19. The one thing the upgrade flips.
    edc_management_api_version: str = Field(
        default="v5beta",
        validation_alias="EDC_MANAGEMENT_API_VERSION",
    )
    # The participant context this connector acts for in its EDC — the `sub` of
    # its organisation client's tokens. Unset means `participant_did`, which is
    # what every ds EDC is configured with (`edc.participant.context.id`).
    edc_participant_context_id: str | None = Field(
        default=None,
        validation_alias="EDC_PARTICIPANT_CONTEXT_ID",
    )

    # ── The EDR, delivered by the EDC ────────────────────────────────────────
    #
    # EDC 0.18.0's v5 has no EDR endpoint. A transfer this connector starts
    # names a callback address, and the `TransferProcessStarted` event posted
    # there carries the EDR, which is stored here (`edr_entries`).
    #
    # `edc_callback_url` is this connector's `POST /webhooks/edc-callback` **as
    # the EDC reaches it**. Unset, no callback is requested, and a consumer
    # transfer never yields an EDR — so consumer routes refuse to start one.
    edc_callback_url: str | None = None
    # EDC puts a header on the callback whose value it reads from **its own
    # vault** under this alias (`CallbackHttpClient`), so the secret never
    # travels in a request. The same value is `edc_callback_secret` here.
    edc_callback_auth_code_id: str = "ds-connector-callback-key"
    edc_callback_secret: str = Field(default="insecure-dev-callback-key")
    edc_callback_secret_file: str | None = None
    # How long a consumer route waits for the EDR after its transfer started.
    edr_wait_timeout: float = 30.0

    # The counterparty connector's base URL, for the one off-DSP-path read a
    # consumer makes: "is this negotiation of mine waiting on a person?" (§6.6).
    # Empty disables it and the consumer simply shows REQUESTED.
    provider_connector_url: str = ""

    # No `dataset_api_url`: the data plane is not something this service calls.
    # The dataset API calls *it* (`POST /internal/dataplane/authorize`), and the
    # address the EDC hands a consumer is the asset's `data_address.base_url` in
    # `governance.yaml`. `CONNECTOR_DATASET_API_URL` still exists — `ds-e2e`
    # reads it under that name — but nothing here does, and setting it never
    # moved this service's data plane.
    provenance_url: str = "http://localhost:30000"

    # How long a contract negotiation may stay parked waiting for a data
    # subject's decision (plan §6.2's ``ds.consent.pending.ttl``). After this the
    # unanswered asks are marked `expired` and the negotiation is terminated;
    # DSP explicitly permits a new negotiation afterwards, so a consumer that
    # still wants the data simply asks again.
    #
    # Not an ODRL constraint: `edc:inForceDate` says when an *agreement* is
    # valid, not how long a negotiation may wait, and there is no upstream
    # operand for the latter. ISO 8601, days/hours/minutes/seconds only.
    consent_pending_ttl: str = "P30D"
    consent_pending_sweep_interval: float = 3600.0

    # How long a data plane may reuse an `allow` from
    # `POST /internal/dataplane/authorize`.
    #
    # This is a **security** parameter, not a performance one. An EDR token
    # carries no `exp` (EDC 0.16 `DataPlaneAuthorizationServiceImpl.createTokenParams`)
    # and nothing resolves it against EDC in our topology, so this window *is*
    # how long a revoked agreement or a withdrawn consent keeps yielding rows.
    # Raise it only with that sentence in mind.
    dataplane_decision_ttl: int = 30

    # The vault seed EDC signs EDR tokens with, and the alias inside it
    # (`edc.transfer.proxy.token.signer.privatekey.alias`). `/internal/edr-jwks`
    # serves the public half so a data plane can verify a token nothing else
    # checks. Reading the same file EDC reads is what keeps the two from
    # drifting on rotation.
    edc_vault_file: str | None = None
    edr_signer_alias: str = "participant-private-key"

    # Both intervals are read. They used to share one: `ConsumerService` took a
    # single `poll_interval` and used it for the negotiation *and* the transfer
    # poll, so `CONNECTOR_TRANSFER_POLL_INTERVAL` was documented, settable, and
    # silently overridden by the negotiation value.
    negotiation_poll_interval: float = 2.0
    negotiation_timeout: float = 120.0
    transfer_poll_interval: float = 2.0
    transfer_timeout: float = 120.0

    identity_registry_url: str = "http://identity-registry:30005"
    participant_registry_cache_ttl: float = 60.0
    #: How long an answer to "may this organisation register consent here" is
    #: reused (plan `a-collector-registers-consent-at-the-holder`). The registry
    #: also sends an invalidation hint when a relation changes; this bounds the
    #: window when that hint is lost. An outage serves the last answer for at
    #: most five times this, then refuses.
    collector_cache_ttl: float = 60.0
    participants_registry_path: str | None = None
    governance_yaml_path: str = "governance/governance.yaml"
    governance_overlay_name: str | None = None
    sharing_offers_path: str | None = Field(
        default=None,
        description="Path to sharing-offers.yaml. Defaults to the file next to "
        "governance.yaml when present.",
    )
    sharing_offers_overlay_name: str | None = None
    #: The dataspace this connector belongs to, as the `memberOf` claim spells it
    #: on the `MembershipCredential` the trust anchor signs. It is the right
    #: operand of the membership constraint in every access policy this connector
    #: publishes, so it must be **byte-identical** to the anchor's
    #: `IDENTITY_REGISTRY_DATASPACE_URI` — a mismatch denies every negotiation,
    #: which is at least the safe direction.
    dataspace_uri: str = "https://dataspaces.localhost/dataspace"
    owners_registry_cache_ttl: float = 60.0
    odrl_profile_path: str | None = None
    # ── Semantic vocabularies (`/ns/{slug}`) ─────────────────────────────────
    #
    # The registry names which vocabularies this deployment serves a local copy
    # of; the cache holds the copies. Both default to nothing registered, so a
    # zero-config dev stack never reaches the network at boot — a deployment
    # opts into that by registering entries.
    vocabularies_path: str | None = Field(
        default=None,
        description="Path to vocabularies.yaml. Defaults to the file next to "
        "governance.yaml when present.",
    )
    vocabularies_overlay_name: str | None = None
    # Under `data/`, per ADR-0008: generated and fetched material
    # lives there and nowhere else. The *registry* is committed configuration and
    # stays beside governance.yaml; only the fetched copies are cache.
    vocabulary_cache_dir: str = "data/vocabularies"
    # **The issuer is named, not mounted** (`DID-17`). Its signing key comes from
    # its DID document, resolved over did:web at request time and cached; a key
    # in a file here would be a second copy of a fact that already has one home,
    # and rotating the anchor's key would mean redeploying every service holding
    # a copy. `CONNECTOR_TRUST_ANCHOR_KEY_PATH` is gone for that reason.
    trust_anchor_did: str = "did:web:trust-anchor.dataspaces.localhost"
    trust_list_url: str | None = Field(
        default=None,
        description=(
            "The dataspace trust list (DSSC-TRF-05). When set, a credential is "
            "refused unless its issuer is listed **active** — resolution proves "
            "who signed, this proves the dataspace still stands behind them."
        ),
    )
    did_web_use_https: bool = Field(
        default=True,
        description=(
            "Resolve did:web over HTTPS. False only in dev, where Caddy serves "
            "DID documents on plain :80 — mirrors the EDC's "
            "edc.iam.did.web.use.https."
        ),
    )
    vc_insecure_dev: bool = Field(
        default=True,
        description=(
            "When True AND no trust-anchor DID is configured, user Verifiable "
            "Credentials are accepted WITHOUT signature verification (local dev "
            "only). Production MUST leave this false."
        ),
    )
    credential_status_path: str | None = None
    credential_status_url: str | None = None
    allow_unknown_participants: bool = False

    # Per-owner scoping of provider writes: how to treat a caller carrying **no**
    # organisation claims at all.
    #
    # False (default) — allow. A deployment that models no organisations is not one
    #   where every operator has lost their rights, and refusing there pushes
    #   operators towards `connector.admin`, which crosses every owner and is
    #   strictly worse than the thing being prevented.
    # True — refuse. Correct wherever organisations *are* modelled, because then a
    #   missing claim means the caller was never scoped rather than that scoping is
    #   off. A deployment with owners should set this.
    #
    # Callers who do carry organisation claims are always scoped, flag or not.
    owner_scoping_strict: bool = Field(
        default=False,
        description=(
            "Refuse a provider write when the caller carries no organisation "
            "claims. Set true where Keycloak organisations model dataset owners."
        ),
    )

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
    # Layer B, second map: a foreign IdP's **organisation** aliases → ds `Owner`
    # ids, as JSON.
    #
    #   {"CELINE-REC-01": "example-org"}
    #
    # The group map above says what a foreign role *means*; this says which owner a
    # foreign organisation *is*. Without it, per-owner scoping cannot work in a realm
    # ds did not name: the claim's aliases match no `Owner.id`, every comparison
    # fails, and the perimeter refuses every operator — fail-closed, but a lock-out.
    #
    # Applied before the owners registry, which then resolves ds's own
    # `Owner.aliases[]`. Empty means the realm already uses ds owner ids.
    owner_aliases: str = ""

    # Layer B: a foreign IdP's group names → ds role bundles, as JSON.
    #
    #   {"celine-manager": "ds-participant-admin"}
    #
    # Empty (the default) means no translation — correct wherever the realm names
    # its groups the ds way. An alias may only name a **bundle**, never a
    # capability: `ds_auth.parse_group_aliases` drops and logs anything else, so
    # deployment config cannot become a permission table.
    oidc_group_aliases: str = ""

    service_client_id: str = Field(
        default="svc-ds-connector",
        description=(
            "The audience this service verifies on incoming tokens. An identity "
            "callers address, not one this service authenticates as."
        ),
    )
    # **The credential this connector presents, everywhere** — to its own EDC's
    # management API, to identity-registry, provenance and the counterparty
    # connector. The organisation's client (`svc-ds-connector-<alias>`, plan
    # decision 3): its `sub` is this participant's context id and it holds
    # `ds_auth.MANAGEMENT_API_SCOPES` plus the connector's service grants.
    client_id: str = Field(
        default="svc-ds-connector-example-org",
        description="Keycloak client this connector authenticates as.",
    )
    client_secret: str = Field(
        default="svc-ds-connector-example-org",
        description="Secret for client_id (client-credentials).",
    )
    # No `admin_scope` / `internal_scope` / `webhook_scope`. A permission name is
    # vocabulary, not deployment configuration: it is declared in
    # `services/keycloak/clients.yaml`, granted there, and checked against a
    # literal in `dependencies.py` (`require_exact_permission("connector.internal")`
    # and friends). These three read like a knob that could rename a scope per
    # deployment; nothing read them, and had anything done so the guard and the
    # realm would have been able to disagree about what a caller must hold.

    keycloak_token_url: str = Field(
        default="http://172.17.0.1:9080/realms/dataspaces/protocol/openid-connect/token",
        description=(
            "Keycloak token endpoint for service-to-service client-credentials grants"
        ),
    )

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/connector"
    )
    debug: bool = False

    # Notification backends — comma-separated: smtp, webhook (default: empty → null)
    notify_backends: str = ""
    notify_portal_base_url: str = "https://portal.dataspaces.localhost"
    webhook_allowed_hosts: str = Field(
        default="",
        description="Comma-separated host allowlist for webhook notification_url. "
        "Empty = reject all webhook URLs (SSRF protection).",
    )

    # SMTP settings (required when notify_backends contains "smtp")
    notify_smtp_host: str | None = None
    notify_smtp_port: int = 587
    notify_smtp_user: str | None = None
    notify_smtp_password: str | None = None
    notify_smtp_from: str | None = None
    notify_smtp_tls: bool = True

    @model_validator(mode="after")
    def load_file_secrets(self):
        if self.edc_callback_secret_file:
            self.edc_callback_secret = (
                Path(self.edc_callback_secret_file).read_text().strip()
            )
        return self

    @property
    def is_provider(self) -> bool:
        return self.role in ("provider", "both")

    @property
    def is_consumer(self) -> bool:
        return self.role in ("consumer", "both")

    @property
    def participant_context_id(self) -> str:
        """This connector's participant context in its EDC."""
        return self.edc_participant_context_id or self.participant_did


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # `role` is `Field(...)` — required, and supplied by `CONNECTOR_ROLE` from the
    # environment rather than by this call. `BaseSettings` populates it during
    # `__init__`, which mypy cannot model, so it reads the required field as a
    # missing argument. Ignored narrowly, by code, so a genuinely missing
    # argument to `Settings` still fails here.
    return Settings()  # type: ignore[call-arg]
