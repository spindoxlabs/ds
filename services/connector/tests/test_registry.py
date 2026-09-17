"""Tests for ParticipantRegistry."""

import textwrap
from pathlib import Path

import httpx
import pytest
import respx

from connector.registry.participants import (
    HttpParticipantRegistry,
    ParticipantRegistry,
    UnknownParticipantError,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "participants.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def test_from_file_loads_participants(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        participants:
          - id: provider
            dsp_address: http://edc-rec:19194/protocol
            allowed_scopes: [dataspaces.query, dataspaces.admin]
            roles: [provider]
          - id: consumer
            dsp_address: http://edc-third-party:29194/protocol
            allowed_scopes: [dataspaces.query]
            roles: [consumer]
    """,
    )
    registry = ParticipantRegistry.from_file(p)
    assert len(registry.all()) == 2


def test_validate_known_participant(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        participants:
          - id: consumer
            dsp_address: http://edc-third-party:29194/protocol
            allowed_scopes: [dataspaces.query]
            roles: [consumer]
    """,
    )
    registry = ParticipantRegistry.from_file(p)
    participant = registry.validate("http://edc-third-party:29194/protocol")
    assert participant.id == "consumer"


@pytest.mark.rule("C-19")
def test_validate_unknown_raises(tmp_path):
    registry = ParticipantRegistry.from_file(tmp_path / "missing.yaml")
    with pytest.raises(UnknownParticipantError):
        registry.validate("http://unknown:9999/protocol")


def test_get_by_id(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        participants:
          - id: provider
            dsp_address: http://edc-rec:19194/protocol
            roles: [provider]
    """,
    )
    registry = ParticipantRegistry.from_file(p)
    participant = registry.get_by_id("provider")
    assert participant is not None
    assert participant.roles == ["provider"]
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
async def test_http_registry_lists_for_the_operator_view_and_caches():
    respx.get(f"{REGISTRY_URL}/admin/participants").mock(
        return_value=httpx.Response(200, json=PARTICIPANTS_RESPONSE)
    )

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        participants = await registry.all()
        assert len(participants) == 2
        assert "dataspaces.query" in participants[0].allowed_scopes
        await registry.all()
        assert respx.calls.call_count == 1
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


# ── One counterparty: GET /participants/resolve (C-19) ──────────

RESOLVED = {
    "did": "did:web:dso.ds.localhost",
    "dsp_address": "http://edc-dso:49194/protocol",
    "roles": ["provider"],
}


def _resolve_route():
    return respx.get(f"{REGISTRY_URL}/participants/resolve")


@pytest.mark.rule("C-19")
@pytest.mark.asyncio
@respx.mock
async def test_a_counterparty_is_resolved_by_address_not_by_the_admin_listing():
    listing = respx.get(f"{REGISTRY_URL}/admin/participants").mock(
        return_value=httpx.Response(200, json=PARTICIPANTS_RESPONSE)
    )
    route = _resolve_route().mock(return_value=httpx.Response(200, json=RESOLVED))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        p = await registry.validate("http://edc-dso:49194/protocol")
        assert p.id == "did:web:dso.ds.localhost"
        assert p.roles == ["provider"]
        # The narrow route discloses no scopes, and none are invented.
        assert p.allowed_scopes == []
        assert route.calls.last.request.url.params["dsp_address"] == (
            "http://edc-dso:49194/protocol"
        )
        await registry.validate("http://edc-dso:49194/protocol")
        assert route.call_count == 1, "the answer is cached"
        assert listing.call_count == 0, "the admin listing is not read"
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_a_participant_is_resolved_by_did():
    route = _resolve_route().mock(return_value=httpx.Response(200, json=RESOLVED))
    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        p = await registry.get_by_id("did:web:dso.ds.localhost")
        assert p is not None and p.dsp_address == RESOLVED["dsp_address"]
        assert route.calls.last.request.url.params["did"] == RESOLVED["did"]
    finally:
        await registry.close()


@pytest.mark.rule("C-19")
@pytest.mark.asyncio
@respx.mock
async def test_http_registry_unknown_raises():
    _resolve_route().mock(return_value=httpx.Response(404, json={"detail": "x"}))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        with pytest.raises(UnknownParticipantError):
            await registry.validate("http://unknown:9999/protocol")
        assert await registry.get_by_id("did:web:unknown") is None
    finally:
        await registry.close()


@pytest.mark.rule("C-19")
@pytest.mark.asyncio
@respx.mock
async def test_an_unreachable_registry_fails_closed_with_nothing_cached():
    _resolve_route().mock(side_effect=httpx.ConnectError("down"))
    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        with pytest.raises(UnknownParticipantError):
            await registry.validate("http://edc-dso:49194/protocol")
        with pytest.raises(UnknownParticipantError):
            await registry.get_by_id("did:web:dso.ds.localhost")
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_a_cached_answer_is_served_through_an_outage_until_too_stale(
    monkeypatch,
):
    import connector.registry.participants as module

    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    route = _resolve_route().mock(return_value=httpx.Response(200, json=RESOLVED))
    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=10)
    try:
        await registry.validate(RESOLVED["dsp_address"])
        route.mock(return_value=httpx.Response(500))
        clock[0] += 20  # past the TTL, within max staleness (300s)
        assert (await registry.validate(RESOLVED["dsp_address"])).id == RESOLVED["did"]
        clock[0] += 400  # past max staleness
        with pytest.raises(UnknownParticipantError):
            await registry.validate(RESOLVED["dsp_address"])
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_invalidate_drops_the_resolved_answers():
    route = _resolve_route().mock(return_value=httpx.Response(404))
    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        assert await registry.get_by_id(RESOLVED["did"]) is None
        route.mock(return_value=httpx.Response(200, json=RESOLVED))
        assert await registry.get_by_id(RESOLVED["did"]) is None, "cached miss"
        registry.invalidate()
        assert (await registry.get_by_id(RESOLVED["did"])) is not None
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
        allowed = await registry.check_scope(
            "did:web:rec.ds.localhost", "dataspaces.query"
        )
        assert allowed is True
    finally:
        await registry.close()


@pytest.mark.rule("C-19")
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


@pytest.mark.rule("X-6b")
@pytest.mark.asyncio
@respx.mock
async def test_http_registry_check_scope_error_returns_false():
    respx.get(
        f"{REGISTRY_URL}/admin/participants/check",
        params={"did": "did:web:rec.ds.localhost", "scope": "dataspaces.query"},
    ).mock(return_value=httpx.Response(500))

    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        allowed = await registry.check_scope(
            "did:web:rec.ds.localhost", "dataspaces.query"
        )
        assert allowed is False
    finally:
        await registry.close()


# ── The collector relation: GET /consent-collectors/check ─────────────────────
#
# Plan `a-collector-registers-consent-at-the-holder`, decision 1: a cached lookup
# with a configurable TTL, dropped by the registry's invalidation hint, serving a
# stale answer through an outage only up to its bound, and failing closed.

HOLDER_DID = "did:web:dso.ds.localhost"
COLLECTOR_DID = "did:web:rec.ds.localhost"
ACCEPTED = {
    "holder_did": HOLDER_DID,
    "collector_did": COLLECTOR_DID,
    "accepted": True,
    "collector_owner": "example-rec",
    "reason": "an accepted collector",
}


def _collector_route():
    return respx.get(f"{REGISTRY_URL}/consent-collectors/check")


@pytest.mark.rule("D-21")
@pytest.mark.asyncio
@respx.mock
async def test_the_collector_answer_is_asked_once_per_ttl():
    route = _collector_route().mock(return_value=httpx.Response(200, json=ACCEPTED))
    registry = HttpParticipantRegistry(
        REGISTRY_URL, cache_ttl=60, collector_cache_ttl=30
    )
    try:
        answer = await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        assert answer.accepted is True
        assert answer.collector_owner == "example-rec"
        params = route.calls.last.request.url.params
        assert (params["holder_did"], params["collector_did"]) == (
            HOLDER_DID,
            COLLECTOR_DID,
        )
        await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        assert route.call_count == 1
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_the_collector_ttl_is_its_own_setting(monkeypatch):
    import connector.registry.participants as module

    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    route = _collector_route().mock(return_value=httpx.Response(200, json=ACCEPTED))
    registry = HttpParticipantRegistry(
        REGISTRY_URL, cache_ttl=600, collector_cache_ttl=5
    )
    try:
        await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        clock[0] += 6
        await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        assert route.call_count == 2
    finally:
        await registry.close()


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
@respx.mock
async def test_a_revoked_collector_is_refused_as_soon_as_the_hint_arrives():
    route = _collector_route().mock(return_value=httpx.Response(200, json=ACCEPTED))
    registry = HttpParticipantRegistry(REGISTRY_URL, cache_ttl=60)
    try:
        assert (await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)).accepted
        route.mock(
            return_value=httpx.Response(200, json={**ACCEPTED, "accepted": False})
        )
        assert (await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)).accepted
        # `POST /internal/registry/invalidate` — the hint the registry sends.
        registry.invalidate()
        assert not (
            await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        ).accepted
    finally:
        await registry.close()


@pytest.mark.asyncio
@respx.mock
async def test_the_collector_lookup_fails_closed(monkeypatch):
    import connector.registry.participants as module
    from connector.registry.participants import CollectorLookupError

    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    route = _collector_route().mock(side_effect=httpx.ConnectError("down"))
    registry = HttpParticipantRegistry(
        REGISTRY_URL, cache_ttl=60, collector_cache_ttl=10
    )
    try:
        with pytest.raises(CollectorLookupError):
            await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        route.mock(return_value=httpx.Response(200, json=ACCEPTED))
        await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        route.mock(return_value=httpx.Response(503))
        clock[0] += 20  # past the TTL, within five TTLs
        assert (await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)).accepted
        clock[0] += 60  # past the staleness bound
        with pytest.raises(CollectorLookupError):
            await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
        # An answer that is not a boolean is no answer.
        route.mock(
            return_value=httpx.Response(200, json={**ACCEPTED, "accepted": "yes"})
        )
        registry.invalidate()
        with pytest.raises(CollectorLookupError):
            await registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
    finally:
        await registry.close()


def test_the_static_registry_knows_the_self_pair_and_the_listed_ones(tmp_path):
    path = tmp_path / "participants.yaml"
    path.write_text(
        textwrap.dedent(
            f"""
            participants: []
            consent_collectors:
              - holder_did: {HOLDER_DID}
                collector_did: {COLLECTOR_DID}
                collector_owner: example-rec
            """
        )
    )
    registry = ParticipantRegistry.from_file(path)
    listed = registry.consent_collector(HOLDER_DID, COLLECTOR_DID)
    assert (listed.accepted, listed.collector_owner) == (True, "example-rec")
    assert registry.consent_collector(HOLDER_DID, HOLDER_DID).accepted
    assert not registry.consent_collector(HOLDER_DID, "did:web:other").accepted
