"""Admin routes for operational portal views."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...dependencies import get_participant_registry
from ...registry.participants import ParticipantRegistry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/participants")
async def list_participants(
    registry: ParticipantRegistry = Depends(get_participant_registry),
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
