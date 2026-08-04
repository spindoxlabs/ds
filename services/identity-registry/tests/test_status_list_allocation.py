"""The seam between the StatusList helpers and the issuance paths.

`test_status_list.py` proves the bit helpers in isolation. `test_vc.py` and
`test_org_onboarding.py` prove that a builder handed ``status_list_index=7``
puts 7 in the credential. Every one of those passes the index **in** as a
literal, so until this file nothing read what an issuance path *allocated*, and
nothing read the stored ``status_lists.bitstring``. Both P0 defects live
entirely in that gap.

The invariant these tests pin, in one sentence: **the bitstring is a revocation
register and never an allocator.** A credential's index comes from a counter; a
bit is set only when something is revoked.

Every test here reads the database rather than a response body — a response
that echoes an index it was given proves nothing about what was stored.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_headers, register_enrolled
from sqlalchemy import select

from identity_registry.db.models import Credential, StatusList
from identity_registry.services.status_list import find_duplicate_indices, get_bit

HEADERS = make_headers()
TA_DID = "did:web:trust-anchor.dataspaces.localhost"
ORG_DID = "did:web:acme.dataspaces.localhost"


# ── Reading the tables ────────────────────────────────────────────


async def _bitstring(db_session) -> bytes:
    """The stored register, read fresh.

    The rollback matters: the client's sessions and this one share an engine,
    and a session holding an open snapshot would answer with what it saw when
    it first read, not with what issuance has since committed.
    """
    await db_session.rollback()
    sl = (
        await db_session.execute(select(StatusList).where(StatusList.id == "1"))
    ).scalar_one_or_none()
    return sl.bitstring if sl else b""


async def _indices(db_session) -> list[int]:
    await db_session.rollback()
    rows = (await db_session.execute(select(Credential))).scalars().all()
    return [c.status_list_index for c in rows]


def _set_bits(bitstring: bytes) -> list[int]:
    """Every index whose bit is set. A revocation register should hold exactly
    the revoked ones, so this is the assertion that catches a bit set at
    issuance — and names *which* index was wrongly set when it fails."""
    return [i for i in range(len(bitstring) * 8) if get_bit(bitstring, i)]


# ── Fixtures for the two API-reachable issuance paths ─────────────


async def _bootstrap_ta(client):
    await client.post(
        "/admin/dids",
        json={"did": TA_DID, "did_type": "participant"},
        headers=HEADERS,
    )


async def _issue_membership(client, did: str, db_session=None):
    """Register the subject the way it comes to exist now, then issue to it.

    `POST /admin/dids` created this DID **and its private key**. It refuses for
    somebody else's identity (`D-51`): a participant registers by proving control
    of a key it generated itself. The anchor's row for it holds the public half —
    which is all issuance needs, since the credential is signed with the anchor's
    key and merely names the subject.
    """
    if db_session is not None:
        await register_enrolled(db_session, did)
    r = await client.post(
        "/admin/credentials/membership",
        json={
            "subject_did": did,
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _issue_data_subject(client, subject_id: str):
    r = await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": subject_id, "linked_participant_did": CUSTODIAN_DID},
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _seed_agreement(db_session):
    from identity_registry.services.agreements import import_agreements

    await import_agreements(
        db_session,
        [
            {
                "id": "dataspace-participation",
                "version": "1.0",
                "effective_from": None,
                "applies_to": ["consumer", "provider"],
                "capacity": "processor",
                "texts": {"en": {"path": "x.md", "sha256": "deadbeef"}},
            }
        ],
    )
    await db_session.commit()


async def _issue_organization(client, db_session):
    """The onboarding chain, to its issuance step.

    This is the path that sets the bit at issuance, so it cannot be replaced by
    a membership credential — the two defects are on different call sites.
    """
    await _bootstrap_ta(client)
    await _seed_agreement(db_session)
    r = await client.post(
        "/admin/organizations/applications",
        json={
            "alias": "acme-energy",
            "legal_name": "Acme Energy",
            "registration_number": "IT12345678901",
            "registration_type": "vatID",
            "hq_country_code": "IT-TN",
            "legal_country_code": "IT-TN",
            "roles": ["consumer"],
            "did": ORG_DID,
            "dsp_address": "https://acme/dsp",
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    await client.patch(
        f"/admin/organizations/applications/{r.json()['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    await client.post(
        "/admin/owners/acme-energy/agreement",
        json={"agreement_id": "dataspace-participation", "version": "1.0"},
        headers=HEADERS,
    )
    # Enrolment sits between the agreement and issuance now (`D-51`): a
    # credential binds to a key the organisation proved control of, and the
    # anchor no longer invents one. The row this leaves is public-key-only,
    # which is all issuance needs.
    await register_enrolled(db_session, "did:web:acme.dataspaces.localhost")
    cred = await client.post(
        "/admin/credentials/organization",
        json={
            "alias": "acme-energy",
            "roles": ["consumer"],
            "dsp_address": "https://acme/dsp",
        },
        headers=HEADERS,
    )
    assert cred.status_code == 201, cred.text
    return cred.json()


# ── Allocation: distinct indices ──────────────────────────────────


@pytest.mark.asyncio
async def test_two_membership_credentials_get_distinct_indices(client, db_session):
    """The core defect. Both issuances read the first unset bit and neither set
    it, so both were allocated the same index — and one revocation then revoked
    both."""
    await _bootstrap_ta(client)
    await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    indices = await _indices(db_session)
    assert len(indices) == 2
    assert None not in indices, "an issued credential must carry an index"
    assert len(set(indices)) == 2, f"indices collided: {indices}"


@pytest.mark.asyncio
async def test_indices_do_not_collide_across_credential_types(client, db_session):
    """Allocation is a property of the register, not of one route. A membership
    and a data-subject credential issued back to back must not share an index —
    they are separate call sites reading the same bitstring."""
    await _bootstrap_ta(client)
    await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    await _issue_data_subject(client, "email-abc123")
    await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    indices = await _indices(db_session)
    assert len(indices) == 3
    assert len(set(indices)) == 3, f"indices collided across types: {indices}"


@pytest.mark.asyncio
async def test_many_issuances_are_all_distinct(client, db_session):
    """Ten in a row. A fix that merely advances by one per *route* rather than
    per issuance passes the pairwise tests and fails this one."""
    await _bootstrap_ta(client)
    for n in range(10):
        await _issue_data_subject(client, f"email-{n}")

    indices = await _indices(db_session)
    assert sorted(indices) == sorted(set(indices)), f"duplicates in {indices}"
    assert len(indices) == 10


# ── The register holds revocations only ───────────────────────────


@pytest.mark.asyncio
async def test_issuance_leaves_the_revocation_bit_clear(client, db_session):
    """The second defect, at the organisation path: the bit was set in the same
    transaction that issued the credential, so it was published revoked from
    birth. Any verifier checking the StatusList would have refused it."""
    cred = await _issue_organization(client, db_session)

    bits = _set_bits(await _bitstring(db_session))
    assert bits == [], f"issuance set revocation bits {bits} for {cred['credentialId']}"


@pytest.mark.asyncio
async def test_the_register_is_empty_until_something_is_revoked(client, db_session):
    """Stated as a whole-register property so it holds no matter which paths
    ran: after N issuances and no revocation, no bit is set anywhere."""
    await _bootstrap_ta(client)
    await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    await _issue_data_subject(client, "email-abc123")

    assert _set_bits(await _bitstring(db_session)) == []


# ── Revocation: one credential, one bit ───────────────────────────


@pytest.mark.asyncio
async def test_revoking_one_credential_does_not_revoke_the_other(client, db_session):
    """The consequence a colliding index produces, asserted from the outside:
    revoke the first credential and the second must still be valid, both in its
    row and in the register the world reads."""
    await _bootstrap_ta(client)
    first = await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    second = await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    r = await client.delete(
        f"/admin/credentials/{first['credentialId']}", headers=HEADERS
    )
    assert r.status_code == 204, r.text

    # Read the values out before touching the session again: `_bitstring`
    # rolls back, which expires every loaded instance.
    await db_session.rollback()
    rows = {
        c.id: (c.status, c.status_list_index)
        for c in (await db_session.execute(select(Credential))).scalars().all()
    }
    revoked_status, revoked_index = rows[first["credentialId"]]
    survivor_status, survivor_index = rows[second["credentialId"]]

    assert revoked_status == "revoked"
    assert survivor_status == "active", "revoking one credential revoked the other"

    bitstring = await _bitstring(db_session)
    bits = _set_bits(bitstring)
    assert bits == [revoked_index], (
        f"expected only the revoked index set, got {bits} "
        f"(revoked={revoked_index}, survivor={survivor_index})"
    )
    assert not get_bit(bitstring, survivor_index)


@pytest.mark.asyncio
async def test_suspending_an_organisation_sets_only_its_own_bit(client, db_session):
    """Suspension is the enforcement point rulebook §5.6 relies on, and it runs
    through a different revocation site than `DELETE /admin/credentials/{id}`.
    A membership credential issued alongside must survive it."""
    await _issue_organization(client, db_session)
    survivor = await _issue_membership(client, "did:web:bystander.dataspaces.localhost", db_session)

    r = await client.patch(
        "/admin/owners/acme-energy", json={"status": "suspended"}, headers=HEADERS
    )
    assert r.status_code == 200, r.text

    await db_session.rollback()
    rows = {
        c.id: (c.credential_type, c.status, c.status_list_index)
        for c in (await db_session.execute(select(Credential))).scalars().all()
    }
    _, bystander_status, bystander_index = rows[survivor["credentialId"]]
    assert bystander_status == "active", "suspension revoked an unrelated credential"

    bitstring = await _bitstring(db_session)
    assert not get_bit(bitstring, bystander_index)
    org = [idx for typ, _, idx in rows.values() if typ == "OrganizationCredential"]
    assert org and all(get_bit(bitstring, idx) for idx in org)


# ── The counter is monotonic, not first-unset ─────────────────────


@pytest.mark.asyncio
async def test_a_revoked_index_is_never_reissued(client, db_session):
    """A pin on the allocator's shape rather than a reproduction of the defect.

    An allocator that scans for the first *unset* bit hands a revoked
    credential's index back out the moment that credential is revoked — the new
    holder inherits a set bit and is born revoked, and un-setting it would
    silently un-revoke the old one. A counter cannot do this. There is no
    arrangement of the current code that fails this test, which is precisely
    why it is worth writing down: it forbids the obvious wrong fix.
    """
    await _bootstrap_ta(client)
    first = await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    await client.delete(f"/admin/credentials/{first['credentialId']}", headers=HEADERS)

    await db_session.rollback()
    revoked_index = (
        await db_session.execute(
            select(Credential.status_list_index).where(
                Credential.id == first["credentialId"]
            )
        )
    ).scalar_one()

    second = await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)
    await db_session.rollback()
    reissued_index = (
        await db_session.execute(
            select(Credential.status_list_index).where(
                Credential.id == second["credentialId"]
            )
        )
    ).scalar_one()

    assert reissued_index != revoked_index
    assert not get_bit(await _bitstring(db_session), reissued_index), (
        "a freshly issued credential inherited a set revocation bit"
    )


@pytest.mark.asyncio
async def test_the_counter_survives_deleting_the_highest_credential(
    client, db_session
):
    """The `max(status_list_index) + 1` allocator's failure mode, forbidden
    explicitly. Deleting the highest-numbered credential row must not make the
    next issuance reuse its index — the deleted credential's JSON is signed and
    may still be in a holder's wallet."""
    await _bootstrap_ta(client)
    await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    top = await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    await db_session.rollback()
    top_row = (
        await db_session.execute(
            select(Credential).where(Credential.id == top["credentialId"])
        )
    ).scalar_one()
    top_index = top_row.status_list_index
    await db_session.delete(top_row)
    await db_session.commit()

    third = await _issue_membership(client, "did:web:three.dataspaces.localhost", db_session)
    await db_session.rollback()
    third_index = (
        await db_session.execute(
            select(Credential.status_list_index).where(
                Credential.id == third["credentialId"]
            )
        )
    ).scalar_one()

    assert third_index != top_index, (
        "the allocator reused a deleted credential's index — its signed JSON "
        "still names that index and may still be presented"
    )


# ── The report for damage already issued ──────────────────────────


@pytest.mark.asyncio
async def test_no_duplicates_are_reported_on_a_healthy_register(client, db_session):
    """The report must be quiet when there is nothing to say, or an operator
    learns to ignore it."""
    await _bootstrap_ta(client)
    await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    await db_session.rollback()
    assert await find_duplicate_indices(db_session) == []


@pytest.mark.asyncio
async def test_duplicates_are_reported_with_every_affected_subject(
    client, db_session
):
    """The collision is written directly, because the code can no longer
    produce one — this is what a database carrying pre-0011 credentials looks
    like, and the report is the only way an operator can tell.

    Both subjects must be named: the operator's next step is re-issuance, and
    they cannot re-issue a credential whose holder the report omits.
    """
    await _bootstrap_ta(client)
    first = await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    second = await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    await db_session.rollback()
    rows = (await db_session.execute(select(Credential))).scalars().all()
    by_id = {c.id: c for c in rows}
    collided_on = by_id[first["credentialId"]].status_list_index
    by_id[second["credentialId"]].status_list_index = collided_on
    await db_session.commit()

    duplicates = await find_duplicate_indices(db_session)
    assert len(duplicates) == 1
    report = duplicates[0]
    assert report.index == collided_on
    assert sorted(report.credential_ids) == sorted(
        [first["credentialId"], second["credentialId"]]
    )
    assert set(report.subject_dids) == {
        "did:web:one.dataspaces.localhost",
        "did:web:two.dataspaces.localhost",
    }
    assert "did:web:one.dataspaces.localhost" in str(report)


@pytest.mark.asyncio
async def test_the_report_ignores_credentials_with_no_index(client, db_session):
    """A NULL `status_list_index` is not a collision, however many rows share
    it. Grouping on NULL would report every un-indexed credential as damage."""
    await _bootstrap_ta(client)
    first = await _issue_membership(client, "did:web:one.dataspaces.localhost", db_session)
    second = await _issue_membership(client, "did:web:two.dataspaces.localhost", db_session)

    await db_session.rollback()
    rows = (await db_session.execute(select(Credential))).scalars().all()
    for c in rows:
        if c.id in (first["credentialId"], second["credentialId"]):
            c.status_list_index = None
    await db_session.commit()

    assert await find_duplicate_indices(db_session) == []
