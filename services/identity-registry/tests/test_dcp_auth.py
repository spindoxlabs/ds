"""Authentication on the DCP-facing endpoints (STS + credential service).

**These tests were rewritten**, not extended. The previous set asserted that a
presentation query is answered only for a token signed by the *requested* DID —
proof that the caller **is** the holder. No DCP verifier ever is: the caller is
the counterparty asking to see credentials, so the old rule rejected every
conformant request and the four tests below it passed while the protocol did not
work at all.

The shapes here are taken from the specification and from the two reference
implementations, not invented:

* `decentralized-claims-protocol/specifications/base.protocol.md`
  §Validating Self-Issued ID Tokens
* `IdentityHub` `SelfIssuedTokenVerifierImpl` — the verification order
* `IdentityHub` `EmbeddedSecureTokenService` — the access token's claim crossover
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from conftest import make_admin_headers, register_enrolled, register_holder
from sqlalchemy import select

from identity_registry.config import get_settings
from identity_registry.db.models import Key
from identity_registry.services.crypto import (
    create_jws,
    decrypt_private_jwk,
    generate_key_pair,
    load_private_key,
)
from identity_registry.services.token import (
    SiTokenInvalid,
    create_access_token,
    create_si_token,
    verify_presentation_authorization,
)

HEADERS = make_admin_headers()

HOLDER = "did:web:rec.dataspaces.localhost"
VERIFIER = "did:web:third-party.dataspaces.localhost"
STRANGER = "did:web:attacker.dataspaces.localhost"

MEMBERSHIP_SCOPE = "org.eclipse.dspace.dcp.vc.type:MembershipCredential:read"


async def _create_participant(db_session, did: str) -> None:
    """A participant **on its own instance** — it holds the private key.

    Was `POST /admin/participants`, which now refuses to create a DID: the anchor
    does not invent a participant's identity (`D-51`). These tests are the
    holder's side — they sign SI tokens and presentations — so the row they need
    is the one `ir-cli participant init` writes locally, not the public-only one
    the anchor records.
    """
    await register_holder(db_session, did)


async def _private_key_of(db_session, did: str):
    key = (
        await db_session.execute(
            select(Key).where(Key.owner_did == did, Key.active.is_(True))
        )
    ).scalar_one()
    raw = decrypt_private_jwk(key.private_jwk, get_settings().encryption_key)
    return key, load_private_key(raw)


async def _publish(resolver, db_session, did: str) -> None:
    key, _ = await _private_key_of(db_session, did)
    resolver.publish(did, key.public_jwk)


async def _si_token(
    db_session,
    signer_did: str,
    *,
    audience: str,
    access_token: str | None = None,
    iss: str | None = None,
    sub: str | None = None,
    ttl: int = 300,
) -> str:
    """Mint the token a verifier presents to a credential service."""
    key, private_key = await _private_key_of(db_session, signer_did)
    now = int(time.time())
    claims = {
        "iss": iss or signer_did,
        "sub": sub or signer_did,
        "aud": [audience],
        "iat": now,
        "exp": now + ttl,
    }
    if access_token:
        claims["token"] = access_token
    return create_jws({"alg": "ES256", "kid": key.kid}, claims, private_key)


async def _valid_request(db_session, resolver) -> str:
    """The token a conformant EDC verifier presents: grant wrapped in an SI token."""
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, VERIFIER)
    return await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)


@pytest.fixture
async def two_participants(client, db_session):
    await _create_participant(db_session, HOLDER)
    await _create_participant(db_session, VERIFIER)


def _query(scope: str = MEMBERSHIP_SCOPE) -> dict:
    return {
        "@context": ["https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"],
        "@type": "PresentationQueryMessage",
        "scope": [scope],
    }


# ── The conformant exchange ─────────────────────────────────────────────────


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_verifier_with_a_valid_grant_is_served(
    client, db_session, resolver, two_participants
):
    """The call every DCP verifier makes, and the one that used to 401."""
    token = await _valid_request(db_session, resolver)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["@type"] == "dcp:PresentationResponseMessage"
    # The namespace is load-bearing: a verifier expands this document and reads
    # `<namespace>presentation`. Under the wrong one it parses to zero
    # presentations and reports a credential-count mismatch, never a format error.
    assert body["@context"]["dcp"] == "https://w3id.org/dspace-dcp/v1.0/"


@pytest.mark.asyncio
async def test_presentation_is_addressed_to_the_verifier(
    client, db_session, resolver, two_participants
):
    """The VP names its audience, so it cannot be replayed into another exchange."""
    token = await _valid_request(db_session, resolver)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    vp_jwt = r.json()["dcp:presentation"]["@value"][0]
    payload = json.loads(
        base64.urlsafe_b64decode(vp_jwt.split(".")[1] + "===").decode()
    )
    assert payload["aud"] == VERIFIER
    assert payload["vp"]["holder"] == HOLDER


# ── Refusals ────────────────────────────────────────────────────────────────


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_query_without_a_token_is_rejected(client, two_participants):
    r = await client.post(f"/credentials/{HOLDER}/presentations/query", json=_query())
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_si_token_without_a_grant_is_rejected(
    client, db_session, resolver, two_participants
):
    """**The invariant that replaces "a token for one DID cannot read another's".**

    A verifier proving control of its own DID is not enough — that is only who is
    asking. Without the access token this participant's STS minted, there is no
    grant, and the query is refused.
    """
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_grant_issued_to_another_verifier_cannot_be_replayed(
    client, db_session, resolver, two_participants
):
    """A grant names who it was minted for; a third party presenting it is refused."""
    await _create_participant(db_session, STRANGER)
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, STRANGER)
    token = await _si_token(db_session, STRANGER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_grant_for_another_participant_is_rejected(
    client, db_session, resolver, two_participants
):
    """A grant minted by one holder does not open a different holder's store."""
    grant = await create_access_token(
        db_session, VERIFIER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8a")
@pytest.mark.asyncio
async def test_unpublished_verifier_is_rejected(
    client, db_session, resolver, two_participants
):
    """No DID document, no key, no verification — never a fallback to "trust it"."""
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8a")
@pytest.mark.asyncio
async def test_signature_checked_against_the_published_key(
    client, db_session, resolver, two_participants
):
    """A verifier whose DID document carries a different key is refused.

    The one that matters most: it is the difference between reading the DID
    document and merely fetching it.
    """
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    impostor = generate_key_pair(VERIFIER)
    resolver.publish(VERIFIER, impostor.public_jwk)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_audience_must_name_the_participant_queried(
    client, db_session, resolver, two_participants
):
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=STRANGER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_issuer_and_subject_must_match(
    client, db_session, resolver, two_participants
):
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(
        db_session, VERIFIER, audience=HOLDER, access_token=grant, sub=STRANGER
    )
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_expired_si_token_is_rejected(
    client, db_session, resolver, two_participants
):
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=MEMBERSHIP_SCOPE
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(
        db_session, VERIFIER, audience=HOLDER, access_token=grant, ttl=-600
    )
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_expired_grant_is_rejected(
    client, db_session, resolver, two_participants
):
    grant = await create_access_token(
        db_session,
        HOLDER,
        verifier_did=VERIFIER,
        scope=MEMBERSHIP_SCOPE,
        token_ttl=-600,
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8a")
@pytest.mark.asyncio
async def test_grant_signed_by_a_foreign_key_is_rejected(
    client, db_session, resolver, two_participants
):
    """A self-minted "grant" is not a grant — it must carry this holder's signature."""
    key, _ = await _private_key_of(db_session, HOLDER)
    forged = generate_key_pair(HOLDER)
    now = int(time.time())
    grant = create_jws(
        {"alg": "ES256", "kid": key.kid},
        {
            "iss": HOLDER,
            "aud": [HOLDER],
            "sub": VERIFIER,
            "scope": MEMBERSHIP_SCOPE,
            "iat": now,
            "exp": now + 300,
        },
        load_private_key(forged.private_jwk),
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_grant_without_scope_is_rejected(
    client, db_session, resolver, two_participants
):
    key, private_key = await _private_key_of(db_session, HOLDER)
    now = int(time.time())
    grant = create_jws(
        {"alg": "ES256", "kid": key.kid},
        {
            "iss": HOLDER,
            "aud": [HOLDER],
            "sub": VERIFIER,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


@pytest.mark.rule("P-8a", "P-11")
@pytest.mark.asyncio
async def test_unsigned_token_is_rejected(client, two_participants):
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    now = int(time.time())
    forged = (
        f"{b64({'alg': 'ES256'})}."
        f"{b64({'iss': VERIFIER, 'sub': VERIFIER, 'aud': [HOLDER], 'exp': now + 300})}."
        "AAAA"
    )
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json=_query(),
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401


# ── Query shape ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scope_and_presentation_definition_together_are_a_400(
    client, db_session, resolver, two_participants
):
    token = await _valid_request(db_session, resolver)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json={**_query(), "presentationDefinition": {"input_descriptors": []}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_query_with_neither_is_a_400(
    client, db_session, resolver, two_participants
):
    token = await _valid_request(db_session, resolver)
    r = await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json={"@type": "PresentationQueryMessage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


# ── STS issuance ────────────────────────────────────────────────────────────


@pytest.mark.rule("P-8")
@pytest.mark.asyncio
async def test_the_anchor_cannot_mint_a_token_for_a_participant_it_enrolled(
    client, db_session
):
    """`D-51`, as the STS sees it.

    Was *"participants created via /admin/participants have no
    sts_client_secret"* — a route that no longer creates participants at all. The
    invariant underneath survives and is now sharper: the row the **anchor**
    holds for an enrolled participant carries a public key and no secret, so the
    anchor cannot issue a token as that participant even though it knows exactly
    who they are. Confirmed live on the split stack: 401 from the anchor, 200
    from the participant's own instance.
    """
    await register_enrolled(db_session, HOLDER)
    r = await client.post(
        f"/sts/{HOLDER}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": HOLDER,
            "client_secret": "anything-at-all",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_client"


@pytest.mark.asyncio
async def test_si_token_carries_no_grant_when_none_was_asked_for(
    client, db_session, two_participants
):
    """DCP: no `bearer_access_scope`, no `token` claim.

    It used to emit `str(uuid.uuid4())` unconditionally — a value that no
    credential service could ever validate, presented as if it were a grant.
    """
    token, _ = await create_si_token(db_session, HOLDER, audience=VERIFIER)
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "===").decode())
    assert "token" not in claims


@pytest.mark.asyncio
async def test_minted_grant_crosses_the_claims_as_the_spec_requires(
    client, db_session, two_participants
):
    """iss/aud stay with the holder; sub names the verifier — that is the binding."""
    token, _ = await create_si_token(
        db_session,
        HOLDER,
        audience=VERIFIER,
        bearer_access_scope=MEMBERSHIP_SCOPE,
    )
    outer = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "===").decode())
    grant = json.loads(
        base64.urlsafe_b64decode(outer["token"].split(".")[1] + "===").decode()
    )
    assert outer["iss"] == outer["sub"] == HOLDER
    assert outer["aud"] == [VERIFIER]
    assert grant["iss"] == HOLDER
    assert grant["aud"] == [HOLDER]
    assert grant["sub"] == VERIFIER
    assert grant["scope"] == MEMBERSHIP_SCOPE


@pytest.mark.asyncio
async def test_a_grant_cannot_be_minted_without_an_audience(
    client, db_session, two_participants
):
    """An unbound grant is a bearer token for whoever obtains it."""
    with pytest.raises(ValueError):
        await create_si_token(db_session, HOLDER, bearer_access_scope=MEMBERSHIP_SCOPE)


# ── Verification unit level ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_returns_the_granted_scopes(
    client, db_session, resolver, two_participants
):
    token = await _valid_request(db_session, resolver)
    grant = await verify_presentation_authorization(
        db_session, token, participant_did=HOLDER, resolver=resolver
    )
    assert grant.verifier_did == VERIFIER
    assert grant.scopes == [MEMBERSHIP_SCOPE]


@pytest.mark.asyncio
async def test_verify_raises_on_a_malformed_token(client, db_session, resolver):
    with pytest.raises(SiTokenInvalid):
        await verify_presentation_authorization(
            db_session, "not-a-jwt", participant_did=HOLDER, resolver=resolver
        )
