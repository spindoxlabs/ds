"""Admin routes for operational portal views."""

from __future__ import annotations

import inspect

from ds_auth import Principal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import (
    get_db,
    get_participant_registry,
    get_prov,
    get_settings_dep,
    require_disclosure_record,
    require_ingestion_record,
    require_provider_read,
)
from ...registry.participants import HttpParticipantRegistry, ParticipantRegistry
from ...services import consent_service
from ...services import consent_vocabulary as vocab
from ...services.prov_bridge import ProvBridge, acting_principal

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/participants")
async def list_participants(
    registry: ParticipantRegistry = Depends(get_participant_registry),
    # A read of registry state the provider console renders, so it is reachable
    # with the provider read grant. Admin still satisfies it (superset) — the
    # point is that the portal no longer needs admin to show this page.
    _claims: dict = Depends(require_provider_read),
):
    # Two registries satisfy this dependency and they disagree on async:
    # `HttpParticipantRegistry.all()` is a coroutine (the deployed path, backed by
    # the identity-registry), while the YAML-seeded `ParticipantRegistry.all()` is
    # not. Awaiting unconditionally breaks the seeded one; not awaiting yielded
    # `TypeError: 'coroutine' object is not iterable` and a 500 on every read.
    # Read through the cache. This page is an operator looking at registry state
    # they may have just changed; serving it from a 60s cache shows a list
    # without the participant they created, which is indistinguishable from the
    # promote having failed. The cache is for the per-negotiation membership
    # checks, not for this.
    participants = (
        registry.all(fresh=True)
        if isinstance(registry, HttpParticipantRegistry)
        else registry.all()
    )
    if inspect.isawaitable(participants):
        participants = await participants

    return [
        {
            "id": participant.id,
            # A participant can hold several roles since `fdf7d6a`. `role` is kept
            # as the first one so existing readers keep working, but `roles` is the
            # truth — a provider that is also a consumer is not an edge case.
            "roles": participant.roles,
            "role": participant.roles[0] if participant.roles else None,
            "dsp_address": participant.dsp_address,
            "dsp_endpoint": participant.dsp_address,
            "allowed_scopes": participant.allowed_scopes,
            "scopes": participant.allowed_scopes,
        }
        for participant in participants
    ]


class IngestionRecord(BaseModel):
    """A DSO / offline data handover, recorded by the operator who performed it.

    The DSO leg is manual in phase A, so ``DataIngested`` has no automatic
    trigger — this endpoint lets the operator record the handover as they do it.
    ``source_ref`` and ``agreement_ref`` identify the handover and its DPA, never
    their contents; no PII is accepted or stored.
    """

    dataset_id: str
    source_ref: str | None = None
    record_count: int | None = None
    agreement_ref: str | None = None
    event_id: str | None = None


@router.post("/ingestion")
async def record_ingestion(
    body: IngestionRecord,
    # An offline handover is a person's decision; the record has to say whose.
    principal: Principal = Depends(require_ingestion_record),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    prov: ProvBridge | None = Depends(get_prov),
):
    """Record a data-ingestion handover and emit a ``DataIngested`` event.

    The connector computes the ``consent_snapshot_hash`` itself from its own
    consent DB — the sorted, recomputable fingerprint of the granted consent
    state that authorised the handover — so the record proves *which* consent
    state was in force without the provenance store holding any subject data.
    """
    try:
        vocab.resolve_dataset(body.dataset_id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    snapshot_hash, granted_count = await consent_service.dataset_consent_snapshot(
        db, body.dataset_id
    )

    if prov is not None:
        await prov.data_ingested(
            dataset_id=body.dataset_id,
            provider_id=settings.participant_id,
            source_ref=body.source_ref,
            record_count=body.record_count,
            consent_snapshot_hash=snapshot_hash,
            agreement_ref=body.agreement_ref,
            event_id=body.event_id,
            acted_by=acting_principal(principal),
        )

    return {
        "status": "recorded",
        "dataset_id": body.dataset_id,
        "consent_snapshot_hash": snapshot_hash,
        "granted_party_count": granted_count,
    }


class DisclosureRecord(BaseModel):
    """Data leaving the platform to a named recipient, recorded as it happens.

    ``columns`` are column *names*, never values (GDPR Art. 13/14), and
    ``recipient_ref`` / ``source_ref`` / ``agreement_ref`` are opaque handles —
    an org alias, a slug, a DPA reference — so nothing here is PII.

    The caller does **not** supply ``consent_snapshot_hash``. It is not an input
    a discloser could honestly provide: it is a fingerprint of *this* connector's
    consent DB at the moment of the handover, and a caller passing one would be
    asserting a consent state it cannot read.

    **Name a dataset or an offer, and exactly one.** A dataset is what the record
    is about, so `L-2`'s hash stays dataset-scoped either way. An offer is what
    the *caller* has: an export scoped to one sharing offer selects the supply
    points whose owners consented to that offer, and it never learns which
    datasets back it — `D-13` keeps those keys out of the public projection, so
    the mapping is not something a caller can be expected to hold. Naming both
    would be two answers to one question, and naming neither is not a disclosure
    of anything.
    """

    dataset_id: str | None = None
    offer_id: str | None = None
    recipient_ref: str
    purpose: list[str] = []
    columns: list[str] = []
    subject_count: int | None = None
    source_ref: str | None = None
    disclosed_by: str | None = None
    agreement_ref: str | None = None
    event_id: str | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> DisclosureRecord:
        if bool(self.dataset_id) == bool(self.offer_id):
            raise ValueError("Name exactly one of 'dataset_id' or 'offer_id'")
        return self


def _event_id_for(
    caller_event_id: str | None, dataset_id: str, offer_scoped: bool
) -> str | None:
    """The idempotency key for one dataset's `DataDisclosed`.

    The provenance service dedupes on ``event_id`` (`L-4`), so emitting several
    events under one caller-supplied id records the first and discards the rest as
    duplicates — an offer expanding to three datasets would leave one event and a
    200 saying three. The offer form therefore derives a per-dataset key from the
    caller's, which keeps a retry idempotent while keeping the datasets distinct.

    Derived on the **offer form as such**, not on "more than one dataset resolved".
    Keying on the count would silently change every key the day a second dataset
    declares an offer, so a retry of a disclosure recorded before that day would
    record a second copy.

    A caller that supplies no id gets ``None`` and the provenance service derives
    one from the event's own payload — which contains ``dataset_id``, so the
    datasets already differ.
    """
    if caller_event_id is None:
        return None
    return f"{caller_event_id}:{dataset_id}" if offer_scoped else caller_event_id


@router.post("/disclosure")
async def record_disclosure(
    body: DisclosureRecord,
    principal: Principal = Depends(require_disclosure_record),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    prov: ProvBridge | None = Depends(get_prov),
):
    """Record an outbound disclosure and emit a ``DataDisclosed`` event.

    The counterpart to ``POST /admin/ingestion``, and it exists for the reason
    rulebook `L-2` was unenforceable without it. `L-2` requires a `DataDisclosed`
    to carry a recomputable `consent_snapshot_hash`; the only producer of that
    event was an out-of-repo service posting to `POST /prov/events` directly, and
    that service cannot compute the hash — it is derived from the granted consent
    rows in *this* connector's database. The rule asked the one component that
    could not comply for the one field it could not produce.

    So the hash is computed here, from the same
    ``consent_service.dataset_consent_snapshot`` that backs ``/admin/ingestion``,
    and returned to the caller as well as recorded — a discloser needs it to
    reconcile its own audit trail.

    **Emission is fatal here.** `L-1`'s failure policy is chosen by position: an
    event describing something that has *already happened* is retried and
    non-fatal, because refusing loses the fact as well. A disclosure recorded
    through this route has not happened yet — the caller is about to hand the
    data over — so a 502 means no disclosure, and that is the answer that leaves
    no unrecorded handover.

    **`offer_id` is an alternative argument, not a replacement.** It is here
    because the caller this route was built for — an onboarding service exporting
    a POD list — is scoped to one sharing offer and cannot reach a dataset key:
    `D-13` keeps those out of the public projection deliberately, and
    `libs/ds-e2e`'s `consent_purpose` flow fails when they leak. So the route
    resolves the offer through ``vocab.datasets_for_offer`` — the same authority
    ``POST /consent/admin/shares`` expands an offer with, on the other side of the
    same seam — and emits **one `DataDisclosed` per resolved dataset**, each
    carrying that dataset's own hash. `L-2` is untouched: the hash stays
    dataset-scoped and stays recomputable.

    **The expansion belongs here rather than in the caller.**
    ``datasets_for_offer`` returns a list. Today's fixture resolves every offer to
    a single dataset only because one dataset declares all three, so a caller that
    read the first element would be correct until a second dataset declared the
    same offer and then silently wrong — a disclosure recorded against one dataset
    and made from two. Expanded server-side, that day produces a second event
    instead of a caller bug.

    **The response names the datasets, and that is not a `D-13` leak.** `D-13`
    keeps dataset keys out of the *public projection* — the surface an onboarding
    wizard renders before anyone has an identity. This is an authenticated
    response to the party that just recorded the handover, and it is the same
    reason the hash is returned: a discloser needs both to reconcile its own audit
    trail against the events in the graph.

    **A contract-based offer is accepted.** Unlike ``POST /consent/admin/shares``,
    which refuses one because provisioning consent for it would manufacture a
    choice that does not exist, a disclosure is a record of a handover that
    happened whatever its legal basis. The snapshot over a dataset nobody has
    consented to is the hash of an empty set, and that is a true statement about
    the consent state, not a missing one.

    **Partial emission is possible on the offer form and is reported.** The
    datasets are emitted in turn and a failure part-way refuses the whole request
    with a 502 naming what was already recorded. That leaves events describing a
    handover the caller was then told not to make — an over-record — which is the
    tolerable direction: the alternative is a handover with no record, which is
    the one `L-1` positions this route to prevent.
    """
    try:
        if body.offer_id:
            # Resolve the offer first, so an unknown offer id is a 422 about the
            # offer rather than an empty dataset list read as "reaches nothing".
            vocab.resolve_offer(body.offer_id)
            dataset_ids = vocab.datasets_for_offer(body.offer_id)
            if not dataset_ids:
                raise HTTPException(
                    422,
                    f"Offer '{body.offer_id}' resolves to no dataset — nothing "
                    "was disclosed under it and there is nothing to record",
                )
        else:
            # Neither form was given. No model validator enforces one-of, so
            # without this the `None` reached `resolve_dataset` and surfaced as
            # whatever that made of it — a 422 about a dataset id the caller
            # never sent, or worse a lookup for the key `None`.
            if not body.dataset_id:
                raise HTTPException(
                    422,
                    "name either offer_id or dataset_id — a disclosure record "
                    "has to say what was disclosed",
                )
            vocab.resolve_dataset(body.dataset_id)
            dataset_ids = [body.dataset_id]
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    if prov is None:
        raise HTTPException(
            503,
            "Provenance is not configured; a disclosure cannot be recorded and "
            "so must not proceed (rulebook L-1).",
        )

    recorded: list[dict] = []
    for dataset_id in dataset_ids:
        snapshot_hash, granted_count = await consent_service.dataset_consent_snapshot(
            db, dataset_id
        )
        try:
            await prov.data_disclosed(
                dataset_id=dataset_id,
                consent_snapshot_hash=snapshot_hash,
                recipient_ref=body.recipient_ref,
                purpose=body.purpose,
                columns=body.columns,
                subject_count=body.subject_count,
                source_ref=body.source_ref,
                disclosed_by=body.disclosed_by or settings.participant_id,
                agreement_ref=body.agreement_ref,
                event_id=_event_id_for(body.event_id, dataset_id, bool(body.offer_id)),
            )
        except Exception as exc:  # noqa: BLE001 — the reason is the caller's to see
            raise HTTPException(
                502,
                f"Disclosure not recorded for '{dataset_id}', so it must not "
                f"proceed: {exc}"
                + (
                    f" (already recorded: {[r['dataset_id'] for r in recorded]})"
                    if recorded
                    else ""
                ),
            ) from exc
        recorded.append(
            {
                "dataset_id": dataset_id,
                "consent_snapshot_hash": snapshot_hash,
                "granted_party_count": granted_count,
            }
        )

    response: dict = {"status": "recorded", "disclosures": recorded}
    if body.offer_id:
        # Deliberately **not** also flattened to the single-dataset keys, even
        # when the offer happens to resolve to one dataset. The response shape
        # follows the argument, not the resolution count — otherwise a caller
        # reading `dataset_id` works on today's fixture and silently reads one of
        # several the day a second dataset declares the offer, which is the trap
        # this route expands server-side to avoid.
        response["offer_id"] = body.offer_id
    else:
        response.update(recorded[0])
    return response
