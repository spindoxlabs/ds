"""The dev database fails closed outside `DS_ENV=dev`, before any connection.

`Settings.database_url` defaults to the dev compose Postgres on
`172.17.0.1:35432` with the password `postgres` — whichever stack publishes that
port. Dev keeps it (zero-config). Under any other `DS_ENV` — unset, `production`,
`prod`, `staging`, a typo — a deployment that never set its own
`CONNECTOR_DATABASE_URL`, or set one still carrying the dev password, must
refuse to start, and must do so before `verify_schema` opens a connection.

The suite itself is pinned to `DS_ENV=dev` (`conftest.py`); these tests set the
environment per test with `monkeypatch`, and pass it to the guard through the
real lifespan.
"""

from __future__ import annotations

import pytest
from ds_auth.production import InsecureProductionConfig

import connector.main as main
from connector.config import Settings

OWN_URL = "postgresql+asyncpg://connector:Xk3v9-generated@db.example.org:5432/connector"


def _record_schema_check(monkeypatch, settings: Settings) -> list[str]:
    touched: list[str] = []

    async def _verify_schema():
        touched.append("verify_schema")

    async def _no_sweeper(*_a, **_k):
        return None

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "verify_schema", _verify_schema)
    monkeypatch.setattr(main, "run_sweeper", _no_sweeper)
    return touched


def test_the_settings_default_carries_the_dev_password():
    """What the guard is protecting against, stated: the shipped default."""
    assert ":postgres@" in Settings(_env_file=None).database_url


@pytest.mark.parametrize(
    "url",
    [
        Settings.model_fields["database_url"].default,
        # The dev password on a production-looking host.
        "postgresql+asyncpg://postgres:postgres@db.example.org:5432/connector",
        "postgresql+asyncpg://connector:changeme@db.example.org:5432/connector",
    ],
)
@pytest.mark.parametrize("env", ["production", "prod", "staging", ""])
async def test_outside_dev_a_dev_database_refuses_before_the_schema_check(
    monkeypatch, url, env
):
    monkeypatch.setenv("DS_ENV", env)
    touched = _record_schema_check(monkeypatch, Settings(database_url=url))
    app = main.create_app()

    with pytest.raises(InsecureProductionConfig, match="CONNECTOR_DATABASE_URL"):
        async with app.router.lifespan_context(app):
            pass

    assert touched == []


async def test_a_deployments_own_database_is_not_reported(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    _record_schema_check(monkeypatch, Settings(database_url=OWN_URL))
    app = main.create_app()

    # Other production settings are still at their dev values, so the guard
    # raises — but not about the database.
    with pytest.raises(InsecureProductionConfig) as excinfo:
        async with app.router.lifespan_context(app):
            pass
    assert "CONNECTOR_DATABASE_URL" not in str(excinfo.value)


async def test_dev_keeps_the_zero_config_default(monkeypatch):
    monkeypatch.setenv("DS_ENV", "dev")
    touched = _record_schema_check(monkeypatch, Settings())
    app = main.create_app()

    async with app.router.lifespan_context(app):
        pass

    assert touched == ["verify_schema"]
