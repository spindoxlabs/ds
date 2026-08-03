import pytest

from identity_registry.services.status_list import (
    build_status_list_credential,
    create_bitstring,
    decode_bitstring,
    encode_bitstring,
    get_bit,
    set_bit,
)


def test_create_bitstring():
    bs = create_bitstring()
    assert len(bs) == 16384
    assert all(b == 0 for b in bs)


def test_set_and_get_bit():
    bs = create_bitstring()
    assert not get_bit(bs, 0)
    bs = set_bit(bs, 0)
    assert get_bit(bs, 0)
    assert not get_bit(bs, 1)


def test_set_bit_various_positions():
    bs = create_bitstring()
    for pos in [0, 1, 7, 8, 15, 100, 1000]:
        bs = set_bit(bs, pos)
        assert get_bit(bs, pos)


def test_encode_decode_roundtrip():
    bs = create_bitstring()
    bs = set_bit(bs, 42)
    encoded = encode_bitstring(bs)
    decoded = decode_bitstring(encoded)
    assert get_bit(decoded, 42)
    assert not get_bit(decoded, 41)


def test_the_module_exposes_no_bitstring_scanning_allocator():
    """`next_available_index(bitstring)` used to live here and was tested here.

    It was the mechanism of both P0 defects: the register's first unset bit
    cannot allocate, because leaving the bit clear never advances it and
    setting it publishes the credential revoked. Allocation is now a counter
    (`allocate_status_list_index`), and this asserts the old shape has not
    quietly come back — a scanning helper is the sort of thing that gets
    re-added as a convenience.
    """
    import identity_registry.services.status_list as sl

    assert not hasattr(sl, "next_available_index")


def test_build_status_list_credential():
    bs = create_bitstring()
    encoded = encode_bitstring(bs)
    cred = build_status_list_credential(
        list_id="1",
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        encoded_list=encoded,
    )
    assert "StatusList2021Credential" in cred["type"]
    assert cred["credentialSubject"]["type"] == "StatusList2021"
    assert cred["credentialSubject"]["statusPurpose"] == "revocation"


# ── The encoding a verifier actually reads ──────────────────────────────────


def test_encoded_list_is_gzip_not_zlib():
    """StatusList2021 says GZIP, and EDC's `BitString` uses `GZIPInputStream`.

    The round-trip tests above all passed while this was a raw zlib stream,
    because `decode_bitstring` used zlib too — the module agreed with itself and
    with nobody else. A verifier that cannot decompress the list cannot clear a
    credential, so every revocation check failed closed and said nothing.

    This asserts against the wire format, not against our own decoder, which is
    the only kind of assertion that could have caught it.
    """
    import base64
    import gzip

    from identity_registry.services.status_list import encode_bitstring

    raw = base64.b64decode(encode_bitstring(bytes(64)))
    assert raw[:2] == b"\x1f\x8b", "encodedList must be GZIP (magic 1f 8b)"
    assert gzip.decompress(raw) == bytes(64)


def test_decode_still_reads_a_legacy_zlib_list():
    """Lists published before the fix are already named by issued credentials."""
    import base64
    import zlib

    from identity_registry.services.status_list import decode_bitstring

    legacy = base64.b64encode(zlib.compress(bytes(32))).decode()
    assert decode_bitstring(legacy) == bytes(32)


# ── How it is served ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_list_is_served_signed_by_default(client, db_session):
    """A verifier sends `Accept: */*` and reads the body as a VC-JWT.

    Served as unsigned JSON-LD, the list is one anybody on the path can rewrite —
    clear a bit and a revoked credential is valid again. EDC takes the JSON
    branch only for an exact `application/json` accept header, so the default
    has to be the signed form.
    """
    import base64
    import json as jsonlib

    from identity_registry.db.models import StatusList

    await _bootstrap_trust_anchor(db_session)
    db_session.add(StatusList(id="1", bitstring=bytes(16384), purpose="revocation"))
    await db_session.commit()

    r = await client.get("/status/1", headers={"Accept": "*/*"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vc+jwt")
    payload = jsonlib.loads(
        base64.urlsafe_b64decode(r.text.split(".")[1] + "===").decode()
    )
    assert "StatusList2021Credential" in payload["vc"]["type"]
    assert payload["iss"].startswith("did:web:")


@pytest.mark.asyncio
async def test_status_list_json_is_opt_in(client, db_session):
    from identity_registry.db.models import StatusList

    await _bootstrap_trust_anchor(db_session)
    db_session.add(StatusList(id="2", bitstring=bytes(16384), purpose="revocation"))
    await db_session.commit()

    r = await client.get("/status/2", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert "StatusList2021Credential" in r.json()["type"]


async def _bootstrap_trust_anchor(db_session) -> None:
    """Create the trust-anchor key + DID, the way `ir-cli bootstrap` does."""
    from identity_registry.db.models import Did, Key
    from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair

    did = "did:web:trust-anchor.dataspaces.localhost"
    kp = generate_key_pair(did)
    key = Key(
        id="trust-anchor-key",
        owner_did=did,
        kid=kp.kid,
        public_jwk=kp.public_jwk,
        private_jwk=encrypt_private_jwk(
            kp.private_jwk, "dev-encryption-key-change-in-production"
        ),
        active=True,
    )
    db_session.add(key)
    db_session.add(Did(did=did, did_type="trust-anchor", key_id=key.id, active=True))
    await db_session.commit()
