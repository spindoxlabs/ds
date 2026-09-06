from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from .crypto import create_jws, generate_credential_id, load_private_key

W3C_CREDENTIALS_V1 = "https://www.w3.org/2018/credentials/v1"
JWS_2020_V1 = "https://w3id.org/security/suites/jws-2020/v1"


def _status_entry(url: str, index: int, purpose: str) -> dict[str, Any]:
    return {
        "id": f"{url}#{index}",
        "type": "StatusList2021Entry",
        "statusPurpose": purpose,
        "statusListIndex": str(index),
        "statusListCredential": url,
    }


def _suspendable_credential_status(
    *,
    status_list_credential_url: str,
    suspension_list_credential_url: str,
    status_list_index: int,
) -> list[dict[str, Any]]:
    """Both registers, on the one index they share.

    A credential carries **two** `credentialStatus` entries because suspension
    and revocation are different answers: one is reversible and one is not, and
    a verifier can only tell them apart if the credential names both registers.
    A credential naming only the revocation register can be revoked and nothing
    else — suspending its holder would set a bit nobody reads.

    Emitting a list rather than an object is safe for every reader that matters:
    EDC's `BaseRevocationListService` enables Jackson's
    `ACCEPT_SINGLE_VALUE_AS_ARRAY`, so both shapes parse, and
    `RevocationServiceRegistryImpl` checks each entry it finds. `ds_auth`'s
    `_verify_credential_status` accepts both shapes for the same reason.

    **Every credential this registry issues uses this**, people included. It was
    participants only until a role change had to be expressible: a superseded
    credential that cannot be suspended leaves two valid credentials making
    different claims about the same person.
    """
    return [
        _status_entry(status_list_credential_url, status_list_index, "revocation"),
        _status_entry(suspension_list_credential_url, status_list_index, "suspension"),
    ]


def build_membership_credential(
    *,
    issuer_did: str,
    subject_did: str,
    role: str,
    allowed_scopes: list[str],
    credentials_context_url: str,
    dataspace_uri: str,
    status_list_credential_url: str,
    suspension_list_credential_url: str,
    status_list_index: int,
    credential_id: str | None = None,
    ttl_days: int = 365,
) -> dict[str, Any]:
    cred_id = credential_id or generate_credential_id()
    now = datetime.now(UTC)

    return {
        "@context": [W3C_CREDENTIALS_V1, JWS_2020_V1, credentials_context_url],
        "id": cred_id,
        "type": ["VerifiableCredential", "MembershipCredential"],
        "issuer": issuer_did,
        "issuanceDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expirationDate": (now + timedelta(days=ttl_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "credentialSubject": {
            "id": subject_did,
            "memberOf": dataspace_uri,
            "role": role.capitalize(),
            "allowedScopes": allowed_scopes,
        },
        "credentialStatus": _suspendable_credential_status(
            status_list_credential_url=status_list_credential_url,
            suspension_list_credential_url=suspension_list_credential_url,
            status_list_index=status_list_index,
        ),
    }


def build_data_subject_credential(
    *,
    issuer_did: str,
    subject_did: str,
    role: str | None = None,
    community_role: str | None = None,
    linked_participant_did: str | None = None,
    allowed_actions: list[str] | None = None,
    credentials_context_url: str,
    dataspace_uri: str,
    status_list_credential_url: str,
    suspension_list_credential_url: str,
    status_list_index: int,
    credential_id: str | None = None,
    ttl_days: int = 365,
    verified_by: str | None = None,
    verification_method: str | None = None,
) -> dict[str, Any]:
    """A credential for a natural person.

    `verified_by` / `verification_method` record **who established this person's
    identity and how** (`D-53`). The dataspace layer does not do KYC — whoever
    runs onboarding does, and for CEEDS BUC#1 that is the energy community. So
    the credential carries the attestation rather than implying an assurance
    level nobody here established, which is the same invariant `verified_by` +
    `evidence_ref` already carry for an organisation.

    `DSSC-IAM-14` asks for assurance aligned with KYC practice. Ours is
    *whatever the onboarding wizard checked* — worth stating, and useless unless
    it travels with the credential.

    `community_role` is what a **role change** changes, and it is a claim rather
    than a credential type so that a person keeps one credential per protocol
    role instead of accumulating one per community role they have ever held. A
    credential is immutable, so changing it is a reissue: see
    `services/role_transition.py`.
    """
    cred_id = credential_id or generate_credential_id()
    now = datetime.now(UTC)

    subject: dict[str, Any] = {
        "id": subject_did,
        "memberOf": dataspace_uri,
    }
    if role:
        subject["role"] = role
    if community_role:
        # **`communityRole`, not `role`.** `role` is the *VC* role — `DataSubject`
        # or `ConsumerUser` — and ds-connector and ds-provenance check it as
        # `required_roles` on every call (`ds_auth.verify_user_vc_jwt`). Writing
        # a community role such as `prosumer` there would 403 the holder out of
        # every route they could previously reach. Two different questions, two
        # claims: what this person may do in the protocol, and what they are in
        # their energy community.
        subject["communityRole"] = community_role
    if linked_participant_did:
        subject["linkedParticipant"] = linked_participant_did
    if allowed_actions:
        subject["allowedActions"] = allowed_actions
    if verified_by:
        subject["verifiedBy"] = verified_by
    if verification_method:
        subject["verificationMethod"] = verification_method

    return {
        "@context": [W3C_CREDENTIALS_V1, JWS_2020_V1, credentials_context_url],
        "id": cred_id,
        "type": ["VerifiableCredential", "DataSubjectCredential"],
        "issuer": issuer_did,
        "issuanceDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expirationDate": (now + timedelta(days=ttl_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "credentialSubject": subject,
        # **Both registers**, as an organisation's credential has always
        # carried. This named the revocation register only, on the argument that
        # a person's credential is revoked or it is not. That argument does not
        # survive a *claim* changing: when what a credential says about somebody
        # stops being true — a consumer commissions generation and becomes a
        # prosumer — the model's answer is to retire the old credential and
        # issue its successor, and "retire" here has to mean suspension. A
        # revocation would say the attestation was withdrawn; it was not, it was
        # superseded, and the person may hold a successor tomorrow.
        "credentialStatus": _suspendable_credential_status(
            status_list_credential_url=status_list_credential_url,
            suspension_list_credential_url=suspension_list_credential_url,
            status_list_index=status_list_index,
        ),
    }


def build_organization_credential(
    *,
    issuer_did: str,
    subject_did: str,
    legal_name: str,
    registration_number: str | None,
    registration_type: str | None,
    hq_country_code: str | None,
    legal_country_code: str | None,
    roles: list[str],
    allowed_scopes: list[str],
    credentials_context_url: str,
    dataspace_uri: str,
    status_list_credential_url: str,
    suspension_list_credential_url: str,
    status_list_index: int,
    parent_organizations: list[str] | None = None,
    sub_organizations: list[str] | None = None,
    dsp_address: str | None = None,
    credential_id: str | None = None,
    ttl_days: int = 365,
) -> dict[str, Any]:
    """Build an OrganizationCredential.

    Shape-compatible with ``gx:LegalParticipant`` (Block D §5.2): the address
    fields nest ``countryCode`` (ISO 3166-2) and ``registrationType`` uses the
    Gaia-X enum. Not full GXDCH compliance — no notarised LRN, no SHACL.
    Mirrors ``build_membership_credential`` (same contexts, same
    ``StatusList2021Entry`` block).
    """
    cred_id = credential_id or generate_credential_id()
    now = datetime.now(UTC)

    subject: dict[str, Any] = {
        "id": subject_did,
        "memberOf": dataspace_uri,
        "legalName": legal_name,
        "roles": roles,
        "allowedScopes": allowed_scopes,
    }
    if registration_number:
        subject["registrationNumber"] = registration_number
    if registration_type:
        subject["registrationType"] = registration_type
    if hq_country_code:
        subject["headquartersAddress"] = {"countryCode": hq_country_code}
    if legal_country_code:
        subject["legalAddress"] = {"countryCode": legal_country_code}
    if parent_organizations:
        subject["parentOrganization"] = parent_organizations
    if sub_organizations:
        subject["subOrganization"] = sub_organizations
    if dsp_address:
        subject["dspAddress"] = dsp_address

    return {
        "@context": [W3C_CREDENTIALS_V1, JWS_2020_V1, credentials_context_url],
        "id": cred_id,
        "type": ["VerifiableCredential", "OrganizationCredential"],
        "issuer": issuer_did,
        "issuanceDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expirationDate": (now + timedelta(days=ttl_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "credentialSubject": subject,
        "credentialStatus": _suspendable_credential_status(
            status_list_credential_url=status_list_credential_url,
            suspension_list_credential_url=suspension_list_credential_url,
            status_list_index=status_list_index,
        ),
    }


def sign_credential(
    vc: dict[str, Any],
    issuer_private_jwk: dict,
    kid: str,
) -> dict[str, Any]:
    private_key = load_private_key(issuer_private_jwk)

    now = int(time.time())
    jwt_header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    jwt_payload = {
        "iss": vc["issuer"],
        "sub": vc["credentialSubject"]["id"],
        "nbf": now,
        "exp": now + 365 * 86400,
        "jti": vc["id"],
        "vc": vc,
    }

    if "expirationDate" in vc:
        exp_dt = datetime.strptime(vc["expirationDate"], "%Y-%m-%dT%H:%M:%SZ")
        jwt_payload["exp"] = int(exp_dt.replace(tzinfo=UTC).timestamp())

    jws_token = create_jws(jwt_header, jwt_payload, private_key)

    vc["proof"] = {
        "type": "JsonWebSignature2020",
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verificationMethod": kid,
        "proofPurpose": "assertionMethod",
        "jws": jws_token,
    }

    return vc
