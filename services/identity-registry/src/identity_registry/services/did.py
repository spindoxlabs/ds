from __future__ import annotations

from typing import Any


def build_did_document(
    did: str,
    public_jwk: dict,
    did_type: str = "participant",
    service_endpoints: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    kid = public_jwk["kid"]

    doc: dict[str, Any] = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "id": did,
        "verificationMethod": [
            {
                "id": kid,
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": {
                    k: v for k, v in public_jwk.items() if k != "d"
                },
            }
        ],
        "assertionMethod": [kid],
    }

    if did_type == "participant":
        doc["authentication"] = [kid]

    if service_endpoints:
        doc["service"] = [
            {
                "id": f"{did}#{ep.get('type', 'service').lower().replace(' ', '-')}",
                "type": ep["type"],
                "serviceEndpoint": ep["serviceEndpoint"],
            }
            for ep in service_endpoints
        ]

    return doc
