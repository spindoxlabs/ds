"""Integration harness — the connector against a real PostgreSQL.

## What this layer exists to prove, and why the unit suite cannot

The unit suite builds its schema with `Base.metadata.create_all` on
**SQLite in memory** (`tests/conftest.py`). Two things follow, and both are
invisible to all 319 of its tests:

* **The migrations never run.** There are eight of them. A model changed without
  a matching revision passes every unit test, because `create_all` builds the
  schema from the models the test just imported — the migrations are not
  consulted. It surfaces at deployment, as a service that starts against a
  database missing a column.
* **PostgreSQL is never exercised.** SQLite accepts things Postgres rejects and
  ignores much of what Postgres enforces. A column type, server default or
  constraint that only works on SQLite is a green suite and a broken deployment.

`db/engine.py` checks at startup that the database is at the head revision, so a
deployment does refuse to serve a stale schema — but that check compares the
*stamp*, not the shape. Migrations that are at head and disagree with the models
pass it.

## Requires Postgres, and says so

`task -d services/connector test:integration` runs this; plain `test` never
collects it (`norecursedirs` in `pyproject.toml`), so the unit suite stays fast
and dependency-free.

Each run gets its **own** database, created and dropped here. It deliberately
does not touch `connector` — the developer's dev database — because a test that
migrates or drops the database you are working in is the `E2E-17` shape, and that
one cost four sessions.
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest_asyncio

#: Admin connection, used only to CREATE/DROP the throwaway database.
#:
#: `172.17.0.1` rather than `localhost`, per the root guide's host-binding rule:
#: it resolves identically from the host and from a container, so this suite runs
#: unchanged in either.
ADMIN_DSN = os.environ.get(
    "CONNECTOR_TEST_PG", "postgresql://postgres:postgres@172.17.0.1:35432/postgres"
)


def _database_url(name: str) -> str:
    """The SQLAlchemy URL for a database on the same server as `ADMIN_DSN`."""
    base, _, _ = ADMIN_DSN.rpartition("/")
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://')}/{name}"


@pytest_asyncio.fixture
async def empty_database() -> str:
    """A freshly created, completely empty database. Dropped afterwards.

    Named with a uuid rather than the pid: two runs on one machine (a rerun
    while the first is still tearing down, or xdist) would otherwise collide and
    the second would silently inherit the first's schema — a fixture that makes
    a *migration* test pass for the wrong reason.
    """
    name = f"connector_it_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    try:
        yield _database_url(name)
    finally:
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            # WITH (FORCE): asyncpg pools in the test may not have finished
            # closing, and a DROP that fails leaves a database behind on every
            # run until the server fills up.
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
