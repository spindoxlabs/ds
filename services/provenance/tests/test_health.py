"""Health and context endpoint smoke tests."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_context_endpoint(client):
    response = await client.get("/prov/context")
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    body = response.json()
    assert "@context" in body
    ctx = body["@context"]
    assert "prov" in ctx
    assert "xsd" in ctx
    assert "wasGeneratedBy" in ctx
