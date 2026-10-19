"""Persist and query EDC contract agreements."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ContractAgreementORM, _uuid


async def upsert_agreement(
    session: AsyncSession,
    agreement_id: str,
    asset_id: str,
    consumer_id: str,
    provider_id: str,
    policy_snapshot: dict,
    agreed_at: datetime,
    dsp_agreement_id: str | None = None,
    consumer_organization_id: str | None = None,
    consumer_organization_type: str | None = None,
) -> ContractAgreementORM:
    """Record an agreement once, whichever writer gets there first — or both at once.

    Two paths write this row — the negotiation webhook and the consumer's negotiation
    status route — and either can be first. **Or concurrent**: a select-then-insert
    let both see no row, the second insert violated `agreement_id`'s unique key, and
    the webhook answered 500 having stored nothing — so the shared DSP id, which only
    the webhook carries, was lost, the EDR named the local id and the provider
    answered `agreement_unknown` (seen 2026-10-19 under a driver polling the status
    route every second). So the row is inserted with `ON CONFLICT DO NOTHING`, then
    read back and completed: the DSP id and the presented organisation, which only the
    webhook carries, are filled in late when empty, never overwritten. Without the DSP
    id the consumer cannot name its own agreement to the provider (migration 0008).
    """
    dialect = session.get_bind().dialect.name
    insert = postgresql_insert if dialect == "postgresql" else sqlite_insert
    await session.execute(
        insert(ContractAgreementORM)
        .values(
            id=_uuid(),
            agreement_id=agreement_id,
            dsp_agreement_id=dsp_agreement_id,
            asset_id=asset_id,
            consumer_id=consumer_id,
            provider_id=provider_id,
            policy_snapshot=policy_snapshot,
            agreed_at=agreed_at,
            consumer_organization_id=consumer_organization_id,
            consumer_organization_type=consumer_organization_type,
        )
        .on_conflict_do_nothing(index_elements=["agreement_id"])
    )
    agreement = (
        await session.execute(
            select(ContractAgreementORM)
            .where(ContractAgreementORM.agreement_id == agreement_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if dsp_agreement_id and not agreement.dsp_agreement_id:
        agreement.dsp_agreement_id = dsp_agreement_id
    if consumer_organization_id and not agreement.consumer_organization_id:
        agreement.consumer_organization_id = consumer_organization_id
        agreement.consumer_organization_type = consumer_organization_type
    await session.flush()
    return agreement


async def _find(
    session: AsyncSession, agreement_id: str
) -> ContractAgreementORM | None:
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


async def get_agreement_status(session: AsyncSession, agreement_id: str) -> dict | None:
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
        # What the consumer's presented `OrganizationCredential` said when it
        # agreed (migration 0017); `None` when not established.
        "consumer_organization_id": agreement.consumer_organization_id,
        "consumer_organization_type": agreement.consumer_organization_type,
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
        agreement.terminated_at = datetime.now(UTC)
        agreement.termination_reason = reason
    return agreement
