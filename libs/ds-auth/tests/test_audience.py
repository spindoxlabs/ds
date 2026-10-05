"""One audience per scope, checked by the receiver (ADR-0026, `ds_auth.audience`)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from ds_auth import Principal
from ds_auth.audience import (
    audience_bound,
    check_audience_bound,
    own_audience,
    plain_service_transition,
    transition_bound,
)
from ds_auth.errors import PermissionDenied

DID = "did:web:rec.example.org"
IR = "svc-ds-identity-registry"
CONNECTOR = "svc-ds-connector"


def _service(client: str, *, aud=None, sub: str = DID, scope: str = "x") -> Principal:
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + 300,
        "sub": sub,
        "azp": client,
        "preferred_username": f"service-account-{client}",
        "scope": scope,
    }
    if aud is not None:
        claims["aud"] = aud
    return Principal.from_claims(claims)


def _person(aud=None) -> Principal:
    now = int(time.time())
    claims = {"iat": now, "exp": now + 300, "sub": "u1", "email": "p@example.test"}
    if aud is not None:
        claims["aud"] = aud
    return Principal.from_claims(claims)


def _request(audience: str | None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(oidc_config=SimpleNamespace(audience=audience))
        )
    )


def test_own_audience_is_the_configured_one():
    assert own_audience(_request(IR)) == IR
    assert own_audience(_request(None)) is None
    assert own_audience(SimpleNamespace()) is None


def test_a_token_minted_for_this_service_passes():
    check_audience_bound(_service("svc-ds-collector-x", aud=IR), IR)
    check_audience_bound(_service("svc-ds-connector-x", aud=[IR, CONNECTOR]), IR)


@pytest.mark.parametrize("aud", [None, CONNECTOR, ["account"]])
def test_a_service_token_without_this_audience_is_refused(aud):
    with pytest.raises(PermissionDenied, match="not minted for this service"):
        check_audience_bound(_service("svc-ds-onboarding", aud=aud), IR)


def test_a_collector_token_minted_for_two_services_is_refused():
    """Asked for two acts at once, so it is good at the other receiver too."""
    with pytest.raises(PermissionDenied, match="one act at a time"):
        check_audience_bound(_service("svc-ds-collector-x", aud=[IR, CONNECTOR]), IR)


def test_a_collector_token_may_carry_a_non_ds_audience():
    """Keycloak's realm defaults may add `account`; it reaches no ds service."""
    check_audience_bound(_service("svc-ds-collector-x", aud=[IR, "account"]), IR)


def test_a_receiver_without_an_audience_refuses():
    with pytest.raises(PermissionDenied, match="no audience configured"):
        check_audience_bound(_service("svc-ds-collector-x", aud=IR), None)


def test_a_person_is_not_audience_checked_here():
    check_audience_bound(_person(), IR)


async def test_the_perimeter_checks_then_delegates():
    calls = []

    def inner(principal, request):
        calls.append(principal.client_id)
        return False

    perimeter = audience_bound(inner)
    assert (
        await perimeter(_service("svc-ds-collector-x", aud=IR), _request(IR)) is False
    )
    assert calls == ["svc-ds-collector-x"]
    with pytest.raises(PermissionDenied):
        await perimeter(_service("svc-ds-collector-x", aud=CONNECTOR), _request(IR))
    assert len(calls) == 1


def test_a_plain_service_is_refused_outside_dev(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    with pytest.raises(PermissionDenied, match="svc-ds-collector"):
        plain_service_transition(_service("svc-ds-onboarding", aud=IR), "issuance")


def test_a_plain_service_is_accepted_in_dev_and_logged(monkeypatch, caplog):
    monkeypatch.setenv("DS_ENV", "dev")
    with caplog.at_level("WARNING"):
        plain_service_transition(_service("svc-ds-onboarding", aud=IR), "issuance")
    assert "svc-ds-onboarding" in caplog.text
    assert "TRANSITION" in caplog.text


@pytest.mark.parametrize("client", ["svc-ds-collector-x", "svc-ds-connector-x"])
def test_an_organisation_is_not_a_plain_service(monkeypatch, client):
    monkeypatch.setenv("DS_ENV", "production")
    plain_service_transition(_service(client, aud=IR), "issuance")


def test_a_person_is_not_a_plain_service(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    plain_service_transition(_person(), "issuance")


async def test_the_transition_perimeter_checks_both(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    perimeter = transition_bound("issuance")
    assert await perimeter(_service("svc-ds-collector-x", aud=IR), _request(IR))
    with pytest.raises(PermissionDenied, match="names no organisation"):
        await perimeter(_service("svc-ds-onboarding", aud=IR), _request(IR))
    with pytest.raises(PermissionDenied, match="not minted"):
        await perimeter(_service("svc-ds-collector-x", aud=CONNECTOR), _request(IR))
