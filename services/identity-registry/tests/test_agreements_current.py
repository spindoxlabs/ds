"""GET /agreements/current — the connector's circle input.

This endpoint decides whether a requesting party is a **processor** of an
offer's controller (disclosed under a DPA, never re-asked) or an independent
controller (a new consent question for the data subject). Answering "processor"
when the organisation never signed as one would suppress a consent request that
GDPR Art. 4(11) requires, so every path that cannot prove a capacity must
answer 404 and let the caller fail closed.
"""
from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.db.models import Owner, Participant

PARTICIPANT_DID = "did:web:partner.dataspaces.localhost"


async def _seed_owner(db_session, **overrides) -> Owner:
    defaults = dict(
        id="partner-org",
        type="organization",
        name="Partner Organisation",
        did=PARTICIPANT_DID,
        aliases=[],
        status="verified",
        agreement_id="dataspace-participation",
        agreement_version="1.0",
        agreement_capacity="processor",
    )
    defaults.update(overrides)
    owner = Owner(**defaults)
    db_session.add(owner)
    await db_session.commit()
    return owner


# ── Authorisation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_a_token(client):
    r = await client.get(f"/agreements/current?participant_did={PARTICIPANT_DID}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_scope_is_forbidden(client):
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(scope="some.other.scope"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_resolve_scope_alone_does_not_grant(client):
    """`identity-registry.resolve` is the email-lookup grant, not a read grant."""
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(scope="identity-registry.resolve"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope", ["identity-registry.read", "identity-registry.admin"]
)
async def test_read_and_admin_scopes_are_accepted(client, db_session, scope):
    await _seed_owner(db_session)
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(scope=scope),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_participant_did_is_required(client):
    r = await client.get("/agreements/current", headers=make_headers())
    assert r.status_code == 422


# ── The answer ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_capacity_for_a_signed_owner(client, db_session):
    await _seed_owner(db_session)
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capacity"] == "processor"
    assert body["owner_alias"] == "partner-org"
    assert body["agreement_id"] == "dataspace-participation"
    assert body["version"] == "1.0"
    assert body["participant_did"] == PARTICIPANT_DID


@pytest.mark.asyncio
async def test_resolves_via_participant_alias_when_owner_has_no_did(client, db_session):
    """An owner and its participant may have been seeded separately.

    Without the alias fallback such a deployment reports "no agreement" for a
    participant that has one, and every processor silently becomes an
    independent controller."""
    db_session.add(
        Participant(did=PARTICIPANT_DID, roles=["consumer"], allowed_scopes=[], active=True)
    )
    await _seed_owner(db_session, did=None, aliases=[PARTICIPANT_DID])
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(),
    )
    assert r.status_code == 200
    assert r.json()["capacity"] == "processor"


# ── Fail-closed paths ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_participant_is_not_found(client):
    r = await client.get(
        "/agreements/current?participant_did=did:web:nobody.example",
        headers=make_headers(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_owner_without_an_accepted_agreement_is_not_found(client, db_session):
    """No agreement means no provable capacity — never a null one."""
    await _seed_owner(db_session, agreement_id=None, agreement_capacity=None)
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "suspended", "revoked"])
async def test_owner_not_verified_is_not_found(client, db_session, status):
    """A suspended organisation must lose its circle membership immediately.

    Otherwise suspension revokes the credential but leaves the party still
    treated as a disclosed processor, which is the case suspension exists for."""
    await _seed_owner(db_session, status=status)
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_current_is_not_shadowed_by_the_agreement_id_route(client, db_session):
    """`/agreements/current` must not be read as agreement id "current".

    That route returns a list; this one returns an object. If ordering
    regressed, a caller reading `.capacity` would get None and treat every
    processor as an independent controller."""
    await _seed_owner(db_session)
    r = await client.get(
        f"/agreements/current?participant_did={PARTICIPANT_DID}",
        headers=make_headers(),
    )
    assert isinstance(r.json(), dict)
