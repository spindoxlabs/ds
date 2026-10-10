"""Generate a complete secrets file for a local or rehearsal deployment.

    uv run --no-project --with pyyaml --with cryptography python \
        helm/tools/generate_secrets.py --values <values file> --out <secrets file> \
        [--collector <organisation alias>]... [--force]

Used by the minikube setup (`task helm:minikube:secrets`, docs/deployment/local-cluster.md)
and by a deployment rehearsing on one. **Not** for a shared environment: there the secrets
are chosen, encrypted and backed up by the operator (docs/deployment/secrets.md). The
output must stay out of version control. An existing file is left alone unless
``--force`` is given: regenerating it under a running system changes every secret.

Shape: every key of ``helm/secrets.example.yaml`` for the participants the values file
enables (a ``.gotmpl`` values file is read as YAML; its template expressions must sit in
quoted strings). Real material where a service parses it:
Fernet keys for the registries' encryption keys and the connector's at-rest keys, an
EC P-256 key pair for each EDC's EDR signing key (the public half kept beside it, as
the render policy requires). Every other value is 32 random bytes, hex. ``svc-edc``'s
secret is the same for every participant and ``svcEdcSecret``: one realm client.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from pathlib import Path

import yaml
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec



def token() -> str:
    return secrets.token_hex(32)


def fernet() -> str:
    return Fernet.generate_key().decode()


def edr_pair(kid: str) -> tuple[str, str]:
    def b64(n: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()

    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_numbers()
    private = {
        "kty": "EC",
        "crv": "P-256",
        "kid": kid,
        "x": b64(pub.x),
        "y": b64(pub.y),
        "d": b64(key.private_numbers().private_value),
    }
    public = {k: v for k, v in private.items() if k != "d"}
    return json.dumps(private), json.dumps(public)


def build(values: dict, collectors: list[str]) -> dict:
    svc_edc = token()
    postgres = {"identity_registry": token()}
    participants: dict[str, dict] = {}
    org_clients: dict[str, dict] = {}
    for p in values.get("participants") or []:
        if not p.get("enabled"):
            continue
        name = p["name"]
        db = name.replace("-", "_")
        for prefix in ("identity_registry", "connector", "provenance", "edc"):
            postgres[f"{prefix}_{db}"] = token()
        private, public = edr_pair(f"{name}-edr-1")
        participants[name] = {
            "organisationClientSecret": token(),
            "edcCallbackKey": token(),
            "connectorAtRestKeys": fernet(),
            "connectorKeyIndexSecret": token(),
            "provenanceSubjectPseudonymKey": token(),
            "edcControlApiKey": token(),
            "connectorClientSecret": svc_edc,
            "edcVault": {
                "edrSigningPrivateJwk": private,
                "edrSigningPublicJwk": public,
            },
            "stsSecret": token(),
            "identityRegistryEncryptionKey": fernet(),
        }
    # Posture B: the collector client's secret is a realm value and onboarding's, not a
    # chart value. Kept here, outside `secrets:`, so the realm sync has one source.
    for alias in collectors:
        org_clients[alias] = {"collectorSecret": token()}
    return {
        "secrets": {
            "identityRegistryEncryptionKey": fernet(),
            "oauth2ProxyCookieSecret": secrets.token_urlsafe(24)[:32],
            "svcDsIdentityRegistrySecret": token(),
            "svcDsOnboardingSecret": token(),
            "svcDsPortalSecret": token(),
            "svcDsConnectorSecret": token(),
            "svcDsFederatedCatalogSecret": token(),
            "svcDsDatasetApiSecret": token(),
            "svcEdcSecret": svc_edc,
            "oauth2ProxyClientSecret": token(),
            "keycloakAdminUsername": "",
            "keycloakAdminPassword": "",
            "organisationClients": {},
            "postgres": postgres,
            "participants": participants,
        },
        # Realm-only secrets, read by the realm sync and by nothing the charts render:
        # posture B's collector clients (ADR-0026) and the clients ds declares that no
        # chart reads here (no `sync.clientId`), given real values so the realm holds no
        # client whose secret is its id.
        "realmOnly": {
            "collectorClients": org_clients,
            "publisherSecret": token(),
            "provenanceSecret": token(),
            # The admin of a bundled local realm (helm/minikube); unused elsewhere.
            "keycloakAdminPassword": token(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--values", required=True, type=Path, help="the deployment's values file")
    parser.add_argument("--out", required=True, type=Path, help="the secrets file to write")
    parser.add_argument("--collector", action="append", default=[], help="an organisation alias that collects consent (ADR-0026); repeatable")
    parser.add_argument("--force", action="store_true", help="overwrite an existing file")
    args = parser.parse_args()
    if args.out.exists() and not args.force:
        print(f"{args.out} exists; left alone (--force replaces every secret)")
        return 0
    values = yaml.safe_load(args.values.read_text())
    args.out.write_text(
        "# Generated by helm/tools/generate_secrets.py. Never commit.\n"
        + yaml.safe_dump(build(values, args.collector), sort_keys=False)
    )
    args.out.chmod(0o600)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
