"""Consent collectors — plan `a-collector-registers-consent-at-the-holder`.

The relation "organisation X is an accepted consent collector for holder Y".
The anchor's admin API manages it on `identity-registry.collectors.write`; the
holder's connector asks `GET /consent-collectors/check` on `identity-registry.read`
and learns, for one pair, whether to accept and whose members to check against.
"""

from __future__ import annotations

import pytest
from conftest import make_headers, register_enrolled

from identity_registry.db.models import Owner

HOLDER = "did:web:dso.example.org"
COLLECTOR = "did:web:rec.example.org"
OTHER = "did:web:other.example.org"
WRITE = make_headers("identity-registry.collectors.write")
READ = make_headers("identity-registry.read")


async def _owner(db, owner_id: str, did: str, status: str = "verified") -> None:
    db.add(
        Owner(
            id=owner_id,
            name=owner_id,
            did=did,
            aliases=[],
            status=status,
            verified_by="test" if status == "verified" else None,
        )
    )
    await db.commit()


@pytest.fixture
async def world(db_session):
    await register_enrolled(db_session, HOLDER, roles=["provider"])
    await _owner(db_session, "example-dso", HOLDER)
    await _owner(db_session, "example-rec", COLLECTOR)
    await _owner(db_session, "example-other", OTHER)
    return db_session


async def _check(client, holder=HOLDER, collector=COLLECTOR):
    r = await client.get(
        "/consent-collectors/check",
        params={"holder_did": holder, "collector_did": collector},
        headers=READ,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.rule("D-21")
@pytest.mark.asyncio
async def test_an_accepted_collector_is_accepted_and_named_by_its_owner(client, world):
    r = await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active"

    body = await _check(client)
    assert body["accepted"] is True
    # The organisation the connector checks the subject's membership against.
    assert body["collector_owner"] == "example-rec"


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_an_organisation_not_on_the_list_is_not_accepted(client, world):
    body = await _check(client, collector=OTHER)
    assert body["accepted"] is False
    assert body["collector_owner"] == "example-other"


@pytest.mark.asyncio
async def test_a_holder_always_collects_for_itself(client, world):
    body = await _check(client, collector=HOLDER)
    assert body["accepted"] is True
    assert body["collector_owner"] == "example-dso"


@pytest.mark.asyncio
async def test_the_self_pair_is_not_recorded(client, world):
    r = await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": HOLDER},
        headers=WRITE,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_the_holder_must_be_an_active_participant(client, world):
    r = await client.post(
        "/admin/consent-collectors",
        json={"holder_did": OTHER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    assert r.status_code == 422
    assert "not an active participant" in r.text


@pytest.mark.asyncio
async def test_the_collector_must_be_a_verified_organisation(client, world):
    r = await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": "did:web:nobody.example.org"},
        headers=WRITE,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_suspended_collector_is_not_accepted_although_listed(client, world):
    await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    from sqlalchemy import select

    owner = (
        await world.execute(select(Owner).where(Owner.id == "example-rec"))
    ).scalar_one()
    owner.status = "suspended"
    await world.commit()

    body = await _check(client)
    assert body["accepted"] is False
    assert "verified" in body["reason"]


@pytest.mark.asyncio
async def test_revocation_marks_and_keeps_the_row(client, world):
    await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    r = await client.post(
        "/admin/consent-collectors/revoke",
        json={
            "holder_did": HOLDER,
            "collector_did": COLLECTOR,
            "reason": "agreement ended",
        },
        headers=WRITE,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "revoked"
    assert (await _check(client))["accepted"] is False

    listed = (await client.get("/admin/consent-collectors", headers=WRITE)).json()
    assert [(row["status"], row["revocation_reason"]) for row in listed] == [
        ("revoked", "agreement ended")
    ]

    # Adding it again reactivates the same row.
    r = await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    assert r.json()["status"] == "active"
    assert r.json()["revoked_at"] is None
    assert (await _check(client))["accepted"] is True


@pytest.mark.asyncio
async def test_revoking_an_unknown_pair_is_a_404_and_needs_a_reason(client, world):
    r = await client.post(
        "/admin/consent-collectors/revoke",
        json={"holder_did": HOLDER, "collector_did": OTHER, "reason": "none"},
        headers=WRITE,
    )
    assert r.status_code == 404
    r = await client.post(
        "/admin/consent-collectors/revoke",
        json={"holder_did": HOLDER, "collector_did": OTHER, "reason": ""},
        headers=WRITE,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        (
            "POST",
            "/admin/consent-collectors",
            {"holder_did": HOLDER, "collector_did": COLLECTOR},
        ),
        (
            "POST",
            "/admin/consent-collectors/revoke",
            {"holder_did": HOLDER, "collector_did": COLLECTOR, "reason": "x-reason"},
        ),
        ("GET", "/admin/consent-collectors", None),
    ],
)
async def test_the_admin_surface_needs_the_collectors_grant(
    client, world, method, path, body
):
    # `identity-registry.read` is what a connector holds; it must not manage the
    # relation it is gated by.
    for headers in (READ, make_headers("identity-registry.organizations.write")):
        r = await client.request(method, path, json=body, headers=headers)
        assert r.status_code == 403, (headers, r.text)
    r = await client.request(
        method, path, json=body, headers=make_headers("identity-registry.admin")
    )
    assert r.status_code < 400 or r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_the_check_needs_a_read_grant(client, world):
    r = await client.get(
        "/consent-collectors/check",
        params={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=make_headers("identity-registry.collectors.write"),
    )
    assert r.status_code == 403
    r = await client.get(
        "/consent-collectors/check",
        params={"holder_did": HOLDER, "collector_did": COLLECTOR},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_write_tells_the_connectors_to_drop_their_cache(
    client, world, monkeypatch
):
    from identity_registry.api.v1 import consent_collectors as route

    calls: list[object] = []

    async def fake_invalidate(settings):
        calls.append(settings)

    monkeypatch.setattr(route, "invalidate_participant_caches", fake_invalidate)
    await client.post(
        "/admin/consent-collectors",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR},
        headers=WRITE,
    )
    await client.post(
        "/admin/consent-collectors/revoke",
        json={"holder_did": HOLDER, "collector_did": COLLECTOR, "reason": "ended"},
        headers=WRITE,
    )
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_two_owners_on_one_did_name_nobody(client, world):
    await _owner(world, "example-dup", COLLECTOR)
    body = await _check(client, collector=HOLDER)
    assert body["collector_owner"] == "example-dso"
    body = await _check(client)
    assert body["collector_owner"] is None
    assert body["accepted"] is False
