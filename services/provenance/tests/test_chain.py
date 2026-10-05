"""R19 — the event record is append-only, tamper-evident, and person ids age out.

`L-17`: every `domain_events` row is chained (`seq`, `prev_hash`, `record_hash`)
and `GET /prov/chain/verify` recomputes the chain. `L-18`: after the retention
period a row's person ids are replaced by their keyed pseudonyms, and the chain
still verifies, because it hashed the pseudonym from the start.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from provenance.cli import main as admin_main
from provenance.db.models import AccessLogORM, DomainEventORM, ProvNodeORM
from provenance.services import chain

from tests import make_headers
from tests.test_my_events_login import person_client, vc_headers  # noqa: F401

SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
OTHER = "did:web:rec.dataspaces.localhost:users:sub-002"
OLD = datetime.now(timezone.utc) - timedelta(days=400)
NEW = datetime.now(timezone.utc) - timedelta(days=1)


def consent(event_id: str, subject: str = SUBJECT, when: datetime = OLD) -> dict:
    return {
        "event_type": "ConsentGranted",
        "event_id": event_id,
        "occurred_at": when.isoformat(),
        "subject_id": subject,
        "dataset_id": "meters",
        "consumer_did": "did:web:consumer.test",
        "purpose": ["service-provision"],
    }


def query(event_id: str, when: datetime = OLD) -> dict:
    return {
        "event_type": "QueryExecuted",
        "event_id": event_id,
        "occurred_at": when.isoformat(),
        "data_product_id": "urn:dataset:meters",
        "provider_did": "did:web:provider.test",
        "consumer_did": "did:web:consumer.test",
        "subject_id": SUBJECT,
        "authorized_subject_ids": [SUBJECT, OTHER],
    }


async def ingest(client, *events: dict) -> None:
    for event in events:
        r = await client.post("/prov/events", json=event)
        assert r.status_code == 201, r.text


async def verified(client) -> dict:
    r = await client.get("/prov/chain/verify")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# ── L-17: append-only, chained ──────────────────────────────────────────────


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_each_event_is_chained_onto_the_last(client, factory):
    await ingest(client, consent("c-1"), consent("c-2"), query("q-1"))

    async with factory() as s:
        rows = (await s.execute(select(DomainEventORM).order_by(DomainEventORM.seq))).scalars().all()
    assert [r.seq for r in rows] == [1, 2, 3]
    assert rows[0].prev_hash == chain.GENESIS
    assert [r.prev_hash for r in rows[1:]] == [r.record_hash for r in rows[:-1]]

    result = await verified(client)
    assert result["ok"] is True
    assert result["records"] == 3
    assert result["head"] == rows[-1].record_hash


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_a_changed_record_is_found(client, factory):
    await ingest(client, consent("c-1"), consent("c-2"), consent("c-3"))
    async with factory() as s:
        row = (await s.execute(select(DomainEventORM).where(DomainEventORM.seq == 2))).scalar_one()
        row.payload = {**row.payload, "purpose": ["marketing"]}
        await s.commit()

    result = await verified(client)
    assert result["ok"] is False
    assert result["firstFailure"]["seq"] == 2


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_a_changed_column_is_found(client, factory):
    """The promoted columns are what the queries filter on; they are hashed too."""
    await ingest(client, consent("c-1"))
    async with factory() as s:
        await s.execute(update(DomainEventORM).values(consumer_did="did:web:someone-else.test"))
        await s.commit()

    assert (await verified(client))["ok"] is False


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_a_removed_record_is_found(client, factory):
    await ingest(client, consent("c-1"), consent("c-2"), consent("c-3"))
    async with factory() as s:
        await s.execute(delete(DomainEventORM).where(DomainEventORM.seq == 2))
        await s.commit()

    result = await verified(client)
    assert result["ok"] is False
    assert result["firstFailure"]["seq"] == 3


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_rows_from_before_the_chain_are_backfilled(client, factory):
    """What migration `0004` does to an existing store, and `provenance-admin
    backfill` to anything it missed."""
    async with factory() as s:
        for n in (1, 2):
            s.add(
                DomainEventORM(
                    event_type="ConsentGranted",
                    event_id=f"legacy-{n}",
                    occurred_at=OLD,
                    payload=consent(f"legacy-{n}"),
                    subject_id=SUBJECT,
                )
            )
        await s.commit()

    before = await verified(client)
    assert before["ok"] is False and before["unchained"] == 2

    async with factory() as s:
        assert await chain.backfill(s) == 2
        await s.commit()
    await ingest(client, consent("c-new"))

    after = await verified(client)
    assert after["ok"] is True and after["records"] == 3


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_verify_is_a_read_and_needs_the_read_scope(client):
    r = await client.get(
        "/prov/chain/verify", headers=make_headers(scope="provenance.write")
    )
    assert r.status_code == 403
    r = await client.get("/prov/chain/verify", headers=make_headers(scope="provenance.read"))
    assert r.status_code == 200


@pytest.mark.rule("L-17")
@pytest.mark.asyncio
async def test_no_route_changes_or_removes_a_record(client):
    """Writes are `POST`s that add. No `PUT`, `PATCH` or `DELETE` exists anywhere."""
    from provenance.main import create_app

    methods = {
        method
        for route in create_app().routes
        for method in getattr(route, "methods", set())
    }
    assert methods <= {"GET", "HEAD", "POST"}


# ── L-18: person ids age out, the chain still verifies ──────────────────────


@pytest.mark.rule("L-18")
def test_the_chain_hashes_the_pseudonym_not_the_id():
    clear = DomainEventORM(
        event_type="ConsentGranted",
        event_id="c-1",
        occurred_at=OLD,
        payload=consent("c-1"),
        subject_id=SUBJECT,
    )
    pseudonymised = DomainEventORM(
        event_type="ConsentGranted",
        event_id="c-1",
        occurred_at=OLD,
        payload=chain.pseudonymise_payload(consent("c-1")),
        subject_id=chain.pseudonym(SUBJECT),
    )
    assert chain.link(clear, 1, chain.GENESIS) == chain.link(pseudonymised, 1, chain.GENESIS)
    assert SUBJECT not in chain.canonical(clear)
    # Another person's pseudonym is not the same record.
    other = DomainEventORM(
        event_type="ConsentGranted",
        event_id="c-1",
        occurred_at=OLD,
        payload=chain.pseudonymise_payload(consent("c-1", subject=OTHER)),
        subject_id=chain.pseudonym(OTHER),
    )
    assert chain.link(other, 1, chain.GENESIS) != clear.record_hash


@pytest.mark.rule("L-18")
def test_the_pseudonym_is_keyed():
    assert chain.pseudonym(SUBJECT, "key-a") != chain.pseudonym(SUBJECT, "key-b")
    assert chain.pseudonym(chain.pseudonym(SUBJECT)) == chain.pseudonym(SUBJECT)


@pytest.mark.rule("L-18")
@pytest.mark.asyncio
async def test_retention_pseudonymises_old_records_only(client, factory):
    await ingest(client, consent("c-old"), query("q-old"), consent("c-new", OTHER, NEW))

    async with factory() as s:
        result = await chain.apply_retention(s, days=365)
        await s.commit()
    assert result.events == 2 and result.access_log == 1

    async with factory() as s:
        rows = {
            r.event_id: r for r in (await s.execute(select(DomainEventORM))).scalars()
        }
        logs = (await s.execute(select(AccessLogORM))).scalars().all()
        iris = {n.iri for n in (await s.execute(select(ProvNodeORM))).scalars()}
        metas = [
            n.external_meta
            for n in (await s.execute(select(ProvNodeORM))).scalars()
            if n.external_meta
        ]

    old = rows["c-old"]
    assert old.subject_id == chain.pseudonym(SUBJECT)
    assert old.payload["subject_id"] == chain.pseudonym(SUBJECT)
    assert old.pseudonymised_at is not None
    assert rows["q-old"].payload["authorized_subject_ids"] == [
        chain.pseudonym(SUBJECT),
        chain.pseudonym(OTHER),
    ]
    assert logs[0].subject_ids == [chain.pseudonym(SUBJECT), chain.pseudonym(OTHER)]
    # Newer than the period: untouched.
    assert rows["c-new"].subject_id == OTHER
    assert rows["c-new"].pseudonymised_at is None
    # The subject's agent node is renamed: nothing newer names them in clear.
    # The other person's is not: a newer record still does.
    assert SUBJECT not in iris and chain.pseudonym(SUBJECT) in iris
    assert OTHER in iris
    assert not any(SUBJECT in str(m) for m in metas)

    assert (await verified(client))["ok"] is True
    # Idempotent.
    async with factory() as s:
        again = await chain.apply_retention(s, days=365)
        await s.commit()
    assert again.events == 0 and again.access_log == 0


@pytest.mark.rule("L-18")
@pytest.mark.asyncio
async def test_a_person_who_returns_joins_their_pseudonymous_node(client, factory):
    await ingest(client, consent("c-1"))
    async with factory() as s:
        await chain.apply_retention(s, days=365)
        await s.commit()
    await ingest(client, consent("c-2", when=NEW))
    async with factory() as s:
        await chain.apply_retention(s, days=365, now=NEW + timedelta(days=366))
        await s.commit()
        iris = [n.iri for n in (await s.execute(select(ProvNodeORM))).scalars()]
    assert iris.count(chain.pseudonym(SUBJECT)) == 1
    assert SUBJECT not in iris
    assert (await verified(client))["ok"] is True


@pytest.mark.rule("L-18")
@pytest.mark.asyncio
async def test_a_record_given_someone_elses_pseudonym_is_found(client, factory):
    await ingest(client, consent("c-1"), consent("c-2"))
    async with factory() as s:
        await chain.apply_retention(s, days=365)
        await s.execute(
            update(DomainEventORM)
            .where(DomainEventORM.event_id == "c-1")
            .values(subject_id=chain.pseudonym(OTHER))
        )
        await s.commit()
    assert (await verified(client))["ok"] is False


@pytest.mark.rule("L-11", "L-18")
@pytest.mark.asyncio
async def test_the_subject_still_reads_their_pseudonymised_history(
    client, person_client, factory  # noqa: F811
):
    await ingest(client, consent("c-old"), consent("c-new", when=NEW))
    async with factory() as s:
        await chain.apply_retention(s, days=365)
        await s.commit()

    r = await person_client.get("/prov/my/events", headers=vc_headers())
    assert r.status_code == 200, r.text
    assert r.json()["hydra:totalItems"] == 2


@pytest.mark.rule("L-18")
def test_the_retention_period_defaults_to_ten_years(monkeypatch):
    """Unset is not "keep in clear forever": ten years, the ordinary limitation
    period, applies to every deployment that does not choose its own."""
    from provenance.config import Settings

    monkeypatch.delenv("PROVENANCE_PERSON_ID_RETENTION_DAYS", raising=False)
    assert Settings(_env_file=None).person_id_retention_days == 3650


@pytest.mark.rule("L-18")
def test_the_deployment_sets_its_own_retention_period(monkeypatch):
    from provenance.config import Settings

    monkeypatch.setenv("PROVENANCE_PERSON_ID_RETENTION_DAYS", "730")
    assert Settings(_env_file=None).person_id_retention_days == 730


@pytest.mark.rule("L-18")
@pytest.mark.parametrize("value", ["0", "-1", ""])
def test_retention_cannot_be_switched_off(monkeypatch, value):
    from pydantic import ValidationError

    from provenance.config import Settings

    monkeypatch.setenv("PROVENANCE_PERSON_ID_RETENTION_DAYS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.rule("L-18")
def test_the_retention_job_runs_with_the_default_period(capsys, monkeypatch, tmp_path):
    """`provenance-admin retention` with nothing configured pseudonymises what
    is older than ten years and leaves what is younger."""
    from pydantic import TypeAdapter
    from sqlalchemy.ext.asyncio import create_async_engine

    from provenance import cli
    from provenance import config as config_module
    from provenance.db.engine import Base
    from provenance.schemas.events import DomainEvent
    from provenance.services.event_service import ingest_event

    monkeypatch.delenv("PROVENANCE_PERSON_ID_RETENTION_DAYS", raising=False)
    monkeypatch.setattr(config_module, "_settings", None)
    url = f"sqlite+aiosqlite:///{tmp_path / 'record.db'}"
    now = datetime.now(timezone.utc)
    events = TypeAdapter(list[DomainEvent]).validate_python(
        [
            consent("c-11y", when=now - timedelta(days=11 * 365)),
            consent("c-9y", OTHER, when=now - timedelta(days=9 * 365)),
        ]
    )

    async def seed() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as s, s.begin():
            for event in events:
                await ingest_event(s, event)
        await engine.dispose()

    asyncio.run(seed())
    monkeypatch.setattr(
        cli,
        "get_session_factory",
        lambda: async_sessionmaker(create_async_engine(url), expire_on_commit=False),
    )

    assert admin_main(["retention"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["events"] == 1
    cutoff = datetime.fromisoformat(result["cutoff"])
    assert timedelta(days=3649) < now - cutoff < timedelta(days=3651)


@pytest.mark.rule("L-18")
@pytest.mark.parametrize("value", ["0", "-30", "ten"])
def test_the_retention_job_refuses_a_period_below_one_day(capsys, value):
    with pytest.raises(SystemExit) as exit_:
        admin_main(["retention", "--days", value])
    assert exit_.value.code != 0
    assert "--days" in capsys.readouterr().err
