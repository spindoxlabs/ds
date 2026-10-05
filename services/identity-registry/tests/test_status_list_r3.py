"""R3: the status register, as DCP v1.0 and EDC's verifier read it.

Three gaps against DCP v1.0 and EDC's IssuerService (Connector/IdentityHub
v0.18.0), each pinned here:

1. **Bitstring Status List, not StatusList2021.** DCP issuance makes it a MUST
   (`credential.issuance.protocol.md@v1.0:359`) and IssuerService publishes
   nothing else: a `BitstringStatusListCredential` signed as a VC 1.1 JWT with a
   `vc` claim, its `encodedList` multibase base64url of a GZIP stream.
2. **415 for an Accept the route does not serve.** IssuerService answers
   `application/vc+jwt`, `application/json` and `*/*` and refuses the rest
   (`StatusListCredentialController`); this answered JSON instead.
3. **A stable `id` per list.** It was a fresh `urn:uuid` on every build.

Credentials issued before R3 name the same URL with `StatusList2021Entry`; the
last tests here keep those verifying.
"""

from __future__ import annotations

import base64
import gzip
import json

import pytest
from ds_auth import user_credentials
from fastapi import HTTPException
from test_status_list import _bootstrap_trust_anchor
from test_status_list_is_readable import REVOCATION_LIST, SUSPENSION_LIST, _serve

from identity_registry.db.models import StatusList
from identity_registry.services.status_list import (
    allocate_suspendable_index,
    revoke_status_list_index,
    set_bit,
)
from identity_registry.services.vc import build_data_subject_credential


def _jwt_vc(body: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(body.split(".")[1] + "==="))


def _edc_bit(encoded_list: str, index: int) -> bool:
    """EDC's `BitString.Parser.parse(..).get(index)`, transcribed from source at
    v0.18.0 (`spi/common/verifiable-credentials-spi/.../revocation/BitString.java`):
    a `z` header is refused; a `u` header selects `Base64.getUrlDecoder()` (padding
    optional) on the rest; anything else `Base64.getDecoder()`; then
    `GZIPInputStream`; then bit `7 - idx % 8` of byte `idx / 8` (left to right).
    """
    assert not encoded_list.startswith("z"), "EDC refuses base58btc"
    if encoded_list.startswith("u"):
        body = encoded_list[1:]
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    else:
        raw = base64.b64decode(encoded_list, validate=True)
    bits = gzip.decompress(raw)  # GZIPInputStream: zlib would raise here
    assert 0 <= index < len(bits) * 8
    return bool(bits[index // 8] & (1 << (7 - index % 8)))


async def _list(db_session, list_id: str = "1", *, bits=(), purpose="revocation"):
    bitstring = bytes(16384)
    for i in bits:
        bitstring = set_bit(bitstring, i)
    db_session.add(StatusList(id=list_id, bitstring=bitstring, purpose=purpose))
    await db_session.commit()


# ── 1. Bitstring Status List ────────────────────────────────────────────────


def test_issued_credentials_carry_bitstring_status_list_entries():
    vc = build_data_subject_credential(
        issuer_did="did:web:ta.example",
        subject_did="did:web:rec.example:users:alice",
        role="DataSubject",
        credentials_context_url="http://test/contexts/credentials.jsonld",
        dataspace_uri="urn:dataspace:test",
        status_list_credential_url=REVOCATION_LIST,
        suspension_list_credential_url=SUSPENSION_LIST,
        status_list_index=7,
    )
    entries = vc["credentialStatus"]
    assert [e["type"] for e in entries] == ["BitstringStatusListEntry"] * 2
    assert {e["statusPurpose"] for e in entries} == {"revocation", "suspension"}
    for entry in entries:
        # What EDC's `BitstringStatusListStatus.from` reads: the index as a
        # string it can `parseInt`, the list URL, and no `statusSize` (default
        # 1 — the only size `BitstringStatusListRevocationService` accepts).
        assert entry["statusListIndex"] == "7"
        assert entry["statusListCredential"] in (REVOCATION_LIST, SUSPENSION_LIST)
        assert "statusSize" not in entry


@pytest.mark.asyncio
async def test_the_list_is_a_signed_bitstring_status_list_credential(
    client, db_session
):
    await _bootstrap_trust_anchor(db_session)
    await _list(db_session, bits=(0, 9, 131071))

    r = await client.get("/status/1")  # no Accept: EDC's default is */*
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vc+jwt")
    header = json.loads(base64.urlsafe_b64decode(r.text.split(".")[0] + "==="))
    claims = _jwt_vc(r.text)
    vc = claims["vc"]

    # The shape IssuerService signs (`BitstringStatusListManager`, VC1_0_JWT).
    assert header["alg"] == "ES256" and header["kid"].startswith(claims["iss"] + "#")
    assert vc["type"] == ["VerifiableCredential", "BitstringStatusListCredential"]
    assert vc["issuer"] == claims["iss"]
    assert vc["issuanceDate"].endswith("Z")
    subject = vc["credentialSubject"]
    assert subject["type"] == "BitstringStatusList"
    assert subject["statusPurpose"] == "revocation"

    encoded = subject["encodedList"]
    assert encoded.startswith("u") and "=" not in encoded
    # Read the way EDC reads it, bit order included.
    assert _edc_bit(encoded, 0) and _edc_bit(encoded, 9) and _edc_bit(encoded, 131071)
    assert not any(_edc_bit(encoded, i) for i in (1, 7, 8, 10, 131070))


# ── 2. Content negotiation ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "accept",
    [
        "text/html",
        "application/xml",
        "image/png",
        "application/vc+ld+json",
        "application/vc+jwt;q=0, text/plain",
    ],
)
@pytest.mark.asyncio
async def test_an_unsupported_accept_is_415(client, db_session, accept):
    await _bootstrap_trust_anchor(db_session)
    await _list(db_session)

    r = await client.get("/status/1", headers={"Accept": accept})
    assert r.status_code == 415, r.text


@pytest.mark.parametrize(
    "accept",
    [
        None,
        "*/*",
        "application/vc+jwt",
        "application/vc+jwt, application/json",  # EDC joins its types with ","
        "application/json, */*",
        "application/*",
    ],
)
@pytest.mark.asyncio
async def test_the_signed_form_is_served_whenever_it_is_acceptable(
    client, db_session, accept
):
    await _bootstrap_trust_anchor(db_session)
    await _list(db_session)

    headers = {} if accept is None else {"Accept": accept}
    r = await client.get("/status/1", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vc+jwt")
    assert r.text.count(".") == 2


@pytest.mark.parametrize("accept", ["application/json", "application/ld+json"])
@pytest.mark.asyncio
async def test_json_only_on_an_explicit_request(client, db_session, accept):
    await _bootstrap_trust_anchor(db_session)
    await _list(db_session)

    r = await client.get("/status/1", headers={"Accept": accept})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(accept)
    assert "BitstringStatusListCredential" in r.json()["type"]


# ── 3. A stable id ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_list_id_is_stable_and_is_its_url(client, db_session):
    await _bootstrap_trust_anchor(db_session)
    await _list(db_session, "1")
    await _list(db_session, "2", purpose="suspension")

    def _get(list_id: str, accept: str) -> dict:
        return client.get(f"/status/{list_id}", headers={"Accept": accept})

    first = (await _get("1", "application/json")).json()
    second = (await _get("1", "application/json")).json()
    signed = _jwt_vc((await _get("1", "application/vc+jwt")).text)["vc"]
    other = (await _get("2", "application/json")).json()

    assert first["id"] == second["id"] == signed["id"]
    assert first["id"].endswith("/status/1")
    assert first["credentialSubject"]["id"] == first["id"] + "#list"
    assert other["id"].endswith("/status/2") and other["id"] != first["id"]

    # A revocation changes the bits, not the identity of the list.
    await revoke_status_list_index(db_session, 3, "1")
    await db_session.commit()
    after = _jwt_vc((await _get("1", "application/vc+jwt")).text)
    assert after["vc"]["id"] == first["id"]
    assert _edc_bit(after["vc"]["credentialSubject"]["encodedList"], 3)


# ── Transition: credentials issued before R3 ────────────────────────────────


def _legacy(index: int) -> dict:
    """A credential as issued before R3: `StatusList2021Entry`, same URLs."""
    return {
        "credentialStatus": [
            {
                "id": f"{url}#{index}",
                "type": "StatusList2021Entry",
                "statusPurpose": purpose,
                "statusListIndex": str(index),
                "statusListCredential": url,
            }
            for url, purpose in (
                (REVOCATION_LIST, "revocation"),
                (SUSPENSION_LIST, "suspension"),
            )
        ]
    }


@pytest.fixture(autouse=True)
def _no_cached_register():
    user_credentials.reset_status_cache()
    yield
    user_credentials.reset_status_cache()


@pytest.mark.asyncio
async def test_a_statuslist2021_credential_still_verifies_against_the_new_list(
    client, db_session, monkeypatch, anchor_identity
):
    live = await allocate_suspendable_index(db_session)
    revoked = await allocate_suspendable_index(db_session)
    await revoke_status_list_index(db_session, revoked)
    await db_session.commit()
    documents = await _serve(client, monkeypatch, anchor_identity)
    assert "BitstringStatusListCredential" in documents[REVOCATION_LIST]["type"]

    user_credentials._verify_credential_status(
        _legacy(live), credential_status_url=REVOCATION_LIST
    )
    with pytest.raises(HTTPException) as exc:
        user_credentials._verify_credential_status(
            _legacy(revoked), credential_status_url=REVOCATION_LIST
        )
    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail
