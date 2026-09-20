"""Tests for JWT scope enforcement on provenance endpoints."""

import pytest
import pytest_asyncio
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import make_headers
from provenance.db.engine import Base
from provenance.dependencies import get_db
from provenance.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

#: Every read this service publishes to a scoped caller. The subject's own view
#: (`GET /prov/my/events`) is deliberately absent: it authenticates a person, not
#: a scope, and `test_events_query.py` pins that separation from both sides.
READ_ROUTES = [
    "/prov/events",
    "/prov/entities",
    "/prov/activities",
    "/prov/agents",
    "/prov/lineage/urn:test",
    "/audit/log",
    "/audit/log/summary?dataset_id=datasets.gold.weather",
]

#: Routes that carry no scope guard, and why each one is allowed to.
UNSCOPED_ROUTES = {
    "/health": "liveness, read by an orchestrator that holds no token",
    "/metrics": "scraped; reachability is a NetworkPolicy question (ADR/knowledge)",
    "/prov/context": "the JSON-LD context is public by definition",
    "/prov/my/events": "authenticates a person by verifiable credential, not a scope",
}


def _guards(route: APIRoute) -> list[tuple[str, ...]]:
    """The permission sets this route is guarded by, one entry per guard.

    `require_permission(*perms)` returns a closure over `perms`, and FastAPI does
    not surface those as OAuth scopes here — the scheme is bearer, not OAuth2 —
    so the closure is where the answer is. Each entry is one guard (**or** within
    it); the guards are **and**ed, which is exactly why a router-level
    "read or write" floor cannot be tightened by a route-level `write`.
    """
    found: list[tuple[str, ...]] = []
    for dep in get_flat_dependant(route.dependant, skip_repeats=True).dependencies:
        call = dep.call
        if call is None or getattr(call, "__name__", "") != "_dependency":
            continue
        for cell in call.__closure__ or ():
            value = cell.cell_contents
            if (
                isinstance(value, tuple)
                and value
                and all(isinstance(item, str) for item in value)
                and all(item.startswith("provenance.") for item in value)
            ):
                found.append(value)
    return found


@pytest_asyncio.fixture(scope="function")
async def raw_client():
    """Client WITHOUT default auth headers for testing 401/403."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.mark.asyncio
async def test_health_no_auth(raw_client):
    r = await raw_client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_context_no_auth(raw_client):
    r = await raw_client.get("/prov/context")
    assert r.status_code == 200


@pytest.mark.rule("L-10", "L-13")
@pytest.mark.asyncio
async def test_write_without_token_returns_401(raw_client):
    r = await raw_client.post(
        "/prov/events",
        json={
            "type": "CataloguePublished",
            "provider_id": "p",
            "catalogue_id": "c",
        },
    )
    assert r.status_code == 401


@pytest.mark.rule("L-10", "L-13")
@pytest.mark.asyncio
async def test_read_without_token_returns_401(raw_client):
    r = await raw_client.get("/prov/lineage/urn:test")
    assert r.status_code == 401


@pytest.mark.rule("L-10", "L-13")
@pytest.mark.asyncio
async def test_audit_without_token_returns_401(raw_client):
    r = await raw_client.get("/audit/log")
    assert r.status_code == 401


@pytest.mark.rule("L-10", "L-13")
@pytest.mark.asyncio
async def test_write_with_read_scope_returns_403(raw_client):
    r = await raw_client.post(
        "/prov/relations",
        json={"subject": "a", "predicate": "wasAttributedTo", "object": "b"},
        headers=make_headers(scope="provenance.read"),
    )
    assert r.status_code == 403


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_read_with_read_scope_ok(raw_client):
    r = await raw_client.get(
        "/prov/entities",
        headers=make_headers(scope="provenance.read"),
    )
    assert r.status_code == 200


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_write_with_write_scope_ok(raw_client):
    r = await raw_client.post(
        "/prov/entities",
        json={"iri": "urn:test:entity", "type": "prov:Entity"},
        headers=make_headers(scope="provenance.write"),
    )
    assert r.status_code == 201


# ── A write scope is not a read scope ────────────────────────────────────────
#
# Measured live on 2026-09-20 against a deployment where two participants share
# one realm: three different organisation clients, each holding
# `provenance.write` and nothing else, read **every event in the holder's
# store** — including a collector's withdrawal `reason`, which `ADR-0019` says is
# "returned by no read".
#
# The route's own comment explained why that was thought safe: *"Each participant
# runs its own provenance store, so this is already scoped to one participant by
# deployment — there is no cross-participant read to guard against here."* The
# store is indeed per participant. The **realm is not**, and a credential issued
# to one participant is accepted by another's store.


@pytest.mark.rule("L-13")
@pytest.mark.parametrize("path", READ_ROUTES)
@pytest.mark.asyncio
async def test_a_write_scope_does_not_confer_read(raw_client, path):
    r = await raw_client.get(path, headers=make_headers(scope="provenance.write"))
    assert r.status_code == 403, f"{path} answered {r.status_code}"


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_a_read_scope_still_reads(raw_client):
    """The other half: tightening must not lock out the operator consoles.

    Every portal provenance page — `/admin/observability`, `/provider/activity`,
    `/consumer/activity`, `/lineage/[iri]` — calls under the **person's** token,
    and all three operator bundles carry `provenance.read`.
    """
    for path in READ_ROUTES:
        r = await raw_client.get(path, headers=make_headers(scope="provenance.read"))
        # Not `== 200`: a lineage read of a node this empty store never held is
        # legitimately a 404. What is asserted is that the *scope* did not
        # refuse it, which is the half of the split that can regress silently.
        assert r.status_code != 403, f"{path} answered 403: {r.text}"
        assert r.status_code in (200, 404), f"{path} answered {r.status_code}"


@pytest.mark.rule("L-13")
@pytest.mark.asyncio
async def test_a_write_only_caller_can_still_write(raw_client):
    """And the other other half, which is the trap in this fix.

    Router-level dependencies are **and**ed with route-level ones, so simply
    changing the mount to `provenance.read` would require read *and* write of
    every writer — and every connector writes with `provenance.write` alone
    (`svc-ds-connector-<alias>`; rulebook `L-13`). The scopes have to be split
    per route, not tightened at the mount.
    """
    write = make_headers(scope="provenance.write")

    event = await raw_client.post(
        "/prov/events",
        json={
            "event_type": "CataloguePublished",
            "occurred_at": "2026-01-01T10:00:00Z",
            "data_product_id": "urn:test:dataset",
            "provider_did": "did:web:example.org",
        },
        headers=write,
    )
    assert event.status_code == 201, event.text

    entity = await raw_client.post(
        "/prov/entities",
        json={"iri": "urn:test:entity-write", "type": "prov:Entity"},
        headers=write,
    )
    assert entity.status_code == 201, entity.text

    audit = await raw_client.post(
        "/audit/log",
        json={
            "dataset_id": "datasets.gold.weather",
            "consumer_id": "did:web:example.org",
            "row_count": 1,
        },
        headers=write,
    )
    assert audit.status_code == 201, audit.text


@pytest.mark.rule("L-13")
def test_every_route_declares_exactly_one_scope_and_it_matches_the_verb():
    """The structural guard, so the next route added cannot re-open this.

    A mixed router (reads and writes under one mount) cannot carry a meaningful
    scope floor, so this service states the scope **per route**. That is easy to
    forget, and forgetting it is silent — which is why it is swept rather than
    reviewed.
    """
    app = create_app()
    problems = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        guards = _guards(route)
        if path in UNSCOPED_ROUTES:
            if guards:
                problems.append(f"{path} is on the unscoped list but is guarded")
            continue
        if len(guards) != 1:
            problems.append(f"{sorted(route.methods)} {path} has {len(guards)} guards")
            continue
        (perms,) = guards
        reads = route.methods == {"GET"}
        want = ("provenance.read",) if reads else ("provenance.write",)
        if perms != want:
            problems.append(
                f"{sorted(route.methods)} {path} requires {perms}, expected {want}"
            )
    assert not problems, "\n".join(problems)
