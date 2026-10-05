"""A suspended organisation's memberships are cleaned up by the operator.

ADR-0026, amended 2026-10-05. A suspended organisation acts nowhere: its own
tokens may not delete its memberships either (`test_collector_client`). Its rows
stay, uncounted by `/memberships/check`, for reinstatement — and when the
organisation is not coming back, removing them is an **operator duty**. These
are the two operator paths, each against a suspended organisation:

* the admin API, `DELETE /admin/memberships/{did}/{org}` with
  `identity-registry.admin` (a service token or a platform administrator's
  login), which takes the owner id or any of its aliases;
* `ir-cli membership remove`, which writes the database directly and resolves
  the organisation to its owner id the same way (`test_membership_cli_alias`).
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import make_headers
from test_collector_client import (  # noqa: F401
    MEMBER,
    REC,
    _add,
    _is_member,
    _suspend,
    seeded,
)
from test_membership_scope import person
from typer.testing import CliRunner

ADMIN = make_headers("identity-registry.admin")


@pytest.mark.parametrize("named_as", ["example-rec", "ex-rec"])
async def test_the_admin_api_removes_a_suspended_organisations_membership(
    seeded,  # noqa: F811
    named_as,
):
    r = await _add(seeded, ADMIN)
    assert r.status_code == 201, r.text
    await _suspend(seeded, "example-rec")

    r = await seeded.delete(f"/admin/memberships/{MEMBER}/{named_as}", headers=ADMIN)
    assert r.status_code == 204, r.text
    # Gone, not only uncounted: reinstating the organisation does not bring it back.
    r = await seeded.patch(
        "/admin/owners/example-rec", json={"status": "verified"}, headers=ADMIN
    )
    assert r.status_code == 200, r.text
    assert await _is_member(seeded) is False


async def test_a_platform_administrator_removes_it_with_their_login(seeded):  # noqa: F811
    r = await _add(seeded, ADMIN)
    assert r.status_code == 201, r.text
    await _suspend(seeded, "example-rec")

    # The organisation's own administrator may not: no organisation seat
    # carries the grant, and a suspended organisation would be refused anyway.
    own_admin = person({"example-rec": ["ds-participant-admin"]})
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-rec", headers=own_admin
    )
    assert r.status_code == 403, r.text

    operator = person({}, roles=["platform-admin"])
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-rec", headers=operator
    )
    assert r.status_code == 204, r.text


# ── ir-cli ───────────────────────────────────────────────────────────────────


@pytest.fixture
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
    yield url
    get_settings.cache_clear()


def test_ir_cli_removes_a_suspended_organisations_membership(cli_database):
    import sqlite3

    from identity_registry.cli.main import app as cli

    with sqlite3.connect(cli_database.removeprefix("sqlite+aiosqlite:///")) as conn:
        conn.execute(
            f"INSERT INTO dids (did, did_type, active) VALUES ('{MEMBER}', 'user', 1)"
        )
        conn.execute(
            "INSERT INTO owners (id, type, name, did, aliases, status, verified_by) "
            f"VALUES ('{REC['id']}', 'schema:Organization', 'x', '{REC['did']}', "
            "'[\"ex-rec\"]', 'suspended', 'test')"
        )

    runner = CliRunner()
    args = ["--user-did", MEMBER, "--organization", REC["id"]]
    added = runner.invoke(cli, ["membership", "add", *args])
    assert added.exit_code == 0, added.output

    removed = runner.invoke(cli, ["membership", "remove", *args])
    assert removed.exit_code == 0, removed.output
    assert "Membership removed" in removed.output

    listed = runner.invoke(cli, ["membership", "list", "--organization", REC["id"]])
    assert f"No members in {REC['id']}." in listed.output
