"""The guard in `conftest.py` holds: a unit test cannot open a real database.

Written after the CLI tests in `test_dev_dids_in_production.py` wrote into
whichever registry published `172.17.0.1:35432`. Each test below takes the path
that did it and shows it now stops before a connection is attempted.
"""

from __future__ import annotations

import os

import pytest
from conftest import TEST_DATABASE_URL, LiveDatabaseInUnitTest
from sqlalchemy.ext import asyncio as sqlalchemy_asyncio
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli
from identity_registry.config import get_settings
from identity_registry.db import engine as engine_module

LIVE_URL = "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/identity_registry"


def test_the_environment_names_sqlite():
    assert os.environ["IDENTITY_REGISTRY_DATABASE_URL"] == TEST_DATABASE_URL
    assert get_settings().database_url == TEST_DATABASE_URL


def test_the_service_engine_is_sqlite_by_default():
    assert engine_module.get_engine().url.drivername == "sqlite+aiosqlite"


def test_a_postgres_url_is_refused_before_connecting(monkeypatch):
    monkeypatch.setenv("IDENTITY_REGISTRY_DATABASE_URL", LIVE_URL)
    get_settings.cache_clear()

    with pytest.raises(LiveDatabaseInUnitTest, match="172.17.0.1:35432"):
        engine_module.get_engine()


def test_the_cli_path_that_wrote_to_a_live_registry_is_refused(tmp_path, monkeypatch):
    """The exact shape of the incident: `owner import` in dev, default URL."""
    monkeypatch.setenv("DS_ENV", "dev")
    monkeypatch.setenv("IDENTITY_REGISTRY_DATABASE_URL", LIVE_URL)
    monkeypatch.delenv("DB_SKIP_SCHEMA_CHECK", raising=False)
    get_settings.cache_clear()
    owners = tmp_path / "owners.yaml"
    owners.write_text(
        "owners:\n"
        "  - id: example-rec\n"
        "    did: did:web:example-rec.dataspaces.localhost\n"
    )

    result = CliRunner().invoke(cli, ["owner", "import", "--file", str(owners)])

    assert result.exit_code != 0
    assert isinstance(result.exception, LiveDatabaseInUnitTest)


def test_the_cached_engine_does_not_survive_a_test():
    """A cached engine built by an earlier test would bypass the factory check."""
    assert engine_module._engine is None
    assert engine_module._session_factory is None


@pytest.mark.integration
def test_the_integration_layer_opts_out():
    """Marked tests get the real factory, which is what lets that layer run."""
    assert engine_module.create_async_engine is sqlalchemy_asyncio.create_async_engine
