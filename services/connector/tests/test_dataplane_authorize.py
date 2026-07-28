"""`POST /internal/dataplane/authorize` — the control plane's answer to the data plane.

The endpoint exists so that a data plane can stop trusting its caller for the
facts that decide access. Two of these tests are the reason it exists at all:

- `test_another_consumers_agreement_is_refused` — an agreement id travels as a
  self-asserted header, so without the binding check, naming someone else's
  agreement would read their data.
- `test_agreement_does_not_unlock_another_dataset` — an agreement over an open
  dataset must not open a consent-gated one.

Everything else here pins a fail-closed default. There is no test asserting that
a missing gate still returns rows, because there is no such case: every unknown
is a refusal.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.services import subject_identities
from connector.services.agreement_service import terminate_agreement, upsert_agreement
from connector.services.consent_service import set_subject_data_sharing
from tests import make_headers

HEADERS = make_headers(scope="connector.internal")

CONSUMER = "did:web:consumer.dataspaces.localhost"
PROVIDER = "did:web:provider.dataspaces.localhost"
SUBJECT = "did:web:users.dataspaces.localhost:sub-001"

# The fixture's consent-gated dataset and one of its three permitted purposes.
GATED = "datasets.silver.meters"
OPEN = "datasets.gold.weather"
IRI = "https://w3id.org/dsp/policy/purpose/"


def _policy(*purposes: str) -> dict:
    """An agreement policy shaped like the one EDC stores back."""
    right = (
        {"@id": f"{IRI}{purposes[0]}"}
        if len(purposes) == 1
        else [{"@id": f"{IRI}{p}"} for p in purposes]
    )
    return {
        "@type": "odrl:Agreement",
        "odrl:permission": [
            {
                "odrl:action": {"@id": "odrl:use"},
                "odrl:constraint": [
                    {
                        "odrl:leftOperand": {"@id": "odrl:purpose"},
                        "odrl:operator": {
                            "@id": "odrl:isA" if len(purposes) == 1 else "odrl:isAnyOf"
                        },
                        "odrl:rightOperand": right,
                    }
                ],
            }
        ],
    }


async def _agreement(engine, agreement_id: str, asset_id: str, *, consumer=CONSUMER,
                     purposes=("EnergyCommunityOperation", "FlexibilityResearch")):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await upsert_agreement(
                session,
                agreement_id=agreement_id,
                asset_id=asset_id,
                consumer_id=consumer,
                provider_id=PROVIDER,
                policy_snapshot=_policy(*purposes),
                agreed_at=datetime.now(timezone.utc),
            )


async def _consent(engine, *, purpose: list[str], consumer=CONSUMER):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=consumer,
                enabled=True,
                purpose=purpose,
            )


@pytest.fixture(autouse=True)
def _resolvable_subjects(monkeypatch):
    """The identity-registry resolves subject DIDs to registry usernames.

    Stubbed rather than mocked away: the mapping is what turns "these subjects
    consented" into something the data plane can key on, so a test that skipped
    it would assert on a decision that could not be enforced.
    """
    async def fake(dids, *_args, **_kwargs):
        return {did: f"user-{did.rsplit(':', 1)[-1]}" for did in dids}

    monkeypatch.setattr(subject_identities, "resolve_usernames", fake)
    yield


async def _authorize(client, **body):
    payload = {
        "consumer_did": CONSUMER,
        "agreement_id": "agr-1",
        "dataset_ids": [GATED],
        "purpose": ["FlexibilityResearch"],
        **body,
    }
    return await client.post("/internal/dataplane/authorize", json=payload, headers=HEADERS)


# ── the binding checks ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_another_consumers_agreement_is_refused(engine, client):
    """The header says `agr-1`; the token says who is asking. They must agree."""
    await _agreement(engine, "agr-1", GATED, consumer="did:web:someone-else.localhost")
    r = await _authorize(client)
    assert r.status_code == 200
    assert r.json()["decision"] == "deny"
    assert r.json()["reason"] == "not_your_agreement"


@pytest.mark.asyncio
async def test_refusal_does_not_disclose_the_owner(engine, client):
    """A refusal must not become an oracle for who holds which agreement."""
    await _agreement(engine, "agr-1", GATED, consumer="did:web:someone-else.localhost")
    body = (await _authorize(client)).json()
    assert "someone-else" not in str(body)


@pytest.mark.asyncio
async def test_agreement_does_not_unlock_another_dataset(engine, client):
    await _agreement(engine, "agr-1", OPEN)
    r = await _authorize(client, dataset_ids=[GATED])
    assert r.json()["reason"] == "dataset_not_in_agreement"


@pytest.mark.asyncio
async def test_unknown_agreement_is_refused(client):
    r = await _authorize(client)
    assert r.json()["reason"] == "agreement_unknown"


@pytest.mark.asyncio
async def test_terminated_agreement_is_refused(engine, client):
    await _agreement(engine, "agr-1", GATED)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await terminate_agreement(session, "agr-1", "revoked by consumer")
    r = await _authorize(client)
    assert r.json()["reason"] == "agreement_inactive"


# ── purpose ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purpose_outside_the_agreement_is_refused(engine, client):
    """The agreed policy is the authority, not today's governance file."""
    await _agreement(engine, "agr-1", GATED, purposes=("FlexibilityResearch",))
    r = await _authorize(client, purpose=["GridMonitoring"])
    assert r.json()["reason"] == "purpose_not_agreed"


@pytest.mark.asyncio
async def test_unknown_purpose_is_refused(engine, client):
    await _agreement(engine, "agr-1", GATED)
    r = await _authorize(client, purpose=["SellingItOn"])
    assert r.json()["reason"] == "purpose_unknown"


@pytest.mark.asyncio
async def test_consent_gated_dataset_needs_a_stated_purpose(engine, client):
    """No stated reason, no rows — the same rule `/internal/consent/check` applies."""
    await _agreement(engine, "agr-1", GATED)
    r = await _authorize(client, purpose=[])
    assert r.json()["datasets"][0]["reason"] == "purpose_required"


# ── consent and the row filter ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_consent_yields_a_refusal_not_an_empty_filter(engine, client):
    await _agreement(engine, "agr-1", GATED)
    r = await _authorize(client)
    assert r.json()["datasets"][0]["reason"] == "no_consent"


@pytest.mark.asyncio
async def test_consent_becomes_a_row_filter_spec(engine, client):
    """The decision carries the filter **as governance declared it**.

    Not a column and a list of DIDs: `rec_registry` resolves devices from a
    member, so the receiving handler needs its own name and args to do that. A
    decision reduced to a column would force the data plane to assume a handler.
    """
    await _agreement(engine, "agr-1", GATED)
    await _consent(engine, purpose=["FlexibilityResearch"])
    body = (await _authorize(client)).json()
    assert body["decision"] == "allow"
    row_filter = body["datasets"][0]["row_filter"]
    assert row_filter["handler"]
    assert row_filter["args"]["column"]
    # Registry-native identifiers, never the DID — a DID is derived from an
    # unsalted email hash and so is re-identifiable by whoever holds the payload.
    assert row_filter["principals"] == [f"user-{SUBJECT.rsplit(':', 1)[-1]}"]
    assert SUBJECT not in str(row_filter)


@pytest.mark.asyncio
async def test_unresolvable_subjects_deny(engine, client, monkeypatch):
    """Consent exists, but nobody can be named to the system holding the data.

    Denying is the only honest answer: an allow with an empty principal list
    reads as "filter to nothing" to one implementation and "no filter" to
    another, and the second serves everything.
    """
    async def resolves_nothing(dids, *_args, **_kwargs):
        return {}

    monkeypatch.setattr(subject_identities, "resolve_usernames", resolves_nothing)
    await _agreement(engine, "agr-1", GATED)
    await _consent(engine, purpose=["FlexibilityResearch"])
    assert (await _authorize(client)).json()["reason"] == "subjects_unresolvable"


@pytest.mark.asyncio
async def test_consent_for_another_purpose_does_not_authorise_this_one(engine, client):
    """Purpose limitation, at the data plane."""
    await _agreement(engine, "agr-1", GATED)
    await _consent(engine, purpose=["IncentiveCalculation"])
    r = await _authorize(client, purpose=["FlexibilityResearch"])
    assert r.json()["datasets"][0]["reason"] == "no_consent"


@pytest.mark.asyncio
async def test_open_dataset_needs_no_filter(engine, client):
    await _agreement(engine, "agr-open", OPEN, purposes=("GridMonitoring",))
    r = await _authorize(
        client, agreement_id="agr-open", dataset_ids=[OPEN], purpose=["GridMonitoring"]
    )
    body = r.json()
    assert body["decision"] == "allow"
    assert body["datasets"][0]["row_filter"] is None


# ── the joined query ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_join_is_as_strict_as_its_strictest_dataset(engine, client):
    """One statement, several datasets: the overall answer is the strictest."""
    await _agreement(engine, "agr-1", GATED)
    await _consent(engine, purpose=["FlexibilityResearch"])
    body = (await _authorize(client, dataset_ids=[GATED, OPEN])).json()
    assert body["decision"] == "deny"
    verdicts = {d["dataset_id"]: d["decision"] for d in body["datasets"]}
    assert verdicts[GATED] == "allow"
    assert verdicts[OPEN] == "deny"  # not covered by this agreement


# ── the endpoint is not open ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_the_internal_grant(client):
    r = await client.post(
        "/internal/dataplane/authorize",
        json={"consumer_did": CONSUMER, "agreement_id": "agr-1", "dataset_ids": [GATED]},
        headers=make_headers(scope="connector.provider.read"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_the_ttl_is_published(engine, client):
    """The data plane may cache an allow for exactly as long as ds says."""
    await _agreement(engine, "agr-1", GATED)
    await _consent(engine, purpose=["FlexibilityResearch"])
    assert (await _authorize(client)).json()["cache"]["ttl_seconds"] > 0
