"""The holder reads the data keys it serves, and their history (ADR-0022).

A collector registers its members' decisions at this connector with their typed
keys, and the data plane serves rows by those keys. These tests pin the holder's
read of that state:

- **who may read** — this connector's own organisation client, the deployment
  operator, or a person granted the permission for this participant; never a
  collector and never a plain service token;
- **what it reads** — keys only, never a subject, and exactly the keys the row
  filter would carry for the offer's recipient;
- **the history** — every key a decision started or stopped carrying, written
  in the flush that changes the row, including the subject's own revoke by id;
- **the answers** ADR-0021's route gives for a bad offer, and paging.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.db.key_ledger import entries_for
from connector.db.models import ConsentKeyEventORM, ConsentRequestORM
from connector.registry.participants import CollectorAnswer
from connector.services import consent_service, subject_identities
from connector.services.membership_check import Membership
from tests import make_headers, make_org_headers, make_user_headers

HOLDER = get_settings().participant_did
COLLECTOR = "did:web:collector.example.org"
GRID = "did:web:grid.example.org"
OFFER = "test-meter-release"
DATASET = "datasets.silver.grid_meters"
HOLDER_READ = ("connector.consent.holder.read",)
PROVISION = ("connector.consent.provision",)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}


def member(n: int) -> str:
    return f"did:web:collector.example.org:users:ex-{n:05d}"


A, B, C, D = member(1), member(2), member(3), member(4)
KEY_A, KEY_B, KEY_A2 = "pod:EX000E00000001", "pod:EX000E00000002", "pod:EX000E00000009"


def collector() -> dict:
    return make_org_headers(
        context=COLLECTOR, scopes=PROVISION + HOLDER_READ, alias="example-coll"
    )


def holder() -> dict:
    return make_org_headers(scopes=HOLDER_READ)


class _Owners:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    async def by_id(self, alias: str):
        did = self._mapping.get(alias)
        if did is None:
            return None
        return type("Owner", (), {"id": alias, "did": did})()


@pytest.fixture(autouse=True)
def _wired(client, monkeypatch):
    async def _member(_url, *, user_did, organization_alias, token_provider=None):
        if organization_alias == "example-coll":
            return Membership.MEMBER
        return Membership.NOT_MEMBER

    async def _collector(_request, holder_did, collector_did):
        if collector_did == COLLECTOR:
            return CollectorAnswer(True, "example-coll", "an accepted collector")
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        return CollectorAnswer(False, "example-other", "not an accepted collector")

    async def _admitted(*_args, consumer_id, **_kwargs):
        # `D-14`: the offer's recipient is admitted, nobody else.
        return {OFFER} if consumer_id == GRID else set()

    monkeypatch.setattr(consent_route, "check_subject_membership", _member)
    monkeypatch.setattr(consent_route, "check_collector", _collector)
    monkeypatch.setattr(consent_route, "_admitted_wildcard_offers", _admitted)
    client._transport.app.state.owners_registry = _Owners({"grid-operator": GRID})


async def _share(client, subject, *, enabled=True, keys=None, **extra):
    body = {
        "subject_id": subject,
        "offer_id": OFFER,
        "enabled": enabled,
        "decided_by": "subject",
    }
    if enabled:
        body["legal_basis"] = EVIDENCE
    if keys is not None:
        body["keys"] = keys
    body.update(extra)
    r = await client.post("/consent/admin/shares", headers=collector(), json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _keys(client, headers=None, **params):
    return await client.get(
        "/consent/admin/holder/keys",
        params={"offer_id": OFFER, **params},
        headers=headers or holder(),
    )


async def _events(client, headers=None, **params):
    return await client.get(
        "/consent/admin/holder/key-events",
        params={"offer_id": OFFER, **params},
        headers=headers or holder(),
    )


# ── what the holder reads ────────────────────────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_the_holder_reads_the_keys_it_serves_and_nothing_about_who(client):
    await _share(client, A, keys=[KEY_A])
    await _share(client, B, keys=[KEY_B])
    await _share(client, C)  # granted, but no key was sent
    await _share(client, D, keys=["pod:EX000E00000004"])
    await _share(client, D, enabled=False)  # withdrawn

    r = await _keys(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["offer_id"], body["recipient"], body["recipient_did"]) == (
        OFFER,
        "grid-operator",
        GRID,
    )
    assert [(k["dataset_id"], k["key"]) for k in body["keys"]] == [
        (DATASET, KEY_A),
        (DATASET, KEY_B),
    ]
    first = body["keys"][0]
    assert (first["key_type"], first["value"]) == ("pod", "EX000E00000001")
    assert first["authorised_since"] is not None
    assert body["datasets"] == [
        {"dataset_id": DATASET, "key_count": 2, "grants_without_keys": True}
    ]
    assert body["next_cursor"] is None
    # Keys only: no subject, from any of the four.
    for subject in (A, B, C, D):
        assert subject not in r.text
    assert "ex-0000" not in r.text


@pytest.mark.rule("D-20", "X-9")
@pytest.mark.asyncio
async def test_the_list_is_what_the_row_filter_carries(engine, client, monkeypatch):
    """The data plane's own decision, for the offer's recipient, carries exactly
    the keys the holder is shown."""
    from ds.governance import DataplaneDecision

    from connector.api.v1 import internal
    from connector.services.agreement_service import upsert_agreement
    from tests.test_dataplane_authorize import _policy

    async def _admitted(*_args, **_kwargs):
        return {OFFER}

    async def _unresolved(dids, *_args, **_kwargs):
        return {}

    monkeypatch.setattr(internal, "_admitted_wildcard_offers", _admitted)
    monkeypatch.setattr(subject_identities, "resolve_usernames", _unresolved)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await upsert_agreement(
            session,
            agreement_id="agr-grid",
            asset_id=DATASET,
            consumer_id=GRID,
            provider_id=HOLDER,
            policy_snapshot=_policy("EnergyCommunityOperation"),
            agreed_at=datetime.now(UTC),
        )

    await _share(client, A, keys=[KEY_A])
    await _share(client, B, keys=[KEY_B])

    r = await client.post(
        "/internal/dataplane/authorize",
        headers=make_headers(scope="connector.internal"),
        json={
            "consumer_did": GRID,
            "agreement_id": "agr-grid",
            "dataset_ids": [DATASET],
            "purpose": ["EnergyCommunityOperation"],
        },
    )
    assert r.status_code == 200, r.text
    decision = DataplaneDecision.model_validate(r.json())
    assert decision.allowed, decision
    served = sorted(decision.verdict_for(DATASET).row_filter.keys)

    listed = sorted(k["key"] for k in (await _keys(client)).json()["keys"])
    assert listed == served == [KEY_A, KEY_B]


@pytest.mark.asyncio
async def test_a_withdrawal_leaves_the_list_and_stays_in_the_history(client):
    await _share(client, A, keys=[KEY_A])
    await _share(client, B, keys=[KEY_B])
    await _share(client, A, enabled=False)

    keys = [k["key"] for k in (await _keys(client)).json()["keys"]]
    assert keys == [KEY_B]

    r = await _events(client)
    assert r.status_code == 200, r.text
    body = r.json()
    trail = [(e["key"], e["event"], e["cause"]) for e in body["events"]]
    assert trail == [
        (KEY_A, "added", "grant"),
        (KEY_B, "added", "grant"),
        (KEY_A, "removed", "withdrawal"),
    ]
    withdrawal = body["events"][-1]
    assert withdrawal["decided_by"] == "subject"
    assert withdrawal["collector"] == COLLECTOR
    assert withdrawal["consumer_id"] == consent_service.WILDCARD_CONSUMER
    assert "backfill" in body["note"]
    assert A not in r.text and B not in r.text


@pytest.mark.asyncio
async def test_a_new_registration_with_other_keys_is_a_key_change(client):
    # Granted as the member's relayed decision, then re-sent by the collector
    # itself with a corrected key: the history names the re-sender for the key
    # change, and the granter for the grant.
    await _share(client, A, keys=[KEY_A])
    await _share(client, A, keys=[KEY_A2], decided_by="collector")

    keys = [k["key"] for k in (await _keys(client)).json()["keys"]]
    assert keys == [KEY_A2]
    trail = [
        (e["key"], e["event"], e["cause"], e["decided_by"], e["collector"])
        for e in (await _events(client)).json()["events"]
    ]
    assert trail == [
        (KEY_A, "added", "grant", "subject", COLLECTOR),
        (KEY_A, "removed", "key_change", "collector", COLLECTOR),
        (KEY_A2, "added", "key_change", "collector", COLLECTOR),
    ]


@pytest.mark.asyncio
async def test_the_subject_s_own_revoke_by_id_is_recorded(engine, client):
    """`/consent/my/{id}/revoke` leaves the keys on the row and only changes its
    status — the ledger still records that the decision stopped carrying them."""
    [row] = await _share(client, A, keys=[KEY_A])

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        revoked = await consent_service.revoke_consent(session, row["id"], A)
        assert revoked is not None and revoked.subject_keys == [KEY_A]

    trail = [
        (e["key"], e["event"], e["cause"])
        for e in (await _events(client)).json()["events"]
    ]
    assert trail == [(KEY_A, "added", "grant"), (KEY_A, "removed", "withdrawal")]
    assert (await _keys(client)).json()["keys"] == []


@pytest.mark.asyncio
async def test_the_history_takes_since_and_pages(client):
    await _share(client, A, keys=[KEY_A])
    await _share(client, B, keys=[KEY_B])
    await _share(client, C, keys=["pod:EX000E00000003"])

    first = (await _events(client, limit=2)).json()
    assert len(first["events"]) == 2 and first["next_cursor"]
    rest = (await _events(client, limit=2, cursor=first["next_cursor"])).json()
    assert len(rest["events"]) == 1 and rest["next_cursor"] is None
    seen = [e["key"] for e in first["events"] + rest["events"]]
    assert sorted(seen) == sorted([KEY_A, KEY_B, "pod:EX000E00000003"])

    later = (await _events(client, since="2999-01-01T00:00:00Z")).json()
    assert later["events"] == []


@pytest.mark.asyncio
async def test_the_key_list_pages_by_key(client):
    await _share(client, A, keys=[KEY_A])
    await _share(client, B, keys=[KEY_B])

    first = (await _keys(client, limit=1)).json()
    assert [k["key"] for k in first["keys"]] == [KEY_A]
    assert first["next_cursor"]
    rest = (await _keys(client, limit=1, cursor=first["next_cursor"])).json()
    assert [k["key"] for k in rest["keys"]] == [KEY_B]
    assert rest["next_cursor"] is None

    r = await _keys(client, cursor="not-a-cursor")
    assert r.status_code == 422


# ── who may read ─────────────────────────────────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_collector_is_refused_and_told_where_to_read(client):
    await _share(client, A, keys=[KEY_A])
    for read in (_keys, _events):
        r = await read(client, collector())
        assert r.status_code == 403, r.text
        assert "/consent/admin/decisions" in r.text


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_plain_service_token_is_refused(client):
    r = await _keys(client, make_headers(scope="connector.consent.holder.read"))
    assert r.status_code == 403
    assert "names no organisation" in r.text


@pytest.mark.asyncio
async def test_the_deployment_operator_reads_and_a_participant_seat_does_not(client):
    await _share(client, A, keys=[KEY_A])
    r = await _keys(client, make_user_headers(roles=["platform-admin"]))
    assert r.status_code == 200, r.text
    assert [k["key"] for k in r.json()["keys"]] == [KEY_A]

    # Not in `ds-participant-admin`: an operator seat is not a key roster.
    r = await _keys(
        client,
        make_user_headers(organizations={"example-org": ["ds-participant-admin"]}),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_token_without_the_permission_is_refused(client):
    r = await _keys(client, make_org_headers(scopes=PROVISION))
    assert r.status_code == 403
    assert "connector.consent.holder.read" in r.text


# ── the answers for a bad offer ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offers_that_cannot_be_listed_are_refused_not_empty(client):
    assert (await _keys(client, offer_id="no-such-offer")).status_code == 422
    assert (await _keys(client, offer_id="test-unbound")).status_code == 422
    assert (await _events(client, offer_id="no-such-offer")).status_code == 422


@pytest.mark.asyncio
async def test_an_unresolvable_recipient_is_a_503(client):
    client._transport.app.state.owners_registry = _Owners({})
    r = await _keys(client)
    assert r.status_code == 503
    assert "grid-operator" in r.text


# ── the ledger itself ────────────────────────────────────────────────────────


def _row(**overrides) -> ConsentRequestORM:
    values = {
        "id": "row-1",
        "subject_id": A,
        "consumer_id": "*",
        "dataset_id": DATASET,
        "offer_id": OFFER,
        "status": "granted",
        "subject_keys": [KEY_A],
        "decided_by": "subject",
    }
    values.update(overrides)
    return ConsentRequestORM(**values)


def test_a_pending_or_keyless_row_writes_nothing():
    assert entries_for(_row(status="pending"), None, None) == []
    assert entries_for(_row(subject_keys=None), None, None) == []
    assert entries_for(_row(status="rejected"), "pending", [KEY_A]) == []
    # Unchanged: still granted, same keys.
    assert entries_for(_row(), "granted", [KEY_A]) == []


def test_an_approved_ask_with_keys_is_a_grant():
    [entry] = entries_for(_row(), "pending", [KEY_A])
    assert (entry.key, entry.event, entry.cause) == (KEY_A, "added", "grant")


@pytest.mark.asyncio
async def test_the_ledger_shares_the_transaction(engine):
    """A rolled-back decision leaves no history behind."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(_row(id="rolled-back"))
        await session.flush()
        await session.rollback()
    async with factory() as session:
        rows = (await session.execute(select(ConsentKeyEventORM))).scalars().all()
        assert list(rows) == []
