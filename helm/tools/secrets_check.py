"""Preflight over a decrypted helm secrets file — `task secrets:check FILE=<it>`.

Run on the operator's machine before an apply (`every-secret-has-one-source`,
M5 / P4), on the file the deployment decrypts from its own sops setup. It checks
what no single pod can see and what the render policy cannot know:

* placeholders and the known dev defaults, any spelling, at any depth — the
  committed dev cookie secret and EDR fixture keys included, read from the files
  that commit them;
* a client secret equal to its client id, with the key → client mapping derived
  from `services/keycloak/clients*.yaml` (`secret: ${VAR:-<client id>}`), so a
  client added there is covered without editing this;
* a custody key shared between two holders (the anchor's and every
  participant's encryption key, every two participants' control keys);
* every participant's EDR key halves agreeing: the public JWK is the private one
  without its private members (chart parity OQ1, option b).

**It never prints a value** — a finding names the key path, and for a client
secret the client id it equals (which is public). Exit 1 on any finding.

    python helm/tools/secrets_check.py secrets.dec.yaml [--repo <ds checkout>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

WEAK = {"changeme", "admin", "password", "postgres", "secret", "test"}
DEV_LITERALS = {
    "insecure-dev-secret",
    "insecure-dev-callback-key",
    "insecure-dev-control-key",
    "insecure-dev-key",
    "dev-encryption-key-change-in-production",
    "ds-local-dev-secret",
    "dev-secret-change-in-prod",
    "change-me-local-client-secret",
}
PRIVATE_MEMBERS = {"d", "p", "q", "dp", "dq", "qi"}
CUSTODY_PER_PARTICIPANT = ("identityRegistryEncryptionKey", "edcControlApiKey")


def weak_form(value: str) -> str:
    return value.strip().lower().replace("_", "").replace("-", "")


def leaves(node, prefix):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from leaves(v, f"{prefix}.{k}")
    else:
        yield prefix, node


def camel_to_env(key: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).upper()


def client_defaults(repo: Path) -> dict[str, str]:
    """`SVC_…_SECRET` → its dev default (the client id), from every realm file."""
    found: dict[str, str] = {}
    for f in sorted((repo / "services/keycloak").glob("clients*.yaml")):
        for var, default in re.findall(r"\$\{([A-Z0-9_]+):-([^}]+)\}", f.read_text()):
            found[var] = default
    # Declared by the realm import rather than the syncer, so not in the files.
    found.setdefault("OAUTH2_PROXY_CLIENT_SECRET", "oauth2_proxy")
    return found


def dev_cookie_secrets(repo: Path) -> set[str]:
    compose = repo / "docker-compose.yml"
    if not compose.is_file():
        return set()
    return set(
        re.findall(
            r"OAUTH2_PROXY_COOKIE_SECRET:\s*\$\{OAUTH2_PROXY_COOKIE_SECRET:-([^}]+)\}",
            compose.read_text(),
        )
    )


def fixture_xs(repo: Path) -> set[str]:
    xs = set()
    for f in (repo / "services/connector/config").glob("*-vault.properties"):
        xs.update(re.findall(r'"x":"([^"]+)"', f.read_text()))
    return xs


def parse_jwk(raw) -> dict | None:
    try:
        jwk = json.loads(str(raw))
    except ValueError:
        return None
    return jwk if isinstance(jwk, dict) else None


def check(doc: dict, repo: Path) -> list[str]:
    findings: list[str] = []
    sec = doc.get("secrets", doc)
    if not isinstance(sec, dict):
        return ["the file has no `secrets:` mapping"]

    # placeholders and dev literals
    cookies = dev_cookie_secrets(repo)
    for path, value in leaves(sec, "secrets"):
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        form = weak_form(text)
        if (
            form in WEAK
            or "changeme" in form
            or text in DEV_LITERALS
            or text.lower().startswith("dev-")
            or text in cookies
        ):
            findings.append(f"{path}: a placeholder or a committed dev default")

    # client secrets equal to their client id
    defaults = client_defaults(repo)
    for key, value in sec.items():
        if isinstance(value, str) and value.strip():
            dev = defaults.get(camel_to_env(key))
            if dev and value.strip() == dev:
                findings.append(
                    f"secrets.{key}: equals the client id {dev!r}, the dev default"
                )
    for name, p in (sec.get("participants") or {}).items():
        if not isinstance(p, dict):
            continue
        for key, client in (
            ("organisationClientSecret", f"svc-ds-connector-{name}"),
            ("connectorClientSecret", "svc-edc"),
        ):
            if str(p.get(key, "")).strip() == client:
                findings.append(
                    f"secrets.participants.{name}.{key}: equals the client id {client!r}, the dev default"
                )
    for alias, c in (sec.get("organisationClients") or {}).items():
        for key, client in (
            ("connectorSecret", f"svc-ds-connector-{alias}"),
            ("collectorSecret", f"svc-ds-collector-{alias}"),
        ):
            if isinstance(c, dict) and str(c.get(key, "")).strip() == client:
                findings.append(
                    f"secrets.organisationClients.{alias}.{key}: equals the client id {client!r}, the dev default"
                )

    # custody keys
    participants = {
        n: p for n, p in (sec.get("participants") or {}).items() if isinstance(p, dict)
    }
    anchor = str(sec.get("identityRegistryEncryptionKey", "")).strip()
    if "changeme" in weak_form(anchor):
        anchor = (
            ""  # already a placeholder finding; equal placeholders say nothing more
        )
    names = sorted(participants)
    for i, a in enumerate(names):
        if (
            anchor
            and str(participants[a].get("identityRegistryEncryptionKey", "")).strip()
            == anchor
        ):
            findings.append(
                f"secrets.participants.{a}.identityRegistryEncryptionKey: equals the anchor's — one key per release"
            )
        for b in names[i + 1 :]:
            for key in CUSTODY_PER_PARTICIPANT:
                va = str(participants[a].get(key, "")).strip()
                if (
                    va
                    and va == str(participants[b].get(key, "")).strip()
                    and "changeme" not in weak_form(va)
                ):
                    findings.append(
                        f"secrets.participants.{a}.{key} and secrets.participants.{b}.{key}: the same value — a custody key is never shared"
                    )

    # svc-edc: one realm client, one secret
    edc = {
        str(p.get("connectorClientSecret", "")).strip() for p in participants.values()
    } - {""}
    if str(sec.get("svcEdcSecret", "")).strip():
        edc.add(str(sec["svcEdcSecret"]).strip())
    if len(edc) > 1:
        findings.append(
            "secrets.svcEdcSecret / secrets.participants.*.connectorClientSecret: differ — every EDC logs in as the one client svc-edc"
        )

    # EDR halves and fixtures
    xs = fixture_xs(repo)
    for name, p in participants.items():
        vault = p.get("edcVault") or {}
        private = parse_jwk(vault.get("edrSigningPrivateJwk", ""))
        if private and private.get("x") in xs:
            findings.append(
                f"secrets.participants.{name}.edcVault.edrSigningPrivateJwk: a committed dev fixture key — its private half is public"
            )
        raw_public = vault.get("edrSigningPublicJwk")
        if raw_public is None:
            continue
        public = parse_jwk(raw_public)
        if public is None or private is None:
            findings.append(
                f"secrets.participants.{name}.edcVault: an EDR key half is not a JSON object"
            )
            continue
        if PRIVATE_MEMBERS & public.keys():
            findings.append(
                f"secrets.participants.{name}.edcVault.edrSigningPublicJwk: carries a private member"
            )
        if any(public.get(c) != private.get(c) for c in ("kty", "crv", "x", "y")):
            findings.append(
                f"secrets.participants.{name}.edcVault.edrSigningPublicJwk: not the public half of edrSigningPrivateJwk"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args(argv)
    try:
        doc = yaml.safe_load(args.file.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"✗ {args.file}: cannot read it as YAML ({type(exc).__name__})")
        return 1
    if "sops" in doc:
        print(
            f"✗ {args.file} is encrypted — decrypt it (sops -d) to a gitignored file and check that; nothing was checked"
        )
        return 1
    findings = check(doc, args.repo)
    for f in findings:
        print(f"✗ {f}")
    if findings:
        print(f"{len(findings)} finding(s) in {args.file}; no value is printed")
        return 1
    print(
        f"✓ {args.file}: no placeholder, no dev default, no client secret equal to its id, no shared custody key; EDR halves agree"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
