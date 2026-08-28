"""Block C — consent/disclosure provenance emits and the ingestion record.

The connector emits provenance from the API layer *after* the transaction
commits (the ``access_revoked`` pattern), so these tests override ``get_prov``
with a recorder and assert the right event fires with the right fields.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.dependencies import get_db, get_notifier, get_prov
from connector.main import create_app
from connector.services import consent_service
from connector.services import consent_vocabulary
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    consent_snapshot_hash,
    dataset_consent_snapshot,
)
from tests import make_headers, make_vc_headers

DATASET = "datasets.silver.meters"
SUBJECT_DID = "did:web:rec.dataspaces.localhost:users:sub-001"
SUBJECT = make_vc_headers(subject_did=SUBJECT_DID)
PROVISION = make_headers(scope="connector.consent.provision")
INGEST = make_headers(scope="connector.ingestion.record")
DISCLOSE = make_headers(scope="connector.disclosure.record")


class FakeProv:
    """Records emitted events instead of POSTing them to ds-provenance."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def _record(self, name: str, **kwargs) -> None:
        self.calls.append((name, kwargs))

    async def consent_granted(self, **kwargs) -> None:
        await self._record("consent_granted", **kwargs)

    async def consent_revoked(self, **kwargs) -> None:
        await self._record("consent_revoked", **kwargs)

    async def data_ingested(self, **kwargs) -> None:
        await self._record("data_ingested", **kwargs)

    # `data_disclosed` is here now because `POST /admin/disclosure` emits it.
    # It was deliberately absent while nothing did: a double that answers for a
    # call nobody makes is how the dead emitter on the real bridge stayed
    # invisible. Adding one is only correct alongside a route that calls it.
    async def data_disclosed(self, **kwargs) -> None:
        await self._record("data_disclosed", **kwargs)

    def of(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]


@pytest.fixture(autouse=True)
def _allow_membership(monkeypatch):
    async def _member(*_args, **_kwargs):
        return True

    monkeypatch.setattr("connector.api.v1.consent.check_subject_membership", _member)


@pytest_asyncio.fixture(scope="function")
async def prov_client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    fake = FakeProv()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_prov] = lambda: fake
    app.dependency_overrides[get_notifier] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, fake


async def _seed(engine, **overrides) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    base = dict(
        subject_id=SUBJECT_DID,
        dataset_id=DATASET,
        consumer_id=WILDCARD_CONSUMER,
        status="granted",
        purpose=["FlexibilityResearch"],
        controller="example-org",
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        transfer_ids=[],
    )
    base.update(overrides)
    row = ConsentRequestORM(**base)
    async with factory() as session:
        async with session.begin():
            session.add(row)
    return row.id


# ── consent emits ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_shares_emits_consent_granted(prov_client):
    client, fake = prov_client
    r = await client.post(
        "/consent/admin/shares",
        headers=PROVISION,
        json={
            "subject_id": SUBJECT_DID,
            "offer_id": "test-flexibility",
            "enabled": True,
            # Granting requires evidence of what the person was shown.
            "legal_basis": {
                "source": "test-harness",
                "consent_text_version": "1.0",
                "rendered_text_sha256": "c" * 64,
            },
        },
    )
    assert r.status_code == 200, r.text
    granted = fake.of("consent_granted")
    assert len(granted) == 1
    call = granted[0]
    assert call["dataset_id"] == DATASET
    assert call["consumer_id"] == WILDCARD_CONSUMER
    assert call["purpose"] == ["FlexibilityResearch"]
    assert call["offer_id"] == "test-flexibility"
    assert call["event_id"].startswith("consent-granted:")
    assert call["legal_basis"] is not None


@pytest.mark.asyncio
async def test_my_shares_toggle_emits_granted_then_revoked(prov_client):
    client, fake = prov_client
    enable = await client.post(
        "/consent/my/shares",
        headers=SUBJECT,
        json={"offer_id": "test-flexibility", "enabled": True},
    )
    assert enable.status_code == 200, enable.text
    assert len(fake.of("consent_granted")) == 1

    disable = await client.post(
        "/consent/my/shares",
        headers=SUBJECT,
        json={"offer_id": "test-flexibility", "enabled": False},
    )
    assert disable.status_code == 200, disable.text
    assert len(fake.of("consent_revoked")) == 1
    assert fake.of("consent_revoked")[0]["dataset_id"] == DATASET


@pytest.mark.asyncio
async def test_approve_emits_consent_granted(engine, prov_client):
    client, fake = prov_client
    consent_id = await _seed(
        engine, consumer_id="did:web:third-party.dataspaces.localhost", status="pending",
        decided_at=None,
    )
    r = await client.post(f"/consent/my/{consent_id}/approve", headers=SUBJECT)
    assert r.status_code == 200, r.text
    granted = fake.of("consent_granted")
    assert len(granted) == 1
    assert granted[0]["event_id"] == f"consent-granted:{consent_id}"


@pytest.mark.asyncio
async def test_revoke_emits_consent_revoked(engine, prov_client):
    client, fake = prov_client
    consent_id = await _seed(
        engine, consumer_id="did:web:third-party.dataspaces.localhost", status="granted",
    )
    r = await client.post(f"/consent/my/{consent_id}/revoke", headers=SUBJECT)
    assert r.status_code == 200, r.text
    revoked = fake.of("consent_revoked")
    assert len(revoked) == 1
    assert revoked[0]["event_id"] == f"consent-revoked:{consent_id}"


# ── ingestion record ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingestion_records_snapshot_and_emits(engine, prov_client):
    client, fake = prov_client
    await _seed(engine)  # one standing granted wildcard row

    r = await client.post(
        "/admin/ingestion",
        headers=INGEST,
        json={"dataset_id": DATASET, "source_ref": "dso-2026-02", "record_count": 99,
              "agreement_ref": "dpa-1.0"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["granted_party_count"] == 1
    assert len(body["consent_snapshot_hash"]) == 64

    ingested = fake.of("data_ingested")
    assert len(ingested) == 1
    assert ingested[0]["dataset_id"] == DATASET
    assert ingested[0]["consent_snapshot_hash"] == body["consent_snapshot_hash"]
    assert ingested[0]["record_count"] == 99


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_ingestion_requires_scope(prov_client):
    client, _ = prov_client
    r = await client.post(
        "/admin/ingestion",
        headers=make_headers(scope="connector.webhook"),
        json={"dataset_id": DATASET},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ingestion_unknown_dataset_422(prov_client):
    client, _ = prov_client
    r = await client.post(
        "/admin/ingestion", headers=INGEST, json={"dataset_id": "datasets.no.such"}
    )
    assert r.status_code == 422


# ── disclosure record ─────────────────────────────────────────────────────────
#
# `L-2` requires a `DataDisclosed` to carry a recomputable `consent_snapshot_hash`.
# Until this route existed the event's only producer was out of repo, and that
# producer cannot compute the hash — it is a fingerprint of *this* service's
# consent DB. The rule was addressed to the one component unable to comply.


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_disclosure_computes_the_snapshot_the_caller_cannot(engine, prov_client):
    """The caller does not send a hash and could not honestly produce one."""
    client, fake = prov_client
    await _seed(engine)  # one standing granted wildcard row

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={
            "dataset_id": DATASET,
            "recipient_ref": "dso-org",
            "purpose": ["GridMonitoring"],
            "columns": ["pod_code", "consumption"],
            "subject_count": 10,
            "agreement_ref": "dpa-1.0",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["granted_party_count"] == 1
    assert len(body["consent_snapshot_hash"]) == 64

    disclosed = fake.of("data_disclosed")
    assert len(disclosed) == 1
    assert disclosed[0]["dataset_id"] == DATASET
    assert disclosed[0]["recipient_ref"] == "dso-org"
    assert disclosed[0]["consent_snapshot_hash"] == body["consent_snapshot_hash"]
    # The same consent state, hashed the same way an ingestion of it would be —
    # recomputable, which is the whole of what `L-2` asks the hash to be.
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        expected, _ = await dataset_consent_snapshot(session, DATASET)
    assert disclosed[0]["consent_snapshot_hash"] == expected


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_a_disclosure_that_cannot_be_recorded_does_not_proceed(engine, monkeypatch):
    """`L-1`'s failure policy is chosen by position. A transfer that already
    happened is recorded non-fatally, because refusing loses the fact too. This
    one has *not* happened — the caller is about to hand the data over — so a
    provenance failure must refuse, or the disclosure goes ahead unrecorded.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    class Broken:
        async def data_disclosed(self, **_kwargs):
            raise RuntimeError("provenance unreachable")

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_prov] = lambda: Broken()
    app.dependency_overrides[get_notifier] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/admin/disclosure",
            headers=DISCLOSE,
            json={"dataset_id": DATASET, "recipient_ref": "dso-org"},
        )
    assert r.status_code == 502, r.text


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_disclosure_requires_its_own_scope(prov_client):
    """Not `connector.ingestion.record`. The two are opposite directions across
    the same boundary, and the discloser has no business recording inbound
    handovers.
    """
    client, _ = prov_client
    r = await client.post(
        "/admin/disclosure",
        headers=INGEST,
        json={"dataset_id": DATASET, "recipient_ref": "dso-org"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_disclosure_unknown_dataset_422(prov_client):
    client, _ = prov_client
    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={"dataset_id": "datasets.no.such", "recipient_ref": "dso-org"},
    )
    assert r.status_code == 422


# ── disclosure by offer ───────────────────────────────────────────────────────
#
# The caller `POST /admin/disclosure` was built for holds an **offer**, never a
# dataset: an onboarding service's POD-list export selects the supply points whose
# owners consented to one sharing offer, and `D-13` keeps dataset keys out of the
# public projection deliberately, so it has no way to learn them. The route asked
# for the one argument the caller could not produce.
#
# `vocab.datasets_for_offer` is the authoritative mapping and
# `POST /consent/admin/shares` already expands an offer with it. These assert the
# other side of the same seam takes the same argument for the same reason — and
# that `L-2` is untouched: the hash stays dataset-scoped, one event per dataset.


def _two_datasets_for_one_offer(tmp_path, monkeypatch) -> tuple[str, str]:
    """A governance file where two datasets declare the same offer.

    The shipped fixture resolves every offer to exactly one dataset, because one
    dataset declares all three — which is precisely the state in which a caller
    reading `datasets_for_offer(...)[0]` is correct and stays correct until it
    isn't. Asserting the expansion needs a fixture where the list is genuinely a
    list, and it has to be the **real** mapping rather than a stubbed one, or the
    test proves the loop and not the wiring.
    """
    import yaml
    from connector.config import get_settings

    src = pathlib.Path(__file__).parent / "fixtures" / "governance.yaml"
    doc = yaml.safe_load(src.read_text())
    second = {
        **doc["sources"]["datasets.silver.meters"],
        "title": "Smart Meter Readings, second table (test)",
    }
    second["dataspace"] = {
        **second["dataspace"],
        "sharing_offers": ["test-flexibility"],
        "asset": {"id": "datasets.silver.meters_daily"},
    }
    doc["sources"]["datasets.silver.meters_daily"] = second

    path = tmp_path / "governance.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "governance_yaml_path", str(path))
    consent_vocabulary.reset_caches()
    return DATASET, "datasets.silver.meters_daily"


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_disclosure_by_offer_emits_one_event_per_dataset(
    engine, prov_client, tmp_path, monkeypatch
):
    """One `DataDisclosed` per dataset the offer resolves to, each with that
    dataset's own hash — so the route and the mapping cannot drift apart."""
    client, fake = prov_client
    first, second = _two_datasets_for_one_offer(tmp_path, monkeypatch)
    await _seed(engine)  # a granted wildcard row on `first` only

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={
            "offer_id": "test-flexibility",
            "recipient_ref": "dso-org",
            "purpose": ["FlexibilityResearch"],
            "columns": ["pod_code", "consumption"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offer_id"] == "test-flexibility"
    assert [d["dataset_id"] for d in body["disclosures"]] == list(
        consent_vocabulary.datasets_for_offer("test-flexibility")
    )
    assert {first, second} == {d["dataset_id"] for d in body["disclosures"]}

    disclosed = fake.of("data_disclosed")
    assert len(disclosed) == 2
    assert {e["dataset_id"] for e in disclosed} == {first, second}

    # Each event carries the hash of *its own* dataset's consent state, and the
    # two states differ here — one dataset has a granted row and the other has
    # none — so a single hash reused across both would be visible.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for event in disclosed:
            expected, count = await dataset_consent_snapshot(session, event["dataset_id"])
            assert event["consent_snapshot_hash"] == expected
            reported = next(
                d for d in body["disclosures"] if d["dataset_id"] == event["dataset_id"]
            )
            assert reported["consent_snapshot_hash"] == expected
            assert reported["granted_party_count"] == count
    assert len({e["consent_snapshot_hash"] for e in disclosed}) == 2


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_disclosure_by_offer_does_not_flatten_to_one_dataset(
    engine, prov_client, tmp_path, monkeypatch
):
    """The response shape follows the **argument**, not the resolution count.

    A caller that reads `dataset_id` off an offer-scoped response would be reading
    one of several and would work on today's fixture. There is no such key.
    """
    client, _ = prov_client
    _two_datasets_for_one_offer(tmp_path, monkeypatch)
    await _seed(engine)

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={"offer_id": "test-flexibility", "recipient_ref": "dso-org"},
    )
    assert r.status_code == 200, r.text
    assert "dataset_id" not in r.json()
    assert "consent_snapshot_hash" not in r.json()


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_disclosure_by_offer_keys_each_event_distinctly(
    engine, prov_client, tmp_path, monkeypatch
):
    """The provenance service dedupes on `event_id`. Reusing the caller's id for
    every dataset would record the first event and discard the rest as duplicates
    — a 200 saying two, and one event in the graph."""
    client, fake = prov_client
    _two_datasets_for_one_offer(tmp_path, monkeypatch)
    await _seed(engine)

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={
            "offer_id": "test-flexibility",
            "recipient_ref": "dso-org",
            "event_id": "export-42",
        },
    )
    assert r.status_code == 200, r.text
    ids = [e["event_id"] for e in fake.of("data_disclosed")]
    assert len(set(ids)) == 2, ids
    assert all(i.startswith("export-42:") for i in ids), ids


@pytest.mark.asyncio
async def test_disclosure_by_offer_keeps_the_dataset_form_unchanged(engine, prov_client):
    """An alternative argument, not a replacement: the `dataset_id` form still
    answers with the three keys it always did."""
    client, _ = prov_client
    await _seed(engine)

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={"dataset_id": DATASET, "recipient_ref": "dso-org", "event_id": "export-7"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataset_id"] == DATASET
    assert len(body["consent_snapshot_hash"]) == 64
    assert body["granted_party_count"] == 1
    assert body["disclosures"][0]["dataset_id"] == DATASET
    assert "offer_id" not in body


@pytest.mark.asyncio
async def test_disclosure_by_offer_accepts_a_contract_based_offer(engine, prov_client):
    """Unlike `POST /consent/admin/shares`, which refuses one because provisioning
    consent for a contractual basis manufactures a choice that does not exist. A
    disclosure records a handover that happened, whatever authorised it."""
    client, fake = prov_client
    await _seed(engine)

    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={"offer_id": "test-incentives", "recipient_ref": "dso-org"},
    )
    assert r.status_code == 200, r.text
    assert len(fake.of("data_disclosed")) == 1


@pytest.mark.asyncio
async def test_disclosure_unknown_offer_422(prov_client):
    client, _ = prov_client
    r = await client.post(
        "/admin/disclosure",
        headers=DISCLOSE,
        json={"offer_id": "no-such-offer", "recipient_ref": "dso-org"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"recipient_ref": "dso-org"},
        {"recipient_ref": "dso-org", "dataset_id": DATASET, "offer_id": "test-flexibility"},
    ],
    ids=["neither", "both"],
)
async def test_disclosure_needs_exactly_one_target(prov_client, body):
    """Naming both is two answers to one question; naming neither discloses
    nothing."""
    client, _ = prov_client
    r = await client.post("/admin/disclosure", headers=DISCLOSE, json=body)
    assert r.status_code == 422


# ── snapshot hash unit ────────────────────────────────────────────────────────

def _row(**overrides) -> ConsentRequestORM:
    base = dict(
        subject_id=SUBJECT_DID,
        dataset_id=DATASET,
        consumer_id=WILDCARD_CONSUMER,
        status="granted",
        purpose=["FlexibilityResearch"],
        controller_role="operator",
        legal_basis={"consent_text_version": "1.0"},
    )
    base.update(overrides)
    return ConsentRequestORM(**base)


@pytest.mark.rule("L-2")
def test_snapshot_hash_is_stable_and_order_independent():
    a = _row(subject_id="did:web:a")
    b = _row(subject_id="did:web:b")
    assert consent_snapshot_hash([a, b]) == consent_snapshot_hash([b, a])
    assert len(consent_snapshot_hash([a])) == 64


@pytest.mark.rule("L-2")
def test_snapshot_hash_reacts_to_purpose_and_version():
    base = consent_snapshot_hash([_row()])
    assert consent_snapshot_hash([_row(purpose=["IncentiveCalculation"])]) != base
    assert consent_snapshot_hash([_row(legal_basis={"consent_text_version": "2.0"})]) != base


@pytest.mark.rule("L-2", "D-14")
def test_snapshot_hash_reacts_to_the_controller():
    """The controller is a dimension of the evidence (#13).

    `D-14` makes it decisive — the wildcard "never admits a new controller" — so
    a fingerprint that cannot tell one controller from another cannot prove which
    consent state authorised a handover. Same subject, same dataset, same purpose,
    same controller role: only the controller differs, and that has to be enough.
    """
    base = consent_snapshot_hash([_row(controller="did:web:dso-a")])
    assert consent_snapshot_hash([_row(controller="did:web:dso-b")]) != base


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_dataset_snapshot_counts_only_granted(engine):
    await _seed(engine, subject_id="did:web:a", status="granted")
    await _seed(engine, subject_id="did:web:b", status="revoked",
                revoked_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        _hash, count = await dataset_consent_snapshot(session, DATASET)
    assert count == 1


# ── the snapshot collapse (#12) ───────────────────────────────────────────────
#
# `latest_granted_rows_for_dataset` collapsed on `(subject_id, consumer_id)` and
# ignored `offer_id`, so a decline of one offer erased a grant on another and the
# hash came out **narrower than the disclosure it authorised** — the one direction
# `L-2` cannot tolerate. Keyed per offer now, matching the enforcement path.


async def _decide(session, offer: str, status: str, **overrides):
    """A settled wildcard decision about one offer, written straight to the DB."""
    async with session.begin():
        session.add(
            _row(
                offer_id=offer,
                status=status,
                purpose=[
                    "FlexibilityResearch"
                    if offer == "test-flexibility"
                    else "EnergyCommunityOperation"
                ],
                requested_at=overrides.pop("at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
                **overrides,
            )
        )


@pytest.mark.rule("L-2", "D-14", "D-15")
@pytest.mark.asyncio
async def test_the_snapshot_keeps_a_grant_when_another_offer_is_declined(engine):
    """The defect: the hash must not be narrower than what it authorises.

    One subject, two offers over one dataset, granting the first and declining
    the second. The decline was simply the more recent row, so the collapse kept
    only that and then discarded it as not `granted` — the subject vanished from
    the evidence while their data still left under the offer they granted.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _decide(session, "test-flexibility", "granted")
        await _decide(
            session,
            "test-grid-planning",
            "revoked",
            at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            revoked_at=datetime(2026, 2, 1, 1, tzinfo=timezone.utc),
        )

        rows = await consent_service.latest_granted_rows_for_dataset(session, DATASET)
        _hash, count = await dataset_consent_snapshot(session, DATASET)

    assert [r.offer_id for r in rows] == ["test-flexibility"]
    assert count == 1


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_the_snapshot_does_not_depend_on_decision_order(engine):
    """The same consent state must fingerprint the same however it was reached.

    Order-dependence is what made this a defect rather than an imprecision:
    evidence that disagrees with itself is not evidence. Both orderings below
    describe one state — granted to flexibility, declined grid-planning — so both
    must hash to the same digest and count the same grant. Recorded in one order,
    cleared, then recorded in the other, because the "order" is the decision
    timestamps rather than the insertion sequence.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    late = datetime(2026, 2, 1, tzinfo=timezone.utc)

    async def snapshot_for(grant_at, decline_at):
        async with factory() as session:
            async with session.begin():
                await session.execute(delete(ConsentRequestORM))
            await _decide(session, "test-flexibility", "granted", at=grant_at)
            await _decide(
                session,
                "test-grid-planning",
                "revoked",
                at=decline_at,
                revoked_at=decline_at,
            )
            return await dataset_consent_snapshot(session, DATASET)

    granted_first = await snapshot_for(early, late)
    declined_first = await snapshot_for(late, early)

    assert granted_first == declined_first
    assert granted_first[1] == 1


@pytest.mark.rule("L-2", "D-11")
@pytest.mark.asyncio
async def test_two_grants_by_one_subject_are_two_grants_in_the_count(engine):
    """`granted_party_count` counts grants, not parties, now the rows are keyed
    per offer — one subject consenting to two offers contributes both.

    The tuple is not keyed on the offer: `D-11` makes the consent key
    `(subject, purpose, controller-role)` — and `D-14` adds the controller — so
    two offers are distinguished by what they are *for* and *for whom*, rather
    than by an offer id added to the evidence.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _decide(session, "test-flexibility", "granted")
        await _decide(
            session,
            "test-grid-planning",
            "granted",
            at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        _hash, count = await dataset_consent_snapshot(session, DATASET)

    assert count == 2


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_a_redecided_offer_still_collapses_to_its_latest(engine):
    """Per-offer keying must not turn a change of mind into two rows.

    The collapse is still a collapse — it is only keyed on more. A subject who
    granted, withdrew and granted the same offer again counts once.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _decide(session, "test-flexibility", "revoked",
                      revoked_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc))
        await _decide(session, "test-flexibility", "granted",
                      at=datetime(2026, 2, 1, tzinfo=timezone.utc))
        _hash, count = await dataset_consent_snapshot(session, DATASET)

    assert count == 1


# ── the controller-blind tuple (#13) ──────────────────────────────────────────
#
# `consent_snapshot_hash` hashed `(subject, dataset, purpose, controller_role,
# consent_text_version)`, so two offers over one dataset agreeing on purpose and
# controller role but naming **different controllers** produced byte-identical
# tuples. `D-14` treats the controller as decisive, so `L-2`'s evidence has to.


@pytest.mark.rule("L-2", "D-14")
@pytest.mark.asyncio
async def test_two_controllers_sharing_a_role_and_purpose_are_distinguishable(engine):
    """The reachable configuration: two DSOs, both `operations`, one purpose.

    Nothing forbids it — `D-11a` constrains which roles a controller may name and
    says nothing about two controllers holding the same one — and before this the
    two states below hashed identically, so the `DataDisclosed` recording a
    handover to the first was indistinguishable from one recording a handover to
    the second.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def snapshot_disclosing_to(controller: str):
        async with factory() as session:
            async with session.begin():
                await session.execute(delete(ConsentRequestORM))
                session.add(
                    _row(
                        offer_id="test-grid-planning",
                        status="granted",
                        purpose=["EnergyCommunityOperation"],
                        controller=controller,
                        controller_role="operations",
                    )
                )
            digest, _count = await dataset_consent_snapshot(session, DATASET)
            return digest

    to_a = await snapshot_disclosing_to("did:web:dso-a")
    to_b = await snapshot_disclosing_to("did:web:dso-b")
    assert to_a != to_b


@pytest.mark.rule("L-2")
@pytest.mark.asyncio
async def test_the_same_controller_still_fingerprints_the_same(engine):
    """The added dimension must not make the hash unrecomputable.

    A state re-recorded unchanged has to reproduce its digest, or `L-2`'s
    "recomputable" claim fails in the other direction.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def snapshot():
        async with factory() as session:
            async with session.begin():
                await session.execute(delete(ConsentRequestORM))
                session.add(
                    _row(
                        offer_id="test-grid-planning",
                        status="granted",
                        purpose=["EnergyCommunityOperation"],
                        controller="did:web:dso-a",
                        controller_role="operations",
                    )
                )
            digest, _count = await dataset_consent_snapshot(session, DATASET)
            return digest

    assert await snapshot() == await snapshot()
