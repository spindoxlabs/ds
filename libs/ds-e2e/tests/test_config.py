"""Tests for E2ESettings configuration loading."""
from __future__ import annotations

import os
from unittest.mock import patch

from ds_e2e.config import E2ESettings


def test_defaults():
    settings = E2ESettings()
    assert settings.connector_url == "http://172.17.0.1:30001"
    assert settings.consumer_connector_url == "http://172.17.0.1:31001"
    assert settings.dataset_api_url == "http://172.17.0.1:30002"
    assert settings.provenance_url == "http://172.17.0.1:30000"
    assert settings.identity_registry_url == "http://172.17.0.1:30005"
    assert settings.counter_party_address == "http://edc-provider:19194/protocol/2025-1"
    assert settings.service_client_id == "svc-ds-portal"
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
        assert settings.counter_party_address == "http://custom-edc:19194/protocol/2025-1"
