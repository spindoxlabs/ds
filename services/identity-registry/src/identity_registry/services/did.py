from __future__ import annotations

from typing import Any


def build_did_document(
    did: str,
    public_jwk: dict | None,
    did_type: str = "participant",
    service_endpoints: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """The DID document for *did*.

    ``public_jwk`` may be **None**, and a document without one is not a
    degraded document — it is the honest one for a subject (`D-49`).

    A natural person is not a credential holder here: they present nothing, sign
    nothing, and have no wallet. Their `DataSubjectCredential` is signed by the
    trust anchor and verified against the *anchor's* key
    (`ds_auth.user_credentials.verify_user_vc_jwt`), so a key of their own would
    be generated, stored, and read by nothing — custody with no purpose and an
    impersonation surface with no upside.

    What the document must still do is **resolve**, because the DID is a subject
    identifier that consent records, provenance events and `credentialSubject.id`
    all point at. So it carries `id` and any service entries, and asserts no
    verification method it cannot back. When a wallet exists the person supplies
    a public key and the method appears — nothing here has to be undone.
    """
    doc: dict[str, Any] = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "id": did,
    }

    if public_jwk is not None:
        kid = public_jwk["kid"]
        doc["verificationMethod"] = [
            {
                "id": kid,
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": {
                    k: v for k, v in public_jwk.items() if k != "d"
                },
            }
        ]
        doc["assertionMethod"] = [kid]
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
