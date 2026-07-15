"""Credentials router — DCP Credential Service (VP queries).

Replaces the per-participant ds-vc-wallet service. All routes are scoped
under /credentials/ for clear provenance.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...services.presentation import build_presentation_response

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.post("/{did:path}/presentations/query")
async def query_presentations(
    did: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Return a Verifiable Presentation containing matching VCs.

    Implements the DCP Credential Service presentations/query endpoint.
    """
    presentation_definition = body.get("presentationDefinition", {})

    try:
        response = await build_presentation_response(
            db, did, presentation_definition
        )
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    return JSONResponse(content=response, media_type="application/ld+json")
