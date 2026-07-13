from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import KeycloakMapping, Participant
from ...dependencies import get_db, require_admin_scope
from ...schemas.responses import (
    KeycloakMappingResponse,
    ParticipantCheckResponse,
    ParticipantResponse,
)

router = APIRouter(tags=["internal"])


@router.get("/participants", response_model=list[ParticipantResponse])
async def list_active_participants(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Participant).where(Participant.active.is_(True))
    )
    return [
        ParticipantResponse(
            did=p.did,
            dsp_address=p.dsp_address,
            role=p.role,
            allowed_scopes=p.allowed_scopes,
            active=p.active,
            registered_at=p.registered_at,
        )
        for p in result.scalars().all()
    ]


@router.get(
    "/participants/{did:path}/check",
    response_model=ParticipantCheckResponse,
)
async def check_participant(
    did: str,
    scope: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Participant).where(Participant.did == did, Participant.active.is_(True))
    )
    participant = result.scalar_one_or_none()
    if not participant:
        return ParticipantCheckResponse(allowed=False)

    allowed = scope in participant.allowed_scopes
    return ParticipantCheckResponse(allowed=allowed)


@router.get(
    "/keycloak/mapping/{did:path}",
    response_model=KeycloakMappingResponse,
)
async def get_keycloak_mapping_by_did(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.did == did)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return KeycloakMappingResponse(
        did=mapping.did,
        keycloak_realm=mapping.keycloak_realm,
        keycloak_user_id=mapping.keycloak_user_id,
        email=mapping.email,
        subject_id=mapping.subject_id,
    )


@router.get(
    "/keycloak/mapping",
    response_model=KeycloakMappingResponse,
)
async def get_keycloak_mapping_by_subject(
    subject_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.subject_id == subject_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return KeycloakMappingResponse(
        did=mapping.did,
        keycloak_realm=mapping.keycloak_realm,
        keycloak_user_id=mapping.keycloak_user_id,
        email=mapping.email,
        subject_id=mapping.subject_id,
    )
