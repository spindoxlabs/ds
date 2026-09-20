"""Consent registry API — subject sovereignty endpoints."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from ds.governance.dataplane import split_key
from ds_auth.user_credentials import verify_user_vc_jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsentRequestORM
from ...dependencies import (
    WRITER_COLLECTOR,
    ConsentWriter,
    get_db,
    get_notifier,
    get_participant_registry,
    get_prov,
    get_settings_dep,
    require_consent_audience,
    require_consent_provision,
    require_consent_read,
    require_consent_writer,
    require_internal_scope,
    require_provider_read,
)
from ...notifications.base import ConsentNotifier
from ...registry.participants import CollectorAnswer, CollectorLookupError
from ...services import circle, consent_service
from ...services import consent_vocabulary as vocab
from ...services.membership_check import (
    Membership,
    check_subject_membership,
    resolve_dataset_owner,
)
from ...services.prov_bridge import ProvBridge
from .internal import _admitted_wildcard_offers

log = logging.getLogger(__name__)
router = APIRouter(prefix="/consent", tags=["consent"])


async def _emit_consent_events(
    prov: ProvBridge | None,
    consents: list[ConsentRequestORM],
    *,
    reason: str | None = None,
    acted_by: dict | None = None,
    keys_supplied: bool | None = None,
) -> None:
    """Emit a provenance event per settled consent row, after the DB commits.

    Follows the ``access_revoked`` pattern: provenance is a downstream,
    non-fatal side effect emitted from the API layer once the transaction has
    committed, never inside it — an event must not be recorded for a write that
    then rolls back.  The row's final status decides the event; event ids are
    deterministic so an idempotent re-run (e.g. a repeated admin provision) is
    deduplicated by the provenance store rather than double-counted.

    Who decided (`decided_by`) and the registering organisation (`collector`)
    are read off the row, which the write stamped server-side; ``acted_by`` is
    the verified token of whoever wrote it. The keys are never passed — only
    whether the call supplied some.
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
                recipient=consent.recipient,
                recipient_role=consent.recipient_role,
                legal_basis=consent.legal_basis,
                event_id=f"consent-granted:{consent.id}",
                **_decision_kwargs(consent, acted_by),
                keys_supplied=keys_supplied,
            )
        elif consent.status == "revoked":
            await prov.consent_revoked(
                subject_id=consent.subject_id,
                dataset_id=consent.dataset_id,
                consumer_id=consent.consumer_id,
                offer_id=consent.offer_id,
                purpose=list(consent.purpose or []),
                recipient=consent.recipient,
                recipient_role=consent.recipient_role,
                reason=reason or consent.revocation_reason,
                event_id=f"consent-revoked:{consent.id}",
                **_decision_kwargs(consent, acted_by),
            )


def _decision_kwargs(consent: ConsentRequestORM, acted_by: dict | None) -> dict:
    """The authority context for an event — only when there is any to record.

    A person's own decision through `/consent/my/*` records none of it, and its
    payload stays exactly what it was.
    """
    if acted_by is None and consent.collector is None:
        return {}
    return {
        "decided_by": consent.decided_by,
        "collector": consent.collector,
        "acted_by": acted_by,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ConsentRequestCreate(BaseModel):
    consumer_id: str
    dataset_id: str
    subject_ids: list[str]
    purpose: list[str] = []
    message: str | None = None
    notification_url: str | None = None
    # Who the data goes to, and in what capacity. `consumer_id` alone cannot
    # answer that: it names a connector, not the party the offer is addressed to.
    #
    # `controller` / `controller_role` are accepted as the deprecated spellings.
    # This model does not forbid extras, so dropping the old names would have
    # made an old caller's recipient vanish silently rather than 422 — the
    # quietest possible way to lose the dimension `D-14` says the wildcard must
    # never cross.
    recipient: str | None = Field(
        default=None, validation_alias=AliasChoices("recipient", "controller")
    )
    recipient_role: str | None = Field(
        default=None,
        validation_alias=AliasChoices("recipient_role", "controller_role"),
    )
    offer_id: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ConsentResponse(BaseModel):
    id: str
    subject_id: str
    consumer_id: str
    dataset_id: str
    purpose: list[str] = []
    recipient: str | None = None
    recipient_role: str | None = None
    offer_id: str | None = None
    legal_basis: dict | None = None
    message: str | None = None
    status: str
    # Which authority took the decision this row records — `subject`, `service`
    # or `operator`. Projected because a caller reading an audience cannot
    # otherwise tell a consent the person gave from one a system recorded for
    # them, and `D-15c` makes that difference decide who may change it.
    decided_by: str = "subject"
    # The organisation (DID) whose token registered the decision, when one did.
    collector: str | None = None
    # Whether the row holds data keys. The keys themselves are returned only to
    # the organisation that registered them (`GET /consent/admin/subject-shares`).
    keys_supplied: bool = False
    requested_at: datetime
    decided_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _keys_supplied_from_row(cls, value):
        if isinstance(value, ConsentRequestORM):
            return {
                **{
                    column: getattr(value, column)
                    for column in cls.model_fields
                    if hasattr(value, column)
                },
                "keys_supplied": bool(value.subject_keys),
            }
        return value


class RegisteredConsentResponse(ConsentResponse):
    """A registration's answer: the row, and what it is still waiting for.

    ``missing_prerequisites`` names the offers this offer is admitted only
    together with (`requires_offers`) that the subject has not granted at this
    connector. Non-empty means the decision is recorded and does not admit the
    subject yet — said here rather than discovered as an empty row filter.
    """

    missing_prerequisites: list[str] = []


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
    connector supplies ``offer_id``, ``recipient``, ``recipient_role`` and
    ``user_visible_hash`` itself from the resolved offer, so the caller cannot
    drift from what the person read.

    **Unknown keys are rejected, not ignored** (``extra="forbid"``). Pydantic's
    default would accept an extra evidence field, drop it, and answer ``200`` —
    the worst outcome an evidence model can produce, because the caller has
    written proof it does not hold. That includes the connector-supplied fields
    above: sending one is a misunderstanding of who owns it, and a ``422`` says
    so where silence looked like agreement.

    **Three fields are required**, because without them the record proves nothing:
    a consent provisioned by a service is only defensible if it can be tied back to
    a specific rendering that a specific person saw (GDPR Art. 7(1)). ``source``
    says which system asked, ``consent_text_version`` which revision, and
    ``rendered_text_sha256`` pins the exact bytes displayed. An evidence record
    missing any of them is decorative, and decorative evidence is worse than none
    because it looks like proof.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    consent_text_version: str
    rendered_text_sha256: str

    rec_slug: str | None = None
    basis_iri: str | None = None
    # Strongly recommended: which rendering the person actually read. Required in
    # any deployment that publishes consent text in more than one language.
    locale: str | None = None
    accepted_at: str | None = None
    submission_ref: str | None = None

    @field_validator("source", "consent_text_version", "rendered_text_sha256")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v

    @field_validator("rec_slug", "submission_ref", "source", mode="after")
    @classmethod
    def _no_obvious_pii(cls, v: str | None) -> str | None:
        """Reject the most common way PII leaks into an evidence record.

        These are opaque references by contract. An address here would put a
        person's identity into the connector's database, which is precisely what
        the codes-and-hashes rule exists to prevent. This catches the obvious
        case, not every case — the contract still relies on the caller.
        """
        if v and "@" in v:
            raise ValueError(
                "must be an opaque reference, not an email address or other identifier"
            )
        return v


class SubjectWithdrawalOverride(BaseModel):
    """A deliberate, evidenced lift of a withdrawal the data subject made.

    `D-15c` makes a subject's own withdrawal theirs to lift, so the ordinary
    provisioning call is refused over one (409). This is the exception, and it is
    shaped so that taking it is an act on the record rather than a flag: an
    operator correcting a decision at a person's request — on the phone, at a
    counter — can, and a re-running onboarding service cannot do it by accident,
    because supplying this means writing down who authorised it and why.

    The row it produces is stamped ``decided_by="operator"``, and this record is
    stored inside the row's ``legal_basis`` beside the consent evidence, which is
    where a later reader asking *how did this consent come back* will look.

    **Opaque references only**, the same contract as `AdminShareLegalBasis`: the
    connector's database is not a PII store, and an operator's name or the
    subject's email in here would make it one.
    """

    model_config = ConfigDict(extra="forbid")

    #: Why the withdrawal is being lifted, in the operator's words.
    reason: str
    #: Who authorised it — a staff or console identifier, never a name or email.
    authorized_by: str
    #: The record of the person asking for it: a ticket, a call reference.
    instruction_ref: str | None = None

    @field_validator("reason", "authorized_by")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v

    @field_validator("authorized_by", "instruction_ref", mode="after")
    @classmethod
    def _no_obvious_pii(cls, v: str | None) -> str | None:
        if v and "@" in v:
            raise ValueError(
                "must be an opaque reference, not an email address or other identifier"
            )
        return v


#: The longest cause a withdrawal may record — one line, not a notes field.
REASON_MAX_LENGTH = 200


class AdminShareRequest(BaseModel):
    """A service recording a subject's standing decision.

    ``legal_basis`` is mandatory when enabling a share: a service asserting that
    someone consented, without evidence of what they were shown, is an assertion
    nobody can defend later. Withdrawal needs no evidence — a person may always
    stop, and requiring proof to stop would be the wrong way round.
    """

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    offer_id: str
    enabled: bool
    legal_basis: AdminShareLegalBasis | None = None
    #: Present only when the caller means to lift a withdrawal the subject made
    #: themselves. Absent, that attempt is refused with a 409 (`D-15c`).
    override_subject_withdrawal: SubjectWithdrawalOverride | None = None
    #: The subject's typed data keys at this holder, `"<type>:<value>"`
    #: (e.g. `pod:…`). Sent with a grant; a later grant replaces them and a
    #: withdrawal drops them, so sending them with a withdrawal is refused.
    keys: list[str] | None = Field(default=None, max_length=64)
    #: **Required from an organisation token, refused from anyone else.**
    #: `subject` — the organisation relays a decision the member took (a
    #: relayed withdrawal is then the member's, `D-15c`); `collector` — the
    #: organisation decided itself (e.g. the member left it).
    decided_by: Literal["subject", "collector"] | None = None
    #: **Why the organisation withdrew**, on its own withdrawal only
    #: (``enabled: false`` with ``decided_by: "collector"`` — a membership
    #: ending). A cause, not a narrative: it is stored as the row's
    #: ``revocation_reason`` and carried by the ``ConsentRevoked`` provenance
    #: event, and projected by no read (`D-12a`). Not ``message``: that is the
    #: text a row is created with, and ``ConsentResponse`` returns it to every
    #: reader.
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=REASON_MAX_LENGTH,
        description=(
            "Why the organisation withdrew — accepted only with enabled=false and "
            "decided_by='collector'. One line, at most "
            f"{REASON_MAX_LENGTH} characters, no personal data (an '@' is refused). "
            "Recorded on the row and in provenance; returned by no read."
        ),
    )

    @field_validator("reason", mode="before")
    @classmethod
    def _reason_is_one_line_and_no_address(cls, v):
        """A cause, in one line, and not the obvious way PII gets in.

        It reaches provenance, where `D-2` allows codes, DIDs and hashes only, so
        the value is trimmed, a line break or control character is refused (a
        cause is one line; a paragraph is a notes field), and an ``@`` is refused
        the way `AdminShareLegalBasis` refuses one — the obvious case, not every
        case.
        """
        if not isinstance(v, str):
            return v
        v = v.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("must be a single line with no control characters")
        if "@" in v:
            raise ValueError(
                "must not carry an email address or other identifier — say why, not who"
            )
        return v

    @field_validator("keys")
    @classmethod
    def _typed_keys(cls, keys: list[str] | None) -> list[str] | None:
        if keys is None:
            return None
        for key in keys:
            try:
                split_key(key)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
        # One list, one order: a re-registration with the same keys in another
        # order is not a change.
        return sorted(set(keys))

    @model_validator(mode="after")
    def _evidence_required_to_grant(self) -> AdminShareRequest:
        if self.enabled and self.legal_basis is None:
            raise ValueError(
                "legal_basis is required when enabling a share: a service cannot "
                "assert that someone consented without evidence of what they were "
                "shown"
            )
        if self.override_subject_withdrawal is not None and not self.enabled:
            # Withdrawing needs no override: a person may always stop, and the
            # guard this overrides only stands in front of *re-opening*. Accepting
            # it here would file an override record against an act that never
            # needed one, which is evidence of a decision nobody took.
            raise ValueError(
                "override_subject_withdrawal applies to enabling a share; a "
                "withdrawal overrides nothing"
            )
        if self.keys is not None and not self.enabled:
            raise ValueError(
                "keys travel with a grant; a withdrawal drops them and takes none"
            )
        if self.reason is not None and (self.enabled or self.decided_by != "collector"):
            # A grant has no cause to record. A relayed withdrawal is the member's
            # (`D-15c`), so the organisation's words would be filed as the cause
            # of a decision it did not take; the operator has no stated need.
            raise ValueError(
                "reason is recorded only on an organisation's own withdrawal: "
                "enabled=false with decided_by='collector'"
            )
        return self


def _verify_user(
    x_user_vc: str | None,
    x_subject_id: str | None,
    settings: Settings,
    roles: set[str],
) -> str:
    """Verify the caller's user credential and return the subject it names.

    **Returns the id so callers stop re-deriving it from the header.** Both
    arrivals are `str | None` — that is what a missing header looks like — and
    `verify_user_vc_jwt` refuses either with a 401 before this returns. Every
    caller then passed the *header* on to a service typed `str`, so eight call
    sites each carried an `Optional` that could not occur, and the guarantee
    lived only in the reader's head.

    Handing back the verified value puts it in the signature instead. No caller
    used the previous return (the claims), so nothing loses anything.
    """
    verify_user_vc_jwt(
        x_user_vc,
        x_subject_id,
        settings.trust_anchor_did,
        roles,
        trust_list_url=settings.trust_list_url,
        did_web_use_https=settings.did_web_use_https,
        expected_linked_participant=settings.participant_did,
        credential_status_path=settings.credential_status_path,
        credential_status_url=settings.credential_status_url,
        insecure_dev=settings.vc_insecure_dev,
    )
    # Unreachable when `x_subject_id` is None — the call above raises 401 first.
    # Asserted rather than cast so the guarantee is checked, not asserted twice.
    assert x_subject_id is not None
    return x_subject_id


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
        allowed = (
            {h.strip().lower() for h in allowed_raw.split(",") if h.strip()}
            if allowed_raw
            else set()
        )
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
                users_domain = settings.trust_anchor_did.replace(
                    "did:web:", ""
                ).replace("trust-anchor.", "users.")
                subject_did = f"did:web:{users_domain}:{subject_id}"

            membership = await check_subject_membership(
                settings.identity_registry_url,
                user_did=subject_did,
                organization_alias=owner_alias,
                token_provider=request.app.state.ir_token_provider,
            )
            # Unverifiable is not the same as refused, and it gets the same 503
            # `_reject_unknown_participant` gives an unreachable participant
            # registry a few lines below. A 403 here would tell the caller the
            # person is not a member — a claim nothing established — and a caller
            # that believes it files a permanent failure for an outage.
            if membership is Membership.UNKNOWN:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Identity registry unavailable, cannot verify that "
                        f"'{subject_id}' is a member of dataset owner "
                        f"organization '{owner_alias}'"
                    ),
                )
            if membership is Membership.NOT_MEMBER:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Subject '{subject_id}' is not a member of dataset owner "
                        f"organization '{owner_alias}'"
                    ),
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
                    recipient=body.recipient,
                    recipient_role=body.recipient_role,
                    offer_id=body.offer_id,
                )
                request_ids.append(consent.id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"request_ids": request_ids, "status": "pending"}


async def _require_known_participant(
    registry, consumer_id: str, settings: Settings
) -> None:
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

    A processor of the offer's recipient acts on its instructions under a DPA;
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
            f"'{offer.id}' as a processor of '{offer.recipients.recipient}' — "
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
    x_subject_id = _verify_user(
        x_user_vc, x_subject_id, settings, {"ConsumerUser", "DataSubject"}
    )
    # The `subject_id` query parameter is caller-supplied; without this check any
    # authenticated holder could enumerate another subject's consent decisions.
    if subject_id != x_subject_id:
        raise HTTPException(403, "Cannot read consent status for another subject")
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
    subject_id = _verify_user(
        x_user_vc, subject_id, settings, {"DataSubject", "ConsumerUser"}
    )

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
    """List standing sharing decisions for the authenticated data subject.

    **The wildcard is always in the key set**, exactly as it is for every reader
    in `consent_service` (`_consent_rows_for`). A standing offer-scoped decision
    is a `consumer_id = "*"` row (§3.1) whichever route recorded it, so filtering
    on a single party hid two things at once: the rows onboarding provisioned for
    this person, and — once the offer path below started writing the wildcard —
    the person's own decision, from the person who made it.
    """
    subject_id = x_subject_id
    subject_id = _verify_user(x_user_vc, subject_id, settings, {"DataSubject"})

    consents = await consent_service.list_subject_consents(
        session=db,
        subject_id=subject_id,
        consumer_id={
            consumer_id or settings.consumer_participant_did,
            consent_service.WILDCARD_CONSUMER,
        },
    )
    # One current decision per *question asked*, not per dataset. Several offers
    # can name the same dataset for different purposes and recipients; collapsing
    # them on the dataset alone hides every decision but the first, so a subject
    # who granted two purposes would see only one of them.
    latest: dict[tuple[str, str | None], ConsentResponse] = {}
    for consent in consents:
        latest.setdefault(
            (consent.dataset_id, consent.offer_id),
            ConsentResponse.model_validate(consent),
        )
    return list(latest.values())


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
    recipient from it, so the decision cannot drift from what the person read.
    Naming a ``dataset_id`` directly remains available for a subject managing
    one dataset from ``/my-data``.

    **An offer-scoped decision is wildcard-scoped (§3.1), whoever records it.**
    It used to be keyed on ``settings.consumer_participant_did`` — the party this
    connector negotiates against when it *consumes*, which is a transfer fact and
    has no bearing on who a member discloses to. Every reader evaluates
    ``{consumer_id, WILDCARD_CONSUMER}`` and asks about the offer's *recipient*,
    so a genuinely recorded consent was in neither set and every audience read
    answered ``[]`` — a well-formed 200 indistinguishable from "nobody
    consented", and an export built on it wrote a correctly-headed file with zero
    rows. ``POST /consent/admin/shares``, the operator-facing twin, has always
    written the wildcard for the same offer; the member's decision is the same
    decision and is now the same row, which is also what lets a member re-decide
    an offer onboarding provisioned for them instead of forking a second row.

    D-14 is what bounds it: the wildcard admits any party inside the circle *for
    that recipient and purpose*, both stamped here from the offer, and never a
    new recipient or purpose. A caller that names ``consumer_id`` explicitly
    still writes a per-party row, which D-15 lets override the standing one.

    **Bounded on the read side, not here.** This route writes one row; who that
    row admits is decided when it is read, by
    :func:`connector.services.circle.admits_wildcard` — the offer's recipient,
    resolved from ``recipients.recipient`` through the owner registry, or a
    processor inside its circle. Until 2026-09-15 nothing applied that bound
    while consent was present, so the sentence above described an intention
    rather than the code; it is enforced now, and the place to change it is
    `circle`, never this docstring.
    """
    x_subject_id = _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})

    if not body.offer_id and not body.dataset_id:
        raise HTTPException(422, "Either offer_id or dataset_id is required")

    # **Grants are aimed; withdrawals spread.**
    #
    # An offer-scoped decision is wildcard-scoped either way (§3.1). The
    # `dataset_id` form is where the two directions part: *stopping* names no
    # party, so it is a statement about every party and is written against the
    # wildcard — the `/my-data` "Stop" control is the blanket one, and pinning it
    # to the negotiation counterparty made it the *weakest* control on the page,
    # which is the reading Art. 7(3) rules out.
    #
    # *Enabling* stays aimed at the configured counterparty. A bare dataset grant
    # names no offer, so it carries no `recipient` and no `recipient_role` —
    # and `consent_satisfies` compares the role only when both sides hold one, so
    # a wildcard row with neither would authorise any party in any role for the
    # purpose. That is a widening nobody asked for; it is refused by keeping the
    # grant narrow rather than by a guard further down.
    if body.offer_id or not body.enabled:
        default_consumer = consent_service.WILDCARD_CONSUMER
    else:
        default_consumer = settings.consumer_participant_did
    consumer_id = body.consumer_id or default_consumer

    try:
        if body.offer_id:
            offer = vocab.resolve_offer(body.offer_id)
            if not offer.requires_consent:
                # Contract-based processing is disclosed, not toggled. Offering
                # a control here would imply a choice that does not exist.
                raise HTTPException(
                    409,
                    f"Offer '{offer.id}' is not consent-based "
                    f"(legal basis {offer.legal_basis}) — it is disclosed, not "
                    "consented",
                )
            # The subject's own decision deserves the same evidence record a
            # service-provisioned one gets. Without it there is no record of
            # *which* consent text this person saw — `user_visible_hash` exists
            # precisely to prove that, and a decision made in the portal is no
            # less in need of proof than one made in the onboarding wizard.
            #
            # No caller-supplied part: everything is derived from the resolved
            # offer server-side, so the portal cannot drift from what was shown.
            legal_basis = _offer_legal_basis_record(offer, None)

            consents = []
            async with db.begin():
                for dataset_id in vocab.datasets_for_offer(offer.id):
                    consents.append(
                        await consent_service.set_subject_data_sharing(
                            session=db,
                            subject_id=x_subject_id,
                            dataset_id=dataset_id,
                            consumer_id=consumer_id,
                            enabled=body.enabled,
                            purpose=[offer.purpose],
                            recipient=offer.recipients.recipient,
                            recipient_role=offer.recipients.recipient_role,
                            offer_id=offer.id,
                            legal_basis=legal_basis,
                            decided_by="subject",
                        )
                    )
            await _emit_consent_events(prov, consents)
            return [ConsentResponse.model_validate(c) for c in consents]

        # Reached only when `offer_id` is absent, and the 422 at the top of this
        # handler already refused a body naming neither — so a dataset id is
        # present here. Bound so that guarantee is visible at the call rather
        # than forty lines above it.
        target_dataset_id = body.dataset_id
        assert target_dataset_id is not None, (
            "the 422 above requires offer_id or dataset_id"
        )
        async with db.begin():
            consent = await consent_service.set_subject_data_sharing(
                session=db,
                subject_id=x_subject_id,
                dataset_id=target_dataset_id,
                consumer_id=consumer_id,
                enabled=body.enabled,
                purpose=body.purpose,
                decided_by="subject",
            )
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    await _emit_consent_events(prov, [consent])
    return ConsentResponse.model_validate(consent)


# ── Service-provisioned shares (onboarding) ───────────────────────────────────


def _offer_legal_basis_record(
    offer,
    caller: AdminShareLegalBasis | None,
    override: SubjectWithdrawalOverride | None = None,
    collector: str | None = None,
) -> dict:
    """Assemble the stored legal-basis evidence for a provisioned share.

    The connector, not the caller, is authoritative for anything that ties the
    record to the offer — ``offer_id``, ``recipient``, ``recipient_role`` and
    the user-visible-facts hash — so a service cannot record consent to
    something other than what the offer describes. The caller supplies only the
    evidence it holds: source, versions, locale, the rendered-text hash and a
    non-PII submission reference.

    ``collector`` — the organisation whose token registered the consent — is the
    connector's too: read off the verified token, never off the body. Present
    only when an organisation registered it.
    """
    sent = caller.model_dump() if caller else {}
    return {
        "source": sent.get("source"),
        "rec_slug": sent.get("rec_slug"),
        "offer_id": offer.id,
        "basis_iri": sent.get("basis_iri") or offer.legal_basis,
        "recipient": offer.recipients.recipient,
        "recipient_role": offer.recipients.recipient_role,
        "consent_text_version": sent.get("consent_text_version")
        or offer.consent_text_version,
        "locale": sent.get("locale"),
        "rendered_text_sha256": sent.get("rendered_text_sha256"),
        "user_visible_hash": vocab.offer_user_visible_hash(offer),
        "accepted_at": sent.get("accepted_at"),
        "submission_ref": sent.get("submission_ref"),
        **({"collector": collector} if collector else {}),
        # Present only on the exceptional path, and then it is the most important
        # thing in the record: this consent came back over a withdrawal the person
        # made themselves, and here is who said so. Absent on every ordinary
        # provision, so its presence is the signal (`D-15c`).
        **(
            {"subject_withdrawal_override": override.model_dump(exclude_none=True)}
            if override
            else {}
        ),
    }


async def check_collector(
    request: Request, holder_did: str, collector_did: str
) -> CollectorAnswer:
    """Ask the participant registry whether *collector_did* may write here.

    One seam for the route and its tests. A registry with no collector lookup
    (none configured) accepts only the holder itself.
    """
    registry = getattr(request.app.state, "registry", None)
    lookup = getattr(registry, "consent_collector", None)
    if lookup is None:
        if holder_did == collector_did:
            return CollectorAnswer(True, None, "a holder collects for itself")
        return CollectorAnswer(False, None, "no collector registry is configured")
    answer = lookup(holder_did, collector_did)
    if inspect.isawaitable(answer):
        answer = await answer
    return answer


async def _admit_writer(
    request: Request, settings: Settings, writer: ConsentWriter, subject_id: str
) -> None:
    """May this writer write — or read back — this subject's decisions here?

    Plan `a-collector-registers-consent-at-the-holder`, decisions 1-2:

    1. a **collector** must be accepted for this holder in the identity
       registry. Not accepted is a 403; a registry that cannot say is a 503.
    2. the subject must be a **member of the organisation the writer speaks
       for** — the collector, or this connector's own organisation — never of
       the offer's recipient (`D-21`). The owner id to check is the registry's
       answer for that organisation's DID.

    A deployment with no identity registry keeps today's behaviour for its own
    services (no membership check) and accepts no collector.
    """
    try:
        answer = await check_collector(
            request, settings.participant_did, writer.organisation
        )
    except CollectorLookupError as exc:
        raise HTTPException(
            503,
            f"Identity registry unavailable, cannot verify that "
            f"'{writer.organisation}' may register consent here",
        ) from exc
    if not answer.accepted:
        raise HTTPException(
            403,
            f"'{writer.organisation}' is not an accepted consent collector for "
            f"this participant ({answer.reason})",
        )
    if not settings.identity_registry_url:
        if writer.kind == WRITER_COLLECTOR:
            raise HTTPException(
                403,
                "no identity registry is configured, so no collector's "
                "membership can be verified",
            )
        return
    if not answer.collector_owner:
        raise HTTPException(
            403,
            f"'{writer.organisation}' is not the DID of a registered organisation, "
            "so whose members it speaks for cannot be checked",
        )
    membership = await check_subject_membership(
        settings.identity_registry_url,
        user_did=subject_id,
        organization_alias=answer.collector_owner,
        token_provider=getattr(request.app.state, "ir_token_provider", None),
    )
    # Retryable, not refused — see the same split on the consent-request
    # route. Provisioning is driven by a service working through approved
    # records, and a 403 is what tells it to stop and file the failure.
    if membership is Membership.UNKNOWN:
        raise HTTPException(
            503,
            f"Identity registry unavailable, cannot verify that "
            f"'{subject_id}' is a member of organisation "
            f"'{answer.collector_owner}'",
        )
    if membership is Membership.NOT_MEMBER:
        raise HTTPException(
            403,
            f"Subject '{subject_id}' is not a member of organisation "
            f"'{answer.collector_owner}', which this caller speaks for",
        )


@router.post("/admin/shares", response_model=list[RegisteredConsentResponse])
async def admin_provision_share(
    body: AdminShareRequest,
    request: Request,
    writer: ConsentWriter = Depends(require_consent_writer),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    prov: ProvBridge | None = Depends(get_prov),
):
    """Register a data subject's standing sharing decision from an offer.

    **Who calls this.** Three kinds of caller, classified from the verified
    token (`ConsentWriter`), never from the body:

    - an **accepted collector** — another organisation's own client, registering
      a decision one of *its* members took (plan
      `a-collector-registers-consent-at-the-holder`): the community collects the
      consent, the organisation holding the data registers it here, and this
      connector's data plane then needs no call back to the community;
    - this connector's **own organisation client** — the holder registering what
      it collected itself. An onboarding service (out of this repository) runs as
      that client;
    - the **deployment operator**, a person holding `connector.admin`, for the
      evidenced `override_subject_withdrawal`.

    **A plain service token is refused** (`403`) since 2026-09-17, and so is a
    participant operator's seat: neither is bound to an organisation that could
    speak for the subject.

    In every case the subject must be a member of the organisation the caller
    speaks for (`D-21`), not of the offer's recipient.

    An organisation token says whose decision it is (``decided_by``): the
    member's, relayed — so a relayed withdrawal is the member's and no service
    provision lifts it (`D-15c`) — or the organisation's own. The organisation is
    recorded on the row, in the evidence and in provenance; the subject's data
    ``keys`` are stored on the row and carried by the data plane's row filter,
    and provenance records only that some were supplied.

    It names an ``offer_id``, never a dataset, so it cannot drift from the copy
    the person read: the connector expands the offer into one **wildcard-scoped**
    row per resolved dataset (§3.1), stamping purpose, recipient-role and the
    user-visible-facts hash from the offer itself. An offer that resolves to no
    dataset here is a 422 — an empty answer would read as "recorded".

    Only consent-based offers can be provisioned — a contract-based offer is
    disclosed, not consented, so provisioning one would manufacture a choice
    that does not exist.  Idempotent: a re-run returns the existing rows, with
    their keys replaced if the call sent different ones.

    **It will not re-open a withdrawal another authority stands behind**
    (`D-15c`): a re-run over a member who has since withdrawn is refused with a
    ``409`` naming the withdrawal. An operator who has a person's instruction to
    restore it sends ``override_subject_withdrawal``, which stamps the row
    ``operator`` and files the authority for the act inside its evidence record.

    ``missing_prerequisites`` on each row names the offers this one is admitted
    only together with that the subject has not granted here.
    """
    if writer.is_organisation_token:
        if body.decided_by is None:
            raise HTTPException(
                422,
                "an organisation registering consent must say whose decision it "
                "is: decided_by='subject' (relayed) or 'collector'",
            )
        if body.override_subject_withdrawal is not None:
            raise HTTPException(
                422,
                "override_subject_withdrawal is an operator's act; an "
                "organisation token relays or takes decisions",
            )
    elif body.decided_by is not None:
        raise HTTPException(
            422,
            "decided_by is stated by an organisation token only; this caller's "
            "authority is recorded from its token",
        )

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

    try:
        dataset_ids = vocab.datasets_for_offer(offer.id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not dataset_ids:
        raise HTTPException(
            422,
            f"Offer '{offer.id}' resolves to no dataset at this connector — there "
            "is nothing here to record the decision against",
        )

    await _admit_writer(request, settings, writer, body.subject_id)

    override = body.override_subject_withdrawal
    legal_basis = _offer_legal_basis_record(
        offer, body.legal_basis, override, collector=writer.collector_did
    )

    # **Whose decision, stated by the caller's class.** An organisation token
    # says it (relayed member decision → `subject`, its own → `collector`). The
    # only other writer is the deployment operator, a person, and its act is
    # `operator` whether or not it carries the evidenced override — the
    # override record in `legal_basis` is what says a person's withdrawal was
    # lifted. A plain service never reaches here (`require_consent_writer`).
    if writer.is_organisation_token:
        decided_by = str(body.decided_by)
    else:
        decided_by = "operator"

    try:
        consents = []
        async with db.begin():
            for dataset_id in dataset_ids:
                consents.append(
                    await consent_service.set_subject_data_sharing(
                        session=db,
                        subject_id=body.subject_id,
                        dataset_id=dataset_id,
                        consumer_id=consent_service.WILDCARD_CONSUMER,
                        enabled=body.enabled,
                        purpose=[offer.purpose],
                        recipient=offer.recipients.recipient,
                        recipient_role=offer.recipients.recipient_role,
                        offer_id=offer.id,
                        legal_basis=legal_basis,
                        decided_by=decided_by,
                        override_subject_withdrawal=bool(override),
                        collector=writer.collector_did,
                        keys=body.keys,
                        holder=settings.participant_did if writer.is_holder else None,
                        reason=body.reason,
                        message=(
                            f"Operator override of the data subject's withdrawal: "
                            f"{override.reason}"
                            if override and body.enabled
                            else None
                        ),
                    )
                )
            missing = {
                consent.id: consent_service.missing_prerequisites(
                    await consent_service.subject_rows_for(
                        db, consent.dataset_id, body.subject_id
                    ),
                    offer.id,
                )
                for consent in consents
            }
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except consent_service.ConsentWithdrawalStands as exc:
        # 409, not 403: the caller holds the permission this route requires and is
        # not being told it may not provision. It is being told the cell already
        # holds a decision it cannot overwrite — a conflict with the state, which
        # is what 409 means, and what the caller has to reconcile before asking
        # again. The transaction rolls back, so a multi-dataset offer provisions
        # all of its rows or none: a partial audience is not a state anyone asked
        # for and not one the caller could detect from a 409.
        whose = (
            f"Subject '{body.subject_id}' withdrew this share themselves"
            if exc.decided_by == "subject"
            else f"This share was withdrawn by {exc.decided_by}"
            + (f" '{exc.collector}'" if exc.collector else "")
        )
        raise HTTPException(
            409,
            f"{whose} (dataset '{exc.dataset_id}', consent '{exc.consent_id}', "
            f"{exc.withdrawn_at}). Only that authority or the subject can lift it "
            "— or an operator, by sending override_subject_withdrawal with the "
            "authority for it (D-15c).",
        ) from exc
    await _emit_consent_events(
        prov,
        consents,
        acted_by=writer.acted_by,
        keys_supplied=bool(body.keys) if body.enabled else None,
    )
    return [
        RegisteredConsentResponse(
            **ConsentResponse.model_validate(c).model_dump(),
            missing_prerequisites=missing.get(c.id, []),
        )
        for c in consents
    ]


class SubjectShare(ConsentResponse):
    """One of a subject's decisions at this connector, for the organisation that
    speaks for them — with the data keys it registered, and nothing it did not."""

    keys: list[str] = []
    missing_prerequisites: list[str] = []


@router.get("/admin/subject-shares", response_model=list[SubjectShare])
async def admin_read_subject_shares(
    request: Request,
    subject_id: str = Query(..., min_length=1),
    writer: ConsentWriter = Depends(require_consent_writer),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """One subject's decisions here, for the organisation that speaks for them.

    The read-back a collector needs (plan
    `a-collector-registers-consent-at-the-holder`, item 6): what did the holder
    record for my member? `D-20` forbids a service reading `/consent/my`; this is
    the narrow exception, and it is **per subject and limited to the caller's own
    members** — the same acceptance and membership check the write makes, so an
    organisation reads back exactly the people it may write for, one at a time.
    Never a roster: `GET /consent/admin/shares` is the cross-subject read, and an
    organisation client does not hold its permission.

    It lists the latest decision per ``(dataset, offer, consumer)``, the asks
    outstanding against the subject here (`D-18`: a member cannot see a holder's
    asks, so their organisation is where they surface), and — for the rows that
    hold them — the data keys, which only the registering organisation gets back.
    """
    await _admit_writer(request, settings, writer, subject_id)

    rows = await consent_service.list_subject_consents(
        session=db, subject_id=subject_id
    )
    latest: dict[tuple[str, str | None, str], ConsentRequestORM] = {}
    for row in sorted(rows, key=consent_service.decision_time, reverse=True):
        if row.status == "pending":
            latest.setdefault((row.dataset_id, row.offer_id, f"ask:{row.id}"), row)
            continue
        latest.setdefault((row.dataset_id, row.offer_id, row.consumer_id), row)

    by_dataset: dict[str, list[ConsentRequestORM]] = {}
    for row in rows:
        by_dataset.setdefault(row.dataset_id, []).append(row)

    shares = []
    for row in latest.values():
        own_keys = (
            writer.collector_did is not None and row.collector == writer.collector_did
        ) or (writer.collector_did is None and row.collector is None)
        shares.append(
            SubjectShare(
                **ConsentResponse.model_validate(row).model_dump(),
                keys=list(row.subject_keys or []) if own_keys else [],
                missing_prerequisites=(
                    consent_service.missing_prerequisites(
                        await consent_service.subject_rows_for(
                            db, row.dataset_id, subject_id
                        ),
                        row.offer_id,
                    )
                    if row.offer_id and row.status == "granted"
                    else []
                ),
            )
        )
    return shares


class OfferAudienceSubject(BaseModel):
    """One consenting subject, and when the authorising decision was taken.

    ``decided_at`` is the ``decided_at`` of the row that authorises *this*
    disclosure — the row ``decide_for_subject`` selected — not the subject's
    earliest or latest decision overall. The two differ whenever a standing
    wildcard is overridden per party, or one offer is re-decided while another
    stands.
    """

    subject_id: str
    decided_at: datetime | None


class OfferAudienceDataset(BaseModel):
    """The subjects one resolved dataset authorises, for one consumer.

    **``subjects`` carries the timestamps; ``subject_ids`` is unchanged.**
    A DSO processing a released supply point has to evidence the lawful basis
    *per point* — which POD, and as of when — so a date that attaches only to the
    export file does not do the job. ``decided_at`` was already loaded and thrown
    away: the row it comes from is the one this route's own filter selected.

    The two keys are kept side by side rather than ``subject_ids`` being reshaped
    in place, so the existing key goes on meaning exactly what it says and the
    caller gains a column rather than a restructure.
    """

    dataset_id: str
    subject_ids: list[str]
    subjects: list[OfferAudienceSubject]
    subject_count: int


class OfferAudience(BaseModel):
    """Who currently consents to an offer, for the consumer it is disclosed to.

    ``purpose`` and ``recipient_role`` are echoed because they were *stamped*
    rather than supplied: a caller reconciling its own audit trail needs to see
    which question the connector actually answered.
    """

    offer_id: str
    consumer_id: str
    purpose: list[str]
    recipient_role: str | None
    datasets: list[OfferAudienceDataset]


@router.get("/admin/shares", response_model=OfferAudience)
async def admin_read_offer_audience(
    request: Request,
    offer_id: str = Query(..., min_length=1),
    consumer_id: str = Query(..., min_length=1),
    _claims: dict = Depends(require_consent_audience),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """Who currently consents to this offer, for this consumer.

    The read counterpart to ``POST /consent/admin/shares``, and the reason it
    exists: onboarding holds ``connector.consent.provision`` and can write a
    standing consent, and until this route there was no way to read one back
    before exporting against it. A supply-point export needs exactly one fact —
    *who currently consents to this offer* — and the asymmetry, not a permission
    width, was the gap.

    **The caller supplies no ``purpose`` and no ``recipient_role``, and that is
    the point.** They are stamped from the offer through ``resolve_offer``,
    exactly as ``POST /consent/admin/shares`` and ``POST /admin/disclosure``
    already stamp them. ``GET /internal/consent/check`` answers
    ``{"subject_ids": []}`` with a 200 when a caller omits ``purpose`` on a
    consent-required dataset — a caller-supplied under-specification silently
    returning "nobody". Here that is unreachable by construction: a caller that
    cannot supply a purpose cannot omit one.

    **``consumer_id`` is required and is a participant DID**, the same key the
    consent rows are written with. It is deliberately *not* the ``recipient_ref``
    a discloser passes to ``POST /admin/disclosure``: that is an opaque handle —
    an org alias, a slug, a DPA reference — and no alias-to-consumer-DID mapping
    exists in this codebase to resolve it with. Guessing one here would be
    undetectable from the response, which returns a plausible list either way.

    **Why it must not be optional, and must not be ``*``.**
    ``get_granted_subject_ids`` evaluates ``{consumer_id, WILDCARD_CONSUMER}``
    together through ``resolve_decision``, where a per-party opt-out beats the
    standing wildcard ``admin/shares`` writes. A call that omitted the consumer,
    or passed the wildcard itself, would load *only* wildcard rows — the specific
    opt-out rows would never be read — and would return people who have
    specifically opted out of that recipient. That is a disclosure against a
    withdrawn consent: the exact defect this route exists to prevent,
    reintroduced by a default. So the parameter is required and the wildcard is
    refused rather than treated as "any consumer".

    **Offer in, datasets out, server-side.** An offer does not name its datasets;
    datasets name the offer, and ``datasets_for_offer`` resolves them. The export
    has an ``offer_id`` and cannot have a dataset key — `D-13` keeps those out of
    the public projection deliberately, which is why ``POST /admin/disclosure``
    was given an ``offer_id`` for this same caller in the first place.

    **One subject set per dataset, never flattened.** Today's fixtures resolve
    each offer to a single dataset, so a caller reading the first element would
    be correct until a second dataset declared the same offer and then silently
    wrong — an export made against one dataset's audience and drawn from two.

    **The answer is keyed on the offer, not just filtered by its purpose.**
    ``offer_id`` is passed down to ``get_granted_subject_ids``, so a subject who
    granted a *different* offer over the same dataset is not in this one's
    audience even when the two share a purpose and a recipient role — and,
    conversely, declining a different offer no longer erases this one's grant.
    Purpose alone very nearly separates them and does not quite: two offers may
    name one purpose with different recipients, and `test-flexibility` in the
    connector's own fixture declares no ``recipient_role`` at all.

    **Bounded by `D-14`, as the data plane is.** A wildcard row reaches this
    consumer only if ``_admitted_wildcard_offers`` admits it — the helper
    ``GET /internal/consent/check`` uses — so this route cannot list an audience
    the connector would then refuse to serve.

    An unknown offer is a 422 and a contract-based offer is a 409 — the same two
    answers ``POST /consent/admin/shares`` gives, for the same reasons. An offer
    resolving to no dataset is a 422 as well, matching ``POST /admin/disclosure``:
    an empty ``datasets`` list reads as "nobody consents" when the truth is
    "nothing was asked".
    """
    if consumer_id == consent_service.WILDCARD_CONSUMER:
        raise HTTPException(
            422,
            f"consumer_id '{consent_service.WILDCARD_CONSUMER}' is the standing "
            "wildcard, not a consumer — reading it directly would skip the "
            "per-party opt-outs that override it. Name the consumer the "
            "disclosure is for.",
        )

    try:
        offer = vocab.resolve_offer(offer_id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    if not offer.requires_consent:
        raise HTTPException(
            409,
            f"Offer '{offer.id}' is not consent-based (legal basis "
            f"{offer.legal_basis}) — it is disclosed, not consented",
        )

    try:
        dataset_ids = vocab.datasets_for_offer(offer.id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not dataset_ids:
        raise HTTPException(
            422,
            f"Offer '{offer.id}' resolves to no dataset — there is no audience "
            "to report, and an empty answer would read as 'nobody consents'",
        )

    datasets = []
    for dataset_id in dataset_ids:
        # `consent_required=True` is asserted rather than re-derived per dataset.
        # The offer is consent-based — a 409 above if it were not — and passing
        # `None` would let a dataset whose governance does not gate on consent
        # short-circuit `consent_satisfies` to "allow" for *any* granted row,
        # including one recorded for a different offer's purpose. This is the
        # same assertion `_authorize_dataset` makes on the data plane.
        admitted = await _admitted_wildcard_offers(
            request,
            settings,
            dataset_id=dataset_id,
            consumer_id=consumer_id,
            purposes=[offer.purpose],
            recipient_role=offer.recipients.recipient_role,
        )
        granted = await consent_service.get_granted_subjects(
            db,
            dataset_id,
            consumer_id,
            purpose=[offer.purpose],
            recipient_role=offer.recipients.recipient_role,
            consent_required=True,
            offer_id=offer.id,
            admitted_wildcard_offers=admitted,
        )
        granted = sorted(granted, key=lambda subject: subject.subject_id)
        datasets.append(
            OfferAudienceDataset(
                dataset_id=dataset_id,
                # Derived from the one list, so the two keys cannot disagree
                # about who is in the audience.
                subject_ids=[subject.subject_id for subject in granted],
                subjects=[
                    OfferAudienceSubject(
                        subject_id=subject.subject_id,
                        decided_at=subject.decided_at,
                    )
                    for subject in granted
                ],
                subject_count=len(granted),
            )
        )

    return OfferAudience(
        offer_id=offer.id,
        consumer_id=consumer_id,
        purpose=[offer.purpose],
        recipient_role=offer.recipients.recipient_role,
        datasets=datasets,
    )


@router.get("/my/{consent_id}")
async def get_my_consent(
    consent_id: str,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    x_subject_id = _verify_user(
        x_user_vc, x_subject_id, settings, {"DataSubject", "ConsumerUser"}
    )
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
    x_subject_id = _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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
            consent.negotiation_id,
            consent.id,
            exc,
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
    x_subject_id = _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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
        log.warning(
            "Could not terminate refused negotiation %s: %s", negotiation_id, exc
        )
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
    x_subject_id = _verify_user(x_user_vc, x_subject_id, settings, {"DataSubject"})
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


@router.post("/register-transfer", status_code=200)
async def register_transfer(
    body: TransferRegisterRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_internal_scope),
):
    async with db.begin():
        ok = await consent_service.register_transfer(
            db, body.consent_request_id, body.transfer_id
        )
    return {"registered": ok}
