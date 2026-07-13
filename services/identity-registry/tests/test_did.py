from identity_registry.services.crypto import generate_key_pair
from identity_registry.services.did import build_did_document


def test_participant_did_document():
    kp = generate_key_pair("did:web:rec.dataspaces.localhost")
    doc = build_did_document(
        did="did:web:rec.dataspaces.localhost",
        public_jwk=kp.public_jwk,
        did_type="participant",
        service_endpoints=[
            {"type": "DSPEndpoint", "serviceEndpoint": "https://rec.dataspaces.localhost/protocol"},
            {"type": "CredentialService", "serviceEndpoint": "https://vc-wallet-rec.dataspaces.localhost/api/v1"},
        ],
    )
    assert doc["id"] == "did:web:rec.dataspaces.localhost"
    assert doc["@context"][0] == "https://www.w3.org/ns/did/v1"
    assert len(doc["verificationMethod"]) == 1
    vm = doc["verificationMethod"][0]
    assert vm["type"] == "JsonWebKey2020"
    assert vm["controller"] == "did:web:rec.dataspaces.localhost"
    assert "d" not in vm["publicKeyJwk"]
    assert "authentication" in doc
    assert "assertionMethod" in doc
    assert len(doc["service"]) == 2


def test_trust_anchor_did_document():
    kp = generate_key_pair("did:web:trust-anchor.dataspaces.localhost")
    doc = build_did_document(
        did="did:web:trust-anchor.dataspaces.localhost",
        public_jwk=kp.public_jwk,
        did_type="trust-anchor",
    )
    assert "authentication" not in doc
    assert "assertionMethod" in doc
    assert "service" not in doc


def test_user_did_document_no_auth():
    kp = generate_key_pair("did:web:users.dataspaces.localhost:email-abc123")
    doc = build_did_document(
        did="did:web:users.dataspaces.localhost:email-abc123",
        public_jwk=kp.public_jwk,
        did_type="user",
    )
    assert "authentication" not in doc
