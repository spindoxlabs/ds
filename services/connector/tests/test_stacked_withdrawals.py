"""Each withdrawal is its own record (ADR-0020).

Maintainer decision, 2026-09-21: when a member withdraws over a withdrawal an
organisation already made, both are stored, each with its own authority, time
and reason — "no mixing up". Until then the writer re-stamped the organisation's
row as the member's and kept the organisation's time and reason, so the row read
"the member decided, for the collector's reason, at the collector's time", and
the member's own act reached neither the table nor provenance (its event id
repeated the collector's and the store dropped it as a duplicate).

What these tests pin:

- a collector's withdrawal, then the member's — relayed by the collector and
  directly through `/consent/my/shares` — are two rows, and the collector's is
  left exactly as it was written;
- the member's act is a provenance event of its own;
- the data is refused from the first withdrawal on, and still after the second;
  and the member's later blanket stop closes a per-party grant made between the
  two (`D-15a`), which the re-stamped row, dated to the collector, did not;
- nobody but the member lifts the member's withdrawal (`D-15c`);
- the member's own withdrawal, then a collector's: both stored, and every
  current-decision read presents the member's (the maintainer: "prioritize the
  member if both"), so a relayer still sees it and only the member lifts it;
- lifting needs authority over every withdrawal standing, not only the newest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.db.models import ConsentRequestORM
from connector.registry.participants import CollectorAnswer
from connector.services import consent_service
from connector.services.membership_check import Membership
from tests import make_org_headers, make_user_headers, make_vc_headers

HOLDER = get_settings().participant_did
COLLECTOR = "did:web:collector.example.org"
MEMBER = "did:web:collector.example.org:users:member-001"
#: A member of this connector's own organisation — the one kind of member whose
#: credential `/consent/my/*` here accepts.
HOLDERS_MEMBER = "did:web:rec.dataspaces.localhost:users:sub-001"
OFFER = "test-flexibility"
DATASET = "datasets.silver.meters"
WHY = "Membership ended in example-rec"

PROVISION = ("connector.consent.provision",)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}
OVERRIDE = {
    "reason": "subject asked us to restore it by phone",
    "authorized_by": "operator-7",
    "instruction_ref": "call-20260921-001",
}


def _collector() -> dict:
    return make_org_headers(context=COLLECTOR, scopes=PROVISION, alias="example-coll")


def _own() -> dict:
    return make_org_headers(scopes=PROVISION)


class _Prov:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        async def record(**kwargs):
            self.calls.append((name, kwargs))

        return record


@pytest.fixture
def prov(client):
    recorder = _Prov()
    client._transport.app.state.prov = recorder
    return recorder


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    """`COLLECTOR` is accepted here, the holder collects for itself, and both
    members belong to the organisation that speaks for them."""

    async def _answer(_request, holder_did, collector_did):
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        if (holder_did, collector_did) == (HOLDER, COLLECTOR):
            return CollectorAnswer(True, "example-coll", "an accepted collector")
        return CollectorAnswer(False, "example-other", "not an accepted collector")

    async def _member(_url, *, user_did, organization_alias, token_provider=None):
        if (user_did, organization_alias) in {
            (MEMBER, "example-coll"),
            (HOLDERS_MEMBER, "example-org"),
        }:
            return Membership.MEMBER
        return Membership.NOT_MEMBER

    monkeypatch.setattr(consent_route, "check_collector", _answer)
    monkeypatch.setattr(consent_route, "check_subject_membership", _member)


async def _share(client, headers, *, subject=MEMBER, enabled=True, **extra):
    body = {"subject_id": subject, "offer_id": OFFER, "enabled": enabled}
    if enabled:
        body["legal_basis"] = EVIDENCE
    body.update(extra)
    return await client.post("/consent/admin/shares", headers=headers, json=body)


async def _rows(engine, subject=MEMBER) -> list[ConsentRequestORM]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(ConsentRequestORM)
            .where(ConsentRequestORM.subject_id == subject)
            .order_by(*consent_service._latest_decision_first())
        )
        return list(result.scalars())


def _snapshot(row: ConsentRequestORM) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "decided_by": row.decided_by,
        "collector": row.collector,
        "revoked_at": row.revoked_at,
        "revocation_reason": row.revocation_reason,
    }


async def _collector_withdraws_over_a_grant(client, headers, subject) -> dict:
    """A relayed grant, then the organisation's own withdrawal with a reason.
    Returns the collector's row as it stands after its withdrawal."""
    granted = await _share(client, headers, subject=subject, decided_by="subject")
    assert granted.status_code == 200, granted.text
    withdrawn = await _share(
        client,
        headers,
        subject=subject,
        enabled=False,
        decided_by="collector",
        reason=WHY,
    )
    assert withdrawn.status_code == 200, withdrawn.text
    return withdrawn.json()[0]


# ── two withdrawals, two records ─────────────────────────────────────────────


@pytest.mark.rule("D-15c", "D-12a")
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["relayed", "direct"])
async def test_a_member_s_withdrawal_over_a_collector_s_is_a_record_of_its_own(
    engine, client, path
):
    """Red on the re-stamp: it wrote no row and rewrote the collector's.

    ``relayed``: the collector relays the member's stop (`decided_by="subject"`),
    what a community's onboarding service does. ``direct``: the member presses stop
    themselves on `/consent/my/shares`, which only a member of this connector's
    own organisation can do — so there the collector is the holder's own client.
    """
    if path == "relayed":
        subject, headers = MEMBER, _collector()
    else:
        subject, headers = HOLDERS_MEMBER, _own()

    await _collector_withdraws_over_a_grant(client, headers, subject)
    [collector_row] = await _rows(engine, subject)
    before = _snapshot(collector_row)
    assert (before["decided_by"], before["revocation_reason"]) == ("collector", WHY)

    if path == "relayed":
        r = await _share(
            client, headers, subject=subject, enabled=False, decided_by="subject"
        )
    else:
        r = await client.post(
            "/consent/my/shares",
            headers=make_vc_headers(subject),
            json={"offer_id": OFFER, "enabled": False},
        )
    assert r.status_code == 200, r.text
    answered = r.json()[0] if isinstance(r.json(), list) else r.json()

    rows = await _rows(engine, subject)
    assert len(rows) == 2, [_snapshot(row) for row in rows]
    member_row, collector_row = rows

    # The collector's record is exactly what the collector wrote.
    assert _snapshot(collector_row) == before

    # The member's is theirs: its own row, time and authority, and no reason of
    # the collector's.
    assert member_row.id != collector_row.id
    assert member_row.status == "revoked"
    assert member_row.decided_by == "subject"
    assert member_row.revoked_at >= collector_row.revoked_at
    assert member_row.revocation_reason != WHY
    assert not member_row.subject_keys

    # And it is what the call answered: the decision it recorded.
    assert answered["id"] == member_row.id
    assert answered["decided_by"] == "subject"


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_the_member_s_act_is_a_provenance_event_of_its_own(engine, client, prov):
    """Red on the re-stamp: the second `ConsentRevoked` carried the collector
    row's id as its `event_id`, which the provenance store answers `duplicate`
    and drops — the member's act never reached the graph."""
    headers = _collector()
    await _collector_withdraws_over_a_grant(client, headers, MEMBER)
    r = await _share(client, headers, enabled=False, decided_by="subject")
    assert r.status_code == 200, r.text

    revoked = [kw for name, kw in prov.calls if name == "consent_revoked"]
    assert len(revoked) == 2
    by_collector, by_member = revoked
    assert by_collector["event_id"] != by_member["event_id"]
    assert (by_collector["decided_by"], by_collector["reason"]) == ("collector", WHY)
    assert by_member["decided_by"] == "subject"
    assert by_member["reason"] != WHY


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_repeat_by_the_same_authority_records_nothing(engine, client):
    """ "Both are stored, since the subjects are different": one record per
    withdrawing authority, not one per call. Can fail if the append ignores
    who already stands behind the refusal."""
    headers = _collector()
    await _collector_withdraws_over_a_grant(client, headers, MEMBER)
    for _ in range(2):
        again = await _share(client, headers, enabled=False, decided_by="subject")
        assert again.status_code == 200, again.text
    again = await _share(
        client, headers, enabled=False, decided_by="collector", reason="Later cause"
    )
    assert again.status_code == 200, again.text

    rows = await _rows(engine)
    assert [row.decided_by for row in rows] == ["subject", "collector"]
    assert rows[1].revocation_reason == WHY  # the first cause stays (ADR-0019)


# ── enforcement ──────────────────────────────────────────────────────────────


@pytest.mark.rule("D-15a", "D-17")
@pytest.mark.asyncio
async def test_refused_from_the_first_withdrawal_and_after_the_second(engine, client):
    """Green on the re-stamp too — this is the property the change must keep.
    Can fail if the appended row is not the cell's latest, or reads as a grant."""
    headers = _collector()
    await _collector_withdraws_over_a_grant(client, headers, MEMBER)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _allowed() -> bool:
        async with factory() as session:
            allowed, _reason, _row = await consent_service.check_consent_detail(
                session,
                MEMBER,
                DATASET,
                "did:web:consumer.example.org",
                purpose=["FlexibilityResearch"],
                offer_id=OFFER,
            )
            granted = await consent_service.get_granted_subject_ids(
                session,
                DATASET,
                "did:web:consumer.example.org",
                purpose=["FlexibilityResearch"],
            )
        return allowed or MEMBER in granted

    assert not await _allowed()
    r = await _share(client, headers, enabled=False, decided_by="subject")
    assert r.status_code == 200, r.text
    assert not await _allowed()


class _Clock:
    """`datetime.now` at strictly increasing, known instants."""

    def __init__(self, start: datetime) -> None:
        self.at = start

    def tick(self) -> None:
        self.at += timedelta(minutes=1)

    def install(self, monkeypatch) -> None:
        clock = self

        class _Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.at

        monkeypatch.setattr(consent_service, "datetime", _Fixed)


@pytest.mark.rule("D-15a")
@pytest.mark.asyncio
async def test_the_member_s_later_stop_closes_a_grant_made_between_the_two(
    engine, monkeypatch
):
    """Red on the re-stamp. The collector withdraws the offer (T1), the member
    then grants one party per-party (T2), then stops sharing the offer with
    everyone (T3). `D-15a`: a withdrawal covers everything it covers and the
    later decision wins, so the per-party grant made at T2 does not survive T3.
    The re-stamped row kept T1, so the grant looked newer and the party was
    still served after the member said stop."""
    clock = _Clock(datetime(2026, 9, 21, 9, 0, tzinfo=UTC))
    clock.install(monkeypatch)
    party = "did:web:consumer.example.org"
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _decide(consumer, enabled, decided_by, **extra):
        async with factory() as session, session.begin():
            await consent_service.set_subject_data_sharing(
                session,
                subject_id=MEMBER,
                dataset_id=DATASET,
                consumer_id=consumer,
                enabled=enabled,
                purpose=["FlexibilityResearch"],
                recipient="example-org",
                offer_id=OFFER,
                decided_by=decided_by,
                **extra,
            )
        clock.tick()

    wildcard = consent_service.WILDCARD_CONSUMER
    await _decide(wildcard, True, "subject", collector=COLLECTOR)
    await _decide(wildcard, False, "collector", collector=COLLECTOR, reason=WHY)  # T1
    await _decide(party, True, "subject")  # T2
    async with factory() as session:
        allowed, _r, _row = await consent_service.check_consent_detail(
            session,
            MEMBER,
            DATASET,
            party,
            purpose=["FlexibilityResearch"],
            offer_id=OFFER,
        )
    assert allowed, "precondition: the per-party grant after T1 stands (D-15a)"

    await _decide(wildcard, False, "subject")  # T3
    async with factory() as session:
        allowed, reason, _row = await consent_service.check_consent_detail(
            session,
            MEMBER,
            DATASET,
            party,
            purpose=["FlexibilityResearch"],
            offer_id=OFFER,
        )
    assert not allowed, reason


# ── who may lift it (`D-15c`) ────────────────────────────────────────────────


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_nobody_but_the_member_lifts_the_member_s_withdrawal(engine, client):
    """Green on the re-stamp too (it also left `subject` on top). Can fail if
    the lift check reads the collector's row — the one the collector may lift —
    instead of the member's."""
    headers = _collector()
    await _collector_withdraws_over_a_grant(client, headers, MEMBER)
    assert (
        await _share(client, headers, enabled=False, decided_by="subject")
    ).status_code == 200
    [member_row, _collector_row] = await _rows(engine)

    refused = await _share(client, headers, decided_by="collector")
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "withdrew this share themselves" in detail
    assert member_row.id in detail

    # The holder's operator, provisioning without the evidenced override.
    operator = make_user_headers(["ds-admin"])
    body = {
        "subject_id": HOLDERS_MEMBER,
        "offer_id": OFFER,
        "enabled": True,
        "legal_basis": EVIDENCE,
    }
    own = _own()
    await _collector_withdraws_over_a_grant(client, own, HOLDERS_MEMBER)
    assert (
        await _share(
            client, own, subject=HOLDERS_MEMBER, enabled=False, decided_by="subject"
        )
    ).status_code == 200
    r = await client.post("/consent/admin/shares", headers=operator, json=body)
    assert r.status_code == 409, r.text
    r = await client.post(
        "/consent/admin/shares",
        headers=operator,
        json={**body, "override_subject_withdrawal": OVERRIDE},
    )
    assert r.status_code == 200, r.text

    # The member, relayed, may — and lifts the cell: the newest row is a grant.
    lifted = await _share(client, headers, decided_by="subject")
    assert lifted.status_code == 200, lifted.text
    assert (await _rows(engine))[0].status == "granted"


# ── the other order: the member first, then a collector ─────────────────────
#
# The maintainer, 2026-09-21: "yes prioritize the member if both, still if it's
# a withdrawal on both side I do not see the problem. It's withdrawn right?"
# Both are stored; every read of the current decision presents the member's.


async def _member_then_collector(client, headers=None, subject=MEMBER) -> None:
    headers = headers or _collector()
    granted = await _share(client, headers, subject=subject, decided_by="subject")
    assert granted.status_code == 200, granted.text
    stopped = await _share(
        client, headers, subject=subject, enabled=False, decided_by="subject"
    )
    assert stopped.status_code == 200, stopped.text
    ended = await _share(
        client,
        headers,
        subject=subject,
        enabled=False,
        decided_by="collector",
        reason=WHY,
    )
    assert ended.status_code == 200, ended.text


async def _two_rows(engine, subject=MEMBER):
    """The member's row and the collector's, which must both exist."""
    rows = await _rows(engine, subject)
    by = {row.decided_by: row for row in rows}
    assert sorted(by) == ["collector", "subject"], [_snapshot(r) for r in rows]
    return by["subject"], by["collector"]


@pytest.mark.rule("D-15c", "D-12a")
@pytest.mark.asyncio
async def test_a_collector_s_withdrawal_over_the_member_s_is_stored_too(
    engine, client, prov
):
    """Red before: the collector's withdrawal over the member's wrote nothing
    and its reason was lost."""
    await _member_then_collector(client)
    member_row, collector_row = await _two_rows(engine)

    assert member_row.status == collector_row.status == "revoked"
    assert collector_row.collector == COLLECTOR
    assert collector_row.revocation_reason == WHY
    assert member_row.revocation_reason != WHY
    assert collector_row.revoked_at >= member_row.revoked_at

    revoked = [kw for name, kw in prov.calls if name == "consent_revoked"]
    assert [kw["decided_by"] for kw in revoked] == ["subject", "collector"]
    assert revoked[1]["reason"] == WHY
    assert revoked[0]["event_id"] != revoked[1]["event_id"]


@pytest.mark.rule("D-15c", "D-19")
@pytest.mark.asyncio
async def test_every_current_decision_read_presents_the_member_s_withdrawal(
    engine, client
):
    """Red before: only one row existed. Can fail if a reader takes the newest
    row — the collector's — instead of the member's standing withdrawal."""
    # Through the collector: its read-back, and the deciding row of a check.
    await _member_then_collector(client)
    member_row, _collector_row = await _two_rows(engine)

    back = await client.get(
        "/consent/admin/subject-shares",
        headers=_collector(),
        params={"subject_id": MEMBER},
    )
    assert back.status_code == 200, back.text
    [shown] = [s for s in back.json() if s["offer_id"] == OFFER]
    assert (shown["id"], shown["decided_by"]) == (member_row.id, "subject")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        allowed, _reason, deciding = await consent_service.check_consent_detail(
            session,
            MEMBER,
            DATASET,
            "did:web:consumer.example.org",
            purpose=["FlexibilityResearch"],
            offer_id=OFFER,
        )
        latest = await consent_service.get_latest_offer_consent(
            session, MEMBER, DATASET, consent_service.WILDCARD_CONSUMER, OFFER
        )
    assert not allowed
    assert deciding is not None and deciding.id == member_row.id
    assert latest is not None and latest.id == member_row.id

    # Through the member's own credential: `/consent/my/shares`, `/consent/status`.
    await _member_then_collector(client, _own(), HOLDERS_MEMBER)
    own_member_row, _ = await _two_rows(engine, HOLDERS_MEMBER)
    vc = make_vc_headers(HOLDERS_MEMBER)
    shares = await client.get("/consent/my/shares", headers=vc)
    assert shares.status_code == 200, shares.text
    [mine] = [s for s in shares.json() if s["offer_id"] == OFFER]
    assert (mine["id"], mine["decided_by"]) == (own_member_row.id, "subject")
    status = await client.get(
        "/consent/status",
        headers=vc,
        params={
            "consumer_id": consent_service.WILDCARD_CONSUMER,
            "dataset_id": DATASET,
            "subject_id": HOLDERS_MEMBER,
        },
    )
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "revoked"


#: The authorities a collector relaying for a community counts as the member's
#: own when it reads the holder back (and a collector's or a service's
#: withdrawal it does not): the shape of the reader the hazard was about.
_MEMBERS_OWN = {"subject", "operator"}


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_relayer_sees_the_member_s_withdrawal_over_the_older_grant(
    engine, client
):
    """The hazard: a relayer that ranks the member's own decisions from the
    read-back (`decided_by` in subject/operator, newest by decision time) and
    then relays the newest one. Had the read shown the collector's newer row,
    the member's withdrawal would have vanished from that ranking, the older
    grant would have been the member's newest decision, and relaying it — as
    the subject — would lift both withdrawals.

    ds cannot refuse a grant relayed as the subject's: `D-15c` makes it the
    member's to lift. What closes the hazard is the read, and this pins it.
    Red before: one row only. Fails if the read presents the collector's row."""
    await _member_then_collector(client)
    member_row, _collector_row = await _two_rows(engine)
    # The member withdrew their own grant, so their row still carries the
    # grant's time in `decided_at`: the older grant a relayer could replay.
    grant_time = member_row.decided_at
    assert grant_time is not None

    back = await client.get(
        "/consent/admin/subject-shares",
        headers=_collector(),
        params={"subject_id": MEMBER},
    )
    offer_rows = [
        r for r in back.json() if r["offer_id"] == OFFER and r["status"] != "pending"
    ]
    own = [r for r in offer_rows if r["decided_by"] in _MEMBERS_OWN]
    assert own, "the member's own withdrawal must be in the read-back"
    newest = max(own, key=lambda r: r.get("revoked_at") or r.get("decided_at"))
    assert newest["status"] == "revoked"
    assert datetime.fromisoformat(newest["revoked_at"]).replace(
        tzinfo=None
    ) > grant_time.replace(tzinfo=None)


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_the_collector_cannot_lift_the_member_s_withdrawal_under_its_own(
    engine, client
):
    """Red before: one row only. Fails if the lift check reads the newest row —
    the collector's own, which it may lift — instead of every standing
    withdrawal."""
    headers = _collector()
    await _member_then_collector(client, headers)
    member_row, _collector_row = await _two_rows(engine)

    refused = await _share(client, headers, decided_by="collector")
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "withdrew this share themselves" in detail
    assert member_row.id in detail
    assert all(r.status == "revoked" for r in await _rows(engine))

    # The member — relayed — lifts the cell, both withdrawals with it.
    lifted = await _share(client, headers, decided_by="subject")
    assert lifted.status_code == 200, lifted.text
    rows = await _rows(engine)
    assert rows[0].status == "granted"
    assert len(rows) == 3


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_withdrawal_needs_authority_over_every_withdrawal_standing(
    engine, client, monkeypatch
):
    """Two collectors each withdraw on their own authority: two records. Neither
    may lift the cell alone, since the other's withdrawal stands too; the
    member may. Fails if lifting reads only the newest withdrawal."""
    second = "did:web:second.example.org"

    async def _two(_request, holder_did, collector_did):
        if collector_did in (COLLECTOR, second):
            return CollectorAnswer(True, "example-coll", "accepted")
        return CollectorAnswer(holder_did == collector_did, "example-org", "self")

    monkeypatch.setattr(consent_route, "check_collector", _two)
    first_h = _collector()
    second_h = make_org_headers(context=second, scopes=PROVISION, alias="second")

    assert (await _share(client, first_h, decided_by="subject")).status_code == 200
    for headers in (first_h, second_h):
        r = await _share(
            client, headers, enabled=False, decided_by="collector", reason=WHY
        )
        assert r.status_code == 200, r.text
    assert sorted(r.collector for r in await _rows(engine)) == sorted(
        [COLLECTOR, second]
    )

    for headers in (first_h, second_h):
        refused = await _share(client, headers, decided_by="collector")
        assert refused.status_code == 409, refused.text
    assert (await _share(client, second_h, decided_by="subject")).status_code == 200
