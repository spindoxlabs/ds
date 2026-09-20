"""An EDC database created by an older EDC comes out with the pinned EDC's schema.

`edc.sql.schema.autocreate` runs `CREATE TABLE IF NOT EXISTS`, so on its own it never
adds a column to a table that already exists. EDC 0.17.0 and 0.18.0 added three, and
the stores read and write all three unconditionally: on a database created by 0.16.0,
every contract agreement fails to store. `test_autocreate_alone_leaves_the_old_shape`
measures that gap, and the rest prove that ds's migrations close it: from each older
schema, on a fresh database, in either queue order, and on every later boot.

"The pinned schema" is the reference throughout, and it is never written down here: it
is whatever the pinned version's own schema files create on an empty database.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import psycopg
import pytest
from conftest import MIGRATIONS, SCHEMA_FIXTURES, pinned_edc_version, throwaway_database

pytestmark = pytest.mark.integration

PINNED = f"v{pinned_edc_version()}"

#: Every schema an existing database may have been created with. Each is a directory of
#: upstream files, so adding one is a copy from the EDC sources and nothing else.
OLDER = sorted(
    (p.name for p in SCHEMA_FIXTURES.iterdir() if p.is_dir() and p.name != PINNED),
    key=lambda v: tuple(int(n) for n in v.lstrip("v").split(".")),
)

Shape = dict[str, object]
Connect = Callable[[], psycopg.Connection]


def _store_schema(version: str) -> list[str]:
    directory = SCHEMA_FIXTURES / version
    assert directory.is_dir(), (
        f"no schema fixtures for {version}: EDC was bumped. Copy the packaged stores' "
        f"*-schema.sql for the new tag into {directory}, read the diff against the old "
        "one, and add a migration under ds-edc-schema/ for every column it adds."
    )
    return [p.read_text() for p in sorted(directory.glob("*.sql"))]


def _migrations() -> list[str]:
    files: list[Path] = sorted(MIGRATIONS.glob("*/V*.sql"), key=lambda p: p.name)
    assert files, f"no migrations under {MIGRATIONS}"
    return [p.read_text() for p in files]


def boot(
    connect: Connect,
    version: str,
    *,
    migrations: bool = True,
    migrations_first: bool = False,
) -> None:
    """What an EDC at `version` does to its database at start, with autocreate on.

    Every queued file for the datasource, joined with "", as one execute, in one
    transaction: `SqlDmlStatementRunner.executeSql` at 0.18.0.
    """
    queued = _store_schema(version)
    if migrations:
        queued = _migrations() + queued if migrations_first else queued + _migrations()
    with connect() as conn:
        conn.execute("".join(queued))


def shape(connect: Connect) -> Shape:
    """Every table, column, index and constraint of the `edc_*` tables, by name.

    Column order is left out on purpose: the stores address columns by name, and an
    added column lands at the end of the table whatever the fresh DDL says.
    """
    with connect() as conn:
        columns = conn.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable,
                   coalesce(column_default, '')
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name LIKE 'edc\\_%'
            """
        ).fetchall()
        indexes = conn.execute(
            """
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND tablename LIKE 'edc\\_%'
            """
        ).fetchall()
        constraints = conn.execute(
            """
            SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'public' AND c.conrelid::regclass::text LIKE 'edc\\_%'
            """
        ).fetchall()
    return {
        "columns": {(t, c): rest for t, c, *rest in columns},
        "indexes": {(t, i): d for t, i, d in indexes},
        "constraints": {(t, c): d for t, c, d in constraints},
    }


def missing_columns(actual: Shape, reference: Shape) -> dict[tuple[str, str], object]:
    ref, act = reference["columns"], actual["columns"]
    assert isinstance(ref, dict) and isinstance(act, dict)
    return {k: v for k, v in ref.items() if k not in act}


@pytest.fixture(scope="module")
def pinned_shape() -> Shape:
    """The reference: the pinned version's own schema files on an empty database."""
    with throwaway_database("edc_schema_ref") as connect:
        boot(connect, PINNED, migrations=False)
        return shape(connect)


def test_there_is_an_older_schema_to_upgrade_from() -> None:
    assert OLDER, f"only {PINNED} is under {SCHEMA_FIXTURES}; nothing is tested"


@pytest.mark.parametrize("old", OLDER)
def test_autocreate_alone_leaves_the_old_shape(
    database: Connect, pinned_shape: Shape, old: str
) -> None:
    """The defect, measured: the pinned store files on an older database add nothing.

    This is also what shows the other tests can fail. Without the migrations the
    upgraded database is the old one, and it lacks exactly these columns.
    """
    boot(database, old, migrations=False)
    boot(database, PINNED, migrations=False)

    # Measured with `git diff <old> <pinned> -- '*.sql'` over the packaged stores.
    # A bump or a new fixture directory changes these, deliberately: read the diff.
    expected = {
        ("v0.16.0", "v0.18.0"): {
            ("edc_contract_agreement", "claims"),
            ("edc_transfer_process", "claims"),
            ("edc_transfer_process", "data_address_owner"),
        },
        ("v0.17.0", "v0.18.0"): {("edc_transfer_process", "data_address_owner")},
    }
    assert (old, PINNED) in expected, f"no measured gap for {old} -> {PINNED}"
    assert (
        set(missing_columns(shape(database), pinned_shape)) == expected[(old, PINNED)]
    )


@pytest.mark.parametrize("migrations_first", [False, True], ids=["after", "before"])
@pytest.mark.parametrize("old", OLDER)
def test_an_older_database_is_upgraded_to_the_pinned_schema(
    database: Connect, pinned_shape: Shape, old: str, migrations_first: bool
) -> None:
    boot(database, old, migrations=False)

    boot(database, PINNED, migrations_first=migrations_first)

    assert shape(database) == pinned_shape


@pytest.mark.parametrize("old", OLDER)
def test_booting_again_changes_nothing(
    database: Connect, pinned_shape: Shape, old: str
) -> None:
    boot(database, old, migrations=False)
    boot(database, PINNED)
    once = shape(database)

    boot(database, PINNED)
    boot(database, PINNED, migrations_first=True)

    assert shape(database) == once == pinned_shape


@pytest.mark.parametrize("migrations_first", [False, True], ids=["after", "before"])
def test_a_fresh_database_gets_exactly_the_pinned_schema(
    database: Connect, pinned_shape: Shape, migrations_first: bool
) -> None:
    """Queued before the store `CREATE`, a migration skips the absent table."""
    boot(database, PINNED, migrations_first=migrations_first)

    assert shape(database) == pinned_shape


@pytest.mark.parametrize("old", OLDER)
def test_existing_rows_survive_and_read_the_upstream_defaults(
    database: Connect, old: str
) -> None:
    """A deployment upgrades a database with agreements and transfers in it."""
    boot(database, old, migrations=False)
    with database() as conn:
        for table in ("edc_contract_agreement", "edc_transfer_process"):
            _insert_minimal_row(conn, table)

    boot(database, PINNED)

    with database() as conn:
        agreements = conn.execute(
            "SELECT claims FROM edc_contract_agreement"
        ).fetchall()
        transfers = conn.execute(
            "SELECT claims, data_address_owner FROM edc_transfer_process"
        ).fetchall()
    assert agreements == [(None,)]
    assert transfers == [(None, False)]


def _insert_minimal_row(conn: psycopg.Connection, table: str) -> None:
    """One row with every NOT NULL column without a default filled, and nothing else."""
    required = conn.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
          AND is_nullable = 'NO' AND column_default IS NULL
        """,
        (table,),
    ).fetchall()
    samples = {"bigint": 1, "integer": 1, "boolean": False, "json": "{}"}
    names = [c for c, _ in required]
    values = [samples.get(t, f"it-{c}") for c, t in required]
    columns = ", ".join(names)
    placeholders = ", ".join(["%s"] * len(names))
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
