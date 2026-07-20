#!/usr/bin/env python3
"""Provision Keycloak organizations from organizations.yaml.

Creates KC native organizations, adds members, and assigns org-level groups.
Idempotent — safe to re-run.

Usage:
    python keycloak_org_sync.py \
        --config services/keycloak/organizations.yaml \
        --keycloak-url http://172.17.0.1:9080 \
        --admin-user admin --admin-password admin
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    # Fallback: scripts may run in minimal containers without PyYAML.
    # The YAML files used here are simple enough for a basic parser,
    # but we prefer PyYAML when available.
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("keycloak-org-sync")


def _load_yaml(path: Path) -> dict:
    text = path.read_text()
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback: use JSON if YAML is unavailable
    raise SystemExit(
        "PyYAML is required. Install it with: pip install pyyaml"
    )


class KeycloakAdmin:
    """Thin wrapper around the KC Admin REST API."""

    def __init__(self, base_url: str, realm: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.token = token

    @classmethod
    def authenticate(
        cls,
        base_url: str,
        realm: str,
        *,
        admin_user: str,
        admin_password: str,
    ) -> "KeycloakAdmin":
        url = f"{base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
        data = urllib.parse.urlencode({
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_password,
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req) as resp:
            token = json.loads(resp.read())["access_token"]
        return cls(base_url, realm, token)

    def _request(
        self,
        method: str,
        path: str,
        body: dict | list | None = None,
        *,
        expect_404: bool = False,
    ) -> dict | list | None:
        url = f"{self.base_url}/admin/realms/{self.realm}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
                if not content:
                    return None
                return json.loads(content)
        except urllib.error.HTTPError as e:
            if expect_404 and e.code == 404:
                return None
            if e.code == 409:
                return None
            raise

    # ── Users ────────────────────────────────────────────────────────────────

    def find_user_by_email(self, email: str) -> dict | None:
        users = self._request("GET", f"/users?email={urllib.parse.quote(email)}&exact=true")
        if isinstance(users, list) and users:
            return users[0]
        return None

    # ── Organizations ────────────────────────────────────────────────────────

    def get_organization_by_alias(self, alias: str) -> dict | None:
        # KC 26 search matches on name, not alias — list all and filter.
        orgs = self._request("GET", "/organizations")
        if isinstance(orgs, list):
            for org in orgs:
                if org.get("alias") == alias:
                    return org
        return None

    def create_organization(
        self,
        alias: str,
        name: str,
        domains: list[str] | None = None,
        attributes: dict[str, list[str]] | None = None,
    ) -> dict:
        existing = self.get_organization_by_alias(alias)
        if existing:
            log.info("Organization %s already exists (id=%s)", alias, existing["id"])
            return existing

        body: dict = {
            "name": name,
            "alias": alias,
            "enabled": True,
        }
        if domains:
            body["domains"] = [{"name": d, "verified": False} for d in domains]
        if attributes:
            body["attributes"] = attributes

        self._request("POST", "/organizations", body)
        created = self.get_organization_by_alias(alias)
        if not created:
            raise RuntimeError(f"Failed to create organization {alias}")
        log.info("Created organization %s (id=%s)", alias, created["id"])
        return created

    def get_org_members(self, org_id: str) -> list[dict]:
        members = self._request("GET", f"/organizations/{org_id}/members")
        return members if isinstance(members, list) else []

    def add_org_member(self, org_id: str, user_id: str) -> None:
        members = self.get_org_members(org_id)
        if any(m.get("id") == user_id for m in members):
            return
        # KC 26 expects the raw user UUID as the request body, not JSON.
        url = f"{self.base_url}/admin/realms/{self.realm}/organizations/{org_id}/members"
        req = urllib.request.Request(url, data=user_id.encode(), method="POST")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req)

    # ── Organization groups ─────────────────────────────────────────────────

    def get_org_groups(self, org_id: str) -> list[dict]:
        groups = self._request("GET", f"/organizations/{org_id}/groups", expect_404=True)
        return groups if isinstance(groups, list) else []

    def ensure_org_group(self, org_id: str, group_name: str) -> dict:
        for g in self.get_org_groups(org_id):
            if g.get("name") == group_name:
                return g
        self._request("POST", f"/organizations/{org_id}/groups", {"name": group_name})
        for g in self.get_org_groups(org_id):
            if g.get("name") == group_name:
                return g
        raise RuntimeError(f"Failed to create org group {group_name}")

    def ensure_user_in_org_group(self, org_id: str, group_id: str, user_id: str) -> None:
        self._request(
            "PUT",
            f"/organizations/{org_id}/groups/{group_id}/members/{user_id}",
            expect_404=True,
        )


def sync_organizations(config_path: Path, kc: KeycloakAdmin) -> None:
    config = _load_yaml(config_path)
    organizations = config.get("organizations", [])

    for org_def in organizations:
        alias = org_def["alias"]
        name = org_def.get("name", alias)
        domains = org_def.get("domains", [])
        attributes = org_def.get("attributes")

        org = kc.create_organization(alias, name, domains, attributes)
        org_id = org["id"]

        for member_def in org_def.get("members", []):
            email = member_def["email"]
            user = kc.find_user_by_email(email)
            if not user:
                log.warning("User %s not found in KC, skipping", email)
                continue

            user_id = user["id"]
            kc.add_org_member(org_id, user_id)
            log.info("Added %s to organization %s", email, alias)

            for group_name in member_def.get("groups", []):
                group = kc.ensure_org_group(org_id, group_name)
                kc.ensure_user_in_org_group(org_id, group["id"], user_id)
                log.info("Assigned group %s to user %s in org %s", group_name, user_id, org_id)

    log.info("Organization sync complete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to organizations.yaml",
    )
    parser.add_argument(
        "--keycloak-url",
        default="http://172.17.0.1:9080",
        help="Keycloak base URL",
    )
    parser.add_argument("--realm", default="dataspaces")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="admin")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    if not args.config.exists():
        log.error("Config file not found: %s", args.config)
        return 1

    kc = KeycloakAdmin.authenticate(
        args.keycloak_url,
        args.realm,
        admin_user=args.admin_user,
        admin_password=args.admin_password,
    )
    sync_organizations(args.config, kc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
