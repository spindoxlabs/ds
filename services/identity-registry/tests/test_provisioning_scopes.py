"""`provisioning.py`'s copy of `svc-ds-connector`'s grants cannot drift.

A promoted third party runs its own connector, which authenticates against
*this* realm. `CONNECTOR_SCOPES` and `CONNECTOR_AUDIENCES` say what its Keycloak
client gets. `services/keycloak/clients.yaml` says what **our** connector gets,
and the two are meant to be the same set — a participant's connector is not a
more privileged thing than ours.

It is a copy by necessity: `clients.yaml` is not in the identity-registry image
(the Dockerfile ships `src/` and `alembic/`), and the list is read by the HTTP
promotion path inside a container. So the authority file cannot be consulted at
runtime, and these tests are what stands in for that.

This is not hypothetical. The list had already drifted before these tests
existed: `identity-registry.credentials.read` was added to `svc-ds-connector`
and not here, so every third-party connector provisioned in between held a
client whose credential check 403s. A drift of this kind is invisible from both
ends — each file is internally consistent, and the failure appears in a
deployment nobody is looking at.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from identity_registry.services.provisioning import (
    CONNECTOR_AUDIENCES,
    CONNECTOR_SCOPES,
)

# …/services/identity-registry/tests/ → repo root
REPO = Path(__file__).resolve().parents[3]
CLIENTS = REPO / "services" / "keycloak" / "clients.yaml"


def _svc_ds_connector() -> dict:
    if not CLIENTS.is_file():
        pytest.skip(f"authority file not present: {CLIENTS}")
    doc = yaml.safe_load(CLIENTS.read_text(encoding="utf-8")) or {}
    for client in doc.get("clients") or []:
        if client.get("client_id") == "svc-ds-connector":
            return client
    raise AssertionError("svc-ds-connector is not declared in clients.yaml")


def test_connector_scopes_match_the_authority_file():
    declared = _svc_ds_connector().get("default_scopes") or []
    assert sorted(CONNECTOR_SCOPES) == sorted(declared), (
        "provisioning.CONNECTOR_SCOPES has drifted from svc-ds-connector's "
        "default_scopes in services/keycloak/clients.yaml. A third party "
        "promoted now gets a connector client with the wrong grants.\n"
        f"  only in provisioning.py: {sorted(set(CONNECTOR_SCOPES) - set(declared))}\n"
        f"  only in clients.yaml:    {sorted(set(declared) - set(CONNECTOR_SCOPES))}"
    )


def test_connector_audiences_match_the_authority_file():
    declared = _svc_ds_connector().get("extra_audiences") or []
    assert sorted(CONNECTOR_AUDIENCES) == sorted(declared), (
        "provisioning.CONNECTOR_AUDIENCES has drifted from svc-ds-connector's "
        "extra_audiences in services/keycloak/clients.yaml. Every ds service "
        "verifies `aud`, so a missing entry means the third party's connector "
        "authenticates and is then refused by the service it calls.\n"
        f"  only in provisioning.py: "
        f"{sorted(set(CONNECTOR_AUDIENCES) - set(declared))}\n"
        f"  only in clients.yaml:    "
        f"{sorted(set(declared) - set(CONNECTOR_AUDIENCES))}"
    )


def test_a_provisioned_connector_never_holds_an_admin_grant():
    """The rule `clients.yaml` states in prose, asserted against the list a
    third party actually receives. `{service}.admin` is a superset that
    satisfies any `{service}.*`, so one entry here would hand a participant
    every permission in the dataspace."""
    offenders = [s for s in CONNECTOR_SCOPES if s.endswith(".admin")]
    assert offenders == [], f"admin grant in a provisioned client: {offenders}"
