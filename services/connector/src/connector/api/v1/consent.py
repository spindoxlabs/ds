"""Consent registry API — subject sovereignty endpoints."""
from __future__ import annotations

import inspect
import logging
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsentRequestORM
from ...dependencies import (
    get_db,
    get_notifier,
    get_participant_registry,
    get_prov,
    get_settings_dep,
    require_consent_provision,
    require_consent_read,
    require_internal_scope,
    require_provider_read,
)
from ...notifications.base import ConsentNotifier
from ...services import circle, consent_service
from ...services import consent_vocabulary as vocab
from ...services.membership_check import check_subject_membership, resolve_dataset_owner
from ...services.prov_bridge import ProvBridge
from ...services.user_credentials import verify_user_vc_jwt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/consent", tags=["consent"])


async def _emit_consent_events(
    prov: ProvBridge | None,
    consents: list[ConsentRequestORM],
    *,
    reason: str | None = None,
) -> None:
    """Emit a provenance event per settled consent row, after the DB commits.

    Follows the ``access_revoked`` pattern: provenance is a downstream,
    non-fatal side effect emitted from the API layer once the transaction has
    committed, never inside it — an event must not be recorded for a write that
    then rolls back.  The row's final status decides the event; event ids are
    deterministic so an idempotent re-run (e.g. a repeated admin provision) is
    deduplicated by the provenance store rather than double-counted.
    """
    if prov is None:
        return
    for consent in consents:
        if consent.status == "granted":
            await prov.consent_granted(
                subject_id=consent.subject_id,
                dataset_id=consent.dataset_id,
                consumer_id=consent.consumer_id,
                offer_id=consent.offer_id,
                purpose=list(consent.purpose or []),
                controller=consent.controller,
                controller_role=consent.controller_role,
                legal_basis=consent.legal_basis,
                event_id=f"consent-granted:{consent.id}",
            )
        elif consent.status == "revoked":
            await prov.consent_revoked(
                subject_id=consent.subject_id,
                dataset_id=consent.dataset_id,
                consumer_id=consent.consumer_id,
                offer_id=consent.offer_id,
                purpose=list(consent.purpose or []),
                controller=consent.controller,
                controller_role=consent.controller_role,
                reason=reason or consent.revocation_reason,
                event_id=f"consent-revoked:{consent.id}",
            )


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ConsentRequestCreate(BaseModel):
    consumer_id: str
    dataset_id: str
    subject_ids: list[str]
    purpose: list[str] = []
    message: str | None = None
    notification_url: str | None = None
    # Who is asking, and in what capacity. `consumer_id` alone cannot answer
    # that: it names a connector, not the controller deciding the purpose.
    controller: str | None = None
    controller_role: str | None = None
    offer_id: str | None = None


class ConsentResponse(BaseModel):
    id: str
    subject_id: str
    consumer_id: str
    dataset_id: str
    purpose: list[str] = []
    controller: str | None = None
    controller_role: str | None = None
    offer_id: str | None = None
    legal_basis: dict | None = None
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
    dataset_id: str | None = None
    consumer_id: str | None = None
    enabled: bool
    purpose: list[str] = []
    # Preferred form: name the offer, not a dataset. The connector expands it
    # into per-dataset rows, so the caller cannot drift from the copy the
    # person actually read.
    offer_id: str | None = None


class AdminShareLegalBasis(BaseModel):
    """Evidence a service records when provisioning consent on a subject's behalf.

    Codes, versions and hashes only — never a name, email, CF or POD. The
    connector supplies ``offer_id``, ``controller``, ``controller_role`` and
    ``user_visible_hash`` itself from the resolved offer, so the caller cannot
    drift from what the person read; anything it sends for those is ignored.
    """

    source: str | None = None
    rec_slug: str | None = None
    basis_iri: str | None = None
    consent_text_version: str | None = None
    locale: str | None = None
    rendered_text_sha256: str | None = None
    accepted_at: str | None = None
    submission_ref: str | None = None


class AdminShareRequest(BaseModel):
    subject_id: str
    offer_id: str
    enabled: bool
    legal_basis: AdminShareLegalBasis | None = None


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
        expected_linked_participant=settings.participant_did,
        credential_status_path=settings.credential_status_path,
        credential_status_url=settings.credential_status_url,
        insecure_dev=settings.vc_insecure_dev,
    )


# ── Provider-local request seeding ────────────────────────────────────────────

@router.post("/request", status_code=201)
async def create_consent_request(
    body: ConsentRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
    registry=Depends(get_participant_registry),
    _claims: dict = Depends(require_consent_provision),
):
    """Seed consent requests for a set of data subjects, **provider-locally**.

    This is an operator/portal tool, not the path a data consumer takes.

    It used to be cross-participant: a consumer's user credential, presented in
    ``X-User-VC``, raised a request on the provider connector. That never worked
    and could not be made to work well. ``_verify_user`` required the credential
    to name *this* participant, so a real consumer got 403; the same call against
    the consumer's own connector returned 201 and wrote a row on the wrong side
    of the dataspace, where ``/internal/consent/check`` — which runs against the
    provider — would never read it. And nothing bound ``consumer_id`` to the
    caller, so a credential could raise a request naming any consumer at all.

    Both were symptoms of one thing: a cross-participant request channel,
    authenticated by a header, running parallel to the one DSP already provides.
    A consumer now simply negotiates. ``ConsentPendingGuard`` parks the
    negotiation, and the requester's identity comes from EDC's DCP-verified
    ``counterPartyId`` rather than from anything the requester asserts about
    itself.

    What remains is the case that was always legitimate: an operator or the
    portal recording an ask on this connector, where the check reads. It
    authenticates as a service or an administrator — ``connector.consent.provision``,
    the same permission the onboarding wizard uses for standing shares — because
    the caller is acting on the *provider's* behalf, not presenting a consumer's
    credential.

    ``consumer_id`` is still validated against the participant registry: naming a
    party the dataspace does not know would put a promise in front of a person
    about a recipient nobody can identify.
    """
    await _require_known_participant(registry, body.consumer_id, settings)

    if body.notification_url:
        allowed_raw = settings.webhook_allowed_hosts.strip()
        allowed = {h.strip().lower() for h in allowed_raw.split(",") if h.strip()} if allowed_raw else set()
        parsed = urlparse(body.notification_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("https", "http") or not host:
            raise HTTPException(400, "notification_url must be an HTTP(S) URL")
        if not allowed or host not in allowed:
            raise HTTPException(
                400,
                f"notification_url host '{host}' is not in the allowed hosts list",
            )

    owner_alias = resolve_dataset_owner(
        settings.governance_yaml_path,
        body.dataset_id,
        overlay_name=settings.governance_overlay_name,
    )

    if owner_alias and settings.identity_registry_url:
        for subject_id in body.subject_ids:
            subject_did = subject_id
            if not subject_did.startswith("did:"):
                users_domain = settings.trust_anchor_did.replace("did:web:", "").replace("trust-anchor.", "users.")
                subject_did = f"did:web:{users_domain}:{subject_id}"

            is_member = await check_subject_membership(
                settings.identity_registry_url,
                user_did=subject_did,
                organization_alias=owner_alias,
                token_provider=request.app.state.ir_token_provider,
            )
            if not is_member:
                raise HTTPException(
                    status_code=403,
                    detail=f"Subject '{subject_id}' is not a member of dataset owner organization '{owner_alias}'",
                )

    await _reject_if_already_covered(request, body, settings)

    request_ids = []
    try:
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
                    controller=body.controller,
                    controller_role=body.controller_role,
                    offer_id=body.offer_id,
                )
                request_ids.append(consent.id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"request_ids": request_ids, "status": "pending"}


async def _require_known_participant(registry, consumer_id: str, settings: Settings) -> None:
    """Refuse a request naming a party the dataspace does not know.

    Option B's surviving half. The cross-participant channel is gone, so this no
    longer has to stand in for authenticating the requester — but a consent
    request still names a recipient to a person, and that recipient has to be
    someone the dataspace can identify. ``allow_unknown_participants`` keeps the
    escape hatch a dev setup with no registry needs.
    """
    if settings.allow_unknown_participants:
        return
    try:
        participant = registry.get_by_id(consumer_id)
        if inspect.isawaitable(participant):
            participant = await participant
    except Exception as exc:  # registry unreachable
        raise HTTPException(
            503, f"Participant registry unavailable, cannot validate '{consumer_id}'"
        ) from exc
    if participant is None:
        raise HTTPException(
            422,
            f"Consumer '{consumer_id}' is not a registered participant — a consent "
            "request must name a recipient the dataspace can identify",
        )


async def _reject_if_already_covered(
    request: Request,
    body: ConsentRequestCreate,
    settings: Settings,
) -> None:
    """Refuse a request from a party the offer already covers as a processor.

    A processor of the offer's controller acts on its instructions under a DPA;
    the controller has not changed and neither has the processing operation.
    Art. 13(1)(e) requires *disclosing* such a recipient, and disclosure is not
    consent — asking anyway would imply a choice that does not exist and would
    train people to click through the questions that do matter.
    """
    if not body.offer_id:
        return
    try:
        offer = vocab.resolve_offer(body.offer_id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    verdict = await circle.evaluate(
        offer,
        requester_did=body.consumer_id,
        identity_registry_url=settings.identity_registry_url,
        token_provider=getattr(request.app.state, "ir_token_provider", None),
    )
    if verdict.covered_processor:
        raise HTTPException(
            409,
            f"Consumer '{body.consumer_id}' is already covered by offer "
            f"'{offer.id}' as a processor of '{offer.recipients.controller}' — "
            "this recipient must be disclosed and notified, not asked for consent",
        )


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
    # The `subject_id` query parameter is caller-supplied; without this check any
    # authenticated holder could enumerate another subject's consent decisions.
    if subject_id != x_subject_id:
        raise HTTPException(
            403, "Cannot read consent status for another subject"
        )
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
        "legal_basis": latest.legal_basis,
    }


@router.get("/pending")
async def get_pending_consent(
    correlation_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_consent_read),
):
    """Is this negotiation waiting on a consent decision, and since when? (§6.6)

    ``REQUESTED`` is ambiguous on the wire. DSP has no state for "waiting on a
    human", so "the provider has not looked yet" and "waiting on a person,
    possibly for weeks" render identically to the consumer — precisely the
    distinction that matters when deciding whether to wait or to give up. This
    answers it.

    It is **not** the rejected relay option. That one carried an identity DSP
    already carries; this carries information DSP does not model at all.
    Constraints that keep it from becoming a back channel:

    - **Off the DSP path.** Not a DSP message, not a precondition of any
      negotiation transition. If it is unavailable the negotiation is
      unaffected and the consumer falls back to showing ``REQUESTED``.
    - **Status only, keyed by ``correlationId``** — the counterparty's own id
      for the negotiation, so a caller can only ask about a negotiation it is
      party to. It answers *whether* a decision is outstanding and *since when*.
      It must never expose who the subjects are, how many there are, or what
      any of them decided: that is the data subject's business, not the
      counterparty's. The response below is deliberately the whole story.

    > **Known limitation.** The perimeter is the unguessable ``correlationId``
    > plus the ``connector.consent.read`` permission. Scoping to *the* caller's
    > own negotiations would need a cross-participant identity, and this
    > platform has exactly one — DCP — which is reachable only inside a DSP
    > exchange. Until a participant-scoped credential exists off that path, the
    > narrowness of the projection is what bounds the disclosure, rather than
    > the authentication.
    """
    consents = await consent_service.list_by_correlation(db, correlation_id)
    if not consents:
        return {
            "correlation_id": correlation_id,
            "awaiting_consent": False,
            "status": "unknown",
        }

    statuses = {c.status for c in consents}
    if "pending" in statuses:
        state = "awaiting_consent"
    elif "granted" in statuses:
        state = "granted"
    elif statuses == {"expired"}:
        state = "expired"
    else:
        state = "refused"

    requested_at = min(
        (c.requested_at for c in consents if c.requested_at), default=None
    )
    return {
        "correlation_id": correlation_id,
        "awaiting_consent": state == "awaiting_consent",
        "status": state,
        "since": requested_at.isoformat() if requested_at else None,
    }


@router.get("/asks")
async def list_consent_asks(
    negotiation_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_provider_read),
):
    """The operator/portal view: which asks are holding up which negotiation.

    Provider-local, over this connector's own table — no protocol involvement.
    ``GET /consent/my`` already shows a subject their own pending requests; what
    was missing is the other direction, the one an operator needs when someone
    asks why a consumer's request has been sitting there for a week.

    Unlike ``GET /consent/pending`` this *does* name subjects: an operator of the
    provider is looking at their own participant's consent records, which is the
    same data ``/internal/consent/check`` already returns to the PEP. The
    counterparty is the party that must not see it.
    """
    consents = await consent_service.list_asks(
        db, negotiation_id=negotiation_id, status=status
    )
    return [
        {
            **ConsentResponse.model_validate(consent).model_dump(),
            "negotiation_id": consent.negotiation_id,
            "correlation_id": consent.correlation_id,
            "negotiation_closed_at": (
                consent.negotiation_closed_at.isoformat()
                if consent.negotiation_closed_at
                else None
            ),
        }
        for consent in consents
    ]


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
    prov: ProvBridge | None = Depends(get_prov),
):
    """Enable or disable a data subject's sharing decision.

    Two forms, one table.  Naming an ``offer_id`` is preferred: the connector
    expands the offer into per-dataset rows and stamps the purpose and
    controller from it, so the decision cannot drift from what the person read.
    Naming a ``dataset_id`` directly remains available for a subject managing
    one dataset from ``/my-data``.
    """
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})

    if not body.offer_id and not body.dataset_id:
        raise HTTPException(422, "Either offer_id or dataset_id is required")

    consumer_id = body.consumer_id or settings.consumer_participant_did

    try:
        if body.offer_id:
            offer = vocab.resolve_offer(body.offer_id)
            if not offer.requires_consent:
                # Contract-based processing is disclosed, not toggled. Offering
                # a control here would imply a choice that does not exist.
                raise HTTPException(
                    409,
                    f"Offer '{offer.id}' is not consent-based "
                    f"(legal basis {offer.legal_basis}) — it is disclosed, not consented",
                )
            consents = []
            async with db.begin():
                for dataset_id in offer.datasets:
                    consents.append(
                        await consent_service.set_subject_data_sharing(
                            session=db,
                            subject_id=x_subject_id,
                            dataset_id=dataset_id,
                            consumer_id=consumer_id,
                            enabled=body.enabled,
                            purpose=[offer.purpose],
                            controller=offer.recipients.controller,
                            controller_role=offer.recipients.controller_role,
                            offer_id=offer.id,
                        )
                    )
            await _emit_consent_events(prov, consents)
            return [ConsentResponse.model_validate(c) for c in consents]

        async with db.begin():
            consent = await consent_service.set_subject_data_sharing(
                session=db,
                subject_id=x_subject_id,
                dataset_id=body.dataset_id,
                consumer_id=consumer_id,
                enabled=body.enabled,
                purpose=body.purpose,
            )
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    await _emit_consent_events(prov, [consent])
    return ConsentResponse.model_validate(consent)


# ── Service-provisioned shares (onboarding) ───────────────────────────────────

def _offer_legal_basis_record(offer, caller: AdminShareLegalBasis | None) -> dict:
    """Assemble the stored legal-basis evidence for a provisioned share.

    The connector, not the caller, is authoritative for anything that ties the
    record to the offer — ``offer_id``, ``controller``, ``controller_role`` and
    the user-visible-facts hash — so a service cannot record consent to
    something other than what the offer describes. The caller supplies only the
    evidence it holds: source, versions, locale, the rendered-text hash and a
    non-PII submission reference.
    """
    sent = caller.model_dump() if caller else {}
    return {
        "source": sent.get("source"),
        "rec_slug": sent.get("rec_slug"),
        "offer_id": offer.id,
        "basis_iri": sent.get("basis_iri") or offer.legal_basis,
        "controller": offer.recipients.controller,
        "controller_role": offer.recipients.controller_role,
        "consent_text_version": sent.get("consent_text_version") or offer.consent_text_version,
        "locale": sent.get("locale"),
        "rendered_text_sha256": sent.get("rendered_text_sha256"),
        "user_visible_hash": vocab.offer_user_visible_hash(offer),
        "accepted_at": sent.get("accepted_at"),
        "submission_ref": sent.get("submission_ref"),
    }


@router.post("/admin/shares")
async def admin_provision_share(
    body: AdminShareRequest,
    request: Request,
    _claims: dict = Depends(require_consent_provision),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    prov: ProvBridge | None = Depends(get_prov),
):
    """Provision a data subject's standing sharing decision from an offer.

    The onboarding service calls this after it syncs a newly-approved
    participant's DID.  It names an ``offer_id``, never a dataset, so it cannot
    drift from the copy the person read: the connector expands the offer into
    one **wildcard-scoped** row per resolved dataset (§3.1), stamping purpose,
    controller-role and the user-visible-facts hash from the offer itself.

    Only consent-based offers can be provisioned — a contract-based offer is
    disclosed, not consented, so provisioning one would manufacture a choice
    that does not exist.  Idempotent: a re-run returns the existing rows.
    """
    try:
        offer = vocab.resolve_offer(body.offer_id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    if not offer.requires_consent:
        raise HTTPException(
            409,
            f"Offer '{offer.id}' is not consent-based (legal basis "
            f"{offer.legal_basis}) — it is disclosed, not consented",
        )

    # A standing share is only meaningful for a member of the offer's controller
    # organisation. Enforced whenever a registry is wired; a pure-unit setup with
    # no registry skips it rather than failing on an unreachable host.
    if settings.identity_registry_url:
        is_member = await check_subject_membership(
            settings.identity_registry_url,
            user_did=body.subject_id,
            organization_alias=offer.recipients.controller,
            token_provider=getattr(request.app.state, "ir_token_provider", None),
        )
        if not is_member:
            raise HTTPException(
                403,
                f"Subject '{body.subject_id}' is not a member of controller "
                f"organisation '{offer.recipients.controller}'",
            )

    legal_basis = _offer_legal_basis_record(offer, body.legal_basis)

    try:
        consents = []
        async with db.begin():
            for dataset_id in offer.datasets:
                consents.append(
                    await consent_service.set_subject_data_sharing(
                        session=db,
                        subject_id=body.subject_id,
                        dataset_id=dataset_id,
                        consumer_id=consent_service.WILDCARD_CONSUMER,
                        enabled=body.enabled,
                        purpose=[offer.purpose],
                        controller=offer.recipients.controller,
                        controller_role=offer.recipients.controller_role,
                        offer_id=offer.id,
                        legal_basis=legal_basis,
                    )
                )
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    await _emit_consent_events(prov, consents)
    return [ConsentResponse.model_validate(c) for c in consents]


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
    request: Request,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
    prov: ProvBridge | None = Depends(get_prov),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
    async with db.begin():
        consent = await consent_service.approve_consent(
            db, consent_id, x_subject_id, notifier=notifier
        )
    if not consent:
        raise HTTPException(404, "Consent request not found or not in pending state")
    await _emit_consent_events(prov, [consent])

    # One grant is enough: the negotiation's consent constraint passes as soon
    # as anybody is in the pool, so the parked negotiation can move now rather
    # than waiting for the rest of the subjects to answer.
    negotiation = await _resume_blocked_negotiation(request, db, consent, settings)
    return {"status": "granted", "id": consent.id, "negotiation": negotiation}


async def _resume_blocked_negotiation(
    request: Request,
    db: AsyncSession,
    consent: ConsentRequestORM,
    settings: Settings,
) -> dict | None:
    """Un-park the negotiation this consent row was blocking, if there is one.

    Best-effort and non-fatal: the subject's decision is recorded and committed
    either way. If the resume does not land, the negotiation stays parked until
    the TTL sweep or a retry reaches it — the wrong outcome, but a recoverable
    one, and much better than failing the subject's own request because a
    control plane was briefly unreachable.
    """
    if not consent.negotiation_id:
        return None
    provider_edc = request.app.state.provider_edc
    if provider_edc is None:
        return None
    try:
        return await provider_edc.resume_negotiation(consent.negotiation_id)
    except Exception as exc:
        log.warning(
            "Could not resume negotiation %s after consent %s was granted: %s",
            consent.negotiation_id, consent.id, exc,
        )
        return {"resumed": False, "outcome": "error"}


@router.post("/my/{consent_id}/reject")
async def reject_consent(
    consent_id: str,
    request: Request,
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

    # One refusal decides nothing about the negotiation — the others may still
    # grant. Only when every ask has come back and none granted is there nothing
    # left to wait for, and the negotiation is terminated rather than left
    # parked until its TTL.
    negotiation = None
    if consent.negotiation_id:
        pending, granted = await consent_service.negotiation_ask_tally(
            db, consent.negotiation_id
        )
        if pending == 0 and granted == 0:
            negotiation = await _terminate_refused_negotiation(
                request, consent.negotiation_id
            )
    return {"status": "rejected", "id": consent.id, "negotiation": negotiation}


async def _terminate_refused_negotiation(request: Request, negotiation_id: str) -> dict:
    """End a negotiation every subject has refused.

    DSP treats ``TERMINATED`` as final but explicitly permits a new negotiation
    afterwards, so this closes the current request without foreclosing a later
    one — which is what a consumer that changes its purpose or its terms needs.
    """
    provider_edc = request.app.state.provider_edc
    if provider_edc is None:
        return {"terminated": False, "outcome": "no_edc_client"}
    try:
        await provider_edc.terminate_negotiation(
            negotiation_id, "All data subjects refused consent"
        )
        return {"terminated": True, "outcome": "terminated"}
    except Exception as exc:
        log.warning("Could not terminate refused negotiation %s: %s", negotiation_id, exc)
        return {"terminated": False, "outcome": "error"}


@router.post("/my/{consent_id}/revoke")
async def revoke_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    notifier: ConsentNotifier = Depends(get_notifier),
    prov: ProvBridge | None = Depends(get_prov),
):
    _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
    async with db.begin():
        consent = await consent_service.revoke_consent(
            db, consent_id, x_subject_id, notifier=notifier
        )
    if not consent:
        raise HTTPException(404, "Consent request not found or not in granted state")
    await _emit_consent_events(prov, [consent])

    # Running transfers are *not* terminated from here. EDC's policy monitor
    # re-evaluates the agreement policy for every started provider transfer, and
    # `AgreementConsentFunction` (bound to the `policy.monitor` scope) now
    # answers that evaluation from this same consent table — so the row we just
    # revoked terminates the transfer on the monitor's next pass, through EDC,
    # with EDC's own state machine and leasing. Terminating from here as well
    # would race that and would only ever cover the transfers this connector
    # happens to have recorded on the row.
    transfer_ids = consent.transfer_ids or []
    if transfer_ids:
        log.info(
            "Consent %s revoked; %d transfer(s) left to the EDC policy monitor",
            consent.id,
            len(transfer_ids),
        )

    return {
        "status": "revoked",
        "id": consent.id,
        "transfer_ids": transfer_ids,
        "termination": "delegated_to_policy_monitor",
    }


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
