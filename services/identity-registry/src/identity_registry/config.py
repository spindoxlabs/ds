from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_REGISTRY_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/identity_registry"
    )
    debug: bool = False

    encryption_key: str = Field(
        default="dev-encryption-key-change-in-production",
        description="Fernet key for encrypting private keys at rest",
    )

    oidc_issuer_url: str | None = Field(
        default=None,
        description="OIDC issuer URL for JWT verification on admin endpoints",
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
        default="svc-ds-identity-registry",
        description="Keycloak client ID for this service (used as JWT audience)",
    )

    service_client_secret: str = Field(
        default="svc-ds-identity-registry",
        description="Secret for this service's own outbound calls.",
    )

    keycloak_token_url: str | None = Field(
        default=None,
        description=(
            "Token endpoint for this service's outbound calls. Only used to tell "
            "connectors their participant cache is stale; unset means no "
            "notification, which costs a minute of staleness, not correctness."
        ),
    )

    connector_urls: str = Field(
        default="",
        description=(
            "Comma-separated connector base URLs to notify when the participant "
            "registry changes (promote, suspend, revoke). Empty disables it."
        ),
    )

    admin_scope: str = Field(
        default="identity-registry.admin",
        description="Required JWT scope for admin endpoints",
    )

    read_scope: str = Field(
        default="identity-registry.read",
        description="Required JWT scope for participant read endpoints",
    )

    resolve_scope: str = Field(
        default="identity-registry.resolve",
        description="Required JWT scope for user resolve endpoint",
    )

    keycloak_admin_url: str | None = Field(
        default=None,
        validation_alias="KEYCLOAK_ADMIN_URL",
        description="Keycloak admin API base URL",
    )

    keycloak_client_id: str = Field(
        default="ds-identity-registry",
        validation_alias="KEYCLOAK_CLIENT_ID",
    )

    keycloak_client_secret: str = Field(
        default="insecure-dev-secret",
        validation_alias="KEYCLOAK_CLIENT_SECRET",
    )

    default_credential_ttl_days: int = 365
    max_credential_ttl_days: int = 730

    trust_anchor_domain: str = Field(
        default="trust-anchor.dataspaces.localhost",
        description="Domain for the trust-anchor DID",
    )

    # ── Provisioning bundle ──────────────────────────────────────────────────
    #
    # A third party configures its own deployment from these, so they must be
    # addresses reachable *from outside this cluster* — an in-cluster service DNS
    # name in a bundle produces a connector that cannot resolve its own trust
    # anchor.
    identity_registry_public_url: str | None = Field(
        default=None,
        description=(
            "Externally reachable base URL of this registry, used in provisioning "
            "bundles. Defaults to https://<trust_anchor_domain> when unset."
        ),
    )

    keycloak_issuer_url: str | None = Field(
        default=None,
        validation_alias="KEYCLOAK_ISSUER_URL",
        description=(
            "Realm issuer URL handed to a third party's connector in its bundle."
        ),
    )

    keycloak_realm: str = Field(
        default="dataspaces",
        validation_alias="KEYCLOAK_REALM",
    )

    # Realm admin credentials, used only to provision a third party's connector
    # client at bundle time. Unset disables that step: the bundle is still issued,
    # without Keycloak credentials in it.
    keycloak_admin_user: str | None = Field(
        default=None, validation_alias="KEYCLOAK_ADMIN_USERNAME"
    )
    keycloak_admin_password: str | None = Field(
        default=None, validation_alias="KEYCLOAK_ADMIN_PASSWORD"
    )

    credentials_context_url: str = Field(
        default="https://dataspaces.localhost/ns/credentials/v1",
        description="Credentials JSON-LD context URL",
    )

    dataspace_uri: str = Field(
        default="https://dataspaces.localhost/dataspace",
        description="Dataspace membership URI",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
