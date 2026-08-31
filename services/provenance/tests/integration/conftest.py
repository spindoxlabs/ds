"""Integration harness — provenance against a real PostgreSQL.

Same gap as `services/connector`, same shape, and worth stating once per service
because the evidence is per service: the unit suite builds its schema with
`Base.metadata.create_all` on **SQLite in memory** (`tests/conftest.py`), so the
three migrations run in no test and no model is ever exercised against Postgres.

`db/engine.py` refuses to serve a database that is not stamped at head, which
catches a *stale* schema and not a *wrong* one — migrations at head that
disagree with the models pass it.

Each run gets its own database, created and dropped here; never `provenance`,
the developer's own. See `services/connector/tests/integration/conftest.py` for
the longer version of the argument.

**This is the second copy of this harness.** It is small and per-service by the
precedent `services/identity-registry` set, but a third one should be extracted
rather than pasted — the drift risk in a duplicated fixture is exactly what
`GOV-01` records.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest_asyncio

ADMIN_DSN = os.environ.get(
    "PROVENANCE_TEST_PG", "postgresql://postgres:postgres@172.17.0.1:35432/postgres"
)


def _database_url(name: str) -> str:
    base, _, _ = ADMIN_DSN.rpartition("/")
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://')}/{name}"


@pytest_asyncio.fixture
async def empty_database() -> str:
    """A freshly created, completely empty database. Dropped afterwards."""
    name = f"provenance_it_{uuid.uuid4().hex[:12]}"
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
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
