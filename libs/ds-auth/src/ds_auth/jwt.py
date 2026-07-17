"""JWT decoding and claim extraction.

The claim-shape helpers (:func:`extract_groups`, :func:`is_service_account`)
deliberately mirror the semantics of ``celine-sdk``'s ``auth.jwt`` so that the
*same* Keycloak realm — synced from ``clients.yaml`` by the shared
``celine-policies`` CLI — authorizes identically in both projects. This is a
verbatim *approach*, not a code dependency: there is no import edge between the
repos.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from .config import OidcConfig
from .errors import AuthConfigError, TokenInvalid, TokenMissing

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def _jwks_client(jwks_uri: str) -> PyJWKClient:
    logger.info("ds-auth: loading JWKS from %s", jwks_uri)
    return PyJWKClient(jwks_uri, cache_jwk_set=True, lifespan=3600)


def get_bearer_token(authorization_header: str | None) -> str:
    """Extract the raw token from an ``Authorization: Bearer <t>`` header."""
    if not authorization_header or not authorization_header.lower().startswith("bearer "):
        raise TokenMissing("Missing bearer token")
    token = authorization_header.split(" ", 1)[1].strip()
    if not token:
        raise TokenMissing("Empty bearer token")
    return token


def extract_groups(claims: dict) -> list[str]:
    """Merge realm-level and org-level groups into a flat, deduped list.

    Realm groups come from the top-level ``groups`` claim. Org groups come from
    ``organization.<alias>.groups`` (legacy / celine-policies) or
    ``organization.<alias>.roles`` (KC 26+ native organizations). Leading
    slashes are stripped so ``/managers`` and ``managers`` compare equal.
    """
    raw: list[str] = []

    realm = claims.get("groups")
    if isinstance(realm, list):
        raw.extend(realm)

    orgs = claims.get("organization")
    if isinstance(orgs, dict):
        for org_data in orgs.values():
            if isinstance(org_data, dict):
                for key in ("groups", "roles"):
                    entries = org_data.get(key)
                    if isinstance(entries, list):
                        raw.extend(entries)

    seen: set[str] = set()
    result: list[str] = []
    for g in raw:
        if not isinstance(g, str):
            continue
        normalized = g.lstrip("/")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def extract_scopes(claims: dict) -> list[str]:
    """Return the OAuth2 ``scope`` claim as a list (space-delimited or array)."""
    scope = claims.get("scope", "")
    if isinstance(scope, str):
        return scope.split()
    if isinstance(scope, list):
        return [s for s in scope if isinstance(s, str)]
    return []


def is_service_account(claims: dict) -> bool:
    """Detect a Keycloak ``client_credentials`` service-account token.

    Keycloak sets ``preferred_username`` to ``service-account-<client_id>`` for
    every client-credentials grant — the most reliable signal. User tokens are
    identified by an email, group membership, or a human ``preferred_username``.
    """
    preferred_username = claims.get("preferred_username", "")

    if isinstance(preferred_username, str) and preferred_username.startswith(
        "service-account-"
    ):
        return True

    if claims.get("gty") == "client-credentials":
        return True

    if claims.get("email"):
        return False
    if extract_groups(claims):
        return False
    if preferred_username and not preferred_username.startswith("service-account-"):
        return False

    # Generic heuristic: a client id but no human behind the token.
    if claims.get("client_id") and not claims.get("email"):
        return True

    return False


def verify_token(token: str, config: OidcConfig) -> dict:
    """Verify a bearer token and return its claims.

    Fail-closed: with no issuer configured, raises :class:`AuthConfigError`
    unless ``insecure_dev`` is explicitly set (a loud, dev-only escape hatch).
    """
    if config.verification_enabled:
        jwks_uri = config.resolved_jwks_uri
        if not jwks_uri:
            raise AuthConfigError("issuer_url set but no JWKS URI could be resolved")
        try:
            signing_key = _jwks_client(jwks_uri).get_signing_key_from_jwt(token)
        except Exception as exc:  # network / unknown-kid / malformed
            raise TokenInvalid(f"Could not resolve signing key: {exc}") from exc

        auds = config.expected_audiences
        try:
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=list(config.algorithms),
                audience=auds or None,
                issuer=config.issuer_url,
                leeway=config.leeway,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": bool(auds),
                    "verify_iss": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalid(str(exc)) from exc

    # No issuer configured.
    if not config.insecure_dev:
        raise AuthConfigError(
            "OIDC issuer not configured and insecure_dev is False — refusing to "
            "accept unverified tokens. Set the issuer URL, or opt in explicitly "
            "with insecure_dev=True for local development."
        )

    logger.warning(
        "ds-auth: INSECURE_DEV — accepting token WITHOUT signature/audience "
        "verification. Never enable this outside local development."
    )
    try:
        return jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalid(str(exc)) from exc
