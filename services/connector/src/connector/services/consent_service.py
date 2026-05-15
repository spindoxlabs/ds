"""Consent lifecycle management."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ConsentRequestORM
from ..notifications.base import ConsentNotifier

log = logging.getLogger(__name__)


async def create_consent_request(
    session: AsyncSession,
    subject_id: str,
    consumer_id: str,
    dataset_id: str,
    purpose: list[str] | None = None,
    message: str | None = None,
    notification_url: str | None = None,
    notifier: ConsentNotifier | None = None,
) -> ConsentRequestORM:
    latest = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    if latest and latest.status in ("pending", "granted"):
        return latest

    consent = ConsentRequestORM(
        subject_id=subject_id,
        consumer_id=consumer_id,
        dataset_id=dataset_id,
        purpose=purpose or [],
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
) -> ConsentRequestORM | None:
    consent = await get_consent_request(session, consent_id)
    if not consent or consent.subject_id != subject_id:
        return None
    if consent.status != "pending":
        return None
    consent.status = "granted"
    consent.decided_at = datetime.now(timezone.utc)
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


async def check_consent(
    session: AsyncSession,
    subject_id: str,
    dataset_id: str,
    consumer_id: str,
) -> bool:
    latest = await get_latest_consent(session, subject_id, dataset_id, consumer_id)
    return latest is not None and latest.status == "granted"


async def get_granted_subject_ids(
    session: AsyncSession,
    dataset_id: str,
    consumer_id: str,
) -> list[str]:
    result = await session.execute(
        select(ConsentRequestORM)
        .where(
            ConsentRequestORM.dataset_id == dataset_id,
            ConsentRequestORM.consumer_id == consumer_id,
        )
        .order_by(
            ConsentRequestORM.subject_id.asc(),
            ConsentRequestORM.requested_at.desc(),
            ConsentRequestORM.revoked_at.desc(),
            ConsentRequestORM.decided_at.desc(),
        )
    )
    latest_by_subject: dict[str, ConsentRequestORM] = {}
    for consent in result.scalars().all():
        latest_by_subject.setdefault(consent.subject_id, consent)
    return [
        subject_id
        for subject_id, consent in latest_by_subject.items()
        if consent.status == "granted"
    ]
