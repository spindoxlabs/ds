"""SI token signing and verification — Self-Issued JWTs for DCP authentication."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models import Key, Participant
from .crypto import (
    _b64url_decode,
    create_jws,
    decrypt_private_jwk,
    load_private_key,
    load_public_key,
    verify_es256,
)


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


class SiTokenInvalid(Exception):
    """A presented DCP self-issued token failed verification."""


async def verify_si_token(
    db: AsyncSession,
    token: str,
    *,
    expected_issuer: str,
    leeway: int = 60,
) -> dict[str, Any]:
    """Verify a DCP self-issued JWT against the issuer's registered public key.

    The DCP credential-service flow authorizes a presentation query with a token
    the holder self-issued through its own STS: ``iss == sub == <holder did>``,
    signed by the key this registry holds for that DID. Verifying the signature
    here is what stops an arbitrary caller from harvesting another participant's
    credentials.

    Returns the decoded claims. Raises :class:`SiTokenInvalid` on any failure —
    never distinguishes *why*, so the endpoint cannot be used as an oracle.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise SiTokenInvalid("malformed token")

    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception as exc:
        raise SiTokenInvalid("undecodable token") from exc

    if header.get("alg") != "ES256":
        raise SiTokenInvalid("unsupported algorithm")

    issuer = claims.get("iss")
    subject = claims.get("sub")
    if not issuer or issuer != subject:
        raise SiTokenInvalid("issuer/subject mismatch")
    if issuer != expected_issuer:
        raise SiTokenInvalid("issuer does not match the requested DID")

    now = int(time.time())
    exp = claims.get("exp")
    if not isinstance(exp, int) or exp + leeway < now:
        raise SiTokenInvalid("token expired or missing exp")
    nbf = claims.get("nbf")
    if isinstance(nbf, int) and nbf - leeway > now:
        raise SiTokenInvalid("token not yet valid")

    key_result = await db.execute(
        select(Key).where(Key.owner_did == issuer, Key.active.is_(True))
    )
    key = key_result.scalar_one_or_none()
    if not key:
        raise SiTokenInvalid("no active key for issuer")

    signing_input = f"{parts[0]}.{parts[1]}".encode()
    if not verify_es256(signing_input, signature, load_public_key(key.public_jwk)):
        raise SiTokenInvalid("bad signature")

    return claims


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

    settings = get_settings()
    raw_jwk = decrypt_private_jwk(key.private_jwk, settings.encryption_key)
    private_key = load_private_key(raw_jwk)
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
