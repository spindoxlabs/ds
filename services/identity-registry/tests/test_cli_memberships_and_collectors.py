"""`ir-cli membership list` and `ir-cli collector …` against a real schema.

`membership list` printed `m.role`, a column migration 0017 dropped, so it
raised instead of listing anybody. The collector commands are the dev
bootstrap's and an operator's path to the relation the connector reads.
"""

from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli

runner = CliRunner()

HOLDER = "did:web:dso.example.org"
COLLECTOR = "did:web:rec.example.org"
MEMBER = "did:web:rec.example.org:users:member-001"


@pytest.fixture(autouse=True)
def cli_database(tmp_path, monkeypatch):
    """A schema-backed SQLite file of this test's own (never a live database)."""
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


def _sql(url: str, *statements: str) -> None:
    import sqlite3

    with sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///")) as conn:
        for statement in statements:
            conn.execute(statement)


def test_membership_list_prints_members_without_the_dropped_role(cli_database):
    _sql(
        cli_database,
        f"INSERT INTO dids (did, did_type, active) VALUES ('{MEMBER}', 'user', 1)",
    )
    added = runner.invoke(
        cli,
        ["membership", "add", "--user-did", MEMBER, "--organization", "example-rec"],
    )
    assert added.exit_code == 0, added.output

    listed = runner.invoke(cli, ["membership", "list", "--organization", "example-rec"])
    assert listed.exit_code == 0, listed.output
    assert MEMBER in listed.output
    assert "status=active" in listed.output
    assert "role=" not in listed.output


def test_membership_list_says_so_when_empty(cli_database):
    listed = runner.invoke(cli, ["membership", "list", "--organization", "nobody"])
    assert listed.exit_code == 0, listed.output
    assert "No members in nobody." in listed.output


def test_collector_add_list_revoke(cli_database):
    _sql(
        cli_database,
        f"INSERT INTO participants (did, roles, allowed_scopes, active) "
        f"VALUES ('{HOLDER}', '[\"provider\"]', '[]', 1)",
        "INSERT INTO owners (id, type, name, did, aliases, status, verified_by) "
        f"VALUES ('example-rec', 'schema:Organization', 'x', '{COLLECTOR}', '[]', "
        "'verified', 'test')",
    )
    args = ["--holder-did", HOLDER, "--collector-did", COLLECTOR]
    added = runner.invoke(cli, ["collector", "add", *args])
    assert added.exit_code == 0, added.output
    assert "active" in added.output

    listed = runner.invoke(cli, ["collector", "list"])
    assert f"{COLLECTOR} → {HOLDER}  active" in listed.output

    revoked = runner.invoke(cli, ["collector", "revoke", *args, "--reason", "ended"])
    assert revoked.exit_code == 0, revoked.output
    listed = runner.invoke(cli, ["collector", "list", "--holder-did", HOLDER])
    assert f"{COLLECTOR} → {HOLDER}  revoked" in listed.output


def test_collector_add_refuses_an_unknown_holder(cli_database):
    refused = runner.invoke(
        cli, ["collector", "add", "--holder-did", HOLDER, "--collector-did", COLLECTOR]
    )
    assert refused.exit_code == 1
    assert "not an active participant" in refused.output
