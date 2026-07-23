"""Tests for the consent vocabulary: validation on write, enforcement on read.

The vocabulary fixtures live in ``tests/fixtures`` — ``datasets.silver.meters``
is consent-gated PII declaring the purposes
{EnergyCommunityOperation, IncentiveCalculation, FlexibilityResearch};
``datasets.gold.weather`` is open and non-personal.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests import make_headers, make_vc_headers
from connector.db.models import ConsentRequestORM
from connector.services import consent_vocabulary as vocab
from connector.services.consent_service import (
    check_consent,
    create_consent_request,
    get_granted_subject_ids,
    set_subject_data_sharing,
)

HEADERS = make_headers(scope="connector.internal")
SUBJECT = make_vc_headers()
SUBJECT_DID = SUBJECT["X-Subject-Id"]

PII = "datasets.silver.meters"
OPEN = "datasets.gold.weather"


async def _grant(engine, **overrides):
    """Persist one granted consent row."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    row = {
        "subject_id": "sub-001",
        "consumer_id": "consumer",
        "dataset_id": PII,
        "purpose": ["FlexibilityResearch"],
        "status": "granted",
        "requested_at": now,
        "decided_at": now,
        "transfer_ids": [],
    }
    row.update(overrides)
    async with factory() as session:
        async with session.begin():
            session.add(ConsentRequestORM(**row))


# ── Validation on the write path ─────────────────────────────────────────────


class TestWriteValidation:
    @pytest.mark.asyncio
    async def test_unknown_dataset_is_rejected(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            with pytest.raises(vocab.VocabularyError):
                await create_consent_request(
                    session,
                    subject_id="sub-001",
                    consumer_id="consumer",
                    dataset_id="datasets.silver.ghost",
                )

    @pytest.mark.asyncio
    async def test_out_of_taxonomy_purpose_is_rejected(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            with pytest.raises(vocab.VocabularyError):
                await set_subject_data_sharing(
                    session,
                    subject_id="sub-001",
                    dataset_id=PII,
                    consumer_id="consumer",
                    enabled=True,
                    purpose=["WhateverWeFeelLike"],
                )

    @pytest.mark.asyncio
    async def test_purposes_are_stored_as_slugs(self, engine):
        """A full IRI and a slug denote the same concept and must not both persist."""
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            async with session.begin():
                consent = await set_subject_data_sharing(
                    session,
                    subject_id="sub-001",
                    dataset_id=PII,
                    consumer_id="consumer",
                    enabled=True,
                    purpose=[
                        "FlexibilityResearch",
                        vocab.get_profile().purpose_iri("FlexibilityResearch"),
                    ],
                )
        assert consent.purpose == ["FlexibilityResearch"]

    @pytest.mark.asyncio
    async def test_api_returns_422_for_unknown_dataset(self, client):
        r = await client.post(
            "/consent/my/shares",
            json={"dataset_id": "datasets.silver.ghost", "enabled": True},
            headers=SUBJECT,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_api_returns_422_for_unknown_purpose(self, client):
        r = await client.post(
            "/consent/my/shares",
            json={"dataset_id": PII, "enabled": True, "purpose": ["Nope"]},
            headers=SUBJECT,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_share_requires_a_dataset_or_an_offer(self, client):
        r = await client.post(
            "/consent/my/shares",
            json={"enabled": True},
            headers=SUBJECT,
        )
        assert r.status_code == 422


# ── Enforcement ──────────────────────────────────────────────────────────────


class TestPurposeEnforcement:
    @pytest.mark.asyncio
    async def test_narrower_purpose_is_allowed(self, engine):
        """Consent to the parent covers a narrower request (odrl:isA)."""
        await _grant(engine, purpose=["EnergyCommunityOperation"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, _ = await check_consent(
                session, "sub-001", PII, "consumer", purpose=["FlexibilityResearch"]
            )
        assert active

    @pytest.mark.asyncio
    async def test_broader_purpose_is_denied(self, engine):
        """Consent to a child does not cover its parent — that would widen it."""
        await _grant(engine, purpose=["FlexibilityResearch"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, reason = await check_consent(
                session, "sub-001", PII, "consumer", purpose=["EnergyCommunityOperation"]
            )
        assert not active
        assert "not covered" in reason

    @pytest.mark.asyncio
    async def test_sibling_purpose_is_denied(self, engine):
        await _grant(engine, purpose=["FlexibilityResearch"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, _ = await check_consent(
                session, "sub-001", PII, "consumer", purpose=["IncentiveCalculation"]
            )
        assert not active

    @pytest.mark.asyncio
    async def test_empty_requested_purpose_is_denied_for_pii(self, engine):
        """An absent purpose means the caller never said why it wants the data."""
        await _grant(engine)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, reason = await check_consent(session, "sub-001", PII, "consumer")
        assert not active
        assert "no purpose declared" in reason

    @pytest.mark.asyncio
    async def test_empty_consented_purpose_is_denied_for_pii(self, engine):
        """Empty is never 'unrestricted': the person was never told the use."""
        await _grant(engine, purpose=[])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, reason = await check_consent(
                session, "sub-001", PII, "consumer", purpose=["FlexibilityResearch"]
            )
        assert not active
        assert "records no purpose" in reason

    @pytest.mark.asyncio
    async def test_open_dataset_needs_no_purpose(self, engine):
        """No data subject, so the question does not arise."""
        await _grant(engine, dataset_id=OPEN, purpose=[])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, _ = await check_consent(session, "sub-001", OPEN, "consumer")
        assert active

    @pytest.mark.asyncio
    async def test_unknown_dataset_fails_closed(self, engine):
        await _grant(engine, dataset_id="datasets.silver.ghost", purpose=[])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, _ = await check_consent(
                session, "sub-001", "datasets.silver.ghost", "consumer"
            )
        assert not active


class TestControllerRoleEnforcement:
    @pytest.mark.asyncio
    async def test_matching_role_is_allowed(self, engine):
        await _grant(engine, controller="example-org", controller_role="community-operator")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, _ = await check_consent(
                session,
                "sub-001",
                PII,
                "consumer",
                purpose=["FlexibilityResearch"],
                controller_role="community-operator",
            )
        assert active

    @pytest.mark.asyncio
    async def test_different_role_is_denied(self, engine):
        """Controller ≠ legal entity: two roles of one company are two controllers."""
        await _grant(engine, controller="example-org", controller_role="community-operator")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            active, reason = await check_consent(
                session,
                "sub-001",
                PII,
                "consumer",
                purpose=["FlexibilityResearch"],
                controller_role="metering",
            )
        assert not active
        assert "controller role" in reason


class TestRowFiltering:
    @pytest.mark.asyncio
    async def test_row_filter_excludes_subjects_who_consented_to_another_purpose(self, engine):
        await _grant(engine, subject_id="sub-consented", purpose=["FlexibilityResearch"])
        await _grant(engine, subject_id="sub-other", purpose=["IncentiveCalculation"])
        await _grant(engine, subject_id="sub-silent", purpose=[])

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            granted = await get_granted_subject_ids(
                session, PII, "consumer", purpose=["FlexibilityResearch"]
            )
        assert granted == ["sub-consented"]

    @pytest.mark.asyncio
    async def test_revoked_row_never_appears(self, engine):
        await _grant(engine, subject_id="sub-consented")
        await _grant(
            engine,
            subject_id="sub-consented",
            status="revoked",
            requested_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            revoked_at=datetime(2030, 1, 2, tzinfo=timezone.utc),
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            granted = await get_granted_subject_ids(
                session, PII, "consumer", purpose=["FlexibilityResearch"]
            )
        assert granted == []


class TestInternalCheckEndpoint:
    @pytest.mark.asyncio
    async def test_purpose_reaches_the_check(self, engine, client):
        await _grant(engine, purpose=["FlexibilityResearch"])

        allowed = await client.get(
            "/internal/consent/check",
            params={
                "subject_id": "sub-001",
                "dataset_id": PII,
                "consumer_id": "consumer",
                "purpose": "FlexibilityResearch",
            },
            headers=HEADERS,
        )
        assert allowed.json()["consent_active"] is True

        denied = await client.get(
            "/internal/consent/check",
            params={
                "subject_id": "sub-001",
                "dataset_id": PII,
                "consumer_id": "consumer",
                "purpose": "IncentiveCalculation",
            },
            headers=HEADERS,
        )
        assert denied.json()["consent_active"] is False

    @pytest.mark.asyncio
    async def test_comma_separated_purposes_are_accepted(self, engine, client):
        """The negotiated offer may permit several purposes; any match suffices."""
        await _grant(engine, purpose=["FlexibilityResearch"])
        r = await client.get(
            "/internal/consent/check",
            params={
                "dataset_id": PII,
                "consumer_id": "consumer",
                "purpose": "IncentiveCalculation,FlexibilityResearch",
            },
            headers=HEADERS,
        )
        assert r.json()["subject_ids"] == ["sub-001"]

    @pytest.mark.asyncio
    async def test_unknown_purpose_is_422(self, client):
        r = await client.get(
            "/internal/consent/check",
            params={"dataset_id": PII, "consumer_id": "consumer", "purpose": "Nope"},
            headers=HEADERS,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_pii_without_purpose_returns_no_subjects(self, engine, client):
        await _grant(engine, purpose=["FlexibilityResearch"])
        r = await client.get(
            "/internal/consent/check",
            params={"dataset_id": PII, "consumer_id": "consumer"},
            headers=HEADERS,
        )
        assert r.json()["subject_ids"] == []


# ── /ns/sharing-offers ───────────────────────────────────────────────────────


class TestSharingOffersEndpoint:
    @pytest.mark.asyncio
    async def test_offers_are_public(self, client):
        r = await client.get("/ns/sharing-offers")
        assert r.status_code == 200
        assert {o["id"] for o in r.json()} == {"test-flexibility", "test-incentives"}

    @pytest.mark.asyncio
    async def test_public_projection_omits_dataset_keys(self, client):
        body = (await client.get("/ns/sharing-offers")).json()
        offer = next(o for o in body if o["id"] == "test-flexibility")
        assert "datasets" not in offer
        assert offer["dataset_count"] == 1

    @pytest.mark.asyncio
    async def test_projection_serves_codes_and_english_fallback(self, client):
        body = (await client.get("/ns/sharing-offers")).json()
        offer = next(o for o in body if o["id"] == "test-flexibility")
        assert offer["purpose"] == "FlexibilityResearch"
        assert offer["purpose_broader"] == ["EnergyCommunityOperation"]
        assert offer["resolution"] == "PT15M"
        assert offer["measures"] == ["consumption"]
        assert offer["recipients"]["processors"]["category"] == "appointed-service-providers"
        assert offer["fallback_text_en"]["purpose_label"]
        assert offer["user_visible_hash"]

    @pytest.mark.asyncio
    async def test_contract_based_offer_is_flagged_as_disclosure(self, client):
        body = (await client.get("/ns/sharing-offers")).json()
        offer = next(o for o in body if o["id"] == "test-incentives")
        assert offer["requires_consent"] is False


class TestOfferDrivenShares:
    @pytest.mark.asyncio
    async def test_offer_expands_to_rows_with_purpose_and_controller(self, client):
        r = await client.post(
            "/consent/my/shares",
            json={"offer_id": "test-flexibility", "enabled": True},
            headers=SUBJECT,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["dataset_id"] == PII
        assert rows[0]["purpose"] == ["FlexibilityResearch"]
        assert rows[0]["controller"] == "example-org"
        assert rows[0]["offer_id"] == "test-flexibility"

    @pytest.mark.asyncio
    async def test_contract_based_offer_cannot_be_toggled(self, client):
        """Offering a control the legal basis does not support invalidates consent."""
        r = await client.post(
            "/consent/my/shares",
            json={"offer_id": "test-incentives", "enabled": True},
            headers=SUBJECT,
        )
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_unknown_offer_is_422(self, client):
        r = await client.post(
            "/consent/my/shares",
            json={"offer_id": "nope", "enabled": True},
            headers=SUBJECT,
        )
        assert r.status_code == 422
