from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Owner
from ...dependencies import get_db, require_admin_scope, require_admin_or_read_scope
from ...schemas.requests import CreateOwnerRequest, UpdateOwnerRequest
from ...schemas.responses import OwnerResponse

router = APIRouter(tags=["owners"])


def _canonical_uri(owner: Owner) -> str | None:
    return owner.did or owner.url or None


def _to_response(owner: Owner) -> OwnerResponse:
    return OwnerResponse(
        id=owner.id,
        type=owner.type,
        name=owner.name,
        did=owner.did,
        url=owner.url,
        aliases=owner.aliases or [],
        organization_config=owner.organization_config,
        canonical_uri=_canonical_uri(owner),
        created_at=owner.created_at,
        updated_at=owner.updated_at,
    )


# ── Admin endpoints ──────────────────────────────────────────────


@router.post("/admin/owners", status_code=201, response_model=OwnerResponse)
async def create_owner(
    data: CreateOwnerRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    existing = await db.execute(select(Owner).where(Owner.id == data.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Owner already exists")

    owner = Owner(
        id=data.id,
        type=data.type,
        name=data.name,
        did=data.did,
        url=data.url,
        aliases=data.aliases,
        organization_config=data.organization_config,
    )
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    return _to_response(owner)


@router.get("/admin/owners", response_model=list[OwnerResponse])
async def list_owners(
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Owner))
    return [_to_response(o) for o in result.scalars().all()]


@router.get("/admin/owners/{owner_id}", response_model=OwnerResponse)
async def get_owner(
    owner_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return _to_response(owner)


@router.put("/admin/owners/{owner_id}", response_model=OwnerResponse)
async def update_owner(
    owner_id: str,
    data: UpdateOwnerRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    if data.type is not None:
        owner.type = data.type
    if data.name is not None:
        owner.name = data.name
    if data.did is not None:
        owner.did = data.did
    if data.url is not None:
        owner.url = data.url
    if data.aliases is not None:
        owner.aliases = data.aliases
    if data.organization_config is not None:
        owner.organization_config = data.organization_config
    owner.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(owner)
    return _to_response(owner)


@router.delete("/admin/owners/{owner_id}", status_code=204)
async def delete_owner(
    owner_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    await db.delete(owner)
    await db.commit()


# ── Service endpoint ─────────────────────────────────────────────


@router.get("/owners/resolve", response_model=OwnerResponse)
async def resolve_owner(
    alias: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    result = await db.execute(select(Owner).where(Owner.id == alias))
    owner = result.scalar_one_or_none()

    if not owner:
        result = await db.execute(select(Owner))
        for o in result.scalars().all():
            if alias in (o.aliases or []):
                owner = o
                break

    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return _to_response(owner)
