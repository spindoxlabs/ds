"""Internal API — used by Dataset API PEP for EDR validation and consent checks."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import httpx
from ds.governance import (
    ALLOW,
    DENY,
    DIRECT_USER_MATCH,
    DataplaneDecision,
    DataplaneRowFilter,
    subject_column,
)
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
    require_registry_invalidate,
)
from ...registry.participants import HttpParticipantRegistry, ParticipantRegistry
from ...services.agreement_service import get_agreement_status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class EdcUnreachable(RuntimeError):
    """The EDC could not be asked — as distinct from having answered "no".

    Rulebook `CR-4`: an undecidable constraint is a denial, never a permission.
    The failure mode this type exists to prevent is subtler than a wrong verdict:
    both helpers below used to answer ``None`` for *"no such agreement"* and for
    *"the connection was refused"*, so ``GET /internal/agreements/{id}/status``
    reported a definite 404 for a question it had not managed to ask. A caller
    cannot fail closed on an answer that does not admit it is missing.
    """


class DataPlaneAuthorizeRequest(BaseModel):
    """What a data plane knows about a request it has already authenticated.

    ``consumer_did`` comes from the **verified** EDR token's ``aud`` — never from
    a header. ``agreement_id`` and ``purpose`` come from headers and are
    self-asserted, which is safe only because this endpoint refuses an agreement
    that does not belong to ``consumer_did`` and a purpose the agreed policy does
    not permit. A caller can therefore lie only within what it already holds.
    """

    consumer_did: str
    agreement_id: str
    dataset_ids: list[str]
    purpose: list[str] = []
    transfer_id: str | None = None


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
    try:
        edc_status = await _check_edc_agreement(agreement_id)
    except EdcUnreachable as exc:
        # **Not a 404.** "We could not ask" and "there is no such agreement" are
        # different answers, and only one of them is safe to cache as a negative.
        raise HTTPException(503, f"Cannot determine agreement status: {exc}") from exc
    if edc_status is not None:
        return edc_status
    raise HTTPException(404, f"Agreement {agreement_id!r} not found")


def _edc_management_url(settings) -> str:
    """The management API of *this* connector's own EDC.

    The internal router mounts in both roles (`main.py`), so reading the provider
    URL unconditionally pointed a consumer-role connector at the other
    participant's EDC — which, when it happened to be reachable, answered about
    the wrong runtime's agreements.
    """
    url = (
        settings.edc_rec_management_url
        if settings.role == "provider"
        else settings.edc_third_party_management_url
    )
    return url.rstrip("/")


async def _check_edc_agreement(agreement_id: str) -> dict | None:
    """Check EDC management API for a contract agreement (role-local fallback).

    ``None`` means the EDC answered and holds no such agreement. Anything that
    stops us getting an answer raises :class:`EdcUnreachable`.
    """
    settings = get_settings()
    edc_url = _edc_management_url(settings)
    headers = {"x-api-key": settings.edc_api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{edc_url}/v3/contractagreements/{agreement_id}", headers=headers
            )
    except httpx.HTTPError as exc:
        raise EdcUnreachable(f"EDC management API unreachable: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise EdcUnreachable(
            f"EDC management API answered {resp.status_code} for agreement "
            f"{agreement_id!r}"
        )
    return {"active": True, "agreement_id": agreement_id, "source": "edc"}


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
        select(ConsumerTransferORM).where(
            ConsumerTransferORM.transfer_id == transfer_id
        )
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        try:
            active = await _check_edc_transfer(transfer_id, agreement_id)
        except EdcUnreachable as exc:
            # Deny, as `CR-4` requires — but say which denial this is. Reporting
            # `transfer_not_found` for an unreachable EDC states a fact we do not
            # have, and it is the fact an operator would use to conclude the
            # consumer never started a transfer.
            log.warning("Transfer status for %s undecidable: %s", transfer_id, exc)
            return {"active": False, "reason": "edc_unreachable"}
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


async def _check_edc_transfer(
    transfer_id: str, agreement_id: str | None
) -> dict | None:
    """Check EDC management API for a transfer by correlationId (role-local lookup).

    ``None`` means the EDC answered and knows no such transfer. Anything that
    stops us getting an answer raises :class:`EdcUnreachable`.
    """
    settings = get_settings()
    edc_url = _edc_management_url(settings)
    headers = {"x-api-key": settings.edc_api_key, "Content-Type": "application/json"}
    query = {
        "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
        "@type": "QuerySpec",
        "filterExpression": [
            {
                "operandLeft": "correlationId",
                "operator": "=",
                "operandRight": transfer_id,
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{edc_url}/v3/transferprocesses/request", json=query, headers=headers
            )
    except httpx.HTTPError as exc:
        raise EdcUnreachable(f"EDC management API unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise EdcUnreachable(
            f"EDC management API answered {resp.status_code} for transfer "
            f"{transfer_id!r}"
        )
    if not resp.text:
        return None
    try:
        results = resp.json()
    except ValueError as exc:
        # A body we cannot parse is not an empty result set.
        raise EdcUnreachable(f"EDC management API returned non-JSON: {exc}") from exc
    if not results:
        return None
    tp = results[0]
    state = tp.get("edc:state", tp.get("state", ""))
    active = state in ("STARTED", "COMPLETED")
    return {
        "active": active,
        "transfer_id": transfer_id,
        "agreement_id": agreement_id,
        "edc_state": state,
    }


@router.post("/dataplane/authorize", response_model=DataplaneDecision)
async def dataplane_authorize(
    body: DataPlaneAuthorizeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings_dep),
    _claims: dict = Depends(require_internal_scope),
):
    """May this data-plane request return rows, and which ones?

    ds is the control plane and decides; the data plane enforces. The caller
    supplies what it has authenticated and what its client asserted; every fact
    that decides the outcome is resolved here, from this connector's own records.

    Five gates, per dataset, all fail-closed:

    1. the agreement exists in **our** records — an EDC-side existence check
       cannot answer the binding in (2), so an unknown agreement is refused
       rather than looked up;
    2. it belongs to ``consumer_did``. **This is the check that makes a
       self-asserted header safe**: without it, naming someone else's agreement
       id would read their data;
    3. it covers *this* dataset — otherwise an agreement over an open dataset
       would unlock a consent-gated one;
    4. the transfer, when the caller names one, is still usable;
    5. the purpose is one the agreed policy permits, and consent exists for it.

    The verdict is **per dataset** because one SQL statement can touch several,
    and the overall answer is the strictest of them: a join must not return rows
    the strictest of its inputs would refuse.

    The answer's shape is `ds.governance.DataplaneDecision` — declared in the
    shared library because this route has readers it does not ship with. Do not
    add a key here without adding it there; `response_model` will refuse it,
    which is the point.
    """
    from ...services import consent_vocabulary as vocab
    from ...services.odrl_reader import extract_purposes

    ttl = {"ttl_seconds": settings.dataplane_decision_ttl}

    def refuse(reason: str, **extra):
        """One deny shape. The data plane returns no rows for any of them.

        Deliberately the *same* key set as the allow below — a PEP should not
        have to branch on the envelope to know which fields it may read.
        """
        return {
            "decision": DENY,
            "reason": reason,
            "agreement_id": body.agreement_id,
            "transfer_id": body.transfer_id,
            "purpose": [],
            "datasets": [
                {
                    "dataset_id": d,
                    "decision": DENY,
                    "reason": reason,
                    "row_filter": None,
                }
                for d in body.dataset_ids
            ],
            "cache": ttl,
            **extra,
        }

    agreement = await get_agreement_status(db, body.agreement_id)
    if agreement is None:
        return refuse("agreement_unknown")
    if not agreement.get("active"):
        return refuse("agreement_inactive")
    if (agreement.get("consumer_id") or "") != body.consumer_did:
        # Deliberately the same shape as every other refusal, and deliberately
        # not "which consumer does own it" — a probe must not learn that.
        return refuse("not_your_agreement")

    if body.transfer_id:
        # Reuse the route the PEP already calls, so "is this transfer usable"
        # has one answer and not two that can drift.
        transfer = await transfer_status(
            body.transfer_id, body.agreement_id, db, _claims
        )
        if not transfer.get("active"):
            return refuse("transfer_inactive", detail=transfer.get("reason"))

    agreed_purposes: list[str] = []
    try:
        agreed_purposes = vocab.normalise_purposes(
            extract_purposes(agreement.get("policy_snapshot"))
        )
    except vocab.VocabularyError:
        # A policy naming a purpose we cannot resolve is not a reason to serve
        # data: it is a reason to stop and look.
        return refuse("agreed_policy_unreadable")

    try:
        requested = vocab.normalise_purposes(body.purpose)
    except vocab.VocabularyError as exc:
        return refuse("purpose_unknown", detail=str(exc))

    if requested and agreed_purposes:
        for purpose in requested:
            if not vocab.purpose_covered([purpose], agreed_purposes):
                return refuse("purpose_not_agreed", detail=purpose)

    datasets = []
    for dataset_id in body.dataset_ids:
        datasets.append(
            await _authorize_dataset(
                db,
                dataset_id=dataset_id,
                agreement=agreement,
                consumer_did=body.consumer_did,
                purposes=requested,
                settings=settings,
                token_provider=getattr(request.app.state, "ir_token_provider", None),
            )
        )

    denied = next((d for d in datasets if d["decision"] == DENY), None)
    return {
        "decision": DENY if denied else ALLOW,
        "reason": denied["reason"] if denied else None,
        "agreement_id": body.agreement_id,
        "transfer_id": body.transfer_id,
        "purpose": requested,
        "datasets": datasets,
        "cache": ttl,
    }


async def _authorize_dataset(
    db: AsyncSession,
    *,
    dataset_id: str,
    agreement: dict,
    consumer_did: str,
    purposes: list[str],
    settings,
    token_provider=None,
) -> dict:
    """One dataset's verdict, with the row filter that goes with it."""
    from ...services import consent_vocabulary as vocab
    from ...services.consent_service import get_granted_subject_ids
    from ...services.subject_identities import resolve_usernames

    def verdict(decision: str, reason: str | None = None, row_filter=None) -> dict:
        return {
            "dataset_id": dataset_id,
            "decision": decision,
            "reason": reason,
            "row_filter": row_filter,
        }

    if dataset_id != agreement.get("asset_id"):
        return verdict(DENY, "dataset_not_in_agreement")

    try:
        rule = vocab.resolve_dataset(dataset_id)
    except vocab.VocabularyError:
        return verdict(DENY, "dataset_unknown")

    gate = vocab.consent_gate(rule)
    # **Which declaration gated it, at the point it is used.** The verdict's
    # `reason` is a token a PEP matches on and cannot carry this; without the log
    # line the answer is invisible here and unrecoverable afterwards, so a
    # recorded *deny, no consent* never said whether the dataset was gated by a
    # producer's explicit `consent_required` or by a `row_filters` block added for
    # an unrelated reason. Four signals are ORed and a dataset's protection can
    # rest on exactly one of them —
    # https://github.com/spindoxlabs/ds/issues/21.
    log.info(
        "dataplane authorize: %s is %s",
        dataset_id,
        gate.reason,
        extra={
            "dataset_id": dataset_id,
            "consent_gated": gate.gated,
            "consent_signals": list(gate.signals),
        },
    )

    if not gate:
        # No data subject behind these rows, so nothing to filter on. The
        # agreement gates it and the agreement said yes.
        return verdict(ALLOW)

    if not purposes:
        # The same rule `/internal/consent/check` applies: no stated reason, no
        # rows. A consent-gated dataset cannot be read "just because".
        return verdict(DENY, "purpose_required")

    subject_ids = await get_granted_subject_ids(
        db, dataset_id, consumer_did, purpose=purposes, consent_required=True
    )
    if not subject_ids:
        return verdict(DENY, "no_consent")

    spec = _row_filter_spec(rule)
    if spec is None:
        # Consent is required but governance names no row filter, so nothing can
        # be applied and every row would leave. Refuse and let the
        # misconfiguration surface.
        return verdict(DENY, "no_row_filter")

    # The data plane filters on **its own** identifiers, not on DIDs. For
    # `rec_registry` the column holds device ids resolved from a *member*, so
    # handing over `subject_ids` would produce a predicate that matches nothing —
    # or, worse, matches by coincidence. Translate to the username the receiving
    # system keys on, and let its handler do the rest.
    usernames = await resolve_usernames(
        subject_ids, settings.identity_registry_url, token_provider
    )
    principals = [usernames[did] for did in subject_ids if did in usernames]
    if not principals:
        # Consent exists but nobody could be named to the system holding the
        # data. Denying is the only honest answer: an empty principal set with
        # an allow would be read as "filter to nothing", and a missing filter as
        # "no filter".
        return verdict(DENY, "subjects_unresolvable")

    return verdict(
        ALLOW,
        row_filter=DataplaneRowFilter(
            handler=spec["handler"],
            args=spec["args"],
            # Registry-native identifiers. Never DIDs: a DID is derived from an
            # unsalted email hash, so it is re-identifiable by anyone who later
            # holds the payload.
            principals=principals,
        ),
    )


def _row_filter_spec(rule) -> dict | None:
    """The row filter as governance declares it — handler and args.

    Returned whole rather than reduced to a column, because the handler is what
    knows how a person maps to values in it. `rec_registry` resolves a member to
    devices; `direct_user_match` matches the subject directly. A decision that
    shipped only a column would have to assume one of them.
    """
    for row_filter in getattr(rule, "row_filters", None) or []:
        args = getattr(row_filter, "args", None)
        if isinstance(args, dict):
            args_dict = dict(args)
        elif args is not None:
            args_dict = args.model_dump() if hasattr(args, "model_dump") else vars(args)
        else:
            args_dict = {}
        handler = getattr(row_filter, "handler", None)
        if handler:
            return {"handler": str(handler), "args": args_dict}

    # Legacy `user_filter_column` — the spelling the canonical schema does not
    # define. Migrated to the same handler the real dataset-api migrates it to,
    # so both sides agree on what it means.
    column = subject_column(rule)
    if column:
        return {"handler": DIRECT_USER_MATCH, "args": {"column": column}}
    return None


@router.get("/consent/check")
async def consent_check(
    request: Request,
    dataset_id: str,
    consumer_id: str,
    subject_id: str | None = None,
    purpose: str | None = None,
    controller_role: str | None = None,
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
    - Without ``subject_id``: returns all granted subject IDs (used by the
      Dataset API PEP
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
    from ...services import consent_vocabulary as vocab
    from ...services.consent_service import (
        check_consent_detail,
        get_granted_subject_ids,
    )

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
    | true | the question was put to at least one person | park |
    | false, ``not_consent_gated`` | no data subject to ask | proceed |
    | false, ``covered_processor`` | Art. 28 disclosure, not consent (§6.3) | proceed |
    | false, ``no_subjects`` | nobody is enrolled in this dataset | proceed† |
    | false, ``unknown_dataset`` | the offer names a dataset we do not have | proceed† |
    | false, ``unknown_purpose`` | the offer names a purpose we do not have | proceed† |

    † and then be refused. "Park" is park the negotiation; "proceed" is let it
    proceed.

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


@router.post("/registry/invalidate", status_code=200)
async def invalidate_participant_registry(
    request: Request,
    registry: ParticipantRegistry = Depends(get_participant_registry),
    _claims: dict = Depends(require_registry_invalidate),
):
    """Forget the cached participant list.

    The identity-registry calls this when it promotes, suspends or revokes a
    participant. The connector caches that list for
    `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL` because DSP-time membership
    checks run per negotiation and cannot afford a round trip each — but a
    change the operator just made should not wait out a timer.

    Idempotent, and a no-op for the YAML-seeded registry, which has no cache to
    drop. Never an error: a caller that cannot invalidate must not fail the
    operation that prompted it — the cache expires on its own, and a promote
    rolled back because a cache hint failed would be a far worse outcome than a
    minute of staleness.
    """
    invalidate = getattr(registry, "invalidate", None)
    if invalidate is None:
        return {"invalidated": False, "reason": "registry has no cache"}
    invalidate()
    log.info("Participant registry cache invalidated")
    return {"invalidated": True}


@router.get("/edr-jwks")
async def edr_jwks(
    _claims: dict = Depends(require_internal_scope),
):
    """The public key EDR tokens are signed with.

    A data plane in this topology is the EDR endpoint itself — upstream removed
    the proxy that used to verify the token before the request arrived — so it
    has to verify the signature, and for that it needs this key.

    It is read from the **same vault seed EDC signs with**
    (`edc.transfer.proxy.token.signer.privatekey.alias`), with the private
    component stripped. Earlier this route proxied EDC's `/v3/jwks`, which does
    not exist at 0.16 — every fetch was a 404 dressed as a 502, and nothing
    noticed because nothing consumed it.

    Serving it from the vault rather than a second copy of the key is what keeps
    rotation honest: change the seed and this answer changes with it.
    """
    settings = get_settings()
    jwk = _edr_public_jwk(settings)
    if jwk is None:
        raise HTTPException(
            503,
            "No EDR verification key configured — set CONNECTOR_EDC_VAULT_FILE "
            "and CONNECTOR_EDR_SIGNER_ALIAS to the vault seed EDC signs with.",
        )
    return {"keys": [jwk]}


@lru_cache(maxsize=4)
def _edr_public_jwk_cached(vault_file: str, alias: str) -> dict | None:
    path = Path(vault_file)
    if not path.exists():
        log.warning("EDR vault seed not found: %s", path)
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() != alias:
            continue
        try:
            jwk = json.loads(value.strip())
        except json.JSONDecodeError:
            log.warning("Vault entry %s is not a JWK", alias)
            return None
        # Public components only. `d` is the private scalar and must never
        # leave this process, grant or no grant.
        public = {
            k: v for k, v in jwk.items() if k not in {"d", "p", "q", "dp", "dq", "qi"}
        }
        # **`kid` is the vault alias, not whatever the JWK claims.** EDC stamps
        # the alias it signed with into the token header
        # (`participant-private-key`), while the seeded JWK carries its own
        # (`edr-rec-key-1`). Publishing the JWK's own kid made every
        # kid-indexed lookup miss, so a verifier had to try every key and hope.
        # Publishing the alias is what makes `kid` mean what JWKS says it means.
        public["kid"] = alias
        return public
    log.warning("Alias %s not present in %s", alias, path)
    return None


def _edr_public_jwk(settings) -> dict | None:
    if not settings.edc_vault_file:
        return None
    return _edr_public_jwk_cached(settings.edc_vault_file, settings.edr_signer_alias)
