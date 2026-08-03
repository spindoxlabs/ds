"""DCP self-issued tokens — issuance by the STS, verification by the credential service.

Two token kinds travel together and are easy to confuse, so they are named apart
here. Both are ES256 JWTs; the difference is who signs and who is named:

**Self-Issued ID token** — proves *who is speaking*. ``iss == sub == the
speaker's DID``, ``aud == the party being spoken to``. Signed by the speaker,
verified by the receiver against the speaker's **DID document**.

**Access token** — proves *what the speaker was granted*. Minted by the holder's
STS, carried inside the SI token's ``token`` claim, and handed back to the
holder's own credential service by the verifier. Signed by the **holder**, so the
holder verifies its own grant.

The shapes are not ours to choose; they are what the counterparty EDC produces
and expects (``EmbeddedSecureTokenService``, ``SelfIssuedTokenVerifierImpl``) and
what the DCP specification requires. Given an SI request ``{iss: holder, sub:
holder, aud: verifier}`` with a ``bearer_access_scope``:

===============  ===========================================================
access.iss       the holder — inherited from the SI request
access.aud       the holder — the SI token's ``iss``
access.sub       the **verifier** — the SI token's ``aud``
access.scope     the granted ``bearer_access_scope``
===============  ===========================================================

That crossover is the binding: the credential service can tell that the party
presenting the access token is the party its own STS minted it for.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
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
from .did_resolver import DidResolutionError, DidResolver, verification_key

#: What EDC's DSP leg names as audience when a counterparty DID is not supplied.
DEFAULT_DSP_AUDIENCE = "https://w3id.org/dspace/2024/1/dsp"

#: Clock-skew tolerance, in seconds. Upstream allows 5; 60 keeps a developer's
#: unsynchronised laptop out of the failure modes without widening a replay window
#: that `jti` does not yet close.
DEFAULT_LEEWAY = 60


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
    """A presented DCP token failed verification."""


@dataclass
class DecodedJwt:
    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes

    @property
    def kid(self) -> str | None:
        kid = self.header.get("kid")
        return kid if isinstance(kid, str) else None


@dataclass
class PresentationGrant:
    """What a verified presentation request is allowed to see."""

    verifier_did: str
    scopes: list[str] = field(default_factory=list)


def decode_jwt(token: str) -> DecodedJwt:
    """Split and decode a compact JWS. Does **not** verify the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        raise SiTokenInvalid("malformed token")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception as exc:
        raise SiTokenInvalid("undecodable token") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise SiTokenInvalid("token header or claims are not objects")
    if header.get("alg") != "ES256":
        raise SiTokenInvalid("unsupported algorithm")
    return DecodedJwt(
        header=header,
        claims=claims,
        signing_input=f"{parts[0]}.{parts[1]}".encode(),
        signature=signature,
    )


def audience_values(claims: dict[str, Any]) -> list[str]:
    """``aud`` is a string or an array of strings; normalise it to a list."""
    aud = claims.get("aud")
    if aud is None:
        return []
    if isinstance(aud, str):
        return [aud]
    if isinstance(aud, list):
        return [value for value in aud if isinstance(value, str)]
    return []


def check_time_claims(claims: dict[str, Any], *, leeway: int, what: str) -> None:
    now = int(time.time())
    exp = claims.get("exp")
    if not isinstance(exp, int) or exp + leeway < now:
        raise SiTokenInvalid(f"{what} expired or missing exp")
    nbf = claims.get("nbf")
    if isinstance(nbf, int) and nbf - leeway > now:
        raise SiTokenInvalid(f"{what} not yet valid")
    iat = claims.get("iat")
    if isinstance(iat, int) and iat - leeway > now:
        raise SiTokenInvalid(f"{what} issued in the future")


# ── Issuance ────────────────────────────────────────────────────────────────


async def create_access_token(
    db: AsyncSession,
    holder_did: str,
    *,
    verifier_did: str,
    scope: str,
    token_ttl: int = 300,
) -> str:
    """Mint the grant a verifier will hand back to *holder_did*'s credential service.

    Self-contained on purpose: it is signed by the holder's key, so the holder
    can verify its own grant with no server-side record. The alternative — an
    opaque handle in a table — is what upstream avoids too, and it would need a
    store, an expiry sweep and a replication story for a value that lives 5
    minutes.
    """
    key, _participant = await get_participant_key(db, holder_did)
    settings = get_settings()
    private_key = load_private_key(
        decrypt_private_jwk(key.private_jwk, settings.encryption_key)
    )
    now = int(time.time())
    claims = {
        "iss": holder_did,
        "aud": [holder_did],
        "sub": verifier_did,
        "scope": scope,
        "iat": now,
        "exp": now + token_ttl,
        "jti": f"accesstoken-{uuid.uuid4()}",
    }
    return create_jws({"alg": "ES256", "kid": key.kid}, claims, private_key)


async def create_si_token(
    db: AsyncSession,
    participant_did: str,
    *,
    audience: str | None = None,
    bearer_access_scope: str | None = None,
    access_token: str | None = None,
    token_ttl: int = 300,
) -> tuple[str, int]:
    """Sign a Self-Issued ID token for *participant_did*.

    ``access_token`` is passed through when the caller already holds one — that
    is the verifier's leg, wrapping the grant it received in its own SI token.
    ``bearer_access_scope`` is the holder's leg, asking for a grant to be minted.

    With neither, **no ``token`` claim is emitted**: the DCP specification says a
    token claim SHOULD NOT be included when no ``bearer_access_scope`` was
    requested. Emitting one unconditionally — as this did, with a random UUID —
    put a value into the protocol that nothing could ever validate.
    """
    key, _participant = await get_participant_key(db, participant_did)

    settings = get_settings()
    raw_jwk = decrypt_private_jwk(key.private_jwk, settings.encryption_key)
    private_key = load_private_key(raw_jwk)
    now = int(time.time())

    claims: dict[str, Any] = {
        "iss": participant_did,
        "sub": participant_did,
        "aud": [audience or DEFAULT_DSP_AUDIENCE],
        "iat": now,
        "exp": now + token_ttl,
        "jti": str(uuid.uuid4()),
    }

    if access_token:
        claims["token"] = access_token
    elif bearer_access_scope:
        if not audience:
            # The access token's `sub` is the audience. Without one there is no
            # party to bind the grant to, and an unbound grant is a bearer token
            # for anybody who obtains it.
            raise ValueError(
                "bearer_access_scope requires an audience — the grant is bound to it"
            )
        claims["token"] = await create_access_token(
            db,
            participant_did,
            verifier_did=audience,
            scope=bearer_access_scope,
            token_ttl=token_ttl,
        )

    if bearer_access_scope:
        claims["bearer_access_scope"] = bearer_access_scope

    jwt_str = create_jws({"alg": "ES256", "kid": key.kid}, claims, private_key)
    return jwt_str, token_ttl


# ── Verification ────────────────────────────────────────────────────────────


async def verify_presentation_authorization(
    db: AsyncSession,
    token: str,
    *,
    participant_did: str,
    resolver: DidResolver,
    leeway: int = DEFAULT_LEEWAY,
) -> PresentationGrant:
    """Authorize a presentation query against *participant_did*'s credentials.

    The caller is the **verifier** — a counterparty asking to see credentials —
    never the holder. This function used to require the opposite, and that single
    comparison is why real DCP verification has never completed on the DSP leg:
    the shape the specification mandates was rejected 100% of the time.

    Two tokens, checked in order:

    1. the outer Self-Issued ID token, proving the verifier controls ``iss``,
       verified against the key in ``iss``'s **DID document**;
    2. the ``token`` claim it carries, proving *this* participant's STS granted
       that verifier a scope, verified against this participant's **own** key.

    Returns the granted scopes. Raises :class:`SiTokenInvalid` on any failure,
    without distinguishing which — the endpoint must not be an oracle.
    """
    outer = decode_jwt(token)
    issuer = outer.claims.get("iss")
    subject = outer.claims.get("sub")

    if not isinstance(issuer, str) or not issuer:
        raise SiTokenInvalid("missing iss")
    if issuer != subject:
        raise SiTokenInvalid("issuer/subject mismatch")
    if participant_did not in audience_values(outer.claims):
        raise SiTokenInvalid("audience does not name the requested participant")
    check_time_claims(outer.claims, leeway=leeway, what="self-issued token")

    try:
        document = await resolver.resolve(issuer)
        jwk = verification_key(document, outer.kid)
    except DidResolutionError as exc:
        raise SiTokenInvalid(f"cannot resolve the verifier's key: {exc}") from exc

    if not verify_es256(outer.signing_input, outer.signature, load_public_key(jwk)):
        raise SiTokenInvalid("bad signature on the self-issued token")

    access_token = outer.claims.get("token")
    if not isinstance(access_token, str) or not access_token:
        raise SiTokenInvalid("no access token presented")

    grant = decode_jwt(access_token)
    if grant.claims.get("sub") != subject:
        # The grant names the party it was minted for. If that is not the party
        # presenting it, a verifier is replaying somebody else's grant.
        raise SiTokenInvalid("access token was not granted to this verifier")
    if participant_did not in audience_values(grant.claims):
        raise SiTokenInvalid("access token was not issued for this participant")
    check_time_claims(grant.claims, leeway=leeway, what="access token")

    local_key = (
        await db.execute(
            select(Key).where(Key.owner_did == participant_did, Key.active.is_(True))
        )
    ).scalar_one_or_none()
    if not local_key:
        raise SiTokenInvalid("no active key for the requested participant")
    if grant.kid and grant.kid != local_key.kid:
        raise SiTokenInvalid("access token was signed by an unknown key")
    if not verify_es256(
        grant.signing_input, grant.signature, load_public_key(local_key.public_jwk)
    ):
        raise SiTokenInvalid("access token was not signed by this participant")

    scope = grant.claims.get("scope")
    if not isinstance(scope, str) or not scope.strip():
        raise SiTokenInvalid("access token carries no scope")

    return PresentationGrant(verifier_did=issuer, scopes=scope.split())
