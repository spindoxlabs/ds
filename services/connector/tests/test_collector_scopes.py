"""One audience per scope, the collector client, and the read-back's own scope.

ADR-0026. What these pin at the connector:

* the consent write and its read-backs are separate scopes — a write token does
  not read back, a read token does not write;
* the audience-bound routes refuse a service token not minted for this
  connector (no `aud`), and a collector token minted for another ds service too;
* an organisation's **collector client** (`svc-ds-collector-<alias>`) is the
  organisation: it registers consent where its connector client could;
* it is never the connector: no publish, no holder key list, no consumer route;
* the grants moved from the plain onboarding client (the offer audience read,
  disclosure records) are refused to a plain service token outside `DS_ENV=dev`,
  and an organisation reads the audience only where it is accepted.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.registry.participants import CollectorAnswer
from connector.services.membership_check import Membership
from tests import _claims, make_headers

HOLDER = get_settings().participant_context_id
COLLECTOR = "did:web:collector.example.org"
STRANGER = "did:web:stranger.example.org"
MEMBER = "did:web:collector.example.org:users:member-001"
CONNECTOR = "svc-ds-connector"
IR = "svc-ds-identity-registry"

PROVISION = "connector.consent.provision"
READ = "connector.consent.collector.read"
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}


def token(
    scopes: str,
    *,
    kind: str = "collector",
    context: str = COLLECTOR,
    alias: str = "example-coll",
    aud: object = CONNECTOR,
) -> dict:
    client = f"svc-ds-{kind}-{alias}"
    claims = _claims(
        sub=context,
        azp=client,
        preferred_username=f"service-account-{client}",
        scope=scopes,
    )
    if aud is not None:
        claims["aud"] = aud
    return {
        "Authorization": f"Bearer {pyjwt.encode(claims, 'secret', algorithm='HS256')}"
    }


def plain(scopes: str, aud: object = CONNECTOR) -> dict:
    claims = _claims(
        sub="svc-uuid",
        azp="svc-ds-onboarding",
        preferred_username="service-account-svc-ds-onboarding",
        scope=scopes,
        aud=aud,
    )
    return {
        "Authorization": f"Bearer {pyjwt.encode(claims, 'secret', algorithm='HS256')}"
    }


@pytest.fixture(autouse=True)
def _state(client):
    """Dependencies a refused request still resolves before its guard refuses."""
    state = client._transport.app.state
    for name in ("notifier", "provider_edc", "consumer_edc", "registry"):
        if not hasattr(state, name):
            setattr(state, name, None)


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    async def _member(_url, *, user_did, organization_alias, token_provider=None):
        return Membership.MEMBER

    async def _answer(_request, holder_did, collector_did):
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        if collector_did == COLLECTOR:
            return CollectorAnswer(True, "example-coll", "an accepted collector")
        return CollectorAnswer(False, "example-other", "not an accepted collector")

    monkeypatch.setattr(consent_route, "check_subject_membership", _member)
    monkeypatch.setattr(consent_route, "check_collector", _answer)


async def _write(client, headers):
    return await client.post(
        "/consent/admin/shares",
        headers=headers,
        json={
            "subject_id": MEMBER,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": EVIDENCE,
            "decided_by": "subject",
        },
    )


async def _read_back(client, headers):
    return await client.get(
        "/consent/admin/subject-shares", params={"subject_id": MEMBER}, headers=headers
    )


# ── the write and the read-back ──────────────────────────────────────────────


async def test_a_collector_client_registers_and_reads_back_with_two_tokens(client):
    """The collector client is the organisation (was: a plain service, 403)."""
    r = await _write(client, token(PROVISION))
    assert r.status_code == 200, r.text
    assert r.json()[0]["collector"] == COLLECTOR
    r = await _read_back(client, token(READ))
    assert r.status_code == 200, r.text
    assert [s["status"] for s in r.json()] == ["granted"]


async def test_the_write_grant_does_not_read_back(client):
    r = await _read_back(client, token(PROVISION))
    assert r.status_code == 403, r.text
    r = await client.get(
        "/consent/admin/decisions",
        params={"offer_id": "test-flexibility"},
        headers=token(PROVISION),
    )
    assert r.status_code == 403, r.text


async def test_the_read_grant_does_not_write(client):
    r = await _write(client, token(READ))
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("kind", ["collector", "connector"])
async def test_a_write_token_not_minted_for_this_connector_is_refused(client, kind):
    """Optional scopes do not stop replay; the audience does."""
    for aud in (None, IR):
        r = await _write(client, token(PROVISION, kind=kind, aud=aud))
        assert r.status_code == 403, r.text
        assert "not minted for this service" in r.text


async def test_a_collector_token_minted_for_two_services_is_refused(client):
    r = await _write(client, token(PROVISION, aud=[CONNECTOR, IR]))
    assert r.status_code == 403, r.text
    assert "one act at a time" in r.text


async def test_the_consent_request_route_is_audience_bound_too(client):
    r = await client.post(
        "/consent/request",
        headers=token(PROVISION, aud=None),
        json={
            "subject_ids": [MEMBER],
            "consumer_id": "did:web:consumer.example.org",
            "dataset_id": "x",
            "purpose": "y",
        },
    )
    assert r.status_code == 403, r.text


# ── a collector is not the connector ─────────────────────────────────────────


async def test_a_collector_client_never_publishes(client):
    headers = token("connector.provider.write", context=HOLDER, alias="example-org")
    r = await client.post("/provider/sync", headers=headers, json={})
    assert r.status_code == 403, r.text


async def test_a_publish_token_not_minted_for_this_connector_is_refused(client):
    headers = token(
        "connector.provider.write", kind="connector", context=HOLDER, aud=None
    )
    r = await client.post("/provider/sync", headers=headers, json={})
    assert r.status_code == 403, r.text
    assert "not minted for this service" in r.text


async def test_a_collector_client_does_not_read_the_holders_keys(client):
    headers = token(
        "connector.consent.holder.read", context=HOLDER, alias="example-org"
    )
    r = await client.get(
        "/consent/admin/holder/keys",
        params={"offer_id": "test-flexibility"},
        headers=headers,
    )
    assert r.status_code == 403, r.text


# ── the grants moved from the plain onboarding client ────────────────────────


async def _audience(client, headers):
    return await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": "did:web:c.example.org"},
        headers=headers,
    )


async def test_a_plain_service_reads_the_audience_only_under_dev(client, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    r = await _audience(client, plain("connector.consent.audience"))
    assert r.status_code == 403, r.text
    assert "svc-ds-collector" in r.text
    monkeypatch.setenv("DS_ENV", "dev")
    r = await _audience(client, plain("connector.consent.audience"))
    assert r.status_code != 403, r.text


async def test_an_organisation_reads_the_audience_only_where_accepted(client):
    r = await _audience(client, token("connector.consent.audience"))
    assert r.status_code != 403, r.text
    stranger = token(
        "connector.consent.audience", context=STRANGER, alias="example-other"
    )
    r = await _audience(client, stranger)
    assert r.status_code == 403, r.text
    assert "not an accepted consent collector" in r.text


async def test_a_plain_service_records_a_disclosure_only_under_dev(client, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    r = await client.post(
        "/admin/disclosure",
        headers=plain("connector.disclosure.record"),
        json={"offer_id": "test-flexibility", "recipient_ref": "did:web:r.example.org"},
    )
    assert r.status_code == 403, r.text
    stranger = token(
        "connector.disclosure.record", context=STRANGER, alias="example-other"
    )
    r = await client.post(
        "/admin/disclosure",
        headers=stranger,
        json={"offer_id": "test-flexibility", "recipient_ref": "did:web:r.example.org"},
    )
    assert r.status_code == 403, r.text


async def test_the_old_shape_plain_service_token_is_still_refused_its_write(client):
    """`svc-ds-onboarding` never wrote consent; it does not start now."""
    r = await _write(client, make_headers(PROVISION))
    assert r.status_code == 403, r.text
