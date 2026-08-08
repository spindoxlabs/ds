"""Suspension as a state distinct from deactivation — `participation.md` §5,
`DSSC-TRF-02`/`-03`/`-04`.

The verb existed before this: `org suspend` revoked every credential, set the
StatusList bit and deactivated the participant, and `revoke` called it and wrote
a different string over the top. Two names, one set of effects, and no way back
from either — which is a slower revocation, not a state.

What makes it a state is asserted here:

* it writes to a **different register**, published with `statusPurpose:
  suspension`, so a verifier is told which of the two answers it got;
* the bit it sets is the only bit anything may clear, so **reinstatement** is
  possible without re-issuing a credential the holder already has;
* **revocation stays terminal** — reachable from suspension, never the reverse.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import make_headers
from sqlalchemy import select

from identity_registry.db.models import (
    Credential,
    Did,
    Owner,
    Participant,
    StatusList,
)
from identity_registry.services.org_onboarding import (
    OrgOnboardingError,
    reinstate_owner,
    revoke_owner,
    suspend_owner,
    suspension_index,
    upsert_owner_from_application,
)
from identity_registry.services.status_list import (
    REVOCATION_LIST_ID,
    SUSPENSION_LIST_ID,
    StatusListPurposeMismatch,
    get_bit,
    get_or_create_status_list,
    revoke_status_list_index,
    suspend_status_list_index,
    unsuspend_status_list_index,
)

HEADERS = make_headers()
TA_DID = "did:web:trust-anchor.dataspaces.localhost"
ORG_DID = "did:web:acme.dataspaces.localhost"


# ── Fixtures: an owner holding a suspendable credential ───────────


def _credential_json(index: int, *, suspendable: bool = True) -> dict:
    revocation = {
        "id": f"https://ta/status/1#{index}",
        "type": "StatusList2021Entry",
        "statusPurpose": "revocation",
        "statusListIndex": str(index),
        "statusListCredential": "https://ta/status/1",
    }
    if not suspendable:
        # The shape every credential issued before the suspension register
        # existed still carries, and the reason `suspend_owner` checks.
        return {"credentialStatus": revocation}
    return {
        "credentialStatus": [
            revocation,
            {
                "id": f"https://ta/status/2#{index}",
                "type": "StatusList2021Entry",
                "statusPurpose": "suspension",
                "statusListIndex": str(index),
                "statusListCredential": "https://ta/status/2",
            },
        ]
    }


async def _seed_owner(
    db_session,
    *,
    index: int = 4,
    suspendable: bool = True,
    credential_type: str = "OrganizationCredential",
) -> Owner:
    db_session.add(Did(did=ORG_DID, did_type="participant"))
    owner = Owner(
        id="acme-energy",
        type="schema:Organization",
        name="Acme Energy",
        did=ORG_DID,
        status="verified",
        verified_by="op1",
        verified_at=datetime.now(UTC),
    )
    db_session.add(owner)
    db_session.add(
        Credential(
            id=f"urn:uuid:cred-{index}",
            credential_type=credential_type,
            issuer_did=TA_DID,
            subject_did=ORG_DID,
            credential_json=_credential_json(index, suspendable=suspendable),
            status="active",
            status_list_index=index,
        )
    )
    db_session.add(
        Participant(
            did=ORG_DID,
            dsp_address="https://acme/dsp",
            roles=["consumer"],
            allowed_scopes=["dataspaces.query"],
            active=True,
        )
    )
    await db_session.flush()
    return owner


async def _bits(db_session, list_id: str) -> bytes:
    sl = (
        await db_session.execute(select(StatusList).where(StatusList.id == list_id))
    ).scalar_one_or_none()
    return sl.bitstring if sl else b"\x00" * 16384


async def _participant(db_session) -> Participant:
    return (
        await db_session.execute(select(Participant).where(Participant.did == ORG_DID))
    ).scalar_one()


# ── The register layer ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_suspension_register_is_published_as_a_suspension_register(
    db_session,
):
    """EDC refuses an entry whose `statusPurpose` does not match the list's
    (`"Credential's statusPurpose value must match the status list's purpose"`),
    so a suspension entry pointing at a register published as `revocation` is
    not a lenient mismatch — it is a credential no verifier will accept.
    """
    sl = await get_or_create_status_list(db_session, SUSPENSION_LIST_ID)
    assert sl.purpose == "suspension"

    revocation = await get_or_create_status_list(db_session, REVOCATION_LIST_ID)
    assert revocation.purpose == "revocation"


@pytest.mark.asyncio
async def test_a_register_whose_stored_purpose_disagrees_is_refused(db_session):
    db_session.add(
        StatusList(
            id=SUSPENSION_LIST_ID,
            purpose="revocation",
            bitstring=b"\x00" * 16384,
            next_index=0,
        )
    )
    await db_session.flush()

    with pytest.raises(StatusListPurposeMismatch):
        await get_or_create_status_list(db_session, SUSPENSION_LIST_ID)


@pytest.mark.asyncio
async def test_a_suspension_bit_is_the_only_bit_that_can_be_cleared(db_session):
    await suspend_status_list_index(db_session, 9)
    assert get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 9)

    await unsuspend_status_list_index(db_session, 9)
    assert not get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 9)

    # Idempotent in both directions — an operator retrying a reinstatement is
    # not an error, and neither is suspending someone already suspended.
    await unsuspend_status_list_index(db_session, 9)
    await suspend_status_list_index(db_session, 9)
    await suspend_status_list_index(db_session, 9)
    assert get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 9)


@pytest.mark.asyncio
async def test_clearing_a_bit_cannot_reach_the_revocation_register(db_session):
    """The failure this forbids is silent and unrecoverable: a cleared
    revocation bit makes a finished credential valid again, and nothing else in
    the system would notice.
    """
    await revoke_status_list_index(db_session, 3)
    await unsuspend_status_list_index(db_session, 3)

    assert get_bit(await _bits(db_session, REVOCATION_LIST_ID), 3)


@pytest.mark.asyncio
async def test_a_revocation_cannot_be_written_to_the_suspension_register(db_session):
    with pytest.raises(StatusListPurposeMismatch):
        await revoke_status_list_index(db_session, 3, SUSPENSION_LIST_ID)


# ── Reading a credential's suspension index ───────────────────────


def test_suspension_index_reads_the_entry_by_purpose():
    assert suspension_index(_credential_json(11)) == 11


def test_a_credential_naming_one_register_has_no_suspension_index():
    assert suspension_index(_credential_json(11, suspendable=False)) is None
    assert suspension_index({}) is None
    assert suspension_index({"credentialStatus": None}) is None


# ── Suspend → reinstate, and the credential in between ────────────


@pytest.mark.asyncio
async def test_suspension_holds_the_credential_and_reinstatement_returns_it(
    db_session,
):
    owner = await _seed_owner(db_session)

    await suspend_owner(db_session, owner)
    cred = (await db_session.execute(select(Credential))).scalars().one()
    assert owner.status == "suspended"
    assert cred.status == "suspended"
    assert cred.revoked_at is None, "a suspension is not an ending"
    assert get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 4)
    assert not get_bit(await _bits(db_session, REVOCATION_LIST_ID), 4)
    assert (await _participant(db_session)).active is False

    await reinstate_owner(db_session, owner)
    cred = (await db_session.execute(select(Credential))).scalars().one()
    assert owner.status == "verified"
    assert cred.status == "active"
    assert cred.id == "urn:uuid:cred-4", "reinstatement re-issued instead of lifting"
    assert not get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 4)
    participant = await _participant(db_session)
    assert participant.active is True
    assert participant.deactivated_at is None


@pytest.mark.asyncio
async def test_suspension_covers_the_membership_credential_too(db_session):
    """An organisation whose `OrganizationCredential` is held while its
    `MembershipCredential` stays active still satisfies the membership
    constraint at a counterparty's connector (`P-16`). Suspending one and not
    the other suspends nobody.
    """
    owner = await _seed_owner(
        db_session, index=6, credential_type="MembershipCredential"
    )

    await suspend_owner(db_session, owner)

    cred = (await db_session.execute(select(Credential))).scalars().one()
    assert cred.status == "suspended"
    assert get_bit(await _bits(db_session, SUSPENSION_LIST_ID), 6)


@pytest.mark.asyncio
async def test_a_credential_no_verifier_would_see_suspended_is_refused(db_session):
    """Setting a bit on a register the credential does not name reports a
    suspension that holds nowhere it counts. Refusing says so, and names the
    two ways forward.
    """
    owner = await _seed_owner(db_session, index=7, suspendable=False)

    with pytest.raises(OrgOnboardingError) as exc:
        await suspend_owner(db_session, owner)

    assert "urn:uuid:cred-7" in exc.value.message
    assert "revoke" in exc.value.message
    assert owner.status == "verified", "the refusal left the owner half-suspended"


# ── Revocation stays terminal ─────────────────────────────────────


@pytest.mark.asyncio
async def test_revocation_is_reachable_from_suspension(db_session):
    owner = await _seed_owner(db_session)
    await suspend_owner(db_session, owner)

    await revoke_owner(db_session, owner)

    cred = (await db_session.execute(select(Credential))).scalars().one()
    assert owner.status == "revoked"
    assert cred.status == "revoked"
    assert cred.revoked_at is not None
    assert get_bit(await _bits(db_session, REVOCATION_LIST_ID), 4)


@pytest.mark.asyncio
async def test_a_revoked_organisation_cannot_be_reinstated(db_session):
    owner = await _seed_owner(db_session)
    await revoke_owner(db_session, owner)

    with pytest.raises(OrgOnboardingError):
        await reinstate_owner(db_session, owner)
    with pytest.raises(OrgOnboardingError):
        await suspend_owner(db_session, owner)

    assert owner.status == "revoked"


@pytest.mark.asyncio
async def test_reinstating_something_that_is_not_suspended_is_an_error(db_session):
    owner = await _seed_owner(db_session)

    with pytest.raises(OrgOnboardingError) as exc:
        await reinstate_owner(db_session, owner)

    assert "nothing to reinstate" in exc.value.message


# ── The path that used to lift a suspension by accident ───────────


@pytest.mark.asyncio
async def test_re_applying_a_seed_cannot_lift_a_suspension(db_session):
    """`upsert_owner_from_application` wrote `status = "verified"`
    unconditionally. Reached with a suspended owner — a re-applied `owners.yaml`,
    a re-run promotion — it undid the suspension **and nothing else**: no bit
    cleared, no participant reactivated. The organisation read as verified while
    every verifier still saw its credential held.
    """
    owner = await _seed_owner(db_session)
    await suspend_owner(db_session, owner)

    application = type(
        "App",
        (),
        {
            "alias": "acme-energy",
            "legal_name": "Acme Energy",
            "did": ORG_DID,
            "registration_number": None,
            "registration_type": None,
            "hq_country_code": None,
            "legal_country_code": None,
            "parent_organizations": None,
            "sub_organizations": None,
            "evidence_ref": None,
            "verified_by": "op1",
        },
    )()

    with pytest.raises(OrgOnboardingError) as exc:
        await upsert_owner_from_application(db_session, application, verified_by="op1")

    assert "reinstate" in exc.value.message
    assert owner.status == "suspended"


# ── What a verifier fetches ───────────────────────────────────────


@pytest.mark.asyncio
async def test_the_suspension_register_is_served_with_its_own_purpose(
    client, db_session
):
    """`/status/2` has to answer, and answer as a suspension register.

    A verifier that cannot fetch a register a credential names fails closed, so
    a 404 here rejects every participant credential this registry has issued.
    """
    await get_or_create_status_list(db_session, SUSPENSION_LIST_ID)
    await db_session.commit()

    response = await client.get(
        "/status/2", headers={"Accept": "application/json"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["credentialSubject"]["statusPurpose"] == "suspension"
