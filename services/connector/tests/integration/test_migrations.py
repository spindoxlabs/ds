"""The migrations build the schema the models describe.

This is the check `db/engine.py`'s startup guard cannot make. That guard compares
the recorded **revision stamp** against `head` and refuses to serve a stale
database — necessary, and blind to the case where the stamp is current and the
shape is wrong. Only running the migrations and comparing the result to the
models can see that, and nothing did.

The failure it catches is ordinary and undramatic: someone adds a column to a
model, the unit suite's `create_all` picks it up from the model, all 319 tests
stay green, and the revision is never written. It is found in a deployment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

import connector.db.models  # noqa: F401 — registers every model on Base.metadata
from connector.db.engine import Base

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]

#: Differences that mean the migrations and the models disagree about the
#: schema. Restricted deliberately: alembic also reports type and default
#: variations that are reflection artefacts rather than drift (Postgres hands
#: back `VARCHAR` for `String`, server defaults come back as text), and a check
#: that cries wolf on those is one people learn to skip. These four are
#: unambiguous — a table or column exists on one side and not the other.
STRUCTURAL = ("add_table", "remove_table", "add_column", "remove_column")


def _alembic_upgrade(
    database_url: str, revision: str = "head"
) -> subprocess.CompletedProcess:
    """Run the real `alembic upgrade`, the way a deployment does.

    A subprocess rather than alembic's Python API on purpose: `alembic/env.py`
    reads the URL from `get_settings()`, so this also proves the migrations pick
    up `CONNECTOR_DATABASE_URL` — the path `task db:migrate` and the compose
    init container both take.

    `revision` is `head` for every schema check here. It is a parameter so a
    **data** migration can be tested the only way one can be: stop at its parent,
    write the rows it is about, then upgrade over them.
    """
    env = {**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=UNIT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


async def test_migrations_apply_to_an_empty_database(empty_database: str) -> None:
    """Every revision runs, in order, against a real Postgres.

    Eight revisions that no test has ever executed. This is the cheapest thing
    this layer buys: a revision with a syntax error, a bad dependency or a
    Postgres-only mistake stops being something a deployment discovers.
    """
    result = _alembic_upgrade(empty_database)
    assert result.returncode == 0, (
        f"`alembic upgrade head` failed against a clean database.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


async def test_the_migrated_schema_matches_the_models(empty_database: str) -> None:
    """The whole point of the layer: migrations and models must agree.

    Fails on a model changed without a revision, and on a revision that builds
    something the models do not describe. The message names the differences
    rather than asserting a bare `== []`, because the remedy depends on which
    direction the drift runs.
    """
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
        + "\n\nA model changed without a revision, or a revision built something no "
        "model describes. Generate one with:\n"
        "  task -d services/connector db:revision MESSAGE=describe_the_change"
    )


#: Columns the migrations left nullable while the model declares them NOT NULL.
#:
#: Found by this file on its first run, and **left as a ratchet rather than a
#: gate** — the same call `CI-01` made for lint. Fixing them means an
#: `ALTER COLUMN … SET NOT NULL` against every deployed database, which is a
#: schema change with its own blast radius and not something a test should smuggle
#: in. Recording them means a *fifth* one fails here on the day it is introduced.
#:
#: The risk is small but it is not zero, and it is worth stating precisely: all
#: four carry a server default, so nothing writes NULL by accident today. What
#: the disagreement costs is the type: `Mapped[datetime]` promises a value the
#: database does not guarantee, so a row written by anything other than this ORM
#: — a migration, a fixture, `psql` — can hand the application a `None` it has no
#: branch for.
KNOWN_NULLABLE_DRIFT = {
    ("consent_requests", "requested_at"),
    ("consumer_access_requests", "created_at"),
    ("consumer_access_requests", "updated_at"),
    ("consumer_transfers", "created_at"),
}


async def test_no_new_nullability_drift(empty_database: str) -> None:
    """The models and the schema agree about what may be NULL — a ratchet.

    Separate from the structural test because the remedy is different: a missing
    column is a forgotten revision, while a nullability difference is usually a
    model tightened after the table was created, which needs a deliberate
    `ALTER` and a decision about existing rows.
    """
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

    # compare_metadata wraps column alterations in a list of one-or-more tuples.
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
        + "\n\nThe model declares NOT NULL and the migration did not. Add an "
        "`ALTER COLUMN … SET NOT NULL` revision, or relax the model."
    )
    # Also fails when one is *fixed* without being removed from the set, so the
    # ratchet cannot quietly stop ratcheting.
    assert not (KNOWN_NULLABLE_DRIFT - found), (
        "these no longer drift — delete them from KNOWN_NULLABLE_DRIFT:\n"
        + "\n".join(f"  - {t}.{c}" for t, c in sorted(KNOWN_NULLABLE_DRIFT - found))
    )


def test_there_is_exactly_one_migration_head() -> None:
    """Two heads make `upgrade head` fail — after the merge, never before it.

    The way this arrives is two branches each adding a revision on the same
    parent. Both suites pass, both migrations are correct, and the *pair* is
    broken. It needs no database, so it is the one check here that still runs
    when Postgres is not up.
    """
    script = ScriptDirectory.from_config(Config(str(UNIT_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"{len(heads)} migration heads: {heads}. `alembic upgrade head` cannot "
        "choose between them. Merge with: alembic merge -m 'merge heads' "
        + " ".join(heads)
    )


# ── 0009, the one data migration ─────────────────────────────────────────────


async def test_0009_rekeys_a_members_offer_decision_and_leaves_asks_alone(
    empty_database: str,
) -> None:
    """The rows written before `/consent/my/shares` learned the wildcard.

    A data migration is testable only over data, and this one carries a
    fail-open if it selects too little: a member who granted before it and
    withdraws after writes a wildcard revocation, which `resolve_decision` lets
    an older *specific* grant outrank (D-15). The withdrawal would be ignored for
    exactly the party the deployment negotiates with.

    Selecting too much is the mirror defect, so both are asserted here. A row
    from `POST /consent/request` is a genuine per-party ask; widening one to the
    wildcard would answer for parties the subject never decided about.
    """
    assert _alembic_upgrade(empty_database, "0008").returncode == 0

    engine = create_async_engine(empty_database)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO consent_requests "
                    "(id, subject_id, consumer_id, dataset_id, offer_id, message, "
                    " status, notification_sent) VALUES "
                    "('r1', 'did:web:x:users:a', 'did:web:counterparty', "
                    "  'datasets.silver.meters', 'flexibility', "
                    "  'Data owner enabled sharing.', 'granted', false),"
                    "('r2', 'did:web:x:users:a', 'did:web:counterparty', "
                    "  'datasets.silver.meters', 'grid-planning', "
                    "  'Data owner disabled sharing.', 'revoked', false),"
                    "('r3', 'did:web:x:users:a', 'did:web:counterparty', "
                    "  'datasets.silver.meters', 'flexibility', "
                    "  'Please share for the pilot', 'pending', false),"
                    "('r4', 'did:web:x:users:a', 'did:web:counterparty', "
                    "  'datasets.silver.meters', NULL, "
                    "  'Data owner enabled sharing.', 'granted', false)"
                )
            )

        assert _alembic_upgrade(empty_database).returncode == 0

        async with engine.connect() as conn:
            keys = dict(
                (
                    await conn.execute(
                        sa.text("SELECT id, consumer_id FROM consent_requests")
                    )
                ).all()
            )
    finally:
        await engine.dispose()

    assert keys["r1"] == "*", "a member's standing grant was left off the key"
    assert keys["r2"] == "*", "a member's withdrawal was left off the key"
    # A consumer's own ask, and a decision about a bare dataset: neither is an
    # offer-scoped standing decision, and neither may be widened into one.
    assert keys["r3"] == "did:web:counterparty"
    assert keys["r4"] == "did:web:counterparty"
