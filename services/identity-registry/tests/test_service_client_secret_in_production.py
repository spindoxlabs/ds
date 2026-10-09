"""Which registry must hold a real `svc-ds-identity-registry` secret.

The secret is read by one thing, `registry_notify`: the trust anchor telling the
connectors that the participant list changed. A participant release never
notifies (the chart gives it no connector URLs and no token URL), so on a
participant the setting authenticates nothing. The guard still refused its dev
default there, so the chart had to feed the participant release *some* real
value — and fed it the EDC's `svc-edc` secret under this client's name (chart
parity row 28). Guarding it only where it is used ends that.
"""

from __future__ import annotations

import pytest
from ds_auth.production import ProductionGuard

from identity_registry.config import Settings, register_service_client_secret


@pytest.mark.parametrize(
    "secret", [None, "svc-ds-identity-registry", "CHANGE_ME"], ids=str
)
def test_the_anchor_refuses_a_dev_or_placeholder_secret(secret):
    kwargs = {"role": "trust-anchor"}
    if secret is not None:
        kwargs["service_client_secret"] = secret
    guard = ProductionGuard("identity-registry", env="production")
    register_service_client_secret(guard, Settings(**kwargs))
    assert {v.setting for v in guard.violations} == {
        "IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET"
    }


def test_the_anchor_passes_a_real_secret():
    guard = ProductionGuard("identity-registry", env="production")
    register_service_client_secret(
        guard, Settings(role="trust-anchor", service_client_secret="b3b1f0c2e4d5a7c9")
    )
    assert guard.violations == []


def test_a_participant_is_not_refused_over_a_secret_it_never_uses():
    guard = ProductionGuard("identity-registry", env="production")
    register_service_client_secret(guard, Settings(role="participant"))
    assert guard.violations == []
