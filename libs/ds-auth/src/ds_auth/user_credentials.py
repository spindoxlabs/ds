"""User Verifiable Credential verification for portal-facing APIs."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePublicNumbers,
    SECP256R1,
)
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import HTTPException

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserCredential:
    did: str
    subject_id: str
    role: str
    issuer: str
    linked_participant: str | None = None


def _b64url_decode(value: str) -> bytes:
    padding = 4 - len(value) % 4
    return base64.urlsafe_b64decode(value + "=" * (padding % 4))


def _load_public_key(jwk_path: str):
    jwk = json.loads(Path(jwk_path).read_text())
    x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
    return EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1()).public_key()


def verify_user_vc_jwt(
    token: str | None,
    expected_subject_id: str | None,
    trust_anchor_key_path: str,
    required_roles: set[str] | None = None,
    expected_issuer: str | None = None,
    expected_linked_participant: str | None = None,
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
    insecure_dev: bool = False,
) -> UserCredential:
    if not token:
        raise HTTPException(401, "Missing user Verifiable Credential (X-User-VC header)")
    if not expected_subject_id:
        raise HTTPException(401, "Missing subject identity (X-Subject-Id header)")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(401, "Invalid user Verifiable Credential format")
    try:
        header: dict[str, Any] = json.loads(_b64url_decode(parts[0]))
    except Exception as exc:
        raise HTTPException(401, "Invalid user Verifiable Credential header") from exc
    if header.get("alg") != "ES256":
        raise HTTPException(401, "Unsupported user Verifiable Credential algorithm")

    # Fail closed: without a trust-anchor key we cannot authenticate the holder,
    # and every downstream ownership check reads its subject from this payload.
    # The unsigned path is a local-dev affordance and must be opted into.
    if not trust_anchor_key_path:
        if not insecure_dev:
            log.error(
                "CONNECTOR_TRUST_ANCHOR_KEY_PATH is not set — refusing to accept an "
                "unverified user Verifiable Credential."
            )
            raise HTTPException(
                503, "User credential verification is not configured"
            )
        log.warning(
            "Accepting user Verifiable Credential WITHOUT signature verification "
            "(CONNECTOR_VC_INSECURE_DEV=true). Local development only."
        )
    else:
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        signature = _b64url_decode(parts[2])
        if len(signature) != 64:
            raise HTTPException(401, "Invalid user Verifiable Credential signature")

        public_key = _load_public_key(trust_anchor_key_path)
        der_signature = encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        try:
            public_key.verify(der_signature, signing_input, ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise HTTPException(401, "Invalid user Verifiable Credential signature") from exc

    payload: dict[str, Any] = json.loads(_b64url_decode(parts[1]))
    vc = payload.get("vc") or {}
    subject = vc.get("credentialSubject") or {}
    subject_id = str(subject.get("id") or payload.get("sub") or "")
    role = str(subject.get("role") or "")
    did = str(subject.get("id") or payload.get("sub") or "")
    issuer = str(payload.get("iss") or vc.get("issuer") or "")
    linked_participant = subject.get("linkedParticipant")
    now = datetime.now(timezone.utc).timestamp()

    if subject_id != expected_subject_id:
        raise HTTPException(403, "User VC subject does not match authenticated subject")
    if expected_issuer and issuer != expected_issuer:
        raise HTTPException(403, "User VC issuer is not trusted")
    if vc.get("issuer") and vc.get("issuer") != issuer:
        raise HTTPException(403, "User VC issuer claim mismatch")
    if payload.get("sub") and payload.get("sub") != did:
        raise HTTPException(403, "User VC subject DID claim mismatch")
    if not did.startswith("did:web:"):
        raise HTTPException(403, "User VC subject must be a did:web identifier")
    if expected_linked_participant and linked_participant != expected_linked_participant:
        raise HTTPException(403, "User VC is not linked to this participant")
    if payload.get("nbf") is not None and float(payload["nbf"]) > now:
        raise HTTPException(401, "User VC is not valid yet")
    if payload.get("exp") is not None and float(payload["exp"]) <= now:
        raise HTTPException(401, "User VC has expired")
    if required_roles and role not in required_roles:
        raise HTTPException(403, f"User VC role {role!r} is not allowed")
    if credential_status_url or credential_status_path:
        _verify_credential_status(vc, credential_status_path, credential_status_url)

    return UserCredential(
        did=did,
        subject_id=subject_id,
        role=role,
        issuer=issuer,
        linked_participant=str(linked_participant) if linked_participant else None,
    )


def _verify_credential_status(
    vc: dict[str, Any],
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
) -> None:
    status = vc.get("credentialStatus")
    if not isinstance(status, dict):
        raise HTTPException(401, "User VC has no credentialStatus")

    status_list = _load_credential_status_list(credential_status_path, credential_status_url)

    entry = (status_list.get("credentials") or {}).get(vc.get("id"))
    if not isinstance(entry, dict):
        raise HTTPException(401, "User VC is not present in credential status list")
    if entry.get("status") != "active":
        raise HTTPException(401, "User VC is not active")


def _load_credential_status_list(
    credential_status_path: str | None,
    credential_status_url: str | None,
) -> dict[str, Any]:
    if credential_status_url:
        try:
            req = Request(credential_status_url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HTTPException(503, "Credential status registry is not available") from exc

    if not credential_status_path:
        raise HTTPException(503, "Credential status registry is not configured")

    path = Path(credential_status_path)
    if not path.exists():
        raise HTTPException(503, "Credential status list is not available")
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise HTTPException(503, "Credential status list is invalid") from exc
