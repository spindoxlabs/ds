#!/usr/bin/env python3
"""Bootstrap local production-like secrets, DID documents and EDC config.

DEPRECATED: This script pre-dates the identity-registry consolidation.
Keys, DIDs, and VCs are now managed by the identity-registry service.
Use `ir-cli bootstrap` and `ir-cli participant add` instead.
This script is retained for reference only and will be removed in a future release.
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_EXAMPLE = ROOT / ".env.production.example"
DEFAULT_ENV_OUT = ROOT / ".env.production"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_secret(path: Path, value: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n")
    path.chmod(0o600)


def generate_jwk(did: str) -> dict[str, str]:
    private_key = generate_private_key(SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    private_numbers = private_key.private_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(public_numbers.x.to_bytes(32, "big")),
        "y": b64url(public_numbers.y.to_bytes(32, "big")),
        "d": b64url(private_numbers.private_value.to_bytes(32, "big")),
        "kid": f"{did}#key-1",
        "use": "sig",
    }


def public_jwk(jwk: dict[str, str]) -> dict[str, str]:
    return {key: jwk[key] for key in ("kty", "crv", "x", "y", "kid", "use")}


def write_json(path: Path, payload: dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def did_host(did: str) -> str:
    return did.removeprefix("did:web:").split(":", 1)[0]


def write_participant_did(
    did_dir: Path,
    did: str,
    jwk: dict[str, str],
    dsp_endpoint: str | None,
    credential_endpoint: str | None,
    force: bool,
) -> Path:
    host = did_host(did)
    services: list[dict[str, str]] = []
    if dsp_endpoint:
        services.append({
            "id": f"{did}#dsp",
            "type": "DSPEndpoint",
            "serviceEndpoint": dsp_endpoint,
        })
    if credential_endpoint:
        services.append({
            "id": f"{did}#credential-service",
            "type": "CredentialService",
            "serviceEndpoint": credential_endpoint,
        })
    doc = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "id": did,
        "verificationMethod": [
            {
                "id": jwk["kid"],
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": public_jwk(jwk),
            }
        ],
        "authentication": [jwk["kid"]],
        "assertionMethod": [jwk["kid"]],
        "service": services,
    }
    path = did_dir / host / "did.json"
    write_json(path, doc, force)
    return path


def write_user_did(did_dir: Path, users_prefix: str, subject_id: str, portal_url: str, force: bool) -> Path:
    host = did_host(users_prefix)
    did = f"{users_prefix}:{subject_id}"
    path = did_dir / host / subject_id / "did.json"
    write_json(
        path,
        {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": did,
            "service": [
                {
                    "id": f"{did}#profile",
                    "type": "DataspaceUserProfile",
                    "serviceEndpoint": f"{portal_url.rstrip('/')}/my-data",
                }
            ],
        },
        force,
    )
    return path


def edc_properties(
    role: str,
    participant_did: str,
    trust_anchor_did: str,
    public_base: str,
    sts_secret_alias: str,
    vault_path: str,
    management_port: int,
    protocol_port: int,
    public_port: int,
    control_port: int,
    version_port: int,
    hostname: str,
    wallet_host: str,
    sts_host: str,
) -> str:
    return "\n".join([
        f"edc.participant.id={participant_did}",
        f"edc.iam.issuer.id={participant_did}",
        f"edc.dsp.callback.address={public_base}/protocol",
        "web.http.port=19191" if role == "provider" else "web.http.port=29191",
        "web.http.path=/api",
        f"web.http.management.port={management_port}",
        "web.http.management.path=/management",
        "web.http.management.auth.key=${EDC_API_KEY}",
        f"web.http.protocol.port={protocol_port}",
        "web.http.protocol.path=/protocol",
        f"web.http.public.port={public_port}",
        "web.http.public.path=/public",
        f"web.http.control.port={control_port}",
        "web.http.control.path=/control",
        f"web.http.version.port={version_port}",
        "web.http.version.path=/version",
        f"edc.hostname={hostname}",
        f"edc.dataplane.api.public.baseurl={public_base}/public",
        f"ds.edr.endpoint.public.baseurl={public_base}/public",
        "edc.transfer.proxy.token.signer.privatekey.alias=participant-private-key",
        "edc.transfer.proxy.token.verifier.publickey.alias=participant-private-key",
        "edc.receiver.http.endpoint=http://ds-connector:30001/webhooks/transfer-process",
        "edc.vault.hashicorp.enabled=false",
        f"edc.vault.fs.file={vault_path}",
        f"edc.iam.sts.oauth.token.url=http://{sts_host}:8080/token",
        f"edc.iam.sts.oauth.client.id={participant_did}",
        f"edc.iam.sts.oauth.client.secret.alias={sts_secret_alias}",
        f"edc.iam.trusted-issuer.0.id={trust_anchor_did}",
        "edc.iam.dcp.scopes.membership.id=membership",
        "edc.iam.dcp.scopes.membership.type=default",
        "edc.iam.dcp.scopes.membership.value=org.eclipse.dspace.dcp.vc.type:MembershipCredential:read",
        "edc.iam.dcp.scopes.membership.profile=*",
        f"edc.credential.service.url=http://{wallet_host}:8081/api/v1",
        "edc.iam.did.web.use.https=true",
        "ds.participants.yaml.path=/governance/participants.yaml",
        "ds.demo.identity.enabled=false",
        "",
    ])


def write_text(path: Path, value: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    env = read_env(args.env_example)
    public_domain = args.public_domain or env["PUBLIC_BASE_DOMAIN"]
    env["PUBLIC_BASE_DOMAIN"] = public_domain
    env["PROVIDER_DID_WEB"] = f"did:web:provider.{public_domain}"
    env["CONSUMER_DID_WEB"] = f"did:web:consumer.{public_domain}"
    env["TRUST_ANCHOR_DID_WEB"] = f"did:web:trust-anchor.{public_domain}"
    env["USERS_DID_WEB_PREFIX"] = f"did:web:users.{public_domain}"
    env["CONNECTOR_CREDENTIAL_STATUS_URL"] = f"https://trust-anchor.{public_domain}/credentials/status-list.json"
    env["VC_WALLET_CREDENTIAL_STATUS_URL"] = env["CONNECTOR_CREDENTIAL_STATUS_URL"]
    env["DATASPACE_ID"] = f"https://{public_domain}"
    env["AUTH_KEYCLOAK_ISSUER"] = f"https://keycloak.{public_domain}/realms/dataspaces"
    env["AUTH_KEYCLOAK_REDIRECT_URI"] = f"https://portal.{public_domain}/auth/callback/keycloak"
    env["ORIGIN"] = f"https://portal.{public_domain}"
    env["AUTH_URL"] = env["ORIGIN"]
    env["NEXTAUTH_URL"] = env["ORIGIN"]
    env["CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS"] = f"https://provider.{public_domain}/protocol/2025-1"
    env["CONSUMER_DEFAULT_ASSIGNER"] = env["PROVIDER_DID_WEB"]

    force = args.force
    created: list[str] = []

    for key in (
        "EDC_API_KEY_FILE",
        "STS_PROVIDER_SECRET_FILE",
        "STS_CONSUMER_SECRET_FILE",
        "AUTH_SECRET_FILE",
        "AUTH_KEYCLOAK_SECRET_FILE",
        "POSTGRES_PASSWORD_FILE",
        "GRAFANA_ADMIN_PASSWORD_FILE",
    ):
        path = ROOT / env[key]
        write_secret(path, secrets.token_urlsafe(32), force)
        created.append(str(path))

    keys = {
        "provider": generate_jwk(env["PROVIDER_DID_WEB"]),
        "consumer": generate_jwk(env["CONSUMER_DID_WEB"]),
        "trust-anchor": generate_jwk(env["TRUST_ANCHOR_DID_WEB"]),
    }
    for name, env_key in (
        ("provider", "PROVIDER_PRIVATE_KEY_FILE"),
        ("consumer", "CONSUMER_PRIVATE_KEY_FILE"),
        ("trust-anchor", "TRUST_ANCHOR_PRIVATE_KEY_FILE"),
    ):
        path = ROOT / env[env_key]
        write_json(path, keys[name], force)
        path.chmod(0o600)
        created.append(str(path))

    provider_secret = (ROOT / env["STS_PROVIDER_SECRET_FILE"]).read_text().strip()
    consumer_secret = (ROOT / env["STS_CONSUMER_SECRET_FILE"]).read_text().strip()
    write_text(
        ROOT / env["EDC_PROVIDER_VAULT_FILE"],
        f"sts-provider-client-secret={provider_secret}\nparticipant-private-key={json.dumps(keys['provider'], separators=(',', ':'))}\n",
        force,
    )
    write_text(
        ROOT / env["EDC_CONSUMER_VAULT_FILE"],
        f"sts-consumer-client-secret={consumer_secret}\nparticipant-private-key={json.dumps(keys['consumer'], separators=(',', ':'))}\n",
        force,
    )
    created.extend([str(ROOT / env["EDC_PROVIDER_VAULT_FILE"]), str(ROOT / env["EDC_CONSUMER_VAULT_FILE"])])

    write_text(
        ROOT / env["EDC_PROVIDER_CONFIG_FILE"],
        edc_properties(
            "provider",
            env["PROVIDER_DID_WEB"],
            env["TRUST_ANCHOR_DID_WEB"],
            f"https://provider.{public_domain}",
            "sts-provider-client-secret",
            "/run/secrets/edc_provider_vault",
            19193,
            19194,
            19291,
            19192,
            19195,
            "edc-provider",
            "vc-wallet-provider",
            "sts-provider",
        ),
        force,
    )
    write_text(
        ROOT / env["EDC_CONSUMER_CONFIG_FILE"],
        edc_properties(
            "consumer",
            env["CONSUMER_DID_WEB"],
            env["TRUST_ANCHOR_DID_WEB"],
            f"https://consumer.{public_domain}",
            "sts-consumer-client-secret",
            "/run/secrets/edc_consumer_vault",
            29193,
            29194,
            29291,
            29192,
            29195,
            "edc-consumer",
            "vc-wallet-consumer",
            "sts-consumer",
        ),
        force,
    )
    created.extend([str(ROOT / env["EDC_PROVIDER_CONFIG_FILE"]), str(ROOT / env["EDC_CONSUMER_CONFIG_FILE"])])

    did_dir = ROOT / env["DID_DOCUMENTS_DIR"]
    created.append(str(write_participant_did(
        did_dir,
        env["PROVIDER_DID_WEB"],
        keys["provider"],
        f"https://provider.{public_domain}/protocol/2025-1",
        "http://vc-wallet-provider:8081/api/v1",
        force,
    )))
    created.append(str(write_participant_did(
        did_dir,
        env["CONSUMER_DID_WEB"],
        keys["consumer"],
        f"https://consumer.{public_domain}/protocol/2025-1",
        "http://vc-wallet-consumer:8081/api/v1",
        force,
    )))
    created.append(str(write_participant_did(
        did_dir,
        env["TRUST_ANCHOR_DID_WEB"],
        keys["trust-anchor"],
        None,
        None,
        force,
    )))
    for subject_id in ("ah-00003", "test"):
        created.append(str(write_user_did(did_dir, env["USERS_DID_WEB_PREFIX"], subject_id, env["ORIGIN"], force)))

    if args.env_out.exists() and not force:
        raise SystemExit(f"{args.env_out} already exists. Re-run with --force to overwrite it.")
    env_lines = []
    example_lines = args.env_example.read_text().splitlines()
    for raw in example_lines:
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            env_lines.append(raw)
            continue
        key = raw.split("=", 1)[0].strip()
        env_lines.append(f"{key}={env.get(key, raw.split('=', 1)[1])}")
    args.env_out.write_text("\n".join(env_lines) + "\n")
    args.env_out.chmod(0o600)
    created.append(str(args.env_out))

    return {
        "env_file": str(args.env_out),
        "public_domain": public_domain,
        "created_or_verified": sorted(set(created)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-example", type=Path, default=DEFAULT_ENV_EXAMPLE)
    parser.add_argument("--env-out", type=Path, default=DEFAULT_ENV_OUT)
    parser.add_argument("--public-domain")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    result = bootstrap(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
