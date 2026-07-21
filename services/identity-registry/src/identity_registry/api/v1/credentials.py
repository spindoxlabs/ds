"""Credentials router — DCP Credential Service (VP queries).

Replaces the per-participant ds-vc-wallet service. All routes are scoped
under /credentials/ for clear provenance.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...services.presentation import build_presentation_response
from ...services.token import SiTokenInvalid, verify_si_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.post("/{did:path}/presentations/query")
async def query_presentations(
    did: str,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return a Verifiable Presentation containing matching VCs.

    Implements the DCP Credential Service presentations/query endpoint.

    Authorization is the DCP self-issued access token: the caller proves it
    controls ``did`` by presenting a JWT signed with that DID's registered key.
    Without this check the endpoint hands any caller a signed VP containing the
    subject's full credential set — i.e. participant impersonation.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing DCP self-issued access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        await verify_si_token(db, authorization[7:].strip(), expected_issuer=did)
    except SiTokenInvalid as exc:
        log.warning("Rejected presentation query for %s: %s", did, exc)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid DCP self-issued access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    presentation_definition = body.get("presentationDefinition", {})

    try:
        response = await build_presentation_response(
            db, did, presentation_definition
        )
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    return JSONResponse(content=response, media_type="application/ld+json")
