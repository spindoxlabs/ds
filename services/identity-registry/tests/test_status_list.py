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
