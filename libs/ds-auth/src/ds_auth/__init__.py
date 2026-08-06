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

from .bundles import (
    MACHINE_IDENTITY_PERMISSIONS,
    ROLE_BUNDLES,
    SERVICE_ONLY_PERMISSIONS,
    all_bundled_permissions,
    bundle_capabilities,
    expand_bundles,
    parse_group_aliases,
)
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
    extract_organizations,
    extract_realm_groups,
    extract_scopes,
    get_bearer_token,
    is_service_account,
    verify_token,
)
from .models import Organization
from .permissions import grant_satisfies, has_exact_permission, has_permission
from .principal import Principal

__all__ = [
    # The role-bundle table and its helpers. Imported here and named nowhere,
    # so `ruff` flagged six unused imports on every run and the names were
    # importable from `ds_auth` only by accident — `from ds_auth import
    # expand_bundles` worked, `ds_auth.__all__` denied it. `bundles_export.py`
    # and `test_vocabulary.py` both rely on them.
    "MACHINE_IDENTITY_PERMISSIONS",
    "ROLE_BUNDLES",
    "SERVICE_ONLY_PERMISSIONS",
    "all_bundled_permissions",
    "bundle_capabilities",
    "expand_bundles",
    "OidcConfig",
    "default_jwks_uri",
    "Organization",
    "parse_group_aliases",
    "Principal",
    "verify_token",
    "get_bearer_token",
    "extract_groups",
    "extract_organizations",
    "extract_realm_groups",
    "extract_scopes",
    "is_service_account",
    "grant_satisfies",
    "has_permission",
    "has_exact_permission",
    "AuthError",
    "AuthConfigError",
    "TokenInvalid",
    "TokenMissing",
    "PermissionDenied",
    "ServiceTokenProvider",
]


def __getattr__(name: str):
    if name == "ServiceTokenProvider":
        from .service_token import ServiceTokenProvider
        return ServiceTokenProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
