"""Production configuration guard — warn in dev, refuse to boot in production."""

from __future__ import annotations

from pathlib import Path

import pytest

from ds_auth.production import (
    InsecureProductionConfig,
    ProductionGuard,
    current_env,
)


def test_defaults_to_production(monkeypatch):
    """Forgetting `DS_ENV` must fail closed, not open.

    This asserted ``"dev"`` until 2026-08-04. That default meant every guard in
    the platform was disarmed by *omission* — a chart that drops the variable, a
    hand-rolled deployment that never heard of it — so the one situation the
    guards exist for, nobody having thought about configuration, was the
    situation in which they said nothing.

    Development now opts out explicitly in `.env.local`, and compose (which *is*
    the dev topology) passes `DS_ENV: ${DS_ENV:-dev}` to every service.
    """
    monkeypatch.delenv("DS_ENV", raising=False)
    assert current_env() == "production"


def test_an_unconfigured_service_refuses_to_start(monkeypatch):
    """The behaviour the inversion buys, end to end."""
    monkeypatch.delenv("DS_ENV", raising=False)
    guard = ProductionGuard("svc")
    guard.forbid_default("KEY", "insecure-dev-key", {"insecure-dev-key"}, "rotate it")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_dev_must_be_asked_for(monkeypatch):
    monkeypatch.setenv("DS_ENV", "dev")
    guard = ProductionGuard("svc")
    guard.forbid_default("KEY", "insecure-dev-key", {"insecure-dev-key"}, "rotate it")
    guard.enforce()  # must not raise


def test_dev_only_warns(caplog):
    guard = ProductionGuard("svc", env="dev")
    guard.forbid_default("KEY", "insecure-dev-key", {"insecure-dev-key"}, "rotate it")
    guard.enforce()  # must not raise
    assert len(guard.violations) == 1


def test_production_raises():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("KEY", "insecure-dev-key", {"insecure-dev-key"}, "rotate it")
    with pytest.raises(InsecureProductionConfig) as exc:
        guard.enforce()
    assert "KEY" in str(exc.value)
    assert "rotate it" in str(exc.value)


def test_production_reports_every_violation_at_once():
    """A chart author should get the full list in one deploy, not one per cycle."""
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("A", "insecure-dev-key", {"insecure-dev-key"}, "fix a")
    guard.require_set("B", None, "fix b")
    guard.forbid_true("C", True, "fix c")
    with pytest.raises(InsecureProductionConfig) as exc:
        guard.enforce()
    message = str(exc.value)
    for name in ("A", "B", "C"):
        assert name in message
    assert "3 insecure default(s)" in message


def test_clean_config_passes_in_production():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("KEY", "a-real-generated-secret", {"insecure-dev-key"}, "x")
    guard.require_set("URL", "https://keycloak.example/realms/ds", "x")
    guard.forbid_true("INSECURE", False, "x")
    guard.enforce()  # must not raise


def test_universal_weak_values_are_caught_without_registration():
    """A dev default nobody remembered to register should still be flagged."""
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("DB_PASSWORD", "postgres", set(), "use a real password")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_require_set_treats_blank_as_unset():
    guard = ProductionGuard("svc", env="production")
    guard.require_set("URL", "   ", "set it")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_require_https_rejects_plain_http():
    guard = ProductionGuard("svc", env="production")
    guard.require_https("ISSUER", "http://keycloak.internal/realms/ds", "use https")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_none_values_are_not_flagged_as_weak_defaults():
    """`forbid_default` is about wrong values; absence is `require_set`'s job."""
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("OPTIONAL", None, {"insecure-dev-key"}, "x")
    guard.enforce()  # must not raise


def test_env_var_drives_enforcement(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    guard = ProductionGuard("svc")
    guard.forbid_true("INSECURE", True, "turn it off")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


# ── A client secret that is still the client id ──────────────────────────────
#
# Dev sets both sides to the same string — `clients.yaml` declares
# `secret: ${SVC_…_SECRET:-<client-id>}` and each service defaults its own
# setting to the same value — so *configured* and *never configured* are
# indistinguishable from either side alone. This is the check that separates
# them, and it runs where both halves are held: the service, at startup.


def test_secret_equal_to_client_id_is_refused():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id(
        "SVC_SECRET", "svc-ds-connector", "svc-ds-connector", "set a real secret"
    )
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_a_real_secret_passes():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id(
        "SVC_SECRET", "svc-ds-connector", "b3b1f0c2e4d5", "set a real secret"
    )
    guard.enforce()  # must not raise


def test_it_catches_a_renamed_client_that_forbid_default_would_miss():
    """The reason this exists alongside `forbid_default`.

    `forbid_default` compares against the shipped literal, so a deployment that
    renames the client and leaves the secret equal to the new id sails through
    it. This compares the two settings against each other, so the name does not
    matter.
    """
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("SVC_SECRET", "acme-connector", {"svc-ds-connector"}, "x")
    guard.enforce()  # forbid_default alone: no violation

    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id(
        "SVC_SECRET", "acme-connector", "acme-connector", "set a real secret"
    )
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_whitespace_and_absence_do_not_flag():
    """Absence is `require_set`'s job; padding must not defeat the comparison."""
    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id("A", None, "x", "r")
    guard.forbid_secret_equal_to_client_id("B", "svc", None, "r")
    guard.forbid_secret_equal_to_client_id("C", "", "", "r")
    guard.enforce()  # must not raise

    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id("D", " svc-ds-portal ", "svc-ds-portal", "r")
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


def test_secret_equal_to_client_id_dev_only_warns(caplog):
    """Same rule as every other guard: loud in dev, fatal in production.

    Named `test_dev_only_warns` until `AUTH-05` cleared ruff: a second function
    by that name shadowed the one at the top of this file, so the
    `forbid_default` dev-path check silently stopped running the day this was
    added. `F811` had been reporting it the whole time, on a linter nothing
    invoked — the smallest possible instance of *a green check is not a check
    that ran*.
    """
    guard = ProductionGuard("svc", env="dev")
    guard.forbid_secret_equal_to_client_id("SVC_SECRET", "svc-x", "svc-x", "r")
    guard.enforce()  # must not raise
    assert len(guard.violations) == 1


# ── AUTH-06 · a guard method with no caller enforces nothing ─────────────────


def test_require_https_is_registered_by_every_service_that_has_an_issuer():
    """`require_https` existed, was tested, and was called by no service.

    A guard method is only a rule once something registers a setting with it, so
    the unit test above proves the method works and this one proves it runs. The
    JWKS every signature is checked against is fetched from the issuer URL;
    over plain HTTP an on-path attacker substitutes the key set.
    """
    root = Path(__file__).resolve().parents[3]
    mains = {
        "connector": root / "services/connector/src/connector/main.py",
        "federated-catalog": root
        / "services/federated-catalog/src/federated_catalog/main.py",
        "identity-registry": root
        / "services/identity-registry/src/identity_registry/main.py",
        "provenance": root / "services/provenance/src/provenance/main.py",
    }
    missing = [
        name
        for name, path in mains.items()
        if "guard.require_https(" not in path.read_text()
    ]
    assert not missing, f"{missing} build a ProductionGuard and register no https rule"


def test_require_https_accepts_https_and_an_unset_value():
    guard = ProductionGuard("svc", env="production")
    guard.require_https("ISSUER", "https://sso.example.org/realms/ds", "use https")
    guard.require_https("ABSENT", None, "use https")
    guard.enforce()  # must not raise


# ── Only `dev` relaxes: an allow-list of one ─────────────────────────────────
#
# The guard used to arm only on the exact string `production`, so every other
# value — `prod`, `staging`, `test`, an empty string from a compose
# `${DS_ENV:-}`, a typo — disarmed every guard on the platform with nothing but
# a warning. Unset, empty and unknown values are production now.

_NOT_DEV = [
    "production",
    "PRODUCTION",
    "prod",
    "staging",
    "test",
    "",
    "  ",
    "devv",
    "development",
]


@pytest.mark.parametrize("value", _NOT_DEV)
def test_every_value_but_dev_is_production(monkeypatch, value):
    from ds_auth.production import is_production

    monkeypatch.setenv("DS_ENV", value)
    assert is_production() is True


@pytest.mark.parametrize("value", ["dev", "DEV", " dev ", "Dev\n"])
def test_only_dev_relaxes(monkeypatch, value):
    from ds_auth.production import is_production

    monkeypatch.setenv("DS_ENV", value)
    assert is_production() is False
    assert current_env() == "dev"


def test_an_empty_value_reads_as_production(monkeypatch):
    monkeypatch.setenv("DS_ENV", "")
    assert current_env() == "production"


@pytest.mark.parametrize("value", _NOT_DEV)
def test_the_guard_raises_for_every_value_but_dev(monkeypatch, value):
    monkeypatch.setenv("DS_ENV", value)
    guard = ProductionGuard("svc")
    guard.forbid_default("KEY", "insecure-dev-key", {"insecure-dev-key"}, "rotate it")
    assert guard.is_production is True
    with pytest.raises(InsecureProductionConfig) as exc:
        guard.enforce()
    assert "only DS_ENV=dev relaxes" in str(exc.value)


@pytest.mark.parametrize("value", ["prod", "staging", "test", "", "typo"])
def test_an_explicit_env_argument_follows_the_same_rule(value):
    guard = ProductionGuard("svc", env=value)
    guard.add("KEY", "bad", "fix")
    with pytest.raises(InsecureProductionConfig) as exc:
        guard.enforce()
    # The message names the value actually seen, not a hard-coded `production`.
    expected = value.strip().lower() or "production"
    assert f"DS_ENV={expected!r}" in str(exc.value)


@pytest.mark.parametrize("value", ["dev", "DEV", " dev "])
def test_an_explicit_dev_argument_only_warns(value):
    guard = ProductionGuard("svc", env=value)
    guard.add("KEY", "bad", "fix")
    assert guard.is_production is False
    guard.enforce()  # must not raise


# ── forbid_dev_database_url ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/connector",
        "postgresql+asyncpg://postgres:postgres@db.internal:5432/provenance",
        "postgresql://app:changeme@db/app",
        "postgresql://app:Password@db/app",
        "postgresql://app:secret@db/app",
        "postgresql://app:@db/app",
        "postgresql://app:%70ostgres@db/app",  # percent-encoded `postgres`
        "postgresql://app:dev@db/app",
    ],
)
def test_a_dev_or_weak_database_password_is_flagged(url):
    guard = ProductionGuard("svc", env="production")
    guard.forbid_dev_database_url("DB_URL", url, "use a real password")
    assert [v.setting for v in guard.violations] == ["DB_URL"]
    with pytest.raises(InsecureProductionConfig):
        guard.enforce()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://app:Xk3v9-long-random@db:5432/app",
        "postgresql://app@db/app",  # no password: peer / IAM auth
        "sqlite+aiosqlite:///./local.db",
        "",
        None,
    ],
)
def test_a_real_or_absent_database_password_passes(url):
    guard = ProductionGuard("svc", env="production")
    guard.forbid_dev_database_url("DB_URL", url, "use a real password")
    assert guard.violations == []


def test_extra_weak_database_passwords_can_be_registered():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_dev_database_url(
        "DB_URL", "postgresql://app:hunter2@db/app", "fix", weak_passwords={"hunter2"}
    )
    assert len(guard.violations) == 1


def test_a_dev_database_url_only_warns_under_dev():
    guard = ProductionGuard("svc", env="dev")
    guard.forbid_dev_database_url(
        "DB_URL", "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/x", "fix"
    )
    assert len(guard.violations) == 1
    guard.enforce()  # must not raise


# ── Placeholders in any spelling (G1, G2) ────────────────────────────────────
#
# Every value in `helm/secrets.example.yaml` is `CHANGE_ME`, and the weak list
# held `changeme` and `change-me` only — so the one placeholder the example file
# is made of passed every guard. A placeholder is matched with case, `_`, `-`
# and no separator all counting as the same word.


@pytest.mark.parametrize(
    "value", ["CHANGE_ME", "Change-Me", "changeme", " change_me ", "CHANGEME"]
)
def test_a_placeholder_in_any_spelling_is_weak(value):
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("SECRET", value, set(), "generate one")
    assert [v.setting for v in guard.violations] == ["SECRET"]


@pytest.mark.parametrize("value", ["change-me-later-9f2c", "exchange_mechanism"])
def test_a_real_value_containing_the_word_passes(value):
    guard = ProductionGuard("svc", env="production")
    guard.forbid_default("SECRET", value, set(), "generate one")
    assert guard.violations == []


@pytest.mark.parametrize("secret", ["CHANGE_ME", "changeme", "password", "secret"])
def test_a_client_secret_that_is_a_weak_value_is_refused(secret):
    """Equal to its client id is one dev default; a placeholder is another, and
    the client-id check alone let it through (G2)."""
    guard = ProductionGuard("svc", env="production")
    guard.forbid_secret_equal_to_client_id("SVC_SECRET", "svc-ds-portal", secret, "r")
    assert [v.setting for v in guard.violations] == ["SVC_SECRET"]


def test_a_placeholder_database_password_is_flagged():
    guard = ProductionGuard("svc", env="production")
    guard.forbid_dev_database_url(
        "DB_URL", "postgresql+asyncpg://app:CHANGE_ME@db:5432/app", "fix"
    )
    assert [v.setting for v in guard.violations] == ["DB_URL"]
