"""The connector's did:web fetches take the same address guard and allowance as
the identity registry's (ADR-0029, extended).

The issuer of a person's credential is resolved through `ds_auth.did_web`, which
now refuses non-public addresses outside `DS_ENV=dev`. A deployment whose cluster
resolves the dataspace's own hosts privately names them, per service:
`CONNECTOR_DID_WEB_INTERNAL_HOSTS` and `_NETWORKS`, both or neither, validated
at load like the registry's.
"""

from __future__ import annotations

import pytest
from ds_auth.address_guard import InternalAllowance
from fastapi import HTTPException
from pydantic import ValidationError

from connector.config import Settings


def test_both_settings_make_the_allowance(monkeypatch):
    monkeypatch.setenv("CONNECTOR_DID_WEB_INTERNAL_HOSTS", ".ds.example.org")
    monkeypatch.setenv("CONNECTOR_DID_WEB_INTERNAL_NETWORKS", "192.168.1.10/32")
    settings = Settings()
    assert settings.did_web_allowance == InternalAllowance.parse(
        ".ds.example.org", "192.168.1.10/32"
    )


def test_the_default_is_no_allowance():
    assert not Settings().did_web_allowance


@pytest.mark.parametrize(
    ("hosts", "networks"),
    [(".ds.example.org", ""), ("", "10.0.0.0/8"), (".org", "10.0.0.0/8"),
     (".ds.example.org", "0.0.0.0/0")],
)
def test_an_unsound_allowance_refuses_to_load(hosts, networks):
    with pytest.raises(ValidationError, match="did:web internal allowance"):
        Settings(did_web_internal_hosts=hosts, did_web_internal_networks=networks)


@pytest.mark.asyncio
async def test_a_person_route_resolves_with_the_service_allowance(monkeypatch):
    from connector import dependencies

    seen: dict = {}

    def capture(*args, **kwargs):
        seen.update(kwargs)
        raise HTTPException(401, "stop")

    monkeypatch.setattr(dependencies, "verify_user_vc_jwt", capture)
    settings = Settings(
        did_web_internal_hosts=".ds.example.org",
        did_web_internal_networks="10.96.0.0/12",
    )
    with pytest.raises(HTTPException):
        await dependencies.verify_person(
            None, "vc", "did:web:x", {"DataSubject"},
            linked_participant=None, settings=settings,
        )
    assert seen["did_web_allowance"] == settings.did_web_allowance
    assert seen["did_web_allowance"]


class _Stop(Exception):
    pass


@pytest.mark.asyncio
async def test_an_active_allowance_is_logged_at_start(monkeypatch):
    """ADR-0029: a widened outbound boundary is said out loud at every start.
    Stopped right after the guard, at the schema check."""
    from connector import main
    from connector.config import get_settings

    said: list[str] = []

    async def stop():
        raise _Stop

    monkeypatch.setattr(main, "verify_schema", stop)
    monkeypatch.setattr(
        main.log, "warning", lambda msg, *args: said.append(msg % args)
    )
    monkeypatch.setenv("DS_ENV", "dev")
    monkeypatch.setenv("CONNECTOR_DID_WEB_INTERNAL_HOSTS", ".ds.example.org")
    monkeypatch.setenv("CONNECTOR_DID_WEB_INTERNAL_NETWORKS", "192.168.1.10/32")
    get_settings.cache_clear()
    try:
        with pytest.raises(_Stop):
            async with main.lifespan(main.create_app()):
                pass
    finally:
        get_settings.cache_clear()
    assert (
        "did:web internal allowance active: hosts under .ds.example.org may "
        "resolve to 192.168.1.10/32"
    ) in said
