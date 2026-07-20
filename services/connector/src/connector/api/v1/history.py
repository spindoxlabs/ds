"""Read-only history endpoints for EDC negotiations, agreements, and transfers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ds_edc import EdcManagementClient

from ...db.models import ContractAgreementORM
from ...dependencies import get_db, get_edc, require_history_read

router = APIRouter(prefix="/history", tags=["history"])

MAX_LIMIT = 200


def _clamp(offset: int, limit: int) -> tuple[int, int]:
    return max(offset, 0), min(max(limit, 1), MAX_LIMIT)


# -- Negotiations -------------------------------------------------------------

@router.get("/negotiations")
async def list_negotiations(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    state: str | None = None,
    edc: EdcManagementClient = Depends(get_edc),
    _p: Any = Depends(require_history_read),
) -> dict[str, Any]:
    offset, limit = _clamp(offset, limit)
    items = await edc.query_negotiations(offset=offset, limit=limit, state=state)
    return {"items": items, "total": len(items), "offset": offset, "limit": limit}


@router.get("/negotiations/{negotiation_id:path}")
async def get_negotiation(
    negotiation_id: str,
    edc: EdcManagementClient = Depends(get_edc),
    _p: Any = Depends(require_history_read),
) -> dict[str, Any]:
    return await edc.get_negotiation(negotiation_id)


# -- Agreements ---------------------------------------------------------------

@router.get("/agreements")
async def list_agreements(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    asset_id: str | None = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _p: Any = Depends(require_history_read),
) -> dict[str, Any]:
    offset, limit = _clamp(offset, limit)

    q = select(ContractAgreementORM)
    count_q = select(func.count()).select_from(ContractAgreementORM)

    if asset_id:
        q = q.where(ContractAgreementORM.asset_id == asset_id)
        count_q = count_q.where(ContractAgreementORM.asset_id == asset_id)
    if active_only:
        q = q.where(ContractAgreementORM.terminated_at.is_(None))
        count_q = count_q.where(ContractAgreementORM.terminated_at.is_(None))

    q = q.order_by(ContractAgreementORM.agreed_at.desc()).offset(offset).limit(limit)

    result = await db.execute(q)
    total = await db.scalar(count_q)
    items = [
        {
            "agreement_id": a.agreement_id,
            "asset_id": a.asset_id,
            "consumer_id": a.consumer_id,
            "provider_id": a.provider_id,
            "agreed_at": a.agreed_at.isoformat() if a.agreed_at else None,
            "terminated_at": a.terminated_at.isoformat() if a.terminated_at else None,
            "termination_reason": a.termination_reason,
        }
        for a in result.scalars()
    ]
    return {"items": items, "total": total or 0, "offset": offset, "limit": limit}


@router.get("/agreements/{agreement_id:path}")
async def get_agreement(
    agreement_id: str,
    edc: EdcManagementClient = Depends(get_edc),
    db: AsyncSession = Depends(get_db),
    _p: Any = Depends(require_history_read),
) -> dict[str, Any]:
    edc_data = await edc.get_agreement(agreement_id)

    result = await db.execute(
        select(ContractAgreementORM).where(
            ContractAgreementORM.agreement_id == agreement_id
        )
    )
    local = result.scalar_one_or_none()

    merged: dict[str, Any] = {**edc_data}
    if local:
        merged["ds:terminated_at"] = (
            local.terminated_at.isoformat() if local.terminated_at else None
        )
        merged["ds:termination_reason"] = local.termination_reason
        merged["ds:policy_snapshot"] = local.policy_snapshot
    return merged


# -- Transfers ----------------------------------------------------------------

@router.get("/transfers")
async def list_transfers(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    state: str | None = None,
    edc: EdcManagementClient = Depends(get_edc),
    _p: Any = Depends(require_history_read),
) -> dict[str, Any]:
    offset, limit = _clamp(offset, limit)
    items = await edc.query_transfers(offset=offset, limit=limit, state=state)
    return {"items": items, "total": len(items), "offset": offset, "limit": limit}
