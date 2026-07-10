"""Internal API — used by Dataset API PEP for EDR validation and consent checks."""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db.models import ConsumerAccessRequestORM, ConsumerTransferORM
from ...dependencies import get_db, get_participant_registry
from ...registry.participants import ParticipantRegistry
from ...services.agreement_service import get_agreement_status

router = APIRouter(prefix="/internal", tags=["internal"])


class QueryAuditRequest(BaseModel):
    dataset_id: str
    provider_id: str | None = None
    consumer_id: str | None = None
    user_id: str | None = None
    subject_id: str | None = None
    agreement_id: str | None = None
    transfer_id: str | None = None
    row_count: int | None = None
    authorized_subject_ids: list[str] | None = None


@router.get("/agreements/{agreement_id}/status")
async def agreement_status(
    agreement_id: str,
    db: AsyncSession = Depends(get_db),
):
    status = await get_agreement_status(db, agreement_id)
    if status is None:
        raise HTTPException(404, f"Agreement {agreement_id!r} not found")
    return status


@router.get("/transfers/{transfer_id}/status")
async def transfer_status(
    transfer_id: str,
    agreement_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return whether a consumer transfer is still active for data access.

    Dataset APIs use this as a PEP back-channel so a stale EDR cannot keep
    querying data after the consumer revokes access.
    """
    result = await db.execute(
        select(ConsumerTransferORM).where(ConsumerTransferORM.transfer_id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        return {"active": False, "reason": "transfer_not_found"}

    if agreement_id and transfer.contract_agreement_id != agreement_id:
        return {"active": False, "reason": "agreement_mismatch"}

    request_result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.transfer_id == transfer_id,
            ConsumerAccessRequestORM.subject_id == transfer.subject_id,
        )
    )
    request = request_result.scalar_one_or_none()
    if request and request.status == "revoked":
        return {"active": False, "reason": "request_revoked"}

    agreement = await get_agreement_status(db, transfer.contract_agreement_id)
    if agreement is not None and not agreement["active"]:
        return {"active": False, "reason": "agreement_terminated"}

    return {
        "active": True,
        "transfer_id": transfer.transfer_id,
        "agreement_id": transfer.contract_agreement_id,
        "asset_id": transfer.asset_id,
        "subject_id": transfer.subject_id,
        "consumer_id": transfer.consumer_id,
    }


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
    registry: ParticipantRegistry = Depends(get_participant_registry),
):
    """Check whether a participant has a given scope.

    Called by edc-extensions AccessScopeFunction as an HTTP proxy — keeps all
    participant logic in Python so no YAML parsing happens in Java.
    """
    participant = registry.get_by_id(participant_id)
    if participant is None:
        return {"participant_id": participant_id, "scope": scope, "allowed": False}
    allowed = scope in participant.allowed_scopes
    return {"participant_id": participant_id, "scope": scope, "allowed": allowed}


@router.post("/audit/query", status_code=202)
async def audit_query(
    req: QueryAuditRequest,
    request: Request,
):
    """Emit a QueryExecuted provenance event from a data adapter/PEP."""
    settings = get_settings()
    prov = getattr(request.app.state, "prov", None)
    if prov:
        await prov.query_executed(
            data_product_id=req.dataset_id,
            provider_id=req.provider_id or settings.participant_did,
            consumer_id=req.consumer_id,
            user_id=req.user_id or req.subject_id,
            subject_id=req.subject_id,
            agreement_id=req.agreement_id,
            transfer_id=req.transfer_id,
            row_count=req.row_count,
            authorized_subject_ids=req.authorized_subject_ids,
        )
    return {"status": "accepted"}


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
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC unreachable: {exc}") from exc
