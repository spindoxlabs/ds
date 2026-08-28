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
CONSUMER = "did:web:third-party.dataspaces.localhost"
OTHER_CONSUMER = "did:web:other.dataspaces.localhost"
SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"

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

@pytest.mark.rule("D-14")
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


@pytest.mark.rule("D-20")
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


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_admin_shares_refuses_an_anonymous_caller(client):
    """The perimeter, asserted from outside it.

    This route's production caller is out of repo (`svc-ds-onboarding`), so no
    in-repo change can break it in a way a caller-side test would catch — what
    this side owns is the perimeter, and the 403 above only proves that *some*
    token is rejected. Unauthenticated is the case that matters: this route
    writes a standing consent decision on a named person's behalf, and the one
    thing it must never do is accept that claim from nobody in particular.
    """
    r = await client.post(
        "/consent/admin/shares",
        json={
            "subject_id": SUBJECT,
            "offer_id": "test-flexibility",
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 401


@pytest.mark.rule("P-4")
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

@pytest.mark.rule("D-14")
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


@pytest.mark.rule("D-15", "A-10")
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


@pytest.mark.rule("D-15")
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


@pytest.mark.rule("D-14")
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


@pytest.mark.rule("D-11", "D-14")
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

@pytest.mark.rule("D-12")
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

@pytest.mark.rule("D-12")
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

@pytest.mark.rule("D-12")
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


@pytest.mark.rule("D-12")
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


@pytest.mark.rule("D-12")
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


@pytest.mark.rule("D-2", "D-12")
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


@pytest.mark.rule("D-15")
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


@pytest.mark.rule("D-12")
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


# ── §3.2 admin/shares, read side ──────────────────────────────────────────────
#
# `GET /consent/admin/shares` — who currently consents to an offer, for the
# consumer a disclosure is for. The read counterpart to the provisioning POST
# above, and the pair is the point: onboarding could write a standing consent
# and could not read one back, so an export ran against a decision it could not
# see. Guarded by `connector.consent.audience`, a scope distinct from the
# `.provision` write beside it.

AUDIENCE = make_headers(scope="connector.consent.audience")
ADMIN = make_headers(scope="connector.admin")


async def _provision(client, subject_id: str = SUBJECT, offer: str = "test-flexibility"):
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": subject_id,
            "offer_id": offer,
            "enabled": True,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_audience_returns_the_provisioned_subjects_per_dataset(client):
    """The round trip the route exists for: provision, then read back.

    The subject sets are keyed per resolved dataset and never flattened. The
    fixture offer resolves to one dataset today, so a caller reading the first
    element would be right until a second dataset declared the same offer — the
    shape is asserted here so that day changes the answer rather than the caller.
    """
    await _provision(client)

    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-flexibility", "consumer_id": CONSUMER},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offer_id"] == "test-flexibility"
    assert body["consumer_id"] == CONSUMER
    # Stamped from the offer, never supplied by the caller.
    assert body["purpose"] == ["FlexibilityResearch"]
    assert body["controller_role"] is None
    assert body["datasets"] == [
        {"dataset_id": DATASET, "subject_ids": [SUBJECT], "subject_count": 1}
    ]


@pytest.mark.rule("D-15", "A-10")
@pytest.mark.asyncio
async def test_audience_omits_a_subject_who_opted_out_of_this_consumer(engine, client):
    """The defect this route exists to prevent, asserted end to end.

    A per-party opt-out beats the standing wildcard (§3.1). A caller that could
    only see the wildcard set would disclose to a recipient this person has
    specifically withdrawn from — so the opted-out subject must be **absent**
    for that consumer while the wildcard still authorises every other one.
    """
    await _provision(client)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(
                _row(
                    consumer_id=CONSUMER,
                    status="revoked",
                    requested_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                    revoked_at=datetime(2026, 2, 1, 1, tzinfo=timezone.utc),
                )
            )

    opted_out = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-flexibility", "consumer_id": CONSUMER},
    )
    assert opted_out.status_code == 200
    assert opted_out.json()["datasets"][0]["subject_ids"] == []

    still_granted = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-flexibility", "consumer_id": OTHER_CONSUMER},
    )
    assert still_granted.status_code == 200
    assert still_granted.json()["datasets"][0]["subject_ids"] == [SUBJECT]


@pytest.mark.asyncio
async def test_audience_requires_a_consumer(client):
    """No default, because the default would be wrong.

    Omitting the consumer would leave `get_granted_subject_ids` loading only
    wildcard rows, so every per-party opt-out would be invisible and the answer
    would name people who had withdrawn. Refused rather than defaulted.
    """
    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-flexibility"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_audience_refuses_the_wildcard_as_a_consumer(client):
    """`*` is the standing row, not a recipient.

    Passing it would read the wildcard set alone — the same blind spot as
    omitting the parameter, reached through a value the schema would otherwise
    accept.
    """
    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-flexibility", "consumer_id": WILDCARD_CONSUMER},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_audience_unknown_offer_is_422_not_an_empty_200(client):
    """The footgun on `GET /internal/consent/check`, closed here.

    That route answers `{"subject_ids": []}` with a 200 when it cannot resolve
    the question, and "nobody consents" is indistinguishable from "you asked
    wrong". A mis-keyed offer must refuse.
    """
    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "no-such-offer", "consumer_id": CONSUMER},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_audience_rejects_contract_offer(client):
    """A contract-based offer is disclosed, not consented — 409, as on the POST.

    Returning an audience for it would imply a consent decision that nobody was
    ever asked to make.
    """
    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": "test-incentives", "consumer_id": CONSUMER},
    )
    assert r.status_code == 409


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_audience_reachable_by_connector_admin(client):
    """Administrative authority over this participant's own consent records.

    `require_permission`, not `require_exact_permission` — the same superset
    `require_consent_provision` beside it allows.
    """
    await _provision(client)
    r = await client.get(
        "/consent/admin/shares",
        headers=ADMIN,
        params={"offer_id": "test-flexibility", "consumer_id": CONSUMER},
    )
    assert r.status_code == 200
    assert r.json()["datasets"][0]["subject_ids"] == [SUBJECT]


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_provision_scope_alone_does_not_reach_the_audience(client):
    """The whole reason `.audience` is a new scope rather than a reuse.

    `connector.consent.provision` is in the `ds-participant-admin` bundle, so
    reusing it would hand every participant operator bulk subject enumeration as
    a side effect of holding a *write* grant. If this test ever goes green by
    accident, that disclosure has been made by nobody on purpose.
    """
    r = await client.get(
        "/consent/admin/shares",
        headers=PROVISION,
        params={"offer_id": "test-flexibility", "consumer_id": CONSUMER},
    )
    assert r.status_code == 403


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_audience_refuses_an_anonymous_caller(client):
    """The perimeter, from outside it.

    A cross-subject read is a distinct capability in this codebase — even an
    authenticated data subject is refused another subject's decisions by
    `GET /consent/status`. Unauthenticated must not reach a list of all of them.
    """
    r = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": CONSUMER},
    )
    assert r.status_code == 401


@pytest.mark.rule("D-20", "E2E-03")
@pytest.mark.asyncio
async def test_audience_refuses_a_weak_token_before_validating_the_query(client):
    """403 before 422, which `api_contract`'s sweep depends on.

    That sweep derives the guarded routes from the app's own OpenAPI document
    and replays an under-privileged token at each with no query string. Were
    FastAPI to validate the required parameters first, this route would answer
    422 and the sweep would read a *validation* error as a refusal — a route
    whose guard had been removed entirely would still look like it held.
    """
    r = await client.get(
        "/consent/admin/shares", headers=make_headers(scope="connector.webhook")
    )
    assert r.status_code == 403


# ── The offer collapse, on the read side ──────────────────────────────────────
#
# `set_subject_data_sharing` keys a decision on its offer; `get_granted_subject_ids`
# collapsed on `(subject_id, consumer_id)` alone. Two consent surfaces disagreeing
# about what a row is keyed by made the answer depend on the *order* two unrelated
# decisions were made in — and in one of the two orders it withheld rows the
# person had consented to share.

async def _provision_offer(client, offer: str, enabled: bool, subject: str = SUBJECT):
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": subject,
            "offer_id": offer,
            "enabled": enabled,
            "legal_basis": EVIDENCE,
        },
    )
    assert r.status_code == 200, r.text


async def _audience(client, offer: str, consumer: str = CONSUMER) -> list[str]:
    r = await client.get(
        "/consent/admin/shares",
        headers=AUDIENCE,
        params={"offer_id": offer, "consumer_id": consumer},
    )
    assert r.status_code == 200, r.text
    return r.json()["datasets"][0]["subject_ids"]


@pytest.mark.rule("D-14", "D-15", "L-2")
@pytest.mark.asyncio
async def test_declining_one_offer_does_not_erase_a_grant_on_another(client):
    """The defect, in the order that used to lose the grant.

    `test-flexibility` and `test-grid-planning` are two consent-based offers over
    the same fixture dataset. Granting the first and then declining the second
    used to answer `[]` for the first — the decline was simply the more recent
    row, and the collapse kept only that. The person's data would have been left
    out of an export they had consented to.
    """
    await _provision_offer(client, "test-flexibility", True)
    await _provision_offer(client, "test-grid-planning", False)

    assert await _audience(client, "test-flexibility") == [SUBJECT]
    assert await _audience(client, "test-grid-planning") == []


@pytest.mark.rule("D-14", "D-15")
@pytest.mark.asyncio
async def test_the_audience_does_not_depend_on_decision_order(client):
    """The same two decisions, made the other way round, answer the same.

    Order-dependence was the symptom that proved the collapse was a defect and
    not an imprecision: nothing about consent should make the answer depend on
    which of two unrelated questions the person was asked first.
    """
    await _provision_offer(client, "test-grid-planning", False)
    await _provision_offer(client, "test-flexibility", True)

    assert await _audience(client, "test-flexibility") == [SUBJECT]
    assert await _audience(client, "test-grid-planning") == []


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_a_grant_on_one_offer_is_not_an_audience_for_another(client):
    """Keyed on the offer, not merely filtered by its purpose.

    Purpose very nearly separates the fixture's two consent offers and does not
    quite — two offers may name one purpose with different controllers, and
    `test-flexibility` declares no `controller_role` at all. A caller asking who
    consents to an offer must get people who decided about *that* offer.
    """
    await _provision_offer(client, "test-flexibility", True)

    assert await _audience(client, "test-flexibility") == [SUBJECT]
    # Never asked about grid-planning, so not in its audience.
    assert await _audience(client, "test-grid-planning") == []


@pytest.mark.rule("D-15", "A-10")
@pytest.mark.asyncio
async def test_withdrawing_the_offer_empties_its_own_audience_only(client):
    """Withdrawal stays scoped to the offer it was made about."""
    await _provision_offer(client, "test-flexibility", True)
    await _provision_offer(client, "test-grid-planning", True)
    assert await _audience(client, "test-flexibility") == [SUBJECT]
    assert await _audience(client, "test-grid-planning") == [SUBJECT]

    await _provision_offer(client, "test-flexibility", False)
    assert await _audience(client, "test-flexibility") == []
    assert await _audience(client, "test-grid-planning") == [SUBJECT]


@pytest.mark.rule("D-15", "A-10")
@pytest.mark.asyncio
async def test_a_dataset_wide_withdrawal_denies_every_offer(engine, client):
    """A decision that names no offer is not scoped to one.

    `POST /consent/my/shares` with a bare `dataset_id` — the `/my-data` control —
    writes a row with no `offer_id`, and revoking it is a statement about the
    dataset rather than about an offer. Per-offer keying must not let an
    offer-scoped grant survive it: that would disclose against a withdrawal,
    which is the one direction this collapse must never get wrong.
    """
    await _provision_offer(client, "test-flexibility", True)
    assert await _audience(client, "test-flexibility") == [SUBJECT]

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(
                _row(
                    offer_id=None,
                    status="revoked",
                    requested_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                    revoked_at=datetime(2026, 3, 1, 1, tzinfo=timezone.utc),
                )
            )

    assert await _audience(client, "test-flexibility") == []


@pytest.mark.rule("D-14", "D-15")
@pytest.mark.asyncio
async def test_the_row_filter_is_fixed_too_not_just_the_audience(engine, client):
    """The data plane asks without an offer, and it had the same defect.

    `_authorize_dataset` builds its row filter from `get_granted_subject_ids`
    with no offer to name, so the decline of an unrelated offer used to withhold
    rows there as well. Passing no offer now unions the per-offer decisions
    rather than keeping only the most recent one.
    """
    await _provision_offer(client, "test-flexibility", True)
    await _provision_offer(client, "test-grid-planning", False)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        granted = await get_granted_subject_ids(
            session, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )
    assert granted == [SUBJECT]


# ── The two readers agree, because they are one reader ────────────────────────

INTERNAL = make_headers(scope="connector.internal")


@pytest.mark.rule("D-14", "D-15")
@pytest.mark.asyncio
async def test_check_consent_agrees_with_the_row_filter(engine, client):
    """The promise `get_granted_subject_ids` has always made in its docstring.

    "Both are considered here so the row-filter agrees with `check_consent`" —
    which held only as long as two separate implementations of the same rules
    stayed in step, and they did not. Fixing the per-offer collapse on one path
    alone turned a consistent wrong answer into a contradiction; both now
    delegate to `decide_for_subject`, so this is enforced rather than asserted.
    """
    await _provision_offer(client, "test-flexibility", True)
    await _provision_offer(client, "test-grid-planning", False)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        allowed, _reason = await check_consent(
            session, SUBJECT, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )
        granted = await get_granted_subject_ids(
            session, DATASET, CONSUMER, purpose=["FlexibilityResearch"]
        )

    assert allowed is True
    assert granted == [SUBJECT]
    assert allowed == (SUBJECT in granted)


@pytest.mark.rule("D-14", "D-15", "D-20")
@pytest.mark.asyncio
async def test_internal_consent_check_does_not_contradict_itself(client):
    """One route, two branches, and they used to answer differently.

    `GET /internal/consent/check` calls `check_consent_detail` when the caller
    names a `subject_id` and `get_granted_subject_ids` when it does not. With a
    grant on one offer and a decline on another it denied the named subject and
    listed that same subject as granted one branch away — a data-plane PEP
    reading either branch would have been correct and they could not both be.
    """
    await _provision_offer(client, "test-flexibility", True)
    await _provision_offer(client, "test-grid-planning", False)

    params = {
        "dataset_id": DATASET,
        "consumer_id": CONSUMER,
        "purpose": "FlexibilityResearch",
    }
    named = await client.get(
        "/internal/consent/check", headers=INTERNAL, params={**params, "subject_id": SUBJECT}
    )
    listed = await client.get("/internal/consent/check", headers=INTERNAL, params=params)
    assert named.status_code == listed.status_code == 200

    assert named.json()["consent_active"] is True
    assert SUBJECT in listed.json()["subject_ids"]
    assert named.json()["consent_active"] == (SUBJECT in listed.json()["subject_ids"])
