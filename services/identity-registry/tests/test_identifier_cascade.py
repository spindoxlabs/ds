"""Identity survives an identifier change; it does not survive a recycled one.

Three identifiers with three different jobs, and only one of them means "the same
human":

* `(realm, user_id)` — the **continuity key**. Stable within a realm.
* `username` — the **data-plane join**. The REC registry resolves a member by it,
  so it is load-bearing *and* mutable.
* `email` — a **bootstrap seed** for a first-time user, and the identifier that
  actually moves.

Resolution used to be email-only, and derived a fresh subject id whenever that
lookup missed. So an ordinary email change minted a *second* DID for the same
person: new keypair, new credentials, empty consent state — while the data plane
resolved **both** DIDs to the same username. A revocation against one left the
other disclosing. That is a consent-integrity failure, not a duplicate row.
"""
from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.db.models import Did, KeycloakMapping

RESOLVE = make_headers(scope="identity-registry.resolve")
ADMIN = make_headers(scope="identity-registry.admin")

REALM = "dataspaces"
USER_ID = "00000000-0000-4000-a000-000000000003"
DID = "did:web:rec.dataspaces.localhost:users:person-a"


async def _seed(db_session, **overrides) -> None:
    db_session.add(Did(did=DID, did_type="user"))
    fields = dict(
        did=DID,
        keycloak_realm=REALM,
        keycloak_user_id=USER_ID,
        username="person-a",
        email="person-a@example.test",
        subject_id=DID,
    )
    fields.update(overrides)
    db_session.add(KeycloakMapping(**fields))
    await db_session.commit()


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_the_continuity_key_wins_over_a_changed_email(client, db_session):
    """The scenario that used to mint a duplicate: same person, new address."""
    await _seed(db_session)
    r = await client.get(
        f"/users/resolve?realm={REALM}&user_id={USER_ID}"
        "&email=person-a-new@example.test&derive=true",
        headers=RESOLVE,
    )
    assert r.status_code == 200
    assert r.json()["did"] == DID, "a changed email must not mint a second identity"


@pytest.mark.asyncio
async def test_username_resolves_when_the_id_is_unknown(client, db_session):
    """The middle rung: no continuity key to hand, but the join key is known."""
    await _seed(db_session)
    r = await client.get("/users/resolve?username=person-a", headers=RESOLVE)
    assert r.status_code == 200
    assert r.json()["did"] == DID


@pytest.mark.asyncio
async def test_email_still_resolves_for_callers_that_have_only_that(client, db_session):
    """The funnel's case, and the reason the email rung stays."""
    await _seed(db_session)
    r = await client.get(
        "/users/resolve?email=person-a@example.test", headers=RESOLVE
    )
    assert r.status_code == 200
    assert r.json()["did"] == DID


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_a_recycled_identifier_is_quarantined(client, db_session):
    """A weaker identifier matching a row with a *different* stronger one.

    Two irreconcilable situations look identical from here — an account deleted and
    re-created (same human, new id) versus an address recycled to a different human
    — so this must not be reconciled. Auto-updating would hand one person's DID,
    credentials and consent history to somebody else.
    """
    await _seed(db_session)
    r = await client.get(
        "/users/resolve?realm=dataspaces&user_id=a-different-user"
        "&email=person-a@example.test",
        headers=RESOLVE,
    )
    assert r.status_code == 409
    assert "operator" in r.json()["detail"]


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_derivation_happens_only_when_every_rung_misses(client, db_session):
    """Deriving on an *email* miss is what minted duplicates. It may only happen
    when the person is genuinely unknown."""
    await _seed(db_session)
    r = await client.get(
        "/users/resolve?email=nobody@example.test&derive=true", headers=RESOLVE
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("did") is None
    assert body["subject_id"], "a first-time user still gets a derived subject id"


@pytest.mark.asyncio
async def test_derive_without_an_email_is_refused(client, db_session):
    """A subject id is seeded by the email and nothing else. Inventing one from a
    username would mint an identity for someone who may already have one."""
    r = await client.get(
        "/users/resolve?username=unknown-person&derive=true", headers=RESOLVE
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_resolve_needs_some_identifier(client):
    r = await client.get("/users/resolve", headers=RESOLVE)
    assert r.status_code == 422


# ── Binding ──────────────────────────────────────────────────────────────────


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_a_keycloak_user_cannot_be_bound_to_a_second_did(client, db_session):
    """The write-side half. Two DIDs for one person is the state the cascade
    exists to prevent, and there is no merge afterwards: provenance is append-only
    and consent rows key on a DID."""
    await _seed(db_session)
    other = "did:web:rec.dataspaces.localhost:users:person-a-again"
    db_session.add(Did(did=other, did_type="user"))
    await db_session.commit()

    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": other,
            "keycloak_realm": REALM,
            "keycloak_user_id": USER_ID,
            "email": "person-a@example.test",
        },
        headers=ADMIN,
    )
    assert r.status_code == 409
    assert DID in r.json()["detail"], "the operator needs to be told which DID holds it"


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_rebinding_the_same_did_updates_its_identifiers(client, db_session):
    """The ordinary case must stay ordinary: an email or username change updates
    the row and keeps the DID."""
    await _seed(db_session)
    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": DID,
            "keycloak_realm": REALM,
            "keycloak_user_id": USER_ID,
            "email": "person-a-new@example.test",
            "username": "person-a-renamed",
        },
        headers=ADMIN,
    )
    assert r.status_code == 200

    check = await client.get(
        f"/users/resolve?realm={REALM}&user_id={USER_ID}", headers=RESOLVE
    )
    assert check.json()["did"] == DID
