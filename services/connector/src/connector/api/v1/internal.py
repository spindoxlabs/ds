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
from ...dependencies import (
    get_db,
    get_notifier,
    get_participant_registry,
    get_settings_dep,
    require_internal_scope,
)
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
    request: Request,
    dataset_id: str,
    consumer_id: str,
    subject_id: Optional[str] = None,
    purpose: Optional[str] = None,
    controller_role: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings_dep),
    _claims: dict = Depends(require_internal_scope),
):
    """The single consent decision — one endpoint, three projections.

    Three callers ask the same question and read different parts of the answer:

    | Caller | Reads |
    |---|---|
    | dataset-api PEP, at query time | ``subject_ids`` — the row filter |
    | ``ConsentStatusFunction``, at negotiation | ``consent_active``/``subject_ids`` |
    | ``ConsentPendingGuard``, before parking | ``should_ask``, ``pending_request_id`` |

    They stay on one endpoint deliberately. The projections are the same query
    under different lenses, returning all of them is cheap, and *one code path
    deciding consent* is the security-relevant property — two endpoints would be
    two chances to diverge.

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
    from ...services.consent_service import check_consent_detail, get_granted_subject_ids
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

    ask = await _ask_projection(
        request,
        db,
        settings,
        dataset_id=dataset_id,
        consumer_id=consumer_id,
        subject_id=subject_id,
        purposes=purposes,
        controller_role=controller_role,
        consent_required=consent_required,
    )

    if subject_id:
        active, reason, row = await check_consent_detail(
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
            # The legal-basis evidence of the row that decided — proof of which
            # consent state authorised access, for the PEP's audit trail.
            "legal_basis": row.legal_basis if row else None,
            **ask,
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
        **ask,
    }


async def _ask_projection(
    request: Request,
    db: AsyncSession,
    settings,
    *,
    dataset_id: str,
    consumer_id: str,
    subject_id: str | None,
    purposes: list[str],
    controller_role: str | None,
    consent_required: bool | None,
) -> dict:
    """``should_ask`` and ``pending_request_id`` — the guard's half of the answer.

    ``should_ask`` answers *if consent is absent, is that a question for a
    person?*  It is deliberately independent of whether consent happens to be
    present right now, so the pending guard reads one flag instead of
    reconstructing the circle rules in Java:

    - **false** for a dataset that is not consent-gated — there is nobody to ask.
    - **false** for a party the offers already cover as a processor (§6.3). Such
      a recipient is disclosed under Art. 13(1)(e), not consented; asking anyway
      would imply a choice that does not exist and would train people to click
      through the questions that do matter.
    - **true** otherwise, including when capacity is unprovable — a redundant
      question is recoverable, a skipped one is not.

    It never leaks *who* consented: it is a boolean over the circle verdict, not
    a membership listing.  ``subject_ids`` remains the only sensitive projection
    and its exposure is unchanged.

    ``pending_request_id`` names an ask already outstanding for this tuple, so a
    re-negotiating consumer reattaches to it instead of asking the same people
    a second time.
    """
    from ...services import circle
    from ...services import consent_vocabulary as vocab
    from ...services.consent_service import find_pending_request

    pending = await find_pending_request(
        db, dataset_id, consumer_id, purpose=purposes, subject_id=subject_id
    )
    projection = {
        "should_ask": False,
        "pending_request_id": pending.id if pending else None,
    }
    if not consent_required:
        return projection

    offers = vocab.offers_covering(dataset_id, purposes, controller_role)
    covered = await circle.is_covered_processor(
        offers,
        requester_did=consumer_id,
        identity_registry_url=settings.identity_registry_url,
        token_provider=getattr(request.app.state, "ir_token_provider", None),
    )
    projection["should_ask"] = not covered
    return projection


class ConsentAskRequest(BaseModel):
    """A parked negotiation asking the connector to put a question to people."""

    negotiation_id: str
    correlation_id: str | None = None
    dataset_id: str
    consumer_id: str
    purpose: list[str] = []
    controller_role: str | None = None


@router.post("/consent/asks", status_code=200)
async def record_consent_ask(
    body: ConsentAskRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings_dep),
    notifier=Depends(get_notifier),
    _claims: dict = Depends(require_internal_scope),
):
    """Record the ask behind a parked contract negotiation (§6.4).

    Called by ``ConsentPendingGuard`` when a provider-side negotiation reaches
    ``REQUESTED`` for a consent-gated dataset and no consent covers the
    requester. The identity in ``consumer_id`` is EDC's ``counterPartyId`` — a
    DCP-verified credential presentation, not a self-asserted header, which is
    the whole reason this replaced the old cross-participant
    ``POST /consent/request``.

    **Never raises for a business answer.** The caller is a state-machine guard;
    a 4xx it has to interpret would put policy back in Java. Every outcome is a
    200 with ``asked`` and a ``reason``:

    | ``asked`` | when | the guard should |
    |---|---|---|
    | true | the question was put to at least one person | park the negotiation |
    | false, ``not_consent_gated`` | no data subject to ask | let it proceed |
    | false, ``covered_processor`` | disclosed under Art. 28, not consented (§6.3) | let it proceed |
    | false, ``no_subjects`` | nobody is enrolled in this dataset | let it proceed — and be refused |
    | false, ``unknown_dataset``/``unknown_purpose`` | the offer names something we do not have | let it proceed — and be refused |

    "Let it proceed" is not "allow": the ODRL consent constraint still evaluates
    and still denies. It only means *parking would not help*, because no human
    decision is pending that could ever unblock it.

    Idempotent by construction: a re-negotiation for the same
    ``(subject pool, dataset, purpose, consumer)`` reattaches to the outstanding
    rows instead of asking the same people twice.
    """
    from ...services import circle
    from ...services import consent_vocabulary as vocab
    from ...services.consent_service import (
        create_consent_request,
        subject_pool_for_dataset,
    )

    def refuse(reason: str, **extra) -> dict:
        return {"asked": False, "reason": reason, "request_ids": [], **extra}

    try:
        rule = vocab.resolve_dataset(body.dataset_id)
    except vocab.VocabularyError:
        return refuse("unknown_dataset")
    if not vocab.requires_consent(rule):
        return refuse("not_consent_gated")

    try:
        purposes = vocab.normalise_purposes(body.purpose)
    except vocab.VocabularyError as exc:
        return refuse("unknown_purpose", detail=str(exc))

    offers = vocab.offers_covering(body.dataset_id, purposes, body.controller_role)
    if await circle.is_covered_processor(
        offers,
        requester_did=body.consumer_id,
        identity_registry_url=settings.identity_registry_url,
        token_provider=getattr(request.app.state, "ir_token_provider", None),
    ):
        return refuse("covered_processor")

    subjects = await subject_pool_for_dataset(db, body.dataset_id)
    if not subjects:
        return refuse("no_subjects")

    offer = offers[0] if offers else None
    request_ids: list[str] = []
    for subject_id in subjects:
        consent = await create_consent_request(
            session=db,
            subject_id=subject_id,
            consumer_id=body.consumer_id,
            dataset_id=body.dataset_id,
            purpose=purposes,
            message="A data consumer has requested access; a contract "
                    "negotiation is waiting on your decision.",
            notifier=notifier,
            controller=offer.recipients.controller if offer else None,
            controller_role=(
                body.controller_role
                or (offer.recipients.controller_role if offer else None)
            ),
            offer_id=offer.id if offer else None,
            negotiation_id=body.negotiation_id,
            correlation_id=body.correlation_id,
        )
        request_ids.append(consent.id)
    await db.commit()

    return {
        "asked": True,
        "reason": "awaiting_consent",
        "request_ids": request_ids,
        "negotiation_id": body.negotiation_id,
        "correlation_id": body.correlation_id,
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
