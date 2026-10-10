"""`ir-cli owner import` never moves a suspended or revoked owner.

The anchor's bootstrap runs `owner import` on every start, and a seed declares
`status: verified` with its evidence. The import wrote that status over an owner
an operator had since suspended (`org suspend`) or revoked (`org revoke`), so the
next restart undid it: `verified` again, with its participant still inactive and
its credentials still suspended. A suspension is lifted by `org reinstate`;
revocation is terminal. The import still updates the owner's other fields and
says why the status was left alone.
"""

from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli

runner = CliRunner()

SEED = """
owners:
  - id: example-rec
    name: Example REC (renamed)
    did: did:web:rec.example.org
    status: verified
    verified_by: seed
    evidence_ref: owners.yaml
"""


@pytest.fixture
def cli_database(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from identity_registry.config import get_settings
    from identity_registry.db.engine import Base

    url = f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}"

    async def _create():
        eng = create_async_engine(url, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_create())
    monkeypatch.setenv("IDENTITY_REGISTRY_DATABASE_URL", url)
    monkeypatch.setenv("DB_SKIP_SCHEMA_CHECK", "true")
    get_settings.cache_clear()
    return url


def _sql(url: str, statement: str):
    import sqlite3

    with sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///")) as conn:
        return conn.execute(statement).fetchall()


@pytest.mark.parametrize("status", ["suspended", "revoked"])
def test_a_re_import_leaves_a_suspended_or_revoked_owner_as_it_is(
    cli_database, tmp_path, status
):
    seed = tmp_path / "owners.yaml"
    seed.write_text(SEED)
    assert runner.invoke(cli, ["owner", "import", "--file", str(seed)]).exit_code == 0
    _sql(
        cli_database, f"UPDATE owners SET status = '{status}' WHERE id = 'example-rec'"
    )

    again = runner.invoke(cli, ["owner", "import", "--file", str(seed)])

    assert again.exit_code == 0, again.output
    assert status in again.output and "example-rec" in again.output
    assert _sql(cli_database, "SELECT status, name FROM owners") == [
        (status, "Example REC (renamed)")
    ]


def test_a_re_import_still_writes_a_verified_owners_claim(cli_database, tmp_path):
    seed = tmp_path / "owners.yaml"
    seed.write_text(SEED)
    runner.invoke(cli, ["owner", "import", "--file", str(seed)])
    _sql(cli_database, "UPDATE owners SET status = 'pending', verified_by = NULL")
    assert runner.invoke(cli, ["owner", "import", "--file", str(seed)]).exit_code == 0
    assert _sql(cli_database, "SELECT status, verified_by FROM owners") == [
        ("verified", "seed")
    ]
