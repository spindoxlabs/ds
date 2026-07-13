from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import KeycloakMapping, Participant
from ...dependencies import get_db
from ...schemas.responses import KeycloakMappingResponse, ParticipantCheckResponse

router = APIRouter(tags=["internal"])


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
