"""ds-auth — shared JWT authentication and unified scope/group authorization.

Core (framework-free)::

    from ds_auth import OidcConfig, Principal, verify_token

FastAPI guard (needs the ``fastapi`` extra)::

    from ds_auth.fastapi import require_permission

The claim semantics mirror ``celine-sdk`` so a Keycloak realm synced from
``clients.yaml`` authorizes identically across projects — a compatible
approach, not a code dependency.
"""
from __future__ import annotations

from .config import OidcConfig, default_jwks_uri
from .errors import (
    AuthConfigError,
    AuthError,
    PermissionDenied,
    TokenInvalid,
    TokenMissing,
)
from .jwt import (
    extract_groups,
    extract_scopes,
    get_bearer_token,
    is_service_account,
    verify_token,
)
from .permissions import grant_satisfies, has_permission
from .principal import Principal

__all__ = [
    "OidcConfig",
    "default_jwks_uri",
    "Principal",
    "verify_token",
    "get_bearer_token",
    "extract_groups",
    "extract_scopes",
    "is_service_account",
    "grant_satisfies",
    "has_permission",
    "AuthError",
    "AuthConfigError",
    "TokenInvalid",
    "TokenMissing",
    "PermissionDenied",
]
