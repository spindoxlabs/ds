"""Admin routes for operational portal views."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import (
    get_db,
    get_participant_registry,
    get_prov,
    get_settings_dep,
    require_admin_scope,
    require_ingestion_record,
)
from ...registry.participants import ParticipantRegistry
from ...services import consent_service
from ...services import consent_vocabulary as vocab
from ...services.prov_bridge import ProvBridge

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/participants")
async def list_participants(
    registry: ParticipantRegistry = Depends(get_participant_registry),
    _claims: dict = Depends(require_admin_scope),
):
    return [
        {
            "id": participant.id,
            "role": participant.role,
            "dsp_address": participant.dsp_address,
            "dsp_endpoint": participant.dsp_address,
            "allowed_scopes": participant.allowed_scopes,
            "scopes": participant.allowed_scopes,
        }
        for participant in registry.all()
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
    _claims: dict = Depends(require_ingestion_record),
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
        )

    return {
        "status": "recorded",
        "dataset_id": body.dataset_id,
        "consent_snapshot_hash": snapshot_hash,
        "granted_party_count": granted_count,
    }
