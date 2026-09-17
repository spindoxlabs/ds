"""A collector registers consent at the holder.

Plan `a-collector-registers-consent-at-the-holder`. The organisation a member
belongs to (the collector) collects their consent; the organisation holding
their data (this connector, the holder) registers it, so its data plane needs no
call back to the collector. What these tests pin:

- **who may write** — an organisation token accepted for this holder in the
  identity registry, or this connector's own organisation; a participant
  operator's seat no longer may (`connector.consent.provision` left the bundle);
- **whose members** — the subject must be a member of the organisation the
  caller speaks for, never of the offer's recipient (`D-21`);
- **whose decision** — a relayed withdrawal is the member's, and no service
  provision lifts it; a collector's own withdrawal is that collector's (`D-15c`);
- **what is recorded** — the collector on the row, in the evidence and in
  provenance; the data keys on the row and in the row filter, and in provenance
  only the fact that some were supplied;
- **offer prerequisites** — an offer admitted only together with another;
- **the read-back** — one subject at a time, the caller's own members only.
"""

from __future__ import annotations

import pytest
from ds.governance import DataplaneDecision
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.db.models import ConsentRequestORM
from connector.registry.participants import CollectorAnswer, CollectorLookupError
from connector.services import consent_service, subject_identities
from connector.services.membership_check import Membership
from tests import make_headers, make_org_headers, make_user_headers

HOLDER = get_settings().participant_did
COLLECTOR = "did:web:collector.example.org"
STRANGER = "did:web:stranger.example.org"
MEMBER = "did:web:collector.example.org:users:member-001"
HOLDERS_MEMBER = "did:web:rec.dataspaces.localhost:users:sub-001"

PROVISION = ("connector.consent.provision",)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}
KEYS = ["pod:EX000E00000001"]

MEMBERS = {
    (MEMBER, "example-coll"),
    (HOLDERS_MEMBER, "example-org"),
}


def collector_headers(context: str = COLLECTOR, alias: str = "example-coll") -> dict:
    return make_org_headers(context=context, scopes=PROVISION, alias=alias)


def own_headers() -> dict:
    return make_org_headers(scopes=PROVISION)


class _Prov:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        async def record(**kwargs):
            self.calls.append((name, kwargs))

        return record


@pytest.fixture
def membership_calls(monkeypatch):
    calls: list[str] = []

    async def _check(_url, *, user_did, organization_alias, token_provider=None):
        calls.append(organization_alias)
        if (user_did, organization_alias) in MEMBERS:
            return Membership.MEMBER
        return Membership.NOT_MEMBER

    monkeypatch.setattr(consent_route, "check_subject_membership", _check)
    return calls


@pytest.fixture
def relation(monkeypatch):
    """The registry: `COLLECTOR` is accepted here; the holder collects for itself."""
    lookups: list[tuple[str, str]] = []

    async def _answer(_request, holder_did, collector_did):
        lookups.append((holder_did, collector_did))
        if holder_did == collector_did:
            return CollectorAnswer(True, "example-org", "a holder collects for itself")
        if (holder_did, collector_did) == (HOLDER, COLLECTOR):
            return CollectorAnswer(True, "example-coll", "an accepted collector")
        return CollectorAnswer(False, "example-other", "not an accepted collector")

    monkeypatch.setattr(consent_route, "check_collector", _answer)
    return lookups


@pytest.fixture
def prov(client):
    recorder = _Prov()
    client._transport.app.state.prov = recorder
    return recorder


@pytest.fixture(autouse=True)
def _defaults(membership_calls, relation):
    return None


def _share(offer="test-flexibility", *, subject=MEMBER, enabled=True, **extra) -> dict:
    body = {"subject_id": subject, "offer_id": offer, "enabled": enabled}
    if enabled:
        body["legal_basis"] = EVIDENCE
    body.update(extra)
    return body


async def _post(client, headers, **body):
    return await client.post("/consent/admin/shares", headers=headers, json=body)


async def _rows(engine, subject=MEMBER) -> list[ConsentRequestORM]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(ConsentRequestORM).where(ConsentRequestORM.subject_id == subject)
        )
        return list(result.scalars().all())


# ── who may write, for whose members ─────────────────────────────────────────


@pytest.mark.rule("D-21", "D-20")
@pytest.mark.asyncio
async def test_an_accepted_collector_registers_its_member_s_consent(
    engine, client, membership_calls, prov
):
    r = await _post(
        client, collector_headers(), **_share(decided_by="subject", keys=KEYS)
    )
    assert r.status_code == 200, r.text
    [row] = r.json()
    assert row["status"] == "granted"
    assert row["decided_by"] == "subject"
    assert row["collector"] == COLLECTOR
    assert row["keys_supplied"] is True
    assert row["missing_prerequisites"] == []
    # Membership in the collecting organisation — not in the offer's
    # controller (`example-org`).
    assert membership_calls == ["example-coll"]

    [stored] = await _rows(engine)
    assert stored.collector == COLLECTOR
    assert stored.subject_keys == KEYS
    # Evidence names the collector, server-side; the keys are not evidence.
    assert stored.legal_basis["collector"] == COLLECTOR
    assert "pod:" not in str(stored.legal_basis)


@pytest.mark.rule("D-21")
@pytest.mark.asyncio
async def test_a_collector_cannot_write_for_another_organisation_s_member(
    engine, client, membership_calls
):
    r = await _post(
        client,
        collector_headers(),
        **_share(subject=HOLDERS_MEMBER, decided_by="subject"),
    )
    assert r.status_code == 403, r.text
    assert "not a member of organisation 'example-coll'" in r.json()["detail"]
    assert await _rows(engine, HOLDERS_MEMBER) == []


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_an_organisation_not_on_the_list_is_refused(engine, client):
    r = await _post(
        client,
        collector_headers(context=STRANGER, alias="example-other"),
        **_share(decided_by="subject"),
    )
    assert r.status_code == 403, r.text
    assert "not an accepted consent collector" in r.json()["detail"]
    assert await _rows(engine) == []


@pytest.mark.asyncio
async def test_a_registry_that_cannot_answer_is_503(client, monkeypatch):
    async def _down(*_args, **_kwargs):
        raise CollectorLookupError("down")

    monkeypatch.setattr(consent_route, "check_collector", _down)
    r = await _post(client, collector_headers(), **_share(decided_by="subject"))
    assert r.status_code == 503


@pytest.mark.rule("D-21")
@pytest.mark.asyncio
async def test_the_holder_s_own_organisation_writes_for_its_own_members(
    engine, client, membership_calls
):
    r = await _post(
        client, own_headers(), **_share(subject=HOLDERS_MEMBER, decided_by="subject")
    )
    assert r.status_code == 200, r.text
    assert membership_calls == ["example-org"]
    assert r.json()[0]["collector"] == HOLDER

    r = await _post(client, own_headers(), **_share(decided_by="subject"))
    assert r.status_code == 403


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_plain_service_is_refused_whatever_it_holds(engine, client):
    """Removed 2026-09-17: a service token names no organisation, and in a shared
    realm one such client could write at every connector. Refused before any
    registry or membership question is asked."""
    for scope in ("connector.consent.provision", "connector.admin"):
        r = await _post(
            client, make_headers(scope=scope), **_share(subject=HOLDERS_MEMBER)
        )
        assert r.status_code == 403, (scope, r.text)
        assert "organisation's own client" in r.json()["detail"]
    assert await _rows(engine, HOLDERS_MEMBER) == []


@pytest.mark.rule("D-21")
@pytest.mark.asyncio
async def test_the_operator_is_checked_against_this_connector_s_organisation(
    client, membership_calls
):
    """Not against the offer's recipient: `test-grid-planning` is the grid
    operator's, and the subject is still checked against this participant."""
    r = await _post(
        client,
        make_user_headers(["ds-admin"]),
        **_share("test-grid-planning", subject=HOLDERS_MEMBER),
    )
    assert r.status_code == 200, r.text
    assert membership_calls == ["example-org"]
    assert r.json()[0]["collector"] is None
    assert r.json()[0]["decided_by"] == "operator"


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_a_participant_operator_seat_no_longer_registers_consent(client):
    r = await _post(
        client,
        make_user_headers(["ds-participant-admin"]),
        **_share(subject=HOLDERS_MEMBER),
    )
    assert r.status_code == 403
    r = await _post(
        client, make_user_headers(["ds-admin"]), **_share(subject=HOLDERS_MEMBER)
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_an_organisation_token_without_the_permission_is_refused(client):
    r = await _post(
        client,
        make_org_headers(context=COLLECTOR, alias="example-coll"),
        **_share(decided_by="subject"),
    )
    assert r.status_code == 403


# ── whose decision ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("headers", "extra", "fragment"),
    [
        (collector_headers, {}, "must say whose decision"),
        (
            lambda: make_user_headers(["ds-admin"]),
            {"decided_by": "subject"},
            "organisation token only",
        ),
        (
            collector_headers,
            {
                "decided_by": "subject",
                "override_subject_withdrawal": {
                    "reason": "asked by phone",
                    "authorized_by": "desk-7",
                },
            },
            "operator's act",
        ),
    ],
    ids=["org-token-says-nothing", "operator-says-decided-by", "org-token-overrides"],
)
@pytest.mark.asyncio
async def test_who_decided_is_stated_by_the_right_caller_only(
    client, headers, extra, fragment
):
    subject = MEMBER if headers is collector_headers else HOLDERS_MEMBER
    r = await _post(client, headers(), **_share(subject=subject, **extra))
    assert r.status_code == 422, r.text
    assert fragment in r.text


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_relayed_withdrawal_is_the_member_s_and_no_service_lifts_it(
    engine, client
):
    """The own organisation relays; the deployment operator then re-provisions
    without an override — the holder's authority, and still not the member's."""
    headers = own_headers()
    operator = make_user_headers(["ds-admin"])
    body = _share(subject=HOLDERS_MEMBER)
    assert (await _post(client, operator, **body)).status_code == 200
    r = await _post(
        client,
        headers,
        **_share(subject=HOLDERS_MEMBER, enabled=False, decided_by="subject"),
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["decided_by"] == "subject"

    again = await _post(client, operator, **body)
    assert again.status_code == 409, again.text
    assert "withdrew this share themselves" in again.json()["detail"]


@pytest.mark.rule("D-15c")
@pytest.mark.asyncio
async def test_a_collector_s_own_withdrawal_is_that_collector_s(
    engine, client, monkeypatch
):
    headers = collector_headers()
    assert (
        await _post(client, headers, **_share(decided_by="subject"))
    ).status_code == 200
    withdrawn = await _post(
        client, headers, **_share(enabled=False, decided_by="collector")
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()[0]["decided_by"] == "collector"

    # Another accepted collector speaking for the same member, deciding itself.
    async def _two(_request, holder_did, collector_did):
        if collector_did in (COLLECTOR, "did:web:second.example.org"):
            return CollectorAnswer(True, "example-coll", "accepted")
        return CollectorAnswer(holder_did == collector_did, "example-org", "self")

    monkeypatch.setattr(consent_route, "check_collector", _two)
    second = collector_headers(context="did:web:second.example.org", alias="second")
    refused = await _post(client, second, **_share(decided_by="collector"))
    assert refused.status_code == 409, refused.text
    assert "withdrawn by collector" in refused.json()["detail"]

    # The member, relayed by either collector, may.
    relayed = await _post(client, second, **_share(decided_by="subject"))
    assert relayed.status_code == 200, relayed.text
    assert relayed.json()[0]["decided_by"] == "subject"


@pytest.mark.rule("D-15c")
def test_the_authority_rule_for_collectors():
    lift = consent_service._may_lift
    by_collector = ConsentRequestORM(decided_by="collector", collector=COLLECTOR)
    assert lift(by_collector, "collector", False, COLLECTOR)
    assert not lift(by_collector, "collector", False, STRANGER)
    assert lift(by_collector, "subject", False, STRANGER)
    # The holder's authority does not reach another organisation's own decision…
    assert not lift(by_collector, "collector", False, HOLDER, HOLDER)
    assert not lift(by_collector, "operator", False, None, HOLDER)
    assert lift(by_collector, "operator", True, None, HOLDER)
    # …and does reach its own organisation's.
    by_holder = ConsentRequestORM(decided_by="collector", collector=HOLDER)
    assert lift(by_holder, "operator", False, None, HOLDER)
    by_service = ConsentRequestORM(decided_by="service")
    assert not lift(by_service, "collector", False, COLLECTOR)
    assert lift(by_service, "collector", False, HOLDER, HOLDER)
    assert lift(by_service, "operator", False, None, HOLDER)
    by_subject = ConsentRequestORM(decided_by="subject")
    assert not lift(by_subject, "collector", False, COLLECTOR)
    assert not lift(by_subject, "operator", False, None, HOLDER)
    assert lift(by_subject, "subject", False, COLLECTOR)


# ── keys ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_new_registration_replaces_the_keys_and_a_withdrawal_drops_them(
    engine, client
):
    headers = collector_headers()
    await _post(client, headers, **_share(decided_by="subject", keys=KEYS))
    new_keys = ["pod:EX000E00000002", "pod:EX000E00000003"]
    r = await _post(client, headers, **_share(decided_by="subject", keys=new_keys))
    assert r.status_code == 200
    [row] = await _rows(engine)
    assert row.subject_keys == new_keys

    # Sent without keys: the standing keys stay.
    await _post(client, headers, **_share(decided_by="subject"))
    [row] = await _rows(engine)
    assert row.subject_keys == new_keys

    await _post(client, headers, **_share(enabled=False, decided_by="subject"))
    [row] = await _rows(engine)
    assert row.status == "revoked"
    assert row.subject_keys is None


@pytest.mark.parametrize(
    "body",
    [
        _share(enabled=False, decided_by="subject", keys=KEYS),
        _share(decided_by="subject", keys=["EX000E00000001"]),
        _share(decided_by="subject", keys=["POD:EX000E00000001"]),
        _share(decided_by="subject", key=KEYS),
    ],
    ids=["keys-with-a-withdrawal", "untyped-key", "uppercase-type", "unknown-field"],
)
@pytest.mark.asyncio
async def test_malformed_key_payloads_are_refused(engine, client, body):
    r = await _post(client, collector_headers(), **body)
    assert r.status_code == 422, r.text
    assert await _rows(engine) == []


@pytest.mark.rule("L-3")
@pytest.mark.asyncio
async def test_provenance_names_the_collector_and_never_the_keys(client, prov):
    await _post(client, collector_headers(), **_share(decided_by="subject", keys=KEYS))
    await _post(
        client, collector_headers(), **_share(enabled=False, decided_by="subject")
    )
    granted = next(kw for name, kw in prov.calls if name == "consent_granted")
    revoked = next(kw for name, kw in prov.calls if name == "consent_revoked")
    assert granted["collector"] == COLLECTOR
    assert granted["decided_by"] == "subject"
    assert granted["keys_supplied"] is True
    assert granted["acted_by"]["client_id"] == "svc-ds-connector-example-coll"
    assert granted["acted_by"]["on_behalf_of"] == COLLECTOR
    assert revoked["decided_by"] == "subject"
    assert revoked["collector"] == COLLECTOR
    assert "pod:" not in repr(prov.calls).replace(repr(EVIDENCE), "")
    assert "EX000E" not in repr(prov.calls)


@pytest.mark.rule("X-9")
@pytest.mark.asyncio
async def test_the_row_filter_carries_the_registered_keys(engine, client, monkeypatch):
    from datetime import UTC, datetime

    from connector.api.v1 import internal
    from connector.services.agreement_service import upsert_agreement
    from tests.test_dataplane_authorize import _policy

    consumer = "did:web:third-party.dataspaces.localhost"

    async def _admitted(*_args, **_kwargs):
        return {"test-meter-release", "test-meter-analytics"}

    async def _unresolved(dids, *_args, **_kwargs):
        return {}

    monkeypatch.setattr(internal, "_admitted_wildcard_offers", _admitted)
    monkeypatch.setattr(subject_identities, "resolve_usernames", _unresolved)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await upsert_agreement(
            session,
            agreement_id="agr-grid",
            asset_id="datasets.silver.grid_meters",
            consumer_id=consumer,
            provider_id=HOLDER,
            policy_snapshot=_policy("FlexibilityResearch"),
            agreed_at=datetime.now(UTC),
        )

    headers = collector_headers()
    for offer in ("test-meter-release", "test-meter-analytics"):
        r = await _post(
            client, headers, **_share(offer, decided_by="subject", keys=KEYS)
        )
        assert r.status_code == 200, r.text

    async def authorize():
        r = await client.post(
            "/internal/dataplane/authorize",
            headers=make_headers(scope="connector.internal"),
            json={
                "consumer_did": consumer,
                "agreement_id": "agr-grid",
                "dataset_ids": ["datasets.silver.grid_meters"],
                "purpose": ["FlexibilityResearch"],
            },
        )
        assert r.status_code == 200, r.text
        return DataplaneDecision.model_validate(r.json())

    decision = await authorize()
    assert decision.allowed, decision
    row_filter = decision.verdict_for("datasets.silver.grid_meters").row_filter
    # No username resolves, and the keys alone are enough to narrow on.
    assert row_filter.principals == []
    assert row_filter.keys == KEYS
    assert row_filter.handler == "subject_key_match"

    # The required release withdrawn: the analytics row stands, and the
    # subject is no longer admitted — so nobody is, and the plane is refused.
    await _post(
        client,
        headers,
        **_share("test-meter-release", enabled=False, decided_by="subject"),
    )
    decision = await authorize()
    assert not decision.allowed
    assert decision.reason == "no_consent"
    rows = {r.offer_id: r.status for r in await _rows(engine)}
    assert rows == {"test-meter-release": "revoked", "test-meter-analytics": "granted"}


# ── offer prerequisites ──────────────────────────────────────────────────────


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_a_dependent_offer_is_admitted_only_with_its_prerequisite(engine, client):
    headers = collector_headers()
    r = await _post(
        client, headers, **_share("test-meter-analytics", decided_by="subject")
    )
    assert r.status_code == 200
    assert r.json()[0]["missing_prerequisites"] == ["test-meter-release"]

    async def audience():
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            return await consent_service.get_granted_subject_ids(
                session,
                "datasets.silver.grid_meters",
                "did:web:third-party.dataspaces.localhost",
                purpose=["FlexibilityResearch"],
                consent_required=True,
                offer_id="test-meter-analytics",
            )

    assert await audience() == []

    r = await _post(
        client, headers, **_share("test-meter-release", decided_by="subject")
    )
    assert r.json()[0]["missing_prerequisites"] == []
    assert await audience() == [MEMBER]

    # A dataset-wide withdrawal closes the prerequisite too.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await consent_service.set_subject_data_sharing(
            session,
            subject_id=MEMBER,
            dataset_id="datasets.silver.grid_meters",
            consumer_id=consent_service.WILDCARD_CONSUMER,
            enabled=False,
        )
    assert await audience() == []


def test_a_prerequisite_bound_elsewhere_is_not_checked_here(monkeypatch):
    """Only offers bound to the rows' dataset are evaluated."""
    from connector.services import consent_vocabulary as vocab

    monkeypatch.setattr(
        vocab, "offers_for_dataset", lambda _d: ["test-meter-analytics"]
    )
    row = ConsentRequestORM(
        subject_id=MEMBER,
        dataset_id="datasets.silver.grid_meters",
        consumer_id="*",
        offer_id="test-meter-analytics",
        status="granted",
        purpose=["FlexibilityResearch"],
    )
    assert consent_service.missing_prerequisites([row], "test-meter-analytics") == []


@pytest.mark.asyncio
async def test_an_offer_bound_to_no_dataset_here_is_422(engine, client):
    r = await _post(
        client, collector_headers(), **_share("test-unbound", decided_by="subject")
    )
    assert r.status_code == 422, r.text
    assert "resolves to no dataset" in r.json()["detail"]
    assert await _rows(engine) == []


# ── the read-back ────────────────────────────────────────────────────────────


@pytest.mark.rule("D-20", "D-19")
@pytest.mark.asyncio
async def test_a_collector_reads_back_its_own_member_one_at_a_time(client):
    headers = collector_headers()
    await _post(client, headers, **_share(decided_by="subject", keys=KEYS))
    r = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": MEMBER},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    [share] = r.json()
    assert share["offer_id"] == "test-flexibility"
    assert share["status"] == "granted"
    assert share["keys"] == KEYS

    # Not another organisation's member, and not without the relation.
    other = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": HOLDERS_MEMBER},
        headers=headers,
    )
    assert other.status_code == 403
    stranger = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": MEMBER},
        headers=collector_headers(context=STRANGER, alias="example-other"),
    )
    assert stranger.status_code == 403


@pytest.mark.asyncio
async def test_the_keys_go_back_only_to_the_organisation_that_registered_them(
    client, monkeypatch
):
    await _post(client, collector_headers(), **_share(decided_by="subject", keys=KEYS))

    # The deployment operator reads the same member, as this participant.
    async def _member(*_args, **_kwargs):
        return Membership.MEMBER

    monkeypatch.setattr(consent_route, "check_subject_membership", _member)
    r = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": MEMBER},
        headers=make_user_headers(["ds-admin"]),
    )
    assert r.status_code == 200, r.text
    [share] = r.json()
    assert share["keys_supplied"] is True
    assert share["keys"] == []


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_the_read_back_is_not_a_subject_surface_or_a_roster(client):
    # No token: 401. A person's credential is not what it takes.
    r = await client.get("/consent/admin/subject-shares", params={"subject_id": MEMBER})
    assert r.status_code == 401
    # The subject is required — there is no "all my members".
    r = await client.get("/consent/admin/subject-shares", headers=collector_headers())
    assert r.status_code == 422
