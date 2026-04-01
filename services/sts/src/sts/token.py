"""JWT signing helpers using participant's EC P-256 private key."""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    SECP256R1,
    generate_private_key,
)
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives import hashes, serialization
from jose import jwt as jose_jwt

from .config import get_settings


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


@lru_cache(maxsize=1)
def _load_private_key() -> EllipticCurvePrivateKey:
    """Load the participant's EC private key from the JWK file."""
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateNumbers,
        EllipticCurvePublicNumbers,
    )
    jwk = get_settings().private_key_jwk
    x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
    d = int.from_bytes(_b64url_decode(jwk["d"]), "big")
    pub_nums = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    priv_nums = EllipticCurvePrivateNumbers(private_value=d, public_numbers=pub_nums)
    return priv_nums.private_key()


def get_public_jwk() -> dict[str, Any]:
    """Return the public JWK (without private key material)."""
    jwk = get_settings().private_key_jwk
    return {k: v for k, v in jwk.items() if k != "d"}


def create_si_token(claims: dict[str, Any]) -> str:
    """Sign claims as an ES256 JWT using the participant's private key."""
    private_key = _load_private_key()
    kid = get_settings().private_key_jwk.get("kid", "key-1")
    return jose_jwt.encode(
        claims,
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


def verify_si_token(token: str, public_jwk: dict[str, Any]) -> dict[str, Any]:
    """Verify an ES256 JWT using a JWK public key dict."""
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePublicNumbers,
    )
    x = int.from_bytes(_b64url_decode(public_jwk["x"]), "big")
    y = int.from_bytes(_b64url_decode(public_jwk["y"]), "big")
    pub_nums = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    public_key = pub_nums.public_key()
    return jose_jwt.decode(token, public_key, algorithms=["ES256"])
