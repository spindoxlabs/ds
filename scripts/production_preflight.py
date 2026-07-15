#!/usr/bin/env python3
"""Production profile preflight checks for DSSC milestone 9."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INSECURE_MARKERS = ("insecure-", "change-me", "dev-secret", "postgres:postgres")
NON_PRODUCTION_MARKERS = ("localhost", ".localhost", ".test")
REQUIRED_ENV = (
    "AUTH_SECRET_FILE",
    "EDC_API_KEY_FILE",
    "STS_PROVIDER_SECRET_FILE",
    "STS_CONSUMER_SECRET_FILE",
    "POSTGRES_PASSWORD_FILE",
    "EDC_PROVIDER_CONFIG_FILE",
    "EDC_CONSUMER_CONFIG_FILE",
    "EDC_PROVIDER_VAULT_FILE",
    "EDC_CONSUMER_VAULT_FILE",
    "PROVIDER_PRIVATE_KEY_FILE",
    "CONSUMER_PRIVATE_KEY_FILE",
    "TRUST_ANCHOR_PRIVATE_KEY_FILE",
    "CREDENTIALS_DIR",
    "CREDENTIAL_STATUS_LIST_FILE",
    "PRODUCTION_CADDYFILE",
    "DID_DOCUMENTS_DIR",
    "AUTH_KEYCLOAK_ISSUER",
    "AUTH_KEYCLOAK_ID",
    "AUTH_KEYCLOAK_SECRET_FILE",
    "AUTH_KEYCLOAK_REDIRECT_URI",
    "KEYCLOAK_REALM_EXPORT",
    "CONNECTOR_CREDENTIAL_STATUS_URL",
    "VC_WALLET_CREDENTIAL_STATUS_URL",
    "PROVIDER_DID_WEB",
    "CONSUMER_DID_WEB",
    "TRUST_ANCHOR_DID_WEB",
    "USERS_DID_WEB_PREFIX",
)
HTTPS_ENV = (
    "AUTH_KEYCLOAK_ISSUER",
    "CONNECTOR_CREDENTIAL_STATUS_URL",
    "VC_WALLET_CREDENTIAL_STATUS_URL",
    "AUTH_KEYCLOAK_REDIRECT_URI",
    "ORIGIN",
    "AUTH_URL",
    "NEXTAUTH_URL",
    "CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS",
)
PUBLIC_ENV = (
    "PUBLIC_BASE_DOMAIN",
    "PROVIDER_DID_WEB",
    "CONSUMER_DID_WEB",
    "TRUST_ANCHOR_DID_WEB",
    "USERS_DID_WEB_PREFIX",
    "CONNECTOR_CREDENTIAL_STATUS_URL",
    "VC_WALLET_CREDENTIAL_STATUS_URL",
    "DATASPACE_ID",
    "AUTH_KEYCLOAK_ISSUER",
    "AUTH_KEYCLOAK_REDIRECT_URI",
    "ORIGIN",
    "AUTH_URL",
    "NEXTAUTH_URL",
    "CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS",
    "CONSUMER_DEFAULT_ASSIGNER",
)
ALLOWED_KEYCLOAK_SCOPES = {
    "openid",
    "profile",
    "email",
    "roles",
    "groups",
    "organization",
    "dataset.query",
    "dataset.read",
}
REQUIRED_COMPOSE_MARKERS = (
    "EDC_PROVIDER_CONFIG_FILE",
    "EDC_CONSUMER_CONFIG_FILE",
    "EDC_PROVIDER_VAULT_FILE",
    "EDC_CONSUMER_VAULT_FILE",
    "PROVIDER_PRIVATE_KEY_FILE",
    "CONSUMER_PRIVATE_KEY_FILE",
    "TRUST_ANCHOR_PRIVATE_KEY_FILE",
    "CREDENTIALS_DIR",
    "PRODUCTION_CADDYFILE",
    "DID_DOCUMENTS_DIR",
    "CONNECTOR_TRUST_ANCHOR_KEY_PATH: /run/secrets/trust_anchor_private_key",
    "STS_PRIVATE_KEY_PATH: /run/secrets/provider_private_key",
    "STS_PRIVATE_KEY_PATH: /run/secrets/consumer_private_key",
    "VC_WALLET_PRIVATE_KEY_PATH: /run/secrets/provider_private_key",
    "VC_WALLET_PRIVATE_KEY_PATH: /run/secrets/consumer_private_key",
)


@dataclass
class Finding:
    check: str
    message: str

    def asdict(self) -> dict[str, str]:
        return {"check": self.check, "message": self.message}


@dataclass
class PreflightResult:
    env_file: str
    compose_file: str
    passed: bool = True
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)

    def error(self, check: str, message: str) -> None:
        self.passed = False
        self.errors.append(Finding(check, message))

    def warning(self, check: str, message: str) -> None:
        self.warnings.append(Finding(check, message))

    def asdict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "env_file": self.env_file,
            "compose_file": self.compose_file,
            "errors": [item.asdict() for item in self.errors],
            "warnings": [item.asdict() for item in self.warnings],
        }


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def validate(env_file: Path, compose_file: Path) -> PreflightResult:
    result = PreflightResult(str(env_file), str(compose_file))
    env = _read_env(env_file)
    if not env_file.exists():
        result.error("env-file", f"Missing production env example/file: {env_file}")
        return result
    if not compose_file.exists():
        result.error("compose-file", f"Missing production compose override: {compose_file}")
        return result

    for key in REQUIRED_ENV:
        if not env.get(key):
            result.error("required-env", f"Missing {key}")
    for key, value in env.items():
        lowered = value.lower()
        if any(marker in lowered for marker in INSECURE_MARKERS):
            result.error("insecure-default", f"{key} contains development placeholder value")
    for key in HTTPS_ENV:
        value = env.get(key, "")
        if value and not value.startswith("https://"):
            result.error("https-required", f"{key} must use https:// in production")
    for key in PUBLIC_ENV:
        value = env.get(key, "")
        lowered = value.lower()
        if value and any(marker in lowered for marker in NON_PRODUCTION_MARKERS):
            result.error("production-domain", f"{key} contains a local/demo marker: {value}")
    redirect_uri = env.get("AUTH_KEYCLOAK_REDIRECT_URI", "")
    if "*" in redirect_uri:
        result.error("keycloak-redirect", "AUTH_KEYCLOAK_REDIRECT_URI must be exact and cannot contain wildcards")
    scopes = set(env.get("AUTH_KEYCLOAK_SCOPE", "").split())
    excessive_scopes = sorted(scopes - ALLOWED_KEYCLOAK_SCOPES)
    if excessive_scopes:
        result.error("keycloak-scope", f"AUTH_KEYCLOAK_SCOPE contains excessive scopes: {', '.join(excessive_scopes)}")

    compose = compose_file.read_text()
    if "!override []" not in compose:
        result.warning("management-api-exposure", "Compose override does not explicitly remove inherited management ports")
    if "secrets:" not in compose:
        result.error("docker-secrets", "Production compose does not declare Docker secrets")
    for marker in ("EDC_API_KEY_FILE", "STS_PROVIDER_SECRET_FILE", "STS_CONSUMER_SECRET_FILE"):
        if marker not in compose:
            result.error("docker-secrets", f"Production compose does not wire {marker}")
    for marker in REQUIRED_COMPOSE_MARKERS:
        if marker not in compose:
            result.error("production-key-material", f"Production compose does not wire {marker}")
    for service in (
        "postgres",
        "identity-registry",
        "edc-provider",
        "edc-consumer",
        "ds-connector",
        "dataset-api",
        "ds-provenance",
        "ds-federated-catalog",
    ):
        if f"  {service}:" in compose and f"  {service}:\n    ports: !override []" not in compose:
            result.error("public-port-exposure", f"{service} must remove inherited public ports in production")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.production.example")
    parser.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.production.yml")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    result = validate(args.env_file, args.compose_file)
    if args.format == "json":
        print(json.dumps(result.asdict(), indent=2, sort_keys=True))
    else:
        print(f"Production preflight: {'PASS' if result.passed else 'FAIL'}")
        for item in result.errors:
            print(f"- FAIL [{item.check}] {item.message}")
        for item in result.warnings:
            print(f"- WARN [{item.check}] {item.message}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
