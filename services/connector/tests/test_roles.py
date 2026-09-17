"""`CONNECTOR_ROLE` is provider, consumer, or both in one process.

Decided 2026-09-17: both roles can coexist, and one participant runs one EDC
runtime, so a both-roles process mounts both routers against one management API.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import connector.main as main
from connector.config import Settings


@pytest.mark.parametrize(
    "role,provider,consumer",
    [
        ("provider", True, False),
        ("consumer", False, True),
        ("both", True, True),
    ],
)
def test_the_role_setting_parses(role, provider, consumer):
    settings = Settings(role=role)
    assert (settings.is_provider, settings.is_consumer) == (provider, consumer)


@pytest.mark.parametrize("role", ["", "PROVIDER", "provider,consumer", "neither"])
def test_an_unknown_role_is_refused(role):
    with pytest.raises(ValidationError):
        Settings(role=role)


def _paths(role: str, monkeypatch) -> set[str]:
    monkeypatch.setattr(main, "get_settings", lambda: Settings(role=role))
    app = main.create_app()
    return {getattr(route, "path", "") for route in app.routes}


@pytest.mark.parametrize(
    "role,mounted,absent",
    [
        ("provider", {"/provider/sync"}, {"/consumer/negotiate"}),
        ("consumer", {"/consumer/negotiate"}, {"/provider/sync"}),
        ("both", {"/provider/sync", "/consumer/negotiate"}, set()),
    ],
)
def test_the_routers_follow_the_role(role, mounted, absent, monkeypatch):
    paths = _paths(role, monkeypatch)
    assert mounted <= paths
    assert not absent & paths
    # Shared routers mount whatever the role.
    assert {
        "/webhooks/edc-callback",
        "/internal/agreements/{agreement_id}/status",
    } <= paths


def test_the_participant_context_defaults_to_the_participant_did():
    settings = Settings(role="provider", participant_did="did:web:rec.example.org")
    assert settings.participant_context_id == "did:web:rec.example.org"
    stated = Settings(
        role="provider",
        participant_did="did:web:rec.example.org",
        edc_participant_context_id="ctx-1",
    )
    assert stated.participant_context_id == "ctx-1"


async def test_a_both_roles_process_uses_one_edc_client(monkeypatch):
    settings = Settings(role="both")

    async def _no_schema_check():
        return None

    async def _no_sweeper(*_a, **_k):
        return None

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "verify_schema", _no_schema_check)
    monkeypatch.setattr(main, "run_sweeper", _no_sweeper)
    app = main.create_app()
    async with app.router.lifespan_context(app):
        assert app.state.provider_edc is app.state.consumer_edc is app.state.edc
        assert app.state.edc.participant_context_id == settings.participant_context_id
        assert app.state.consumer_service is not None
