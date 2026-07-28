"""Persist and query EDC contract agreements."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
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
    dsp_agreement_id: str | None = None,
) -> ContractAgreementORM:
    result = await session.execute(
        select(ContractAgreementORM).where(
            ContractAgreementORM.agreement_id == agreement_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Two paths write this row — the negotiation webhook and the transfer
        # route — and either can be first. Only the webhook carries the shared
        # DSP id, so fill it in late rather than losing it to whichever arrived
        # first. Without this the consumer cannot name its own agreement to the
        # provider (migration 0008).
        if dsp_agreement_id and not existing.dsp_agreement_id:
            existing.dsp_agreement_id = dsp_agreement_id
            await session.flush()
        return existing
    agreement = ContractAgreementORM(
        agreement_id=agreement_id,
        dsp_agreement_id=dsp_agreement_id,
        asset_id=asset_id,
        consumer_id=consumer_id,
        provider_id=provider_id,
        policy_snapshot=policy_snapshot,
        agreed_at=agreed_at,
    )
    session.add(agreement)
    await session.flush()
    return agreement


async def _find(session: AsyncSession, agreement_id: str) -> ContractAgreementORM | None:
    """Resolve by either identifier.

    A counterparty names the **shared** DSP id; this connector's own records and
    its EDC name the local one. Both must find the same row, or a data-plane
    request would be refused for an agreement that plainly exists.
    """
    result = await session.execute(
        select(ContractAgreementORM).where(
            or_(
                ContractAgreementORM.agreement_id == agreement_id,
                ContractAgreementORM.dsp_agreement_id == agreement_id,
            )
        )
    )
    return result.scalars().first()


async def get_agreement_status(
    session: AsyncSession, agreement_id: str
) -> dict | None:
    agreement = await _find(session, agreement_id)
    if not agreement:
        return None
    return {
        "active": agreement.terminated_at is None,
        "agreement_id": agreement.agreement_id,
        # The id a counterparty can name (migration 0008). Callers that hand an
        # identifier onward must send this one, never the local `agreement_id`.
        "dsp_agreement_id": agreement.dsp_agreement_id,
        "asset_id": agreement.asset_id,
        "consumer_id": agreement.consumer_id,
        "provider_id": agreement.provider_id,
        "agreed_at": agreement.agreed_at.isoformat(),
        "terminated_at": (
            agreement.terminated_at.isoformat() if agreement.terminated_at else None
        ),
        # The policy as agreed — the authority on what this exchange permits.
        # `POST /internal/dataplane/authorize` reads its `odrl:purpose` to decide
        # what a query may be made for, so it has to come from the agreement
        # rather than from today's governance file: a dataset's purposes can be
        # edited after an agreement was signed, and the agreement is what the
        # counterparty accepted.
        "policy_snapshot": agreement.policy_snapshot or {},
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
