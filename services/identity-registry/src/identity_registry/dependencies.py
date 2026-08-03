from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth.fastapi import require_permission
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db.engine import get_session_factory
from .services.did_resolver import DidResolver

log = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def get_settings_dep() -> Settings:
    return get_settings()


def get_did_resolver() -> DidResolver:
    """Resolver for counterparty DID documents.

    A dependency rather than a module global so a test can substitute a document
    without an HTTP server, and so a deployment's scheme choice
    (``did_web_use_https``) is read once, where it is configured.
    """
    settings = get_settings()
    return DidResolver(
        use_https=settings.did_web_use_https,
        timeout_seconds=settings.did_resolution_timeout_seconds,
    )


# ── Authorization guards ────────────────────────────────────────────────────
#
# One unified guard (ds_auth.require_permission) authorizes BOTH service tokens
# (via the `scope` claim) and user tokens (via Keycloak groups). ``{service}.admin``
# is a superset, so an admin service token or an admin-group user both satisfy the
# finer permissions below.

require_admin_scope = require_permission("identity-registry.admin")
require_read_scope = require_permission("identity-registry.read")
require_resolve_scope = require_permission("identity-registry.resolve")
require_admin_or_read_scope = require_permission(
    "identity-registry.admin", "identity-registry.read"
)
require_membership_read_scope = require_permission(
    "identity-registry.admin", "identity-registry.membership.read"
)

# ── Onboarding, split out of the admin grant ─────────────────────────────────
#
# An operator console should be grantable exactly what its pages need, and
# `identity-registry.admin` hands over every endpoint here — including DID and key
# management. These name what they permit instead. The admin grant still satisfies
# each of them by the superset rule, so `ir-cli` and the bootstrap are unaffected.
#
# `promote` is deliberately not part of `write`: marking an application verified is
# reviewable clerical work, while promotion is the irreversible act that turns an
# applicant into a DSP counterparty others will negotiate with.
require_org_read = require_permission(
    "identity-registry.admin", "identity-registry.organizations.read"
)
require_org_write = require_permission(
    "identity-registry.admin", "identity-registry.organizations.write"
)
require_org_promote = require_permission(
    "identity-registry.admin", "identity-registry.organizations.promote"
)
require_agreements_read = require_permission(
    "identity-registry.admin",
    "identity-registry.read",
    "identity-registry.agreements.read",
)
require_participants_write = require_permission(
    "identity-registry.admin", "identity-registry.participants.write"
)

# ── What an onboarding service actually does ─────────────────────────────────
#
# P6 split organisations and agreements out of the admin grant but left
# credentials, memberships and keycloak-sync on it — which is most of what an
# external onboarding application calls, so such a service still had to hold
# `identity-registry.admin`. That is a superset over every endpoint here,
# including DID and key management: one long-lived process able to mint or
# delete any identity in the dataspace, to do three narrow things.
#
# These name the three. `clients.yaml` refuses `*.admin` to a service client in
# a comment; this is what makes that possible to honour.
require_credentials_write = require_permission(
    "identity-registry.admin", "identity-registry.credentials.write"
)
# One (subject, type) question at a time — `GET /credentials/check`. Deliberately
# not `identity-registry.read`, and deliberately not the `admin` that guards
# `GET /admin/credentials`: enumerating what a person holds and asking whether
# they hold one named thing are different disclosures, exactly as
# `/admin/memberships` and `/memberships/check` are. The connector needs the
# second to evaluate a sharing offer's `admitted_by`, and a service client may
# not hold `*.admin`.
require_credential_read = require_permission(
    "identity-registry.admin", "identity-registry.credentials.read"
)
require_memberships_write = require_permission(
    "identity-registry.admin", "identity-registry.memberships.write"
)
require_keycloak_sync = require_permission(
    "identity-registry.admin", "identity-registry.keycloak.sync"
)
