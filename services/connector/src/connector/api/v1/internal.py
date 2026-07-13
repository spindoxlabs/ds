"""Internal API — used by Dataset API PEP for EDR validation and consent checks."""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...dependencies import get_db, get_participant_registry
from ...registry.participants import HttpParticipantRegistry, ParticipantRegistry
from ...services.agreement_service import get_agreement_status

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/agreements/{agreement_id}/status")
async def agreement_status(
    agreement_id: str,
    db: AsyncSession = Depends(get_db),
):
    status = await get_agreement_status(db, agreement_id)
    if status is None:
        raise HTTPException(404, f"Agreement {agreement_id!r} not found")
    return status


@router.get("/consent/check")
async def consent_check(
    dataset_id: str,
    consumer_id: str,
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Check consent for a consumer+dataset pair.

    - With ``subject_id``: returns whether that specific subject has active consent.
    - Without ``subject_id``: returns all granted subject IDs (used by the Dataset API PEP
      to build a row-level IN-list filter).
    """
    from ...services.consent_service import check_consent, get_granted_subject_ids

    if subject_id:
        active = await check_consent(db, subject_id, dataset_id, consumer_id)
        return {
            "subject_id": subject_id,
            "dataset_id": dataset_id,
            "consumer_id": consumer_id,
            "consent_active": active,
        }
    # No subject_id: return all granted subjects for this (consumer, dataset)
    granted = await get_granted_subject_ids(db, dataset_id, consumer_id)
    return {
        "dataset_id": dataset_id,
        "consumer_id": consumer_id,
        "subject_ids": granted,
    }


@router.get("/participants/check")
async def participants_check(
    participant_id: str,
    scope: str,
    registry=Depends(get_participant_registry),
):
    """Check whether a participant has a given scope.

    Called by edc-extensions AccessScopeFunction as an HTTP proxy — keeps all
    participant logic in Python so no YAML parsing happens in Java.
    """
    if isinstance(registry, HttpParticipantRegistry):
        allowed = await registry.check_scope(participant_id, scope)
        return {"participant_id": participant_id, "scope": scope, "allowed": allowed}

    participant = registry.get_by_id(participant_id)
    if participant is None:
        return {"participant_id": participant_id, "scope": scope, "allowed": False}
    allowed = scope in participant.allowed_scopes
    return {"participant_id": participant_id, "scope": scope, "allowed": allowed}


@router.get("/edr-jwks")
async def edr_jwks():
    """Proxy the EDC provider JWKS endpoint.

    Allows the Dataset API (or any other consumer) to fetch the provider's
    public key set for EDR JWT signature verification without needing direct
    access to the EDC management API.
    """
    settings = get_settings()
    jwks_url = f"{settings.edc_provider_management_url.rstrip('/')}/v3/jwks"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                jwks_url,
                headers={"X-Api-Key": settings.edc_api_key},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC JWKS fetch failed: {exc.response.status_code}") from exc
    except httpx.RequestError:
        raise HTTPException(502, "EDC unreachable")
