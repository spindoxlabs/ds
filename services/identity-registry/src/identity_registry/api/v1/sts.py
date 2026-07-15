"""STS router — issues Self-Issued JWT tokens for DCP authentication.

Replaces the per-participant ds-sts service. All routes are scoped
under /sts/ for clear provenance.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Participant
from ...dependencies import get_db
from ...services.crypto import verify_sts_secret
from ...services.token import create_si_token

router = APIRouter(prefix="/sts", tags=["sts"])


@router.post("/{did:path}/token")
async def issue_token(
    did: str,
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str, Form()],
    scope: Annotated[str | None, Form()] = None,
    audience: Annotated[str | None, Form()] = None,
    bearer_access_scope: Annotated[str | None, Form()] = None,
    token: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
):
    """Issue a Self-Issued ID Token (ES256) — OAuth2 client_credentials grant."""
    if grant_type != "client_credentials":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_grant_type"},
        )

    if client_id != did:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    from sqlalchemy import select

    result = await db.execute(
        select(Participant).where(
            Participant.did == did,
            Participant.active.is_(True),
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    expected_secret = getattr(participant, "sts_client_secret", None)
    if expected_secret and not verify_sts_secret(client_secret, expected_secret):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    requested_scope = bearer_access_scope or scope

    try:
        jwt_str, expires_in = await create_si_token(
            db,
            did,
            audience=audience,
            bearer_access_scope=requested_scope,
            access_token=token,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client", "error_description": str(exc)},
        ) from exc

    return JSONResponse({
        "access_token": jwt_str,
        "token_type": "bearer",
        "expires_in": expires_in,
        "scope": requested_scope or "",
    })
