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
from ...dependencies import get_db, get_participant_registry, require_internal_scope
from ...registry.participants import HttpParticipantRegistry, ParticipantRegistry
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
    _claims: dict = Depends(require_internal_scope),
):
    status = await get_agreement_status(db, agreement_id)
    if status is not None:
        return status
    edc_status = await _check_edc_agreement(agreement_id)
    if edc_status is not None:
        return edc_status
    raise HTTPException(404, f"Agreement {agreement_id!r} not found")


async def _check_edc_agreement(agreement_id: str) -> dict | None:
    """Check EDC management API for a contract agreement (provider-side fallback)."""
    settings = get_settings()
    edc_url = settings.edc_provider_management_url.rstrip("/")
    headers = {"x-api-key": settings.edc_api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{edc_url}/v3/contractagreements/{agreement_id}", headers=headers)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return {"active": True, "agreement_id": agreement_id, "source": "edc"}
    except (httpx.RequestError, Exception):
        return None


@router.get("/transfers/{transfer_id}/status")
async def transfer_status(
    transfer_id: str,
    agreement_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_internal_scope),
):
    """Return whether a consumer transfer is still active for data access.

    Dataset APIs use this as a PEP back-channel so a stale EDR cannot keep
    querying data after the consumer revokes access.

    Falls back to EDC management API when the transfer is not in the local DB
    (provider-side check: the consumer's transfer_id maps to a provider-side
    transfer via correlationId).
    """
    result = await db.execute(
        select(ConsumerTransferORM).where(ConsumerTransferORM.transfer_id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        active = await _check_edc_transfer(transfer_id, agreement_id)
        if active is not None:
            return active
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


async def _check_edc_transfer(transfer_id: str, agreement_id: str | None) -> dict | None:
    """Check EDC management API for a transfer by correlationId (provider-side lookup)."""
    settings = get_settings()
    edc_url = settings.edc_provider_management_url.rstrip("/")
    headers = {"x-api-key": settings.edc_api_key, "Content-Type": "application/json"}
    query = {
        "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
        "@type": "QuerySpec",
        "filterExpression": [
            {"operandLeft": "correlationId", "operator": "=", "operandRight": transfer_id}
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{edc_url}/v3/transferprocesses/request", json=query, headers=headers)
        if resp.status_code != 200 or not resp.text:
            return None
        results = resp.json()
        if not results:
            return None
        tp = results[0]
        state = tp.get("edc:state", tp.get("state", ""))
        active = state in ("STARTED", "COMPLETED")
        return {"active": active, "transfer_id": transfer_id, "agreement_id": agreement_id, "edc_state": state}
    except (httpx.RequestError, Exception):
        return None


@router.get("/consent/check")
async def consent_check(
    dataset_id: str,
    consumer_id: str,
    subject_id: Optional[str] = None,
    purpose: Optional[str] = None,
    controller_role: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_internal_scope),
):
    """Check consent for a consumer+dataset pair, scoped to a purpose and role.

    - With ``subject_id``: returns whether that specific subject has active consent.
    - Without ``subject_id``: returns all granted subject IDs (used by the Dataset API PEP
      to build a row-level IN-list filter).

    ``purpose`` is a comma-separated list of profile purpose slugs or IRIs — the
    reason the caller wants the data.  Matching uses ``odrl:isA`` semantics over
    the profile's local ``broader`` chain, so a consent to a parent purpose
    covers a narrower request but never the other way round.

    For a consent-required dataset an absent ``purpose`` denies: the caller has
    not said why it wants the data, so no consent can authorise it.  Callers
    that predate the purpose chain therefore fail closed rather than silently
    receiving everything.
    """
    from ...services.consent_service import check_consent, get_granted_subject_ids
    from ...services import consent_vocabulary as vocab

    purposes = [p.strip() for p in (purpose or "").split(",") if p.strip()]
    try:
        purposes = vocab.normalise_purposes(purposes)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    consent_required = None
    try:
        consent_required = vocab.requires_consent(vocab.resolve_dataset(dataset_id))
    except vocab.VocabularyError:
        # Leave it to the service layer, which fails closed on unknown datasets.
        pass

    if subject_id:
        active, reason = await check_consent(
            db,
            subject_id,
            dataset_id,
            consumer_id,
            purpose=purposes,
            controller_role=controller_role,
            consent_required=consent_required,
        )
        return {
            "subject_id": subject_id,
            "dataset_id": dataset_id,
            "consumer_id": consumer_id,
            "purpose": purposes,
            "controller_role": controller_role,
            "consent_active": active,
            "reason": reason,
        }
    # No subject_id: return all granted subjects for this (consumer, dataset)
    granted = await get_granted_subject_ids(
        db,
        dataset_id,
        consumer_id,
        purpose=purposes,
        controller_role=controller_role,
        consent_required=consent_required,
    )
    return {
        "dataset_id": dataset_id,
        "consumer_id": consumer_id,
        "purpose": purposes,
        "controller_role": controller_role,
        "subject_ids": granted,
    }


@router.get("/participants/check")
async def participants_check(
    participant_id: str,
    scope: str,
    registry=Depends(get_participant_registry),
    _claims: dict = Depends(require_internal_scope),
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


@router.post("/audit/query", status_code=202)
async def audit_query(
    req: QueryAuditRequest,
    request: Request,
    _claims: dict = Depends(require_internal_scope),
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
async def edr_jwks(
    _claims: dict = Depends(require_internal_scope),
):
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
