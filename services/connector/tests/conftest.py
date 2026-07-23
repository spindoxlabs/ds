"""Shared test fixtures for ds-connector."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("CONNECTOR_ROLE", "provider")

# Point the consent vocabulary at the test fixtures before any settings are
# read. Consent writes resolve dataset ids and purposes against these, so the
# suite asserts on a stable vocabulary instead of the dev catalogue.
_FIXTURES = Path(__file__).parent / "fixtures"
os.environ.setdefault("CONNECTOR_GOVERNANCE_YAML_PATH", str(_FIXTURES / "governance.yaml"))
os.environ.setdefault("CONNECTOR_SHARING_OFFERS_PATH", str(_FIXTURES / "sharing-offers.yaml"))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.db.engine import Base
from connector.dependencies import get_db
from connector.main import create_app
from connector.services import consent_vocabulary


@pytest.fixture(autouse=True)
def _fresh_vocabulary():
    """Governance and offers are cached per process — reload them per test."""
    consent_vocabulary.reset_caches()
    yield
    consent_vocabulary.reset_caches()

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
