"""A subject's data keys and every stored EDR are ciphertext at rest.

`db/sealed.py`. What the code reads is unchanged; what the database holds is
not the value. A key event keeps a deterministic, keyed index beside its sealed
key, so equality lookups still work.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.config import DEV_AT_REST_KEY, DEV_KEY_INDEX_SECRET, get_settings
from connector.db import sealed
from connector.db.models import ConsentKeyEventORM, ConsentRequestORM, EdrEntryORM
from connector.db.sealed import PREFIX, SealedValueError, Sealer, seal_rows

POD = "pod:ex-pod-00001"


@pytest.fixture(autouse=True)
def _fresh_sealer():
    sealed.sealer.cache_clear()
    yield
    sealed.sealer.cache_clear()


def _grant(**overrides) -> ConsentRequestORM:
    row = dict(
        subject_id="did:web:rec.example.org:users:ex-00001",
        consumer_id="*",
        dataset_id="datasets.gold.test",
        status="granted",
        decided_by="collector",
        subject_keys=[POD],
    )
    row.update(overrides)
    return ConsentRequestORM(**row)


async def test_the_data_keys_are_ciphertext_in_the_database(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        row = _grant()
        session.add(row)
        await session.commit()

        raw = await session.scalar(
            text("SELECT subject_keys FROM consent_requests WHERE id = :id"),
            {"id": row.id},
        )
        assert raw.startswith(PREFIX)
        assert "ex-pod" not in raw

        stored = await session.scalar(text("SELECT key FROM consent_key_events"))
        assert stored.startswith(PREFIX) and "ex-pod" not in stored

    async with factory() as session:
        again = await session.get(ConsentRequestORM, row.id)
        assert again.subject_keys == [POD]


async def test_a_key_event_is_found_by_its_index(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(_grant())
        session.add(
            _grant(
                subject_id="did:web:rec.example.org:users:ex-00002",
                subject_keys=["pod:ex-pod-00002"],
            )
        )
        await session.commit()

        found = (
            await session.scalars(
                select(ConsentKeyEventORM).where(
                    ConsentKeyEventORM.key_index == sealed.blind_index(POD)
                )
            )
        ).all()
        assert [e.key for e in found] == [POD]


def test_the_index_is_deterministic_and_keyed():
    a = Sealer([DEV_AT_REST_KEY], "one-secret")
    b = Sealer([DEV_AT_REST_KEY], "another-secret")
    assert a.index(POD) == a.index(POD)
    assert a.index(POD) != b.index(POD)
    # The ciphertext is not: two seals of one value differ.
    assert a.seal(POD) != a.seal(POD)


async def test_the_edr_bearer_is_ciphertext_in_the_database(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            EdrEntryORM(
                transfer_id="tp-1",
                endpoint="http://dp/query",
                authorization="eyJ.live-token",
                data_address={"authorization": "eyJ.live-token"},
            )
        )
        await session.commit()
        row = (
            await session.execute(
                text("SELECT authorization, data_address FROM edr_entries")
            )
        ).one()
        assert all(v.startswith(PREFIX) and "live-token" not in v for v in row)

    async with factory() as session:
        edr = await session.get(EdrEntryORM, "tp-1")
        assert edr.authorization == "eyJ.live-token"
        assert edr.data_address == {"authorization": "eyJ.live-token"}


def test_a_value_no_key_opens_is_an_error_not_the_stored_text():
    stored = Sealer([Fernet.generate_key().decode()], "x").seal(POD)
    with pytest.raises(SealedValueError):
        Sealer([DEV_AT_REST_KEY], "x").open(stored)
    with pytest.raises(SealedValueError):
        Sealer([DEV_AT_REST_KEY], "x").open(POD)


def test_a_rotation_opens_old_rows_and_seals_under_the_new_key():
    new = Fernet.generate_key().decode()
    old_row = Sealer([DEV_AT_REST_KEY], "x").seal(POD)
    rotated = Sealer([new, DEV_AT_REST_KEY], "x")
    resealed = rotated.reseal(old_row)
    assert Sealer([new], "x").open(resealed) == POD


async def test_the_backfill_seals_plaintext_rows_and_is_idempotent(engine):
    """What migration 0015 and `reseal` run."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO consent_key_events (id, consent_id, dataset_id, "
                "consumer_id, key, key_index, event, cause, at) VALUES "
                "('e1', 'c1', 'd', '*', :k, '', 'added', 'backfill', "
                "'2026-10-01 00:00:00')"
            ),
            {"k": POD},
        )
        s = Sealer([DEV_AT_REST_KEY], DEV_KEY_INDEX_SECRET)
        await conn.run_sync(seal_rows, s, plaintext_ok=True)
        first = (
            await conn.execute(text("SELECT key, key_index FROM consent_key_events"))
        ).one()
        await conn.run_sync(seal_rows, s, plaintext_ok=False)
        second = (
            await conn.execute(text("SELECT key, key_index FROM consent_key_events"))
        ).one()

    assert first.key.startswith(PREFIX) and s.open(first.key) == POD
    assert first.key_index == s.index(POD) == second.key_index
    assert s.open(second.key) == POD


async def test_reseal_refuses_a_row_that_was_never_sealed(engine):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO edr_entries (transfer_id, endpoint, auth_type, "
                "authorization, data_address, received_at) VALUES "
                "('tp-9', 'e', 'bearer', 'plain', '{}', '2026-10-01 00:00:00')"
            )
        )
        with pytest.raises(SealedValueError):
            await conn.run_sync(
                seal_rows, Sealer([DEV_AT_REST_KEY], "x"), plaintext_ok=False
            )


def test_the_dev_keys_are_the_settings_defaults():
    settings = get_settings()
    assert settings.at_rest_keys == DEV_AT_REST_KEY
    assert settings.key_index_secret == DEV_KEY_INDEX_SECRET


@pytest.mark.parametrize(
    "env",
    [
        {"CONNECTOR_AT_REST_KEYS": DEV_AT_REST_KEY},
        {"CONNECTOR_KEY_INDEX_SECRET": DEV_KEY_INDEX_SECRET},
    ],
)
async def test_outside_dev_the_dev_keys_refuse_to_start(monkeypatch, env):
    from ds_auth.production import InsecureProductionConfig

    from connector.main import create_app, lifespan

    monkeypatch.setenv("CONNECTOR_AT_REST_KEYS", Fernet.generate_key().decode())
    monkeypatch.setenv("CONNECTOR_KEY_INDEX_SECRET", "a-real-index-secret")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DS_ENV", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(InsecureProductionConfig) as refused:
            async with lifespan(create_app()):
                pass
        assert next(iter(env)) in str(refused.value)
    finally:
        get_settings.cache_clear()


async def test_a_malformed_key_refuses_to_start_even_in_dev(monkeypatch):
    from connector.main import create_app, lifespan

    monkeypatch.setenv("CONNECTOR_AT_REST_KEYS", "not-a-fernet-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="not a Fernet key"):
            async with lifespan(create_app()):
                pass
    finally:
        get_settings.cache_clear()
