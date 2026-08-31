"""STS router — issues Self-Issued JWT tokens for DCP authentication.

Replaces the per-participant ds-sts service. All routes are scoped
under /sts/ for clear provenance.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Participant
from ...dependencies import get_db
from ...services.crypto import verify_sts_secret
from ...services.did_resolver import normalize_did_web
from ...services.token import create_si_token

log = logging.getLogger(__name__)

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
    # A URL path decodes `%3A`, so a DID carrying a port arrives spelled
    # differently from the way it is stored. See `normalize_did_web`.
    did = normalize_did_web(did)
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

    # Fail closed: a participant with no stored secret cannot authenticate.
    # `sts_client_secret` is nullable (added by migration 0002) and participants
    # created through POST /admin/participants do not set it — treating "unset"
    # as "no check required" would mint a signed SI token for any caller.
    expected_secret = getattr(participant, "sts_client_secret", None)
    if not expected_secret:
        log.error(
            "STS token request for %s rejected: participant has no sts_client_secret. "
            "Set one via `ir-cli participant set-secret` or POST /admin/participants.",
            did,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )
    if not verify_sts_secret(client_secret, expected_secret):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    # `bearer_access_scope` is what asks the STS to mint an access token; `scope`
    # is the plain OAuth2 parameter. EDC sends the former (`RemoteSecureTokenService`
    # maps the `aud` claim to `audience` and forwards `token` verbatim), so the
    # two are equivalent inputs here and neither is a synonym for the other's
    # absence: with neither, no `token` claim is emitted at all.
    requested_scope = bearer_access_scope or scope

    try:
        jwt_str, expires_in = await create_si_token(
            db,
            did,
            audience=audience,
            bearer_access_scope=requested_scope,
            access_token=token,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "error_description": str(exc)},
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client", "error_description": str(exc)},
        ) from exc

    # Log what was issued, on the success path. An STS that is silent when it
    # mints is one whose output can only be inferred from the failure it causes
    # at the far end — which is how an audience mismatch reads as an opaque
    # "Unauthorized" three services away.
    log.info(
        "STS issued token for %s (aud=%s, grant=%s)",
        did,
        audience or "default",
        (
            "minted"
            if (requested_scope and not token)
            else "passed-through"
            if token
            else "none"
        ),
    )
    return JSONResponse(
        {
            "access_token": jwt_str,
            "token_type": "bearer",
            "expires_in": expires_in,
            "scope": requested_scope or "",
        }
    )
