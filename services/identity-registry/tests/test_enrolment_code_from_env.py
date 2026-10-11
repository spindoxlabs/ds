"""`ir-cli org enrolment-token --code-env`: a code the deployment supplies.

A co-hosted participant is enrolled through the charts (docs/deployment/operations.md,
"Enrolment"): the deployment generates one code per participant into its secrets
file, the anchor's hook registers it here, and the participant's own registry spends
it. The hook runs on every install and upgrade, so registering is idempotent, and it
never re-opens an organisation that has already enrolled: a code that was spent, or an
owner enrolled by any other code, registers nothing.

The code never reaches argv or stdout: it is read from the named environment
variable, and only its hash is stored, as for a generated one.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli
from identity_registry.services.enrolment import hash_code

runner = CliRunner()

CODE = "a-deployment-generated-enrolment-code-of-48-chars-x"


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
    monkeypatch.setenv("ENROLMENT_CODE_EXAMPLE_REC", CODE)
    get_settings.cache_clear()
    return url


def _db(url: str):
    import sqlite3

    return sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///"))


def _owner(url: str, alias: str = "example-rec", status: str = "verified") -> None:
    with _db(url) as conn:
        conn.execute(
            "INSERT INTO owners (id, type, name, aliases, status, collects_consent, "
            "verified_by, verified_at) VALUES (?, 'schema:Organization', 'Example', "
            "'[]', ?, 0, ?, ?)",
            (
                alias,
                status,
                "ops@example.test" if status == "verified" else None,
                datetime.now(UTC).isoformat() if status == "verified" else None,
            ),
        )


def _tokens(url: str) -> list[tuple]:
    with _db(url) as conn:
        return conn.execute(
            "SELECT code_hash, owner_alias, redeemed_at, roles, allowed_scopes, "
            "expires_at FROM enrolment_tokens ORDER BY created_at"
        ).fetchall()


def _register(*extra: str):
    return runner.invoke(
        cli,
        [
            "org",
            "enrolment-token",
            "--alias",
            "example-rec",
            "--roles",
            "provider,consumer",
            "--scope",
            "dataspaces.query",
            "--code-env",
            "ENROLMENT_CODE_EXAMPLE_REC",
            *extra,
        ],
    )


def test_the_supplied_code_is_registered_by_its_hash_and_never_printed(cli_database):
    _owner(cli_database)
    result = _register()
    assert result.exit_code == 0, result.output
    assert CODE not in result.output
    rows = _tokens(cli_database)
    assert len(rows) == 1
    code_hash, alias, redeemed, roles, scopes, _ = rows[0]
    assert (code_hash, alias, redeemed) == (hash_code(CODE), "example-rec", None)
    assert "provider" in roles and "consumer" in roles
    assert "dataspaces.query" in scopes


def test_registering_twice_is_a_no_op(cli_database):
    _owner(cli_database)
    assert _register().exit_code == 0
    again = _register()
    assert again.exit_code == 0, again.output
    assert "already registered" in again.output
    assert len(_tokens(cli_database)) == 1


def test_a_spent_code_is_not_registered_again(cli_database):
    _owner(cli_database)
    assert _register().exit_code == 0
    with _db(cli_database) as conn:
        conn.execute(
            "UPDATE enrolment_tokens SET redeemed_at = CURRENT_TIMESTAMP, "
            "redeemed_did = 'did:web:example-rec.ds.test'"
        )
    again = _register()
    assert again.exit_code == 0, again.output
    assert "already enrolled" in again.output
    rows = _tokens(cli_database)
    assert len(rows) == 1 and rows[0][2] is not None


def test_an_owner_enrolled_by_another_code_gets_none(cli_database):
    _owner(cli_database)
    with _db(cli_database) as conn:
        conn.execute(
            "INSERT INTO enrolment_tokens (id, code_hash, owner_alias, redeemed_at, "
            "redeemed_did, created_at) VALUES ('t1', ?, 'example-rec', "
            "CURRENT_TIMESTAMP, 'did:web:example-rec.ds.test', CURRENT_TIMESTAMP)",
            (hash_code("an-operator-issued-code"),),
        )
    result = _register()
    assert result.exit_code == 0, result.output
    assert "already enrolled" in result.output
    assert len(_tokens(cli_database)) == 1


def test_an_expired_unspent_code_is_rearmed(cli_database):
    _owner(cli_database)
    assert _register().exit_code == 0
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with _db(cli_database) as conn:
        conn.execute("UPDATE enrolment_tokens SET expires_at = ?", (past,))
    again = _register()
    assert again.exit_code == 0, again.output
    rows = _tokens(cli_database)
    assert len(rows) == 1
    assert rows[0][5] > past


def test_a_missing_or_short_code_is_refused(cli_database, monkeypatch):
    _owner(cli_database)
    monkeypatch.delenv("ENROLMENT_CODE_EXAMPLE_REC")
    missing = _register()
    assert missing.exit_code != 0
    assert "ENROLMENT_CODE_EXAMPLE_REC" in missing.output
    monkeypatch.setenv("ENROLMENT_CODE_EXAMPLE_REC", "short")
    short = _register()
    assert short.exit_code != 0
    assert "at least 32" in short.output
    assert _tokens(cli_database) == []


def test_an_unverified_owner_gets_no_code(cli_database):
    _owner(cli_database, status="pending")
    result = _register()
    assert result.exit_code == 1
    assert _tokens(cli_database) == []


def test_without_code_env_a_code_is_generated_and_printed_as_before(cli_database):
    _owner(cli_database)
    result = runner.invoke(
        cli, ["org", "enrolment-token", "--alias", "example-rec", "--roles", "provider"]
    )
    assert result.exit_code == 0, result.output
    rows = _tokens(cli_database)
    assert len(rows) == 1
    printed = result.stdout.strip().splitlines()[0]
    assert hash_code(printed) == rows[0][0]
