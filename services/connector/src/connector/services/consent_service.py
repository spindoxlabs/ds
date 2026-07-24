"""Consent lifecycle management."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ConsentRequestORM
from ..notifications.base import ConsentNotifier
from . import consent_vocabulary as vocab

log = logging.getLogger(__name__)

# A consent row whose consumer is the wildcard admits *any party inside the
# circle* for its controller and purpose (§3.1) — a processor of the declared
# controller, never a new controller and never a new purpose. A per-party
# specific row always overrides it: an explicit grant or an explicit opt-out
# both beat the standing wildcard.
WILDCARD_CONSUMER = "*"


def _validated(dataset_id: str, purpose: list[str] | None) -> list[str]:
    """Resolve the dataset and normalise purposes, or raise ``VocabularyError``.

    Every consent write goes through here.  Before this existed, ``dataset_id``
    was an unvalidated string and ``purpose`` an unvalidated list, so a row
    could record a promise about a dataset that did not exist for a purpose
    nobody had defined.
    """
    vocab.resolve_dataset(dataset_id)
    return vocab.normalise_purposes(purpose)


async def create_consent_request(
    session: AsyncSession,
    subject_id: str,
    consumer_id: str,
    dataset_id: str,
    purpose: list[str] | None = None,
    message: str | None = None,
    notification_url: str | None = None,
    notifier: ConsentNotifier | None = None,
    controller: str | None = None,
    controller_role: str | None = None,
    offer_id: str | None = None,
    legal_basis: dict | None = None,
) -> ConsentRequestORM:
    purposes = _validated(dataset_id, purpose)

    latest = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    if latest and latest.status in ("pending", "granted"):
        return latest

    consent = ConsentRequestORM(
        subject_id=subject_id,
        consumer_id=consumer_id,
        dataset_id=dataset_id,
        purpose=purposes,
        controller=controller,
        controller_role=controller_role,
        offer_id=offer_id,
        legal_basis=legal_basis,
        message=message,
        notification_url=notification_url,
        status="pending",
        transfer_ids=[],
    )
    session.add(consent)
    await session.flush()
    if notifier:
        try:
            await notifier.notify_requested(consent)
            consent.notification_sent = True
        except Exception as exc:
            log.warning("notify_requested failed for consent %s: %s", consent.id, exc)
    return consent


async def get_latest_consent(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
) -> ConsentRequestORM | None:
    result = await session.execute(
        select(ConsentRequestORM)
        .where(
            ConsentRequestORM.subject_id == subject_id,
            ConsentRequestORM.dataset_id == dataset_id,
            ConsentRequestORM.consumer_id == consumer_id,
        )
        .order_by(
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    return result.scalars().first()


async def get_consent_request(
    session: AsyncSession, consent_id: str
) -> ConsentRequestORM | None:
    result = await session.execute(
        select(ConsentRequestORM).where(ConsentRequestORM.id == consent_id)
    )
    return result.scalar_one_or_none()


async def list_subject_consents(
    session: AsyncSession,
    subject_id: str,
    status: str | None = None,
    dataset_id: str | None = None,
    consumer_id: str | None = None,
) -> list[ConsentRequestORM]:
    stmt = select(ConsentRequestORM).where(ConsentRequestORM.subject_id == subject_id)
    if status:
        stmt = stmt.where(ConsentRequestORM.status == status)
    if dataset_id:
        stmt = stmt.where(ConsentRequestORM.dataset_id == dataset_id)
    if consumer_id:
        stmt = stmt.where(ConsentRequestORM.consumer_id == consumer_id)
    stmt = stmt.order_by(ConsentRequestORM.requested_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def approve_consent(
    session: AsyncSession,
    consent_id: str,
    subject_id: str,
    notifier: ConsentNotifier | None = None,
    legal_basis: dict | None = None,
) -> ConsentRequestORM | None:
    consent = await get_consent_request(session, consent_id)
    if not consent or consent.subject_id != subject_id:
        return None
    if consent.status != "pending":
        return None
    consent.status = "granted"
    consent.decided_at = datetime.now(timezone.utc)
    if legal_basis is not None:
        consent.legal_basis = legal_basis
    if notifier:
        try:
            await notifier.notify_status_changed(consent)
        except Exception as exc:
            log.warning("notify_status_changed failed for consent %s: %s", consent.id, exc)
    return consent


async def reject_consent(
    session: AsyncSession,
    consent_id: str,
    subject_id: str,
    notifier: ConsentNotifier | None = None,
) -> ConsentRequestORM | None:
    consent = await get_consent_request(session, consent_id)
    if not consent or consent.subject_id != subject_id:
        return None
    if consent.status != "pending":
        return None
    consent.status = "rejected"
    consent.decided_at = datetime.now(timezone.utc)
    if notifier:
        try:
            await notifier.notify_status_changed(consent)
        except Exception as exc:
            log.warning("notify_status_changed failed for consent %s: %s", consent.id, exc)
    return consent


async def set_subject_data_sharing(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
    enabled: bool,
    purpose: list[str] | None = None,
    message: str | None = None,
    controller: str | None = None,
    controller_role: str | None = None,
    offer_id: str | None = None,
    legal_basis: dict | None = None,
) -> ConsentRequestORM:
    """Set a data subject's standing sharing decision for a dataset.

    This is owner-driven consent: the subject can make their data available or
    unavailable without waiting for a consumer-created pending request.
    """
    purposes = _validated(dataset_id, purpose)

    latest = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    now = datetime.now(timezone.utc)

    if enabled:
        if latest and latest.status == "granted":
            return latest
        consent = ConsentRequestORM(
            subject_id=subject_id,
            consumer_id=consumer_id,
            dataset_id=dataset_id,
            purpose=purposes,
            controller=controller,
            controller_role=controller_role,
            offer_id=offer_id,
            legal_basis=legal_basis,
            message=message or "Data owner enabled sharing.",
            status="granted",
            requested_at=now,
            decided_at=now,
            transfer_ids=[],
        )
        session.add(consent)
        await session.flush()
        return consent

    if latest and latest.status == "granted":
        latest.status = "revoked"
        latest.revoked_at = now
        latest.revocation_reason = message or "Data owner disabled sharing."
        return latest

    if latest and latest.status in {"revoked", "rejected"}:
        return latest

    consent = ConsentRequestORM(
        subject_id=subject_id,
        consumer_id=consumer_id,
        dataset_id=dataset_id,
        purpose=purposes,
        controller=controller,
        controller_role=controller_role,
        offer_id=offer_id,
        legal_basis=legal_basis,
        message=message or "Data owner disabled sharing.",
        status="revoked",
        requested_at=now,
        revoked_at=now,
        revocation_reason=message or "Data owner disabled sharing.",
        transfer_ids=[],
    )
    session.add(consent)
    await session.flush()
    return consent


async def revoke_consent(
    session: AsyncSession,
    consent_id: str,
    subject_id: str,
    reason: str | None = None,
    notifier: ConsentNotifier | None = None,
) -> ConsentRequestORM | None:
    consent = await get_consent_request(session, consent_id)
    if not consent or consent.subject_id != subject_id:
        return None
    if consent.status != "granted":
        return None
    consent.status = "revoked"
    consent.revoked_at = datetime.now(timezone.utc)
    consent.revocation_reason = reason
    if notifier:
        try:
            await notifier.notify_status_changed(consent)
        except Exception as exc:
            log.warning("notify_status_changed failed for consent %s: %s", consent.id, exc)
    return consent


async def register_transfer(
    session: AsyncSession, consent_id: str, transfer_id: str
) -> bool:
    consent = await get_consent_request(session, consent_id)
    if not consent:
        return False
    existing = list(consent.transfer_ids or [])
    if transfer_id not in existing:
        existing.append(transfer_id)
        consent.transfer_ids = existing
    return True


def consent_satisfies(
    consent: ConsentRequestORM,
    purpose: list[str] | None,
    controller_role: str | None,
    consent_required: bool,
) -> tuple[bool, str]:
    """Does a granted row authorise *this* request? Returns (allowed, reason).

    The matrix, for a dataset whose rows are gated on consent:

    | purpose is the consented one or narrower AND controller-role matches | allow |
    | purpose empty, unrelated, or broader                                 | deny  |
    | controller-role differs                                              | deny  |

    For an open, non-personal dataset there is no data subject and the question
    does not arise, so the row's own status is the whole answer.
    """
    if consent.status != "granted":
        return False, f"consent status is {consent.status}"

    if not consent_required:
        return True, "dataset does not require per-subject consent"

    if not purpose:
        # Absent purpose means the caller never declared why it wants the data.
        return False, "no purpose declared for a consent-required dataset"

    consented = list(consent.purpose or [])
    if not consented:
        # The person was never told the use, so the consent does not meet
        # GDPR Art. 4(11). Empty is never "unrestricted".
        return False, "consent row records no purpose"

    if not vocab.purpose_covered(purpose, consented):
        return False, (
            f"requested purpose {purpose} is not covered by consented {consented}"
        )

    if controller_role and consent.controller_role and controller_role != consent.controller_role:
        return False, (
            f"controller role '{controller_role}' differs from consented "
            f"'{consent.controller_role}'"
        )

    return True, "consent covers the requested purpose and controller role"


def resolve_decision(
    specific: ConsentRequestORM | None,
    wildcard: ConsentRequestORM | None,
    purpose: list[str] | None,
    controller_role: str | None,
    consent_required: bool,
) -> tuple[bool, str, ConsentRequestORM | None]:
    """Combine a per-party row with the standing wildcard (§3.1).

    | specific granted           > wildcard | allow (purpose + role must match) |
    | specific revoked/rejected  > wildcard | deny  (explicit opt-out wins)     |
    | no specific + wildcard granted        | allow (purpose + role must match) |
    | no specific + no wildcard             | deny  (fail-closed)               |

    A *pending* specific row is a consumer's unanswered ask, not the subject's
    decision, so it neither grants nor blocks — it falls through to whatever the
    subject already decided via the wildcard.  Returns the row that decided, so
    callers can surface its legal-basis evidence.
    """
    if specific is not None:
        if specific.status == "granted":
            allowed, reason = consent_satisfies(
                specific, purpose, controller_role, consent_required
            )
            return allowed, reason, specific
        if specific.status in ("revoked", "rejected"):
            return False, f"consumer explicitly opted out (status {specific.status})", specific
    if wildcard is not None:
        allowed, reason = consent_satisfies(
            wildcard, purpose, controller_role, consent_required
        )
        return allowed, reason, wildcard
    return False, "no consent record", None


async def check_consent(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    controller_role: str | None = None,
    consent_required: bool | None = None,
) -> tuple[bool, str]:
    """Whether one subject's consent authorises this consumer, purpose and role."""
    allowed, reason, _row = await check_consent_detail(
        session,
        subject_id,
        dataset_id,
        consumer_id,
        purpose=purpose,
        controller_role=controller_role,
        consent_required=consent_required,
    )
    return allowed, reason


async def check_consent_detail(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    controller_role: str | None = None,
    consent_required: bool | None = None,
) -> tuple[bool, str, ConsentRequestORM | None]:
    """As :func:`check_consent`, also returning the row that decided."""
    if consent_required is None:
        consent_required = _dataset_requires_consent(dataset_id)

    specific = None
    if consumer_id != WILDCARD_CONSUMER:
        specific = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    wildcard = await get_latest_consent(
        session, subject_id, dataset_id, WILDCARD_CONSUMER
    )
    return resolve_decision(
        specific, wildcard, purpose, controller_role, consent_required
    )


def _dataset_requires_consent(dataset_id: str) -> bool:
    """Resolve the dataset's consent gate, defaulting to fail-closed.

    An unknown dataset id reaching the check is not a reason to relax: treat it
    as consent-required so a mis-keyed request denies rather than leaks.
    """
    try:
        return vocab.requires_consent(vocab.resolve_dataset(dataset_id))
    except vocab.VocabularyError:
        log.warning("Consent check for unknown dataset '%s' — failing closed", dataset_id)
        return True


def consent_snapshot_hash(rows: Iterable[ConsentRequestORM]) -> str:
    """A recomputable, non-PII fingerprint of a consent state (§4.1).

    SHA-256 over the sorted ``(subject_did, dataset_id, purpose,
    controller_role, consent_text_version)`` tuples.  It proves *which* consent
    state authorised a handover, verifiable by recomputation from the connector
    DB, while holding no name, POD or fiscal code — the subject appears only as
    its pseudonymous DID, exactly as it does on the consent row itself.
    """
    tuples = sorted(
        (
            row.subject_id or "",
            row.dataset_id or "",
            ",".join(sorted(row.purpose or [])),
            row.controller_role or "",
            (row.legal_basis or {}).get("consent_text_version") or "",
        )
        for row in rows
    )
    payload = json.dumps(tuples, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def latest_granted_rows_for_dataset(
    session: AsyncSession, dataset_id: str
) -> list[ConsentRequestORM]:
    """The effective granted consent rows for a dataset — latest per party.

    One row per ``(subject_id, consumer_id)`` — the most recent — kept only when
    it is currently ``granted``.  This is the state a :class:`DataIngested` or
    ``DataDisclosed` snapshot hashes over.
    """
    result = await session.execute(
        select(ConsentRequestORM)
        .where(ConsentRequestORM.dataset_id == dataset_id)
        .order_by(
            ConsentRequestORM.subject_id.asc(),
            ConsentRequestORM.consumer_id.asc(),
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    latest: dict[tuple[str, str], ConsentRequestORM] = {}
    for row in result.scalars().all():
        latest.setdefault((row.subject_id, row.consumer_id), row)
    return [row for row in latest.values() if row.status == "granted"]


async def dataset_consent_snapshot(
    session: AsyncSession, dataset_id: str
) -> tuple[str, int]:
    """``(consent_snapshot_hash, granted_party_count)`` for a dataset."""
    rows = await latest_granted_rows_for_dataset(session, dataset_id)
    return consent_snapshot_hash(rows), len(rows)


async def get_granted_subject_ids(
    session: AsyncSession,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    controller_role: str | None = None,
    consent_required: bool | None = None,
) -> list[str]:
    """Subjects whose latest consent authorises this consumer, purpose and role.

    This is the row-filter list: a subject who did not consent to the declared
    purpose simply does not appear, so their rows never leave the provider.

    A subject may be authorised by a per-party grant *or* by the scoped wildcard
    (§3.1); a per-party opt-out overrides the wildcard.  Both are considered here
    so the row-filter agrees with :func:`check_consent`.
    """
    if consent_required is None:
        consent_required = _dataset_requires_consent(dataset_id)

    consumer_ids = {consumer_id, WILDCARD_CONSUMER}
    result = await session.execute(
        select(ConsentRequestORM)
        .where(
            ConsentRequestORM.dataset_id == dataset_id,
            ConsentRequestORM.consumer_id.in_(consumer_ids),
        )
        .order_by(
            ConsentRequestORM.subject_id.asc(),
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    specific_by_subject: dict[str, ConsentRequestORM] = {}
    wildcard_by_subject: dict[str, ConsentRequestORM] = {}
    for consent in result.scalars().all():
        if consent.consumer_id == WILDCARD_CONSUMER:
            wildcard_by_subject.setdefault(consent.subject_id, consent)
        else:
            specific_by_subject.setdefault(consent.subject_id, consent)

    granted: list[str] = []
    for subject_id in specific_by_subject.keys() | wildcard_by_subject.keys():
        allowed, reason, _row = resolve_decision(
            specific_by_subject.get(subject_id),
            wildcard_by_subject.get(subject_id),
            purpose,
            controller_role,
            consent_required,
        )
        if allowed:
            granted.append(subject_id)
        else:
            log.debug(
                "Subject %s excluded from %s row filter: %s", subject_id, dataset_id, reason
            )
    return granted
