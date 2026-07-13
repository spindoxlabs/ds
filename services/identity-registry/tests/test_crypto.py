import pytest

from identity_registry.services.crypto import (
    _b64url_decode,
    _b64url_encode,
    create_jws,
    generate_key_pair,
    load_private_key,
    next_key_index,
    sign_es256,
)


def test_generate_key_pair_format():
    kp = generate_key_pair("did:web:example.localhost")
    assert kp.kid == "did:web:example.localhost#key-1"
    assert kp.public_jwk["kty"] == "EC"
    assert kp.public_jwk["crv"] == "P-256"
    assert "x" in kp.public_jwk
    assert "y" in kp.public_jwk
    assert "d" not in kp.public_jwk
    assert kp.private_jwk["kty"] == "EC"
    assert "d" in kp.private_jwk


def test_generate_key_pair_custom_index():
    kp = generate_key_pair("did:web:test.localhost", key_index=3)
    assert kp.kid == "did:web:test.localhost#key-3"


def test_load_private_key_roundtrip():
    kp = generate_key_pair("did:web:test.localhost")
    pk = load_private_key(kp.private_jwk)
    numbers = pk.private_numbers()
    assert numbers.public_numbers.curve.name == "secp256r1"


def test_sign_es256_produces_64_bytes():
    kp = generate_key_pair("did:web:test.localhost")
    pk = load_private_key(kp.private_jwk)
    sig = sign_es256(b"test payload", pk)
    assert len(sig) == 64


def test_create_jws_three_parts():
    kp = generate_key_pair("did:web:test.localhost")
    pk = load_private_key(kp.private_jwk)
    header = {"alg": "ES256", "typ": "JWT", "kid": kp.kid}
    payload = {"iss": "test", "sub": "test"}
    jws = create_jws(header, payload, pk)
    parts = jws.split(".")
    assert len(parts) == 3


def test_b64url_roundtrip():
    data = b"hello world"
    encoded = _b64url_encode(data)
    assert "=" not in encoded
    decoded = _b64url_decode(encoded)
    assert decoded == data


def test_next_key_index():
    assert next_key_index(None) == 1
    assert next_key_index("did:web:x#key-1") == 2
    assert next_key_index("did:web:x#key-5") == 6
    assert next_key_index("invalid") == 1
