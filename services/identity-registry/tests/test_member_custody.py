"""A natural person belongs to an organisation, and so does their credential.

`DID-11` step 2 — `D-49`, `D-50`, `DSSC-SVD-25`.

Two changes, and they are separate on purpose:

* **The identifier** moves from `did:web:users.<anchor>:<id>` to
  `did:web:<participant>:users:<id>`. The old shape said every person in the
  dataspace belonged to the *trust anchor*, which is not the relationship
  anybody has with them — the REC onboarded them, the REC vouches for them, the
  REC answers for them.
* **Custody** moves with the credential: the anchor signs it and pushes it to
  the organisation the credential is *about a relationship with*, over the same
  CIP Storage API a participant's own credentials use.

The two do not always name the same organisation, which is the case worth
testing: a person who is a data subject at their REC and a consumer user at
another company has **one** identifier and **two** custodians.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_admin_headers, register_custodian
from sqlalchemy import select

from identity_registry.db.models import Credential, Did, Key
from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair
from identity_registry.services.did import custodian_of, subject_did_for, subject_id_of

ANCHOR = "did:web:trust-anchor.dataspaces.localhost"
OTHER = "did:web:third-party.dataspaces.localhost"
HEADERS = make_admin_headers()


@pytest.fixture(autouse=True)
async def anchor_key(db_session):
    from identity_registry.config import get_settings

    kp = generate_key_pair(ANCHOR)
    key = Key(
        owner_did=ANCHOR,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
    )
    db_session.add(key)
    await db_session.flush()
    db_session.add(Did(did=ANCHOR, did_type="participant", key_id=key.id))
    await db_session.commit()
    return key


async def issue(client, subject_id, *, participant=CUSTODIAN_DID, role="DataSubject"):
    r = await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": subject_id,
            "role": role,
            "linked_participant_did": participant,
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── the namespace ─────────────────────────────────────────────────


def test_a_subject_did_names_its_custodian():
    did = subject_did_for("did:web:rec.example.org", "alice")
    assert did == "did:web:rec.example.org:users:alice"
    # It resolves at the participant's own host, through the `/dids` route every
    # participant already serves — which is what closes `D-22` without a rule of
    # its own for path-bearing DIDs.
    assert custodian_of(did) == "did:web:rec.example.org"
    assert subject_id_of(did) == "alice"


@pytest.mark.asyncio
async def test_issuing_without_a_custodian_is_refused(client, db_session):
    """The single most tempting default in this change.

    Falling back to the anchor's namespace would look like a courtesy and would
    recreate exactly what this replaces: a person filed under the party that has
    no relationship with them. A person nobody is custodian for has nowhere to
    live, and that is a 422, not a default.
    """
    r = await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": "orphan", "role": "DataSubject"},
        headers=HEADERS,
    )
    assert r.status_code == 422
    assert "custodian" in r.text


@pytest.mark.asyncio
async def test_one_person_keeps_one_did_across_organisations(
    client, db_session, credential_store
):
    """Roles are additive; identifiers are not.

    The endpoint is called once per role, so deriving the DID from *this* call's
    participant would give a dual-role person two identifiers — splitting their
    consent records, their memberships and their provenance in half, silently.
    The first call decides where they live; custody still follows each credential.
    """
    await register_custodian(db_session)
    await register_custodian(db_session, OTHER)

    first = await issue(client, "dual", participant=CUSTODIAN_DID)
    second = await issue(client, "dual", participant=OTHER, role="ConsumerUser")

    assert first["subjectDid"] == f"{CUSTODIAN_DID}:users:dual"
    assert second["subjectDid"] == first["subjectDid"], "one human, one identifier"
    # …and two custodians, because that is what is true.
    assert first["custodianDid"] == CUSTODIAN_DID
    assert second["custodianDid"] == OTHER
    assert {d["url"] for d in credential_store} == {
        f"http://rec.dataspaces.localhost/credentials/{CUSTODIAN_DID}/credentials",
        f"http://rec.dataspaces.localhost/credentials/{OTHER}/credentials",
    }


# ── custody ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_credential_is_delivered_to_the_custodian(
    client, db_session, credential_store
):
    await register_custodian(db_session)
    result = await issue(client, "alice")

    assert result["deliveredTo"], result
    assert result["deliveryError"] is None

    message = credential_store[0]["body"]
    assert message["type"] == "CredentialMessage"
    container = message["credentials"][0]
    assert container["credentialType"] == "DataSubjectCredential"
    # The person is the **subject**; the organisation is the **holder**. A
    # delivery that conflated them would file the credential under the REC.
    assert container["payload"]["credentialSubject"]["id"] == result["subjectDid"]


@pytest.mark.asyncio
async def test_the_anchor_keeps_its_issuance_record(
    client, db_session, credential_store
):
    """Delivery is not a handover.

    The issuer knows *what it attested* — that is what revocation acts on and
    what `GET /admin/credentials/{id}` reads. The custodian holds *what it can
    serve*. Different facts about the same credential; losing either one loses a
    question nobody else can answer.
    """
    await register_custodian(db_session)
    result = await issue(client, "alice")

    row = (
        await db_session.execute(
            select(Credential).where(Credential.id == result["credentialId"])
        )
    ).scalar_one()
    assert row.subject_did == result["subjectDid"]
    assert row.status_list_index is not None, "the register is the issuer's"


@pytest.mark.asyncio
async def test_a_delivery_failure_is_reported_and_the_credential_survives(
    client, db_session
):
    """No `credential_store` here, so the push has nowhere to land.

    The credential row **stays**: it is what a retry re-delivers. And the caller
    is told, because a person whose organisation does not hold their credential
    is a person that organisation cannot answer for — a fact that has to surface
    at the call that caused it, not at the first query that fails.
    """
    await register_custodian(db_session)
    result = await issue(client, "alice")

    assert result["deliveredTo"] is None
    assert result["deliveryError"]
    row = (
        await db_session.execute(
            select(Credential).where(Credential.id == result["credentialId"])
        )
    ).scalar_one()
    assert row.credential_json


@pytest.mark.asyncio
async def test_a_custodian_publishing_no_credential_service_is_named(
    client, db_session
):
    await register_custodian(db_session, credential_service=False)
    result = await issue(client, "alice")
    assert "CredentialService" in (result["deliveryError"] or "")


@pytest.mark.asyncio
async def test_an_unregistered_custodian_is_named(client, db_session):
    result = await issue(client, "alice", participant="did:web:stranger.example.test")
    assert "not registered here" in (result["deliveryError"] or "")


# ── the holder-side route ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_instance_serves_the_credentials_it_holds(client, db_session):
    """`GET /users/{did}/credentials` — the custody half of `/users/resolve`.

    Exercised here on the anchor, which is custodian for DIDs in its own
    namespace; the route is mounted on both roles and the logic is the same one
    a participant runs. What decides the answer is `custodian_of(did)` against
    *this* instance's own DID, which the last two tests in this file pin.

    *Who is this person* is registry data and stays at the anchor; *what do they
    hold* is custody and lives here. A REC-side application asks its own
    instance, rather than asking the issuer for credentials the issuer happens to
    have a copy of.
    """
    from identity_registry.services import issuance

    subject = f"{ANCHOR}:users:alice"
    await issuance.store_delivered(
        db_session,
        holder_did=ANCHOR,
        issuer_did=ANCHOR,
        credentials=[
            {
                "format": "json-ld",
                "credentialType": "DataSubjectCredential",
                "payload": {
                    "id": "urn:uuid:c-1",
                    "type": ["VerifiableCredential", "DataSubjectCredential"],
                    "credentialSubject": {"id": subject, "role": "DataSubject"},
                    "proof": {"jws": "eyJ.stub.sig"},
                },
            }
        ],
    )
    await db_session.commit()

    body = (await client.get(f"/users/{subject}/credentials", headers=HEADERS)).json()
    assert body["did"] == subject
    assert body["subject_id"] == "alice"
    assert body["roles"] == ["DataSubject"]
    assert body["vc_jws"] == "eyJ.stub.sig"


@pytest.mark.asyncio
async def test_a_stored_member_credential_keeps_the_person_as_its_subject(
    client, db_session
):
    """The defect this route would otherwise have hidden.

    `store_delivered` recorded `subject_did = holder_did`, which is right when a
    participant stores its own credentials and wrong for a credential *about
    somebody else*: every member credential would have been filed under the REC,
    and this route would return nothing for the person it is actually about.
    """
    from identity_registry.services import issuance

    subject = f"{ANCHOR}:users:bob"
    await issuance.store_delivered(
        db_session,
        holder_did=ANCHOR,
        issuer_did=ANCHOR,
        credentials=[
            {
                "format": "json-ld",
                "credentialType": "DataSubjectCredential",
                "payload": {
                    "id": "urn:uuid:c-2",
                    "type": ["VerifiableCredential", "DataSubjectCredential"],
                    "credentialSubject": {"id": subject},
                },
            }
        ],
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(Credential).where(Credential.id == "urn:uuid:c-2")
        )
    ).scalar_one()
    assert row.subject_did == subject, "the subject is the person, not the holder"


@pytest.mark.asyncio
async def test_an_instance_answers_for_a_person_it_holds_a_credential_about(
    client, db_session
):
    """Namespace is **not** the test here, and the first version of this got it
    wrong.

    A person is *named* by the organisation that onboarded them and may hold
    credentials from a relationship with another — `dual-user` is exactly that,
    and refusing on namespace hid a credential the consumer legitimately holds.
    What bounds the answer is what was delivered to this instance.
    """
    from identity_registry.services import issuance

    foreign_person = f"{OTHER}:users:dual"
    await issuance.store_delivered(
        db_session,
        holder_did=ANCHOR,
        issuer_did=ANCHOR,
        credentials=[
            {
                "format": "json-ld",
                "credentialType": "DataSubjectCredential",
                "payload": {
                    "id": "urn:uuid:c-3",
                    "type": ["VerifiableCredential", "DataSubjectCredential"],
                    "credentialSubject": {"id": foreign_person, "role": "ConsumerUser"},
                    "proof": {"jws": "eyJ.stub.sig"},
                },
            }
        ],
    )
    await db_session.commit()

    body = (
        await client.get(f"/users/{foreign_person}/credentials", headers=HEADERS)
    ).json()
    assert body["roles"] == ["ConsumerUser"]


@pytest.mark.asyncio
async def test_a_person_this_instance_holds_nothing_about_is_empty(client):
    """Not a 404: "I hold nothing for them" and "they do not exist" are
    different answers, and only the first is this instance's to give."""
    r = await client.get(f"/users/{OTHER}:users:stranger/credentials", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["credentials"] == []


@pytest.mark.asyncio
async def test_a_participant_did_is_not_a_person(client):
    r = await client.get(f"/users/{OTHER}/credentials", headers=HEADERS)
    assert r.status_code == 422
