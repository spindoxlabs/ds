import pytest

from conftest import make_admin_headers


@pytest.mark.asyncio
async def test_admin_without_token_returns_401(client):
    r = await client.post("/admin/participants", json={"did": "did:web:x", "role": "consumer"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_with_wrong_scope_returns_403(client):
    r = await client.post(
        "/admin/participants",
        json={"did": "did:web:x", "role": "consumer"},
        headers=make_admin_headers(scope="some.other.scope"),
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
async def test_internal_check_without_auth(client):
    r = await client.get("/participants/did:web:x/check?scope=test")
    assert r.status_code == 200
    assert r.json()["allowed"] is False
