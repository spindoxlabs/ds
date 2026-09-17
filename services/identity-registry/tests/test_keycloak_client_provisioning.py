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
    """Records the admin API calls `ensure_service_client` makes.

    Models one client (`uuid-1`), the realm's client scopes and the client's
    default scopes, because the call reconciles those too.
    """

    def __init__(
        self,
        *,
        existing_mappers=None,
        realm_scopes=(),
        assigned=(),
        exists=True,
        secret="s3cret",
    ):
        self.posted: list[tuple[str, dict]] = []
        self.put: list[tuple[str, dict | None]] = []
        self.deleted: list[str] = []
        self._existing_mappers = existing_mappers or []
        self.realm_scopes = {name: f"id-{name}" for name in realm_scopes}
        self.assigned = {name: f"id-{name}" for name in assigned}
        self.exists = exists
        self.secret = secret

    async def __call__(self, method, path, json_body=None, **kwargs):
        if method == "GET" and path == "/clients":
            return [{"id": "uuid-1"}] if self.exists else []
        if method == "POST" and path == "/clients":
            self.posted.append((path, json_body or {}))
            self.exists = True
            self.assigned.update(
                {
                    name: f"id-{name}"
                    for name in json_body.get("defaultClientScopes", [])
                    if name in self.realm_scopes
                }
            )
            if json_body.get("secret"):
                self.secret = json_body["secret"]
            return None
        if method == "GET" and path == "/client-scopes":
            return [{"name": n, "id": i} for n, i in self.realm_scopes.items()]
        if method == "GET" and path.endswith("/default-client-scopes"):
            return [{"name": n, "id": i} for n, i in self.assigned.items()]
        if method == "PUT" and "/default-client-scopes/" in path:
            scope_id = path.rsplit("/", 1)[1]
            name = scope_id.removeprefix("id-")
            self.assigned[name] = scope_id
            self.put.append((path, json_body))
            return None
        if method == "DELETE" and "/default-client-scopes/" in path:
            scope_id = path.rsplit("/", 1)[1]
            self.assigned.pop(scope_id.removeprefix("id-"), None)
            self.deleted.append(path)
            return None
        if method == "GET" and path.endswith("/protocol-mappers/models"):
            return self._existing_mappers
        if method == "GET" and path.endswith("/client-secret"):
            return {"value": self.secret}
        if method == "PUT":
            self.put.append((path, json_body))
            return None
        if method == "POST":
            self.posted.append((path, json_body or {}))
        return None

    def audiences(self) -> list[str]:
        return [
            body["config"]["included.client.audience"]
            for path, body in self.posted
            if path.endswith("/protocol-mappers/models")
            and body["protocolMapper"] == "oidc-audience-mapper"
        ]

    def subject_mappers(self) -> list[dict]:
        return [
            body
            for path, body in self.posted
            if path.endswith("/protocol-mappers/models")
            and body["protocolMapper"] == "oidc-hardcoded-claim-mapper"
        ]


def _client_with(fake) -> KeycloakAdminClient:
    admin = KeycloakAdminClient.__new__(KeycloakAdminClient)
    admin._request = fake
    return admin


@pytest.mark.asyncio
async def test_every_audience_gets_a_mapper():
    """Without these the client authenticates and is then refused by every ds
    service it calls, because each verifies `aud`."""
    fake = _FakeKeycloak(realm_scopes=["identity-registry.read"])
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


# ── Scopes are reconciled on every call ───────────────────────────


@pytest.mark.asyncio
async def test_a_missing_default_scope_is_assigned_to_an_existing_client():
    """Keycloak assigns `defaultClientScopes` only when it creates a client. A
    client created before `management-api:*` existed would never receive them,
    and EDC would refuse its connector."""
    fake = _FakeKeycloak(
        realm_scopes=["identity-registry.read", "management-api:catalog:read"],
        assigned=["identity-registry.read"],
    )
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=["identity-registry.read", "management-api:catalog:read"],
    )

    assert [p for p, _ in fake.put] == [
        "/clients/uuid-1/default-client-scopes/id-management-api:catalog:read"
    ]


@pytest.mark.asyncio
async def test_a_scope_the_realm_does_not_declare_is_an_error():
    """Keycloak ignores an unknown scope name without a word; the client would
    look provisioned and be refused wherever the scope is checked."""
    fake = _FakeKeycloak(realm_scopes=[])
    with pytest.raises(RuntimeError, match="management-api:catalog:read"):
        await _client_with(fake).ensure_service_client(
            "svc-ds-connector-acme",
            name="ds connector — Acme",
            scopes=["management-api:catalog:read"],
        )


@pytest.mark.asyncio
async def test_an_unlisted_management_api_scope_is_removed_and_realm_defaults_kept():
    """A `management-api` grant is a caller of EDC's management API, and EDC does
    not check `aud` — so one the list no longer names must go. The scopes
    Keycloak assigned at creation (`profile`, …) are not ds's to remove."""
    fake = _FakeKeycloak(
        realm_scopes=["profile", "management-api:admin", "management-api:catalog:read"],
        assigned=["profile", "management-api:admin", "management-api:catalog:read"],
    )
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme",
        name="ds connector — Acme",
        scopes=["management-api:catalog:read"],
    )

    assert fake.deleted == [
        "/clients/uuid-1/default-client-scopes/id-management-api:admin"
    ]
    assert set(fake.assigned) == {"profile", "management-api:catalog:read"}


# ── The `sub` an organisation client's tokens carry ───────────────

DID = "did:web:rec.example.org"


@pytest.mark.asyncio
async def test_the_subject_mapper_sets_sub_on_the_access_token():
    """EDC's v5 management API reads the caller's participant context from `sub`;
    Keycloak otherwise sets it to the service account's UUID."""
    fake = _FakeKeycloak()
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[], subject=DID
    )

    (mapper,) = fake.subject_mappers()
    assert mapper["name"] == "participant-context-sub"
    assert mapper["config"]["claim.name"] == "sub"
    assert mapper["config"]["claim.value"] == DID
    assert mapper["config"]["access.token.claim"] == "true"


@pytest.mark.asyncio
async def test_no_subject_means_no_mapper():
    fake = _FakeKeycloak()
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[]
    )
    assert fake.subject_mappers() == []


@pytest.mark.asyncio
async def test_a_subject_mapper_already_right_is_left_alone():
    fake = _FakeKeycloak(
        existing_mappers=[
            {
                "id": "m-1",
                "name": "participant-context-sub",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {"claim.name": "sub", "claim.value": DID},
            }
        ]
    )
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[], subject=DID
    )
    assert fake.subject_mappers() == []
    assert fake.put == []


@pytest.mark.asyncio
async def test_a_subject_mapper_naming_another_context_is_corrected():
    fake = _FakeKeycloak(
        existing_mappers=[
            {
                "id": "m-1",
                "name": "participant-context-sub",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "sub",
                    "claim.value": "did:web:old.example.org",
                },
            }
        ]
    )
    await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[], subject=DID
    )
    ((path, body),) = fake.put
    assert path == "/clients/uuid-1/protocol-mappers/models/m-1"
    assert body["id"] == "m-1"
    assert body["config"]["claim.value"] == DID


# ── A configured secret is a creation-time value ──────────────────


@pytest.mark.asyncio
async def test_a_configured_secret_is_used_when_the_client_is_created():
    fake = _FakeKeycloak(exists=False)
    held = await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[], secret="chosen"
    )
    ((_, body),) = [(p, b) for p, b in fake.posted if p == "/clients"]
    assert body["secret"] == "chosen"
    assert body["serviceAccountsEnabled"] is True
    assert held == "chosen"


@pytest.mark.asyncio
async def test_a_configured_secret_never_rewrites_an_existing_client():
    """Rotation is an explicit act; a sync that rewrote a live secret would cut
    off whatever already holds it."""
    fake = _FakeKeycloak(secret="live")
    held = await _client_with(fake).ensure_service_client(
        "svc-ds-connector-acme", name="n", scopes=[], secret="chosen"
    )
    assert held == "live"
    assert not any(p == "/clients" for p, _ in fake.posted)
    assert not any(p.endswith("/client-secret") for p, _ in fake.posted)
