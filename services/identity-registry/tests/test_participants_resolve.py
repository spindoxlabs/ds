"""`GET /participants/resolve` — the non-admin participant lookup (`C-19`).

A consumer connector asks it before it dials a counterparty. The route must
answer that one question and disclose nothing the admin listing adds: no scopes,
no registration time, no inactive participants, and no way to tell a suspended
participant from an unknown one.
"""

from __future__ import annotations

import pytest
from conftest import make_headers, register_enrolled
from sqlalchemy import select

PROVIDER = "did:web:rec.example.org"
ADDRESS = "https://rec.example.org/protocol/2025-1"


async def _participant(db, did=PROVIDER, address=ADDRESS, *, active=True, roles=None):
    from identity_registry.db.models import Participant

    await register_enrolled(
        db, did, roles=roles or ["provider"], scopes=["dataspaces.query", "secret.x"]
    )
    row = (
        await db.execute(select(Participant).where(Participant.did == did))
    ).scalar_one()
    row.dsp_address = address
    row.active = active
    await db.commit()


@pytest.mark.rule("C-19")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", [{"did": PROVIDER}, {"dsp_address": ADDRESS}], ids=["did", "address"]
)
async def test_an_active_participant_resolves_by_either_key(client, db_session, params):
    await _participant(db_session)
    r = await client.get(
        "/participants/resolve",
        params=params,
        headers=make_headers("identity-registry.read"),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"did": PROVIDER, "dsp_address": ADDRESS, "roles": ["provider"]}


@pytest.mark.asyncio
async def test_it_discloses_nothing_the_question_does_not_need(client, db_session):
    await _participant(db_session)
    body = (
        await client.get(
            "/participants/resolve",
            params={"did": PROVIDER},
            headers=make_headers("identity-registry.read"),
        )
    ).json()
    assert set(body) == {"did", "dsp_address", "roles"}
    assert "secret.x" not in str(body)


@pytest.mark.rule("C-19")
@pytest.mark.asyncio
async def test_inactive_and_unknown_are_the_same_404(client, db_session):
    await _participant(db_session, active=False)
    headers = make_headers("identity-registry.read")
    suspended = await client.get(
        "/participants/resolve", params={"did": PROVIDER}, headers=headers
    )
    unknown = await client.get(
        "/participants/resolve",
        params={"did": "did:web:nobody.example.org"},
        headers=headers,
    )
    assert suspended.status_code == unknown.status_code == 404
    assert suspended.json() == unknown.json()


@pytest.mark.asyncio
async def test_an_address_two_participants_claim_resolves_to_neither(
    client, db_session
):
    await _participant(db_session)
    await _participant(db_session, did="did:web:other.example.org")
    r = await client.get(
        "/participants/resolve",
        params={"dsp_address": ADDRESS},
        headers=make_headers("identity-registry.read"),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{}, {"did": PROVIDER, "dsp_address": ADDRESS}, {"did": ""}],
    ids=["neither", "both", "empty"],
)
async def test_exactly_one_key_is_required(client, db_session, params):
    await _participant(db_session)
    r = await client.get(
        "/participants/resolve",
        params=params,
        headers=make_headers("identity-registry.read"),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope,status",
    [
        ("identity-registry.read", 200),
        ("identity-registry.admin", 200),
        ("identity-registry.membership.read", 403),
        ("identity-registry.organizations.read", 403),
        ("connector.consumer.read", 403),
    ],
)
async def test_the_read_scope_guards_it(client, db_session, scope, status):
    await _participant(db_session)
    r = await client.get(
        "/participants/resolve", params={"did": PROVIDER}, headers=make_headers(scope)
    )
    assert r.status_code == status


@pytest.mark.asyncio
async def test_no_token_is_401(client, db_session):
    r = await client.get("/participants/resolve", params={"did": PROVIDER})
    assert r.status_code == 401


def test_it_is_served_by_the_anchor_only():
    """The registry answers for the whole dataspace; a participant instance
    holds no participant registry to answer from."""
    from identity_registry.roles import PARTICIPANT, TRUST_ANCHOR, roles_for_path

    assert roles_for_path("/participants/resolve") == frozenset({TRUST_ANCHOR})
    assert PARTICIPANT not in roles_for_path("/participants/resolve")
