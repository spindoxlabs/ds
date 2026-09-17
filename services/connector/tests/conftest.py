"""Shared test fixtures for ds-connector."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("CONNECTOR_ROLE", "provider")

# Point the consent vocabulary at the test fixtures before any settings are
# read. Consent writes resolve dataset ids and purposes against these, so the
# suite asserts on a stable vocabulary instead of the dev catalogue.
_FIXTURES = Path(__file__).parent / "fixtures"
os.environ.setdefault(
    "CONNECTOR_GOVERNANCE_YAML_PATH", str(_FIXTURES / "governance.yaml")
)
os.environ.setdefault(
    "CONNECTOR_SHARING_OFFERS_PATH", str(_FIXTURES / "sharing-offers.yaml")
)

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
    from tests import attach_edc

    attach_edc(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


#: The organisation this connector's participant belongs to, as the identity
#: registry would name it. The consent fixtures' offers are `example-org`'s.
OWN_ORGANISATION = "example-org"


@pytest.fixture(autouse=True)
def _own_organisation_collects(monkeypatch):
    """The collector relation, as a registry with no relations would answer it.

    Plan `a-collector-registers-consent-at-the-holder`: a consent write asks the
    registry whether the calling organisation may write here and whose members
    it speaks for. A unit run has no registry, so this answers what one with no
    relations would: this connector's own organisation (`OWN_ORGANISATION`)
    collects for itself, nobody else is accepted. Tests about the relation
    override it (`tests/test_consent_collectors.py`).
    """
    from connector.api.v1 import consent
    from connector.registry.participants import CollectorAnswer

    async def _answer(_request, holder_did, collector_did):
        if holder_did == collector_did:
            return CollectorAnswer(
                True, OWN_ORGANISATION, "a holder collects for itself"
            )
        return CollectorAnswer(False, None, "not an accepted collector")

    monkeypatch.setattr(consent, "check_collector", _answer)
