"""The cached service token is refreshed by the wall clock the token expires on."""

from __future__ import annotations

import httpx
import pytest

from ds_auth import service_token
from ds_auth.service_token import ServiceTokenProvider


@pytest.fixture()
def keycloak(monkeypatch):
    """Answers a new token on every grant, and counts the grants."""
    issued: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        issued.append(f"token-{len(issued) + 1}")
        return httpx.Response(200, json={"access_token": issued[-1], "expires_in": 300})

    real = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return real(*args, **kwargs)

    monkeypatch.setattr(service_token.httpx, "AsyncClient", client)
    return issued


@pytest.fixture()
def clocks(monkeypatch):
    """A wall clock and a monotonic clock the test moves independently."""
    now = {"wall": 1_000_000.0, "mono": 500.0}
    monkeypatch.setattr(service_token.time, "time", lambda: now["wall"])
    monkeypatch.setattr(service_token.time, "monotonic", lambda: now["mono"])
    return now


def _provider() -> ServiceTokenProvider:
    return ServiceTokenProvider("http://kc/token", "svc-example", "secret")


async def test_a_fresh_token_is_reused(keycloak, clocks):
    provider = _provider()

    assert await provider() == await provider() == "token-1"
    assert len(keycloak) == 1


async def test_a_token_past_its_expiry_is_replaced(keycloak, clocks):
    provider = _provider()
    await provider()

    clocks["wall"] += 300
    clocks["mono"] += 300

    assert await provider() == "token-2"


async def test_a_suspended_host_does_not_reuse_an_expired_token(keycloak, clocks):
    """The monotonic clock stops during suspend; the token's expiry does not."""
    provider = _provider()
    await provider()

    clocks["wall"] += 8 * 3600  # a night asleep: only the wall clock moved

    assert await provider() == "token-2"


@pytest.fixture()
def grants(monkeypatch):
    """The token requests the provider sends, answered with a token each."""
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "t", "expires_in": 300})

    real = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return real(*args, **kwargs)

    monkeypatch.setattr(service_token.httpx, "AsyncClient", client)
    return seen


async def test_no_scope_asks_for_the_client_defaults(grants):
    await ServiceTokenProvider("http://kc.test/token", "svc-a", "s")()

    assert "scope" not in grants[0].content.decode()


async def test_a_scope_is_requested_on_top_of_the_defaults(grants):
    """The connector's EDC token: the optional EDC scopes, asked for by name."""
    from urllib.parse import parse_qs

    from ds_auth import EDC_MANAGEMENT_SCOPE, EDC_TOKEN_SCOPE, MANAGEMENT_API_SCOPES

    await ServiceTokenProvider(
        "http://kc.test/token", "svc-a", "s", scope=EDC_TOKEN_SCOPE
    )()

    requested = parse_qs(grants[0].content.decode())["scope"][0].split()
    assert set(requested) == {*MANAGEMENT_API_SCOPES, EDC_MANAGEMENT_SCOPE}
