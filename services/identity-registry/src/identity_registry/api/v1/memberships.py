from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Did, OrganizationMembership
from ...dependencies import (
    get_db,
    require_admin_scope,
    require_membership_read_scope,
    require_memberships_write,
)
from ...schemas.requests import CreateMembershipRequest
from ...schemas.responses import MembershipCheckResponse, MembershipResponse
from ...services.org_onboarding import resolve_owner

router = APIRouter(tags=["memberships"])


async def _canonical_org(db: AsyncSession, alias: str) -> str:
    """The owner id *alias* belongs to, or *alias* itself when it names no owner.

    **An organisation answers to more than one name, and a membership row is
    worthless under the wrong one.** ``Owner.aliases`` exists precisely because a
    realm, a governance file and an owner list routinely spell one organisation
    three ways, and ``/owners/resolve`` has always collapsed them. This table did
    not: every route compared ``organization_alias`` as a literal string, so a
    row written under an alias was invisible to a check made under the owner id.
    Both sides answered exactly what they were asked and the member was refused
    anyway — a 403 asserting they belonged to nothing, with an active membership
    one alias away.

    Resolving on **every** route, rather than on the check alone, is what makes
    the property hold rather than merely usually hold:

    * writing under any spelling stores one row, so two names cannot become two
      members;
    * a delete resolves to the row its create wrote, instead of 404ing and
      leaving a membership behind that revocation believed it had removed;
    * a list filtered by either spelling returns the same members.

    Unknown names pass through untouched. A deployment that registers no owners
    keeps the literal-string behaviour it has today, so this cannot turn a
    working setup into a 404.
    """
    owner = await resolve_owner(db, alias)
    return owner.id if owner else alias


def _to_response(m: OrganizationMembership) -> MembershipResponse:
    return MembershipResponse(
        user_did=m.user_did,
        organization_alias=m.organization_alias,
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ── Admin endpoints ──────────────────────────────────────────────


@router.post("/admin/memberships", status_code=201, response_model=MembershipResponse)
async def create_membership(
    data: CreateMembershipRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_memberships_write),
):
    organization_alias = await _canonical_org(db, data.organization_alias)
    existing = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_did == data.user_did,
                OrganizationMembership.organization_alias == organization_alias,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Membership already exists")

    # user_did is a FK to dids.did — check up front so an unregistered DID returns a
    # clear 404 instead of surfacing an IntegrityError as a 500.
    known_did = await db.execute(select(Did.did).where(Did.did == data.user_did))
    if not known_did.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Unknown DID: {data.user_did}")

    membership = OrganizationMembership(
        user_did=data.user_did,
        organization_alias=organization_alias,
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
    # Stays on admin deliberately. Registering a membership and *enumerating*
    # who belongs to which organisation are different acts: `membership.read`
    # answers one (user, org) question at a time via `/memberships/check`, and
    # widening it to this list would hand every holder the whole roster.
    _claims: dict = Depends(require_admin_scope),
):
    stmt = select(OrganizationMembership)
    if organization:
        stmt = stmt.where(
            OrganizationMembership.organization_alias
            == await _canonical_org(db, organization)
        )
    if user_did:
        stmt = stmt.where(OrganizationMembership.user_did == user_did)
    result = await db.execute(stmt)
    return [_to_response(m) for m in result.scalars().all()]


@router.delete(
    "/admin/memberships/{user_did:path}/{organization_alias}", status_code=204
)
async def delete_membership(
    user_did: str,
    organization_alias: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_memberships_write),
):
    result = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_did == user_did,
                OrganizationMembership.organization_alias
                == await _canonical_org(db, organization_alias),
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
                OrganizationMembership.organization_alias
                == await _canonical_org(db, organization),
                OrganizationMembership.status == "active",
            )
        )
    )
    return MembershipCheckResponse(member=result.scalar_one_or_none() is not None)
