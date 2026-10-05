"""`ir-cli membership` resolves `--organization` as the admin API does.

Rows are stored under the owner id (`canonical_organisation`), so a command
matching the name literally answered "Membership not found" for an alias of the
very organisation the row belongs to — the operator's clean-up of a suspended
organisation (ADR-0026, amended 2026-10-05) then depended on knowing which of
its names was the stored one.
"""

from __future__ import annotations

import sqlite3

import pytest
from test_collector_client import MEMBER, REC  # noqa: F401
from test_suspended_organisation_cleanup import cli_database  # noqa: F401
from typer.testing import CliRunner

ALIAS = "ex-rec"


@pytest.fixture(autouse=True)
def _dev(monkeypatch):
    """ir-cli refuses its dev defaults outside DS_ENV=dev; not this test's subject."""
    monkeypatch.setenv("DS_ENV", "dev")


def _seed(url: str, *, member_row: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///"))
    conn.execute(
        f"INSERT INTO dids (did, did_type, active) VALUES ('{MEMBER}', 'user', 1)"
    )
    conn.execute(
        "INSERT INTO owners (id, type, name, did, aliases, status, verified_by) "
        f"VALUES ('{REC['id']}', 'schema:Organization', 'x', '{REC['did']}', "
        f"'[\"{ALIAS}\"]', 'suspended', 'test')"
    )
    if member_row:
        # As `POST /admin/memberships` writes it: under the owner id.
        conn.execute(
            "INSERT INTO organization_memberships "
            "(user_did, organization_alias, status) "
            f"VALUES ('{MEMBER}', '{REC['id']}', 'active')"
        )
    conn.commit()
    return conn


def _rows(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT user_did, organization_alias FROM organization_memberships"
    ).fetchall()


def test_an_alias_removes_a_suspended_organisations_membership(cli_database):  # noqa: F811
    from identity_registry.cli.main import app as cli

    conn = _seed(cli_database, member_row=True)
    runner = CliRunner()

    listed = runner.invoke(cli, ["membership", "list", "--organization", ALIAS])
    assert listed.exit_code == 0, listed.output
    assert MEMBER in listed.output

    removed = runner.invoke(
        cli, ["membership", "remove", "--user-did", MEMBER, "--organization", ALIAS]
    )
    assert removed.exit_code == 0, removed.output
    assert "Membership removed" in removed.output
    assert _rows(conn) == []


def test_an_alias_adds_under_the_owner_id(cli_database):  # noqa: F811
    """One row whatever the name, so the admin API and the check find it."""
    from identity_registry.cli.main import app as cli

    conn = _seed(cli_database, member_row=False)
    runner = CliRunner()
    for name in (ALIAS, REC["id"]):
        r = runner.invoke(
            cli, ["membership", "add", "--user-did", MEMBER, "--organization", name]
        )
        assert r.exit_code == 0, r.output
    assert _rows(conn) == [(MEMBER, REC["id"])]


def test_an_unknown_name_is_kept_verbatim(cli_database):  # noqa: F811
    from identity_registry.cli.main import app as cli

    conn = _seed(cli_database, member_row=False)
    r = CliRunner().invoke(
        cli,
        ["membership", "add", "--user-did", MEMBER, "--organization", "no-such-org"],
    )
    assert r.exit_code == 0, r.output
    assert _rows(conn) == [(MEMBER, "no-such-org")]
