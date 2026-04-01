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
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import get_settings

app = FastAPI(title="ds-vc-wallet", version="0.1.0")


def _load_credentials() -> list[dict[str, Any]]:
    s = get_settings()
    base = Path(s.credentials_path)
    if not base.exists():
        return []
    return [
        json.loads(f.read_text())
        for f in sorted(base.glob("*.json"))
    ]


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

    presentation = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "type": ["VerifiablePresentation"],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "holder": s.participant_did,
        "verifiableCredential": credentials,
    }
    return JSONResponse(content=presentation, media_type="application/ld+json")
