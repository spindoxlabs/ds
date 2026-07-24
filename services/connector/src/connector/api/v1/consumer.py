"""Consumer routes: catalog, negotiate, transfer, EDR, flow."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsumerAccessRequestORM, ConsumerTransferORM
from ...dependencies import get_consumer_service, get_db, get_settings_dep
from ...registry.participants import UnknownParticipantError
from ...schemas.edc import FlowRequest, FlowResult
from ...services.agreement_service import terminate_agreement, upsert_agreement
from ...services.user_credentials import verify_user_vc_jwt

router = APIRouter(prefix="/consumer", tags=["consumer"])


class CatalogRequest(BaseModel):
    counter_party_address: str
    counter_party_id: str | None = None
    filters: dict | None = None


class NegotiateRequest(BaseModel):
    counter_party_address: str
    offer_id: str
    asset_id: str
    assigner: str
    odrl_policy: dict | None = None


class TransferStartRequest(BaseModel):
    contract_agreement_id: str
    counter_party_address: str
    asset_id: str
    connector_id: str


class RevokeRequest(BaseModel):
    reason: str | None = None


def _verify_consumer_user(
    x_user_vc: str | None,
    x_subject_id: str | None,
    settings: Settings,
):
    return verify_user_vc_jwt(
        x_user_vc,
        x_subject_id,
        settings.trust_anchor_key_path,
        {"ConsumerUser"},
        expected_issuer=settings.trust_anchor_did,
        expected_linked_participant=settings.consumer_participant_did,
        credential_status_path=settings.credential_status_path,
        credential_status_url=settings.credential_status_url,
        insecure_dev=settings.vc_insecure_dev,
    )


@router.post("/catalog")
async def request_catalog(
    req: CatalogRequest,
    svc=Depends(get_consumer_service),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
):
    try:
        catalog = await svc.request_catalog(req.counter_party_address, req.counter_party_id)
        prov = getattr(svc, "_prov", None)
        if prov:
            await prov.catalog_viewed(
                provider_id=req.counter_party_id or settings.participant_did,
                consumer_id=settings.consumer_participant_did,
                user_id=x_subject_id,
                counter_party_address=req.counter_party_address,
                dataset_count=len(catalog.get("dataset") or []),
                event_id=f"catalog-view:{x_subject_id or 'anonymous'}:{req.counter_party_address}",
            )
        return catalog
    except UnknownParticipantError as exc:
        raise HTTPException(403, f"Unknown dataspace participant: {req.counter_party_address}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC catalog request failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC catalog request failed: {exc.response.text}") from exc


@router.post("/negotiate")
async def start_negotiation(
    req: NegotiateRequest,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    duplicate = await _find_blocking_request(db, svc, x_subject_id, req.asset_id)
    if duplicate:
        raise HTTPException(
            409,
            (
                f"Access for asset {req.asset_id!r} was already requested by this user "
                f"(status={duplicate['status']}, id={duplicate['id']})."
            ),
        )
    try:
        negotiation_id = await svc.negotiate(
            counter_party_address=req.counter_party_address,
            offer_id=req.offer_id,
            asset_id=req.asset_id,
            assigner=req.assigner,
            odrl_policy=req.odrl_policy,
        )
    except UnknownParticipantError as exc:
        raise HTTPException(403, f"Unknown dataspace participant: {req.counter_party_address}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC negotiation failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC negotiation failed: {exc.response.text}") from exc
    access_request = ConsumerAccessRequestORM(
        subject_id=x_subject_id,
        asset_id=req.asset_id,
        counter_party_address=req.counter_party_address,
        offer_id=req.offer_id,
        assigner=req.assigner,
        negotiation_id=negotiation_id,
        status="negotiating",
    )
    db.add(access_request)
    await db.flush()
    prov = getattr(svc, "_prov", None)
    if prov:
        await prov.access_requested(
            request_id=access_request.id,
            data_product_id=req.asset_id,
            provider_id=req.assigner,
            consumer_id=settings.consumer_participant_did,
            user_id=x_subject_id,
            purpose=_extract_purposes(req.odrl_policy),
            offer_id=req.offer_id,
        )
        await prov.negotiation_started(
            negotiation_id=negotiation_id,
            data_product_id=req.asset_id,
            provider_id=req.assigner,
            consumer_id=settings.consumer_participant_did,
            user_id=x_subject_id,
            offer_id=req.offer_id,
        )
    await db.commit()
    return {"negotiation_id": negotiation_id}


@router.get("/requests")
async def list_access_requests(
    http_request: Request,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    result = await db.execute(
        select(ConsumerAccessRequestORM)
        .where(ConsumerAccessRequestORM.subject_id == x_subject_id)
        .order_by(desc(ConsumerAccessRequestORM.created_at))
    )
    requests = result.scalars().all()
    items = []
    changed = False
    for request in requests:
        negotiation_state = None
        transfer_state = None
        awaiting_since = None
        if request.negotiation_id:
            try:
                negotiation = await svc._edc.get_negotiation(request.negotiation_id)
                negotiation_state = negotiation.get("state")
                if negotiation_state in {"FINALIZED", "VERIFIED", "AGREED"} and request.status == "negotiating":
                    request.status = "finalized"
                    changed = True
                elif negotiation_state == "TERMINATED" and request.status != "revoked":
                    request.status = "terminated"
                    changed = True
                elif negotiation_state == "REQUESTED" and request.status in {
                    "negotiating", "awaiting_consent"
                }:
                    # REQUESTED is ambiguous on the wire: it means both "the
                    # provider has not looked yet" and "waiting on a person,
                    # possibly for weeks". Only the provider can tell them
                    # apart, so ask — off the DSP path, and never as a
                    # precondition of anything (§6.6).
                    awaiting_since = await _provider_consent_status(
                        http_request, settings, request.negotiation_id
                    )
                    status = "awaiting_consent" if awaiting_since else "negotiating"
                    if request.status != status:
                        request.status = status
                        changed = True
            except (httpx.RequestError, httpx.HTTPStatusError):
                negotiation_state = None
        if request.transfer_id:
            try:
                transfer = await svc._edc.get_transfer(request.transfer_id)
                transfer_state = transfer.get("state")
            except (httpx.RequestError, httpx.HTTPStatusError):
                transfer_state = None
        items.append({
            "id": request.id,
            "subject_id": request.subject_id,
            "asset_id": request.asset_id,
            "counter_party_address": request.counter_party_address,
            "offer_id": request.offer_id,
            "assigner": request.assigner,
            "negotiation_id": request.negotiation_id,
            "contract_agreement_id": request.contract_agreement_id,
            "negotiation_state": negotiation_state,
            "transfer_id": request.transfer_id,
            "transfer_state": transfer_state,
            "status": request.status,
            "awaiting_consent_since": awaiting_since,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "updated_at": request.updated_at.isoformat() if request.updated_at else None,
            "can_revoke": request.status in {
                "negotiating", "awaiting_consent", "finalized", "transferring", "transferred"
            },
        })
    if changed:
        await db.commit()
    return items


async def _provider_consent_status(
    http_request: Request,
    settings: Settings,
    negotiation_id: str,
) -> str | None:
    """When did the provider start waiting on a person for this negotiation?

    ``None`` for "not waiting, or cannot tell" — the two are deliberately the
    same answer here. This read is off the DSP path: if the provider is
    unreachable, or does not implement it, the negotiation is unaffected and the
    request simply keeps showing as negotiating. Nothing may depend on it.

    Our negotiation id is the provider's ``correlationId``, which is why the
    provider can answer without us learning any provider-side identifier.
    """
    base_url = settings.provider_connector_url
    token_provider = getattr(http_request.app.state, "ir_token_provider", None)
    if not base_url or token_provider is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/consent/pending",
                params={"correlation_id": negotiation_id},
                headers={"Authorization": f"Bearer {await token_provider()}"},
            )
        if response.status_code != 200:
            return None
        body = response.json()
        return body.get("since") if body.get("awaiting_consent") else None
    except (httpx.HTTPError, ValueError):
        return None


@router.post("/requests/{request_id}/revoke")
async def revoke_access_request(
    request_id: str,
    req: RevokeRequest | None = None,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.id == request_id,
            ConsumerAccessRequestORM.subject_id == x_subject_id,
        )
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Access request not found")

    reason = req.reason if req else None
    transfer_terminated = False
    agreement_ids = await _agreement_ids_for_request(db, request)
    if request.transfer_id:
        try:
            await svc._edc.terminate_transfer(request.transfer_id, reason)
            transfer_terminated = True
        except httpx.HTTPStatusError as exc:
            raise HTTPException(502, f"EDC transfer revoke failed: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise HTTPException(502, f"EDC transfer revoke failed: {exc}") from exc

    request.status = "revoked"
    terminated_agreements: list[str] = []
    for agreement_id in agreement_ids:
        agreement = await terminate_agreement(db, agreement_id, reason)
        if agreement:
            terminated_agreements.append(agreement_id)
    transfer_result = await db.execute(
        select(ConsumerTransferORM).where(
            ConsumerTransferORM.subject_id == x_subject_id,
            ConsumerTransferORM.asset_id == request.asset_id,
        )
    )
    for transfer in transfer_result.scalars().all():
        await db.delete(transfer)
    await db.commit()
    prov = getattr(svc, "_prov", None)
    if prov:
        await prov.access_revoked(
            data_product_id=request.asset_id,
            provider_id=request.assigner,
            consumer_id=settings.consumer_participant_did,
            subject_id=x_subject_id,
            agreement_id=agreement_ids[0] if agreement_ids else None,
            transfer_id=request.transfer_id,
            reason=reason,
            event_id=f"revoke:{request.id}",
        )
    return {
        "status": "revoked",
        "id": request.id,
        "transfer_terminated": transfer_terminated,
        "terminated_agreements": terminated_agreements,
    }


@router.get("/negotiations/{negotiation_id}")
async def get_negotiation(
    negotiation_id: str,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    try:
        data = await svc._edc.get_negotiation(negotiation_id)
        agreement_id = data.get("contractAgreementId")
        state = data.get("state")
        access_request = await _access_request_for_negotiation(db, negotiation_id)
        if data.get("state") in {"FINALIZED", "VERIFIED", "AGREED"} and agreement_id:
            asset_id = (
                data.get("assetId")
                or (access_request.asset_id if access_request else "")
            )
            provider_id = (
                data.get("counterPartyId")
                or (access_request.assigner if access_request else "provider")
            )
            await upsert_agreement(
                session=db,
                agreement_id=agreement_id,
                asset_id=asset_id,
                consumer_id=settings.consumer_participant_did,
                provider_id=provider_id,
                policy_snapshot=data.get("policy") or {},
                agreed_at=datetime.now(timezone.utc),
            )
            await _update_access_request_status(
                db, negotiation_id, "finalized", contract_agreement_id=agreement_id
            )
            prov = getattr(svc, "_prov", None)
            if prov:
                await prov.negotiation_finalized(
                    negotiation_id=negotiation_id,
                    agreement_id=agreement_id,
                    data_product_id=asset_id,
                    provider_id=provider_id,
                    consumer_id=settings.consumer_participant_did,
                    user_id=access_request.subject_id if access_request else None,
                )
                await prov.contract_agreement_signed(
                    agreement_id=agreement_id,
                    data_product_id=asset_id,
                    provider_id=provider_id,
                    consumer_id=settings.consumer_participant_did,
                    event_id=f"contract-agreement:{agreement_id}",
                )
            await db.commit()
        elif state in {"TERMINATED"}:
            await _update_access_request_status(db, negotiation_id, "terminated")
            prov = getattr(svc, "_prov", None)
            if prov:
                await prov.negotiation_terminated(
                    negotiation_id=negotiation_id,
                    data_product_id=access_request.asset_id if access_request else None,
                    provider_id=access_request.assigner if access_request else None,
                    consumer_id=settings.consumer_participant_did,
                    user_id=access_request.subject_id if access_request else None,
                    reason=data.get("errorDetail") or data.get("error_detail"),
                )
            await db.commit()
        return data
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC negotiation status failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC negotiation status failed: {exc.response.text}") from exc


@router.post("/transfer")
async def start_transfer(
    req: TransferStartRequest,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    subject_id = x_subject_id
    _verify_consumer_user(x_user_vc, subject_id, settings)
    duplicate = await _find_blocking_transfer(db, svc, subject_id, req.asset_id)
    if duplicate:
        raise HTTPException(
            409,
            (
                f"An active transfer for asset {req.asset_id!r} already exists for this user "
                f"(transfer_id={duplicate})."
            ),
        )
    try:
        transfer_id = await svc.transfer(
            contract_agreement_id=req.contract_agreement_id,
            counter_party_address=req.counter_party_address,
            asset_id=req.asset_id,
            connector_id=req.connector_id,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC transfer failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC transfer failed: {exc.response.text}") from exc
    db.add(ConsumerTransferORM(
        transfer_id=transfer_id,
        subject_id=subject_id,
        asset_id=req.asset_id,
        contract_agreement_id=req.contract_agreement_id,
        consumer_id=settings.consumer_participant_did,
    ))
    latest_request = await _latest_access_request(db, subject_id, req.asset_id)
    if latest_request:
        latest_request.transfer_id = transfer_id
        latest_request.contract_agreement_id = req.contract_agreement_id
        latest_request.status = "transferred"
    prov = getattr(svc, "_prov", None)
    if prov:
        await prov.transfer_started(
            transfer_id=transfer_id,
            agreement_id=req.contract_agreement_id,
            data_product_id=req.asset_id,
            provider_id=req.connector_id,
            consumer_id=settings.consumer_participant_did,
            user_id=subject_id,
        )
    await db.commit()
    return {"transfer_id": transfer_id}


@router.get("/transfers")
async def list_transfers(
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    owned_result = await db.execute(
        select(ConsumerTransferORM).where(ConsumerTransferORM.subject_id == x_subject_id)
    )
    owned = {row.transfer_id: row for row in owned_result.scalars().all()}
    if not owned:
        return []

    try:
        transfers = await svc._edc.list_transfers()
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC transfer list failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC transfer list failed: {exc.response.text}") from exc

    result = []
    for transfer in transfers:
        transfer_id = transfer.get("@id") or transfer.get("id")
        owner = owned.get(transfer_id)
        if not transfer_id or not owner:
            continue
        item = {
            **transfer,
            "transfer_id": transfer_id,
            "requested_by": owner.subject_id,
            "asset_id": transfer.get("assetId") or transfer.get("asset_id") or owner.asset_id,
            "contract_agreement_id": (
                transfer.get("contractId")
                or transfer.get("contract_agreement_id")
                or owner.contract_agreement_id
            ),
        }
        if transfer_id and transfer.get("state") == "STARTED":
            try:
                item["edr"] = (await svc.get_edr(transfer_id)).model_dump()
            except (httpx.RequestError, httpx.HTTPStatusError):
                item["edr"] = None
        result.append(item)
    return result


@router.get("/transfers/{transfer_id}")
async def get_transfer(
    transfer_id: str,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    if not await _subject_owns_transfer(db, transfer_id, x_subject_id):
        raise HTTPException(404, "Transfer not found")
    try:
        return await svc._edc.get_transfer(transfer_id)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC transfer status failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC transfer status failed: {exc.response.text}") from exc


@router.get("/edr/{transfer_id}")
async def get_edr(
    transfer_id: str,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    if not await _subject_owns_transfer(db, transfer_id, x_subject_id):
        raise HTTPException(404, "Transfer not found")
    try:
        return await svc.get_edr(transfer_id)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC EDR lookup failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC EDR lookup failed: {exc.response.text}") from exc


@router.post("/flow", response_model=FlowResult)
async def run_flow(
    req: FlowRequest,
    svc=Depends(get_consumer_service),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    try:
        return await svc.run_flow(req)
    except UnknownParticipantError as exc:
        raise HTTPException(403, "Unknown dataspace participant") from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC flow failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC flow failed: {exc.response.text}") from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


async def _subject_owns_transfer(
    db: AsyncSession,
    transfer_id: str,
    subject_id: str,
) -> bool:
    result = await db.execute(
        select(ConsumerTransferORM).where(
            ConsumerTransferORM.transfer_id == transfer_id,
            ConsumerTransferORM.subject_id == subject_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _latest_access_request(
    db: AsyncSession,
    subject_id: str,
    asset_id: str,
) -> ConsumerAccessRequestORM | None:
    result = await db.execute(
        select(ConsumerAccessRequestORM)
        .where(
            ConsumerAccessRequestORM.subject_id == subject_id,
            ConsumerAccessRequestORM.asset_id == asset_id,
        )
        .order_by(desc(ConsumerAccessRequestORM.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _update_access_request_status(
    db: AsyncSession,
    negotiation_id: str,
    status: str,
    contract_agreement_id: str | None = None,
) -> None:
    result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.negotiation_id == negotiation_id
        )
    )
    request = result.scalar_one_or_none()
    if request:
        request.status = status
        if contract_agreement_id:
            request.contract_agreement_id = contract_agreement_id


async def _access_request_for_negotiation(
    db: AsyncSession,
    negotiation_id: str,
) -> ConsumerAccessRequestORM | None:
    result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.negotiation_id == negotiation_id
        )
    )
    return result.scalar_one_or_none()


def _extract_purposes(policy: dict | None) -> list[str]:
    purposes: list[str] = []

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            left = value.get("odrl:leftOperand") or value.get("leftOperand")
            if isinstance(left, dict):
                left = left.get("@id") or left.get("id")
            if left == "odrl:purpose":
                right = value.get("odrl:rightOperand") or value.get("rightOperand")
                if isinstance(right, dict):
                    right = right.get("@id") or right.get("id")
                if isinstance(right, str) and right not in purposes:
                    purposes.append(right)
            for item in value.values():
                walk(item)

    walk(policy or {})
    return purposes


async def _agreement_ids_for_request(
    db: AsyncSession,
    request: ConsumerAccessRequestORM,
) -> list[str]:
    ids: list[str] = []
    if request.contract_agreement_id:
        ids.append(request.contract_agreement_id)

    if request.transfer_id:
        transfer_result = await db.execute(
            select(ConsumerTransferORM).where(
                ConsumerTransferORM.transfer_id == request.transfer_id,
                ConsumerTransferORM.subject_id == request.subject_id,
            )
        )
        transfer = transfer_result.scalar_one_or_none()
        if transfer and transfer.contract_agreement_id not in ids:
            ids.append(transfer.contract_agreement_id)

    return ids


async def _find_blocking_request(
    db: AsyncSession,
    svc,
    subject_id: str,
    asset_id: str,
) -> dict | None:
    transfer_id = await _find_blocking_transfer(db, svc, subject_id, asset_id)
    if transfer_id:
        return {"id": transfer_id, "status": "active-transfer"}

    result = await db.execute(
        select(ConsumerAccessRequestORM)
        .where(
            ConsumerAccessRequestORM.subject_id == subject_id,
            ConsumerAccessRequestORM.asset_id == asset_id,
            ConsumerAccessRequestORM.status.in_(
                ["negotiating", "finalized", "transferring", "transferred"]
            ),
        )
        .order_by(desc(ConsumerAccessRequestORM.created_at))
        .limit(1)
    )
    request = result.scalar_one_or_none()
    if not request:
        return None
    return {"id": request.negotiation_id or request.id, "status": request.status}


async def _find_blocking_transfer(
    db: AsyncSession,
    svc,
    subject_id: str,
    asset_id: str,
) -> str | None:
    result = await db.execute(
        select(ConsumerTransferORM)
        .where(
            ConsumerTransferORM.subject_id == subject_id,
            ConsumerTransferORM.asset_id == asset_id,
        )
        .order_by(desc(ConsumerTransferORM.created_at))
    )
    for transfer in result.scalars().all():
        try:
            state = (await svc._edc.get_transfer(transfer.transfer_id)).get("state")
        except (httpx.RequestError, httpx.HTTPStatusError):
            return transfer.transfer_id
        if state not in {"TERMINATED", "DEPROVISIONED"}:
            return transfer.transfer_id
    return None
