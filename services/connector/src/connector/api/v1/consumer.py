"""Consumer routes: catalog, negotiate, transfer, EDR, flow."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from ds_auth.user_credentials import verify_user_vc_jwt
from ds_edc import EdcPollTimeout
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsumerAccessRequestORM, ConsumerTransferORM
from ...dependencies import (
    CatalogCaller,
    get_consumer_service,
    get_db,
    get_settings_dep,
    require_consumer_catalog_caller,
)
from ...registry.participants import UnknownParticipantError
from ...schemas.edc import FlowRequest, FlowResult
from ...services.agreement_service import (
    get_agreement_status,
    terminate_agreement,
    upsert_agreement,
)
from ...services.odrl_reader import extract_purposes

router = APIRouter(prefix="/consumer", tags=["consumer"])


class CatalogRequest(BaseModel):
    counter_party_address: str
    counter_party_id: str | None = None
    filters: dict | None = None


class NegotiateRequest(BaseModel):
    """A request to negotiate, and — optionally — why.

    ``declared_purpose`` and the window are the consumer's **statement of
    intent**. They are not a policy: EDC resolves the contract policy from the
    offer id against the provider's own contract definition
    (``ContractNegotiationProtocolServiceImpl``), so nothing a consumer puts in
    the request body can widen or narrow what the agreement permits. What the
    declaration does buy is accountability — an offer permitting *any of* three
    purposes otherwise leaves a permanent record saying only "one of these
    three", which cannot answer "why did this organisation ask for this data".

    It is validated against the offer's own purposes, so a declaration can only
    ever be as broad as the offer already allows. ``justification_ref`` is an
    opaque external reference (a ticket or document id), never free text about a
    person — the same contract ``evidence_ref`` carries in organisation
    onboarding.
    """

    counter_party_address: str
    offer_id: str
    asset_id: str
    assigner: str
    odrl_policy: dict | None = None
    declared_purpose: list[str] | None = None
    declared_from: datetime | None = None
    declared_until: datetime | None = None
    justification_ref: str | None = None

    @field_validator("justification_ref")
    @classmethod
    def _no_obvious_pii(cls, v: str | None) -> str | None:
        """Reject the commonest way PII reaches a request record.

        Mirrors ``AdminShareLegalBasis``: this catches an email pasted into a
        reference field, not every possible leak. The codes-and-references-only
        rule stays the caller's obligation.
        """
        if v and "@" in v:
            raise ValueError(
                "must be an opaque reference, not an email address or other identifier"
            )
        return v


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
        settings.trust_anchor_did,
        {"ConsumerUser"},
        trust_list_url=settings.trust_list_url,
        did_web_use_https=settings.did_web_use_https,
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
    caller: CatalogCaller = Depends(require_consumer_catalog_caller),
):
    """Fetch a counterparty's catalogue over DSP.

    Guarded by either mechanism — see :func:`require_consumer_catalog_caller`.
    The identity recorded against the resulting ``CatalogViewed`` is the one that
    guard verified, never a header the caller chose (rulebook `D-16`).
    """
    try:
        catalog = await svc.request_catalog(
            req.counter_party_address, req.counter_party_id
        )
        prov = getattr(svc, "_prov", None)
        if prov:
            await prov.catalog_viewed(
                provider_id=req.counter_party_id or settings.participant_did,
                consumer_id=settings.consumer_participant_did,
                # `None` for a service: the event records that the participant
                # fetched a catalogue, and there is no natural person to name.
                # Putting the service's client id in `user_id` would make an
                # automated crawl indistinguishable from a person browsing.
                user_id=caller.subject_id,
                counter_party_address=req.counter_party_address,
                dataset_count=len(catalog.get("dataset") or []),
                # Keyed on the verified actor, so two callers cannot collide on
                # one event id — and so a caller cannot pick another's key.
                event_id=f"catalog-view:{caller.actor}:{req.counter_party_address}",
            )
        return catalog
    except UnknownParticipantError as exc:
        raise HTTPException(
            403, f"Unknown dataspace participant: {req.counter_party_address}"
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC catalog request failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            502, f"EDC catalog request failed: {exc.response.text}"
        ) from exc


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
    # Before any EDC call: a refused declaration must not leave a live
    # negotiation behind that the record then fails to describe.
    declared_purpose = _validated_declaration(req)
    if (
        req.declared_from
        and req.declared_until
        and req.declared_from > req.declared_until
    ):
        raise HTTPException(422, "declared_from is after declared_until")
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
        raise HTTPException(
            403, f"Unknown dataspace participant: {req.counter_party_address}"
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"EDC negotiation failed: {exc}. Check that EDC provider/consumer containers are running.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            502, f"EDC negotiation failed: {exc.response.text}"
        ) from exc
    access_request = ConsumerAccessRequestORM(
        subject_id=x_subject_id,
        asset_id=req.asset_id,
        counter_party_address=req.counter_party_address,
        offer_id=req.offer_id,
        assigner=req.assigner,
        negotiation_id=negotiation_id,
        status="negotiating",
        declared_purpose=declared_purpose or None,
        declared_from=req.declared_from,
        declared_until=req.declared_until,
        justification_ref=req.justification_ref,
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
            # What the offer permits and what this consumer says it intends are
            # different facts, so they are different fields. `purpose` stays the
            # offer's set — existing readers keep their meaning.
            declared_purpose=declared_purpose,
            declared_from=req.declared_from,
            declared_until=req.declared_until,
            justification_ref=req.justification_ref,
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
                if (
                    negotiation_state in {"FINALIZED", "VERIFIED", "AGREED"}
                    and request.status == "negotiating"
                ):
                    request.status = "finalized"
                    changed = True
                elif negotiation_state == "TERMINATED" and request.status != "revoked":
                    request.status = "terminated"
                    changed = True
                elif negotiation_state == "REQUESTED" and request.status in {
                    "negotiating",
                    "awaiting_consent",
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
        items.append(
            {
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
                "declared_purpose": request.declared_purpose or [],
                "declared_from": request.declared_from.isoformat()
                if request.declared_from
                else None,
                "declared_until": (
                    request.declared_until.isoformat()
                    if request.declared_until
                    else None
                ),
                "justification_ref": request.justification_ref,
                "created_at": request.created_at.isoformat()
                if request.created_at
                else None,
                "updated_at": request.updated_at.isoformat()
                if request.updated_at
                else None,
                "can_revoke": request.status
                in {
                    "negotiating",
                    "awaiting_consent",
                    "finalized",
                    "transferring",
                    "transferred",
                },
            }
        )
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
            raise HTTPException(
                502, f"EDC transfer revoke failed: {exc.response.text}"
            ) from exc
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
            asset_id = data.get("assetId") or (
                access_request.asset_id if access_request else ""
            )
            provider_id = data.get("counterPartyId") or (
                access_request.assigner if access_request else "provider"
            )
            await upsert_agreement(
                session=db,
                agreement_id=agreement_id,
                asset_id=asset_id,
                consumer_id=settings.consumer_participant_did,
                provider_id=provider_id,
                policy_snapshot=data.get("policy") or {},
                agreed_at=datetime.now(UTC),
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
        raise HTTPException(
            502, f"EDC negotiation status failed: {exc.response.text}"
        ) from exc


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
    db.add(
        ConsumerTransferORM(
            transfer_id=transfer_id,
            subject_id=subject_id,
            asset_id=req.asset_id,
            contract_agreement_id=req.contract_agreement_id,
            consumer_id=settings.consumer_participant_did,
        )
    )
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
        select(ConsumerTransferORM).where(
            ConsumerTransferORM.subject_id == x_subject_id
        )
    )
    owned = {row.transfer_id: row for row in owned_result.scalars().all()}
    if not owned:
        return []

    try:
        transfers = await svc._edc.list_transfers()
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC transfer list failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            502, f"EDC transfer list failed: {exc.response.text}"
        ) from exc

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
            "asset_id": transfer.get("assetId")
            or transfer.get("asset_id")
            or owner.asset_id,
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
        raise HTTPException(
            502, f"EDC transfer status failed: {exc.response.text}"
        ) from exc


@router.get("/edr/{transfer_id}")
async def get_edr(
    transfer_id: str,
    svc=Depends(get_consumer_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
):
    """The EDR, plus what the client must send with it.

    The endpoint and token come from EDC. The three `Edc-*` values a data-plane
    query carries — agreement, transfer, purpose — are **this connector's**
    records, and they are returned here so a client forwards them rather than
    inventing them. In particular `purpose` is the purpose declared when access
    was requested: a client that made a declaration then queries under it, which
    is what makes the declaration mean something at query time instead of only
    in an audit record.
    """
    _verify_consumer_user(x_user_vc, x_subject_id, settings)
    if not await _subject_owns_transfer(db, transfer_id, x_subject_id):
        raise HTTPException(404, "Transfer not found")
    try:
        edr = await svc.get_edr(transfer_id)
    except httpx.RequestError as exc:
        raise HTTPException(502, f"EDC EDR lookup failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"EDC EDR lookup failed: {exc.response.text}") from exc

    result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.transfer_id == transfer_id
        )
    )
    request = result.scalar_one_or_none()
    # `get_edr` returns an `EdrResponse`, not a dict — an `isinstance(edr, dict)`
    # guard here silently skipped the whole block and the client got an EDR with
    # nothing to put in its headers.
    payload = edr.model_dump() if hasattr(edr, "model_dump") else dict(edr)
    if request is not None:
        # The **shared** DSP agreement id, resolved from our own record: the
        # local id EDC gave us means nothing to the provider (migration 0008).
        shared = await get_agreement_status(db, request.contract_agreement_id or "")
        payload = {
            **payload,
            "agreement_id": (shared or {}).get("dsp_agreement_id")
            or request.contract_agreement_id,
            "transfer_id": transfer_id,
            "purpose": request.declared_purpose or [],
        }
    return payload


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
    except EdcPollTimeout as exc:
        # Rulebook, data exchange X-10: a timeout is reported as a timeout. It
        # used to arrive as `state="TIMEOUT"` and leave here as a 502, which
        # says the counterparty answered badly — the one thing that did not
        # happen. 504 says nobody answered in time, and the message names the
        # last state the exchange was actually seen in.
        raise HTTPException(504, str(exc)) from exc
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


# One reader for both sides of the exchange — see `services/odrl_reader.py`.
_extract_purposes = extract_purposes


def _validated_declaration(req: NegotiateRequest) -> list[str]:
    """The declared purposes, checked against the offer, as taxonomy slugs.

    Two rules, both fail-closed:

    - A declared purpose must be in the taxonomy. An unrecognised string would
      make the record unqueryable and unverifiable — worse than no record.
    - A declared purpose must be one the **offer** permits (``odrl:isA`` over
      the local ``broader`` chain, so declaring a narrower purpose than the
      offer names is fine and declaring a broader one is not). Without the
      offer's policy there is nothing to check against, so a declaration
      submitted without ``odrl_policy`` is refused rather than recorded
      unverified: an unverifiable claim in an audit record reads as a verified
      one later.
    """
    from ...services import consent_vocabulary as vocab

    if not req.declared_purpose:
        return []
    try:
        declared = vocab.normalise_purposes(req.declared_purpose)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    offer_purposes = _extract_purposes(req.odrl_policy)
    if not offer_purposes:
        raise HTTPException(
            422,
            "declared_purpose requires odrl_policy — the declaration is checked "
            "against the purposes the offer permits, and this offer carries none "
            "that can be read.",
        )
    try:
        permitted = vocab.normalise_purposes(offer_purposes)
    except vocab.VocabularyError as exc:
        raise HTTPException(
            422, f"Offer purposes are not in the taxonomy: {exc}"
        ) from exc

    for purpose in declared:
        if not vocab.purpose_covered([purpose], permitted):
            raise HTTPException(
                422,
                f"Declared purpose '{purpose}' is not permitted by this offer "
                f"(offer permits: {', '.join(permitted)}).",
            )
    return declared


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
