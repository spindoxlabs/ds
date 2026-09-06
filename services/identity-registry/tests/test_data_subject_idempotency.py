"""Issuing a person's credential twice (`ds#30`).

`POST /admin/credentials/data-subject` is the endpoint an **external onboarding
application** calls — `dependencies.py` says so where it splits
`identity-registry.credentials.write` out of `identity-registry.admin`. Such an
application provisions on demand: it resolves a member, finds no dataspace
identity, and issues. So a member who opens the page twice used to get two
credentials and spend two status-list indices.

**The index is why this is a defect and not untidiness.** A bit in the register
is allocated per issuance and never recovered, so a wizard in front of a few
hundred members exhausted capacity at a rate set by page visits rather than by
people.

Every test here reads the database. A response body that echoes a credential id
proves nothing about how many rows were written.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_headers
from sqlalchemy import select

from identity_registry.db.models import Credential, StatusList
from identity_registry.services.status_list import REVOCATION_LIST_ID

HEADERS = make_headers()
SUBJECT = "member-001"
TA_DID = "did:web:trust-anchor.dataspaces.localhost"


@pytest.fixture(autouse=True)
async def _anchor(client):
    """Issuance signs with the anchor's key, so every test here needs one.

    Without it the endpoint answers 500 "Trust anchor not bootstrapped" and the
    index test passes for the wrong reason — nothing was allocated because
    nothing was issued.
    """
    await client.post(
        "/admin/dids",
        json={"did": TA_DID, "did_type": "participant"},
        headers=HEADERS,
    )


async def _issue(client, *, subject_id: str = SUBJECT, role: str | None = None):
    body: dict = {"subject_id": subject_id, "linked_participant_did": CUSTODIAN_DID}
    if role is not None:
        body["role"] = role
    return await client.post(
        "/admin/credentials/data-subject", json=body, headers=HEADERS
    )


async def _credentials(db_session) -> list[Credential]:
    await db_session.rollback()
    return list(
        (
            await db_session.execute(
                select(Credential).where(
                    Credential.credential_type == "DataSubjectCredential"
                )
            )
        )
        .scalars()
        .all()
    )


async def _next_index(db_session) -> int:
    await db_session.rollback()
    sl = (
        await db_session.execute(
            select(StatusList).where(StatusList.id == REVOCATION_LIST_ID)
        )
    ).scalar_one_or_none()
    return sl.next_index if sl else 0


async def test_issuing_twice_writes_one_credential(client, db_session):
    first = await _issue(client)
    assert first.status_code == 201, first.text
    second = await _issue(client)
    assert second.status_code == 201, second.text

    creds = await _credentials(db_session)
    assert len(creds) == 1
    # The caller cannot tell whether it minted or matched, and does not need to:
    # what it asked for is true either way.
    assert first.json()["credentialId"] == second.json()["credentialId"]
    assert first.json()["subjectDid"] == second.json()["subjectDid"]


async def test_issuing_twice_spends_one_status_list_index(client, db_session):
    """The assertion that actually matters. A duplicate row can be deleted; a
    consumed index cannot be returned to the register."""
    await _issue(client)
    after_first = await _next_index(db_session)
    await _issue(client)
    assert await _next_index(db_session) == after_first


async def test_a_second_role_for_the_same_person_is_still_issued(client, db_session):
    """Idempotent **per role**, not per subject.

    One person is legitimately a data subject about their own consumption *and*
    a consumer user acting for an organisation. Keying this on
    `credential_type` alone makes a dual-role person impossible to create —
    `credential_type` cannot carry the role, because it is also the VC `type`
    that DCP presentation matching keys on.
    """
    first = await _issue(client, role="DataSubject")
    second = await _issue(client, role="ConsumerUser")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["credentialId"] != second.json()["credentialId"]

    creds = await _credentials(db_session)
    assert len(creds) == 2
    # One person, one DID — the roles are additive, the identity is not.
    assert len({c.subject_did for c in creds}) == 1
    assert len({c.status_list_index for c in creds}) == 2


async def test_the_roleless_credential_is_not_matched_by_a_roled_one(
    client, db_session
):
    """`None` is a role like any other here. A credential carrying no `role`
    claim must not satisfy a request that names one, or the first call a caller
    makes would suppress every later one."""
    await _issue(client)  # no role
    await _issue(client, role="DataSubject")
    assert len(await _credentials(db_session)) == 2


async def test_a_revoked_credential_does_not_suppress_a_reissue(client, db_session):
    """Only an **active** credential matches.

    This is what makes the plan's transition possible at all: retiring a
    credential and issuing its successor has to produce a second row, or a role
    change would be a no-op that reported success.
    """
    first = await _issue(client)
    cred_id = first.json()["credentialId"]

    r = await client.delete(f"/admin/credentials/{cred_id}", headers=HEADERS)
    assert r.status_code == 204, r.text

    second = await _issue(client)
    assert second.status_code == 201, second.text
    assert second.json()["credentialId"] != cred_id
    assert len(await _credentials(db_session)) == 2
