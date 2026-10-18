"""Reissuing an organisation's credential: successor delivered, predecessor revoked.

`ir-cli org reissue` (decision D16). What an `OrganizationCredential` asserts
can grow — `organizationId` and `organizationType` were added after
organisations already held one — and a credential has no in-place update. The
DCP answer is a **successor**: issued by the anchor, written to the holder's
own store over the Storage API exactly as an issuance request's credentials are
(`issuance.deliver_to_custodian`, here with the organisation as its own
custodian), and only then the predecessor revoked in the status list.

**The order is the availability guarantee.** The holder presents what it holds,
so revoking first would leave it with nothing valid to present until the
delivery lands, and a delivery that never lands would leave it with nothing at
all. So the successor is recorded and committed first (a credential that has
left this registry must be in its issuance register, as `renewal.py` does), then
delivered; the predecessor is revoked only after the holder accepted the
successor. A failed delivery revokes nothing: the organisation keeps the
credential it has, the successor stays recorded, and the failure is reported. A
re-run issues another successor and, once one is delivered, revokes every other
OrganizationCredential this registry issued to that DID — the undelivered ones
included.

**Not enrolment.** No enrolment code is issued and nothing is re-enrolled: the
DID is already registered with its `CredentialService` entry, and that entry is
where the successor goes. Nor is it a re-verification (`org reverify`): the
legal identity is the one already verified, read from the owner as every
issuance reads it, and the agreement acceptance the issuance gate requires is
the one on record — a new acceptance is registered separately, not here.

**Refused, before anything is written:** an owner that is not registered, not
verified, has no DID, has not enrolled (its DID is not registered here), or
publishes no `CredentialService` entry; and an organisation holding no current
OrganizationCredential — the first one is `org apply`'s to issue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Credential, Did, Owner
from .enrolment import CREDENTIAL_SERVICE_TYPE, endpoint_of
from .issuance import ORGANIZATION, IssuanceError, as_utc, deliver_to_custodian
from .org_onboarding import (
    OrgOnboardingError,
    issue_organization_credential,
    organization_type,
    resolve_owner,
)
from .status_list import revoke_status_list_index

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ReissueOutcome:
    """What one reissue did, or (dry-run) would do."""

    alias: str
    did: str
    #: The successor's id; ``None`` on a dry run.
    successor: str | None = None
    #: The claims the successor carries that its predecessor did not.
    organization_id: str | None = None
    organization_type: str | None = None
    #: Where the successor went (or would go).
    endpoint: str | None = None
    delivered: bool = False
    #: Predecessors revoked — or, on a dry run, that would be.
    revoked: list[str] = field(default_factory=list)
    #: Why delivery failed; the predecessors are then untouched.
    error: str | None = None


async def _issued_org_credentials(db: AsyncSession, did: str) -> list[Credential]:
    """This registry's live OrganizationCredentials for *did*, newest first.

    Live is ``active`` or ``suspended``, as `reverify_owner` retires them. One
    with no status-list index was not issued here and is not ours to revoke.
    """
    rows = (
        (
            await db.execute(
                select(Credential).where(
                    Credential.subject_did == did,
                    Credential.credential_type == ORGANIZATION,
                    Credential.status.in_(("active", "suspended")),
                    Credential.status_list_index.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    never = datetime.min.replace(tzinfo=UTC)
    return sorted(
        rows,
        key=lambda c: (as_utc(c.expires_at) or never, as_utc(c.issued_at) or never),
        reverse=True,
    )


def _is_current(cred: Credential, now: datetime) -> bool:
    expires = as_utc(cred.expires_at)
    return cred.status == "active" and (expires is None or expires > now)


async def reissue_owner(
    db: AsyncSession,
    settings: Settings,
    alias: str,
    *,
    dry_run: bool = False,
) -> ReissueOutcome:
    """Issue *alias*'s successor OrganizationCredential, deliver it, revoke the rest.

    Commits on its own — the successor before delivery, the revocations after —
    because the two writes are separated by a network call to somebody else's
    service. A dry run checks every precondition, writes nothing and delivers
    nothing. Raises `OrgOnboardingError` for a refusal; a failed delivery is
    returned in ``error``, not raised.
    """
    owner: Owner | None = await resolve_owner(db, alias)
    if owner is None:
        raise OrgOnboardingError(
            f"Owner {alias!r} is not registered; `org apply` onboards it.",
            status_code=404,
        )
    if owner.status != "verified":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is {owner.status!r}; only a verified owner's "
            "credential is reissued."
        )
    if not owner.did:
        raise OrgOnboardingError(f"Owner {owner.id!r} has no DID.", status_code=422)
    did = owner.did

    did_row = (await db.execute(select(Did).where(Did.did == did))).scalar_one_or_none()
    if did_row is None or not did_row.active:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has not enrolled: {did} is not registered here. "
            "Reissue replaces a credential an enrolled organisation holds; `org "
            "apply` and enrolment issue the first one."
        )
    endpoint = endpoint_of(
        list(did_row.service_endpoints or []), CREDENTIAL_SERVICE_TYPE
    )
    if not endpoint:
        raise OrgOnboardingError(
            f"{did} publishes no {CREDENTIAL_SERVICE_TYPE} entry, so a successor "
            "could not be delivered; nothing was issued."
        )

    held = await _issued_org_credentials(db, did)
    now = datetime.now(UTC)
    current = next((c for c in held if _is_current(c, now)), None)
    if current is None:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} holds no current OrganizationCredential to "
            "reissue; `org apply` issues one."
        )

    outcome = ReissueOutcome(
        alias=owner.id,
        did=did,
        organization_id=owner.id,
        organization_type=organization_type(owner),
        endpoint=endpoint,
    )
    if dry_run:
        # Nothing has been written, so there is nothing to roll back.
        outcome.revoked = [c.id for c in held]
        return outcome

    # The successor re-attests what the current credential attests, with the
    # claims it lacked: the same participant roles, scopes and DSP address. The
    # legal identity is read from the owner by the issuance itself, and
    # `LEGAL_IDENTITY_FIELDS` keeps that equal to what the predecessor says.
    prior = (current.credential_json or {}).get("credentialSubject") or {}
    predecessors = [c.id for c in held]
    successor = await issue_organization_credential(
        db,
        settings,
        owner,
        roles=list(prior.get("roles") or []),
        allowed_scopes=list(prior.get("allowedScopes") or []),
        dsp_address=prior.get("dspAddress"),
    )
    signed = successor.credential_json
    outcome.successor = successor.id
    await db.commit()
    log.info("reissue %s: successor %s issued", owner.id, successor.id)

    try:
        await deliver_to_custodian(
            db,
            settings,
            custodian_did=did,
            credentials=[(ORGANIZATION, signed)],
            issuer_pid=outcome.successor,
            holder_pid=did,
        )
    except IssuanceError as exc:
        await db.rollback()
        outcome.error = exc.message
        log.error(
            "reissue %s: successor %s not delivered, predecessors kept: %s",
            outcome.alias,
            outcome.successor,
            exc.message,
        )
        return outcome
    outcome.delivered = True

    # Delivered: the holder has the successor, so the predecessors can go.
    # Revoked, as `reverify_owner` retires an OrganizationCredential (D16).
    revoked_at = datetime.now(UTC)
    for cred_id in predecessors:
        cred = await db.get(Credential, cred_id, populate_existing=True)
        if cred is None or cred.status == "revoked" or cred.status_list_index is None:
            continue
        await revoke_status_list_index(db, cred.status_list_index)
        cred.status = "revoked"
        cred.revoked_at = revoked_at
        outcome.revoked.append(cred.id)
    await db.commit()
    log.info(
        "reissue %s: %s delivered to %s, revoked %s",
        outcome.alias,
        outcome.successor,
        endpoint,
        ", ".join(outcome.revoked) or "nothing",
    )
    return outcome


__all__ = ["ReissueOutcome", "reissue_owner"]
