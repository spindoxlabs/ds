"""The same person, the same role, two organisations: no cross-organisation hand-over.

One human keeps one DID across organisations (`issue_data_subject_credential`),
and a credential is idempotent per (subject, role) (ds#30). So a second
organisation issuing the **same role** for a person the first one onboarded
matched the first organisation's credential, and:

* issuance answered `201` with the first organisation's `credentialId`, and
  re-delivered that credential — the whole signed VC, `linkedParticipant`,
  `verifiedBy`, `verificationMethod`, status indices — to the **second**
  organisation's custodian;
* a role transition by the second organisation suspended the first one's
  credential and issued a successor linked to the second, still carrying the
  first one's `verifiedBy`.

Both are refused (`409`) before anything is written or delivered. Whether the
second organisation should instead get a credential of its own is a design
question (ADR-0026's residual) and not decided here.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, register_custodian
from sqlalchemy import select
from test_keycloak_sync_collector import (  # noqa: F401
    CRED,
    DSO_DID,
    _sync,
    dso,
    rec,
    seeded,
)
from test_suspended_organisation_cleanup import cli_database  # noqa: F401

from identity_registry.db.models import Credential

SUBJECT = "member-001"
ROLE = "DataSubject"


async def _issue(client, headers, linked):
    return await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": SUBJECT,
            "role": ROLE,
            "linked_participant_did": linked,
            "verified_by": linked,
            "verification_method": "id-document",
        },
        headers=headers,
    )


@pytest.fixture
async def first(seeded, db_session, credential_store):  # noqa: F811
    """The REC onboarded the person; both organisations can hold credentials."""
    await register_custodian(db_session)
    await register_custodian(db_session, DSO_DID)
    r = await _issue(seeded, rec(CRED), CUSTODIAN_DID)
    assert r.status_code == 201, r.text
    return r.json()


async def _rows(db_session):
    db_session.expire_all()
    return (await db_session.execute(select(Credential.id, Credential.status))).all()


async def test_the_second_organisation_gets_neither_the_credential_nor_its_id(
    seeded,  # noqa: F811
    db_session,
    credential_store,
    first,
):
    delivered_before = len(credential_store)

    r = await _issue(seeded, dso(CRED), DSO_DID)

    assert r.status_code == 409, r.text
    assert first["credentialId"] not in r.text
    assert CUSTODIAN_DID not in r.text
    # Nothing reached the second organisation's custodian.
    assert len(credential_store) == delivered_before
    assert await _rows(db_session) == [(first["credentialId"], "active")]


async def test_the_first_organisation_still_re_delivers_its_own(
    seeded,  # noqa: F811
    credential_store,
    first,
):
    """ds#30's re-delivery is unchanged for the organisation it is linked to."""
    r = await _issue(seeded, rec(CRED), CUSTODIAN_DID)
    assert r.status_code == 201, r.text
    assert r.json()["credentialId"] == first["credentialId"]
    assert credential_store[-1]["url"].endswith(f"/{CUSTODIAN_DID}/credentials")


async def test_the_second_organisation_cannot_transition_the_first_ones_credential(
    seeded,  # noqa: F811
    db_session,
    credential_store,
    first,
):
    delivered_before = len(credential_store)

    r = await seeded.post(
        "/admin/credentials/data-subject/transition",
        json={
            "subject_id": SUBJECT,
            "role": ROLE,
            "to_role": "prosumer",
            "linked_participant_did": DSO_DID,
        },
        headers=dso(CRED),
    )

    assert r.status_code == 409, r.text
    assert len(credential_store) == delivered_before
    assert await _rows(db_session) == [(first["credentialId"], "active")]
    # And the first organisation keeps its member.
    r = await _sync(seeded, rec(), first["subjectDid"])
    assert r.status_code == 200, r.text


async def test_another_role_is_still_the_second_organisations_own(
    seeded,  # noqa: F811
    first,
):
    """One person, one DID, many organisations — unchanged."""
    r = await seeded.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": SUBJECT,
            "role": "ConsumerUser",
            "linked_participant_did": DSO_DID,
        },
        headers=dso(CRED),
    )
    assert r.status_code == 201, r.text
    assert r.json()["subjectDid"] == first["subjectDid"]
    assert r.json()["credentialId"] != first["credentialId"]


# ── ir-cli credential issue-data-subject: the same rule ─────────────────────


def test_ir_cli_does_not_re_deliver_another_organisations_credential(
    cli_database,  # noqa: F811
    monkeypatch,
):
    import json
    import sqlite3

    from typer.testing import CliRunner

    from identity_registry.cli.main import app as cli

    monkeypatch.setenv("DS_ENV", "dev")
    did = f"{CUSTODIAN_DID}:users:{SUBJECT}"
    vc = {
        "credentialSubject": {
            "id": did,
            "role": ROLE,
            "linkedParticipant": CUSTODIAN_DID,
        }
    }
    with sqlite3.connect(cli_database.removeprefix("sqlite+aiosqlite:///")) as conn:
        conn.execute(
            f"INSERT INTO dids (did, did_type, active) VALUES ('{did}', 'user', 1)"
        )
        conn.execute(
            "INSERT INTO credentials (id, credential_type, issuer_did, "
            "subject_did, credential_json, status) VALUES ('urn:uuid:first', "
            f"'DataSubjectCredential', 'did:web:ta', '{did}', ?, 'active')",
            (json.dumps(vc),),
        )

    r = CliRunner().invoke(
        cli,
        [
            "credential",
            "issue-data-subject",
            "--subject-id",
            SUBJECT,
            "--role",
            ROLE,
            "--linked-participant-did",
            DSO_DID,
        ],
    )
    assert r.exit_code == 1, r.output
    assert "linked to another organisation" in r.output
    assert "urn:uuid:first" not in r.output
