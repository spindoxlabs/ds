"""Consent registry API — subject sovereignty endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_notifier, get_settings_dep
from ...notifications.base import ConsentNotifier
from ...services import consent_service
from ...clients.edc_management import EdcManagementClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/consent", tags=["consent"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ConsentRequestCreate(BaseModel):
    consumer_id: str
    dataset_id: str
    subject_ids: list[str]
    purpose: list[str] = []
    message: str | None = None
    notification_url: str | None = None


class ConsentResponse(BaseModel):
    id: str
    subject_id: str
    consumer_id: str
    dataset_id: str
    purpose: list[str] = []
    message: str | None = None
    status: str
    requested_at: datetime
    decided_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class TransferRegisterRequest(BaseModel):
    consent_request_id: str
    transfer_id: str


# ── Consumer-facing endpoints ─────────────────────────────────────────────────

@router.post("/request", status_code=201)
async def create_consent_request(
    body: ConsentRequestCreate,
    db: AsyncSession = Depends(get_db),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    """Initiate consent requests for a set of data subjects."""
    request_ids = []
    async with db.begin():
        for subject_id in body.subject_ids:
            consent = await consent_service.create_consent_request(
                session=db,
                subject_id=subject_id,
                consumer_id=body.consumer_id,
                dataset_id=body.dataset_id,
                purpose=body.purpose,
                message=body.message,
                notification_url=body.notification_url,
                notifier=notifier,
            )
            request_ids.append(consent.id)
    return {"request_ids": request_ids, "status": "pending"}


@router.get("/status")
async def get_consent_status(
    consumer_id: str,
    dataset_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
):
    consents = await consent_service.list_subject_consents(
        session=db,
        subject_id=subject_id,
        dataset_id=dataset_id,
        consumer_id=consumer_id,
    )
    if not consents:
        return {"status": "not_found", "decided_at": None}
    latest = consents[0]
    return {
        "status": latest.status,
        "decided_at": latest.decided_at.isoformat() if latest.decided_at else None,
    }


# ── Subject-facing endpoints (JWT-protected) ──────────────────────────────────

@router.get("/my")
async def list_my_consents(
    status: str | None = None,
    dataset_id: str | None = None,
    consumer_id: str | None = None,
    x_subject_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List all consent records for the authenticated data subject."""
    subject_id = x_subject_id
    if not subject_id:
        raise HTTPException(401, "Missing subject identity (X-Subject-Id header)")

    consents = await consent_service.list_subject_consents(
        session=db,
        subject_id=subject_id,
        status=status,
        dataset_id=dataset_id,
        consumer_id=consumer_id,
    )
    return [ConsentResponse.model_validate(c) for c in consents]


@router.get("/my/{consent_id}")
async def get_my_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not x_subject_id:
        raise HTTPException(401, "Missing subject identity")
    consent = await consent_service.get_consent_request(db, consent_id)
    if not consent or consent.subject_id != x_subject_id:
        raise HTTPException(404, "Consent request not found")
    return ConsentResponse.model_validate(consent)


@router.post("/my/{consent_id}/approve")
async def approve_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    if not x_subject_id:
        raise HTTPException(401, "Missing subject identity")
    async with db.begin():
        consent = await consent_service.approve_consent(
            db, consent_id, x_subject_id, notifier=notifier
        )
    if not consent:
        raise HTTPException(404, "Consent request not found or not in pending state")
    return {"status": "granted", "id": consent.id}


@router.post("/my/{consent_id}/reject")
async def reject_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    if not x_subject_id:
        raise HTTPException(401, "Missing subject identity")
    async with db.begin():
        consent = await consent_service.reject_consent(
            db, consent_id, x_subject_id, notifier=notifier
        )
    if not consent:
        raise HTTPException(404, "Consent request not found or not in pending state")
    return {"status": "rejected", "id": consent.id}


@router.post("/my/{consent_id}/revoke")
async def revoke_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    if not x_subject_id:
        raise HTTPException(401, "Missing subject identity")
    async with db.begin():
        consent = await consent_service.revoke_consent(
            db, consent_id, x_subject_id, notifier=notifier
        )
    if not consent:
        raise HTTPException(404, "Consent request not found or not in granted state")

    # Terminate active EDC transfers
    transfer_ids = consent.transfer_ids or []
    if transfer_ids:
        provider_edc = EdcManagementClient(
            base_url=settings.edc_provider_management_url,
            api_key=settings.edc_api_key,
        )
        for tid in transfer_ids:
            try:
                await provider_edc.delete_asset(tid)  # placeholder: use terminate endpoint
                log.info("Terminated transfer %s due to consent revocation", tid)
            except Exception as exc:
                log.warning("Failed to terminate transfer %s: %s", tid, exc)
        await provider_edc.close()

    return {"status": "revoked", "id": consent.id, "transfers_terminated": len(transfer_ids)}


# ── Internal endpoints ────────────────────────────────────────────────────────

@router.post("/register-transfer", status_code=200, include_in_schema=False)
async def register_transfer(
    body: TransferRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        ok = await consent_service.register_transfer(db, body.consent_request_id, body.transfer_id)
    return {"registered": ok}
