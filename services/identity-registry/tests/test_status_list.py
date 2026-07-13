from identity_registry.services.status_list import (
    build_status_list_credential,
    create_bitstring,
    decode_bitstring,
    encode_bitstring,
    get_bit,
    next_available_index,
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


def test_next_available_index():
    bs = create_bitstring()
    assert next_available_index(bs) == 0
    bs = set_bit(bs, 0)
    assert next_available_index(bs) == 1
    bs = set_bit(bs, 1)
    assert next_available_index(bs) == 2


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
