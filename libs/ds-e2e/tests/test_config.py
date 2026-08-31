"""Tests for E2ESettings configuration loading."""

from __future__ import annotations

import os
from unittest.mock import patch

from ds_e2e.config import E2ESettings


def test_defaults():
    # `_env_file=None` like every sibling test. Without it this reads whatever
    # `.env` / `.env.local` the working directory happens to expose, so the same
    # assertion passes or fails depending on where pytest was started.
    settings = E2ESettings(_env_file=None)
    assert settings.connector_url == "http://172.17.0.1:30001"
    assert settings.consumer_connector_url == "http://172.17.0.1:31001"
    # 30022 — the mock, which is what `task docker:restart` starts. 30002
    # belongs to the real celine dataset-api, whose compose file `build` and
    # `docker:restart` both skip by name (`E2E-13`).
    assert settings.dataset_api_url == "http://172.17.0.1:30022"
    assert settings.provenance_url == "http://172.17.0.1:30000"
    assert settings.identity_registry_url == "http://172.17.0.1:30005"
    # The host-gateway address, not a Docker DNS name: the EDCs are reachable at
    # the same address whether they run in compose or on the host (see config.py).
    assert settings.counter_party_address == "http://172.17.0.1:19194/protocol/2025-1"
    # `svc-ds-e2e`, not the portal's client. The harness borrowing
    # `svc-ds-portal` is what `a6e6e34` ended — the portal held ten grants it did
    # not need because the tests were using its identity.
    assert settings.service_client_id == "svc-ds-e2e"
    assert settings.poll_timeout == 120


def test_env_override():
    overrides = {
        "CONNECTOR_URL": "http://custom:30001",
        "CATALOG_CONNECTOR_URL": "http://custom:31001",
        "E2E_COUNTER_PARTY_ADDRESS": "http://custom-edc:19194/protocol/2025-1",
    }
    with patch.dict(os.environ, overrides, clear=False):
        settings = E2ESettings(_env_file=None)
        assert settings.connector_url == "http://custom:30001"
        assert settings.consumer_connector_url == "http://custom:31001"
        assert (
            settings.counter_party_address == "http://custom-edc:19194/protocol/2025-1"
        )


# ── E2E-13 / T-1 · the run says which data plane it exercised ────────────────


def test_the_default_data_plane_is_the_one_the_stack_starts():
    """`task docker:restart` brings up the mock on 30022 and nothing on 30002.

    The default has to name what the documented sequence actually starts, or
    that sequence cannot be run as written — which is what `E2E-13` was.
    """
    settings = E2ESettings(_env_file=None)
    assert settings.dataset_api_url.endswith(":30022")
    assert "mock" in settings.data_plane_label


def test_pointing_at_the_real_data_plane_is_one_variable(monkeypatch):
    """`T-1`: the backend is already parameterised, and now it is also named."""
    monkeypatch.setenv("CONNECTOR_DATASET_API_URL", "http://172.17.0.1:30002")
    settings = E2ESettings(_env_file=None)
    assert "real celine dataset-api" in settings.data_plane_label


def test_an_unrecognised_data_plane_says_so_rather_than_guessing(monkeypatch):
    """Silence would be the defect again: an unlabelled run is one whose
    evidence cannot be attributed to a backend afterwards."""
    monkeypatch.setenv("CONNECTOR_DATASET_API_URL", "http://elsewhere.test:8080")
    settings = E2ESettings(_env_file=None)
    label = settings.data_plane_label
    assert "unrecognised" in label
    assert "http://elsewhere.test:8080" in label
