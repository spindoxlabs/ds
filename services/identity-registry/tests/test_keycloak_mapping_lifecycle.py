"""A Keycloak mapping can be removed, and a DID deletion says it left one.

**The defect.** `DELETE /admin/dids/{did}` deactivates the DID and revokes its
credentials. The `keycloak_mappings` row is untouched, and until now no route
removed one — so every member teardown left an orphan behind. Measured in a
deployment: over 19 teardowns the consistency check's orphan note went **3 → 25**.
It is a *note* rather than a failure, which is why it went unnoticed for 19 runs.

**Why an orphan is not cosmetic.** `POST /admin/keycloak/sync` answers **409**
when the Keycloak user is already bound to a different DID — *"Rebinding is an
explicit operator act, never a side effect of a sync"*. So a surviving mapping
does not merely sit there: it **permanently refuses re-provisioning of that
Keycloak user**, and the only way out was writing into the anchor's database by
hand, which the agent that found this correctly declined to do.
"""

from __future__ import annotations

import pytest
from conftest import make_headers, register_did

HEADERS = make_headers()

DID = "did:web:rec.example.org:users:member-001"
OTHER_DID = "did:web:rec.example.org:users:member-002"
REALM = "example-realm"
KC_USER = "11111111-2222-3333-4444-555555555555"


async def _sync(client, did: str, *, user_id: str = KC_USER):
    return await client.post(
        "/admin/keycloak/sync",
        json={
            "did": did,
            "keycloak_realm": REALM,
            "keycloak_user_id": user_id,
            "email": "member-001@example.org",
            "username": "member-001@example.org",
        },
        headers=HEADERS,
    )


async def _mapping(client, did: str):
    """The mapping as `GET /users/resolve` sees it, or `None`."""
    r = await client.get(
        "/users/resolve",
        params={"realm": REALM, "user_id": KC_USER},
        headers=make_headers(scope="identity-registry.resolve"),
    )
    return r.json() if r.status_code == 200 else None


# ── The harm, pinned ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_orphan_mapping_refuses_the_next_binding(client, db_session):
    """Passes before and after: it is the *reason* for the route, not the fix.

    Deactivating the DID leaves the binding, and the binding is what a re-run
    collides with. Nothing below can be read as an improvement unless this is
    true first.
    """
    await register_did(db_session, DID)
    await register_did(db_session, OTHER_DID)
    assert (await _sync(client, DID)).status_code == 200

    assert (await client.delete(f"/admin/dids/{DID}", headers=HEADERS)).status_code in (
        200,
        204,
    )

    clash = await _sync(client, OTHER_DID)
    assert clash.status_code == 409
    assert DID in clash.text


# ── The route ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_mapping_can_be_deleted(client, db_session):
    await register_did(db_session, DID)
    assert (await _sync(client, DID)).status_code == 200
    assert await _mapping(client, DID) is not None

    r = await client.delete(f"/admin/keycloak/mappings/{DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["did"] == DID

    assert await _mapping(client, DID) is None


@pytest.mark.asyncio
async def test_an_orphan_left_by_an_earlier_teardown_can_be_cleared(client, db_session):
    """**The 22 rows standing in the deployment right now are exactly this.**

    Their DID was deactivated first and the mapping outlived it, so the route
    must not require an active DID — or a live one at all. It answers on the
    mapping, and reports the DID's state rather than demanding it.
    """
    await register_did(db_session, DID)
    await register_did(db_session, OTHER_DID)
    await _sync(client, DID)
    await client.delete(f"/admin/dids/{DID}", headers=HEADERS)

    r = await client.delete(f"/admin/keycloak/mappings/{DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    # Said aloud, because an operator clearing an orphan should be told the
    # identity behind it was already gone — and one clearing a *live* binding
    # should be told that too.
    assert r.json()["did_active"] is False

    # And the point of clearing it: the Keycloak user can be bound again.
    assert (await _sync(client, OTHER_DID)).status_code == 200


@pytest.mark.asyncio
async def test_deleting_a_live_binding_says_the_did_is_still_active(client, db_session):
    await register_did(db_session, DID)
    await _sync(client, DID)

    r = await client.delete(f"/admin/keycloak/mappings/{DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["did_active"] is True


@pytest.mark.asyncio
async def test_deleting_a_mapping_that_is_not_there_is_404(client, db_session):
    await register_did(db_session, DID)
    r = await client.delete(f"/admin/keycloak/mappings/{DID}", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_the_mapping_delete_needs_the_admin_scope(client, db_session):
    await register_did(db_session, DID)
    await _sync(client, DID)
    r = await client.delete(
        f"/admin/keycloak/mappings/{DID}",
        headers=make_headers(scope="identity-registry.read"),
    )
    assert r.status_code == 403


# ── The DID deletion stops being silent ──────────────────────────────────────


@pytest.mark.asyncio
async def test_the_did_deletion_names_what_it_left_standing(client, db_session):
    """A delete that does not erase has to say so.

    This route answered `204` and left a mapping that would refuse the next
    binding. The caller had no way to learn that from the response, and a
    deployment accumulated 22 of them before anybody looked.
    """
    await register_did(db_session, DID)
    await _sync(client, DID)

    r = await client.delete(f"/admin/dids/{DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deactivated"] is True
    assert body["keycloak_mapping_retained"] is True
    # Not a hint to go looking — the call to make.
    assert "/admin/keycloak/mappings/" in body["residue"]


@pytest.mark.asyncio
async def test_the_did_deletion_reports_no_residue_when_there_is_none(
    client, db_session
):
    await register_did(db_session, DID)
    r = await client.delete(f"/admin/dids/{DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["keycloak_mapping_retained"] is False
    assert r.json()["residue"] is None
