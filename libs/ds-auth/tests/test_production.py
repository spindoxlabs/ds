"""Production configuration guard — warn in dev, refuse to boot in production."""
from __future__ import annotations

import pytest

from ds_auth.production import (
    InsecureProductionConfig,
    ProductionGuard,
    current_env,
)


def test_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("DS_ENV", raising=False)
    assert current_env() == "dev"


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
