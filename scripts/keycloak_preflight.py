#!/usr/bin/env python3
"""Validate a production Keycloak realm export for the dataspace portal."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NON_PRODUCTION_MARKERS = ("localhost", ".localhost", ".test")
REQUIRED_CLIENT_ROLES = {"admin", "dataset.admin"}
REQUIRED_REALM_ROLES = {"ds-admin", "dataset.admin"}
REQUIRED_CLIENT_SCOPES = {"profile", "email", "roles", "groups", "organization", "dataset.query", "dataset.read"}
DISALLOWED_CLIENT_SCOPES = {"offline_access", "microprofile-jwt"}


@dataclass
class Finding:
    check: str
    message: str

    def asdict(self) -> dict[str, str]:
        return {"check": self.check, "message": self.message}


@dataclass
class KeycloakPreflightResult:
    realm_export: str
    passed: bool = True
    errors: list[Finding] = field(default_factory=list)

    def error(self, check: str, message: str) -> None:
        self.passed = False
        self.errors.append(Finding(check, message))

    def asdict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "realm_export": self.realm_export,
            "errors": [item.asdict() for item in self.errors],
        }


def _read_env(path: Path | None) -> dict[str, str]:
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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _client_roles(realm: dict[str, Any], client_id: str) -> set[str]:
    roles = ((realm.get("roles") or {}).get("client") or {}).get(client_id) or []
    return {str(role.get("name")) for role in roles if isinstance(role, dict)}


def _realm_roles(realm: dict[str, Any]) -> set[str]:
    roles = ((realm.get("roles") or {}).get("realm") or [])
    return {str(role.get("name")) for role in roles if isinstance(role, dict)}


def _client_scopes(realm: dict[str, Any], client: dict[str, Any]) -> set[str]:
    scopes = set(str(scope) for scope in client.get("defaultClientScopes") or [])
    scope_defs = {
        str(scope.get("name"))
        for scope in realm.get("clientScopes") or []
        if isinstance(scope, dict) and scope.get("name")
    }
    return scopes | (REQUIRED_CLIENT_SCOPES & scope_defs)


def _contains_non_production_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in NON_PRODUCTION_MARKERS)


def _find_client(realm: dict[str, Any], client_id: str) -> dict[str, Any] | None:
    for client in realm.get("clients") or []:
        if isinstance(client, dict) and client.get("clientId") == client_id:
            return client
    return None


def validate(realm_export: Path, env_file: Path | None = None) -> KeycloakPreflightResult:
    result = KeycloakPreflightResult(str(realm_export))
    if not realm_export.exists():
        result.error("realm-export", f"Missing Keycloak realm export: {realm_export}")
        return result

    env = _read_env(env_file)
    expected_client_id = env.get("AUTH_KEYCLOAK_ID", "ds-portal-production")
    expected_redirect_uri = env.get("AUTH_KEYCLOAK_REDIRECT_URI")
    expected_origin = env.get("ORIGIN") or env.get("AUTH_URL")
    expected_issuer = env.get("AUTH_KEYCLOAK_ISSUER", "")

    try:
        realm = _load_json(realm_export)
    except json.JSONDecodeError as exc:
        result.error("realm-export", f"Invalid JSON: {exc}")
        return result

    if not realm.get("enabled", True):
        result.error("realm-enabled", "Production realm must be enabled")
    if realm.get("realm") in {"master", None, ""}:
        result.error("realm-name", "Production realm must not be master/empty")
    if expected_issuer and expected_issuer.rstrip("/").split("/")[-1] != realm.get("realm"):
        result.error("realm-name", "AUTH_KEYCLOAK_ISSUER realm does not match export realm")
    if not realm.get("eventsEnabled"):
        result.error("audit-log", "eventsEnabled must be true")
    if not realm.get("adminEventsEnabled"):
        result.error("audit-log", "adminEventsEnabled must be true")
    if not realm.get("adminEventsDetailsEnabled"):
        result.error("audit-log", "adminEventsDetailsEnabled must be true")

    client = _find_client(realm, expected_client_id)
    if not client:
        result.error("client", f"Missing client {expected_client_id}")
        return result
    if not client.get("enabled", True):
        result.error("client", f"Client {expected_client_id} must be enabled")
    if client.get("publicClient"):
        result.error("client", f"Client {expected_client_id} must be confidential, not public")
    if not client.get("standardFlowEnabled", True):
        result.error("client-flow", "standardFlowEnabled must be true for Auth.js OIDC login")
    if client.get("directAccessGrantsEnabled"):
        result.error("client-flow", "directAccessGrantsEnabled must be false in production")
    if client.get("serviceAccountsEnabled"):
        result.error("client-flow", "serviceAccountsEnabled must be false for portal user login")
    if client.get("secret"):
        result.error("client-secret", "Realm export must not contain a literal client secret")

    redirect_uris = [str(uri) for uri in client.get("redirectUris") or []]
    if expected_redirect_uri and redirect_uris != [expected_redirect_uri]:
        result.error("redirect-uri", "Client redirectUris must contain exactly AUTH_KEYCLOAK_REDIRECT_URI")
    for uri in redirect_uris:
        if "*" in uri:
            result.error("redirect-uri", f"Wildcard redirect URI is not allowed: {uri}")
        if not uri.startswith("https://") or _contains_non_production_marker(uri):
            result.error("redirect-uri", f"Redirect URI must be production HTTPS: {uri}")

    web_origins = [str(origin) for origin in client.get("webOrigins") or []]
    if expected_origin and web_origins != [expected_origin]:
        result.error("web-origin", "Client webOrigins must contain exactly ORIGIN/AUTH_URL")
    for origin in web_origins:
        if origin == "+" or "*" in origin:
            result.error("web-origin", f"Wildcard web origin is not allowed: {origin}")
        if not origin.startswith("https://") or _contains_non_production_marker(origin):
            result.error("web-origin", f"Web origin must be production HTTPS: {origin}")

    client_roles = _client_roles(realm, expected_client_id)
    missing_client_roles = sorted(REQUIRED_CLIENT_ROLES - client_roles)
    if missing_client_roles:
        result.error("roles", f"Missing client roles: {', '.join(missing_client_roles)}")

    realm_roles = _realm_roles(realm)
    missing_realm_roles = sorted(REQUIRED_REALM_ROLES - realm_roles)
    if missing_realm_roles:
        result.error("roles", f"Missing realm roles: {', '.join(missing_realm_roles)}")

    scopes = _client_scopes(realm, client)
    missing_scopes = sorted(REQUIRED_CLIENT_SCOPES - scopes)
    if missing_scopes:
        result.error("client-scopes", f"Missing required client scopes: {', '.join(missing_scopes)}")
    excessive_scopes = sorted((set(client.get("defaultClientScopes") or []) | set(client.get("optionalClientScopes") or [])) & DISALLOWED_CLIENT_SCOPES)
    if excessive_scopes:
        result.error("client-scopes", f"Disallowed production scopes configured: {', '.join(excessive_scopes)}")

    groups = {str(group.get("name")) for group in realm.get("groups") or [] if isinstance(group, dict)}
    for group in ("dataspace-admins", "dataset-admins", "consumer-users", "data-subjects"):
        if group not in groups:
            result.error("groups", f"Missing group {group}")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm-export", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    result = validate(args.realm_export, args.env_file)
    if args.format == "json":
        print(json.dumps(result.asdict(), indent=2, sort_keys=True))
    else:
        print(f"Keycloak preflight: {'PASS' if result.passed else 'FAIL'}")
        for error in result.errors:
            print(f"- FAIL [{error.check}] {error.message}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
