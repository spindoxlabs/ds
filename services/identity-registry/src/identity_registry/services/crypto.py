from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import hmac
import json
import os
import uuid
import weakref
from dataclasses import dataclass

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as ec_utils
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_FERNET_KDF_ITERATIONS = 480_000
_STS_HASH_ITERATIONS = 600_000
#: Derived Fernet keys kept per process — one per (passphrase, salt), so one per
#: stored private key. Bounded, so a long-lived process that has rotated many
#: keys keeps only the recent ones.
_DERIVED_KEY_CACHE_SIZE = 64
#: Successful STS secret checks remembered per process (see `verify_sts_secret`).
_STS_VERIFIED_CACHE_SIZE = 256
#: STS secret hashes computed at once. Each is ~0.5 s of CPU; the rest wait, off
#: the event loop, instead of taking every core the process has.
_STS_HASH_CONCURRENCY = 2


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
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
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


@functools.lru_cache(maxsize=_DERIVED_KEY_CACHE_SIZE)
def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    """The Fernet key for *passphrase* and *salt*, derived once per process.

    The iteration count protects the **stored** ciphertext from an offline
    guess; it buys nothing by being paid again on every request, and paying it
    per request put a ~0.5 s computation on the public signing paths (status
    list, STS, presentations). Every key has its own random salt, so a rotated
    key — or a changed passphrase — is a different cache entry rather than a
    stale one, and nothing needs invalidating. What is cached is equivalent to
    the passphrase this process already holds in its settings.
    """
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


_LEGACY_FERNET_SALT = b"ds-identity-registry-v1"


class PrivateKeyNotHeld(LookupError):
    """This instance knows the key but does not hold its private half.

    Not an error condition in the data — it is `DID-09` working. A trust anchor
    records the **public** key of every participant it enrols, because it needs
    one to verify their signatures and to bind an issued credential, and holds
    the private half of none of them (`Key.private_jwk` is nullable precisely so
    that row can exist, and `DID-12` asserts the anchor holds no other kind).

    So a `NULL` here means *a signing operation was routed to the wrong
    instance*, and it deserves to say that. Before this existed, eight call sites
    passed the column straight to :func:`decrypt_private_jwk`, which does
    ``"_enc" not in stored`` — on ``None`` that is a ``TypeError`` about argument
    types, several frames from anything that names a key or a DID.
    """


def require_private_jwk(stored: dict | None, *, kid: str, purpose: str) -> dict:
    """The stored private JWK, or a refusal that says which key and what for."""
    if stored is None:
        raise PrivateKeyNotHeld(
            f"cannot {purpose}: this instance holds no private key for {kid!r}. "
            "It records the public half of keys it has enrolled and the private "
            "half of its own only — so this signing request reached the wrong "
            "instance, or the key belongs to a participant that must sign for "
            "itself."
        )
    return stored


def decrypt_private_jwk(stored: dict, encryption_key: str) -> dict:
    if "_enc" not in stored:
        return stored
    if "_salt" in stored:
        salt = bytes.fromhex(stored["_salt"])
    else:
        salt = _LEGACY_FERNET_SALT
    fernet = Fernet(_derive_fernet_key(encryption_key, salt))
    plaintext = fernet.decrypt(stored["_enc"].encode())
    return json.loads(plaintext)


# ── STS client secret hashing ────────────────────────────────────


def hash_sts_secret(secret: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _STS_HASH_ITERATIONS)
    return f"pbkdf2:sha256:{salt.hex()}:{dk.hex()}"


#: A per-process key for remembering which (stored hash, secret) pairs already
#: verified, so the cache holds neither secret nor a fast unsalted hash of one.
_STS_CACHE_KEY = os.urandom(32)
_sts_verified: dict[bytes, None] = {}
#: One semaphore per event loop — an asyncio primitive belongs to the loop it
#: first waited on, and tests run several loops in one process.
_sts_hash_slots: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Semaphore
] = weakref.WeakKeyDictionary()


def _sts_cache_key(secret: str, stored: str) -> bytes:
    return hmac.new(
        _STS_CACHE_KEY, f"{stored}\x00{secret}".encode(), hashlib.sha256
    ).digest()


async def verify_sts_secret_async(secret: str, stored: str) -> bool:
    """`verify_sts_secret` for a request handler.

    A secret that already verified against *stored* is answered from memory —
    the client presents the same secret on every token request. Anything else is
    hashed in a worker thread, at most `_STS_HASH_CONCURRENCY` at a time, so the
    event loop keeps serving while it runs. Only successes are remembered: a
    changed secret changes *stored*, so an old entry can never match it.
    """
    marker = _sts_cache_key(secret, stored)
    if marker in _sts_verified:
        return True
    slots = _sts_hash_slots.setdefault(
        asyncio.get_running_loop(), asyncio.Semaphore(_STS_HASH_CONCURRENCY)
    )
    async with slots:
        ok = await asyncio.to_thread(verify_sts_secret, secret, stored)
    if ok:
        _sts_verified[marker] = None
        while len(_sts_verified) > _STS_VERIFIED_CACHE_SIZE:
            _sts_verified.pop(next(iter(_sts_verified)))
    return ok


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
