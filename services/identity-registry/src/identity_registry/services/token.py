"""SI token signing — issues Self-Issued JWTs for DCP authentication."""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Key, Participant
from .crypto import create_jws, load_private_key


async def get_participant_key(
    db: AsyncSession, participant_did: str
) -> tuple[Key, Participant]:
    result = await db.execute(
        select(Participant).where(
            Participant.did == participant_did,
            Participant.active.is_(True),
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise LookupError(f"Participant not found or inactive: {participant_did}")

    key_result = await db.execute(
        select(Key).where(
            Key.owner_did == participant_did,
            Key.active.is_(True),
        )
    )
    key = key_result.scalar_one_or_none()
    if not key:
        raise LookupError(f"No active key for participant: {participant_did}")

    return key, participant


async def create_si_token(
    db: AsyncSession,
    participant_did: str,
    *,
    audience: str | None = None,
    bearer_access_scope: str | None = None,
    access_token: str | None = None,
    token_ttl: int = 300,
) -> tuple[str, int]:
    """Sign an SI JWT using the participant's private key from the DB.

    Returns (jwt_string, expires_in).
    """
    key, _participant = await get_participant_key(db, participant_did)

    private_key = load_private_key(key.private_jwk)
    now = int(time.time())

    claims: dict[str, Any] = {
        "iss": participant_did,
        "sub": participant_did,
        "aud": [audience or "https://w3id.org/dspace/2024/1/dsp"],
        "iat": now,
        "exp": now + token_ttl,
        "jti": str(uuid.uuid4()),
    }
    if bearer_access_scope:
        claims["bearer_access_scope"] = bearer_access_scope
        claims["bearerAccessScope"] = bearer_access_scope
    claims["token"] = access_token or str(uuid.uuid4())

    header = {"alg": "ES256", "kid": key.kid}
    jwt_str = create_jws(header, claims, private_key)
    return jwt_str, token_ttl
