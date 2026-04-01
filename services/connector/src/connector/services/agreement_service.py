"""Persist and query EDC contract agreements."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ContractAgreementORM


async def upsert_agreement(
    session: AsyncSession,
    agreement_id: str,
    asset_id: str,
    consumer_id: str,
    provider_id: str,
    policy_snapshot: dict,
    agreed_at: datetime,
) -> ContractAgreementORM:
    result = await session.execute(
        select(ContractAgreementORM).where(
            ContractAgreementORM.agreement_id == agreement_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    agreement = ContractAgreementORM(
        agreement_id=agreement_id,
        asset_id=asset_id,
        consumer_id=consumer_id,
        provider_id=provider_id,
        policy_snapshot=policy_snapshot,
        agreed_at=agreed_at,
    )
    session.add(agreement)
    await session.flush()
    return agreement


async def get_agreement_status(
    session: AsyncSession, agreement_id: str
) -> dict | None:
    result = await session.execute(
        select(ContractAgreementORM).where(
            ContractAgreementORM.agreement_id == agreement_id
        )
    )
    agreement = result.scalar_one_or_none()
    if not agreement:
        return None
    return {
        "active": agreement.terminated_at is None,
        "asset_id": agreement.asset_id,
        "consumer_id": agreement.consumer_id,
        "provider_id": agreement.provider_id,
        "agreed_at": agreement.agreed_at.isoformat(),
        "terminated_at": (
            agreement.terminated_at.isoformat() if agreement.terminated_at else None
        ),
    }


async def terminate_agreement(
    session: AsyncSession,
    agreement_id: str,
    reason: str | None = None,
) -> ContractAgreementORM | None:
    result = await session.execute(
        select(ContractAgreementORM).where(
            ContractAgreementORM.agreement_id == agreement_id
        )
    )
    agreement = result.scalar_one_or_none()
    if agreement:
        agreement.terminated_at = datetime.now(timezone.utc)
        agreement.termination_reason = reason
    return agreement
