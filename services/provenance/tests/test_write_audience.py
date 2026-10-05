"""A provenance write is audience-bound, and an organisation's act (ADR-0026).

`provenance.write` moved from the plain onboarding client to each organisation's
collector client, and it adds `aud=svc-ds-provenance`. So a service token not
minted for this service is refused, a collector token minted for another ds
service too is refused, and a plain service token is accepted only under
`DS_ENV=dev`. A connector writes with its organisation client's default token,
which names this audience, and is unaffected.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest

PROV = "svc-ds-provenance"
ENTITY = {
    "iri": "https://rec.example.org/datasets/meters_15m",
    "label": "Meter Readings 15m",
    "energy_type": "ConsumptionMeasurement",
}


def _token(client_id: str, *, aud=PROV, sub="did:web:rec.example.org") -> dict:
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + 300,
        "sub": sub,
        "azp": client_id,
        "preferred_username": f"service-account-{client_id}",
        "scope": "provenance.write",
    }
    if aud is not None:
        claims["aud"] = aud
    return {
        "Authorization": f"Bearer {pyjwt.encode(claims, 'k' * 32, algorithm='HS256')}"
    }


async def _write(client, headers):
    return await client.post("/prov/entities", json=ENTITY, headers=headers)


@pytest.mark.parametrize(
    "client_id", ["svc-ds-collector-example-rec", "svc-ds-connector-example-rec"]
)
async def test_an_organisation_writes_in_production(client, monkeypatch, client_id):
    monkeypatch.setenv("DS_ENV", "production")
    r = await _write(client, _token(client_id))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("aud", [None, "svc-ds-connector"])
async def test_a_token_not_minted_for_provenance_is_refused(client, aud):
    r = await _write(client, _token("svc-ds-collector-example-rec", aud=aud))
    assert r.status_code == 403, r.text
    assert "not minted for this service" in r.text


async def test_a_collector_token_minted_for_two_services_is_refused(client):
    r = await _write(
        client, _token("svc-ds-collector-example-rec", aud=[PROV, "svc-ds-connector"])
    )
    assert r.status_code == 403, r.text


async def test_a_plain_service_writes_only_under_dev(client, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    r = await _write(client, _token("svc-ds-onboarding", sub="svc-uuid"))
    assert r.status_code == 403, r.text
    assert "svc-ds-collector" in r.text
    monkeypatch.setenv("DS_ENV", "dev")
    r = await _write(client, _token("svc-ds-onboarding", sub="svc-uuid"))
    assert r.status_code == 201, r.text
