"""A role change is a reissue (`a-role-change-is-a-reissue`).

A consumer commissions generation equipment and becomes a prosumer. Nothing in
the credential model updates a claim in place — VCDM 2.0 defines no such
property, algorithm or section — so the answer is: suspend the superseded
credential, issue its successor, both in one transaction.

**The assertions that matter are the ones about the register**, not about the
response body. A response can say "transitioned" while the bit that tells a
counterparty which credential is current was never written, and that is the
failure this whole design exists to prevent.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_headers
from sqlalchemy import select

from identity_registry.db.models import Credential, StatusList
from identity_registry.services.status_list import (
    REVOCATION_LIST_ID,
    SUSPENSION_LIST_ID,
    get_bit,
)

HEADERS = make_headers()
SUBJECT = "member-001"
TA_DID = "did:web:trust-anchor.dataspaces.localhost"


@pytest.fixture(autouse=True)
async def _anchor(client):
    await client.post(
        "/admin/dids",
        json={"did": TA_DID, "did_type": "participant"},
        headers=HEADERS,
    )


async def _issue(client, *, role: str | None = None, community_role: str | None = None):
    """A first credential. `community_role` is not settable over the issuance
    endpoint yet, so it is written the way a transition writes it — from
    `consumer` — which is also the realistic starting state."""
    body: dict = {"subject_id": SUBJECT, "linked_participant_did": CUSTODIAN_DID}
    if role is not None:
        body["role"] = role
    r = await client.post("/admin/credentials/data-subject", json=body, headers=HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


async def _transition(client, *, to_role: str, role: str | None = None, **extra):
    body: dict = {
        "subject_id": SUBJECT,
        "to_role": to_role,
        "linked_participant_did": CUSTODIAN_DID,
        **extra,
    }
    if role is not None:
        body["role"] = role
    return await client.post(
        "/admin/credentials/data-subject/transition", json=body, headers=HEADERS
    )


async def _bits(db_session, list_id: str) -> list[int]:
    await db_session.rollback()
    sl = (
        await db_session.execute(select(StatusList).where(StatusList.id == list_id))
    ).scalar_one_or_none()
    if sl is None:
        return []
    return [i for i in range(len(sl.bitstring) * 8) if get_bit(sl.bitstring, i)]


async def _creds(db_session) -> list[Credential]:
    await db_session.rollback()
    return list(
        (
            await db_session.execute(
                select(Credential)
                .where(Credential.credential_type == "DataSubjectCredential")
                .order_by(Credential.issued_at)
            )
        )
        .scalars()
        .all()
    )


# ── the transition itself ─────────────────────────────────────────


@pytest.mark.rule("P-28")
async def test_a_transition_suspends_the_predecessor_and_issues_a_successor(
    client, db_session
):
    first = await _issue(client)
    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["supersededCredentialId"] == first["credentialId"]
    assert body["credentialId"] != first["credentialId"]
    assert body["toRole"] == "prosumer"

    creds = {c.id: c for c in await _creds(db_session)}
    assert len(creds) == 2
    assert creds[first["credentialId"]].status == "suspended"
    assert creds[body["credentialId"]].status == "active"


@pytest.mark.rule("P-28")
async def test_the_suspension_bit_is_set_and_the_revocation_bit_is_not(
    client, db_session
):
    """**Suspended, never revoked.** Revocation says the attestation was
    withdrawn and is terminal; this attestation was replaced. A verifier reads
    the difference off the register, so writing the wrong bit tells every
    counterparty something the issuer does not mean."""
    first = await _issue(client)
    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 201

    creds = {c.id: c for c in await _creds(db_session)}
    superseded_index = creds[first["credentialId"]].status_list_index

    assert await _bits(db_session, SUSPENSION_LIST_ID) == [superseded_index]
    assert await _bits(db_session, REVOCATION_LIST_ID) == []


@pytest.mark.rule("P-28")
async def test_the_successor_carries_the_new_claim_and_keeps_the_old_ones(
    client, db_session
):
    """A transition changes the community role. It is not an opportunity to
    silently drop everything else the credential said."""
    await _issue(client, role="ConsumerUser")
    r = await _transition(
        client,
        to_role="prosumer",
        role="ConsumerUser",
        verified_by="REC Milano",
        verification_method="meter-commissioning-cert",
    )
    assert r.status_code == 201, r.text

    successor = [c for c in await _creds(db_session) if c.status == "active"][0]
    subject = successor.credential_json["credentialSubject"]
    assert subject["communityRole"] == "prosumer"
    # `role` is the *protocol* role and is untouched — ds-connector and
    # ds-provenance check it as `required_roles`, so moving a community role
    # into it would 403 the holder out of every route they could reach.
    assert subject["role"] == "ConsumerUser"
    assert subject["linkedParticipant"] == CUSTODIAN_DID
    assert subject["verifiedBy"] == "REC Milano"
    assert subject["verificationMethod"] == "meter-commissioning-cert"


@pytest.mark.rule("P-28")
async def test_the_successor_names_both_registers(client, db_session):
    """Otherwise the *next* role change would have nothing to suspend."""
    await _issue(client)
    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 201

    successor = [c for c in await _creds(db_session) if c.status == "active"][0]
    purposes = {
        e["statusPurpose"] for e in successor.credential_json["credentialStatus"]
    }
    assert purposes == {"revocation", "suspension"}


@pytest.mark.rule("P-28")
async def test_a_second_transition_supersedes_the_successor(client, db_session):
    """`pending → consumer → prosumer` is a chain, not a special case."""
    await _issue(client)
    first = await _transition(client, to_role="consumer")
    assert first.status_code == 201
    second = await _transition(client, to_role="prosumer")
    assert second.status_code == 201, second.text

    assert second.json()["fromRole"] == "consumer"
    assert second.json()["supersededCredentialId"] == first.json()["credentialId"]
    creds = await _creds(db_session)
    assert [c.status for c in creds] == ["suspended", "suspended", "active"]
    assert len(await _bits(db_session, SUSPENSION_LIST_ID)) == 2


# ── what it refuses ───────────────────────────────────────────────


async def test_a_transition_for_an_unknown_person_is_a_404(client):
    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 404
    assert "No dataspace identity" in r.json()["detail"]


@pytest.mark.rule("P-28")
async def test_a_transition_to_the_role_already_held_is_refused(client, db_session):
    """It would burn a status-list index and suspend a credential to replace it
    with an identical one. An index is never recovered."""
    await _issue(client)
    assert (await _transition(client, to_role="prosumer")).status_code == 201
    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 409
    assert "already holds" in r.json()["detail"]
    assert len(await _creds(db_session)) == 2


async def test_a_transition_of_a_role_the_person_does_not_hold_is_a_404(
    client, db_session
):
    """Idempotency and transition are both **per protocol role**. Superseding a
    `ConsumerUser` credential when only a `DataSubject` one exists would issue a
    successor to nothing."""
    await _issue(client, role="DataSubject")
    r = await _transition(client, to_role="prosumer", role="ConsumerUser")
    assert r.status_code == 404
    assert "nothing to supersede" in r.json()["detail"]
    assert len(await _creds(db_session)) == 1


@pytest.mark.rule("P-27", "P-28")
async def test_a_predecessor_naming_no_suspension_register_is_refused(
    client, db_session
):
    """A credential issued before `P-27` names the revocation register only.

    Superseding it would mean **revoking** it, and revocation asserts the
    attestation was withdrawn when it was merely replaced — a claim the issuer
    does not mean, made to every counterparty, permanently. So it is refused
    with the reason, not quietly downgraded to a revocation.
    """
    first = await _issue(client)
    cred_id = first["credentialId"]

    # Rewrite it into the shape issuance produced before `P-27`: one entry, an
    # object rather than an array.
    await db_session.rollback()
    cred = await db_session.get(Credential, cred_id)
    vc = dict(cred.credential_json)
    vc["credentialStatus"] = [
        e for e in vc["credentialStatus"] if e["statusPurpose"] == "revocation"
    ][0]
    cred.credential_json = vc
    await db_session.commit()

    r = await _transition(client, to_role="prosumer")
    assert r.status_code == 409
    assert "no suspension register" in r.json()["detail"]

    # Nothing written, and above all no revocation bit.
    assert await _bits(db_session, REVOCATION_LIST_ID) == []
    assert await _bits(db_session, SUSPENSION_LIST_ID) == []
    assert len(await _creds(db_session)) == 1


@pytest.mark.rule("P-28")
async def test_a_refused_transition_writes_nothing(client, db_session):
    """The register is the assertion. A refusal that had already allocated an
    index or set a bit would leave the person mid-transition with no way to
    tell."""
    await _issue(client)
    assert (await _transition(client, to_role="prosumer")).status_code == 201
    bits_before = await _bits(db_session, SUSPENSION_LIST_ID)

    assert (await _transition(client, to_role="prosumer")).status_code == 409

    assert await _bits(db_session, SUSPENSION_LIST_ID) == bits_before
    assert await _bits(db_session, REVOCATION_LIST_ID) == []
    assert len(await _creds(db_session)) == 2
