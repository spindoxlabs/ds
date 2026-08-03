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
from ...dependencies import get_db, get_did_resolver, require_credential_read
from ...schemas.responses import CredentialCheckResponse
from ...services.did_resolver import DidResolver, normalize_did_web
from ...services.presentation import (
    build_presentation_response,
    credential_types_for,
    types_from_presentation_definition,
)
from ...services.token import SiTokenInvalid, verify_presentation_authorization

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
    resolver: DidResolver = Depends(get_did_resolver),
):
    """Return a Verifiable Presentation containing matching VCs.

    Implements the DCP Credential Service presentations/query endpoint
    (`verifiable.presentation.protocol.md` §Resolution API).

    **The caller is the verifier, not the holder.** It presents its own
    Self-Issued ID token — proving control of its DID, checked against that DID's
    document — carrying in the ``token`` claim the grant *this* participant's STS
    minted for it. Both are verified; the grant's scope bounds what comes back.

    This endpoint previously required the caller to *be* ``did``, which no DCP
    verifier ever is: it rejected every conformant request and served none, and
    the EDC's demo identity fallback hid that for as long as it existed.
    """
    did = normalize_did_web(did)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing DCP self-issued access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        grant = await verify_presentation_authorization(
            db, authorization[7:].strip(), participant_did=did, resolver=resolver
        )
    except SiTokenInvalid as exc:
        log.warning("Rejected presentation query for %s: %s", did, exc)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid DCP self-issued access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    scopes = body.get("scope") or []
    if isinstance(scopes, str):
        scopes = [scopes]
    presentation_definition = body.get("presentationDefinition") or {}

    # The spec makes this an error rather than a precedence question: a request
    # carrying both says two different things about what it wants.
    if scopes and presentation_definition:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A query carries either scope or presentationDefinition, not both",
        )
    if not scopes and not presentation_definition:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A query must carry either scope or presentationDefinition",
        )

    requested_types = (
        credential_types_for(scopes)
        if scopes
        else types_from_presentation_definition(presentation_definition)
    )

    try:
        response = await build_presentation_response(
            db,
            did,
            granted_types=credential_types_for(grant.scopes),
            requested_types=requested_types,
            audience=grant.verifier_did,
        )
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    # An enforcement point that is silent when it permits cannot be told apart
    # from one that never ran — the `NegotiationConsentValidator` lesson, and the
    # reason a green e2e is evidence that real DCP verification happened.
    log.info(
        "Presentation served for %s to verifier %s (granted=%s, requested=%s)",
        did,
        grant.verifier_did,
        " ".join(grant.scopes),
        " ".join(sorted(requested_types)) or "-",
    )
    return JSONResponse(content=response, media_type="application/ld+json")
