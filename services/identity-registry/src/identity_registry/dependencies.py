from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth import Principal
from ds_auth.audience import audience_bound, transition_bound
from ds_auth.fastapi import require_permission
from ds_auth.permissions import has_permission
from fastapi import Depends, HTTPException, Request
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
#
# `credentials.write` and `memberships.write` are **audience-bound** (ADR-0026):
# a service token must have been minted for this registry (`aud`), and a
# collector client's token for nothing else. The issuance grant is also one the
# plain `svc-ds-onboarding` client held for acts that belong to an organisation:
# presented by a plain service it is accepted only under `DS_ENV=dev`, logged.
# An organisation's own token is bound to credentials linked to its organisation
# (`require_credentials_write` below).
_require_credentials_write_scope = require_permission(
    "identity-registry.admin",
    "identity-registry.credentials.write",
    perimeter=transition_bound("credential issuance or revocation"),
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
    "identity-registry.admin",
    "identity-registry.memberships.write",
    perimeter=audience_bound(),
)
# `keycloak.sync` writes the (realm, Keycloak user id) → DID mapping a person
# route's login binding reads (ADR-0024), so it is an organisation's act like the
# other two (ADR-0026, amended 2026-10-05): audience-bound, accepted from the
# plain `svc-ds-onboarding` only under `DS_ENV=dev`, and bound to the caller's
# own members by `authorize_keycloak_sync` below.
require_keycloak_sync = require_permission(
    "identity-registry.admin",
    "identity-registry.keycloak.sync",
    perimeter=transition_bound("binding a login to a DID (keycloak sync)"),
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
# * an **organisation's own client** — its collector client
#   (`svc-ds-collector-<alias>`, the one that holds the grant, ADR-0026) or any
#   client carrying its DID as `sub` (`Principal.organisation_context`) — the
#   owner whose `did` is that context, and no other, and only while that owner is
#   **verified**: a suspended organisation writes no memberships. The same
#   mapping `/consent-collectors/check` uses;
# * a **person** — an organisation in which their own groups grant the
#   permission (`Principal.grants_in`), and which is verified. No bundle grants
#   `memberships.write` today, so this only matters if one ever does;
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


async def token_owner(db: AsyncSession, principal: Principal):
    """The :class:`Owner` an organisation client's token speaks for, or ``None``.

    The token's participant context (`sub`, set by the client's hardcoded-claim
    mapper) is the organisation's DID; the owner carrying that DID is the
    organisation. ``None`` for any other token, and for a context no single
    owner carries.
    """
    from .services.consent_collectors import owner_for_did

    context = principal.organisation_context
    if not context:
        return None
    return await owner_for_did(db, context)


async def token_organisation(db: AsyncSession, principal: Principal) -> str | None:
    """The owner id an organisation client's token speaks for, or ``None``."""
    owner = await token_owner(db, principal)
    return owner.id if owner else None


VERIFIED = "verified"


async def _organisation_status(db: AsyncSession, organisation: str) -> str | None:
    """The status of the owner whose id is *organisation*, or ``None`` if none is."""
    from .db.models import Owner

    owner = await db.get(Owner, organisation)
    return owner.status if owner is not None else None


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
        owner = await token_owner(db, principal)
        own = owner.id if owner is not None else None
        if own is not None and own == organisation:
            if owner.status != VERIFIED:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Organisation '{own}' is {owner.status}, not verified: "
                        "it may not change memberships"
                    ),
                )
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
                "memberships: use the organisation's collector client "
                "(svc-ds-collector-<alias>) or identity-registry.admin"
            ),
        )
    if await _person_grants_in(
        db, principal, organisation, MEMBERSHIPS_WRITE_PERMISSION
    ):
        status = await _organisation_status(db, organisation)
        if status is not None and status != VERIFIED:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Organisation '{organisation}' is {status}, not verified: "
                    "its memberships may not change"
                ),
            )
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


# ── Whose credentials a caller may issue or revoke (ADR-0026) ────────────────
#
# `credentials.write` says a caller may issue a data-subject credential; it does
# not say for which organisation's members. Since the grant moved from the plain
# `svc-ds-onboarding` client to each organisation's collector client, the
# organisation is the token's: its `sub` (the organisation's DID) names the
# owner, and the credential must be **linked** to that organisation —
#
# * issue / transition (`POST /admin/credentials/data-subject[/transition]`): the
#   request's `linked_participant_did` — the custodian, in whose namespace the
#   person's DID lives — must be the organisation's DID;
# * revoke (`DELETE /admin/credentials/{cred_id}`), whose request names no
#   organisation: the credential's own `credentialSubject.linkedParticipant`
#   must be. A credential that is not found, or not linked to the caller, is the
#   same 403, so the route is not an oracle for credential ids.
#
# The owner must be verified. An administrator is unbounded; a plain service
# token went through the dev-only transition in the permission's perimeter.


async def authorize_credential_write(
    db: AsyncSession, principal: Principal, request: Request
) -> None:
    """Refuse (403) an organisation's credential write outside its organisation."""
    if principal.grants(ADMIN_PERMISSION) or not principal.is_organisation:
        return
    owner = await token_owner(db, principal)
    context = principal.organisation_context
    if owner is None:
        raise HTTPException(
            status_code=403,
            detail=f"'{context}' is not the DID of exactly one registered organisation",
        )
    if owner.status != VERIFIED:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Organisation '{owner.id}' is {owner.status}, not verified: it may "
                "not issue or revoke credentials"
            ),
        )

    cred_id = request.path_params.get("cred_id")
    if cred_id is not None:
        from .db.models import Credential

        cred = await db.get(Credential, cred_id)
        subject = ((cred.credential_json or {}) if cred else {}).get(
            "credentialSubject"
        ) or {}
        if cred is None or subject.get("linkedParticipant") != context:
            raise HTTPException(
                status_code=403,
                detail=(
                    "An organisation may revoke only a credential linked to "
                    f"itself ('{owner.id}')"
                ),
            )
        return

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — the route's own validation answers it
        body = None
    linked = body.get("linked_participant_did") if isinstance(body, dict) else None
    if linked != context:
        raise HTTPException(
            status_code=403,
            detail=(
                "An organisation may issue credentials only for its own members: "
                f"linked_participant_did must be its DID ('{context}'), "
                f"not {linked!r}"
            ),
        )


async def require_credentials_write(
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(_require_credentials_write_scope),
) -> Principal:
    """`credentials.write` (audience-bound), bound to the caller's organisation."""
    await authorize_credential_write(db, principal, request)
    return principal


# ── Whose logins an organisation may bind (ADR-0026, amended 2026-10-05) ─────
#
# `POST /admin/keycloak/sync` writes the (realm, Keycloak user id) → DID mapping
# that ADR-0024's person binding relies on: whoever writes it decides which
# login acts as which person. An organisation's token may bind a login only to a
# DID **its own members** hold, and the registry data that says so is the
# credential:
#
# * the DID holds a data-subject credential, not revoked, whose
#   `credentialSubject.linkedParticipant` is the token's DID. The registry signs
#   it, and issues it to an organisation only for its own DID
#   (`authorize_credential_write`), so it is the record of *this organisation
#   onboarded this person*. It also covers the person who belongs to two
#   organisations: one human keeps one DID (`issue_data_subject_credential`),
#   so the second organisation's member lives in the first one's namespace,
#   and the DID's namespace alone would refuse the second organisation;
# * **not** a membership row. An organisation writes its own memberships, and
#   that write bounds the organisation, not the DID, so a membership rule would
#   let an organisation make anybody its member and then bind its own login to
#   them;
# * a DID that is **already bound** to another login is not rebound by an
#   organisation: the same Keycloak user re-syncs (an email or username
#   correction), anything else is the operator's explicit act, as the `409` for
#   the reverse case already says.
#
# The organisation must be verified. A DID that is not found and one that is not
# the organisation's get the same 403, so the route is no oracle for DIDs. An
# administrator is unbounded; a plain service token went through the dev-only
# transition in the permission's perimeter.


async def authorize_keycloak_sync(
    db: AsyncSession,
    principal: Principal,
    did: str,
    *,
    keycloak_realm: str,
    keycloak_user_id: str,
) -> None:
    """Refuse (403) an organisation binding a login outside its own members."""
    if principal.grants(ADMIN_PERMISSION) or not principal.is_organisation:
        return
    owner = await token_owner(db, principal)
    context = principal.organisation_context
    if owner is None:
        raise HTTPException(
            status_code=403,
            detail=f"'{context}' is not the DID of exactly one registered organisation",
        )
    if owner.status != VERIFIED:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Organisation '{owner.id}' is {owner.status}, not verified: it may "
                "not bind logins to DIDs"
            ),
        )

    from sqlalchemy import select

    from .db.models import Credential, KeycloakMapping

    creds = await db.execute(
        select(Credential).where(
            Credential.subject_did == did, Credential.status != "revoked"
        )
    )
    linked = any(
        ((c.credential_json or {}).get("credentialSubject") or {}).get(
            "linkedParticipant"
        )
        == context
        for c in creds.scalars()
    )
    if not linked:
        raise HTTPException(
            status_code=403,
            detail=(
                "An organisation may bind a login only to a DID of its own members: "
                "the DID must hold a credential, not revoked, linked to "
                f"'{owner.id}'"
            ),
        )

    mapped = await db.execute(select(KeycloakMapping).where(KeycloakMapping.did == did))
    mapping = mapped.scalar_one_or_none()
    if mapping is not None and (
        mapping.keycloak_realm != keycloak_realm
        or mapping.keycloak_user_id != keycloak_user_id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "This DID is already bound to another login. Rebinding is an "
                "operator's explicit act (DELETE /admin/keycloak/mappings/{did}, "
                "then sync), never an organisation's"
            ),
        )
