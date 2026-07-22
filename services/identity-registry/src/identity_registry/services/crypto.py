from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_FERNET_KDF_ITERATIONS = 480_000
_STS_HASH_ITERATIONS = 600_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _int_to_b64url(n: int, length: int = 32) -> str:
    return _b64url_encode(n.to_bytes(length, byteorder="big"))


def _b64url_to_int(s: str) -> int:
    return int.from_bytes(_b64url_decode(s), byteorder="big")


@dataclass
class KeyPair:
    kid: str
    private_jwk: dict
    public_jwk: dict


def generate_key_pair(did: str, key_index: int = 1) -> KeyPair:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_numbers = private_key.private_numbers()
    public_numbers = private_numbers.public_numbers

    kid = f"{did}#key-{key_index}"

    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _int_to_b64url(public_numbers.x),
        "y": _int_to_b64url(public_numbers.y),
        "kid": kid,
        "use": "sig",
    }

    private_jwk = {
        **public_jwk,
        "d": _int_to_b64url(private_numbers.private_value),
    }

    return KeyPair(kid=kid, private_jwk=private_jwk, public_jwk=public_jwk)


def load_private_key(jwk: dict) -> ec.EllipticCurvePrivateKey:
    x = _b64url_to_int(jwk["x"])
    y = _b64url_to_int(jwk["y"])
    d = _b64url_to_int(jwk["d"])

    public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
    private_numbers = ec.EllipticCurvePrivateNumbers(d, public_numbers)
    return private_numbers.private_key()


def load_public_key(jwk: dict) -> ec.EllipticCurvePublicKey:
    """Rebuild a P-256 public key from its JWK representation."""
    x = _b64url_to_int(jwk["x"])
    y = _b64url_to_int(jwk["y"])
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def verify_es256(
    payload: bytes, signature: bytes, public_key: ec.EllipticCurvePublicKey
) -> bool:
    """Verify a raw r‖s ES256 signature. Returns False rather than raising."""
    if len(signature) != 64:
        return False
    der_sig = ec_utils.encode_dss_signature(
        int.from_bytes(signature[:32], byteorder="big"),
        int.from_bytes(signature[32:], byteorder="big"),
    )
    try:
        public_key.verify(der_sig, payload, ec.ECDSA(SHA256()))
    except Exception:
        return False
    return True


def sign_es256(payload: bytes, private_key: ec.EllipticCurvePrivateKey) -> bytes:
    der_sig = private_key.sign(payload, ec.ECDSA(SHA256()))
    r, s = ec_utils.decode_dss_signature(der_sig)
    return r.to_bytes(32, byteorder="big") + s.to_bytes(32, byteorder="big")


def create_jws(
    header: dict, payload: dict, private_key: ec.EllipticCurvePrivateKey
) -> str:
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode()
    )
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = sign_es256(signing_input, private_key)
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def next_key_index(existing_kid: str | None) -> int:
    if not existing_kid or "#key-" not in existing_kid:
        return 1
    try:
        return int(existing_kid.rsplit("#key-", 1)[1]) + 1
    except (ValueError, IndexError):
        return 1


def generate_credential_id() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


# ── Private key encryption at rest ───────────────────────────────


def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=_FERNET_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def encrypt_private_jwk(jwk: dict, encryption_key: str) -> dict:
    salt = os.urandom(16)
    fernet = Fernet(_derive_fernet_key(encryption_key, salt))
    plaintext = json.dumps(jwk, separators=(",", ":")).encode()
    return {"_enc": fernet.encrypt(plaintext).decode(), "_salt": salt.hex()}


def decrypt_private_jwk(stored: dict, encryption_key: str) -> dict:
    if "_enc" not in stored:
        return stored
    salt = bytes.fromhex(stored["_salt"])
    fernet = Fernet(_derive_fernet_key(encryption_key, salt))
    plaintext = fernet.decrypt(stored["_enc"].encode())
    return json.loads(plaintext)


# ── STS client secret hashing ────────────────────────────────────


def hash_sts_secret(secret: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _STS_HASH_ITERATIONS)
    return f"pbkdf2:sha256:{salt.hex()}:{dk.hex()}"


def verify_sts_secret(secret: str, stored: str) -> bool:
    if not stored.startswith("pbkdf2:"):
        return False
    parts = stored.split(":")
    if len(parts) != 4:
        return False
    salt = bytes.fromhex(parts[2])
    expected = bytes.fromhex(parts[3])
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _STS_HASH_ITERATIONS)
    return hmac.compare_digest(dk, expected)
