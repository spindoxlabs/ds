from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PROVENANCE_", env_file=".env", extra="ignore"
    )

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/provenance"
    )
    debug: bool = False

    oidc_issuer_url: str | None = None
    oidc_insecure_dev: bool = Field(
        default=True,
        description=(
            "When True AND no issuer is configured, tokens are accepted WITHOUT "
            "signature/audience verification (local dev only). Production MUST set "
            "the issuer URL, which enforces verification regardless of this flag."
        ),
    )
    # Layer B: a foreign IdP's group names → ds role bundles, as JSON.
    #
    #   {"celine-manager": "ds-participant-admin"}
    #
    # Empty (the default) means no translation — correct wherever the realm names
    # its groups the ds way. An alias may only name a **bundle**, never a
    # capability: `ds_auth.parse_group_aliases` drops and logs anything else, so
    # deployment config cannot become a permission table.
    oidc_group_aliases: str = ""

    service_client_id: str = "svc-ds-provenance"
    # No `read_scope` / `write_scope`: a permission name is vocabulary, not
    # configuration. It is declared in `services/keycloak/clients.yaml`, granted
    # there, reached through a bundle, and checked against a literal in
    # `dependencies.py`. A per-deployment override would let the guard and the
    # realm disagree about what a caller must hold, while looking like a knob.
    #
    # No `base_url` either — nothing generated an IRI from it. Every IRI this
    # service mints is a URN (`urn:activity:…`), and `context_url` is the one
    # absolute URL it publishes.
    context_url: str = "https://provenance.dataspaces.localhost/prov/context"
    max_lineage_depth: int = 20

    # ── Data-subject credentials (GET /prov/my/events) ────────────────────────
    #
    # A subject reads their own history with a VC-JWT, not a scope, so these
    # mirror the connector's settings of the same name — the same credential is
    # presented to both services and must verify identically.
    # **The issuer is named, not mounted** (`DID-17`) — see the connector's
    # settings of the same name for why. The same credential is presented to
    # both services and must verify identically, so these must not drift.
    trust_anchor_did: str = "did:web:trust-anchor.dataspaces.localhost"
    trust_list_url: str | None = None
    did_web_use_https: bool = True
    vc_insecure_dev: bool = Field(
        default=True,
        description=(
            "When True AND no trust-anchor DID is configured, user Verifiable "
            "Credentials are accepted WITHOUT signature verification (local dev "
            "only). Production MUST leave this false."
        ),
    )
    credential_status_path: str | None = None
    # Required outside dev (`ProductionGuard`): a verifier that reads no register
    # never sees a revocation. Mirrors the connector's setting.
    credential_status_url: str | None = None
    credential_status_cache_seconds: float = Field(
        default=900.0,
        description=(
            "How long a verified credential status register is reused — the "
            "revocation latency. Defaults to EDC's revocation cache (15 min)."
        ),
    )

    # ── The person's login (R3) ───────────────────────────────────────────────
    #
    # `GET /prov/my/events` takes the person's own Keycloak login token beside the
    # credential, and the identity registry says which subject that login is
    # bound to (`GET /users/me`, asked with the person's token — this service
    # needs no credential of its own for it). Unset `person_token_required`
    # means required everywhere except DS_ENV=dev. See `ds_auth.person_binding`.
    identity_registry_url: str | None = None
    person_token_required: bool | None = None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
