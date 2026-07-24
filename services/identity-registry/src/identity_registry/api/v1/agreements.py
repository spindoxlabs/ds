from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Agreement, AgreementAcceptance
from ...dependencies import get_db, require_admin_or_read_scope
from ...schemas.responses import AgreementAcceptanceResponse, AgreementResponse

router = APIRouter(tags=["agreements"])


def _to_response(a: Agreement) -> AgreementResponse:
    return AgreementResponse(
        id=a.id,
        version=a.version,
        effective_from=a.effective_from,
        applies_to=a.applies_to or [],
        capacity=a.capacity,
        texts=a.texts or {},
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.get("/agreements", response_model=list[AgreementResponse])
async def list_agreements(
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    result = await db.execute(select(Agreement))
    return [_to_response(a) for a in result.scalars().all()]


@router.get("/agreements/{agreement_id}", response_model=list[AgreementResponse])
async def get_agreement_versions(
    agreement_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    versions = result.scalars().all()
    if not versions:
        raise HTTPException(status_code=404, detail="Agreement not found")
    return [_to_response(a) for a in versions]


@router.get(
    "/agreements/{agreement_id}/acceptances",
    response_model=list[AgreementAcceptanceResponse],
)
async def list_acceptances(
    agreement_id: str,
    owner_alias: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    stmt = select(AgreementAcceptance).where(
        AgreementAcceptance.agreement_id == agreement_id
    )
    if owner_alias:
        stmt = stmt.where(AgreementAcceptance.owner_alias == owner_alias)
    result = await db.execute(stmt)
    return [
        AgreementAcceptanceResponse(
            id=x.id,
            owner_alias=x.owner_alias,
            agreement_id=x.agreement_id,
            agreement_version=x.agreement_version,
            capacity=x.capacity,
            locale=x.locale,
            text_sha256=x.text_sha256,
            accepted_by=x.accepted_by,
            accepted_at=x.accepted_at,
        )
        for x in result.scalars().all()
    ]
