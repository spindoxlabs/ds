"""`D-15c` — a withdrawal may only be lifted by the authority that made it.

Issue #34: a service holding ``connector.consent.provision`` could lift a
withdrawal the person had made themselves, and nothing refused, warned or
recorded that it happened. The refusal only *appended* — ``set_subject_data_sharing``
asked "is it already granted?" and nothing else — so the fresh ``granted`` row won
the cell on recency, carrying a caller-supplied evidence record that read as proof
of a consent taken at a moment the person had already said stop.

What each test here pins, and why it is not covered elsewhere:

- the refusal itself, on the route, with the standing withdrawal named in it;
- that a **service's own** withdrawal is still liftable, because that is the
  ordinary onboarding re-run and refusing it would break the route's purpose;
- that the operator override works and leaves the authority for the act on the
  row rather than looking like an ordinary provision;
- that ``decided_by`` follows the row's *current* decision through the mutation
  path, which is the half of the rule that no request body can express.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.services.consent_service import WILDCARD_CONSUMER
from connector.services.membership_check import Membership
from tests import make_headers, make_vc_headers

PROVISION = make_headers(scope="connector.consent.provision")
SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
OFFER = "test-flexibility"

EVIDENCE = {
    "source": "onboarding",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}
OVERRIDE = {
    "reason": "subject asked us to restore it by phone",
    "authorized_by": "operator-7",
    "instruction_ref": "call-20260909-114",
}


@pytest.fixture(autouse=True)
def _allow_membership(monkeypatch):
    async def _member(*_args, **_kwargs):
        return Membership.MEMBER

    monkeypatch.setattr("connector.api.v1.consent.check_subject_membership", _member)


async def _rows(engine) -> list[ConsentRequestORM]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(ConsentRequestORM).where(ConsentRequestORM.subject_id == SUBJECT)
        )
        return list(result.scalars())


async def _subject_sets(client, *, enabled: bool):
    return await client.post(
        "/consent/my/shares",
        headers=make_vc_headers(SUBJECT),
        json={"offer_id": OFFER, "enabled": enabled},
    )


async def _service_provisions(client, *, enabled: bool = True, **extra):
    body = {"subject_id": SUBJECT, "offer_id": OFFER, "enabled": enabled}
    if enabled:
        body["legal_basis"] = EVIDENCE
    body.update(extra)
    return await client.post("/consent/admin/shares", headers=PROVISION, json=body)


# ── the refusal ───────────────────────────────────────────────────────────────


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_service_cannot_lift_a_withdrawal_the_subject_made(client, engine):
    assert (await _service_provisions(client)).status_code == 200
    assert (await _subject_sets(client, enabled=False)).status_code == 200

    r = await _service_provisions(client)

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "withdrew this share themselves" in detail
    assert "D-15c" in detail
    # The refusal names the withdrawal it refused to overwrite, so the caller can
    # go and look at it rather than guessing which cell blocked the provision.
    assert SUBJECT in detail

    # And nothing was written: the audience is still empty.
    statuses = [r.status for r in await _rows(engine)]
    assert statuses.count("granted") == 0, (
        "a refused provision must leave no granted row — the whole defect was a "
        "second row winning the cell on recency"
    )


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_the_refused_subject_is_not_back_in_the_audience(client):
    """The reproduction from the issue, read through the route that discloses."""
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)
    await _service_provisions(client)

    r = await client.get(
        "/consent/admin/shares",
        headers=make_headers(scope="connector.consent.audience"),
        params={"offer_id": OFFER, "consumer_id": "did:web:example-org"},
    )
    assert r.status_code == 200
    subjects = [s for dataset in r.json()["datasets"] for s in dataset["subject_ids"]]
    assert SUBJECT not in subjects


# ── what stays possible ───────────────────────────────────────────────────────


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_service_may_lift_its_own_withdrawal(client, engine):
    """The ordinary onboarding re-run, which the guard must not break.

    A service withdrawing and then re-provisioning is the same authority deciding
    twice. Refusing this would make the guard cost more than the defect.
    """
    assert (await _service_provisions(client)).status_code == 200
    assert (await _service_provisions(client, enabled=False)).status_code == 200

    r = await _service_provisions(client)

    assert r.status_code == 200
    assert [row["status"] for row in r.json()] == ["granted"]
    assert [row["decided_by"] for row in r.json()] == ["service"]


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_the_subject_may_lift_their_own_withdrawal(client):
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)

    r = await _subject_sets(client, enabled=True)

    assert r.status_code == 200
    assert [row["status"] for row in r.json()] == ["granted"]
    assert [row["decided_by"] for row in r.json()] == ["subject"]


# ── the override ──────────────────────────────────────────────────────────────


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_an_evidenced_operator_override_lifts_it_and_says_so(client):
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)

    r = await _service_provisions(client, override_subject_withdrawal=OVERRIDE)

    assert r.status_code == 200
    row = r.json()[0]
    assert row["status"] == "granted"
    # `operator`, not `service`: the act is a person's, and the column is what a
    # later reader — or the next provisioning call — goes by.
    assert row["decided_by"] == "operator"
    recorded = row["legal_basis"]["subject_withdrawal_override"]
    assert recorded["authorized_by"] == "operator-7"
    assert recorded["instruction_ref"] == "call-20260909-114"
    assert recorded["reason"].startswith("subject asked us")
    # The row does not claim the data owner did this.
    assert "Operator override" in row["message"]


@pytest.mark.asyncio
async def test_an_ordinary_provision_files_no_override_record(client):
    """Its presence is the signal, so it must be absent when nothing was overridden."""
    r = await _service_provisions(client)
    assert "subject_withdrawal_override" not in r.json()[0]["legal_basis"]


@pytest.mark.asyncio
async def test_an_override_on_a_withdrawal_is_refused(client):
    """A person may always stop; there is nothing there to override."""
    r = await _service_provisions(
        client, enabled=False, override_subject_withdrawal=OVERRIDE
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_the_override_record_refuses_obvious_pii(client):
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)
    r = await _service_provisions(
        client,
        override_subject_withdrawal={**OVERRIDE, "authorized_by": "op@example.org"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_override_key_is_refused_not_dropped(client):
    """`extra="forbid"`, for the reason `AdminShareLegalBasis` has it.

    An accepted-and-dropped field leaves the caller holding written proof of
    something never stored, and this record is the proof for the one act that
    most needs it.
    """
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)
    r = await _service_provisions(
        client, override_subject_withdrawal={**OVERRIDE, "approved_by_legal": True}
    )
    assert r.status_code == 422


# ── the column follows the decision, not the creator ──────────────────────────


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_subject_withdrawing_a_service_grant_makes_it_theirs(client, engine):
    """The mutation path: withdrawing rewrites the granted row in place.

    Leaving the granter's authority on it would let the next provisioning call
    lift a decision the person took — the defect, reached through the other
    branch. Asserted on the row because no response shape shows a mutation.
    """
    await _service_provisions(client)
    await _subject_sets(client, enabled=False)

    revoked = [r for r in await _rows(engine) if r.status == "revoked"]
    assert len(revoked) == 1
    assert revoked[0].decided_by == "subject"
    assert revoked[0].consumer_id == WILDCARD_CONSUMER


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_subject_repeating_stop_takes_ownership_of_the_refusal(client, engine):
    """A standing service withdrawal, then the person says stop as well.

    The decision does not change, so no row is written — but whose refusal it is
    does change, and it can only escalate. Without this, a service could withdraw
    on someone's behalf, that person could confirm it, and the next service could
    still lift it.
    """
    await _service_provisions(client)
    await _service_provisions(client, enabled=False)
    await _subject_sets(client, enabled=False)

    assert [r.decided_by for r in await _rows(engine) if r.status == "revoked"] == [
        "subject"
    ]
    assert (await _service_provisions(client)).status_code == 409
