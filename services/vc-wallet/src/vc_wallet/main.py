"""ds-vc-wallet — minimal Verifiable Credential wallet / Credential Service.

Implements the DCP Credential Service API so that EDC can retrieve
VCs during DSP negotiation.

Endpoints (DCP Credential Service API subset):
  GET  /api/v1/credentials                list all held VCs
  GET  /api/v1/credentials/{id}           get a single VC
  POST /api/v1/presentations/query        return a VP matching the query
  GET  /health

VCs are stored as JSON files under $VC_WALLET_CREDENTIALS_PATH.
For dev, these are pre-issued by scripts/issue-vcs.py.
"""
from __future__ import annotations

import json
import time
import uuid
import base64
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    EllipticCurvePrivateNumbers,
    EllipticCurvePublicNumbers,
    SECP256R1,
)
from jose import jwt as jose_jwt

from .config import get_settings
from .metrics import install_metrics

app = FastAPI(title="ds-vc-wallet", version="0.1.0")
install_metrics(app, "ds-vc-wallet")


def _load_credentials() -> list[dict[str, Any]]:
    s = get_settings()
    base = Path(s.credentials_path)
    if not base.exists():
        return []
    credentials = [
        json.loads(f.read_text())
        for f in sorted(base.glob("*.json"))
    ]
    return _active_credentials(credentials)


def _active_credentials(credentials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s = get_settings()
    if not s.credential_status_url and not s.credential_status_path:
        return credentials
    status_list = _load_status_registry(s.credential_status_url, s.credential_status_path)
    entries = status_list.get("credentials") or {}
    active: list[dict[str, Any]] = []
    for credential in credentials:
        entry = entries.get(credential.get("id"))
        if isinstance(entry, dict) and entry.get("status") == "active":
            active.append(credential)
    return active


def _load_status_registry(status_url: str | None, status_path: str | None) -> dict[str, Any]:
    if status_url:
        try:
            req = Request(status_url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HTTPException(503, "Credential status registry is not available") from exc
    if not status_path:
        return {"credentials": {}}
    path = Path(status_path)
    if not path.exists():
        raise HTTPException(503, "Credential status list is not available")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(503, "Credential status list is invalid") from exc


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


def _load_private_key(path: str) -> tuple[EllipticCurvePrivateKey, str]:
    jwk = json.loads(Path(path).read_text())
    x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
    d = int.from_bytes(_b64url_decode(jwk["d"]), "big")
    public_numbers = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    private_numbers = EllipticCurvePrivateNumbers(private_value=d, public_numbers=public_numbers)
    return private_numbers.private_key(), jwk.get("kid", "key-1")


def _create_vp_token(credentials: list[dict[str, Any]]) -> str | None:
    s = get_settings()
    if not s.private_key_path:
        return None
    vc_tokens = [
        vc["proof"]["jws"]
        for vc in credentials
        if isinstance(vc.get("proof"), dict) and vc["proof"].get("jws")
    ]
    private_key, kid = _load_private_key(s.private_key_path)
    now = int(time.time())
    claims = {
        "iss": s.participant_did,
        "sub": s.participant_did,
        "nbf": now,
        "iat": now,
        "exp": now + 300,
        "jti": str(uuid.uuid4()),
        "vp": {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "holder": s.participant_did,
            "verifiableCredential": vc_tokens,
        },
    }
    return jose_jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": kid})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/credentials")
def list_credentials():
    return {"credentials": _load_credentials()}


@app.get("/api/v1/credentials/{credential_id}")
def get_credential(credential_id: str):
    for vc in _load_credentials():
        if vc.get("id") == credential_id:
            return vc
    raise HTTPException(404, "Credential not found")


@app.post("/api/v1/presentations/query")
async def query_presentations(body: dict[str, Any]):
    """Return a Verifiable Presentation containing matching VCs.

    The DCP query body contains a `presentationDefinition` with
    `input_descriptors`. For dev, we return all held VCs as a VP.
    """
    s = get_settings()
    credentials = _load_credentials()

    # Filter by type if requested
    requested_types: list[str] = []
    for desc in (body.get("presentationDefinition") or {}).get("input_descriptors", []):
        for constraint in (desc.get("constraints") or {}).get("fields", []):
            if "$.type" in constraint.get("path", []):
                for filt in (constraint.get("filter") or {}).get("contains", {}).get("const", []):
                    requested_types.append(filt)

    if requested_types:
        credentials = [
            vc for vc in credentials
            if any(t in vc.get("type", []) for t in requested_types)
        ]

    presentation = _create_vp_token(credentials) or {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "type": ["VerifiablePresentation"],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "holder": s.participant_did,
        "verifiableCredential": credentials,
    }
    response = {
        "@context": {
            "dcp": "https://w3id.org/tractusx-trust/v0.8/",
        },
        "@type": "dcp:PresentationResponseMessage",
        "dcp:presentation": {
            "@value": [presentation],
            "@type": "@json",
        },
    }
    return JSONResponse(content=response, media_type="application/ld+json")
