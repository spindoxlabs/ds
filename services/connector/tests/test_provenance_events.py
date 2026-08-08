"""Block C — consent/disclosure provenance emits and the ingestion record.

The connector emits provenance from the API layer *after* the transaction
commits (the ``access_revoked`` pattern), so these tests override ``get_prov``
with a recorder and assert the right event fires with the right fields.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.dependencies import get_db, get_notifier, get_prov
from connector.main import create_app
from connector.services import consent_service
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


def test_snapshot_hash_is_stable_and_order_independent():
    a = _row(subject_id="did:web:a")
    b = _row(subject_id="did:web:b")
    assert consent_snapshot_hash([a, b]) == consent_snapshot_hash([b, a])
    assert len(consent_snapshot_hash([a])) == 64


def test_snapshot_hash_reacts_to_purpose_and_version():
    base = consent_snapshot_hash([_row()])
    assert consent_snapshot_hash([_row(purpose=["IncentiveCalculation"])]) != base
    assert consent_snapshot_hash([_row(legal_basis={"consent_text_version": "2.0"})]) != base


@pytest.mark.asyncio
async def test_dataset_snapshot_counts_only_granted(engine):
    await _seed(engine, subject_id="did:web:a", status="granted")
    await _seed(engine, subject_id="did:web:b", status="revoked",
                revoked_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        _hash, count = await dataset_consent_snapshot(session, DATASET)
    assert count == 1
