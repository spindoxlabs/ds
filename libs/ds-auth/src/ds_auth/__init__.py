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
    ORGANISATION_BUNDLES,
    ORGANISATION_PERMISSIONS,
    PLATFORM_ADMIN_ROLE,
    PLATFORM_BUNDLES,
    REALM_ROLE_BUNDLES,
    ROLE_BUNDLES,
    SERVICE_ONLY_PERMISSIONS,
    all_bundled_permissions,
    bundle_capabilities,
    organisation_authority,
    parse_group_aliases,
    platform_authority,
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
    extract_organizations,
    extract_realm_roles,
    extract_scopes,
    get_bearer_token,
    is_service_account,
    verify_token,
)
from .management_api import (
    COLLECTOR_CLIENT_DEFAULT_SCOPES,
    COLLECTOR_CLIENT_OPTIONAL_SCOPES,
    COLLECTOR_CLIENT_PREFIX,
    CONNECTOR_AUDIENCE,
    CONNECTOR_AUDIENCES,
    CONNECTOR_SERVICE_SCOPES,
    CONSENT_AUDIENCE_SCOPE,
    CONSENT_COLLECTOR_READ_SCOPE,
    CONSENT_PROVISION_SCOPE,
    CREDENTIALS_WRITE_SCOPE,
    DISCLOSURE_RECORD_SCOPE,
    DS_SERVICE_AUDIENCES,
    EDC_MANAGEMENT_AUDIENCE,
    EDC_MANAGEMENT_SCOPE,
    EDC_TOKEN_SCOPE,
    IDENTITY_REGISTRY_AUDIENCE,
    KEYCLOAK_SYNC_SCOPE,
    MANAGEMENT_API_SCOPES,
    MEMBERSHIPS_WRITE_SCOPE,
    ONBOARDING_TRANSITION_SCOPES,
    ORGANISATION_ACTION_SCOPES,
    ORGANISATION_CLIENT_DEFAULT_SCOPES,
    ORGANISATION_CLIENT_OPTIONAL_SCOPES,
    ORGANISATION_CLIENT_PREFIX,
    ORGANISATION_CLIENT_SCOPES,
    PROVENANCE_AUDIENCE,
    PROVENANCE_WRITE_SCOPE,
    PROVIDER_WRITE_SCOPE,
    SCOPE_AUDIENCES,
    collector_client_id,
    is_management_api_scope,
    organisation_client_id,
    scope_satisfies,
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
    # The two levels: platform (realm roles) and organisation (its own groups).
    "PLATFORM_ADMIN_ROLE",
    "PLATFORM_BUNDLES",
    "ORGANISATION_BUNDLES",
    "ORGANISATION_PERMISSIONS",
    "REALM_ROLE_BUNDLES",
    "platform_authority",
    "organisation_authority",
    # EDC's management-API scopes ds grants, and to whom (`management_api.py`).
    "CONNECTOR_AUDIENCES",
    "CONNECTOR_SERVICE_SCOPES",
    "EDC_MANAGEMENT_AUDIENCE",
    "EDC_MANAGEMENT_SCOPE",
    "EDC_TOKEN_SCOPE",
    "MANAGEMENT_API_SCOPES",
    "ORGANISATION_CLIENT_DEFAULT_SCOPES",
    "ORGANISATION_CLIENT_OPTIONAL_SCOPES",
    "ORGANISATION_CLIENT_SCOPES",
    "ORGANISATION_CLIENT_PREFIX",
    "is_management_api_scope",
    "organisation_client_id",
    "scope_satisfies",
    # The organisation's acts: one audience per scope, the collector client
    # (`svc-ds-collector-<alias>`) and the onboarding transition (ADR-0026).
    "COLLECTOR_CLIENT_DEFAULT_SCOPES",
    "COLLECTOR_CLIENT_OPTIONAL_SCOPES",
    "COLLECTOR_CLIENT_PREFIX",
    "CONNECTOR_AUDIENCE",
    "CONSENT_AUDIENCE_SCOPE",
    "CONSENT_COLLECTOR_READ_SCOPE",
    "CONSENT_PROVISION_SCOPE",
    "CREDENTIALS_WRITE_SCOPE",
    "DISCLOSURE_RECORD_SCOPE",
    "DS_SERVICE_AUDIENCES",
    "IDENTITY_REGISTRY_AUDIENCE",
    "KEYCLOAK_SYNC_SCOPE",
    "MEMBERSHIPS_WRITE_SCOPE",
    "ONBOARDING_TRANSITION_SCOPES",
    "ORGANISATION_ACTION_SCOPES",
    "PROVENANCE_AUDIENCE",
    "PROVENANCE_WRITE_SCOPE",
    "PROVIDER_WRITE_SCOPE",
    "SCOPE_AUDIENCES",
    "collector_client_id",
    "OidcConfig",
    "default_jwks_uri",
    "Organization",
    "parse_group_aliases",
    "Principal",
    "verify_token",
    "get_bearer_token",
    "extract_organizations",
    "extract_realm_roles",
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
