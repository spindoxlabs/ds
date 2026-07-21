"""Authentication on the DCP-facing endpoints (STS + credential service).

These two endpoints hand out signed identity material — an SI token and a
Verifiable Presentation respectively. Both were reachable without proving
control of the DID they act for; these tests pin the fix.
"""
from __future__ import annotations

import time

import pytest

from identity_registry.services.crypto import create_jws, load_private_key
from identity_registry.services.token import SiTokenInvalid, verify_si_token

from conftest import make_admin_headers

HEADERS = make_admin_headers()
TEST_DID = "did:web:provider.dataspaces.localhost"
OTHER_DID = "did:web:attacker.dataspaces.localhost"


async def _create_participant(client, did: str = TEST_DID) -> None:
    r = await client.post(
        "/admin/participants",
        json={"did": did, "role": "provider", "allowed_scopes": ["dataspaces.query"]},
        headers=HEADERS,
    )
    assert r.status_code == 201


async def _si_token_for(db_session, did: str, *, ttl: int = 300) -> str:
    """Mint a valid SI token the way the participant's own STS would."""
    from sqlalchemy import select

    from identity_registry.config import get_settings
    from identity_registry.db.models import Key
    from identity_registry.services.crypto import decrypt_private_jwk

    key = (
        await db_session.execute(
            select(Key).where(Key.owner_did == did, Key.active.is_(True))
        )
    ).scalar_one()
    raw = decrypt_private_jwk(key.private_jwk, get_settings().encryption_key)
    now = int(time.time())
    return create_jws(
        {"alg": "ES256", "kid": key.kid},
        {"iss": did, "sub": did, "iat": now, "exp": now + ttl},
        load_private_key(raw),
    )


# ── Credential service (DCP presentations/query) ────────────────────────────


@pytest.mark.asyncio
async def test_presentation_query_without_token_is_rejected(client):
    await _create_participant(client)
    r = await client.post(
        f"/credentials/{TEST_DID}/presentations/query", json={}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_presentation_query_with_unsigned_token_is_rejected(client):
    """A base64 payload with a garbage signature must not be accepted."""
    await _create_participant(client)
    import base64
    import json

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(d).encode()
        ).rstrip(b"=").decode()

    now = int(time.time())
    forged = (
        f"{b64({'alg': 'ES256'})}."
        f"{b64({'iss': TEST_DID, 'sub': TEST_DID, 'exp': now + 300})}."
        "AAAA"
    )
    r = await client.post(
        f"/credentials/{TEST_DID}/presentations/query",
        json={},
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_presentation_query_with_valid_token_succeeds(client, db_session):
    await _create_participant(client)
    token = await _si_token_for(db_session, TEST_DID)
    r = await client.post(
        f"/credentials/{TEST_DID}/presentations/query",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_presentation_query_rejects_token_for_another_did(client, db_session):
    """Holding your own valid token must not let you query someone else's VCs."""
    await _create_participant(client, TEST_DID)
    await _create_participant(client, OTHER_DID)
    attacker_token = await _si_token_for(db_session, OTHER_DID)
    r = await client.post(
        f"/credentials/{TEST_DID}/presentations/query",
        json={},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert r.status_code == 401


# ── SI token verification unit-level ────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_si_token_rejects_expired(client, db_session):
    await _create_participant(client)
    token = await _si_token_for(db_session, TEST_DID, ttl=-600)
    with pytest.raises(SiTokenInvalid):
        await verify_si_token(db_session, token, expected_issuer=TEST_DID)


@pytest.mark.asyncio
async def test_verify_si_token_rejects_issuer_subject_mismatch(client, db_session):
    from sqlalchemy import select

    from identity_registry.config import get_settings
    from identity_registry.db.models import Key
    from identity_registry.services.crypto import decrypt_private_jwk

    await _create_participant(client)
    key = (
        await db_session.execute(
            select(Key).where(Key.owner_did == TEST_DID, Key.active.is_(True))
        )
    ).scalar_one()
    raw = decrypt_private_jwk(key.private_jwk, get_settings().encryption_key)
    now = int(time.time())
    token = create_jws(
        {"alg": "ES256", "kid": key.kid},
        {"iss": TEST_DID, "sub": OTHER_DID, "iat": now, "exp": now + 300},
        load_private_key(raw),
    )
    with pytest.raises(SiTokenInvalid):
        await verify_si_token(db_session, token, expected_issuer=TEST_DID)


# ── STS token issuance ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sts_rejects_participant_without_stored_secret(client):
    """Participants created via /admin/participants have no sts_client_secret.

    Before the fix the secret check was skipped entirely for these, and the
    endpoint minted a signed SI token for any caller.
    """
    await _create_participant(client)
    r = await client.post(
        f"/sts/{TEST_DID}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": TEST_DID,
            "client_secret": "anything-at-all",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_client"
