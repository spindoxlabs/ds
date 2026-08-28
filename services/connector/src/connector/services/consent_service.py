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
    negotiation_id: str | None = None,
    correlation_id: str | None = None,
) -> ConsentRequestORM:
    purposes = _validated(dataset_id, purpose)

    latest = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    if latest and latest.status in ("pending", "granted"):
        # Reattach rather than duplicate. A negotiation retrying against an ask
        # the subject has not answered yet is the same question, so it adopts the
        # existing row — but it does bind it to the negotiation now waiting on
        # it, which an earlier ask may not have had.
        if latest.status == "pending" and negotiation_id and not latest.negotiation_id:
            latest.negotiation_id = negotiation_id
            latest.correlation_id = correlation_id
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
        negotiation_id=negotiation_id,
        correlation_id=correlation_id,
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


async def subject_pool_for_dataset(
    session: AsyncSession, dataset_id: str
) -> list[str]:
    """Who can be asked about this dataset.

    The pool is the set of subjects this connector already holds a consent row
    for — which, in practice, is everyone onboarded: ``POST /consent/admin/shares``
    writes a standing wildcard row per subject as they are approved, so a person
    enters the pool at onboarding rather than at the first request.

    Deliberately *not* a directory query against the identity-registry. A
    membership listing is a different question with a different blast radius,
    and the provider connector should not need to enumerate an organisation's
    people in order to relay a question to the ones whose data is at stake.

    An empty pool means there is nobody to ask, which is a real answer: a
    negotiation for a dataset nobody has enrolled in must be refused, not parked
    forever waiting on a decision no one can make.
    """
    result = await session.execute(
        select(ConsentRequestORM.subject_id)
        .where(ConsentRequestORM.dataset_id == dataset_id)
        .distinct()
    )
    return sorted(
        subject_id
        for subject_id in result.scalars().all()
        if subject_id and subject_id != WILDCARD_CONSUMER
    )


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


async def get_latest_offer_consent(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
    offer_id: str,
) -> ConsentRequestORM | None:
    """The subject's most recent decision **about one offer**.

    Distinct from :func:`get_latest_consent`, which keys on the dataset alone.
    Several offers can name the same dataset for different purposes and different
    controllers, and those are different questions: agreeing to share meter data
    for flexibility research is not agreeing to share it for grid planning. Keyed
    on the dataset, the second decision would collide with the first — granting
    would be a silent no-op and withdrawing would revoke the wrong purpose.
    """
    result = await session.execute(
        select(ConsentRequestORM)
        .where(
            ConsentRequestORM.subject_id == subject_id,
            ConsentRequestORM.dataset_id == dataset_id,
            ConsentRequestORM.consumer_id == consumer_id,
            ConsentRequestORM.offer_id == offer_id,
        )
        .order_by(
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    return result.scalars().first()


async def find_pending_request(
    session: AsyncSession,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    subject_id: str | None = None,
) -> ConsentRequestORM | None:
    """An ask already outstanding for this tuple, if there is one.

    Keyed on ``(subject pool, dataset, purpose, consumer)`` — the same tuple
    ``check_consent`` decides on — so a consumer that re-negotiates reattaches
    to the question already put to the subjects instead of asking it again.
    Without this, every retry of a parked negotiation would create a fresh row
    and the subject would see the same request repeatedly.

    Purpose matching is ``odrl:isA``: an outstanding ask for a broader purpose
    already covers a narrower re-request.  Returns the most recent match.
    """
    stmt = select(ConsentRequestORM).where(
        ConsentRequestORM.dataset_id == dataset_id,
        ConsentRequestORM.consumer_id == consumer_id,
        ConsentRequestORM.status == "pending",
    )
    if subject_id:
        stmt = stmt.where(ConsentRequestORM.subject_id == subject_id)
    stmt = stmt.order_by(ConsentRequestORM.requested_at.desc())
    result = await session.execute(stmt)

    for row in result.scalars().all():
        if not purpose:
            return row
        if vocab.purpose_covered(purpose, list(row.purpose or [])):
            return row
    return None


async def list_by_correlation(
    session: AsyncSession, correlation_id: str
) -> list[ConsentRequestORM]:
    """Every ask raised for one counterparty-side negotiation id.

    ``correlation_id`` is the *consumer's* id for the negotiation, which is the
    only handle it holds — so this is the lookup behind ``GET /consent/pending``.
    Callers must project it down to a status; the rows themselves name subjects.
    """
    result = await session.execute(
        select(ConsentRequestORM).where(
            ConsentRequestORM.correlation_id == correlation_id
        )
    )
    return list(result.scalars().all())


async def list_asks(
    session: AsyncSession,
    negotiation_id: str | None = None,
    status: str | None = None,
) -> list[ConsentRequestORM]:
    """Asks raised because a negotiation is parked — the operator's view."""
    stmt = select(ConsentRequestORM).where(
        ConsentRequestORM.negotiation_id.is_not(None)
    )
    if negotiation_id:
        stmt = stmt.where(ConsentRequestORM.negotiation_id == negotiation_id)
    if status:
        stmt = stmt.where(ConsentRequestORM.status == status)
    result = await session.execute(
        stmt.order_by(ConsentRequestORM.requested_at.desc())
    )
    return list(result.scalars().all())


async def negotiation_ask_tally(
    session: AsyncSession, negotiation_id: str
) -> tuple[int, int]:
    """``(pending, granted)`` counts of the asks blocking one negotiation.

    A negotiation asks the whole subject pool at once, and the ODRL consent
    check passes as soon as *anybody* has granted — so one grant is enough to
    resume, while one refusal decides nothing. Only when every ask has come back
    and none of them granted is the negotiation actually dead.
    """
    result = await session.execute(
        select(ConsentRequestORM.status).where(
            ConsentRequestORM.negotiation_id == negotiation_id
        )
    )
    statuses = list(result.scalars().all())
    return (
        sum(1 for status in statuses if status == "pending"),
        sum(1 for status in statuses if status == "granted"),
    )


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

    # A decision made about an offer is scoped to that offer. Two offers may name
    # the same dataset for different purposes and controllers; treating them as
    # one row makes granting the second a silent no-op and makes withdrawing it
    # revoke the first. Decisions made about a bare dataset keep the old key.
    latest = (
        await get_latest_offer_consent(
            session, subject_id, dataset_id, consumer_id, offer_id
        )
        if offer_id
        else await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    )
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
    offer_id: str | None = None,
) -> list[str]:
    """Subjects whose latest consent authorises this consumer, purpose and role.

    This is the row-filter list: a subject who did not consent to the declared
    purpose simply does not appear, so their rows never leave the provider.

    A subject may be authorised by a per-party grant *or* by the scoped wildcard
    (§3.1); a per-party opt-out overrides the wildcard.  Both are considered here
    so the row-filter agrees with :func:`check_consent`.

    **Decisions collapse per offer, not per subject.** The write side already
    keys on the offer — ``set_subject_data_sharing`` reads back through
    :func:`get_latest_offer_consent` whenever one is named, because "two offers
    may name the same dataset for different purposes and controllers; treating
    them as one row makes granting the second a silent no-op and makes
    withdrawing it revoke the first". The read side collapsed on
    ``(subject_id, consumer_id)`` alone and kept only the most recent row, so it
    disagreed with the write side about what a row is keyed by, and the
    disagreement was **order-dependent**: one subject, two decisions about two
    different offers over one dataset, and the answer changed when they were made
    in the opposite order.

        grant flexibility, then decline grid-planning  → filter(Flexibility) = []
        decline grid-planning, then grant flexibility  → filter(Flexibility) = [alice]

    The decline of an unrelated offer erased a grant, so the filter withheld rows
    the person had consented to share. Keyed per offer, each decision answers only
    for its own offer and a subject is authorised when **any** of them does.

    ``offer_id`` narrows the question to one offer, for a caller that has one —
    ``GET /consent/admin/shares`` asks "who consents to *this* offer", and
    answering it from a different offer's grant would name people who never saw
    this offer's text. A subject with no decision about the named offer is
    therefore absent from its audience, even holding a grant on the dataset
    itself. The data plane passes nothing and gets the union, which is the
    question it asks: is this subject's row disclosable for the declared purpose,
    under whichever offer authorises it.

    **A withdrawal that names no offer is not scoped to one.** A decision made
    about the bare dataset — ``POST /consent/my/shares`` with a ``dataset_id``,
    or a subject rejecting a consumer's ask — carries no ``offer_id``, so
    revoking it is a statement about the dataset rather than about an offer, and
    it denies whatever any offer-scoped row still says. Fail-closed, and the only
    direction that can be wrong here without disclosing against a withdrawal.
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
    specific: dict[tuple[str, str | None], ConsentRequestORM] = {}
    wildcard: dict[tuple[str, str | None], ConsentRequestORM] = {}
    offers_by_subject: dict[str, set[str | None]] = {}
    for consent in result.scalars().all():
        key = (consent.subject_id, consent.offer_id)
        offers_by_subject.setdefault(consent.subject_id, set()).add(consent.offer_id)
        if consent.consumer_id == WILDCARD_CONSUMER:
            wildcard.setdefault(key, consent)
        else:
            specific.setdefault(key, consent)

    def decide(key: tuple[str, str | None]):
        """One offer's verdict, wildcard and per-party row resolved together."""
        return resolve_decision(
            specific.get(key), wildcard.get(key), purpose, controller_role, consent_required
        )

    granted: list[str] = []
    for subject_id in sorted(offers_by_subject):
        bare_allowed, bare_reason, bare_row = decide((subject_id, None))
        if bare_row is not None and bare_row.status in ("revoked", "rejected"):
            log.debug(
                "Subject %s excluded from %s row filter: %s (names no offer, so "
                "it is not scoped to one)",
                subject_id,
                dataset_id,
                bare_reason,
            )
            continue

        if offer_id is not None:
            allowed, reason, _row = decide((subject_id, offer_id))
        else:
            allowed, reason = bare_allowed, bare_reason
            for offer in sorted(o for o in offers_by_subject[subject_id] if o):
                if allowed:
                    break
                allowed, reason, _row = decide((subject_id, offer))

        if allowed:
            granted.append(subject_id)
        else:
            log.debug(
                "Subject %s excluded from %s row filter: %s", subject_id, dataset_id, reason
            )
    return granted
