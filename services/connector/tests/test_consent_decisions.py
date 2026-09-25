"""An organisation's own decisions, as a list: `GET /consent/admin/decisions`.

Plan `an-audience-says-who-consents-not-who-withdrew`, ADR-0021. The audience
route lists who may be served, so a subject who withdrew is absent from it and
reads like one never asked. This route lists every state an organisation's own
members hold on one offer here, and it is bounded exactly as the per-subject
read-back is (`D-20`):

- the caller must be an accepted collector here, and is **refused** otherwise,
  never answered with an empty list;
- only subjects who are **current members** of the caller's organisation, each
  checked as the write checks them, and one unanswerable check is a `503`;
- only cells the caller's organisation **collected**, never another
  organisation's registration;
- each cell's **presented** decision, which is the member's own withdrawal
  whenever one stands (ADR-0020), the same row `subject-shares` returns;
- paged by subject, with a maximum, and never truncated silently.
"""

from __future__ import annotations

import base64

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.registry.participants import CollectorAnswer, CollectorLookupError
from connector.services import consent_service
from connector.services import consent_vocabulary as vocab
from connector.services.membership_check import Membership
from tests import make_headers, make_org_headers

HOLDER = get_settings().participant_did
COLLECTOR = "did:web:collector.example.org"
SECOND = "did:web:second.example.org"
STRANGER = "did:web:stranger.example.org"
OFFER = "test-flexibility"
DATASET = "datasets.silver.meters"
WHY = "Membership ended in example-rec"
KEYS = ["pod:EX000E00000001"]

PROVISION = ("connector.consent.provision",)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}


def member(n: int, org: str = "collector") -> str:
    return f"did:web:{org}.example.org:users:ex-{n:05d}"


A, B, C = member(1), member(2), member(3)
#: A member of the second organisation only.
D = member(4, "second")
#: A member of both organisations.
SHARED = member(5)
HOLDERS_MEMBER = "did:web:rec.dataspaces.localhost:users:sub-001"


def collector() -> dict:
    return make_org_headers(context=COLLECTOR, scopes=PROVISION, alias="example-coll")


def second() -> dict:
    return make_org_headers(context=SECOND, scopes=PROVISION, alias="example-second")


def own() -> dict:
    return make_org_headers(scopes=PROVISION)


#: Every subject the identity registry was asked about, in this test.
ASKED: list[str] = []


@pytest.fixture
def members(monkeypatch):
    """Who is a member of what, as the identity registry would say. Mutable, so
    a test can end a membership; a value of `UNKNOWN` is a registry that cannot
    answer for that subject."""
    table: dict[tuple[str, str], Membership] = {
        (A, "example-coll"): Membership.MEMBER,
        (B, "example-coll"): Membership.MEMBER,
        (C, "example-coll"): Membership.MEMBER,
        (SHARED, "example-coll"): Membership.MEMBER,
        (D, "example-second"): Membership.MEMBER,
        (SHARED, "example-second"): Membership.MEMBER,
        (HOLDERS_MEMBER, "example-org"): Membership.MEMBER,
    }

    async def _check(_url, *, user_did, organization_alias, token_provider=None):
        ASKED.append(user_did)
        return table.get((user_did, organization_alias), Membership.NOT_MEMBER)

    monkeypatch.setattr(consent_route, "check_subject_membership", _check)
    ASKED.clear()
    return table


@pytest.fixture(autouse=True)
def _registry(monkeypatch, members):
    async def _answer(_request, holder_did, collector_did):
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        if collector_did == COLLECTOR:
            return CollectorAnswer(True, "example-coll", "an accepted collector")
        if collector_did == SECOND:
            return CollectorAnswer(True, "example-second", "an accepted collector")
        return CollectorAnswer(False, "example-other", "not an accepted collector")

    monkeypatch.setattr(consent_route, "check_collector", _answer)


async def _share(client, headers, subject, *, enabled=True, **extra):
    body = {"subject_id": subject, "offer_id": OFFER, "enabled": enabled}
    if enabled:
        body["legal_basis"] = EVIDENCE
    body.update(extra)
    r = await client.post("/consent/admin/shares", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _grant(client, headers, subject, **extra):
    return await _share(client, headers, subject, decided_by="subject", **extra)


async def _decisions(client, headers, **params):
    return await client.get(
        "/consent/admin/decisions",
        params={"offer_id": OFFER, **params},
        headers=headers,
    )


def _by_subject(body: dict) -> dict[str, list[dict]]:
    return {s["subject_id"]: s["decisions"] for s in body["subjects"]}


# ── every state, the caller's own members only ───────────────────────────────


@pytest.mark.rule("D-20", "D-21")
@pytest.mark.asyncio
async def test_a_collector_lists_its_own_members_decisions_in_every_state(
    client, members
):
    await _grant(client, collector(), A, keys=KEYS)
    await _grant(client, collector(), B)
    await _share(
        client, collector(), B, enabled=False, decided_by="collector", reason=WHY
    )
    await _grant(client, collector(), C)
    await _grant(client, second(), D)

    # C leaves the organisation after it registered their consent.
    members[(C, "example-coll")] = Membership.NOT_MEMBER

    r = await _decisions(client, collector())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offer_id"] == OFFER
    assert body["datasets"] == [DATASET]
    assert body["next_cursor"] is None
    listed = _by_subject(body)
    # Not C (no longer a member), not D (another organisation's member and its
    # registration), and not SHARED (a member, but never asked).
    assert sorted(listed) == [A, B]

    [a] = listed[A]
    assert (a["dataset_id"], a["state"], a["decided_by"]) == (
        DATASET,
        "granted",
        "subject",
    )
    assert a["collector"] == COLLECTOR
    assert a["keys"] == KEYS
    assert a["decided_at"] is not None and a["revoked_at"] is None

    [b] = listed[B]
    assert (b["state"], b["decided_by"], b["collector"]) == (
        "withdrawn",
        "collector",
        COLLECTOR,
    )
    assert b["revoked_at"] is not None
    assert b["keys"] == []
    # The collector's reason is returned by no read (`D-12a`).
    assert WHY not in r.text


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_another_organisation_s_registration_is_never_listed(client):
    """SHARED is a member of both organisations. Only the second registered a
    decision for them, so the first has nothing of its own to list, even though
    its per-subject read-back would show the second's row."""
    await _grant(client, second(), SHARED, keys=KEYS)
    await _grant(client, collector(), A)

    ASKED.clear()
    mine = _by_subject((await _decisions(client, collector())).json())
    assert sorted(mine) == [A]
    # The registry is asked about the subjects this organisation registered,
    # not about everyone who decided on the offer.
    assert ASKED == [A]

    theirs = _by_subject((await _decisions(client, second())).json())
    assert sorted(theirs) == [SHARED]
    assert theirs[SHARED][0]["keys"] == KEYS

    # The holder's own organisation collected nothing here.
    holder = await _decisions(client, own())
    assert holder.status_code == 200, holder.text
    assert holder.json()["subjects"] == []


# ── the presented decision, as subject-shares presents it ────────────────────


@pytest.mark.rule("D-20", "D-15c")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member_first", [False, True], ids=["collector-first", "member-first"]
)
async def test_both_withdrew_and_the_member_s_row_is_the_one_listed(
    client, member_first
):
    await _grant(client, collector(), A, keys=KEYS)
    order = ["subject", "collector"] if member_first else ["collector", "subject"]
    rows = {}
    for who in order:
        extra = {"reason": WHY} if who == "collector" else {}
        [rows[who]] = await _share(
            client, collector(), A, enabled=False, decided_by=who, **extra
        )

    r = await _decisions(client, collector())
    assert r.status_code == 200, r.text
    [d] = _by_subject(r.json())[A]
    assert d["state"] == "withdrawn"
    assert d["decided_by"] == "subject"
    assert d["consent_id"] == rows["subject"]["id"]
    # The same instant; SQLite drops the zone on read, the write answer keeps it.
    assert d["revoked_at"].rstrip("Z") == rows["subject"]["revoked_at"].rstrip("Z")

    # The very row the per-subject read-back presents for this cell.
    back = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": A},
        headers=collector(),
    )
    [share] = back.json()
    assert share["id"] == d["consent_id"]
    assert (share["decided_by"], share["revoked_at"]) == (
        d["decided_by"],
        d["revoked_at"],
    )


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_withdrawal_relayed_by_another_organisation_over_our_grant_is_listed(
    client,
):
    """The withdrawal rewrites the grant row's ``collector`` to the relayer's.
    The grant's evidence still names the organisation that collected it, so
    that organisation sees the member withdrew, rather than seeing nothing."""
    await _grant(client, collector(), SHARED, keys=KEYS)
    await _share(client, second(), SHARED, enabled=False, decided_by="subject")

    [d] = _by_subject((await _decisions(client, collector())).json())[SHARED]
    assert (d["state"], d["decided_by"], d["collector"]) == (
        "withdrawn",
        "subject",
        SECOND,
    )
    assert d["keys"] == []


@pytest.mark.asyncio
async def test_one_entry_per_dataset_never_flattened(client, engine, monkeypatch):
    """An offer resolving to two datasets here lists each separately, with its
    own state: withdrawing one does not read as withdrawing the offer."""
    grid = "datasets.silver.grid_meters"
    monkeypatch.setattr(
        vocab, "datasets_for_offer_or_raise", lambda _offer: [DATASET, grid]
    )
    await _grant(client, collector(), A)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        offer = vocab.resolve_offer(OFFER)
        await consent_service.set_subject_data_sharing(
            session=session,
            subject_id=A,
            dataset_id=grid,
            consumer_id=consent_service.WILDCARD_CONSUMER,
            enabled=False,
            purpose=[offer.purpose],
            offer_id=OFFER,
            decided_by="subject",
            collector=COLLECTOR,
        )

    r = await _decisions(client, collector())
    assert r.status_code == 200, r.text
    assert r.json()["datasets"] == sorted([DATASET, grid])
    states = {d["dataset_id"]: d["state"] for d in _by_subject(r.json())[A]}
    assert states == {DATASET: "granted", grid: "withdrawn"}


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_another_org_s_decision_on_our_member_s_other_dataset_is_not_listed(
    client, engine, monkeypatch
):
    """SHARED is on our page, because we registered their decision over one
    dataset. The second organisation registered theirs over the other dataset
    of the same offer. That cell is the second organisation's, and it is not
    listed here, not even as a state."""
    grid = "datasets.silver.grid_meters"
    monkeypatch.setattr(
        vocab, "datasets_for_offer_or_raise", lambda _offer: [DATASET, grid]
    )
    offer = vocab.resolve_offer(OFFER)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        for dataset_id, by in ((DATASET, COLLECTOR), (grid, SECOND)):
            await consent_service.set_subject_data_sharing(
                session=session,
                subject_id=SHARED,
                dataset_id=dataset_id,
                consumer_id=consent_service.WILDCARD_CONSUMER,
                enabled=True,
                purpose=[offer.purpose],
                offer_id=OFFER,
                legal_basis={"collector": by},
                decided_by="subject",
                collector=by,
            )

    mine = _by_subject((await _decisions(client, collector())).json())
    assert [d["dataset_id"] for d in mine[SHARED]] == [DATASET]
    theirs = _by_subject((await _decisions(client, second())).json())
    assert [d["dataset_id"] for d in theirs[SHARED]] == [grid]


# ── refusals, not empty lists ────────────────────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_caller_not_accepted_here_is_refused_not_answered_empty(client):
    await _grant(client, collector(), A)
    stranger = make_org_headers(
        context=STRANGER, scopes=PROVISION, alias="example-other"
    )
    r = await _decisions(client, stranger)
    assert r.status_code == 403, r.text
    assert "not an accepted consent collector" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_registry_that_cannot_say_is_503(client, monkeypatch):
    async def _down(*_args, **_kwargs):
        raise CollectorLookupError("registry down")

    monkeypatch.setattr(consent_route, "check_collector", _down)
    r = await _decisions(client, collector())
    assert r.status_code == 503, r.text


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_one_member_the_registry_cannot_answer_for_is_503_not_a_shorter_list(
    client, members
):
    await _grant(client, collector(), A)
    await _grant(client, collector(), B)
    members[(B, "example-coll")] = Membership.UNKNOWN
    r = await _decisions(client, collector())
    assert r.status_code == 503, r.text
    assert B in r.json()["detail"]


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_not_a_subject_surface_and_not_a_plain_service(client):
    r = await client.get("/consent/admin/decisions", params={"offer_id": OFFER})
    assert r.status_code == 401
    r = await _decisions(client, make_headers("connector.consent.provision"))
    assert r.status_code == 403, r.text
    r = await client.get("/consent/admin/decisions", headers=collector())
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("offer", "status"),
    [("no-such-offer", 422), ("test-incentives", 409), ("test-unbound", 422)],
    ids=["unknown", "contract-based", "bound-to-no-dataset"],
)
async def test_the_offer_is_refused_as_the_write_refuses_it(client, offer, status):
    r = await client.get(
        "/consent/admin/decisions",
        params={"offer_id": offer},
        headers=collector(),
    )
    assert r.status_code == status, r.text


# ── paging ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pages_cover_every_subject_once_and_only_the_last_ends_the_list(
    client, members
):
    everyone = [member(n) for n in range(10, 17)]
    for subject in everyone:
        members[(subject, "example-coll")] = Membership.MEMBER
        await _grant(client, collector(), subject)
    # One of them has since left: their page is shorter, and the list goes on.
    gone = everyone[2]
    members[(gone, "example-coll")] = Membership.NOT_MEMBER

    seen: list[str] = []
    pages = 0
    cursor = None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        r = await _decisions(client, collector(), **params)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["limit"] == 2
        assert len(body["subjects"]) <= 2
        seen += [s["subject_id"] for s in body["subjects"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert pages == 4  # 7 subjects, 2 per page
    assert seen == sorted(s for s in everyone if s != gone)


@pytest.mark.asyncio
async def test_the_page_size_has_a_documented_maximum(client):
    for limit in (0, consent_route.DECISIONS_PAGE_MAX + 1):
        r = await _decisions(client, collector(), limit=limit)
        assert r.status_code == 422, (limit, r.text)
    r = await _decisions(client, collector(), limit=consent_route.DECISIONS_PAGE_MAX)
    assert r.status_code == 200, r.text

    from connector.main import create_app

    op = create_app().openapi()["paths"]["/consent/admin/decisions"]["get"]
    [limit] = [p for p in op["parameters"] if p["name"] == "limit"]
    assert limit["schema"]["maximum"] == consent_route.DECISIONS_PAGE_MAX


@pytest.mark.asyncio
async def test_a_cursor_this_route_did_not_issue_is_422(client):
    bad = base64.urlsafe_b64encode(b"\xff\xfe").decode().rstrip("=")
    for cursor in ("!!not-base64!!", bad):
        r = await _decisions(client, collector(), cursor=cursor)
        assert r.status_code == 422, (cursor, r.text)
