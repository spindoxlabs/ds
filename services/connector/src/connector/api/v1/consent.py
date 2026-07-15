"""Consent registry API — subject sovereignty endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_notifier, get_settings_dep, require_internal_scope
from ...notifications.base import ConsentNotifier
from ...services import consent_service
from ...services.user_credentials import verify_user_vc_jwt
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


class DataSharingSetRequest(BaseModel):
    dataset_id: str
    consumer_id: str | None = None
    enabled: bool
    purpose: list[str] = []


def _verify_user(
    x_user_vc: str | None,
    x_subject_id: str | None,
    settings: Settings,
    roles: set[str],
):
    return verify_user_vc_jwt(
        x_user_vc,
        x_subject_id,
        settings.trust_anchor_key_path,
        roles,
        expected_issuer=settings.trust_anchor_did,
        expected_linked_participant=settings.consumer_participant_did,
        credential_status_path=settings.credential_status_path,
        credential_status_url=settings.credential_status_url,
    )


# ── Consumer-facing endpoints ─────────────────────────────────────────────────

@router.post("/request", status_code=201)
async def create_consent_request(
    body: ConsentRequestCreate,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    """Initiate consent requests for a set of data subjects."""
    _verify_user(x_user_vc, x_subject_id, settings, {"ConsumerUser"})
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
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"ConsumerUser", "DataSubject"})
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
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """List all consent records for the authenticated data subject."""
    subject_id = x_subject_id
    _verify_user(x_user_vc, subject_id, settings, {"DataSubject", "ConsumerUser"})

    consents = await consent_service.list_subject_consents(
        session=db,
        subject_id=subject_id,
        status=status,
        dataset_id=dataset_id,
        consumer_id=consumer_id,
    )
    return [ConsentResponse.model_validate(c) for c in consents]


@router.get("/my/shares")
async def list_my_data_shares(
    consumer_id: str | None = None,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """List standing sharing decisions for the authenticated data subject."""
    subject_id = x_subject_id
    _verify_user(x_user_vc, subject_id, settings, {"DataSubject"})

    consents = await consent_service.list_subject_consents(
        session=db,
        subject_id=subject_id,
        consumer_id=consumer_id or settings.consumer_participant_did,
    )
    latest_by_dataset: dict[str, ConsentResponse] = {}
    for consent in consents:
        latest_by_dataset.setdefault(consent.dataset_id, ConsentResponse.model_validate(consent))
    return list(latest_by_dataset.values())


@router.post("/my/shares")
async def set_my_data_share(
    body: DataSharingSetRequest,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """Enable or disable a data subject's sharing decision for one dataset."""
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})

    async with db.begin():
        consent = await consent_service.set_subject_data_sharing(
            session=db,
            subject_id=x_subject_id,
            dataset_id=body.dataset_id,
            consumer_id=body.consumer_id or settings.consumer_participant_did,
            enabled=body.enabled,
            purpose=body.purpose,
        )
    return ConsentResponse.model_validate(consent)


@router.get("/my/{consent_id}")
async def get_my_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject", "ConsumerUser"})
    consent = await consent_service.get_consent_request(db, consent_id)
    if not consent or consent.subject_id != x_subject_id:
        raise HTTPException(404, "Consent request not found")
    return ConsentResponse.model_validate(consent)


@router.post("/my/{consent_id}/approve")
async def approve_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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
    _claims: dict = Depends(require_internal_scope),
):
    async with db.begin():
        ok = await consent_service.register_transfer(db, body.consent_request_id, body.transfer_id)
    return {"registered": ok}
