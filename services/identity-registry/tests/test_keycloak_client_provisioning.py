"""What a Keycloak client must carry to be usable.

A client that authenticates as itself needs a service account, and a token is
only accepted where its `aud` names the recipient.
`keycloak_admin.ensure_service_client` is where ds states that — the client it
creates itself when it owns the realm and promotes a third party. It dropped
part of it once, and the client is created successfully and fails later,
somewhere else, in a way that reads like a permissions bug.

The other surface this file used to cover was `keycloak_mirror.build_mirror`, the
fragment a host realm had to carry when ds is a guest in it. There is no fragment
now: the host mounts `services/keycloak/clients.yaml` itself, so what crosses is a
file boundary and `libs/ds-auth/tests/test_vocabulary.py` asserts it there.
"""

from __future__ import annotations

import pytest

from identity_registry.services.keycloak_admin import KeycloakAdminClient

# ── The client ds creates itself carries its audiences ────────────


class _FakeKeycloak:
    """Records the admin API calls `ensure_service_client` makes."""

    def __init__(self, *, existing_mappers=None):
        self.posted: list[tuple[str, dict]] = []
        self._existing_mappers = existing_mappers or []

    async def __call__(self, method, path, json_body=None, **kwargs):
        if method == "GET" and path == "/clients":
            return [{"id": "uuid-1"}]
        if method == "GET" and path.endswith("/protocol-mappers/models"):
            return self._existing_mappers
        if method == "GET" and path.endswith("/client-secret"):
            return {"value": "s3cret"}
        if method == "POST":
            self.posted.append((path, json_body or {}))
        return None

    def audiences(self) -> list[str]:
        return [
            body["config"]["included.client.audience"]
            for path, body in self.posted
            if path.endswith("/protocol-mappers/models")
        ]


def _client_with(fake) -> KeycloakAdminClient:
    admin = KeycloakAdminClient.__new__(KeycloakAdminClient)
    admin._request = fake
    return admin


@pytest.mark.asyncio
async def test_every_audience_gets_a_mapper():
    """Without these the client authenticates and is then refused by every ds
    service it calls, because each verifies `aud`."""
    fake = _FakeKeycloak()
    secret = await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=["identity-registry.read"],
        audiences=["svc-ds-identity-registry", "svc-ds-provenance"],
    )

    assert secret == "s3cret"
    assert fake.audiences() == [
        "svc-ds-identity-registry",
        "svc-ds-provenance",
    ]


@pytest.mark.asyncio
async def test_the_mapper_lands_in_the_access_token():
    """An audience mapper that only writes the id token changes nothing — the
    services read the access token."""
    fake = _FakeKeycloak()
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=[],
        audiences=["svc-ds-provenance"],
    )

    _, body = next(
        (p, b) for p, b in fake.posted if p.endswith("/protocol-mappers/models")
    )
    assert body["protocolMapper"] == "oidc-audience-mapper"
    assert body["config"]["access.token.claim"] == "true"


@pytest.mark.asyncio
async def test_existing_mappers_are_not_duplicated():
    """Re-running promotion is idempotent, and a duplicated mapper would put the
    audience in the token twice."""
    fake = _FakeKeycloak(
        existing_mappers=[
            {
                "protocolMapper": "oidc-audience-mapper",
                "config": {"included.client.audience": "svc-ds-provenance"},
            }
        ]
    )
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=[],
        audiences=["svc-ds-provenance", "svc-ds-identity-registry"],
    )

    assert fake.audiences() == ["svc-ds-identity-registry"]


@pytest.mark.asyncio
async def test_audiences_are_applied_to_a_client_that_already_exists():
    """The repair path. Every client provisioned before the mappers existed is
    already out there; applying them only at creation would leave that whole
    population broken with no way to fix it but deleting the client."""
    fake = _FakeKeycloak()
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=[],
        audiences=["svc-ds-identity-registry"],
    )

    # No client was created — the GET found one — yet the mapper was still added.
    assert not any(p == "/clients" for p, _ in fake.posted)
    assert fake.audiences() == ["svc-ds-identity-registry"]
