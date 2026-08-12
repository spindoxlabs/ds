"""Invite-gated organisation intake.

The public route is the only unauthenticated write on a service that holds every
private key, so its refusals matter more than its successes.
"""
from __future__ import annotations

import pytest
from conftest import make_headers

WRITE = make_headers(scope="identity-registry.organizations.write")
READ = make_headers(scope="identity-registry.organizations.read")


async def issue(client, **body) -> str:
    r = await client.post("/admin/onboarding/invites", headers=WRITE, json=body or {})
    assert r.status_code == 201, r.text
    return r.json()["code"]


def application(code: str, alias: str = "acme-energy") -> dict:
    return {
        "invite_code": code,
        "alias": alias,
        "legal_name": "Acme Energy",
        "roles": ["consumer"],
        "evidence_ref": "ticket-4711",
    }


# ── issuing ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_code_is_returned_once_and_never_again(client):
    code = await issue(client, label="acme")

    listed = await client.get("/admin/onboarding/invites", headers=READ)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    # Only the hash is stored, so the code cannot reappear in any projection.
    assert "code" not in rows[0]
    assert code not in listed.text


@pytest.mark.asyncio
async def test_issuing_needs_write_and_listing_needs_read(client):
    assert (await client.post("/admin/onboarding/invites", headers=READ, json={})).status_code == 403
    assert (await client.get("/admin/onboarding/invites", headers=make_headers(scope="nope"))).status_code == 403


# ── redeeming ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_code_files_an_application(client):
    code = await issue(client)

    r = await client.post("/onboarding/applications", json=application(code))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["alias"] == "acme-energy"
    assert body["status"] == "pending"
    # The acknowledgement is not the record: an applicant cannot read back what an
    # operator will later judge.
    assert set(body) == {"id", "alias", "status"}

    # …and it lands in the operator's queue.
    queue = await client.get("/admin/organizations/applications", headers=READ)
    assert [a["alias"] for a in queue.json()] == ["acme-energy"]


@pytest.mark.rule("P-4")
@pytest.mark.asyncio
async def test_a_code_works_exactly_once(client):
    code = await issue(client)
    assert (await client.post("/onboarding/applications", json=application(code))).status_code == 201

    again = await client.post("/onboarding/applications", json=application(code, alias="acme-two"))
    assert again.status_code == 403


@pytest.mark.asyncio
async def test_redemption_is_recorded_against_the_invite(client):
    code = await issue(client)
    created = await client.post("/onboarding/applications", json=application(code))

    row = (await client.get("/admin/onboarding/invites", headers=READ)).json()[0]
    assert row["redeemed_at"] is not None
    # Spent rather than deleted, so an operator can still see what it produced.
    assert row["application_id"] == created.json()["id"]


@pytest.mark.asyncio
async def test_no_code_and_a_wrong_code_are_refused_identically(client):
    await issue(client)
    wrong = await client.post("/onboarding/applications", json=application("not-a-real-code"))
    assert wrong.status_code == 403
    # Same answer either way: the route must not reveal which codes exist.
    assert wrong.json()["detail"] == "Invalid or already used invite code"


@pytest.mark.asyncio
async def test_expired_code_is_refused(client, db_session):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from identity_registry.db.models import OnboardingInvite

    code = await issue(client)
    invite = (await db_session.execute(select(OnboardingInvite))).scalar_one()
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    assert (await client.post("/onboarding/applications", json=application(code))).status_code == 403


@pytest.mark.rule("P-4")
@pytest.mark.asyncio
async def test_duplicate_alias_is_refused(client):
    first, second = await issue(client), await issue(client)
    assert (await client.post("/onboarding/applications", json=application(first))).status_code == 201

    clash = await client.post("/onboarding/applications", json=application(second))
    assert clash.status_code == 409


@pytest.mark.rule("P-1")
@pytest.mark.asyncio
async def test_application_is_pending_and_grants_nothing(client):
    """Filing an application must not create an owner or a participant."""
    code = await issue(client)
    await client.post("/onboarding/applications", json=application(code))

    owners = await client.get("/admin/owners", headers=READ)
    assert owners.json() == []
