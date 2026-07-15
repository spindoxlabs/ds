import tempfile

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from identity_registry.config import Settings
from identity_registry.db.engine import Base
from identity_registry.dependencies import get_db, get_settings_dep
from identity_registry.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def make_headers(scope: str = "identity-registry.admin") -> dict:
    token = pyjwt.encode({"scope": scope, "sub": "test"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


make_admin_headers = make_headers


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
async def db_session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(engine, tmp_path):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    test_settings = Settings(
        database_url=TEST_DATABASE_URL,
        export_base_path=str(tmp_path),
        oidc_issuer_url=None,
    )

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: test_settings

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
