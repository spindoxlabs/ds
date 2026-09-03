from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import Owner
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_org_read,
    require_org_write,
    require_owner_resolve,
)
from ...schemas.requests import CreateOwnerRequest, UpdateOwnerRequest
from ...schemas.responses import OwnerResponse
from ...services.did import refuse_dev_only_did
from ...services.org_onboarding import resolve_owner as ops_resolve_owner

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
        registration_number=owner.registration_number,
        registration_type=owner.registration_type,
        hq_country_code=owner.hq_country_code,
        legal_country_code=owner.legal_country_code,
        parent_organizations=owner.parent_organizations,
        sub_organizations=owner.sub_organizations,
        status=owner.status,
        verified_at=owner.verified_at,
        verified_by=owner.verified_by,
        evidence_ref=owner.evidence_ref,
        agreement_id=owner.agreement_id,
        agreement_version=owner.agreement_version,
        agreement_accepted_at=owner.agreement_accepted_at,
        agreement_capacity=owner.agreement_capacity,
        created_at=owner.created_at,
        updated_at=owner.updated_at,
    )


# ── Admin endpoints ──────────────────────────────────────────────


@router.post("/admin/owners", status_code=201, response_model=OwnerResponse)
async def create_owner(
    data: CreateOwnerRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_org_write),
    settings: Settings = Depends(get_settings_dep),
):
    existing = await db.execute(select(Owner).where(Owner.id == data.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Owner already exists")

    refuse_dev_only_did(data.did, route="POST /admin/owners", settings=settings)

    status = data.status or "pending"
    verified_by = data.verified_by
    verified_at = data.verified_at
    evidence_ref = data.evidence_ref
    if status == "verified":
        # A verified owner must carry its evidence — the same rule the DB CHECK
        # enforces, surfaced here as a 422 instead of an IntegrityError. This is
        # what stops a seeded owner from reading as verified for free.
        if not verified_by:
            raise HTTPException(
                status_code=422,
                detail="status 'verified' requires 'verified_by'",
            )
        verified_at = verified_at or datetime.now(UTC)

    owner = Owner(
        id=data.id,
        type=data.type,
        name=data.name,
        did=data.did,
        url=data.url,
        aliases=data.aliases,
        organization_config=data.organization_config,
        status=status,
        verified_by=verified_by,
        verified_at=verified_at,
        evidence_ref=evidence_ref,
    )
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    return _to_response(owner)


@router.get("/admin/owners", response_model=list[OwnerResponse])
async def list_owners(
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_org_read),
):
    result = await db.execute(select(Owner))
    return [_to_response(o) for o in result.scalars().all()]


@router.get("/admin/owners/{owner_id}", response_model=OwnerResponse)
async def get_owner(
    owner_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_org_read),
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
    _claims: dict = Depends(require_org_write),
    settings: Settings = Depends(get_settings_dep),
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
        refuse_dev_only_did(
            data.did, route=f"PUT /admin/owners/{owner_id}", settings=settings
        )
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
    _claims: dict = Depends(require_org_write),
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
    _claims: dict = Depends(require_owner_resolve),
):
    # The same id-then-alias fallback the onboarding service resolves by. It
    # was inlined here, so a change to how an alias matches would have had to
    # be made in two places to hold.
    #
    # The guard used to be `require_admin_or_read_scope`, which refused the
    # caller this route was written for: `svc-ds-onboarding` holds
    # `identity-registry.organizations.read` — annotated in `clients.yaml` as
    # "resolve the bound community's organisation at boot" — and deliberately
    # holds neither `admin` nor `read`. So the realm entry named the operation,
    # the endpoint implemented it, and the guard refused it; the onboarding
    # service fell back to `GET /admin/owners/{alias}`, which matches on
    # `Owner.id` and 404s on an alias — read on that side as *no such
    # organisation*, a startup-refusing error for a correct deployment.
    owner = await ops_resolve_owner(db, alias)

    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return _to_response(owner)
