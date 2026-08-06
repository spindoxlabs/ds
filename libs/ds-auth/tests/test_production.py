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
        "federated-catalog":
            root / "services/federated-catalog/src/federated_catalog/main.py",
        "identity-registry":
            root / "services/identity-registry/src/identity_registry/main.py",
        "provenance": root / "services/provenance/src/provenance/main.py",
    }
    missing = [
        name for name, path in mains.items()
        if "guard.require_https(" not in path.read_text()
    ]
    assert not missing, f"{missing} build a ProductionGuard and register no https rule"


def test_require_https_accepts_https_and_an_unset_value():
    guard = ProductionGuard("svc", env="production")
    guard.require_https("ISSUER", "https://sso.example.org/realms/ds", "use https")
    guard.require_https("ABSENT", None, "use https")
    guard.enforce()  # must not raise
