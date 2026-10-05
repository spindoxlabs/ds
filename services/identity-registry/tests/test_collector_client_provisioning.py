"""`org-sync` provisions a collector client for an organisation declared to collect.

ADR-0026: `svc-ds-collector-<alias>`, `sub` = the organisation's DID, no default
scope, no client-level audience, no EDC scope, the organisation's acts optional;
disabled (never deleted) once the organisation stops declaring the flag.
"""

from __future__ import annotations

import json

import httpx
import pytest
from ds_auth import (
    COLLECTOR_CLIENT_OPTIONAL_SCOPES,
    is_management_api_scope,
)
from test_keycloak_admin import REALM, FakeKeycloak, _sub_values, make_client

from identity_registry.services.keycloak_admin import (
    OrganizationsConfig,
    secret_env_name,
    sync_organizations,
)

REC_DID = "did:web:rec.example.org"
COLLECTOR = "svc-ds-collector-example-rec"


class FakeKeycloakWithClientUpdates(FakeKeycloak):
    """The base fake plus `PUT /clients/{id}` and the collector's scopes."""

    def __init__(self):
        super().__init__()
        self.realm_scopes |= set(COLLECTOR_CLIENT_OPTIONAL_SCOPES)

    def handler(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split(f"/admin/realms/{REALM}/", 1)[-1].split("/")
        if request.method == "PUT" and len(parts) == 2 and parts[0] == "clients":
            client = next(c for c in self.clients.values() if c["id"] == parts[1])
            client["enabled"] = json.loads(request.content).get("enabled", True)
            self.requests.append(("PUT", request.url.path))
            return httpx.Response(204)
        if request.method == "GET" and parts == ["clients"]:
            found = self.clients.get(request.url.params.get("clientId"))
            self.requests.append(("GET", request.url.path))
            return httpx.Response(
                200,
                json=(
                    [{"id": found["id"], "enabled": found.get("enabled", True)}]
                    if found
                    else []
                ),
            )
        return super().handler(request)


def _config(collects: bool) -> OrganizationsConfig:
    return OrganizationsConfig.model_validate(
        {
            "realm": REALM,
            "organizations": [
                {
                    "alias": "example-rec",
                    "participant_context_id": REC_DID,
                    "collects_consent": collects,
                },
                {
                    "alias": "example-dso",
                    "participant_context_id": "did:web:dso.example.org",
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_a_collecting_organisation_gets_its_collector_client():
    fake = FakeKeycloakWithClientUpdates()
    kc = await make_client(fake)
    report = await sync_organizations(_config(True), kc, environ={}, production=False)

    assert report.collector_clients_ensured == [COLLECTOR]
    assert "svc-ds-collector-example-dso" not in fake.clients
    client = fake.clients[COLLECTOR]
    assert client["secret"] == COLLECTOR
    assert client["scopes"] == set()
    assert client["optional"] == set(COLLECTOR_CLIENT_OPTIONAL_SCOPES)
    assert not any(is_management_api_scope(s) for s in client["optional"])
    assert "edc.management" not in client["optional"]
    assert _sub_values(client) == [REC_DID]
    assert not [
        m for m in client["mappers"] if m["protocolMapper"] == "oidc-audience-mapper"
    ]
    assert client["body"]["standardFlowEnabled"] is False
    assert not report.has_warnings
    await kc.aclose()


@pytest.mark.asyncio
async def test_turning_the_flag_off_disables_the_collector_client():
    fake = FakeKeycloakWithClientUpdates()
    kc = await make_client(fake)
    await sync_organizations(_config(True), kc, environ={}, production=False)
    report = await sync_organizations(_config(False), kc, environ={}, production=False)

    assert report.collector_clients_disabled == [COLLECTOR]
    assert fake.clients[COLLECTOR]["enabled"] is False
    # And back on: enabled again, not recreated.
    report = await sync_organizations(_config(True), kc, environ={}, production=False)
    assert fake.clients[COLLECTOR]["enabled"] is True
    assert report.collector_clients_ensured == [COLLECTOR]
    await kc.aclose()


@pytest.mark.asyncio
async def test_production_needs_the_collectors_own_secret():
    fake = FakeKeycloakWithClientUpdates()
    kc = await make_client(fake)
    env = {
        secret_env_name("svc-ds-connector-example-rec"): "conn-secret",
        secret_env_name("svc-ds-connector-example-dso"): "dso-secret",
    }
    report = await sync_organizations(_config(True), kc, environ=env, production=True)
    assert COLLECTOR not in fake.clients
    assert any("SVC_DS_COLLECTOR_EXAMPLE_REC_SECRET" in e for e in report.client_errors)

    env[secret_env_name(COLLECTOR)] = "collector-secret"
    report = await sync_organizations(_config(True), kc, environ=env, production=True)
    assert fake.clients[COLLECTOR]["secret"] == "collector-secret"
    await kc.aclose()


@pytest.mark.asyncio
async def test_the_organisation_client_moves_its_acts_to_optional():
    """An organisation client provisioned with the old shape (consent and
    publishing as defaults) is corrected by the next sync."""
    fake = FakeKeycloakWithClientUpdates()
    fake.clients["svc-ds-connector-example-rec"] = {
        "id": "client-pre",
        "body": {},
        "secret": "svc-ds-connector-example-rec",
        "scopes": {"connector.consent.provision", "connector.provider.write"},
        "optional": set(),
        "mappers": [],
    }
    kc = await make_client(fake)
    await sync_organizations(_config(False), kc, environ={}, production=False)
    client = fake.clients["svc-ds-connector-example-rec"]
    assert "connector.consent.provision" not in client["scopes"]
    assert "connector.provider.write" not in client["scopes"]
    assert {
        "connector.consent.provision",
        "connector.provider.write",
        "connector.consent.collector.read",
    } <= client["optional"]
    await kc.aclose()


def test_the_dev_community_is_declared_a_collector():
    from pathlib import Path

    from identity_registry.services.keycloak_admin import load_organizations_config

    repo = Path(__file__).resolve().parents[3]
    config = load_organizations_config(repo / "services/keycloak/organizations.yaml")
    collectors = [o.alias for o in config.organizations if o.collects_consent]
    assert collectors == ["example-org"]
