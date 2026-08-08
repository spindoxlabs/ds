"""Admin routes for operational portal views."""
from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ds_auth import Principal

from ...services.prov_bridge import acting_principal
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
from ...services.prov_bridge import ProvBridge

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
    """

    dataset_id: str
    recipient_ref: str
    purpose: list[str] = []
    columns: list[str] = []
    subject_count: int | None = None
    source_ref: str | None = None
    disclosed_by: str | None = None
    agreement_ref: str | None = None
    event_id: str | None = None


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
    """
    try:
        vocab.resolve_dataset(body.dataset_id)
    except vocab.VocabularyError as exc:
        raise HTTPException(422, str(exc)) from exc

    snapshot_hash, granted_count = await consent_service.dataset_consent_snapshot(
        db, body.dataset_id
    )

    if prov is None:
        raise HTTPException(
            503,
            "Provenance is not configured; a disclosure cannot be recorded and "
            "so must not proceed (rulebook L-1).",
        )

    try:
        await prov.data_disclosed(
            dataset_id=body.dataset_id,
            consent_snapshot_hash=snapshot_hash,
            recipient_ref=body.recipient_ref,
            purpose=body.purpose,
            columns=body.columns,
            subject_count=body.subject_count,
            source_ref=body.source_ref,
            disclosed_by=body.disclosed_by or settings.participant_id,
            agreement_ref=body.agreement_ref,
            event_id=body.event_id,
        )
    except Exception as exc:  # noqa: BLE001 — the reason is the caller's to see
        raise HTTPException(
            502, f"Disclosure not recorded, so it must not proceed: {exc}"
        ) from exc

    return {
        "status": "recorded",
        "dataset_id": body.dataset_id,
        "consent_snapshot_hash": snapshot_hash,
        "granted_party_count": granted_count,
    }
