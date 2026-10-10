"""Startup — the code path the suite never ran.

Every other test builds the app with `create_app()` and drives it through
`ASGITransport`, which does not run `lifespan`. So `verify_schema` and the
`ProductionGuard` — the two things standing between a misconfigured deployment
and a service that starts anyway — were exercised by nothing: a change that
removed either would have left the suite green.

These tests call the lifespan directly rather than through a transport, because
what is being asserted is the startup contract, not a request.
"""

from __future__ import annotations

import logging

import pytest

from ds_auth.production import InsecureProductionConfig
from provenance import config as config_module
from provenance.db import engine as engine_module
from provenance.main import create_app, lifespan


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """`get_settings` memoises, so a test that changes the environment has to
    clear it — otherwise it either reads another test's settings or leaks its own."""
    monkeypatch.setattr(config_module, "_settings", None)
    yield
    monkeypatch.setattr(config_module, "_settings", None)


async def _run_lifespan(monkeypatch, *, skip_schema: bool = True) -> None:
    if skip_schema:
        monkeypatch.setenv("DB_SKIP_SCHEMA_CHECK", "true")
    app = create_app()
    async with lifespan(app):
        pass


@pytest.mark.asyncio
async def test_startup_succeeds_with_the_dev_defaults(monkeypatch):
    """Dev is zero-config on purpose: the guard warns and startup proceeds.

    `DS_ENV=dev` is now **set**, not deleted. It used to delete the variable and
    rely on absence meaning dev; the guard's default was inverted to
    `production` so that forgetting it fails closed, which makes "unset" the
    strict case — see the test below.
    """
    monkeypatch.setenv("DS_ENV", "dev")
    await _run_lifespan(monkeypatch)


@pytest.mark.asyncio
async def test_an_absent_ds_env_is_treated_as_production(monkeypatch):
    """The safety property the inversion buys, at this service's own boundary.

    A deployment that never heard of `DS_ENV` gets the strict guard rather than
    the permissive one, so its dev defaults stop it at boot instead of being
    served from.
    """
    monkeypatch.delenv("DS_ENV", raising=False)

    with pytest.raises(InsecureProductionConfig):
        await _run_lifespan(monkeypatch)


@pytest.mark.asyncio
async def test_production_refuses_to_start_on_the_dev_defaults(monkeypatch):
    """The four settings this service registers, all at their dev values."""
    monkeypatch.setenv("DS_ENV", "production")

    with pytest.raises(InsecureProductionConfig) as excinfo:
        await _run_lifespan(monkeypatch)

    message = str(excinfo.value)
    for setting in (
        "PROVENANCE_OIDC_ISSUER_URL",
        "PROVENANCE_OIDC_INSECURE_DEV",
        # `DID-17`: the trust anchor is **named**, not mounted. What production
        # requires is an issuer to resolve and a list to check it against; the
        # mounted `PROVENANCE_TRUST_ANCHOR_KEY_PATH` is gone, and so is the
        # deployment that satisfied the guard by mounting a file it never read.
        "PROVENANCE_TRUST_LIST_URL",
        "PROVENANCE_VC_INSECURE_DEV",
        # R3: no register read means no revocation seen, and no registry to ask
        # means no person's login can be bound to their credential.
        "PROVENANCE_CREDENTIAL_STATUS_URL",
        "PROVENANCE_IDENTITY_REGISTRY_URL",
        # R19: the key the record's chain pseudonymises person ids under.
        "PROVENANCE_SUBJECT_PSEUDONYM_KEY",
    ):
        assert setting in message


@pytest.mark.asyncio
async def test_production_starts_once_all_of_them_are_supplied(monkeypatch):
    """A guard with no supply path is a denial of service on your own deployment
    (`IR-10`). This is the exact set the chart has to render."""
    monkeypatch.setenv("DS_ENV", "production")
    monkeypatch.setenv(
        "PROVENANCE_OIDC_ISSUER_URL", "https://kc.example/realms/dataspaces"
    )
    monkeypatch.setenv("PROVENANCE_OIDC_INSECURE_DEV", "false")
    monkeypatch.setenv("PROVENANCE_TRUST_ANCHOR_DID", "did:web:ta.example.org")
    monkeypatch.setenv("PROVENANCE_TRUST_LIST_URL", "https://ta.example.org/trust")
    monkeypatch.setenv("PROVENANCE_DID_WEB_USE_HTTPS", "true")
    monkeypatch.setenv("PROVENANCE_VC_INSECURE_DEV", "false")
    monkeypatch.setenv(
        "PROVENANCE_CREDENTIAL_STATUS_URL", "https://ta.example.org/status/1"
    )
    monkeypatch.setenv("PROVENANCE_IDENTITY_REGISTRY_URL", "http://ir.example.org")
    monkeypatch.setenv("PROVENANCE_SUBJECT_PSEUDONYM_KEY", "k-9f3c-generated")
    monkeypatch.setenv(
        "PROVENANCE_DATABASE_URL",
        "postgresql+asyncpg://provenance:Xk3v9-generated@db.example.org:5432/provenance",
    )

    await _run_lifespan(monkeypatch)


@pytest.mark.rule("L-18")
@pytest.mark.asyncio
async def test_startup_names_the_retention_period_in_force(monkeypatch):
    """Unset is the ten-year default, said once at startup and not a warning.

    The handler sits on the module's logger: `create_app` configures the root
    logger, which replaces pytest's capture handler."""
    monkeypatch.setenv("DS_ENV", "dev")
    monkeypatch.delenv("PROVENANCE_PERSON_ID_RETENTION_DAYS", raising=False)
    records: list[logging.LogRecord] = []
    handler = logging.Handler(logging.INFO)
    handler.emit = records.append  # type: ignore[method-assign]
    logger = logging.getLogger("provenance.main")
    monkeypatch.setattr(logger, "level", logging.INFO)
    logger.addHandler(handler)
    try:
        await _run_lifespan(monkeypatch)
    finally:
        logger.removeHandler(handler)
    said = [r for r in records if "PERSON_ID_RETENTION_DAYS" in r.getMessage()]
    assert len(said) == 1
    assert said[0].levelname == "INFO"
    assert "3650 days" in said[0].getMessage()


@pytest.mark.asyncio
async def test_the_registry_is_not_required_once_the_binding_is_switched_off(
    monkeypatch,
):
    """`PROVENANCE_PERSON_TOKEN_REQUIRED=false` is the transition switch for a
    caller that does not forward the person's token yet. The status register is
    still required: the switch is about who presents, not about revocation."""
    monkeypatch.setenv("DS_ENV", "production")
    monkeypatch.setenv("PROVENANCE_PERSON_TOKEN_REQUIRED", "false")

    with pytest.raises(InsecureProductionConfig) as excinfo:
        await _run_lifespan(monkeypatch)
    message = str(excinfo.value)
    assert "PROVENANCE_CREDENTIAL_STATUS_URL" in message
    assert "PROVENANCE_IDENTITY_REGISTRY_URL" not in message


@pytest.mark.parametrize("env", ["prod", "staging", "test", ""])
@pytest.mark.asyncio
async def test_any_ds_env_but_dev_is_production(monkeypatch, env):
    """Only `DS_ENV=dev` relaxes the guard; a near-miss value must not disarm it."""
    monkeypatch.setenv("DS_ENV", env)

    with pytest.raises(InsecureProductionConfig):
        await _run_lifespan(monkeypatch)


@pytest.mark.parametrize(
    "url",
    [
        # The dev default itself.
        "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/provenance",
        # The dev password on a production-looking host: a whole-value compare
        # against the default would miss it.
        "postgresql+asyncpg://postgres:postgres@db.example.org:5432/provenance",
        "postgresql+asyncpg://provenance:changeme@db.example.org:5432/provenance",
    ],
)
@pytest.mark.asyncio
async def test_production_refuses_a_dev_database_password(monkeypatch, url):
    monkeypatch.setenv("DS_ENV", "production")
    monkeypatch.setenv("PROVENANCE_DATABASE_URL", url)

    with pytest.raises(InsecureProductionConfig, match="PROVENANCE_DATABASE_URL"):
        await _run_lifespan(monkeypatch)


@pytest.mark.asyncio
async def test_production_refuses_before_the_schema_check(monkeypatch):
    """The dev database names whichever stack publishes the port: a refused
    deployment must not have connected to it first."""
    from provenance import main as main_module

    touched: list[str] = []

    async def _verify_schema():
        touched.append("verify_schema")

    monkeypatch.setattr(main_module, "verify_schema", _verify_schema)
    monkeypatch.setenv("DS_ENV", "production")

    with pytest.raises(InsecureProductionConfig):
        await _run_lifespan(monkeypatch, skip_schema=False)
    assert touched == []


@pytest.mark.asyncio
async def test_startup_refuses_a_database_alembic_does_not_own(monkeypatch):
    """`verify_schema` is the other half of startup. Against a database with no
    `alembic_version` it must refuse, not build the schema itself — a half-built
    schema surfaces later as a 500 on whichever read touched the missing column.

    `DS_ENV=dev` pinned like its neighbours: unset is the strict guard, which
    refuses the dev defaults before the schema check is ever reached."""
    monkeypatch.setenv("DS_ENV", "dev")
    monkeypatch.delenv("DB_SKIP_SCHEMA_CHECK", raising=False)
    monkeypatch.setenv("PROVENANCE_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_session_factory", None)

    with pytest.raises(RuntimeError, match="schema revision"):
        await _run_lifespan(monkeypatch, skip_schema=False)

    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_session_factory", None)


def test_the_suite_runs_without_signature_verification(monkeypatch):
    """States the posture the token helper depends on, so a green run is never
    read as evidence that signatures are checked. See `tests/__init__.py`."""
    settings = config_module.Settings()
    assert settings.oidc_issuer_url is None
    assert settings.oidc_insecure_dev is True


@pytest.mark.asyncio
async def test_an_active_did_web_allowance_is_logged_at_start(monkeypatch):
    """ADR-0029: a widened outbound boundary is said out loud at every start.

    Recorded off the module logger: `create_app` configures logging (`ds_obs`),
    which replaces the handlers `caplog` relies on."""
    from provenance import main

    said: list[str] = []
    monkeypatch.setattr(
        main.log, "warning", lambda msg, *args: said.append(msg % args)
    )
    monkeypatch.setenv("DS_ENV", "dev")
    monkeypatch.setenv("PROVENANCE_DID_WEB_INTERNAL_HOSTS", ".ds.example.org")
    monkeypatch.setenv("PROVENANCE_DID_WEB_INTERNAL_NETWORKS", "192.168.1.10/32")
    await _run_lifespan(monkeypatch)
    assert (
        "did:web internal allowance active: hosts under .ds.example.org may "
        "resolve to 192.168.1.10/32"
    ) in said
