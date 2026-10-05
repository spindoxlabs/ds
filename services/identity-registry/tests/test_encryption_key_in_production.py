"""A committed `IDENTITY_REGISTRY_ENCRYPTION_KEY` is refused outside dev.

The key seals every private key an instance holds. Each compose participant
ships its own `dev-<participant>-encryption-key` and `.env.example` a
`CHANGE_ME`; the guard knew only the service default, so the others started.
"""

from __future__ import annotations

import pytest
from ds_auth.production import InsecureProductionConfig, ProductionGuard

from identity_registry.config import (
    DEV_ENCRYPTION_KEY,
    Settings,
    get_settings,
    refuse_dev_encryption_key_in_production,
    register_encryption_key,
)


@pytest.mark.parametrize(
    "key",
    [
        DEV_ENCRYPTION_KEY,
        "dev-rec-encryption-key",
        "dev-grid-operator-encryption-key",
        "DEV-third-party-encryption-key",
        "CHANGE_ME",
        "",
    ],
)
def test_a_committed_or_placeholder_key_is_a_violation(key):
    guard = ProductionGuard("identity-registry", env="production")
    register_encryption_key(guard, Settings(encryption_key=key))
    assert {v.setting for v in guard.violations} == {"IDENTITY_REGISTRY_ENCRYPTION_KEY"}


def test_a_deployments_own_key_passes():
    guard = ProductionGuard("identity-registry", env="production")
    register_encryption_key(
        guard, Settings(encryption_key="Vt3w0lTq8cS1gmZ5Hj2kq9yR7nB4xE6aPd0uLf8sWcY")
    )
    assert guard.violations == []


def test_the_one_shot_check_refuses_only_outside_dev(monkeypatch):
    monkeypatch.setenv("IDENTITY_REGISTRY_ENCRYPTION_KEY", "dev-rec-encryption-key")
    monkeypatch.setenv("DS_ENV", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(
            InsecureProductionConfig, match="IDENTITY_REGISTRY_ENCRYPTION_KEY"
        ):
            refuse_dev_encryption_key_in_production("ir-cli")
        monkeypatch.setenv("DS_ENV", "dev")
        refuse_dev_encryption_key_in_production("ir-cli")
    finally:
        get_settings.cache_clear()
