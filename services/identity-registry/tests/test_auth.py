import pytest

from conftest import make_headers


@pytest.mark.asyncio
async def test_admin_without_token_returns_401(client):
    r = await client.post("/admin/participants", json={"did": "did:web:x", "role": "consumer"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_with_wrong_scope_returns_403(client):
    r = await client.post(
        "/admin/participants",
        json={"did": "did:web:x", "role": "consumer"},
        headers=make_headers(scope="some.other.scope"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_public_did_without_auth(client):
    r = await client.get("/dids/did:web:nonexistent/did.json")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_status_without_auth(client):
    r = await client.get("/status/1")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_participant_check_requires_auth(client):
    r = await client.get("/admin/participants/check?did=did:web:x&scope=test")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_participant_check_with_read_scope(client):
    r = await client.get(
        "/admin/participants/check?did=did:web:x&scope=test",
        headers=make_headers(scope="identity-registry.read"),
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False


@pytest.mark.asyncio
async def test_participant_check_with_admin_scope(client):
    r = await client.get(
        "/admin/participants/check?did=did:web:x&scope=test",
        headers=make_headers(scope="identity-registry.admin"),
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False


@pytest.mark.asyncio
async def test_participant_list_requires_auth(client):
    r = await client.get("/admin/participants")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_participant_list_with_read_scope(client):
    r = await client.get(
        "/admin/participants",
        headers=make_headers(scope="identity-registry.read"),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_participant_list_read_scope_returns_active_only(client):
    """Read scope always filters to active participants only."""
    headers_admin = make_headers(scope="identity-registry.admin")
    headers_read = make_headers(scope="identity-registry.read")

    await client.post(
        "/admin/participants",
        json={"did": "did:web:active-one", "role": "consumer"},
        headers=headers_admin,
    )
    await client.post(
        "/admin/participants",
        json={"did": "did:web:inactive-one", "role": "consumer"},
        headers=headers_admin,
    )
    await client.patch(
        "/admin/participants/did:web:inactive-one",
        json={"active": False},
        headers=headers_admin,
    )

    r_admin = await client.get("/admin/participants", headers=headers_admin)
    assert r_admin.status_code == 200
    assert len(r_admin.json()) == 2

    r_read = await client.get("/admin/participants", headers=headers_read)
    assert r_read.status_code == 200
    dids = [p["did"] for p in r_read.json()]
    assert "did:web:active-one" in dids
    assert "did:web:inactive-one" not in dids


@pytest.mark.asyncio
async def test_keycloak_mapping_without_auth_returns_401(client):
    r = await client.get("/admin/keycloak/mapping/did:web:x")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_keycloak_mapping_by_subject_without_auth_returns_401(client):
    r = await client.get("/admin/keycloak/mapping?subject_id=did:web:x")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_resolve_without_auth_returns_401(client):
    r = await client.get("/users/resolve?email=test@example.com")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_resolve_with_wrong_scope_returns_403(client):
    # Note: `identity-registry.admin` is a superset that also grants resolve,
    # so a genuinely unrelated scope is used here to assert the 403 path.
    r = await client.get(
        "/users/resolve?email=test@example.com",
        headers=make_headers(scope="some.other.scope"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_resolve_with_correct_scope(client):
    r = await client.get(
        "/users/resolve?email=nonexistent@example.com",
        headers=make_headers(scope="identity-registry.resolve"),
    )
    assert r.status_code == 404
