from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from .crypto import create_jws, generate_credential_id, load_private_key

W3C_CREDENTIALS_V1 = "https://www.w3.org/2018/credentials/v1"
JWS_2020_V1 = "https://w3id.org/security/suites/jws-2020/v1"


def build_membership_credential(
    *,
    issuer_did: str,
    subject_did: str,
    role: str,
    allowed_scopes: list[str],
    credentials_context_url: str,
    dataspace_uri: str,
    status_list_credential_url: str,
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
        "credentialStatus": {
            "id": f"{status_list_credential_url}#{status_list_index}",
            "type": "StatusList2021Entry",
            "statusPurpose": "revocation",
            "statusListIndex": str(status_list_index),
            "statusListCredential": status_list_credential_url,
        },
    }


def build_data_subject_credential(
    *,
    issuer_did: str,
    subject_did: str,
    role: str | None = None,
    linked_participant_did: str | None = None,
    allowed_actions: list[str] | None = None,
    credentials_context_url: str,
    dataspace_uri: str,
    status_list_credential_url: str,
    status_list_index: int,
    credential_id: str | None = None,
    ttl_days: int = 365,
) -> dict[str, Any]:
    cred_id = credential_id or generate_credential_id()
    now = datetime.now(UTC)

    subject: dict[str, Any] = {
        "id": subject_did,
        "memberOf": dataspace_uri,
    }
    if role:
        subject["role"] = role
    if linked_participant_did:
        subject["linkedParticipant"] = linked_participant_did
    if allowed_actions:
        subject["allowedActions"] = allowed_actions

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
        "credentialStatus": {
            "id": f"{status_list_credential_url}#{status_list_index}",
            "type": "StatusList2021Entry",
            "statusPurpose": "revocation",
            "statusListIndex": str(status_list_index),
            "statusListCredential": status_list_credential_url,
        },
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
        "credentialStatus": {
            "id": f"{status_list_credential_url}#{status_list_index}",
            "type": "StatusList2021Entry",
            "statusPurpose": "revocation",
            "statusListIndex": str(status_list_index),
            "statusListCredential": status_list_credential_url,
        },
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
