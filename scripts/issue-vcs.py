#!/usr/bin/env python3
"""Issue membership Verifiable Credentials for dev participants.

Signs VCs with the trust anchor's private key (ES256 + JWS proof).
Output is written to data/credentials/{provider,consumer}/*.json.

Usage:
    python3 scripts/issue-vcs.py

Requires: cryptography, python-jose
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePrivateNumbers,
    EllipticCurvePublicNumbers,
    SECP256R1,
)
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives import hashes

REPO_ROOT = Path(__file__).parent.parent

TRUST_ANCHOR_KEY_PATH = REPO_ROOT / "services/connector/config/trust-anchor-key.json"
CREDENTIALS_DIR = REPO_ROOT / "data/credentials"

PARTICIPANTS = [
    {
        "did": "did:web:provider.dataspaces.localhost",
        "role": "Provider",
        "out_dir": "provider",
    },
    {
        "did": "did:web:consumer.dataspaces.localhost",
        "role": "Consumer",
        "out_dir": "consumer",
    },
]


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


def load_private_key(jwk: dict):
    x = int.from_bytes(b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(b64url_decode(jwk["y"]), "big")
    d = int.from_bytes(b64url_decode(jwk["d"]), "big")
    pub_nums = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    priv_nums = EllipticCurvePrivateNumbers(private_value=d, public_numbers=pub_nums)
    return priv_nums.private_key()


def sign_vc(vc: dict, private_key, kid: str) -> dict:
    """Attach a JWS proof to the VC (detached payload, compact serialisation)."""
    now = int(time.time())
    payload = {
        "iss": "did:web:trust-anchor.dataspaces.localhost",
        "sub": vc["credentialSubject"]["id"],
        "nbf": now,
        "exp": now + 365 * 24 * 3600,
        "jti": vc["id"],
        "vc": vc,
    }
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    signing_input = ".".join([
        b64url(json.dumps(header, separators=(",", ":")).encode()),
        b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]).encode()
    der_signature = private_key.sign(signing_input, ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    token = f"{signing_input.decode()}.{b64url(raw_signature)}"
    vc["proof"] = {
        "type": "JsonWebSignature2020",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verificationMethod": kid,
        "proofPurpose": "assertionMethod",
        "jws": token,
    }
    return vc


def issue_membership_vc(participant_did: str, role: str, ta_key_jwk: dict) -> dict:
    now = int(time.time())
    issuance_date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    vc = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
            "https://dataspaces.localhost/ns/credentials/v1",
        ],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "MembershipCredential"],
        "issuer": "did:web:trust-anchor.dataspaces.localhost",
        "issuanceDate": issuance_date,
        "credentialSubject": {
            "id": participant_did,
            "memberOf": "https://dataspaces.localhost/dataspace",
            "role": role,
            "allowedScopes": ["dataspaces.query"],
        },
        "credentialStatus": {
            "id": "https://trust-anchor.dataspaces.localhost/status/1#0",
            "type": "StatusList2021Entry",
            "statusPurpose": "revocation",
            "statusListIndex": "0",
            "statusListCredential": "https://trust-anchor.dataspaces.localhost/status/1",
        },
    }

    private_key = load_private_key(ta_key_jwk)
    kid = ta_key_jwk["kid"]
    return sign_vc(vc, private_key, kid)


def main():
    if not TRUST_ANCHOR_KEY_PATH.exists():
        print(f"Trust anchor key not found at {TRUST_ANCHOR_KEY_PATH}")
        print("Create it with scripts/gen-keys.sh")
        raise SystemExit(1)

    ta_jwk = json.loads(TRUST_ANCHOR_KEY_PATH.read_text())

    for p in PARTICIPANTS:
        out_dir = CREDENTIALS_DIR / p["out_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)

        vc = issue_membership_vc(p["did"], p["role"], ta_jwk)
        out_path = out_dir / "membership-vc.json"
        out_path.write_text(json.dumps(vc, indent=2))
        print(f"Issued membership VC for {p['did']} → {out_path}")


if __name__ == "__main__":
    main()
