"""Tests for flow registry and base flow."""
from __future__ import annotations

from ds_e2e.flows import FLOW_REGISTRY, BaseFlow
from ds_e2e.flows.smoke import SmokeFlow
from ds_e2e.flows.uc1 import UC1Flow
from ds_e2e.flows.uc2 import UC2Flow
from ds_e2e.flows.uc3 import UC3Flow


def test_flow_registry_contains_all_flows():
    assert "smoke" in FLOW_REGISTRY
    assert "uc1" in FLOW_REGISTRY
    assert "uc2" in FLOW_REGISTRY
    assert "uc3" in FLOW_REGISTRY


def test_all_flows_are_base_flow_subclasses():
    for name, cls in FLOW_REGISTRY.items():
        assert issubclass(cls, BaseFlow), f"{name} is not a BaseFlow subclass"


def test_all_flows_have_name_and_description():
    for name, cls in FLOW_REGISTRY.items():
        assert cls.name, f"{name} has no name"
        assert cls.description, f"{name} has no description"
