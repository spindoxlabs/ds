"""What the public routes may cost this service, and where they may send it.

Two rules from the participation rulebook:

* `P-8d` — a DID document is fetched only for a caller that could be admitted,
  only from a public address (private and loopback ones too, but only under
  `DS_ENV=dev`), over HTTPS outside dev, without following redirects, within one
  deadline and up to a size limit;
* `P-8e` — the routes anyone can reach pay for key derivation and signing once
  per change, not once per request, and each client has a request budget.
"""

from __future__ import annotations

import asyncio
import time

import httpcore
import httpx
import pytest
from conftest import ANCHOR_DID, StubResolver, register_holder

from identity_registry.dependencies import get_did_resolver
from identity_registry.rate_limit import BURST, RateLimiter
from identity_registry.services import crypto, did_resolver
from identity_registry.services.crypto import (
    create_jws,
    decrypt_private_jwk,
    encrypt_private_jwk,
    generate_key_pair,
    hash_sts_secret,
    load_private_key,
    verify_sts_secret_async,
)
from identity_registry.services.did_resolver import (
    MAX_DOCUMENT_BYTES,
    DidResolutionError,
    DidResolver,
    admitted_address,
    outbound_transport,
)

# ── P-8d: which addresses may be dialled ────────────────────────────────────

NOT_PUBLIC = [
    "10.0.0.5",
    "172.16.3.4",
    "192.168.1.1",
    "127.0.0.1",
    "100.64.0.1",
    "::1",
    "fd00::1",
    "::ffff:10.0.0.5",
]
NEVER = ["169.254.169.254", "fe80::1", "0.0.0.0", "224.0.0.1", "240.0.0.1"]


@pytest.mark.rule("P-8d")
@pytest.mark.parametrize("address", NOT_PUBLIC + NEVER)
def test_a_non_public_address_is_refused_outside_dev(address):
    with pytest.raises(DidResolutionError):
        admitted_address("host.example.org", [address], dev=False)


@pytest.mark.rule("P-8d")
@pytest.mark.parametrize("address", NEVER)
def test_link_local_and_unroutable_addresses_are_refused_even_in_dev(address):
    with pytest.raises(DidResolutionError):
        admitted_address("host.example.org", [address], dev=True)


@pytest.mark.rule("P-8d")
@pytest.mark.parametrize("address", ["10.0.0.5", "172.18.0.7", "127.0.0.1", "::1"])
def test_dev_admits_the_local_topology(address):
    """`*.localhost` and compose service names resolve to exactly these."""
    assert admitted_address("rec.dataspaces.localhost", [address], dev=True)


@pytest.mark.rule("P-8d")
def test_a_public_address_is_admitted():
    assert admitted_address("host.example.org", ["93.184.216.34"], dev=False) == (
        "93.184.216.34"
    )


@pytest.mark.rule("P-8d")
def test_one_private_answer_among_public_ones_is_refused():
    """Otherwise the address dialled depends on the order DNS answers in."""
    with pytest.raises(DidResolutionError):
        admitted_address("host.example.org", ["93.184.216.34", "10.0.0.5"], dev=False)


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_the_address_checked_is_the_address_dialled(monkeypatch):
    """The check sits in the connection itself, so a refused name never connects."""
    dialled: list[str] = []

    async def lookup(host, port):
        return ["10.0.0.5"] if host == "internal.example.org" else ["93.184.216.34"]

    async def connect_tcp(self, host, port, **kwargs):
        dialled.append(host)
        raise httpcore.ConnectError("stop here")

    monkeypatch.setattr(did_resolver, "_lookup", lookup)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect_tcp)

    async with httpx.AsyncClient(transport=outbound_transport(dev=False)) as client:
        with pytest.raises(httpx.ConnectError, match="non-public"):
            await client.get("https://internal.example.org/.well-known/did.json")
        assert dialled == []

        with pytest.raises(httpx.ConnectError):
            await client.get("https://public.example.org/.well-known/did.json")
    assert dialled == ["93.184.216.34"]


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_plain_http_is_not_resolved_outside_dev(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    sent: list[httpx.Request] = []
    _stub(monkeypatch, lambda request: sent.append(request) or httpx.Response(200))
    with pytest.raises(DidResolutionError, match="DS_ENV=dev"):
        await DidResolver(use_https=False).resolve("did:web:example.org")
    assert sent == []


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_a_redirect_is_not_followed(monkeypatch):
    sent: list[httpx.Request] = []

    def handler(request):
        sent.append(request)
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/did.json"})

    _stub(monkeypatch, handler)
    with pytest.raises(DidResolutionError, match="HTTP 302"):
        await DidResolver().resolve("did:web:example.org")
    assert len(sent) == 1


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_an_oversized_document_is_refused(monkeypatch):
    padding = "x" * (MAX_DOCUMENT_BYTES + 1)
    _stub(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"id": "did:web:example.org", "padding": padding}
        ),
    )
    with pytest.raises(DidResolutionError, match="size limit"):
        await DidResolver().resolve("did:web:example.org")


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_a_slow_answer_is_cut_off_at_one_deadline(monkeypatch):
    """A per-read timeout alone lets a server drip a body forever."""

    async def drip():
        while True:
            await asyncio.sleep(0.05)
            yield b" "

    _stub(monkeypatch, lambda request: httpx.Response(200, content=drip()))
    started = time.monotonic()
    with pytest.raises(DidResolutionError, match="timed out"):
        await DidResolver(timeout_seconds=0.3).resolve("did:web:example.org")
    assert time.monotonic() - started < 2


# ── P-8d: trust before the fetch ────────────────────────────────────────────


class RecordingResolver(StubResolver):
    def __init__(self):
        super().__init__()
        self.asked: list[str] = []

    async def resolve(self, did: str) -> dict:
        self.asked.append(did)
        return await super().resolve(did)


@pytest.fixture
def recording_resolver(client):
    stub = RecordingResolver()
    client._transport.app.dependency_overrides[get_did_resolver] = lambda: stub
    return stub


def _si_token(did: str, audience: str, **extra) -> str:
    kp = generate_key_pair(did)
    now = int(time.time())
    claims = {"iss": did, "sub": did, "aud": [audience], "iat": now, "exp": now + 300}
    claims.update(extra)
    return create_jws(
        {"alg": "ES256", "kid": kp.kid}, claims, load_private_key(kp.private_jwk)
    )


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_a_delivery_from_an_untrusted_issuer_resolves_nothing(
    client, db_session, recording_resolver
):
    holder = "did:web:rec.dataspaces.localhost"
    await register_holder(db_session, holder)
    stranger = "did:web:elsewhere.example.org"

    r = await client.post(
        f"/credentials/{holder}/credentials",
        json={"type": "CredentialMessage", "credentials": []},
        headers={"Authorization": f"Bearer {_si_token(stranger, holder)}"},
    )
    assert r.status_code == 403
    assert recording_resolver.asked == []


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_an_unknown_enrolment_code_resolves_nothing(
    client, db_session, recording_resolver
):
    stranger = "did:web:elsewhere.example.org"
    r = await client.post(
        "/issuer/credentials",
        json={
            "type": "CredentialRequestMessage",
            "holderPid": "req-1",
            "credentials": [{"id": "MembershipCredential"}],
        },
        headers={
            "Authorization": "Bearer "
            + _si_token(stranger, ANCHOR_DID, **{"pre-authorized_code": "made-up"})
        },
    )
    assert r.status_code == 401
    assert recording_resolver.asked == []


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_a_status_request_for_no_recorded_request_resolves_nothing(
    client, recording_resolver
):
    stranger = "did:web:elsewhere.example.org"
    r = await client.get(
        "/issuer/requests/some-request",
        headers={"Authorization": f"Bearer {_si_token(stranger, ANCHOR_DID)}"},
    )
    assert r.status_code == 401
    assert recording_resolver.asked == []


@pytest.mark.rule("P-8d")
@pytest.mark.asyncio
async def test_a_presentation_query_without_our_grant_resolves_nothing(
    client, db_session, recording_resolver
):
    holder = "did:web:rec.dataspaces.localhost"
    await register_holder(db_session, holder)
    stranger = "did:web:elsewhere.example.org"
    forged_grant = _si_token(holder, holder, sub=stranger, scope="x")

    for token in (
        _si_token(stranger, holder),
        _si_token(stranger, holder, token=forged_grant),
    ):
        r = await client.post(
            f"/credentials/{holder}/presentations/query",
            json={"scope": ["x"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
    assert recording_resolver.asked == []


# ── P-8e: paid once per change, not once per request ────────────────────────


@pytest.mark.rule("P-8e")
def test_a_private_key_is_derived_once_per_process(monkeypatch):
    calls = []
    real = crypto.PBKDF2HMAC.derive

    def counting(self, material):
        calls.append(1)
        return real(self, material)

    monkeypatch.setattr(crypto.PBKDF2HMAC, "derive", counting)
    stored = encrypt_private_jwk({"kty": "EC", "d": "x"}, "passphrase-a")
    for _ in range(3):
        assert decrypt_private_jwk(stored, "passphrase-a") == {"kty": "EC", "d": "x"}
    assert len(calls) == 1

    # A rotated key has its own salt, so it is derived — never served stale.
    rotated = encrypt_private_jwk({"kty": "EC", "d": "y"}, "passphrase-a")
    assert decrypt_private_jwk(rotated, "passphrase-a") == {"kty": "EC", "d": "y"}


@pytest.mark.rule("P-8e")
@pytest.mark.asyncio
async def test_a_verified_sts_secret_is_not_hashed_again(monkeypatch):
    stored = hash_sts_secret("right")
    calls = []
    real = crypto.verify_sts_secret

    def counting(secret, against):
        calls.append(secret)
        return real(secret, against)

    monkeypatch.setattr(crypto, "verify_sts_secret", counting)
    assert await verify_sts_secret_async("right", stored)
    assert await verify_sts_secret_async("right", stored)
    assert not await verify_sts_secret_async("wrong", stored)
    assert not await verify_sts_secret_async("wrong", stored)
    # The right secret once; a wrong one is never remembered.
    assert calls == ["right", "wrong", "wrong"]
    # A changed secret is a changed hash, so the old entry cannot match it.
    assert not await verify_sts_secret_async("right", hash_sts_secret("new"))


async def _status_list_with_anchor(db_session, list_id: str):
    from identity_registry.config import get_settings
    from identity_registry.db.models import Did, Key, StatusList

    kp = generate_key_pair(ANCHOR_DID)
    key = Key(
        owner_did=ANCHOR_DID,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
        active=True,
    )
    db_session.add(key)
    await db_session.flush()
    db_session.add(
        Did(
            did=ANCHOR_DID, did_type="participant", display_name="Anchor", key_id=key.id
        )
    )
    status_list = StatusList(id=list_id, bitstring=bytes(16384), purpose="revocation")
    db_session.add(status_list)
    await db_session.commit()
    return key, status_list


@pytest.mark.rule("P-8e")
@pytest.mark.asyncio
async def test_the_status_list_is_signed_once_per_change(
    client, db_session, monkeypatch
):
    from identity_registry.api.v1 import public

    signed = []
    real = public.sign_credential

    def counting(*args, **kwargs):
        signed.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(public, "sign_credential", counting)
    key, status_list = await _status_list_with_anchor(db_session, "cache-1")

    first = await client.get("/status/cache-1", headers={"Accept": "*/*"})
    again = await client.get("/status/cache-1", headers={"Accept": "*/*"})
    assert first.status_code == again.status_code == 200
    assert first.text == again.text
    assert len(signed) == 1

    # A revocation changes the bits, and the next fetch shows it.
    bits = bytearray(status_list.bitstring)
    bits[0] = 0x80
    status_list.bitstring = bytes(bits)
    await db_session.commit()
    changed = await client.get("/status/cache-1", headers={"Accept": "*/*"})
    assert changed.text != first.text
    assert len(signed) == 2

    # So does a new signing key.
    kp = generate_key_pair(ANCHOR_DID)
    from identity_registry.config import get_settings

    key.kid = f"{ANCHOR_DID}#key-2"
    key.public_jwk = kp.public_jwk
    key.private_jwk = encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key)
    await db_session.commit()
    rotated = await client.get("/status/cache-1", headers={"Accept": "*/*"})
    assert rotated.status_code == 200
    assert len(signed) == 3


# ── P-8e: a request budget per client ──────────────────────────────────────


@pytest.mark.rule("P-8e")
def test_the_budget_refills_at_the_configured_rate():
    now = [0.0]
    limiter = RateLimiter(rate=2.0, burst=3.0, clock=lambda: now[0])
    assert [limiter.take("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.take("a") == pytest.approx(0.5)
    assert limiter.take("b") == 0.0  # another client has its own budget
    now[0] += 0.5
    assert limiter.take("a") == 0.0


@pytest.mark.rule("P-8e")
def test_forgotten_clients_are_bounded():
    limiter = RateLimiter(rate=1.0, burst=1.0, max_clients=2, clock=lambda: 0.0)
    for client in ("a", "b", "c"):
        limiter.take(client)
    assert len(limiter._buckets) == 2


@pytest.mark.rule("P-8e")
@pytest.mark.asyncio
async def test_a_public_route_answers_429_once_the_budget_is_spent(client):
    # A slow refill, so the test does not race the clock.
    client._transport.app.state.public_rate_limiter = RateLimiter(rate=0.01, burst=3)
    codes = [
        (await client.get("/status/none", headers={"Accept": "*/*"})).status_code
        for _ in range(4)
    ]
    assert codes == [404, 404, 404, 429]
    r = await client.get("/.well-known/did.json")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    # Routes outside the public set are not on this budget.
    assert (await client.get("/health")).status_code == 200


@pytest.mark.rule("P-8e")
@pytest.mark.asyncio
async def test_the_default_budget_covers_a_burst_of_negotiations(client):
    codes = {
        (await client.get("/status/none", headers={"Accept": "*/*"})).status_code
        for _ in range(int(BURST) // 2)
    }
    assert codes == {404}


# ── helpers ────────────────────────────────────────────────────────────────


class _Transport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self._handler = handler

    async def handle_async_request(self, request):
        return self._handler(request)


def _stub(monkeypatch, handler):
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = _Transport(handler)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
