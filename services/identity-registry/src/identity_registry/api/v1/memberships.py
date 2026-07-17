from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import OrganizationMembership
from ...dependencies import (
    get_db,
    require_admin_scope,
    require_membership_read_scope,
)
from ...schemas.requests import CreateMembershipRequest
from ...schemas.responses import MembershipCheckResponse, MembershipResponse

router = APIRouter(tags=["memberships"])


def _to_response(m: OrganizationMembership) -> MembershipResponse:
    return MembershipResponse(
        user_did=m.user_did,
        organization_alias=m.organization_alias,
        role=m.role,
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ── Admin endpoints ──────────────────────────────────────────────


@router.post("/admin/memberships", status_code=201, response_model=MembershipResponse)
async def create_membership(
    data: CreateMembershipRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    existing = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_did == data.user_did,
                OrganizationMembership.organization_alias == data.organization_alias,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Membership already exists")

    membership = OrganizationMembership(
        user_did=data.user_did,
        organization_alias=data.organization_alias,
        role=data.role,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return _to_response(membership)


@router.get("/admin/memberships", response_model=list[MembershipResponse])
async def list_memberships(
    organization: str | None = Query(default=None),
    user_did: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    stmt = select(OrganizationMembership)
    if organization:
        stmt = stmt.where(OrganizationMembership.organization_alias == organization)
    if user_did:
        stmt = stmt.where(OrganizationMembership.user_did == user_did)
    result = await db.execute(stmt)
    return [_to_response(m) for m in result.scalars().all()]


@router.delete("/admin/memberships/{user_did:path}/{organization_alias}", status_code=204)
async def delete_membership(
    user_did: str,
    organization_alias: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_did == user_did,
                OrganizationMembership.organization_alias == organization_alias,
            )
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    await db.delete(membership)
    await db.commit()


# ── Service endpoint ─────────────────────────────────────────────


@router.get("/memberships/check", response_model=MembershipCheckResponse)
async def check_membership(
    user_did: str = Query(...),
    organization: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_membership_read_scope),
):
    result = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_did == user_did,
                OrganizationMembership.organization_alias == organization,
                OrganizationMembership.status == "active",
            )
        )
    )
    return MembershipCheckResponse(member=result.scalar_one_or_none() is not None)
