"""Consent lifecycle management."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
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


async def _consent_rows_for(
    session: AsyncSession,
    dataset_id: str,
    consumer_ids: set[str],
    subject_id: str | None = None,
) -> list[ConsentRequestORM]:
    """A dataset's consent rows for these consumer keys, latest first.

    One loader for both readers below, ordered once, so "latest" cannot mean two
    different things on the two paths.
    """
    stmt = select(ConsentRequestORM).where(
        ConsentRequestORM.dataset_id == dataset_id,
        ConsentRequestORM.consumer_id.in_(consumer_ids),
    )
    if subject_id is not None:
        stmt = stmt.where(ConsentRequestORM.subject_id == subject_id)
    result = await session.execute(
        stmt.order_by(
            ConsentRequestORM.subject_id.asc(),
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    return list(result.scalars().all())


def decide_for_subject(
    rows: Iterable[ConsentRequestORM],
    purpose: list[str] | None,
    controller_role: str | None,
    consent_required: bool,
    offer_id: str | None = None,
) -> tuple[bool, str, ConsentRequestORM | None]:
    """One subject's verdict over their rows for a dataset, keyed **per offer**.

    ``rows`` are that subject's rows for one dataset, latest first, already
    narrowed to the consumer being asked about and the wildcard.

    **The single decision procedure**, and it is shared deliberately.
    :func:`check_consent_detail` and :func:`get_granted_subject_ids` answer the
    same question about one subject and about every subject, and
    ``GET /internal/consent/check`` calls *both* — the first when the caller
    names a ``subject_id``, the second when it does not. They were separate
    implementations of the same rules, and they drifted: keyed per offer on one
    path and per subject on the other, the route contradicted itself, denying a
    named subject while listing that same subject as granted a branch away.
    Sharing the procedure is what makes the docstring promise that they agree
    something the code enforces rather than something it asserts.

    **Decisions collapse per offer, not per subject.** The write side already
    keys on the offer — ``set_subject_data_sharing`` reads back through
    :func:`get_latest_offer_consent` whenever one is named, because "two offers
    may name the same dataset for different purposes and controllers; treating
    them as one row makes granting the second a silent no-op and makes
    withdrawing it revoke the first". Collapsing on the subject alone kept only
    the most recent row, which made the answer depend on the **order** two
    unrelated decisions were made in:

        grant flexibility, then decline grid-planning  → denied
        decline grid-planning, then grant flexibility  → allowed

    The decline of an unrelated offer erased a grant, so the row filter withheld
    rows the person had consented to share. Keyed per offer, each decision
    answers only for its own offer.

    ``offer_id`` narrows the question to one offer, for a caller that has one.
    Without it the subject is authorised when **any** of their offers authorises,
    which is what a data-plane row filter asks: is this row disclosable for the
    declared purpose, under whichever offer allows it. With it, a subject holding
    no decision about that offer is not in its audience even holding a grant on
    the dataset itself — answering "who consents to this offer" from a different
    offer's grant would name people who never saw this offer's text.

    **A withdrawal that names no offer is not scoped to one.** A decision about
    the bare dataset — ``POST /consent/my/shares`` with a ``dataset_id``, or a
    subject rejecting a consumer's ask — carries no ``offer_id``, so revoking it
    is a statement about the dataset rather than about an offer, and it denies
    whatever any offer-scoped row still says. Fail-closed, and the only direction
    that can be wrong here without disclosing against a withdrawal.
    """
    specific: dict[str | None, ConsentRequestORM] = {}
    wildcard: dict[str | None, ConsentRequestORM] = {}
    offers: list[str | None] = []
    for row in rows:
        if row.offer_id not in offers:
            offers.append(row.offer_id)
        target = wildcard if row.consumer_id == WILDCARD_CONSUMER else specific
        target.setdefault(row.offer_id, row)

    def decide(offer: str | None):
        return resolve_decision(
            specific.get(offer),
            wildcard.get(offer),
            purpose,
            controller_role,
            consent_required,
        )

    bare_allowed, bare_reason, bare_row = decide(None)
    if bare_row is not None and bare_row.status in ("revoked", "rejected"):
        return (
            False,
            f"{bare_reason} — the decision names no offer, so it is not scoped to one",
            bare_row,
        )

    if offer_id is not None:
        return decide(offer_id)

    allowed, reason, row = bare_allowed, bare_reason, bare_row
    for offer in sorted(o for o in offers if o):
        if allowed:
            break
        allowed, reason, row = decide(offer)
    return allowed, reason, row


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
    offer_id: str | None = None,
) -> tuple[bool, str, ConsentRequestORM | None]:
    """As :func:`check_consent`, also returning the row that decided.

    One subject's half of :func:`decide_for_subject`; the row-filter half is
    :func:`get_granted_subject_ids`. Both delegate, so the two branches of
    ``GET /internal/consent/check`` cannot disagree about the same rows.
    """
    if consent_required is None:
        consent_required = _dataset_requires_consent(dataset_id)

    rows = await _consent_rows_for(
        session,
        dataset_id,
        {consumer_id, WILDCARD_CONSUMER},
        subject_id=subject_id,
    )
    return decide_for_subject(
        rows, purpose, controller_role, consent_required, offer_id
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

    SHA-256 over the sorted ``(subject_did, dataset_id, purpose, controller,
    controller_role, consent_text_version)`` tuples.  It proves *which* consent
    state authorised a handover, verifiable by recomputation from the connector
    DB, while holding no name, POD or fiscal code — the subject appears only as
    its pseudonymous DID, exactly as it does on the consent row itself.  A
    controller alias is an organisation, not a person, so naming it costs the
    fingerprint none of that.

    **``controller`` is in the tuple since 2026-08-28, and it was missing.**
    `D-11` names the consent key ``(subject, purpose, controller-role)`` and
    says matching on the controller *alone* is insufficient — which makes the
    role necessary, not the controller irrelevant. `D-14` then makes the
    controller decisive in as many words: the wildcard "never admits a new
    controller and never a new purpose". A dimension the wildcard refuses to
    cross has to be visible in the evidence that proves which consent state
    authorised the handover. Without it, two offers over one dataset agreeing on
    purpose and controller role but naming **different controllers** produced
    byte-identical tuples, so `L-2`'s digest could not tell a disclosure to one
    from a disclosure to the other. The write path already stored what was
    needed — ``set_subject_data_sharing`` persists ``controller`` from
    ``offer.recipients.controller`` — and only the hash omitted it.

    Not reachable on the offers shipped here, whose three purposes separate them
    on their own; reachable as soon as two controllers share a role and a
    purpose over one dataset, which nothing forbids — `D-11a` constrains which
    roles a controller may name and does nothing to separate two controllers
    holding the same one.

    **Every hash recorded before that date was computed over the old tuple**, so
    an auditor recomputing an older `DataDisclosed` from today's code will not
    reproduce it. That is deliberate and not migrated: a stored digest is
    evidence of what it was computed over, and rewriting the recorded evidence to
    match new code would destroy exactly the property the record exists for.
    """
    tuples = sorted(
        (
            row.subject_id or "",
            row.dataset_id or "",
            ",".join(sorted(row.purpose or [])),
            row.controller or "",
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
    """The effective granted consent rows for a dataset — latest per decision.

    One row per ``(subject_id, consumer_id, offer_id)`` — the most recent — kept
    only when it is currently ``granted``.  This is the state a
    :class:`DataIngested` or ``DataDisclosed`` snapshot hashes over.

    **Keyed on the offer, because a decision is.** This collapsed on
    ``(subject_id, consumer_id)`` alone and kept only the most recent row, so a
    subject whose latest decision was a *decline* of one offer vanished from the
    snapshot entirely — including the grant they still held on another offer over
    the same dataset. The hash was then **narrower than the disclosure it
    authorised**: the data left under an offer the person had granted, and the
    fingerprint that is supposed to prove which consent state backed the handover
    did not contain them. Narrower is the one direction `L-2` cannot tolerate,
    and the result was order-dependent — the same two decisions in the opposite
    order produced different evidence.

    The same collapse was fixed on the enforcement path first
    (:func:`decide_for_subject`); this is the evidence path catching up, and the
    two now agree about what a decision is keyed by.

    **This fix changed which rows are hashed, not the tuple.** The tuple did
    change afterwards — :func:`consent_snapshot_hash` gained ``controller``,
    because `D-14` makes it decisive and it was absent — but that was a separate
    question about the tuple's contents, decided separately.

    **The tuple is still not keyed on the offer, and deliberately.** An offer
    *carries* a consent key rather than adding a dimension to one: two offers
    that differ in purpose, controller or role already produce different tuples,
    and two agreeing on all of them plus the text version are the same consent
    key by `D-11`, so hashing them identically is correct rather than lossy. A
    negotiated ask (`D-16`) frequently carries no ``offer_id`` at all, so keying
    the *tuple* on the offer would be degenerate for exactly the model that needs
    coordinated granting. Whether the hash should become offer-scoped is a
    rulebook question and was decided by neither change.

    `L-2` stays true as written — "a recomputable SHA-256 over the authorising
    consent tuples" — and becomes true in fact, which it was not while granted
    rows were being dropped.
    """
    result = await session.execute(
        select(ConsentRequestORM)
        .where(ConsentRequestORM.dataset_id == dataset_id)
        .order_by(
            ConsentRequestORM.subject_id.asc(),
            ConsentRequestORM.consumer_id.asc(),
            ConsentRequestORM.offer_id.asc(),
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    latest: dict[tuple[str, str, str | None], ConsentRequestORM] = {}
    for row in result.scalars().all():
        latest.setdefault((row.subject_id, row.consumer_id, row.offer_id), row)
    return [row for row in latest.values() if row.status == "granted"]


async def dataset_consent_snapshot(
    session: AsyncSession, dataset_id: str
) -> tuple[str, int]:
    """``(consent_snapshot_hash, granted_party_count)`` for a dataset.

    The count is **grants, not parties**, since the rows became keyed per offer:
    one subject holding standing consent to two offers over this dataset counts
    twice. It is diagnostic and never reaches the event graph — it is returned to
    the discloser alongside the hash so an opaque digest can be sanity-checked
    against the size of the export it authorises. `L-2`'s evidence is the hash.
    """
    rows = await latest_granted_rows_for_dataset(session, dataset_id)
    return consent_snapshot_hash(rows), len(rows)


@dataclass(frozen=True)
class GrantedSubject:
    """One subject in a dataset's audience, and when they decided.

    ``decided_at`` is the timestamp of **the row that authorises this
    disclosure** — the one :func:`decide_for_subject` selected — not the
    subject's earliest or latest decision overall. Those differ whenever a
    standing wildcard is overridden per party, or one offer is re-decided while
    another stands, and the authorising row is the only one that evidences
    *this* release.

    It is ``None`` only for a row that was granted without ever being decided,
    which the schema permits and the write paths do not produce.
    """

    subject_id: str
    decided_at: datetime | None


async def get_granted_subjects(
    session: AsyncSession,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    controller_role: str | None = None,
    consent_required: bool | None = None,
    offer_id: str | None = None,
) -> list[GrantedSubject]:
    """Subjects whose latest consent authorises this consumer, purpose and role.

    This is the row-filter list: a subject who did not consent to the declared
    purpose simply does not appear, so their rows never leave the provider.

    Every-subject half of :func:`decide_for_subject`, which is where the rules
    live — per-offer keying, the wildcard/per-party precedence of §3.1, and the
    offer-agnostic withdrawal. :func:`check_consent_detail` is the one-subject
    half and delegates to the same procedure, so this list and that verdict
    cannot disagree about the same rows.

    :func:`get_granted_subject_ids` is the same answer with the timestamps
    dropped, and delegates here rather than repeating the loop — the same reason
    the one-subject and every-subject paths share ``decide_for_subject``.
    """
    if consent_required is None:
        consent_required = _dataset_requires_consent(dataset_id)

    rows = await _consent_rows_for(
        session, dataset_id, {consumer_id, WILDCARD_CONSUMER}
    )
    by_subject: dict[str, list[ConsentRequestORM]] = {}
    for row in rows:
        by_subject.setdefault(row.subject_id, []).append(row)

    granted: list[GrantedSubject] = []
    for subject_id in sorted(by_subject):
        allowed, reason, row = decide_for_subject(
            by_subject[subject_id],
            purpose,
            controller_role,
            consent_required,
            offer_id,
        )
        if allowed:
            granted.append(
                GrantedSubject(
                    subject_id=subject_id,
                    decided_at=row.decided_at if row is not None else None,
                )
            )
        else:
            log.debug(
                "Subject %s excluded from %s row filter: %s", subject_id, dataset_id, reason
            )
    return granted


async def get_granted_subject_ids(
    session: AsyncSession,
    dataset_id: str,
    consumer_id: str,
    purpose: list[str] | None = None,
    controller_role: str | None = None,
    consent_required: bool | None = None,
    offer_id: str | None = None,
) -> list[str]:
    """The subject DIDs of :func:`get_granted_subjects`, in the same order.

    The row filter every PEP-side caller wants: the identities, without the
    decision timestamps that only a disclosure audit needs.
    """
    return [
        subject.subject_id
        for subject in await get_granted_subjects(
            session,
            dataset_id,
            consumer_id,
            purpose,
            controller_role,
            consent_required,
            offer_id,
        )
    ]
