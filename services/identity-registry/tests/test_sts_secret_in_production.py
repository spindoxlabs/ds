"""A placeholder STS secret is refused **before** it is stored, not only at boot.

`ensure_identity` (run by `ir-cli participant init`, the chart's `identity` init
container) writes the hash of `IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET` into the
participant's own database on every start. The service's lifespan guard refused a
placeholder, but only after that write. On a cluster that is a rollout which fails
its guard and still replaces the stored hash under the pod that is serving: the
healthy pod's own EDC then gets `invalid_client` from its STS, and rolling back does
not undo it (found by the first cluster install, 2026-10-09).

*Red:* store the hash before checking, or check only in the service lifespan.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from ds_auth.production import InsecureProductionConfig, ProductionGuard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from identity_registry.config import Settings, register_participant_sts_secret
from identity_registry.db.models import Base, Participant
from identity_registry.services import participant_bootstrap as boot
from identity_registry.services.crypto import verify_sts_secret

DID = "did:web:holder.example.org"
REAL = "a-real-sts-secret-the-participant-chose"


def _settings(secret: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_issuer_url=None,
        role="participant",
        participant_did=DID,
        identity_registry_public_url="https://holder.example.org",
        participant_dsp_address="https://holder.example.org/protocol/2025-1",
        encryption_key="holder-instance-key-not-the-anchors",
        participant_sts_secret=secret,
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _stored(db) -> str:
    row = (await db.execute(select(Participant).where(Participant.did == DID))).scalar_one()
    return row.sts_client_secret


@pytest.mark.parametrize("placeholder", ["CHANGE_ME", "changeme", "insecure-dev-secret", "password"])
def test_a_placeholder_or_dev_sts_secret_is_a_violation(placeholder):
    guard = ProductionGuard("identity-registry", env="production")
    register_participant_sts_secret(guard, _settings(placeholder))
    assert {v.setting for v in guard.violations} == {"IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET"}


def test_a_chosen_sts_secret_passes():
    guard = ProductionGuard("identity-registry", env="production")
    register_participant_sts_secret(guard, _settings(REAL))
    assert guard.violations == []


@pytest.mark.asyncio
async def test_under_production_a_placeholder_never_replaces_the_stored_secret(db, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    await boot.ensure_identity(db, _settings(REAL))
    await db.commit()
    assert verify_sts_secret(REAL, await _stored(db))

    with pytest.raises(InsecureProductionConfig, match="IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET"):
        await boot.ensure_identity(db, _settings("CHANGE_ME"))
    await db.rollback()

    assert verify_sts_secret(REAL, await _stored(db)), "the serving pod's secret was replaced"


@pytest.mark.asyncio
async def test_under_dev_the_dev_secret_is_still_accepted(db, monkeypatch):
    monkeypatch.setenv("DS_ENV", "dev")
    await boot.ensure_identity(db, _settings("insecure-dev-secret"))
    await db.commit()
    assert verify_sts_secret("insecure-dev-secret", await _stored(db))
