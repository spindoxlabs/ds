"""The signed status list lives a day, and what the route serves outlives a
verifier's cache.

A verifier keeps the list it fetched (ds-auth 900 s, EDC's revocation cache
15 min), so the list is signed for `status_list_jwt_ttl_seconds` (a day) and a
cached copy is signed again once half of that has passed. Ordinary credentials
keep their year.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from test_status_list import _bootstrap_trust_anchor

from identity_registry.api.v1 import public
from identity_registry.config import Settings
from identity_registry.db.models import StatusList
from identity_registry.services.crypto import generate_key_pair
from identity_registry.services.vc import (
    build_data_subject_credential,
    sign_credential,
)

DAY = 86400


def _claims(jws: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(jws.split(".")[1] + "==="))


@pytest.fixture(autouse=True)
def _empty_signed_list_cache(monkeypatch):
    monkeypatch.setattr(
        public,
        "_signed_lists",
        public._SignedListCache(ttl=public._SIGNED_LIST_TTL_SECONDS, size=32),
    )


async def _a_list(db_session) -> None:
    await _bootstrap_trust_anchor(db_session)
    db_session.add(StatusList(id="1", bitstring=bytes(16384), purpose="revocation"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_the_list_is_signed_for_a_day(client, db_session):
    await _a_list(db_session)

    r = await client.get("/status/1", headers={"Accept": "application/vc+jwt"})
    assert r.status_code == 200
    claims = _claims(r.text)

    assert abs(claims["exp"] - (claims["nbf"] + DAY)) <= 2
    assert abs(claims["exp"] - (time.time() + DAY)) <= 5
    # The same date inside the credential, which is what EDC reads.
    until = datetime.strptime(claims["vc"]["expirationDate"], "%Y-%m-%dT%H:%M:%SZ")
    assert int(until.replace(tzinfo=UTC).timestamp()) == claims["exp"]


@pytest.mark.asyncio
async def test_the_unsigned_form_states_the_same_lifetime(client, db_session):
    await _a_list(db_session)

    r = await client.get("/status/1", headers={"Accept": "application/json"})
    assert r.status_code == 200
    until = datetime.strptime(r.json()["expirationDate"], "%Y-%m-%dT%H:%M:%SZ")
    assert abs(until.replace(tzinfo=UTC).timestamp() - (time.time() + DAY)) <= 5


@pytest.mark.asyncio
async def test_an_unchanged_list_is_served_from_cache(client, db_session):
    await _a_list(db_session)

    first = await client.get("/status/1")
    second = await client.get("/status/1")
    assert first.text == second.text


@pytest.mark.asyncio
async def test_a_cached_list_past_half_its_life_is_signed_again(
    client, db_session, monkeypatch
):
    await _a_list(db_session)
    first = await client.get("/status/1")
    first_exp = _claims(first.text)["exp"]

    # Twelve hours and a minute later: the cached copy has less than half of
    # its day left. (Only the wall clock moves; the cache's own monotonic
    # ageing does not, so this is the lifetime rule alone.)
    later = time.time() + DAY / 2 + 60
    monkeypatch.setattr(time, "time", lambda: later)

    second = await client.get("/status/1")
    assert second.status_code == 200
    assert second.text != first.text
    claims = _claims(second.text)
    assert claims["exp"] > first_exp
    assert claims["exp"] - later >= DAY - 5


def test_ordinary_credentials_keep_a_year():
    key = generate_key_pair("did:web:ta.example")
    vc = build_data_subject_credential(
        issuer_did="did:web:ta.example",
        subject_did="did:web:rec.example.org:users:ex-00001",
        role="DataSubject",
        credentials_context_url="http://test/contexts/credentials.jsonld",
        dataspace_uri="urn:dataspace:test",
        status_list_credential_url="http://ta.example/status/1",
        suspension_list_credential_url="http://ta.example/status/2",
        status_list_index=1,
    )
    vc.pop("expirationDate")
    claims = _claims(sign_credential(vc, key.private_jwk, key.kid)["proof"]["jws"])
    assert abs(claims["exp"] - (claims["nbf"] + 365 * DAY)) <= 2


@pytest.mark.parametrize("value", [0, -1, 900, 1799])
def test_a_lifetime_below_the_floor_is_refused(value):
    """Half the lifetime is when a cached copy is re-signed, and it must still
    outlast a verifier's 15-minute cache — so nothing under 1800 s loads."""
    with pytest.raises(ValidationError):
        Settings(status_list_jwt_ttl_seconds=value)


def test_a_lifetime_below_the_floor_is_refused_from_the_environment(monkeypatch):
    monkeypatch.setenv("IDENTITY_REGISTRY_STATUS_LIST_JWT_TTL_SECONDS", "900")
    with pytest.raises(ValidationError):
        Settings()


def test_the_floor_itself_loads():
    settings = Settings(status_list_jwt_ttl_seconds=1800)
    assert settings.status_list_jwt_ttl_seconds == 1800
