"""Tests for flow registry and base flow."""
from __future__ import annotations

from ds_e2e.cli import FlowName
from ds_e2e.config import E2ESettings
from ds_e2e.flows import (
    CHAIN_FLOWS,
    FAST_FLOWS,
    FLOW_REGISTRY,
    SECURITY_FLOWS,
    BaseFlow,
)
from ds_e2e.flows.api_contract import PUBLIC_ROUTES, _guarded_routes

AGGREGATE_FLOWS = {"all", "fast", "security", "chains"}


def test_flow_registry_contains_all_flows():
    assert "smoke" in FLOW_REGISTRY
    assert "uc1" in FLOW_REGISTRY
    assert "uc2" in FLOW_REGISTRY
    assert "uc3" in FLOW_REGISTRY
    assert "api-contract" in FLOW_REGISTRY
    assert "authz-perimeter" in FLOW_REGISTRY


def test_all_flows_are_base_flow_subclasses():
    for name, cls in FLOW_REGISTRY.items():
        assert issubclass(cls, BaseFlow), f"{name} is not a BaseFlow subclass"


def test_all_flows_have_name_and_description():
    for name, cls in FLOW_REGISTRY.items():
        assert cls.name, f"{name} has no name"
        assert cls.description, f"{name} has no description"


def test_registry_key_matches_flow_name():
    """`--flow x` must run the flow that reports itself as x.

    The registry key is what the CLI dispatches on and the flow's `name` is what
    the report is filed under; a mismatch means the report names a flow that did
    not run."""
    for key, cls in FLOW_REGISTRY.items():
        assert cls.name == key, f"registry key {key!r} != flow name {cls.name!r}"


def test_cli_exposes_every_registered_flow():
    """A flow that is registered but not in the enum is unreachable from the CLI."""
    cli_flows = {f.value for f in FlowName} - AGGREGATE_FLOWS
    assert cli_flows == set(FLOW_REGISTRY)


def test_flow_subsets_are_registered():
    assert set(FAST_FLOWS) <= set(FLOW_REGISTRY)
    assert set(SECURITY_FLOWS) <= set(FLOW_REGISTRY)
    assert set(CHAIN_FLOWS) <= set(FLOW_REGISTRY)


def test_public_and_guarded_route_tables_are_disjoint():
    """A route cannot be both intentionally public and required to refuse.

    The two tables encode opposite expectations, so an overlap would make the
    contract flow assert both 200 and 401 for the same endpoint — and whichever
    assertion ran second would silently define the policy."""
    settings = E2ESettings(_env_file=None)
    public = {(svc, method, path) for svc, method, path in PUBLIC_ROUTES}
    guarded = {(svc, method, path) for svc, method, path, _ in _guarded_routes(settings)}
    assert not (public & guarded)


def test_guarded_route_table_has_no_duplicates():
    settings = E2ESettings(_env_file=None)
    routes = [(svc, method, path) for svc, method, path, _ in _guarded_routes(settings)]
    assert len(routes) == len(set(routes))
