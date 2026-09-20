"""Integration harness: the EDC schema migrations against a real PostgreSQL.

## What is emulated, and why that is enough

At boot, EDC's `SqlSchemaBootstrapperExtension` takes every SQL file queued on the
bootstrapper for one datasource, joins them with `""`, and executes the result as one
string, in one transaction. The stores queue their `*-schema.sql`, and
`EdcSchemaMigrationExtension` queues ds's migrations on the same bootstrapper.
`boot()` below does exactly that and nothing more, so what is tested is the SQL the
runtime would run, in the form it would run it. Which Java class queues which file is
`EdcSchemaMigrationExtensionTest`'s job.

## The fixtures

`edc-schema/v<version>/` holds the schema files of the eight SQL stores
`connector.jar` packages, unmodified, taken from the Eclipse EDC Connector sources at
that tag (Apache-2.0). The directory for the pinned version is checked byte for byte
against the jar by `SchemaFixtureTest` in `services/edc-connector`, so "the pinned
schema" here is the jar's own. Every other directory is an older schema an existing
database may have been created with.

## Requires Postgres, and says so

`task -d services/edc-extensions test:integration`. Each test gets its own database,
created and dropped here, on the server `EDC_EXTENSIONS_TEST_PG` names. It never
touches an EDC's database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest

ADMIN_DSN = os.environ.get(
    "EDC_EXTENSIONS_TEST_PG", "postgresql://postgres:postgres@172.17.0.1:35432/postgres"
)

HERE = Path(__file__).parent
UNIT = HERE.parents[1]
REPO = UNIT.parents[1]
SCHEMA_FIXTURES = HERE / "edc-schema"
MIGRATIONS = UNIT / "src" / "main" / "resources" / "ds-edc-schema"


def pinned_edc_version() -> str:
    """`edcVersion` from the root `gradle.properties`: the one source for it."""
    for line in (REPO / "gradle.properties").read_text().splitlines():
        if line.startswith("edcVersion="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("gradle.properties declares no edcVersion")


def _dsn(name: str) -> str:
    base, _, _ = ADMIN_DSN.rpartition("/")
    return f"{base}/{name}"


@contextmanager
def throwaway_database(prefix: str) -> Iterator[Callable[[], psycopg.Connection]]:
    """A fresh, empty database, and a way to connect to it. Dropped afterwards.

    Named with a uuid so that two runs can never share one: a migration test that
    inherits an earlier run's schema passes for the wrong reason.
    """
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield lambda: psycopg.connect(_dsn(name))
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def database() -> Iterator[Callable[[], psycopg.Connection]]:
    with throwaway_database("edc_schema_it") as connect:
        yield connect
