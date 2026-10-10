"""Provenance's did:web fetches take the same address guard and allowance as the
identity registry's (ADR-0029, extended): `PROVENANCE_DID_WEB_INTERNAL_HOSTS` and
`_NETWORKS`, both or neither, validated at load."""

from __future__ import annotations

import pytest
from ds_auth.address_guard import InternalAllowance
from fastapi import HTTPException
from pydantic import ValidationError

from provenance.config import Settings


def test_both_settings_make_the_allowance(monkeypatch):
    monkeypatch.setenv("PROVENANCE_DID_WEB_INTERNAL_HOSTS", ".ds.example.org")
    monkeypatch.setenv("PROVENANCE_DID_WEB_INTERNAL_NETWORKS", "192.168.1.10/32")
    assert Settings().did_web_allowance == InternalAllowance.parse(
        ".ds.example.org", "192.168.1.10/32"
    )


def test_the_default_is_no_allowance():
    assert not Settings().did_web_allowance


@pytest.mark.parametrize(
    ("hosts", "networks"),
    [(".ds.example.org", ""), ("", "10.0.0.0/8"), (".ds.example.org", "8.8.8.0/24")],
)
def test_an_unsound_allowance_refuses_to_load(hosts, networks):
    with pytest.raises(ValidationError, match="did:web internal allowance"):
        Settings(did_web_internal_hosts=hosts, did_web_internal_networks=networks)


@pytest.mark.asyncio
async def test_the_subject_route_resolves_with_the_service_allowance(monkeypatch):
    from provenance.services import subject

    seen: dict = {}

    def capture(*args, **kwargs):
        seen.update(kwargs)
        raise HTTPException(401, "stop")

    monkeypatch.setattr(subject, "verify_user_vc_jwt", capture)
    settings = Settings(
        did_web_internal_hosts=".ds.example.org",
        did_web_internal_networks="10.96.0.0/12",
    )
    with pytest.raises(HTTPException):
        await subject.verified_subject_id(None, "vc", "did:web:x", settings)
    assert seen["did_web_allowance"] == settings.did_web_allowance
    assert seen["did_web_allowance"]
