from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROVENANCE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/provenance"
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
    read_scope: str = "provenance.read"
    write_scope: str = "provenance.write"
    base_url: str = "https://provenance.dataspaces.localhost"
    context_url: str = "https://provenance.dataspaces.localhost/prov/context"
    max_lineage_depth: int = 20

    # ── Data-subject credentials (GET /prov/my/events) ────────────────────────
    #
    # A subject reads their own history with a VC-JWT, not a scope, so these
    # mirror the connector's settings of the same name — the same credential is
    # presented to both services and must verify identically.
    trust_anchor_did: str = "did:web:trust-anchor.dataspaces.localhost"
    trust_anchor_key_path: str | None = None
    vc_insecure_dev: bool = Field(
        default=True,
        description=(
            "When True AND no trust-anchor key is configured, user Verifiable "
            "Credentials are accepted WITHOUT signature verification (local dev "
            "only). Production MUST set PROVENANCE_TRUST_ANCHOR_KEY_PATH."
        ),
    )
    credential_status_path: str | None = None
    credential_status_url: str | None = None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
