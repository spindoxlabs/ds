"""A person released by one organisation joins another: a new DID, the login moves.

ADR-0028. Two organisations here, the REC that onboarded the person first
(`example-rec`) and a second one (`example-dso` stands in for the next
community). The rules pinned:

* **a DID is reused only while it holds a credential not revoked** — a second
  role (dual-role person) still shares it; a released person is issued a new DID
  in the issuing organisation's namespace, and a spent DID is never revived;
* **the login moves with the collector's sync** once the old DID holds nothing
  live and the new DID is the caller's member. The old binding stays, released,
  as history, and nothing resolves it;
* **R35's sweep then retires the old DID and only it.**
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import CUSTODIAN_DID, register_custodian
from sqlalchemy import select
from test_keycloak_sync_collector import (  # noqa: F401
    ADMIN,
    CRED,
    DSO_DID,
    REALM,
    USER,
    _sync,
    dso,
    rec,
    seeded,
)
from test_suspended_organisation_cleanup import cli_database  # noqa: F401
from typer.testing import CliRunner

from identity_registry.config import Settings
from identity_registry.db.models import KeycloakMapping
from identity_registry.services import did_retirement

OLD_ID = "ex-00001"
#: What a caller re-onboarding the person sends: a new opaque id (`D-22c`).
NEW_ID = "ex-00002"
READ = {"Authorization": ADMIN["Authorization"]}


async def _issue(client, headers, linked, subject, role=None):
    body = {"subject_id": subject, "linked_participant_did": linked}
    if role:
        body["role"] = role
    return await client.post(
        "/admin/credentials/data-subject", json=body, headers=headers
    )


async def _release(client, issued):
    r = await client.delete(
        f"/admin/credentials/{issued['credentialId']}", headers=rec(CRED)
    )
    assert r.status_code == 204, r.text


@pytest.fixture
async def first(seeded, db_session):  # noqa: F811
    """The REC onboarded the person and bound their login."""
    await register_custodian(db_session)
    await register_custodian(db_session, DSO_DID)
    r = await _issue(seeded, rec(CRED), CUSTODIAN_DID, OLD_ID)
    assert r.status_code == 201, r.text
    issued = r.json()
    r = await _sync(seeded, rec(), issued["subjectDid"])
    assert r.status_code == 200, r.text
    return issued


# ── the DID ──────────────────────────────────────────────────────────────────


async def test_a_released_person_is_issued_a_new_did_in_the_next_namespace(
    seeded,  # noqa: F811
    first,
):
    """Red before: the next organisation was issued the released DID, in the
    first one's namespace, which that one's sweep then retired under it."""
    await _release(seeded, first)
    r = await _issue(seeded, dso(CRED), DSO_DID, OLD_ID)
    assert r.status_code == 201, r.text
    assert r.json()["subjectDid"] == f"{DSO_DID}:users:{OLD_ID}"
    assert r.json()["subjectDid"] != first["subjectDid"]


async def test_a_live_did_is_still_shared_by_a_second_role(
    seeded,  # noqa: F811
    first,
):
    """A dual-role person keeps one DID while it is in use."""
    r = await _issue(seeded, dso(CRED), DSO_DID, OLD_ID, role="consumer")
    assert r.status_code == 201, r.text
    assert r.json()["subjectDid"] == first["subjectDid"]


async def test_a_spent_did_is_not_revived(seeded, first):  # noqa: F811
    """Joining the same organisation again under the same id would revive the
    retired identifier and append to its history: refused, naming neither."""
    await _release(seeded, first)
    r = await _issue(seeded, rec(CRED), CUSTODIAN_DID, OLD_ID)
    assert r.status_code == 409, r.text
    assert "new, opaque subject id" in r.text
    assert first["subjectDid"] not in r.text
    # A new id is a new DID.
    r = await _issue(seeded, rec(CRED), CUSTODIAN_DID, NEW_ID)
    assert r.status_code == 201, r.text
    assert r.json()["subjectDid"] == f"{CUSTODIAN_DID}:users:{NEW_ID}"


async def test_the_second_organisation_s_same_role_is_still_a_conflict(
    seeded,  # noqa: F811
    first,
):
    """Run (j)'s rule is unchanged while the first credential stands."""
    r = await _issue(seeded, dso(CRED), DSO_DID, OLD_ID)
    assert r.status_code == 409, r.text
    assert "linked to another organisation" in r.text


async def test_a_released_identity_has_nothing_to_transition(
    seeded,  # noqa: F811
    first,
):
    await _release(seeded, first)
    r = await seeded.post(
        "/admin/credentials/data-subject/transition",
        json={
            "subject_id": OLD_ID,
            "role": None,
            "to_role": "prosumer",
            "linked_participant_did": CUSTODIAN_DID,
        },
        headers=rec(CRED),
    )
    assert r.status_code == 404, r.text
    assert "No dataspace identity" in r.text


def test_ir_cli_does_not_revive_a_spent_did(cli_database, monkeypatch):  # noqa: F811
    from identity_registry.cli.main import app as cli

    monkeypatch.setenv("DS_ENV", "dev")
    did = f"{CUSTODIAN_DID}:users:{OLD_ID}"
    vc = {"credentialSubject": {"id": did, "linkedParticipant": CUSTODIAN_DID}}
    with sqlite3.connect(cli_database.removeprefix("sqlite+aiosqlite:///")) as conn:
        conn.execute(
            f"INSERT INTO dids (did, did_type, active) VALUES ('{did}', 'user', 1)"
        )
        conn.execute(
            "INSERT INTO credentials (id, credential_type, issuer_did, "
            "subject_did, credential_json, status) VALUES ('urn:uuid:first', "
            f"'DataSubjectCredential', 'did:web:ta', '{did}', ?, 'revoked')",
            (json.dumps(vc),),
        )
    r = CliRunner().invoke(
        cli,
        [
            "credential",
            "issue-data-subject",
            "--subject-id",
            OLD_ID,
            "--linked-participant-did",
            CUSTODIAN_DID,
        ],
    )
    assert r.exit_code == 1, r.output
    assert "new, opaque subject id" in r.output


# ── the login ────────────────────────────────────────────────────────────────


async def _mappings(db_session) -> dict[str, KeycloakMapping]:
    db_session.expire_all()
    rows = (await db_session.execute(select(KeycloakMapping))).scalars()
    return {m.did: m for m in rows}


async def test_the_login_moves_to_the_new_did_and_the_old_binding_is_kept(
    seeded,  # noqa: F811
    db_session,
    first,
):
    """Red before: the next organisation's sync was a 409 naming the old DID,
    and only the operator could unbind it, so the join failed closed."""
    old = first["subjectDid"]
    await _release(seeded, first)
    r = await _issue(seeded, dso(CRED), DSO_DID, NEW_ID)
    assert r.status_code == 201, r.text
    new = r.json()["subjectDid"]

    r = await _sync(seeded, dso(), new)
    assert r.status_code == 200, r.text
    # The old DID is not handed to the next organisation.
    assert old not in r.text

    rows = await _mappings(db_session)
    assert rows[old].released_at is not None
    assert rows[new].released_at is None
    assert (rows[new].keycloak_realm, rows[new].keycloak_user_id) == (REALM, USER)

    # Nothing resolves the released binding: not the data plane's DID → username…
    r = await seeded.post("/users/identities", json={"dids": [old, new]}, headers=READ)
    assert r.status_code == 200, r.text
    assert [i["did"] for i in r.json()] == [new]
    # …and the operator still reads it, as history.
    r = await seeded.get(f"/admin/keycloak/mapping/{old}", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["released_at"] is not None

    # A released binding is not revived, by the old organisation or the operator.
    assert (await _sync(seeded, rec(), old)).status_code == 403
    r = await _sync(seeded, ADMIN, old)
    assert r.status_code == 409, r.text
    assert "not revived" in r.text


async def test_the_login_does_not_move_while_the_old_did_is_live(
    seeded,  # noqa: F811
    db_session,
    first,
):
    """Still a person acting at the first organisation: two live identities for
    one login is the divergence the 409 exists for."""
    r = await _issue(seeded, dso(CRED), DSO_DID, NEW_ID)
    assert r.status_code == 201, r.text
    new = r.json()["subjectDid"]
    r = await _sync(seeded, dso(), new)
    assert r.status_code == 409, r.text
    assert "still holds a credential not revoked" in r.text
    rows = await _mappings(db_session)
    assert rows[first["subjectDid"]].released_at is None
    assert new not in rows


async def test_the_login_moves_only_to_the_caller_s_own_member(
    seeded,  # noqa: F811
    db_session,
    first,
):
    """The new DID is the second organisation's member: the first one cannot
    move the login there, released old DID or not (ADR-0026 amendment)."""
    await _release(seeded, first)
    r = await _issue(seeded, dso(CRED), DSO_DID, NEW_ID)
    new = r.json()["subjectDid"]
    r = await _sync(seeded, rec(), new)
    assert r.status_code == 403, r.text
    assert "own members" in r.text
    rows = await _mappings(db_session)
    assert rows[first["subjectDid"]].released_at is None


# ── the sweep ────────────────────────────────────────────────────────────────


async def test_the_sweep_retires_the_released_did_and_not_the_new_one(
    seeded,  # noqa: F811
    db_session,
    first,
):
    """R35, over every credential under both DIDs: the old one is spent, the
    new one holds the next organisation's credential."""
    await _release(seeded, first)
    r = await _issue(seeded, dso(CRED), DSO_DID, NEW_ID)
    new = r.json()["subjectDid"]
    db_session.expire_all()
    result = await did_retirement.sweep(
        db_session,
        Settings(role="participant", participant_did=CUSTODIAN_DID),
        did_retirement.anchor_reader,
        dry_run=True,
    )
    assert first["subjectDid"] in result.retired
    assert new not in result.retired
