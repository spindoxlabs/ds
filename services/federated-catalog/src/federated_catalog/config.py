"""ds-federated-catalog configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ds-connector base URL — all DSP catalog calls go through it
    connector_url: str = "http://172.17.0.1:31001"

    # Identity-registry URL for fetching participant list
    identity_registry_url: str = "http://identity-registry:30005"

    # Fallback: Path to participants.yaml (used only if identity_registry_url is empty)
    participants_yaml: str = ""

    # Crawl interval in seconds
    crawl_interval: int = 300

    # Seconds to wait before retrying a cycle that reached no source at all.
    # `startup_delay` is a guess about how long the connector and the EDC behind
    # it take to accept connections, and on a cold boot it is regularly wrong.
    # Waiting a full `crawl_interval` to discover that would leave the catalogue
    # empty for minutes after the stack is healthy, so a cycle that connected to
    # nothing retries promptly instead.
    crawl_retry_delay: int = 15

    # Seconds to wait after startup before first crawl (allows connector to be ready)
    startup_delay: int = 10

    # Maximum datasets to store per provider (prevents memory bloat)
    max_datasets_per_provider: int = 500

    # Service identity
    base_url: str = "https://federated-catalog.dataspaces.localhost"

    # Path to catalogues.yaml — DCAT-AP sources to crawl
    dcat_sources_yaml: str = ""

    keycloak_token_url: str = Field(
        default="http://172.17.0.1:9080/realms/dataspaces/protocol/openid-connect/token",
        description=(
            "Keycloak token endpoint for service-to-service "
            "client-credentials grants"
        ),
    )
    service_client_secret: str = Field(
        default="svc-ds-federated-catalog",
        description="Client secret for service_client_id (Keycloak client-credentials)",
    )

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

    service_client_id: str = "svc-ds-federated-catalog"

    # No `read_scope`, `port` or `debug`. All three were settings nothing read:
    # `dependencies.py` names `catalog.read` literally, and the port is fixed by
    # the Dockerfile, compose and the chart. A scope name is vocabulary, not
    # configuration — an override would have silently widened what a deployment
    # accepts while every guard stayed on the old name. `test_settings_are_read`
    # is what stops another one appearing.


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
