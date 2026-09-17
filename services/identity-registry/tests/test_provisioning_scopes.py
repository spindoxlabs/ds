"""What identity-registry gives an organisation's client comes from `ds_auth`.

`svc-ds-connector` in `services/keycloak/clients.yaml` is an audience and holds
nothing (plan `the-management-api-is-v3-behind-one-key`, decision 3): every
connector presents its organisation's client, `svc-ds-connector-<alias>`, which
this service creates. `clients.yaml` is not in this image, so the grants cannot
be read from it at runtime; `ds_auth` holds the one list, and these tests check
it against the realm declaration.

The list this replaced was a copy pinned to `svc-ds-connector`'s grants, and it
had drifted once — `identity-registry.credentials.read` was added to the client
and not to the copy, and every connector provisioned in between got a client
whose credential check 403s.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ds_auth import (
    CONNECTOR_AUDIENCES as AUTHORITY_AUDIENCES,
)
from ds_auth import (
    CONNECTOR_SERVICE_SCOPES,
    MANAGEMENT_API_SCOPES,
    is_management_api_scope,
)

from identity_registry.services.provisioning import (
    CONNECTOR_AUDIENCES,
    CONNECTOR_SCOPES,
    ORGANISATION_CLIENT_SCOPES,
    client_id_for,
)

# …/services/identity-registry/tests/ → repo root
REPO = Path(__file__).resolve().parents[3]
KEYCLOAK = REPO / "services" / "keycloak"


def _declared() -> tuple[set[str], set[str]]:
    scopes: set[str] = set()
    clients: set[str] = set()
    for path in KEYCLOAK.glob("clients*.yaml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scopes |= {s["name"] for s in doc.get("scopes") or []}
        clients |= {c["client_id"] for c in doc.get("clients") or []}
    if not scopes:
        pytest.skip(f"realm declarations not present under {KEYCLOAK}")
    return scopes, clients


def test_the_connector_grants_are_ds_auth_s():
    assert CONNECTOR_SCOPES == list(CONNECTOR_SERVICE_SCOPES)
    assert CONNECTOR_AUDIENCES == list(AUTHORITY_AUDIENCES)


def test_every_granted_scope_is_one_the_realm_declares():
    """Keycloak ignores an unknown default scope without a word."""
    declared, _ = _declared()
    assert set(ORGANISATION_CLIENT_SCOPES) <= declared


def test_every_audience_is_a_declared_client():
    """An audience mapper emits a literal; one naming no client is a token no
    service accepts."""
    _, clients = _declared()
    assert set(CONNECTOR_AUDIENCES) <= clients


def test_svc_ds_connector_is_an_audience_only():
    doc = yaml.safe_load((KEYCLOAK / "clients.yaml").read_text(encoding="utf-8"))
    (client,) = [c for c in doc["clients"] if c["client_id"] == "svc-ds-connector"]
    assert not client.get("default_scopes")
    assert client.get("scopes_prefix") == "connector"


def test_a_provisioned_connector_never_holds_an_admin_grant():
    """The rule `clients.yaml` states in prose, asserted against the list a
    third party actually receives. `{service}.admin` is a superset that
    satisfies any `{service}.*`, so one entry here would hand a participant
    every permission in the dataspace."""
    offenders = [s for s in CONNECTOR_SCOPES if s.endswith(".admin")]
    assert offenders == [], f"admin grant in a provisioned client: {offenders}"


def test_an_organisation_client_holds_the_connector_grants_and_the_edc_scopes():
    """The organisation's client is its connector's client, plus EDC's
    management-API scopes for its own participant context — the list
    `ds_auth` owns and `clients.yaml` declares, nothing added here."""
    assert ORGANISATION_CLIENT_SCOPES == [*CONNECTOR_SCOPES, *MANAGEMENT_API_SCOPES]
    assert [s for s in CONNECTOR_SCOPES if is_management_api_scope(s)] == []


def test_the_bundle_and_org_sync_name_the_same_client():
    from ds_auth import organisation_client_id

    assert client_id_for("example-rec") == organisation_client_id("example-rec")
    assert client_id_for("example-rec") == "svc-ds-connector-example-rec"
