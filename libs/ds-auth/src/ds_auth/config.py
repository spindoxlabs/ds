"""OIDC verification configuration.

A service builds an :class:`OidcConfig` from its own settings and stores it on
``app.state.oidc_config`` (see :mod:`ds_auth.fastapi`). The config is a plain
dataclass — no environment coupling — so each service keeps its existing
settings prefix (e.g. ``CONNECTOR_OIDC_ISSUER_URL``) and maps it in.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def default_jwks_uri(issuer_url: str) -> str:
    """Derive the Keycloak JWKS endpoint from a realm issuer URL."""
    return f"{issuer_url.rstrip('/')}/protocol/openid-connect/certs"


@dataclass(frozen=True)
class OidcConfig:
    """Everything needed to verify a bearer token.

    Fail-closed by design: if ``issuer_url`` is unset and ``insecure_dev`` is
    False, verification raises :class:`ds_auth.errors.AuthConfigError` rather
    than silently trusting unverified tokens (the old dev-only behaviour that
    was a production footgun).
    """

    # Keycloak realm issuer, e.g. http://keycloak:8080/realms/dataspaces
    issuer_url: str | None = None
    # Defaults to ``default_jwks_uri(issuer_url)`` when unset.
    jwks_uri: str | None = None
    # Expected primary audience — this service's client id.
    audience: str | None = None
    # Extra audiences to also accept (e.g. shared gateways). Use sparingly.
    allowed_audiences: tuple[str, ...] = ()
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    leeway: int = 30
    # Explicit, LOUD opt-in for local dev without a reachable Keycloak.
    # When True and no issuer is configured, signatures are NOT verified.
    insecure_dev: bool = False

    _resolved_jwks: str | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def verification_enabled(self) -> bool:
        return bool(self.issuer_url)

    @property
    def resolved_jwks_uri(self) -> str | None:
        if self.jwks_uri:
            return self.jwks_uri
        if self.issuer_url:
            return default_jwks_uri(self.issuer_url)
        return None

    @property
    def expected_audiences(self) -> list[str]:
        auds: list[str] = []
        if self.audience:
            auds.append(self.audience)
        auds.extend(a for a in self.allowed_audiences if a and a != self.audience)
        return auds
