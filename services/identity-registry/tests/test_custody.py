"""`DID-12` — the invariant the whole decentralization pass exists to make true.

An instance holds the private key of its own DID and of nothing else. Everything
else in `DID-04`…`DID-11` is machinery for making that so; this is what says
whether it *is*.

The interesting tests are not the ones where custody is clean. They are the ones
where a foreign key is **planted** — because a sweep that has never been shown a
violation is indistinguishable from one that cannot see them, which is the
failure mode this ledger keeps finding.
"""

from __future__ import annotations

import pytest
from conftest import register_enrolled, register_holder
from sqlalchemy import text

from identity_registry.config import Settings, get_settings
from identity_registry.db.models import Did, Key
from identity_registry.roles import PARTICIPANT, TRUST_ANCHOR
from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair
from identity_registry.services.custody import audit_custody, describe

ANCHOR = "did:web:trust-anchor.dataspaces.localhost"
OTHER = "did:web:provider.dataspaces.localhost"
SUBJECT = "did:web:users.dataspaces.localhost:alice"


def anchor_settings(**overrides) -> Settings:
    base = {"oidc_issuer_url": None, "role": TRUST_ANCHOR}
    base.update(overrides)
    return Settings(_env_file=None, **base)


async def _hold_private_key(db, did: str, did_type: str = "participant"):
    """Give this instance a usable private key for *did*."""
    kp = generate_key_pair(did)
    key = Key(
        owner_did=did,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(key)
    await db.flush()
    existing = await db.execute(
        text("SELECT 1 FROM dids WHERE did = :d"), {"d": did}
    )
    if existing.first() is None:
        db.add(Did(did=did, did_type=did_type, key_id=key.id))
    await db.commit()
    return key


# ── Clean custody ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_anchor_holding_only_its_own_key_is_clean(db_session):
    await _hold_private_key(db_session, ANCHOR)
    report = await audit_custody(db_session, anchor_settings())

    assert report.ok
    assert [k.did for k in report.own] == [ANCHOR]
    assert report.foreign == []


@pytest.mark.asyncio
async def test_an_enrolled_participants_public_key_is_not_custody(db_session):
    """The row enrolment leaves: a key this instance knows and cannot use."""
    await _hold_private_key(db_session, ANCHOR)
    await register_enrolled(db_session, OTHER)

    report = await audit_custody(db_session, anchor_settings())
    assert report.ok
    assert [k.did for k in report.foreign] == []


@pytest.mark.asyncio
async def test_a_participant_instance_holds_its_own(db_session):
    """The same invariant from the other side."""
    await _hold_private_key(db_session, OTHER)
    report = await audit_custody(
        db_session, anchor_settings(role=PARTICIPANT, participant_did=OTHER)
    )
    assert report.ok
    assert [k.did for k in report.own] == [OTHER]


# ── A planted violation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_foreign_private_key_is_caught(db_session):
    """The case the sweep exists for: this instance can sign as somebody else."""
    await _hold_private_key(db_session, ANCHOR)
    await _hold_private_key(db_session, OTHER)

    report = await audit_custody(db_session, anchor_settings())

    assert not report.ok
    assert [k.did for k in report.foreign] == [OTHER]
    lines = describe(report, anchor_settings())
    assert any(OTHER in line and "can sign as" in line for line in lines)


@pytest.mark.asyncio
async def test_a_rotated_out_key_still_counts(db_session):
    """`active` is not the question.

    A rotated-out key still decrypts and still signs. "We stopped using it" is
    not "we cannot use it", and a sweep that filtered on `active` would report
    clean custody for a registry that can still speak as a participant.
    """
    await _hold_private_key(db_session, ANCHOR)
    key = await _hold_private_key(db_session, OTHER)
    key.active = False
    await db_session.commit()

    report = await audit_custody(db_session, anchor_settings())
    assert [k.did for k in report.foreign] == [OTHER]


@pytest.mark.asyncio
async def test_a_participant_instance_holding_the_anchors_key_is_caught(db_session):
    """Symmetry: a participant that could sign as the trust anchor is worse."""
    await _hold_private_key(db_session, OTHER)
    await _hold_private_key(db_session, ANCHOR)

    report = await audit_custody(
        db_session, anchor_settings(role=PARTICIPANT, participant_did=OTHER)
    )
    assert [k.did for k in report.foreign] == [ANCHOR]


# ── The declared exception, reported rather than hidden ───────────


@pytest.mark.asyncio
async def test_a_data_subject_key_is_a_named_deviation_not_a_violation(db_session):
    """`D-49`/`DID-11` — deferred, and therefore *reported* every start.

    The anchor still generates a keypair for every data subject. That is a known
    deviation, so it must not fail the sweep — and it must not be invisible
    either, or the deviation quietly becomes the design.
    """
    await _hold_private_key(db_session, ANCHOR)
    await _hold_private_key(db_session, SUBJECT, did_type="user")

    settings = anchor_settings()
    report = await audit_custody(db_session, settings)

    assert report.ok
    assert [k.did for k in report.subjects] == [SUBJECT]
    lines = describe(report, settings)
    assert any(SUBJECT in line and "D-49" in line for line in lines)


# ── It reads SQL, and that is load-bearing ────────────────────────


@pytest.mark.asyncio
async def test_a_json_null_private_key_does_not_read_as_held(db_session):
    """The `none_as_null` defect, pinned where it actually mattered.

    Before migration `0014`, an enrolled participant's `private_jwk` was the JSON
    value `'null'` rather than SQL NULL — so `IS NULL` was False and this sweep
    would have reported **every enrolled participant as a custody violation**,
    on Postgres only. The type is fixed; this asserts the sweep's own reading
    agrees with it.
    """
    await _hold_private_key(db_session, ANCHOR)
    await register_enrolled(db_session, OTHER)

    stored = (
        await db_session.execute(
            text("SELECT private_jwk IS NULL FROM keys WHERE owner_did = :d"),
            {"d": OTHER},
        )
    ).scalar_one()
    assert stored is True or stored == 1

    report = await audit_custody(db_session, anchor_settings())
    assert report.ok


@pytest.mark.asyncio
async def test_a_key_with_no_did_row_is_still_foreign(db_session):
    """Fail closed on a row the join cannot classify.

    A `keys` row whose DID was deleted has no `did_type`, so it cannot be
    excused as a data subject. Treating an unclassifiable key as safe is how a
    sweep becomes decoration.
    """
    await _hold_private_key(db_session, ANCHOR)
    kp = generate_key_pair(OTHER)
    db_session.add(
        Key(
            owner_did=OTHER,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(
                kp.private_jwk, get_settings().encryption_key
            ),
            public_jwk=kp.public_jwk,
        )
    )
    await db_session.commit()

    report = await audit_custody(db_session, anchor_settings())
    assert [k.did for k in report.foreign] == [OTHER]
    assert report.foreign[0].did_type == "unknown"


# ── The holder fixture must not itself be a violation ─────────────


@pytest.mark.asyncio
async def test_the_holder_fixture_is_clean_on_its_own_instance(db_session):
    """`register_holder` is what a participant instance looks like.

    If it read as a violation there, every test using it would be modelling the
    defect rather than the design.
    """
    await register_holder(db_session, OTHER)
    report = await audit_custody(
        db_session, anchor_settings(role=PARTICIPANT, participant_did=OTHER)
    )
    assert report.ok


# ── `D-49` step 1: a subject has no key to hold ───────────────────


@pytest.mark.asyncio
async def test_issuing_to_a_data_subject_creates_no_key(client, db_session):
    """The deviation the sweep used to report, removed at source.

    The anchor generated an EC P-256 keypair for every person onboarded and kept
    the private half. Nothing read it: a subject presents nothing and signs
    nothing, and their credential is verified against the **anchor's** key. So
    it was custody with no purpose — an impersonation surface with no upside.
    """
    from conftest import make_admin_headers

    await _hold_private_key(db_session, ANCHOR)
    r = await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": "alice",
            "role": "DataSubject",
            "verified_by": "riverside-rec",
            "verification_method": "phone-otp",
        },
        headers=make_admin_headers(),
    )
    assert r.status_code == 201, r.text
    subject_did = r.json()["subjectDid"]

    held = (
        await db_session.execute(
            text("SELECT count(*) FROM keys WHERE owner_did = :d"), {"d": subject_did}
        )
    ).scalar_one()
    assert held == 0

    report = await audit_custody(db_session, anchor_settings())
    assert report.ok
    assert report.subjects == [], "no subject key means no deviation to report"


@pytest.mark.asyncio
async def test_a_subject_did_still_resolves(client, db_session):
    """`personal-data.md` `D-22`. The DID is what consent and provenance point at.

    A document with no verification method is the honest one for somebody who
    presents nothing — and it must still resolve, or every reference to the
    subject dangles.
    """
    from conftest import make_admin_headers

    await _hold_private_key(db_session, ANCHOR)
    created = await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": "alice", "role": "DataSubject"},
        headers=make_admin_headers(),
    )
    subject_did = created.json()["subjectDid"]

    r = await client.get(f"/dids/{subject_did}/did.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["id"] == subject_did
    assert "verificationMethod" not in doc
    assert "authentication" not in doc


@pytest.mark.asyncio
async def test_the_credential_records_who_attested_the_person(client, db_session):
    """`D-53` — assurance is delegated, so it is *recorded* rather than claimed."""
    from conftest import make_admin_headers

    await _hold_private_key(db_session, ANCHOR)
    created = await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": "alice",
            "role": "DataSubject",
            "verified_by": "riverside-rec",
            "verification_method": "phone-otp",
        },
        headers=make_admin_headers(),
    )
    cred_id = created.json()["credentialId"]

    vc = (
        await client.get(f"/admin/credentials/{cred_id}", headers=make_admin_headers())
    ).json()
    subject = vc["credentialSubject"]
    assert subject["verifiedBy"] == "riverside-rec"
    assert subject["verificationMethod"] == "phone-otp"


@pytest.mark.asyncio
async def test_a_participant_did_with_no_key_still_does_not_resolve(client, db_session):
    """The exception is for **users**, and only users.

    A keyless participant DID means this registry recorded that a party exists
    without being shown a key — so it is not the one that publishes their
    document, and `P-6` still refuses.
    """
    from conftest import make_headers

    # `POST /admin/participants` records a party it has never been shown a key
    # for: a DID row with **no key at all** (`D-51`). That is the case here —
    # `register_did` would give it a public key, which the anchor *may* serve.
    registered = await client.post(
        "/admin/participants",
        json={"did": OTHER, "roles": ["consumer"]},
        headers=make_headers(),
    )
    assert registered.status_code == 201

    r = await client.get(f"/dids/{OTHER}/did.json", headers=make_headers())
    assert r.status_code == 404
