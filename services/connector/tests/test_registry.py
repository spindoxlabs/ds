"""Tests for ParticipantRegistry."""
import textwrap
from pathlib import Path

import httpx
import pytest
import respx

from connector.registry.participants import (
    HttpParticipantRegistry,
    Participant,
    ParticipantRegistry,
    UnknownParticipantError,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "participants.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def test_from_file_loads_participants(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: provider
            dsp_address: http://edc-provider:19194/protocol
            allowed_scopes: [dataspaces.query, dataspaces.admin]
            role: provider
          - id: consumer
            dsp_address: http://edc-consumer:29194/protocol
            allowed_scopes: [dataspaces.query]
            role: consumer
    """)
    registry = ParticipantRegistry.from_file(p)
    assert len(registry.all()) == 2


def test_validate_known_participant(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: consumer
            dsp_address: http://edc-consumer:29194/protocol
            allowed_scopes: [dataspaces.query]
            role: consumer
    """)
    registry = ParticipantRegistry.from_file(p)
    participant = registry.validate("http://edc-consumer:29194/protocol")
    assert participant.id == "consumer"


def test_validate_unknown_raises(tmp_path):
    registry = ParticipantRegistry.from_file(tmp_path / "missing.yaml")
    with pytest.raises(UnknownParticipantError):
        registry.validate("http://unknown:9999/protocol")


def test_get_by_id(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: provider
            dsp_address: http://edc-provider:19194/protocol
            role: provider
    """)
    registry = ParticipantRegistry.from_file(p)
    participant = registry.get_by_id("provider")
    assert participant is not None
    assert participant.role == "provider"
    assert registry.get_by_id("nonexistent") is None


def test_empty_registry():
    registry = ParticipantRegistry.empty()
    assert registry.all() == []
    with pytest.raises(UnknownParticipantError):
        registry.validate("any")


# ── HttpParticipantRegistry ─────────────────────────────────────


REGISTRY_URL = "http://identity-registry:30005"

PARTICIPANTS_RESPONSE = [
    {
        "did": "did:web:rec.ds.localhost",
        "dsp_address": "http://edc-rec:19194/protocol",
        "role": "provider",
        "allowed_scopes": ["dataspaces.query", "identity-registry.admin"],
        "active": True,
        "registered_at": "2026-01-01T00:00:00Z",
    },
    {
        "did": "did:web:dso.ds.localhost",
        "dsp_address": "http://edc-dso:49194/protocol",
        "role": "provider",
        "allowed_scopes": ["dataspaces.query"],
        "active": True,
        "registered_at": "2026-01-01T00:00:00Z",
    },
]


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_fetches_and_caches():
    respx.get(f"{REGISTRY_URL}/admin/participants").mock(
        return_value=httpx.Response(200, json=PARTICIPANTS_RESPONSE)
    )

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        participants = await registry.all()
        assert len(participants) == 2

        p = await registry.get_by_id("did:web:rec.ds.localhost")
        assert p is not None
        assert p.role == "provider"
        assert "dataspaces.query" in p.allowed_scopes

        p2 = await registry.validate("http://edc-dso:49194/protocol")
        assert p2.id == "did:web:dso.ds.localhost"

        assert respx.calls.call_count == 1
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_unknown_raises():
    respx.get(f"{REGISTRY_URL}/admin/participants").mock(
        return_value=httpx.Response(200, json=PARTICIPANTS_RESPONSE)
    )

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        with pytest.raises(UnknownParticipantError):
            await registry.validate("http://unknown:9999/protocol")
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_uses_stale_cache_on_error():
    route = respx.get(f"{REGISTRY_URL}/admin/participants")
    route.mock(return_value=httpx.Response(200, json=PARTICIPANTS_RESPONSE))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=0)
    try:
        await registry.all()
        assert respx.calls.call_count == 1

        route.mock(return_value=httpx.Response(500))
        participants = await registry.all()
        assert len(participants) == 2
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_check_scope():
    respx.get(
        f"{REGISTRY_URL}/admin/participants/check",
        params={"did": "did:web:rec.ds.localhost", "scope": "dataspaces.query"},
    ).mock(return_value=httpx.Response(200, json={"allowed": True}))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        allowed = await registry.check_scope("did:web:rec.ds.localhost", "dataspaces.query")
        assert allowed is True
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_check_scope_denied():
    respx.get(
        f"{REGISTRY_URL}/admin/participants/check",
        params={"did": "did:web:rec.ds.localhost", "scope": "admin.secret"},
    ).mock(return_value=httpx.Response(200, json={"allowed": False}))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        allowed = await registry.check_scope("did:web:rec.ds.localhost", "admin.secret")
        assert allowed is False
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_registry_check_scope_error_returns_false():
    respx.get(
        f"{REGISTRY_URL}/admin/participants/check",
        params={"did": "did:web:rec.ds.localhost", "scope": "dataspaces.query"},
    ).mock(return_value=httpx.Response(500))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        allowed = await registry.check_scope("did:web:rec.ds.localhost", "dataspaces.query")
        assert allowed is False
    finally:
        await registry.close()
