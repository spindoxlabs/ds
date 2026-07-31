"""Credentials router — DCP Credential Service (VP queries).

Replaces the per-participant ds-vc-wallet service. All routes are scoped
under /credentials/ for clear provenance.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Credential
from ...dependencies import get_db, require_credential_read
from ...schemas.responses import CredentialCheckResponse
from ...services.presentation import build_presentation_response
from ...services.token import SiTokenInvalid, verify_si_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["credentials"])


# Declared before the `{did:path}` route below, which matches anything. Different
# methods today, so nothing collides — but a path catch-all that precedes its
# siblings is how `POST /catalog/search` came to 404 as a missing dataset.
@router.get("/check", response_model=CredentialCheckResponse)
async def check_credential(
    subject_did: str = Query(...),
    type: str = Query(..., description="Credential type, e.g. OrganizationCredential"),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_credential_read),
):
    """Does *subject_did* hold a **valid** credential of *type*?

    The service question behind a sharing offer's `admitted_by`, and the sibling
    of `GET /memberships/check`. It answers a boolean, not a credential list —
    the caller is deciding admission and needs nothing else, and enumerating what
    a person holds is a disclosure `GET /admin/credentials` keeps behind `admin`.

    **Valid means active and unexpired**, both checked here rather than by the
    caller. The connector previously asked `/admin/credentials` for the list and
    read a `revoked` field the response has never had — so every entry read as
    *not revoked*, and any credential of any type would have admitted anyone. It
    was saved only by the 403 it got for want of the admin grant: a fail-closed
    accident standing in for a check. Deciding validity where the state lives is
    what stops that recurring.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(Credential).where(
            Credential.subject_did == subject_did,
            Credential.credential_type == type,
            Credential.status == "active",
        )
    )
    holds = any(
        cred.expires_at is None or _as_utc(cred.expires_at) > now
        for cred in result.scalars().all()
    )
    return CredentialCheckResponse(
        subject_did=subject_did, credential_type=type, holds=holds
    )


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back a naive datetime where Postgres hands back an aware one."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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
