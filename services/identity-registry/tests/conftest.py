
import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from identity_registry.config import Settings
from identity_registry.db.engine import Base
from identity_registry.dependencies import get_db, get_did_resolver, get_settings_dep
from identity_registry.main import create_app
from identity_registry.services.did import build_did_document
from identity_registry.services.did_resolver import DidResolutionError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def make_headers(scope: str = "identity-registry.admin") -> dict:
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "preferred_username": "service-account-svc-ds-identity-registry",
        },
        "secret",
        algorithm="HS256",
    )
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


class StubResolver:
    """Serves DID documents from a dict instead of over HTTP.

    The production resolver always goes through did:web — deliberately, so dev
    and production run the same code — which means a unit test has to supply the
    documents. Registering one here is the test's way of saying "this DID is
    published, with this key".
    """

    def __init__(self, documents: dict[str, dict] | None = None):
        self.documents = documents or {}

    def publish(self, did: str, public_jwk: dict) -> None:
        self.documents[did] = build_did_document(did, public_jwk)

    async def resolve(self, did: str) -> dict:
        if did not in self.documents:
            raise DidResolutionError(f"{did} is not published")
        return self.documents[did]


@pytest.fixture
def resolver(client):
    """Install a stub DID resolver into the app under test, and hand it back."""
    stub = StubResolver()
    client._transport.app.dependency_overrides[get_did_resolver] = lambda: stub
    return stub


@pytest_asyncio.fixture(scope="function")
async def client(engine, tmp_path):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    test_settings = Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
    )

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: test_settings

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
