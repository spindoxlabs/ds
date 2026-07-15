#!/usr/bin/env python3
"""Configurable VC issuer and credential status registry manager."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePrivateNumbers,
    EllipticCurvePublicNumbers,
    SECP256R1,
)
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_SUBJECT_ID = re.compile(r"^[A-Za-z0-9._+-]{1,128}$")

DEFAULTS = {
    "issuer_did": "did:web:trust-anchor.dataspaces.localhost",
    "trust_anchor_key": str(REPO_ROOT / "services/connector/config/trust-anchor-key.json"),
    "credentials_dir": str(REPO_ROOT / "data/credentials"),
    "status_list_path": str(REPO_ROOT / "data/credentials/status-list.json"),
    "status_list_url": "https://trust-anchor.dataspaces.localhost/credentials/status-list.json",
    "did_documents_dir": str(REPO_ROOT / "services/caddy/did"),
    "user_profile_endpoint": "http://localhost:30004/my-data",
    "dataspace_id": "https://dataspaces.localhost/dataspace",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
    "users_did_prefix": "did:web:users.dataspaces.localhost",
}

USER_TEMPLATES = [
    {
        "subject_id": "ah-00003",
        "role": "DataSubject",
        "out_dir": "users/ah-00003",
        "allowed_actions": ["consent.manage", "data.share"],
    },
    {
        "subject_id": "test",
        "role": "ConsumerUser",
        "out_dir": "users/test",
        "allowed_actions": ["catalog.read", "contract.negotiate", "transfer.query"],
    },
]


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(value: str) -> bytes:
    padding = 4 - len(value) % 4
    return base64.urlsafe_b64decode(value + "=" * (padding % 4))


def read_env_file(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def setting(
    explicit: str | None,
    env: dict[str, str],
    env_names: tuple[str, ...],
    default_key: str,
) -> str:
    if explicit:
        return explicit
    for name in env_names:
        if os.environ.get(name):
            return os.environ[name]
        if env.get(name):
            return env[name]
    return DEFAULTS[default_key]


def load_private_key(jwk: dict[str, Any]):
    x = int.from_bytes(b64url_decode(jwk["x"]), "big")
    y = int.from_bytes(b64url_decode(jwk["y"]), "big")
    d = int.from_bytes(b64url_decode(jwk["d"]), "big")
    public_numbers = EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1())
    private_numbers = EllipticCurvePrivateNumbers(private_value=d, public_numbers=public_numbers)
    return private_numbers.private_key()


def sign_vc(vc: dict[str, Any], private_key, kid: str, ttl_days: int) -> dict[str, Any]:
    now = int(time.time())
    payload = {
        "iss": vc["issuer"],
        "sub": vc["credentialSubject"]["id"],
        "nbf": now,
        "exp": now + ttl_days * 24 * 3600,
        "jti": vc["id"],
        "vc": vc,
    }
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    signing_input = ".".join(
        [
            b64url(json.dumps(header, separators=(",", ":")).encode()),
            b64url(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    ).encode()
    der_signature = private_key.sign(signing_input, ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    vc["proof"] = {
        "type": "JsonWebSignature2020",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verificationMethod": kid,
        "proofPurpose": "assertionMethod",
        "jws": f"{signing_input.decode()}.{b64url(raw_signature)}",
    }
    return vc


def attach_credential_status(vc: dict[str, Any], status_list_url: str, index: int) -> dict[str, Any]:
    vc["credentialStatus"] = {
        "id": f"{status_list_url}#{index}",
        "type": "DataspaceCredentialStatusEntry",
        "statusPurpose": "revocation",
        "statusListCredential": status_list_url,
        "statusListIndex": str(index),
    }
    return vc


def issue_membership_vc(
    participant_did: str,
    role: str,
    issuer_did: str,
    dataspace_id: str,
    status_list_url: str,
    status_index: int,
    key_jwk: dict[str, Any],
    ttl_days: int,
) -> dict[str, Any]:
    vc = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
            "https://dataspaces.localhost/ns/credentials/v1",
        ],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": [
            "VerifiableCredential",
            "MembershipCredential",
            "org.eclipse.dspace.dcp.vc.type:MembershipCredential:read",
        ],
        "issuer": issuer_did,
        "issuanceDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentialSubject": {
            "id": participant_did,
            "memberOf": dataspace_id,
            "role": role,
            "allowedScopes": ["dataspaces.query"],
        },
    }
    attach_credential_status(vc, status_list_url, status_index)
    return sign_vc(vc, load_private_key(key_jwk), key_jwk["kid"], ttl_days)


def issue_user_vc(
    user: dict[str, Any],
    issuer_did: str,
    linked_participant_did: str,
    users_did_prefix: str,
    status_list_url: str,
    status_index: int,
    key_jwk: dict[str, Any],
    ttl_days: int,
) -> dict[str, Any]:
    subject_did = f"{users_did_prefix}:{user['subject_id']}"
    vc = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
            "https://dataspaces.localhost/ns/credentials/v1",
        ],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "DataspaceUserCredential"],
        "issuer": issuer_did,
        "issuanceDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentialSubject": {
            "id": subject_did,
            "subjectId": user["subject_id"],
            "role": user["role"],
            "linkedParticipant": linked_participant_did,
            "allowedActions": user["allowed_actions"],
        },
    }
    attach_credential_status(vc, status_list_url, status_index)
    return sign_vc(vc, load_private_key(key_jwk), key_jwk["kid"], ttl_days)


def status_entry(vc: dict[str, Any]) -> dict[str, Any]:
    subject = vc["credentialSubject"]
    return {
        "status": "active",
        "subject": subject["id"],
        "subjectId": subject.get("subjectId"),
        "type": vc["type"],
        "credentialStatus": vc["credentialStatus"],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def did_web_document_path(did_documents_dir: Path, subject_did: str) -> Path:
    if not subject_did.startswith("did:web:"):
        raise SystemExit(f"Only did:web user DID documents are supported: {subject_did}")
    return did_documents_dir.joinpath(*subject_did.removeprefix("did:web:").split(":")) / "did.json"


def user_did_document(subject_did: str, profile_endpoint: str) -> dict[str, Any]:
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": subject_did,
        "service": [
            {
                "id": f"{subject_did}#profile",
                "type": "DataspaceUserProfile",
                "serviceEndpoint": profile_endpoint,
            }
        ],
    }


def validate_subject_id(subject_id: str) -> str:
    value = subject_id.strip()
    if not value:
        raise SystemExit("Subject id cannot be empty")
    if "/" in value or "\\" in value or value in {".", ".."} or ".." in value.split(":"):
        raise SystemExit("Subject id cannot contain path separators or traversal segments")
    if not SAFE_SUBJECT_ID.fullmatch(value):
        raise SystemExit("Subject id contains characters that are not valid for DID issuance")
    return value


def parse_allowed_actions(values: list[str] | None) -> list[str]:
    if not values:
        return ["consent.manage", "data.share"]
    actions: list[str] = []
    for raw in values:
        for item in raw.split(","):
            action = item.strip()
            if action and action not in actions:
                actions.append(action)
    if not actions:
        raise SystemExit("At least one allowed action is required")
    return actions


def load_status_list(path: Path, issuer_did: str, status_list_url: str) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://dataspaces.localhost/ns/credentials/status/v1",
        ],
        "id": status_list_url,
        "type": ["VerifiableCredential", "DataspaceCredentialStatusList"],
        "issuer": issuer_did,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentials": {},
    }


def next_status_index(status_list: dict[str, Any]) -> int:
    indexes: list[int] = []
    for entry in (status_list.get("credentials") or {}).values():
        credential_status = entry.get("credentialStatus") or {}
        raw_index = credential_status.get("statusListIndex")
        if raw_index is not None:
            indexes.append(int(raw_index))
    return max(indexes, default=-1) + 1


def issue_user(args: argparse.Namespace) -> int:
    env = read_env_file(args.env_file)
    issuer_did = setting(
        args.issuer_did,
        env,
        ("TRUST_ANCHOR_DID_WEB", "VC_ISSUER_DID"),
        "issuer_did",
    )
    consumer_did = setting(args.consumer_did, env, ("CONSUMER_DID_WEB",), "consumer_did")
    trust_anchor_key = resolve_path(
        setting(
            args.trust_anchor_key,
            env,
            ("TRUST_ANCHOR_PRIVATE_KEY_FILE", "TRUST_ANCHOR_KEY_FILE"),
            "trust_anchor_key",
        )
    )
    credentials_dir = resolve_path(
        setting(args.credentials_dir, env, ("CREDENTIALS_DIR",), "credentials_dir")
    )
    status_list_path = resolve_path(
        setting(args.status_list_path, env, ("CREDENTIAL_STATUS_LIST_FILE",), "status_list_path")
    )
    status_list_url = setting(
        args.status_list_url,
        env,
        ("CONNECTOR_CREDENTIAL_STATUS_URL", "VC_WALLET_CREDENTIAL_STATUS_URL"),
        "status_list_url",
    )
    users_did_prefix = setting(
        args.users_did_prefix,
        env,
        ("USERS_DID_WEB_PREFIX",),
        "users_did_prefix",
    )
    did_documents_dir = resolve_path(
        setting(args.did_documents_dir, env, ("DID_DOCUMENTS_DIR",), "did_documents_dir")
    )
    user_profile_endpoint = setting(
        args.user_profile_endpoint,
        env,
        ("USER_PROFILE_ENDPOINT", "PORTAL_USER_PROFILE_ENDPOINT"),
        "user_profile_endpoint",
    )
    linked_participant_did = args.linked_participant_did or consumer_did
    subject_id = validate_subject_id(args.subject_id)
    out_dir = args.out_dir or f"users/{subject_id}"
    out_path = credentials_dir / out_dir / "user-vc.json"

    if out_path.exists() and not args.force:
        vc = json.loads(out_path.read_text())
        subject_did = vc.get("credentialSubject", {}).get("id")
        if not subject_did:
            raise SystemExit(f"Existing VC is missing credentialSubject.id: {out_path}")
        did_document_path = did_web_document_path(did_documents_dir, subject_did)
        if not args.skip_did_document and not did_document_path.exists():
            write_json(did_document_path, user_did_document(subject_did, user_profile_endpoint))
        evidence = {
            "profile": args.profile,
            "issuer": vc.get("issuer", issuer_did),
            "subjectId": subject_id,
            "subjectDid": subject_did,
            "credentialId": vc.get("id"),
            "didDocumentPath": str(did_document_path),
            "path": str(out_path),
            "status": "exists",
        }
        print(json.dumps(evidence, indent=2))
        return 0

    if not trust_anchor_key.exists():
        raise SystemExit(f"Trust anchor key not found: {trust_anchor_key}")

    key_jwk = json.loads(trust_anchor_key.read_text())
    status_list = load_status_list(status_list_path, issuer_did, status_list_url)
    status_index = next_status_index(status_list)
    user = {
        "subject_id": subject_id,
        "role": args.role,
        "out_dir": out_dir,
        "allowed_actions": parse_allowed_actions(args.allowed_action),
    }
    vc = issue_user_vc(
        user,
        issuer_did,
        linked_participant_did,
        users_did_prefix,
        status_list_url,
        status_index,
        key_jwk,
        args.ttl_days,
    )
    write_json(out_path, vc)
    did_document_path = did_web_document_path(did_documents_dir, vc["credentialSubject"]["id"])
    if not args.skip_did_document:
        write_json(
            did_document_path,
            user_did_document(vc["credentialSubject"]["id"], user_profile_endpoint),
        )

    credentials = status_list.setdefault("credentials", {})
    credentials[vc["id"]] = status_entry(vc)
    status_list["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(status_list_path, status_list)

    evidence = {
        "profile": args.profile,
        "issuer": issuer_did,
        "statusList": status_list_url,
        "statusListPath": str(status_list_path),
        "subjectId": subject_id,
        "subjectDid": vc["credentialSubject"]["id"],
        "credentialId": vc["id"],
        "didDocumentPath": str(did_document_path),
        "path": str(out_path),
        "status": "issued",
        "generatedAt": status_list["updated"],
    }
    if args.report_path:
        write_json(resolve_path(args.report_path), evidence)
    print(json.dumps(evidence, indent=2))
    return 0


def issue(args: argparse.Namespace) -> int:
    env = read_env_file(args.env_file)
    issuer_did = setting(args.issuer_did, env, ("TRUST_ANCHOR_DID_WEB", "VC_ISSUER_DID"), "issuer_did")
    provider_did = setting(args.provider_did, env, ("PROVIDER_DID_WEB",), "provider_did")
    consumer_did = setting(args.consumer_did, env, ("CONSUMER_DID_WEB",), "consumer_did")
    trust_anchor_key = resolve_path(
        setting(args.trust_anchor_key, env, ("TRUST_ANCHOR_PRIVATE_KEY_FILE", "TRUST_ANCHOR_KEY_FILE"), "trust_anchor_key")
    )
    credentials_dir = resolve_path(setting(args.credentials_dir, env, ("CREDENTIALS_DIR",), "credentials_dir"))
    status_list_path = resolve_path(
        setting(args.status_list_path, env, ("CREDENTIAL_STATUS_LIST_FILE",), "status_list_path")
    )
    status_list_url = setting(
        args.status_list_url,
        env,
        ("CONNECTOR_CREDENTIAL_STATUS_URL", "VC_WALLET_CREDENTIAL_STATUS_URL"),
        "status_list_url",
    )
    dataspace_id = setting(args.dataspace_id, env, ("DATASPACE_ID",), "dataspace_id")
    users_did_prefix = setting(args.users_did_prefix, env, ("USERS_DID_WEB_PREFIX",), "users_did_prefix")
    linked_participant_did = args.linked_participant_did or consumer_did

    if not trust_anchor_key.exists():
        raise SystemExit(f"Trust anchor key not found: {trust_anchor_key}")

    key_jwk = json.loads(trust_anchor_key.read_text())
    status_entries: dict[str, dict[str, Any]] = {}
    issued: list[dict[str, str]] = []
    status_index = 0

    for participant_did, role, out_dir in (
        (provider_did, "Provider", "provider"),
        (consumer_did, "Consumer", "consumer"),
    ):
        vc = issue_membership_vc(
            participant_did,
            role,
            issuer_did,
            dataspace_id,
            status_list_url,
            status_index,
            key_jwk,
            args.ttl_days,
        )
        out_path = credentials_dir / out_dir / "membership-vc.json"
        write_json(out_path, vc)
        status_entries[vc["id"]] = status_entry(vc)
        issued.append({"type": "membership", "subject": participant_did, "path": str(out_path)})
        status_index += 1

    for user in USER_TEMPLATES:
        vc = issue_user_vc(
            user,
            issuer_did,
            linked_participant_did,
            users_did_prefix,
            status_list_url,
            status_index,
            key_jwk,
            args.ttl_days,
        )
        out_path = credentials_dir / user["out_dir"] / "user-vc.json"
        write_json(out_path, vc)
        status_entries[vc["id"]] = status_entry(vc)
        issued.append({"type": "user", "subject": user["subject_id"], "path": str(out_path)})
        status_index += 1

    status_list = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://dataspaces.localhost/ns/credentials/status/v1",
        ],
        "id": status_list_url,
        "type": ["VerifiableCredential", "DataspaceCredentialStatusList"],
        "issuer": issuer_did,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentials": status_entries,
    }
    write_json(status_list_path, status_list)

    evidence = {
        "profile": args.profile,
        "issuer": issuer_did,
        "statusList": status_list_url,
        "statusListPath": str(status_list_path),
        "credentialsDir": str(credentials_dir),
        "issued": issued,
        "generatedAt": status_list["updated"],
    }
    if args.report_path:
        write_json(resolve_path(args.report_path), evidence)
    print(json.dumps(evidence, indent=2))
    return 0


def revoke(args: argparse.Namespace) -> int:
    status_list_path = resolve_path(args.status_list_path)
    if not status_list_path.exists():
        raise SystemExit(f"Credential status list not found: {status_list_path}")
    status_list = json.loads(status_list_path.read_text())
    credentials = status_list.get("credentials") or {}
    changed: list[str] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for credential_id, entry in credentials.items():
        if args.credential_id and credential_id != args.credential_id:
            continue
        if args.subject and args.subject not in {entry.get("subject"), entry.get("subjectId")}:
            continue
        entry["status"] = "revoked"
        entry["revokedAt"] = now
        entry["revocationReason"] = args.reason
        changed.append(credential_id)

    if not changed:
        raise SystemExit("No credential matched the revocation selector")

    status_list["updated"] = now
    write_json(status_list_path, status_list)
    evidence = {
        "statusListPath": str(status_list_path),
        "revoked": changed,
        "reason": args.reason,
        "generatedAt": now,
    }
    if args.report_path:
        write_json(resolve_path(args.report_path), evidence)
    print(json.dumps(evidence, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    issue_parser = subparsers.add_parser("issue", help="Issue membership and user VCs")
    issue_parser.add_argument("--env-file", type=Path)
    issue_parser.add_argument("--profile", default="dev")
    issue_parser.add_argument("--issuer-did")
    issue_parser.add_argument("--trust-anchor-key")
    issue_parser.add_argument("--credentials-dir")
    issue_parser.add_argument("--status-list-path")
    issue_parser.add_argument("--status-list-url")
    issue_parser.add_argument("--dataspace-id")
    issue_parser.add_argument("--provider-did")
    issue_parser.add_argument("--consumer-did")
    issue_parser.add_argument("--users-did-prefix")
    issue_parser.add_argument("--linked-participant-did")
    issue_parser.add_argument("--ttl-days", type=int, default=365)
    issue_parser.add_argument("--report-path")
    issue_parser.set_defaults(func=issue)

    user_parser = subparsers.add_parser(
        "issue-user",
        help="Issue one user VC without rewriting all credentials",
    )
    user_parser.add_argument("--env-file", type=Path)
    user_parser.add_argument("--profile", default="dev")
    user_parser.add_argument("--issuer-did")
    user_parser.add_argument("--trust-anchor-key")
    user_parser.add_argument("--credentials-dir")
    user_parser.add_argument("--status-list-path")
    user_parser.add_argument("--status-list-url")
    user_parser.add_argument("--consumer-did")
    user_parser.add_argument("--users-did-prefix")
    user_parser.add_argument("--did-documents-dir")
    user_parser.add_argument("--user-profile-endpoint")
    user_parser.add_argument("--linked-participant-did")
    user_parser.add_argument("--subject-id", required=True)
    user_parser.add_argument("--role", default="DataSubject")
    user_parser.add_argument("--allowed-action", action="append")
    user_parser.add_argument("--out-dir")
    user_parser.add_argument("--ttl-days", type=int, default=365)
    user_parser.add_argument("--report-path")
    user_parser.add_argument("--force", action="store_true")
    user_parser.add_argument("--skip-did-document", action="store_true")
    user_parser.set_defaults(func=issue_user)

    revoke_parser = subparsers.add_parser("revoke", help="Revoke a VC in a status list")
    revoke_parser.add_argument("--status-list-path", required=True)
    selector = revoke_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--credential-id")
    selector.add_argument("--subject")
    revoke_parser.add_argument("--reason", default="operator-request")
    revoke_parser.add_argument("--report-path")
    revoke_parser.set_defaults(func=revoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
