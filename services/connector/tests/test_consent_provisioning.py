"""Block B — service-provisioned shares, the scoped wildcard, legal-basis evidence.

Covers §3.2 (``POST /consent/admin/shares``), §3.1 (the ``consumer_id = "*"``
wildcard and its precedence rules) and §3.3 (the ``legal_basis`` evidence
record round-tripping through the write and read paths).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    check_consent,
    get_granted_subject_ids,
)
from tests import make_headers

PROVISION = make_headers(scope="connector.consent.provision")
DATASET = "datasets.silver.meters"
CONSUMER = "did:web:consumer.dataspaces.localhost"
OTHER_CONSUMER = "did:web:other.dataspaces.localhost"
SUBJECT = "did:web:users.dataspaces.localhost:sub-001"

# The connector requires evidence to grant: a service asserting that someone
# consented, without proof of what they were shown, is indefensible. Tests that
# are about something else still have to send a valid record.
EVIDENCE = {
    "source": "test-harness",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "b" * 64,
}


@pytest.fixture(autouse=True)
def _allow_membership(monkeypatch):
    """The admin endpoint checks org membership against the IR; stub it True.

    The membership gate has its own coverage in ``test_membership_check``; here
    we assert the provisioning behaviour, not the network call.
    """
    async def _member(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        "connector.api.v1.consent.check_subject_membership", _member
    )


def _row(**overrides) -> ConsentRequestORM:
    base = dict(
        subject_id=SUBJECT,
        dataset_id=DATASET,
        consumer_id=WILDCARD_CONSUMER,
        status="granted",
        purpose=["FlexibilityResearch"],
        controller="example-org",
        controller_role=None,
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        transfer_ids=[],
    )
    base.update(overrides)
    return ConsentRequestORM(**base)


# ── §3.2 admin/shares ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_shares_expands_offer_to_wildcard_rows(client):
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": {
                "source": "onboarding",
                "rec_slug": "example",
                "consent_text_version": "1.0",
                "locale": "it",
                "rendered_text_sha256": "sha-of-shown-text",
                "submission_ref": "20260101-abc123",
            },
        },
    )
    assert r.status_code == 200
    rows = r.json()
    # The fixture offer resolves to exactly one dataset.
    assert len(rows) == 1
    row = rows[0]
    assert row["consumer_id"] == WILDCARD_CONSUMER
    assert row["status"] == "granted"
    assert row["purpose"] == ["FlexibilityResearch"]
    assert row["controller"] == "example-org"
    assert row["offer_id"] == "test-flexibility"

    lb = row["legal_basis"]
    # Server is authoritative for offer-derived fields.
    assert lb["offer_id"] == "test-flexibility"
    assert lb["basis_iri"] == "https://w3id.org/dpv#Consent"
    assert lb["controller"] == "example-org"
    assert lb["user_visible_hash"]
    # Caller-supplied evidence is carried through.
    assert lb["source"] == "onboarding"
    assert lb["submission_ref"] == "20260101-abc123"
    assert lb["rendered_text_sha256"] == "sha-of-shown-text"


@pytest.mark.asyncio
async def test_admin_shares_rejects_contract_offer(client):
    """A contract-based offer is disclosed, not consented — 409, no row."""
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-incentives",
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_admin_shares_unknown_offer_422(client):
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "no-such-offer",
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_shares_requires_provision_scope(client):
    r = await client.post(
        "/consent/admin/shares",
        headers=make_headers(scope="connector.webhook"),
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_shares_is_idempotent(engine, client):
    body = {
        "subject_id": SUBJECT,
        "offer_id": "test-flexibility",
        "enabled": True,
        "legal_basis": EVIDENCE,
    }
    first = await client.post("/consent/admin/shares", headers=PROVISION, json=body)
    second = await client.post("/consent/admin/shares", headers=PROVISION, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()[0]["id"] == second.json()[0]["id"]

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        count = await session.execute(select(func.count()).select_from(ConsentRequestORM))
    assert count.scalar_one() == 1


# ── §3.1 scoped wildcard ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wildcard_authorises_any_consumer(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(_row())

        granted = await get_granted_subject_ids(
            session, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )
        assert granted == [SUBJECT]
        # A different consumer is admitted by the same wildcard.
        granted_other = await get_granted_subject_ids(
            session, DATASET, OTHER_CONSUMER, purpose=["FlexibilityResearch"]
        )
        assert granted_other == [SUBJECT]


@pytest.mark.asyncio
async def test_specific_revoke_overrides_wildcard(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(_row())  # standing wildcard grant
            session.add(
                _row(
                    consumer_id=CONSUMER,
                    status="revoked",
                    requested_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                    revoked_at=datetime(2026, 2, 1, 1, tzinfo=timezone.utc),
                )
            )

        # The opted-out consumer is denied despite the wildcard.
        granted = await get_granted_subject_ids(
            session, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )
        assert granted == []
        # Every other consumer still rides the wildcard.
        granted_other = await get_granted_subject_ids(
            session, DATASET, OTHER_CONSUMER, purpose=["FlexibilityResearch"]
        )
        assert granted_other == [SUBJECT]


@pytest.mark.asyncio
async def test_specific_grant_authorises_without_wildcard(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(_row(consumer_id=CONSUMER))

        allowed, _ = await check_consent(
            session, SUBJECT, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )
        assert allowed is True


@pytest.mark.asyncio
async def test_wildcard_purpose_must_match(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(_row(purpose=["FlexibilityResearch"]))

        # Sibling purpose, not narrower — denied.
        granted = await get_granted_subject_ids(
            session, DATASET, CONSUMER, purpose=["IncentiveCalculation"]
        )
        assert granted == []


@pytest.mark.asyncio
async def test_wildcard_controller_role_must_match(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(_row(controller_role="community-operator"))

        allowed, _ = await check_consent(
            session,
            SUBJECT,
            DATASET,
            CONSUMER,
            purpose=["FlexibilityResearch"],
            controller_role="metering-operator",
        )
        assert allowed is False


# ── §3.3 legal-basis evidence surfaces on the read path ───────────────────────

@pytest.mark.asyncio
async def test_legal_basis_surfaces_in_internal_check(client):
    await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": {
                **EVIDENCE,
                "source": "onboarding",
                "submission_ref": "20260101-abc123",
            },
        },
    )

    internal = make_headers(scope="connector.internal")
    r = await client.get(
        "/internal/consent/check",
        params={
            "subject_id": SUBJECT,
            "dataset_id": DATASET,
            "consumer_id": CONSUMER,
            "purpose": "FlexibilityResearch",
        },
        headers=internal,
    )
    assert r.status_code == 200
    body = r.json()
    # The wildcard row decides for a consumer with no specific row of its own.
    assert body["consent_active"] is True
    assert body["legal_basis"]["offer_id"] == "test-flexibility"
    assert body["legal_basis"]["submission_ref"] == "20260101-abc123"


# ── the subject's own decision carries the same evidence ─────────────────────

@pytest.mark.asyncio
async def test_subject_offer_share_records_legal_basis(client):
    """A decision made in the portal is no less in need of proof than one made in
    the onboarding wizard.

    Without this, `legal_basis` was populated only for service-provisioned
    consent, so for every subject who used the portal there was no record of
    *which* consent text they saw — which is exactly what `user_visible_hash`
    exists to prove (Art. 7(1)).
    """
    from tests import make_vc_headers

    subject = make_vc_headers()
    r = await client.post(
        "/consent/my/shares",
        headers=subject,
        json={"offer_id": "test-flexibility", "enabled": True},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1

    lb = rows[0]["legal_basis"]
    assert lb is not None, "the subject's own decision must carry an evidence record"
    # Everything here is derived from the resolved offer server-side: the caller
    # supplies none of it, so the portal cannot drift from what was shown.
    assert lb["offer_id"] == "test-flexibility"
    assert lb["basis_iri"] == "https://w3id.org/dpv#Consent"
    assert lb["controller"] == "example-org"
    assert lb["consent_text_version"]
    assert lb["user_visible_hash"]


# ── §7 the external-application write contract ────────────────────────────────

@pytest.mark.asyncio
async def test_granting_without_evidence_is_refused(client):
    """A service asserting that someone consented, with no record of what they
    were shown, produces a consent nobody can defend later."""
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={"subject_id": SUBJECT, "offer_id": "test-flexibility", "enabled": True},
    )
    assert r.status_code == 422
    assert "legal_basis is required" in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["source", "consent_text_version", "rendered_text_sha256"])
async def test_partial_evidence_is_refused(client, missing):
    """Each of the three carries part of the proof: which system asked, which
    revision, and the exact bytes displayed. Any one missing and the record cannot
    tie a decision to a rendering."""
    evidence = {k: v for k, v in EVIDENCE.items() if k != missing}
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": evidence,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_withdrawal_needs_no_evidence(client):
    """A person may always stop. Requiring proof to stop would be the wrong way
    round — and would make withdrawal harder than consent."""
    await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={"subject_id": SUBJECT, "offer_id": "test-flexibility", "enabled": False},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_an_email_in_an_opaque_reference_is_refused(client):
    """These fields are opaque references by contract. An address here would put a
    person's identity into the connector's database, which is exactly what the
    codes-and-hashes rule exists to prevent."""
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": {**EVIDENCE, "submission_ref": "alice@example.test"},
        },
    )
    assert r.status_code == 422
    assert "opaque reference" in r.text


# ── two offers over one dataset ───────────────────────────────────────────────
#
# Found by the portal UI journeys, not by unit tests: a subject who had already
# granted one offer clicked "Share" on a second one, got 200 OK, and the page
# still showed "not shared". Both offers name the same dataset, and the decision
# was keyed on the dataset alone — so the second grant collided with the first.

OFFER_A = "test-flexibility"
OFFER_B = "test-grid-planning"


@pytest.mark.asyncio
async def test_granting_a_second_offer_on_the_same_dataset_is_recorded(client):
    """Two offers over one dataset are two questions, not one.

    Agreeing to share meter data for flexibility research is not agreeing to
    share it for community operation: different purpose, different controller.
    Keyed on the dataset, the second grant silently returned the first row and
    recorded nothing — the subject believed they had consented, and no evidence
    existed either way.
    """
    from tests import make_vc_headers

    subject = make_vc_headers()
    for offer in (OFFER_A, OFFER_B):
        r = await client.post(
            "/consent/my/shares",
            headers=subject,
            json={"offer_id": offer, "enabled": True},
        )
        assert r.status_code == 200, r.text

    rows = (await client.get("/consent/my/shares", headers=subject)).json()
    by_offer = {r["offer_id"]: r for r in rows}
    assert by_offer.keys() >= {OFFER_A, OFFER_B}, "both decisions must be visible"
    assert by_offer[OFFER_A]["status"] == "granted"
    assert by_offer[OFFER_B]["status"] == "granted"
    # Each carries its own offer's purpose and controller, not the other's.
    assert by_offer[OFFER_A]["purpose"] == ["FlexibilityResearch"]
    assert by_offer[OFFER_B]["purpose"] == ["EnergyCommunityOperation"]
    assert by_offer[OFFER_B]["controller"] == "grid-operator"


@pytest.mark.asyncio
async def test_withdrawing_one_offer_leaves_the_other_granted(client):
    """The dangerous direction: withdrawal must not revoke a different purpose."""
    from tests import make_vc_headers

    subject = make_vc_headers()
    for offer in (OFFER_A, OFFER_B):
        await client.post(
            "/consent/my/shares",
            headers=subject,
            json={"offer_id": offer, "enabled": True},
        )

    r = await client.post(
        "/consent/my/shares",
        headers=subject,
        json={"offer_id": OFFER_B, "enabled": False},
    )
    assert r.status_code == 200, r.text

    rows = (await client.get("/consent/my/shares", headers=subject)).json()
    by_offer = {r["offer_id"]: r for r in rows}
    assert by_offer[OFFER_B]["status"] == "revoked"
    assert by_offer[OFFER_A]["status"] == "granted", (
        "stopping one purpose must not silently withdraw another"
    )


# ── T29 — an evidence record rejects what it cannot record ────────


@pytest.mark.asyncio
async def test_admin_shares_rejects_unknown_evidence_field(client):
    """Pydantic's default would accept, drop and answer 200.

    That is the worst outcome an evidence model can produce: the caller comes
    away holding written proof the connector never stored. A 422 says so.
    """
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": {**EVIDENCE, "evidence_document_ref": "DOC-1"},
        },
    )
    assert r.status_code == 422, r.text
    assert "evidence_document_ref" in r.text


@pytest.mark.asyncio
async def test_admin_shares_rejects_a_server_owned_field(client):
    """`user_visible_hash` is the connector's to compute from the resolved
    offer. A caller sending one has misunderstood who owns it — and silently
    ignoring it looked like agreement."""
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": {**EVIDENCE, "user_visible_hash": "deadbeef"},
        },
    )
    assert r.status_code == 422, r.text
