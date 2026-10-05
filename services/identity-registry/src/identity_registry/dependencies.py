from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth import Principal
from ds_auth.fastapi import require_permission
from ds_auth.permissions import has_permission
from fastapi import HTTPException
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
# (via the `scope` claim) and user tokens (via an allowlisted realm role, or a group
# inside the organisation concerned, ADR-0023). ``{service}.admin`` is a superset, so
# an admin service token or a platform-admin user both satisfy the
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

# `GET /owners/resolve` — the alias-aware read beside `GET /admin/owners/{id}`.
#
# Three grants reach it, and each is here for a caller that exists. `admin` by
# the superset rule. `identity-registry.read` because the **connector** resolves
# an owner alias on every governance scoping decision
# (`ds.governance.owners.HttpOwnersRegistry`, wired in `connector/main.py`) and
# holds nothing narrower. `organizations.read` because an onboarding service
# resolves its bound community's organisation at boot — the exact words
# `services/keycloak/clients.yaml` uses to justify granting it — and P6 removed
# the admin grant from that client on purpose.
#
# It is deliberately **not** `require_org_read`. That guard is the one the
# endpoint had by habit inverted: admitting `organizations.read` while dropping
# `identity-registry.read` would fix the onboarding caller by breaking the
# connector. Widening the *client* instead is the other wrong move —
# `identity-registry.read` reaches the participant registry and the presentation
# queries, and an onboarding funnel has no business in either.
require_owner_resolve = require_permission(
    "identity-registry.admin",
    "identity-registry.read",
    "identity-registry.organizations.read",
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

# "This organisation may register consent for its members at that holder" —
# plan `a-collector-registers-consent-at-the-holder`. A governance act about two
# organisations, so it has its own grant rather than riding
# `organizations.write`: an onboarding reviewer editing an application has no
# business deciding who may speak for whose members at a third party's connector.
# The connector's read is `GET /consent-collectors/check`, on `.read`.
require_collectors_write = require_permission(
    "identity-registry.admin", "identity-registry.collectors.write"
)


# ── Whose memberships a caller may touch ─────────────────────────────────────
#
# `memberships.write` says a caller may register memberships; it does not say
# *in which organisation*. Checked alone, any holder could make any DID a member
# of any organisation — and the connector's "the subject is a member of the
# organisation this caller speaks for" check (`connector/api/v1/consent.py`
# `_admit_writer`) reads exactly these rows, so an unscoped write would let one
# organisation vouch for another's members.
#
# The rule, applied by the routes after the permission guard:
#
# * `identity-registry.admin` (an operator, `ir-cli`, a platform admin) — any
#   organisation;
# * an **organisation's own client** (`svc-ds-connector-<alias>`,
#   `Principal.organisation_context`) — the owner whose `did` is that context,
#   and no other. The same mapping `/consent-collectors/check` uses;
# * a **person** — an organisation in which their own groups grant the
#   permission (`Principal.grants_in`). No bundle grants `memberships.write`
#   today, so this only matters if one ever does;
# * a **plain service token** — refused. It names no organisation, so there is
#   nothing to scope it to; the connector refuses it on the consent write for
#   the same reason.

ADMIN_PERMISSION = "identity-registry.admin"
MEMBERSHIPS_WRITE_PERMISSION = "identity-registry.memberships.write"
MEMBERSHIP_READ_PERMISSION = "identity-registry.membership.read"


async def canonical_organisation(db: AsyncSession, alias: str) -> str:
    """The owner id *alias* names, or *alias* verbatim when it names no owner."""
    from .services.org_onboarding import resolve_owner

    owner = await resolve_owner(db, alias)
    return owner.id if owner else alias


async def token_organisation(db: AsyncSession, principal: Principal) -> str | None:
    """The owner id an organisation client's token speaks for, or ``None``.

    The token's participant context (`sub`, set by the client's hardcoded-claim
    mapper) is the organisation's DID; the owner carrying that DID is the
    organisation. ``None`` for any other token, and for a context no single
    owner carries.
    """
    from .services.consent_collectors import owner_for_did

    context = principal.organisation_context
    if not context:
        return None
    owner = await owner_for_did(db, context)
    return owner.id if owner else None


async def _person_grants_in(
    db: AsyncSession, principal: Principal, organisation: str, *perms: str
) -> bool:
    """Does one of this person's organisations, resolved, grant *perms* there?"""
    for org in principal.organizations:
        if await canonical_organisation(db, org.alias) != organisation:
            continue
        if principal.grants_in(org.alias, *perms):
            return True
    return False


async def authorize_membership_write(
    db: AsyncSession, principal: Principal, organisation: str
) -> None:
    """Refuse (403) a membership write outside the caller's own organisation.

    *organisation* is already canonical (:func:`canonical_organisation`), so an
    alias of the caller's own organisation is its own organisation.
    """
    if principal.grants(ADMIN_PERMISSION):
        return
    if principal.is_organisation:
        own = await token_organisation(db, principal)
        if own is not None and own == organisation:
            return
        raise HTTPException(
            status_code=403,
            detail=(
                f"An organisation client may change memberships of its own "
                f"organisation only: this token speaks for "
                f"'{own or principal.organisation_context}', not '{organisation}'"
            ),
        )
    if principal.is_service:
        raise HTTPException(
            status_code=403,
            detail=(
                "A service token names no organisation, so it may not change "
                "memberships: use the organisation's own client "
                "(svc-ds-connector-<alias>) or identity-registry.admin"
            ),
        )
    if await _person_grants_in(
        db, principal, organisation, MEMBERSHIPS_WRITE_PERMISSION
    ):
        return
    raise HTTPException(
        status_code=403,
        detail=f"Not permitted to change memberships of '{organisation}'",
    )


async def authorize_membership_check(
    db: AsyncSession, principal: Principal, organisation: str
) -> None:
    """Bound a **person's** `/memberships/check` to their own organisations.

    A service — the connector — is not bounded, by design: it asks whether a
    subject belongs to a *collector* organisation (consent) or to a recipient
    (the sharing circle), neither of which is its own. A person's
    `membership.read` comes from an organisation's groups (`ds-participant-admin`)
    and, like every organisation grant, holds in that organisation only.
    """
    if principal.is_service:
        return
    if has_permission(
        principal.platform_authority,
        (ADMIN_PERMISSION, MEMBERSHIP_READ_PERMISSION),
    ):
        return
    if await _person_grants_in(db, principal, organisation, MEMBERSHIP_READ_PERMISSION):
        return
    raise HTTPException(
        status_code=403,
        detail=f"Not permitted to read memberships of '{organisation}'",
    )
