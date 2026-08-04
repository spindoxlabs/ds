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


#: The segment separating a participant's host from a person it holds
#: credentials for. `did:web` uses `:` for path segments, so
#: `did:web:rec.example.org:users:alice` resolves at
#: `https://rec.example.org/users/alice/did.json` — the participant's own host,
#: through the same `/dids` route every participant already serves.
USER_SEGMENT = "users"


class SubjectNamespaceError(Exception):
    """A person's identifier cannot be placed without naming a custodian."""


def subject_did_for(linked_participant_did: str | None, subject_id: str) -> str:
    """Where a natural person's identifier lives — `D-50`, `DID-11` step 2.

    It used to be `did:web:users.<anchor-domain>:<id>`: every person in the
    dataspace named under the **trust anchor's** domain, which said that the
    anchor is the party they belong to. It is not. A person is onboarded by an
    organisation, their credentials are held by that organisation, and the
    identifier should say which one — this is the four-corner model's
    *participant agent service provider* relationship, written into the name.

    **Refused without a participant**, rather than falling back to the anchor.
    A person with no organisation holding their credentials has no custodian,
    and minting them an identifier under the anchor's domain would recreate the
    thing this replaces while looking like a default.
    """
    if not linked_participant_did:
        raise SubjectNamespaceError(
            "a natural person's DID lives in the namespace of the organisation "
            "that holds their credentials, so linked_participant_did is required "
            "— there is nowhere to put an identifier for a person no participant "
            "is custodian for (D-50)"
        )
    if not linked_participant_did.startswith("did:web:"):
        raise SubjectNamespaceError(
            f"linked_participant_did must be a did:web identifier, got "
            f"{linked_participant_did!r}"
        )
    return f"{linked_participant_did}:{USER_SEGMENT}:{subject_id}"


def subject_id_of(did: str) -> str | None:
    """The person's id inside a subject DID, or None if this is not one."""
    marker = f":{USER_SEGMENT}:"
    if not did.startswith("did:web:") or marker not in did:
        return None
    return did.rsplit(marker, 1)[1] or None


def custodian_of(did: str) -> str | None:
    """The participant whose namespace a subject DID sits in.

    The inverse of `subject_did_for`, and what tells a registry *whose* person
    this is — which is the question the old flat `users.<anchor>` namespace made
    unanswerable.
    """
    marker = f":{USER_SEGMENT}:"
    if not did.startswith("did:web:") or marker not in did:
        return None
    return did.rsplit(marker, 1)[0] or None
