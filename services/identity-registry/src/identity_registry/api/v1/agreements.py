from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Agreement, AgreementAcceptance, Owner, Participant
from ...dependencies import get_db, require_admin_or_read_scope
from ...schemas.responses import (
    AgreementAcceptanceResponse,
    AgreementResponse,
    CurrentAgreementResponse,
)

router = APIRouter(tags=["agreements"])


async def _owner_for_participant(db: AsyncSession, participant_did: str) -> Owner | None:
    """Resolve a DSP participant DID to the owner that signed for it.

    An owner is normally reachable by its own ``did``. When it is not — the
    participant was registered directly rather than promoted from an
    application — fall back to matching the participant's aliases, so a
    deployment that seeded its owners and participants separately still
    resolves rather than silently reporting "no agreement".
    """
    result = await db.execute(select(Owner).where(Owner.did == participant_did))
    owner = result.scalar_one_or_none()
    if owner is not None:
        return owner

    participant = (
        await db.execute(select(Participant).where(Participant.did == participant_did))
    ).scalar_one_or_none()
    if participant is None:
        return None

    for candidate in (await db.execute(select(Owner))).scalars().all():
        if participant_did in (candidate.aliases or []):
            return candidate
    return None


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


@router.get("/agreements/current", response_model=CurrentAgreementResponse)
async def get_current_agreement(
    participant_did: str = Query(..., description="DSP participant DID"),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    """The agreement a participant currently holds, and the capacity it declares.

    This is the connector's circle check (`services/connector/.../circle.py`):
    it decides whether a requesting party is a **processor** of an offer's
    controller — disclosed under a DPA, never re-asked — or an **independent
    controller**, which is a new question for the data subject. Capacity is not
    inferable from identity, so it is read from what the organisation signed.

    Fails closed by design. An unknown participant, an owner with no accepted
    agreement, or a suspended owner all yield 404 rather than a null capacity:
    the caller treats "no answer" as "outside the circle", which asks a possibly
    redundant question instead of skipping a required one.

    Routed above `/agreements/{agreement_id}` so `current` is not swallowed as
    an agreement id.
    """
    owner = await _owner_for_participant(db, participant_did)
    if owner is None:
        raise HTTPException(
            status_code=404, detail="No owner is registered for that participant DID"
        )
    if owner.status != "verified":
        raise HTTPException(
            status_code=404,
            detail=f"Owner '{owner.id}' is {owner.status}, not verified",
        )
    if not owner.agreement_id or not owner.agreement_capacity:
        raise HTTPException(
            status_code=404,
            detail=f"Owner '{owner.id}' has accepted no agreement",
        )
    return CurrentAgreementResponse(
        participant_did=participant_did,
        owner_alias=owner.id,
        agreement_id=owner.agreement_id,
        version=owner.agreement_version,
        capacity=owner.agreement_capacity,
        accepted_at=owner.agreement_accepted_at,
    )


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
