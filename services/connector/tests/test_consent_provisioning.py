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
        json={"subject_id": SUBJECT, "offer_id": "test-incentives", "enabled": True},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_admin_shares_unknown_offer_422(client):
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={"subject_id": SUBJECT, "offer_id": "no-such-offer", "enabled": True},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_shares_requires_provision_scope(client):
    r = await client.post(
        "/consent/admin/shares",
        headers=make_headers(scope="connector.webhook"),
        json={"subject_id": SUBJECT, "offer_id": "test-flexibility", "enabled": True},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_shares_is_idempotent(engine, client):
    body = {"subject_id": SUBJECT, "offer_id": "test-flexibility", "enabled": True}
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
            "legal_basis": {"source": "onboarding", "submission_ref": "20260101-abc123"},
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
