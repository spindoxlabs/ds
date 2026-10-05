"""Renewing a person's credential before it expires.

A `DataSubjectCredential` lives a month (`data_subject_credential_ttl_days`).
`ir-cli credential renew`, run daily, issues the **successor** of every one in
the last part of its life (`…_renewal_window_days`), so the person never sees
an expiry: the portal reads the newest live credential at each login and
presents that one.

**A successor, not an edit.** Same subject, same DID, same role, same
`linkedParticipant`, the same claims; a new id and a new status-list index.
It is delivered exactly as a first issuance is, to the linked organisation's
custodian and nobody else.

**The predecessor is not revoked.** It expires on its own. A revocation would
tell every verifier the attestation was withdrawn, and a copy somebody cached a
minute ago would stop working mid-session. So for a few days a person holds
two live credentials for one role, and every path that retires "the"
credential — a release, an offboarding, a role transition, an admin delete of a
DID — retires every live one (`issuance.active_data_subject_credentials`).

**Renewed only from a live predecessor**, and only while the person is still
somebody's member:

* the predecessor is `active` — not revoked, not suspended;
* the DID is not spent (every credential revoked) nor deactivated: a released
  identity is never revived (ADR-0028);
* the linked organisation is known and `verified` — a suspended one speaks for
  nobody (ADR-0026);
* the IR membership (DID, that organisation) still stands.

Each of these is checked **again inside the transaction that inserts the
successor**, with the rows locked, not only when the candidates are chosen. A
release removes the membership and then revokes; a renewal that read the
membership before the release deleted it would otherwise issue a credential
the release never saw.

**Expired is recoverable.** A credential past its expiry, of a person who still
passes every check above, is renewed by the daily job for
`…_renewal_grace_days` after it expired, and by `--subject` at any time (an
operator's recovery). Expiry is the only liveness rule relaxed.

**Idempotent.** Only the newest live credential of each (DID, role,
organisation) is ever a candidate, and a successor is outside the window the
day it is issued, so a second run the same day issues nothing. A successor
whose delivery failed is re-delivered on the following runs while it is
recent; the holder's Storage API is idempotent on the credential id.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Credential, Did, OrganizationMembership, Owner
from .crypto import decrypt_private_jwk, generate_credential_id, require_private_jwk
from .did import subject_id_of
from .issuance import (
    IssuanceError,
    as_utc,
    credential_role,
    data_subject_ttl_days,
    deliver_to_custodian,
    is_spent,
    newest_first,
)
from .org_onboarding import OrgOnboardingError, get_trust_anchor_key
from .status_list import SUSPENSION_LIST_ID, allocate_suspendable_index
from .vc import build_data_subject_credential, sign_credential

log = logging.getLogger(__name__)

DATA_SUBJECT = "DataSubjectCredential"

# Outcomes. Names, never free text: the job's output is read by an alert, and a
# reason is the same string on every run.
RENEWED = "renewed"
WOULD_RENEW = "would_renew"
REDELIVERED = "redelivered"
NOT_DUE = "not_due"


@dataclass
class SubjectResult:
    """What one run did for one DID. Counts and reason names only."""

    did: str
    renewed: int = 0
    redelivered: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    failed: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def fail(self, reason: str) -> None:
        self.failed[reason] = self.failed.get(reason, 0) + 1

    def as_dict(self) -> dict:
        return {
            "did": self.did,
            "renewed": self.renewed,
            "redelivered": self.redelivered,
            "skipped": dict(sorted(self.skipped.items())),
            "failed": dict(sorted(self.failed.items())),
        }


@dataclass
class RenewalReport:
    dry_run: bool = False
    examined: int = 0
    not_due: int = 0
    subjects: dict[str, SubjectResult] = field(default_factory=dict)

    def subject(self, did: str) -> SubjectResult:
        if did not in self.subjects:
            self.subjects[did] = SubjectResult(did)
        return self.subjects[did]

    @property
    def renewed(self) -> int:
        return sum(s.renewed for s in self.subjects.values())

    @property
    def failed(self) -> int:
        return sum(sum(s.failed.values()) for s in self.subjects.values())

    def as_dict(self) -> dict:
        skipped: dict[str, int] = defaultdict(int)
        for s in self.subjects.values():
            for reason, n in s.skipped.items():
                skipped[reason] += n
        return {
            "dry_run": self.dry_run,
            "examined": self.examined,
            "not_due": self.not_due,
            "renewed": self.renewed,
            "redelivered": sum(s.redelivered for s in self.subjects.values()),
            "skipped": dict(sorted(skipped.items())),
            "failed": self.failed,
            "subjects": [self.subjects[did].as_dict() for did in sorted(self.subjects)],
        }


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_jwk: dict | None


@dataclass(frozen=True)
class Candidate:
    """The newest live credential of one (DID, role, organisation)."""

    credential_id: str
    subject_did: str
    role: str | None
    linked: str | None
    expires_at: datetime | None
    #: Older live credentials of the same group: present after a renewal, until
    #: they expire.
    older: int


def _linked(cred: Credential) -> str | None:
    subject = (cred.credential_json or {}).get("credentialSubject") or {}
    linked = subject.get("linkedParticipant")
    return linked if isinstance(linked, str) and linked else None


async def candidates(
    db: AsyncSession, settings: Settings, *, subject_did: str | None = None
) -> list[Candidate]:
    """The newest live credential of every (DID, role, organisation).

    Only this registry's own issuance record (it holds a status-list index);
    a holder's copy of somebody else's credential is not this instance's to
    renew. Older live ones of the same group are counted, never candidates: a
    predecessor that already has a successor is done.
    """
    stmt = select(Credential).where(
        Credential.credential_type == DATA_SUBJECT,
        Credential.status == "active",
        Credential.issuer_did == settings.trust_anchor_did,
        Credential.status_list_index.is_not(None),
    )
    if subject_did:
        stmt = stmt.where(Credential.subject_did == subject_did)
    rows = (await db.execute(stmt)).scalars().all()

    groups: dict[tuple, list[Credential]] = defaultdict(list)
    for cred in rows:
        key = (cred.subject_did, credential_role(cred.credential_json), _linked(cred))
        groups[key].append(cred)

    out = []
    for (did, role, linked), held in sorted(
        groups.items(), key=lambda kv: tuple(str(k) for k in kv[0])
    ):
        held.sort(key=newest_first, reverse=True)
        out.append(
            Candidate(
                credential_id=held[0].id,
                subject_did=did,
                role=role,
                linked=linked,
                expires_at=as_utc(held[0].expires_at),
                older=len(held) - 1,
            )
        )
    return out


async def _refusal(
    db: AsyncSession, cred: Credential | None, linked: str | None, *, lock: bool
) -> str | None:
    """Why *cred* may not be renewed now, or ``None``. Reads with row locks.

    Every rule except expiry; see the module docstring.
    """
    if cred is None:
        return "predecessor_gone"
    if cred.status == "revoked":
        return "predecessor_revoked"
    if cred.status == "suspended":
        return "predecessor_suspended"
    if cred.status != "active":
        return "predecessor_not_active"
    if linked is None:
        # Nobody to deliver to and no membership to check: an operator names
        # the organisation by issuing again, the job does not guess one.
        return "no_linked_organisation"

    did_row = await db.get(Did, cred.subject_did, populate_existing=True)
    if did_row is None or not did_row.active:
        return "did_deactivated"
    if await is_spent(db, cred.subject_did):
        return "did_spent"

    owner_stmt = (
        select(Owner)
        .where(Owner.did == linked)
        .execution_options(populate_existing=True)
    )
    if lock:
        owner_stmt = owner_stmt.with_for_update(of=Owner)
    owners = (await db.execute(owner_stmt)).scalars().all()
    if len(owners) != 1:
        # None, or two owners on one DID — `owner_for_did`'s rule: picking one
        # would decide membership by row order.
        return "organisation_unknown"
    owner = owners[0]
    if owner.status != "verified":
        return "organisation_not_verified"

    member_stmt = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.user_did == cred.subject_did,
            OrganizationMembership.organization_alias == owner.id,
            OrganizationMembership.status == "active",
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        member_stmt = member_stmt.with_for_update(of=OrganizationMembership)
    if (await db.execute(member_stmt)).scalar_one_or_none() is None:
        return "membership_gone"
    return None


async def _has_newer_live(
    db: AsyncSession, cred: Credential, linked: str | None
) -> bool:
    """A successor already stands — the run that issued it got here first."""
    rows = (
        (
            await db.execute(
                select(Credential).where(
                    Credential.subject_did == cred.subject_did,
                    Credential.credential_type == DATA_SUBJECT,
                    Credential.status == "active",
                    Credential.id != cred.id,
                )
            )
        )
        .scalars()
        .all()
    )
    role = credential_role(cred.credential_json)
    mine = newest_first(cred)
    return any(
        credential_role(c.credential_json) == role
        and _linked(c) == linked
        and newest_first(c) > mine
        for c in rows
    )


def _due(
    candidate: Candidate,
    settings: Settings,
    now: datetime,
    *,
    recovery: bool,
) -> str | None:
    """``None`` when due for renewal, else the reason it is not."""
    if candidate.expires_at is None:
        return "no_expiry"
    left = candidate.expires_at - now
    if left > timedelta(days=settings.data_subject_credential_renewal_window_days):
        return NOT_DUE
    if left <= timedelta(0) and not recovery:
        grace = timedelta(days=settings.data_subject_credential_renewal_grace_days)
        if now - candidate.expires_at > grace:
            return "expired_beyond_grace"
    return None


async def renew_one(
    db: AsyncSession,
    settings: Settings,
    candidate: Candidate,
    result: SubjectResult,
    *,
    anchor_key: SigningKey,
    now: datetime,
    dry_run: bool = False,
) -> str | None:
    """Issue the successor of *candidate*'s credential, then deliver it.

    The checks run again here with the rows locked, in the transaction that
    inserts — the predecessor, the organisation and the membership are re-read,
    not trusted from `candidates`. Returns the successor's id, or ``None``.
    """
    # Nothing read before this point is trusted: every row below is read again,
    # in this transaction, and locked.
    db.expire_all()
    stmt = (
        select(Credential)
        .where(Credential.id == candidate.credential_id)
        .execution_options(populate_existing=True)
    )
    if not dry_run:
        # `of=`: the row is loaded with its `dids` row outer-joined
        # (`Credential.subject`), and Postgres refuses `FOR UPDATE` on the
        # nullable side of an outer join. SQLite ignores the clause entirely, so
        # only the integration suite can see this.
        stmt = stmt.with_for_update(of=Credential)
    cred = (await db.execute(stmt)).scalar_one_or_none()

    refusal = await _refusal(db, cred, candidate.linked, lock=not dry_run)
    if refusal is None and cred is not None:
        if await _has_newer_live(db, cred, candidate.linked):
            refusal = "already_renewed"
    if refusal is not None or cred is None:
        await db.rollback()
        result.skip(refusal or "predecessor_gone")
        log.info("renewal skipped for %s: %s", candidate.subject_did, refusal)
        return None

    if dry_run:
        await db.rollback()
        result.skip(WOULD_RENEW)
        return None

    predecessor_id, subject_did = cred.id, cred.subject_did
    prior = (cred.credential_json or {}).get("credentialSubject") or {}
    ttl = data_subject_ttl_days(settings)
    successor_id = generate_credential_id()
    index = await allocate_suspendable_index(db)
    vc = build_data_subject_credential(
        issuer_did=settings.trust_anchor_did,
        subject_did=subject_did,
        role=prior.get("role"),
        community_role=prior.get("communityRole"),
        linked_participant_did=candidate.linked,
        allowed_actions=prior.get("allowedActions"),
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=settings.status_list_url(),
        suspension_list_credential_url=settings.status_list_url(SUSPENSION_LIST_ID),
        status_list_index=index,
        credential_id=successor_id,
        ttl_days=ttl,
        # Who established the person's identity, and how (`D-53`), carried
        # over: a renewal re-attests nothing, it extends what was attested.
        verified_by=prior.get("verifiedBy"),
        verification_method=prior.get("verificationMethod"),
    )
    jwk = decrypt_private_jwk(
        require_private_jwk(
            anchor_key.private_jwk,
            kid=anchor_key.kid,
            purpose="renew a person's credential as the trust anchor",
        ),
        settings.encryption_key,
    )
    signed = sign_credential(vc, jwk, anchor_key.kid)
    db.add(
        Credential(
            id=successor_id,
            credential_type=DATA_SUBJECT,
            issuer_did=settings.trust_anchor_did,
            subject_did=subject_did,
            credential_json=signed,
            status_list_index=index,
            # Stated, not the server default: the order of the two rows is what
            # every "newest" decision reads.
            issued_at=now,
            expires_at=now + timedelta(days=ttl),
        )
    )
    await db.commit()
    result.renewed += 1
    log.info(
        "renewed a credential of %s: %s superseded by %s (predecessor left to expire)",
        subject_did,
        predecessor_id,
        successor_id,
    )

    await _deliver(db, settings, candidate.linked, subject_did, signed, result)
    return successor_id


async def _deliver(
    db: AsyncSession,
    settings: Settings,
    custodian: str | None,
    subject_did: str,
    signed: dict,
    result: SubjectResult,
    *,
    retry: bool = False,
) -> bool:
    """To the linked organisation's custodian, as issuance delivers. Never another."""
    if custodian is None:
        result.fail("delivery")
        return False
    try:
        await deliver_to_custodian(
            db,
            settings,
            custodian_did=custodian,
            credentials=[(DATA_SUBJECT, signed)],
            issuer_pid=signed["id"],
            holder_pid=subject_id_of(subject_did) or subject_did,
        )
        await db.commit()
    except IssuanceError as exc:
        await db.rollback()
        result.fail("delivery")
        log.error(
            "renewed credential of %s not delivered (retried on the next run): %s",
            subject_did,
            exc.message,
        )
        return False
    if retry:
        result.redelivered += 1
    return True


async def renew_due(
    db: AsyncSession,
    settings: Settings,
    *,
    subject_did: str | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> RenewalReport:
    """One run of the job. Failures are counted per subject, never raised.

    `subject_did` restricts the run to one person and is the operator's
    recovery: it renews an expired credential however long ago it expired.
    """
    now = now or datetime.now(UTC)
    report = RenewalReport(dry_run=dry_run)
    anchor_key: SigningKey | None
    try:
        key = await get_trust_anchor_key(db, settings)
        # Copied out of the row: every renewal expires the session's objects.
        anchor_key = SigningKey(kid=key.kid, private_jwk=key.private_jwk)
    except OrgOnboardingError:
        anchor_key = None

    due = await candidates(db, settings, subject_did=subject_did)
    # End the read: each renewal is its own transaction, re-reading what it
    # decides on.
    await db.rollback()
    for candidate in due:
        report.examined += 1
        why = _due(candidate, settings, now, recovery=subject_did is not None)
        if why == NOT_DUE:
            await _maybe_redeliver(db, settings, candidate, report, now, dry_run)
            continue
        result = report.subject(candidate.subject_did)
        if why is not None:
            result.skip(why)
            continue
        if anchor_key is None:
            result.fail("no_issuing_key")
            continue
        try:
            await renew_one(
                db,
                settings,
                candidate,
                result,
                anchor_key=anchor_key,
                now=now,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 — one person's failure is not the run's
            await db.rollback()
            result.fail("error")
            # The exception's class only: a message can carry a row's contents.
            log.error(
                "renewal failed for %s (%s); the predecessor is untouched and the "
                "next run retries",
                candidate.subject_did,
                type(exc).__name__,
            )
    return report


async def _maybe_redeliver(
    db: AsyncSession,
    settings: Settings,
    candidate: Candidate,
    report: RenewalReport,
    now: datetime,
    dry_run: bool,
) -> None:
    """Re-deliver a recent successor: a failed delivery is retried this way.

    A successor is recent while its predecessor could still be the copy the
    custodian holds — issued within the renewal window. Liveness is checked as
    for a renewal: nothing is pushed for a person who is no longer a member.
    """
    window = timedelta(days=settings.data_subject_credential_renewal_window_days)
    if candidate.older == 0 or dry_run:
        report.not_due += 1
        return
    cred = await db.get(Credential, candidate.credential_id, populate_existing=True)
    issued = as_utc(cred.issued_at) if cred is not None else None
    if cred is None or issued is None or now - issued > window:
        report.not_due += 1
        return
    result = report.subject(candidate.subject_did)
    refusal = await _refusal(db, cred, candidate.linked, lock=False)
    if refusal is not None:
        await db.rollback()
        result.skip(refusal)
        return
    await _deliver(
        db,
        settings,
        candidate.linked,
        cred.subject_did,
        cred.credential_json,
        result,
        retry=True,
    )


__all__ = [
    "Candidate",
    "RenewalReport",
    "SubjectResult",
    "candidates",
    "renew_due",
    "renew_one",
]
