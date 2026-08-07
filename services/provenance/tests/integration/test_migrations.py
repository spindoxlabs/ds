"""The migrations build the schema the models describe.

The check `db/engine.py`'s startup guard cannot make: it compares the recorded
revision **stamp** against head, so a database that is at head and shaped wrong
passes it. Only running the migrations against a real Postgres and comparing the
result to the models can see that, and until now nothing did.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

import provenance.db.models  # noqa: F401 — registers every model on Base.metadata
from provenance.db.engine import Base

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]

#: See the connector's copy for why this is restricted to the unambiguous four:
#: alembic also reports reflection artefacts, and a check that cries wolf is one
#: people learn to skip.
STRUCTURAL = ("add_table", "remove_table", "add_column", "remove_column")


def _alembic_upgrade(database_url: str) -> subprocess.CompletedProcess:
    """Run the real `alembic upgrade head`, the way a deployment does."""
    env = {**os.environ, "PROVENANCE_DATABASE_URL": database_url, "DS_ENV": "dev"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=UNIT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


async def test_migrations_apply_to_an_empty_database(empty_database: str) -> None:
    """Every revision runs, in order, against a real Postgres."""
    result = _alembic_upgrade(empty_database)
    assert result.returncode == 0, (
        f"`alembic upgrade head` failed against a clean database.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


async def test_the_migrated_schema_matches_the_models(empty_database: str) -> None:
    """Fails on a model changed without a revision, and on the reverse."""
    assert _alembic_upgrade(empty_database).returncode == 0

    engine = create_async_engine(empty_database)
    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(sync_conn), Base.metadata
                )
            )
    finally:
        await engine.dispose()

    structural = [d for d in diffs if isinstance(d, tuple) and d and d[0] in STRUCTURAL]
    assert not structural, (
        "the migrated schema does not match the models:\n"
        + "\n".join(f"  - {d}" for d in structural)
        + "\n\nGenerate a revision with:\n"
        "  task -d services/provenance db:revision MESSAGE=describe_the_change"
    )


#: Columns the migrations left nullable while the model declares them NOT NULL.
#: A ratchet, not a gate — see the connector's copy for the reasoning. Fixing one
#: means an `ALTER COLUMN … SET NOT NULL` against every deployed database, which
#: is a schema change with its own blast radius and not something a test should
#: smuggle in. Recording them makes the *next* one fail here.
KNOWN_NULLABLE_DRIFT = {
    ("access_log", "logged_at"),
    ("domain_events", "received_at"),
    ("prov_nodes", "created_at"),
    ("prov_nodes", "updated_at"),
    ("prov_relations", "created_at"),
}


async def test_no_new_nullability_drift(empty_database: str) -> None:
    """The models and the schema agree about what may be NULL — a ratchet."""
    assert _alembic_upgrade(empty_database).returncode == 0

    engine = create_async_engine(empty_database)
    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(sync_conn), Base.metadata
                )
            )
    finally:
        await engine.dispose()

    flat = [
        d for group in diffs for d in (group if isinstance(group, list) else [group])
    ]
    found = {
        (d[2], d[3])
        for d in flat
        if isinstance(d, tuple) and d and d[0] == "modify_nullable"
    }

    assert not (found - KNOWN_NULLABLE_DRIFT), (
        "new nullability drift between the models and the migrations:\n"
        + "\n".join(f"  - {t}.{c}" for t, c in sorted(found - KNOWN_NULLABLE_DRIFT))
    )
    assert not (KNOWN_NULLABLE_DRIFT - found), (
        "these no longer drift — delete them from KNOWN_NULLABLE_DRIFT:\n"
        + "\n".join(f"  - {t}.{c}" for t, c in sorted(KNOWN_NULLABLE_DRIFT - found))
    )


def test_there_is_exactly_one_migration_head() -> None:
    """Two heads make `upgrade head` fail — after the merge, never before it."""
    script = ScriptDirectory.from_config(Config(str(UNIT_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"{len(heads)} migration heads: {heads}. `alembic upgrade head` cannot "
        "choose between them. Merge with: alembic merge -m 'merge heads' "
        + " ".join(heads)
    )
