"""The dev database default fails closed under `DS_ENV=production`.

`Settings.database_url` defaults to the dev compose Postgres on
`172.17.0.1:35432`, which is whichever stack publishes that port. Dev keeps it
(zero-config). A deployment that never set `IDENTITY_REGISTRY_DATABASE_URL` must
refuse to start, and `ir-cli` must refuse to open it, before any connection.
"""

from __future__ import annotations

import pytest
from ds_auth.production import InsecureProductionConfig, ProductionGuard
from typer.testing import CliRunner

from identity_registry import main as main_module
from identity_registry.cli.main import app as cli
from identity_registry.config import (
    DEV_DATABASE_URL,
    Settings,
    get_settings,
    refuse_dev_database_in_production,
    register_database_url,
)

OWN_URL = "postgresql+asyncpg://registry:s3cret@db.example.org:5432/identity_registry"


def _use_url(monkeypatch, env: str, url: str) -> None:
    monkeypatch.setenv("DS_ENV", env)
    monkeypatch.setenv("IDENTITY_REGISTRY_DATABASE_URL", url)
    get_settings.cache_clear()


def test_the_settings_default_is_the_registered_dev_value(monkeypatch):
    monkeypatch.delenv("IDENTITY_REGISTRY_DATABASE_URL")
    assert Settings(_env_file=None).database_url == DEV_DATABASE_URL


def test_the_guard_flags_the_dev_default():
    guard = ProductionGuard("identity-registry", env="production")
    register_database_url(guard, Settings(database_url=DEV_DATABASE_URL))
    assert [v.setting for v in guard.violations] == ["IDENTITY_REGISTRY_DATABASE_URL"]


def test_the_guard_accepts_a_deployments_own_database():
    guard = ProductionGuard("identity-registry", env="production")
    register_database_url(guard, Settings(database_url=OWN_URL))
    assert guard.violations == []


def test_the_one_shot_check_refuses_only_in_production(monkeypatch):
    _use_url(monkeypatch, "production", DEV_DATABASE_URL)
    with pytest.raises(
        InsecureProductionConfig, match="IDENTITY_REGISTRY_DATABASE_URL"
    ):
        refuse_dev_database_in_production("ir-cli")

    _use_url(monkeypatch, "production", OWN_URL)
    refuse_dev_database_in_production("ir-cli")

    _use_url(monkeypatch, "dev", DEV_DATABASE_URL)
    refuse_dev_database_in_production("ir-cli")


def test_the_cli_refuses_the_dev_database_before_connecting(tmp_path, monkeypatch):
    """Exit 1 with the guard's message — not the conftest's live-database error,
    which would mean an engine was built first."""
    _use_url(monkeypatch, "production", DEV_DATABASE_URL)
    monkeypatch.delenv("DB_SKIP_SCHEMA_CHECK", raising=False)
    owners = tmp_path / "owners.yaml"
    owners.write_text(
        "owners:\n  - id: example-rec\n    did: did:web:rec.example.org\n"
    )

    result = CliRunner().invoke(cli, ["owner", "import", "--file", str(owners)])

    assert result.exit_code == 1, result.output
    assert "IDENTITY_REGISTRY_DATABASE_URL" in result.output
    assert not isinstance(result.exception, RuntimeError)


def _record_db_access(monkeypatch) -> list[str]:
    touched: list[str] = []

    async def _verify_schema():
        touched.append("verify_schema")

    async def _custody(guard, settings):
        touched.append("custody")

    async def _indices():
        touched.append("indices")

    monkeypatch.setattr(main_module, "verify_schema", _verify_schema)
    monkeypatch.setattr(main_module, "_check_key_custody", _custody)
    monkeypatch.setattr(main_module, "_warn_on_duplicate_status_list_indices", _indices)
    return touched


async def test_the_service_refuses_the_dev_database_before_the_schema_check(
    monkeypatch,
):
    _use_url(monkeypatch, "production", DEV_DATABASE_URL)
    touched = _record_db_access(monkeypatch)

    with pytest.raises(
        InsecureProductionConfig, match="IDENTITY_REGISTRY_DATABASE_URL"
    ):
        async with main_module.lifespan(None):
            pass

    assert touched == []


async def test_dev_keeps_the_zero_config_default(monkeypatch):
    _use_url(monkeypatch, "dev", DEV_DATABASE_URL)
    touched = _record_db_access(monkeypatch)

    async with main_module.lifespan(None):
        pass

    assert touched == ["verify_schema", "custody", "indices"]
