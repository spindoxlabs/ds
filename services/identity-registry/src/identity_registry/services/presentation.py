"""VP building — constructs Verifiable Presentations for DCP credential queries."""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models import Credential, Key
from .crypto import create_jws, decrypt_private_jwk, load_private_key


def _extract_requested_types(presentation_definition: dict[str, Any]) -> list[str]:
    types: list[str] = []
    for desc in presentation_definition.get("input_descriptors", []):
        for constraint in (desc.get("constraints") or {}).get("fields", []):
            if "$.type" in constraint.get("path", []):
                for filt in (
                    (constraint.get("filter") or {})
                    .get("contains", {})
                    .get("const", [])
                ):
                    types.append(filt)
    return types


async def build_presentation_response(
    db: AsyncSession,
    participant_did: str,
    presentation_definition: dict[str, Any],
) -> dict[str, Any]:
    """Build a DCP PresentationResponseMessage containing a VP JWT."""
    key_result = await db.execute(
        select(Key).where(
            Key.owner_did == participant_did,
            Key.active.is_(True),
        )
    )
    key = key_result.scalar_one_or_none()
    if not key:
        raise LookupError(f"No active key for participant: {participant_did}")

    cred_result = await db.execute(
        select(Credential).where(
            Credential.subject_did == participant_did,
            Credential.status == "active",
        )
    )
    credentials = [row.credential_json for row in cred_result.scalars().all()]

    requested_types = _extract_requested_types(presentation_definition)
    if requested_types:
        credentials = [
            vc
            for vc in credentials
            if any(t in vc.get("type", []) for t in requested_types)
        ]

    vc_tokens = [
        vc["proof"]["jws"]
        for vc in credentials
        if isinstance(vc.get("proof"), dict) and vc["proof"].get("jws")
    ]

    settings = get_settings()
    raw_jwk = decrypt_private_jwk(key.private_jwk, settings.encryption_key)
    private_key = load_private_key(raw_jwk)
    now = int(time.time())

    vp_claims = {
        "iss": participant_did,
        "sub": participant_did,
        "nbf": now,
        "iat": now,
        "exp": now + 300,
        "jti": str(uuid.uuid4()),
        "vp": {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "holder": participant_did,
            "verifiableCredential": vc_tokens,
        },
    }

    vp_jwt = create_jws({"alg": "ES256", "kid": key.kid}, vp_claims, private_key)

    return {
        "@context": {
            "dcp": "https://w3id.org/tractusx-trust/v0.8/",
        },
        "@type": "dcp:PresentationResponseMessage",
        "dcp:presentation": {
            "@value": [vp_jwt],
            "@type": "@json",
        },
    }
