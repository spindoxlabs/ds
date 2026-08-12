import pytest
import json

import jwt

from identity_registry.services.crypto import generate_key_pair, load_private_key
from identity_registry.services.vc import (
    build_data_subject_credential,
    build_membership_credential,
    sign_credential,
)


def test_membership_credential_structure():
    vc = build_membership_credential(
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        subject_did="did:web:rec.dataspaces.localhost",
        role="provider",
        allowed_scopes=["dataspaces.query"],
        credentials_context_url="https://dataspaces.localhost/ns/credentials/v1",
        dataspace_uri="https://dataspaces.localhost/dataspace",
        status_list_credential_url="https://trust-anchor.dataspaces.localhost/status/1",
        suspension_list_credential_url="https://trust-anchor.dataspaces.localhost/status/2",
        status_list_index=0,
    )
    assert "VerifiableCredential" in vc["type"]
    assert "MembershipCredential" in vc["type"]
    assert vc["issuer"] == "did:web:trust-anchor.dataspaces.localhost"
    assert vc["credentialSubject"]["id"] == "did:web:rec.dataspaces.localhost"
    assert vc["credentialSubject"]["role"] == "Provider"
    assert vc["credentialSubject"]["allowedScopes"] == ["dataspaces.query"]
    # Both registers, on the one index they share. A membership credential that
    # named only the revocation register could be revoked and nothing else, so
    # suspending its holder would set a bit no verifier fetches.
    purposes = {e["statusPurpose"]: e for e in vc["credentialStatus"]}
    assert set(purposes) == {"revocation", "suspension"}
    assert all(e["type"] == "StatusList2021Entry" for e in vc["credentialStatus"])
    assert all(e["statusListIndex"] == "0" for e in vc["credentialStatus"])
    assert purposes["revocation"]["statusListCredential"].endswith("/status/1")
    assert purposes["suspension"]["statusListCredential"].endswith("/status/2")
    assert vc["id"].startswith("urn:uuid:")


@pytest.mark.rule("P-25")
def test_data_subject_credential_names_only_the_revocation_register():
    """A natural person's credential is revoked or it is not.

    Suspension is a *participant* lifecycle state; there is no in-between state
    for a `DataSubjectCredential` to be in. It stays a single object, which is
    also what `ds_auth._verify_credential_status` requires of it.
    """
    vc = build_data_subject_credential(
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        subject_did="did:web:rec.dataspaces.localhost:users:email-abc",
        credentials_context_url="https://dataspaces.localhost/ns/credentials/v1",
        dataspace_uri="https://dataspaces.localhost/dataspace",
        status_list_credential_url="https://trust-anchor.dataspaces.localhost/status/1",
        status_list_index=3,
    )
    assert isinstance(vc["credentialStatus"], dict)
    assert vc["credentialStatus"]["statusPurpose"] == "revocation"


def test_data_subject_credential_structure():
    vc = build_data_subject_credential(
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        subject_did="did:web:rec.dataspaces.localhost:users:email-abc",
        role="data-subject",
        linked_participant_did="did:web:rec.dataspaces.localhost",
        allowed_actions=["consent.manage"],
        credentials_context_url="https://dataspaces.localhost/ns/credentials/v1",
        dataspace_uri="https://dataspaces.localhost/dataspace",
        status_list_credential_url="https://trust-anchor.dataspaces.localhost/status/1",
        status_list_index=1,
    )
    assert "DataSubjectCredential" in vc["type"]
    assert vc["credentialSubject"]["linkedParticipant"] == "did:web:rec.dataspaces.localhost"
    assert vc["credentialSubject"]["allowedActions"] == ["consent.manage"]


def test_sign_credential_adds_proof():
    kp = generate_key_pair("did:web:trust-anchor.dataspaces.localhost")
    vc = build_membership_credential(
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        subject_did="did:web:rec.dataspaces.localhost",
        role="provider",
        allowed_scopes=["dataspaces.query"],
        credentials_context_url="https://dataspaces.localhost/ns/credentials/v1",
        dataspace_uri="https://dataspaces.localhost/dataspace",
        status_list_credential_url="https://trust-anchor.dataspaces.localhost/status/1",
        suspension_list_credential_url="https://trust-anchor.dataspaces.localhost/status/2",
        status_list_index=0,
    )
    signed = sign_credential(vc, kp.private_jwk, kp.kid)

    assert "proof" in signed
    assert signed["proof"]["type"] == "JsonWebSignature2020"
    assert signed["proof"]["verificationMethod"] == kp.kid
    assert signed["proof"]["proofPurpose"] == "assertionMethod"


def test_sign_credential_jws_verifiable():
    kp = generate_key_pair("did:web:trust-anchor.dataspaces.localhost")
    vc = build_membership_credential(
        issuer_did="did:web:trust-anchor.dataspaces.localhost",
        subject_did="did:web:rec.dataspaces.localhost",
        role="provider",
        allowed_scopes=["dataspaces.query"],
        credentials_context_url="https://dataspaces.localhost/ns/credentials/v1",
        dataspace_uri="https://dataspaces.localhost/dataspace",
        status_list_credential_url="https://trust-anchor.dataspaces.localhost/status/1",
        suspension_list_credential_url="https://trust-anchor.dataspaces.localhost/status/2",
        status_list_index=0,
    )
    signed = sign_credential(vc, kp.private_jwk, kp.kid)

    jws_token = signed["proof"]["jws"]
    public_key = load_private_key(kp.private_jwk).public_key()

    decoded = jwt.decode(
        jws_token,
        public_key,
        algorithms=["ES256"],
        options={"verify_aud": False},
    )
    assert decoded["iss"] == "did:web:trust-anchor.dataspaces.localhost"
    assert decoded["sub"] == "did:web:rec.dataspaces.localhost"
    assert decoded["vc"]["type"] == ["VerifiableCredential", "MembershipCredential"]
