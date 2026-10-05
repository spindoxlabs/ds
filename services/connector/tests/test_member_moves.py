"""A person leaves one community for another: what the holder keeps apart.

A member of `example-rec-a` is released and joins `example-rec-b`. Both
communities are accepted collectors at the holder (`example-dso`). The person's
history under the first community stays where it is, keyed to the DID it was
recorded under and to the organisation that collected it. These tests pin what
the second community can and cannot reach:

- **the read-back** (`GET /consent/admin/subject-shares`) lists only the cells
  the calling organisation collected. A DID still carrying the first
  community's rows (one issued before a move minted a new DID, or a dual-role
  person's) does not hand that history to the second;
- **the key owner** is a subject *and* the organisation that asserted it, so the
  same DID under another organisation's assertion is a `409` too;
- **the supply point moves with the person**: the second community's grant on the
  same `pod:` key under the person's new DID is a `409` while the first
  community's grant carries it, and goes through once the first community's
  withdrawal released it. Nothing under the old DID is rewritten.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.db.models import ConsentKeyOwnerORM, ConsentRequestORM
from connector.db.sealed import blind_index
from connector.registry.participants import CollectorAnswer
from connector.services import consent_service
from connector.services.membership_check import Membership
from tests import make_org_headers, make_user_headers

REC_A = "did:web:rec-a.example.org"
REC_B = "did:web:rec-b.example.org"
GRID = "did:web:dso.example.org"
OFFER = "test-meter-release"
DATASET = "datasets.silver.grid_meters"
SCOPES = (
    "connector.consent.provision",
    "connector.consent.collector.read",
)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}
POD = "pod:EX000E00000001"
#: The person's DID under the first community, and the one the second minted.
OLD = "did:web:rec-a.example.org:users:ex-00001"
NEW = "did:web:rec-b.example.org:users:ex-00002"


def rec_a() -> dict:
    return make_org_headers(context=REC_A, scopes=SCOPES, alias="example-rec-a")


def rec_b() -> dict:
    return make_org_headers(context=REC_B, scopes=SCOPES, alias="example-rec-b")


def assertion() -> dict:
    return {
        "terms": "rec-pod-assertion/1",
        "terms_sha256": "1" * 64,
        "method": "uploaded-document",
        "verification_ref": "00000000-0000-4000-8000-000000000001",
        "verified_by": "2" * 64,
        "verified_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "evidence": [{"kind": "utility_bill", "sha256": "3" * 64}],
    }


class _Owners:
    async def by_id(self, alias: str):
        if alias != "grid-operator":
            return None
        return type("Owner", (), {"id": alias, "did": GRID})()


@pytest.fixture
def members(client, monkeypatch):
    """Who is a member of what, as the identity registry says *now*."""
    table: dict[tuple[str, str], Membership] = {}

    async def _member(_url, *, user_did, organization_alias, token_provider=None):
        return table.get((user_did, organization_alias), Membership.NOT_MEMBER)

    async def _collector(_request, holder_did, collector_did):
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        if collector_did == REC_A:
            return CollectorAnswer(True, "example-rec-a", "an accepted collector")
        if collector_did == REC_B:
            return CollectorAnswer(True, "example-rec-b", "an accepted collector")
        return CollectorAnswer(False, None, "not an accepted collector")

    async def _admitted(*_args, consumer_id, **_kwargs):
        return {OFFER} if consumer_id == GRID else set()

    monkeypatch.setattr(consent_route, "check_subject_membership", _member)
    monkeypatch.setattr(consent_route, "check_collector", _collector)
    monkeypatch.setattr(consent_route, "_admitted_wildcard_offers", _admitted)
    client._transport.app.state.owners_registry = _Owners()
    return table


async def _share(client, headers, subject, *, keys=None, enabled=True, **extra):
    body = {"subject_id": subject, "offer_id": OFFER, "enabled": enabled}
    body["decided_by"] = "subject"
    if enabled:
        body["legal_basis"] = {**EVIDENCE, "key_assertion": assertion()}
    if keys is not None:
        body["keys"] = keys
    body.update(extra)
    return await client.post("/consent/admin/shares", headers=headers, json=body)


async def _read_back(client, headers, subject):
    return await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": subject},
        headers=headers,
    )


async def _rows(engine, model):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return list((await session.execute(select(model))).scalars())


# ── the read-back ────────────────────────────────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_the_next_community_does_not_read_the_last_one_s_history(client, members):
    """Red before: `subject-shares` listed every row of the DID, so the second
    community read the first one's grant, its dataset, purposes and consumer."""
    members[(OLD, "example-rec-a")] = Membership.MEMBER
    assert (await _share(client, rec_a(), OLD, keys=[POD])).status_code == 200

    # Released from the first, a member of the second under the same DID.
    del members[(OLD, "example-rec-a")]
    members[(OLD, "example-rec-b")] = Membership.MEMBER

    r = await _read_back(client, rec_b(), OLD)
    assert r.status_code == 200, r.text
    assert r.json() == []
    assert REC_A not in r.text and DATASET not in r.text
    # The first community no longer reads its former member at all.
    assert (await _read_back(client, rec_a(), OLD)).status_code == 403


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_each_community_reads_its_own_cell_and_the_operator_reads_all(
    client, engine, members, monkeypatch
):
    """Two communities speaking for one DID (a dual-role person) each read back
    only what they collected. The deployment operator reads both."""
    other = "test-flexibility"
    members[(OLD, "example-rec-a")] = Membership.MEMBER
    members[(OLD, "example-rec-b")] = Membership.MEMBER
    assert (await _share(client, rec_a(), OLD, keys=[POD])).status_code == 200
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await consent_service.set_subject_data_sharing(
            session=session,
            subject_id=OLD,
            dataset_id="datasets.silver.meters",
            consumer_id=consent_service.WILDCARD_CONSUMER,
            enabled=True,
            purpose=None,
            offer_id=other,
            decided_by="subject",
            collector=REC_B,
            legal_basis={**EVIDENCE, "collector": REC_B},
        )

    a = (await _read_back(client, rec_a(), OLD)).json()
    b = (await _read_back(client, rec_b(), OLD)).json()
    assert [(s["offer_id"], s["collector"]) for s in a] == [(OFFER, REC_A)]
    assert [(s["offer_id"], s["collector"]) for s in b] == [(other, REC_B)]
    assert a[0]["keys"] == [POD]

    async def _anyone(*_args, **_kwargs):
        return Membership.MEMBER

    monkeypatch.setattr(consent_route, "check_subject_membership", _anyone)
    r = await _read_back(client, make_user_headers(roles=["platform-admin"]), OLD)
    assert r.status_code == 200, r.text
    assert sorted(s["offer_id"] for s in r.json()) == sorted([OFFER, other])
    # Not even the operator gets keys it did not register.
    assert all(s["keys"] == [] for s in r.json())


@pytest.mark.rule("D-18")
@pytest.mark.asyncio
async def test_an_open_ask_still_reaches_the_community_that_speaks_for_the_person(
    client, engine, members
):
    """An ask is a question to the person, which nobody collected: it is listed
    to whichever organisation speaks for them now (`D-18`)."""
    members[(NEW, "example-rec-b")] = Membership.MEMBER
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await consent_service.create_consent_request(
            session, subject_id=NEW, consumer_id=GRID, dataset_id=DATASET
        )
    r = await _read_back(client, rec_b(), NEW)
    assert r.status_code == 200, r.text
    assert [s["status"] for s in r.json()] == ["pending"]


# ── the supply point ─────────────────────────────────────────────────────────


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_the_same_did_under_another_community_cannot_take_a_held_key(
    client, engine, members
):
    """Red before: the owner was matched on the subject only, so the second
    community took the key over while the owner row still named the first."""
    members[(OLD, "example-rec-a")] = Membership.MEMBER
    members[(OLD, "example-rec-b")] = Membership.MEMBER
    assert (await _share(client, rec_a(), OLD, keys=[POD])).status_code == 200

    r = await _share(client, rec_b(), OLD, keys=[POD])
    assert r.status_code == 409, r.text
    assert POD not in r.text and REC_A not in r.text
    [owner] = await _rows(engine, ConsentKeyOwnerORM)
    assert (owner.subject_id, owner.collector, owner.released_at) == (
        OLD,
        REC_A,
        None,
    )


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_the_supply_point_moves_with_the_person_once_released(
    client, engine, members
):
    """The move, end to end at the holder: the old DID's grant carries the POD,
    so the new DID's grant is a 409; the first community's release withdrawal
    frees it and the second community's grant then goes through. The old rows
    stay as written."""
    members[(OLD, "example-rec-a")] = Membership.MEMBER
    assert (await _share(client, rec_a(), OLD, keys=[POD])).status_code == 200
    members[(NEW, "example-rec-b")] = Membership.MEMBER

    # Before the release: the key is the first community's member's.
    r = await _share(client, rec_b(), NEW, keys=[POD])
    assert r.status_code == 409, r.text
    assert "held by another subject" in r.text

    # The release: the first community withdraws on its own authority.
    r = await _share(
        client,
        rec_a(),
        OLD,
        enabled=False,
        decided_by="collector",
        reason="Membership ended in example-rec-a",
    )
    assert r.status_code == 200, r.text
    del members[(OLD, "example-rec-a")]

    r = await _share(client, rec_b(), NEW, keys=[POD])
    assert r.status_code == 200, r.text

    owners = sorted(
        await _rows(engine, ConsentKeyOwnerORM), key=lambda o: o.released_at is None
    )
    assert [
        (o.key_index, o.subject_id, o.collector, o.released_at is None) for o in owners
    ] == [
        (blind_index(POD), OLD, REC_A, False),
        (blind_index(POD), NEW, REC_B, True),
    ]
    # Nothing under the old DID was rewritten: its row still names the first
    # community and is withdrawn; the new DID has its own.
    rows = {r.subject_id: r for r in await _rows(engine, ConsentRequestORM)}
    assert (rows[OLD].status, (rows[OLD].legal_basis or {}).get("collector")) == (
        "revoked",
        REC_A,
    )
    assert (rows[NEW].status, rows[NEW].collector) == ("granted", REC_B)
    # And the second community's read-back of its member holds only its own.
    back = (await _read_back(client, rec_b(), NEW)).json()
    assert [(s["subject_id"], s["keys"]) for s in back] == [(NEW, [POD])]
