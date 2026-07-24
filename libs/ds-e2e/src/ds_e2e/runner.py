from __future__ import annotations

import logging
from collections.abc import Iterable

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY, BaseFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


def run_flow(flow_name: str, settings: E2ESettings) -> FlowResult:
    flow_cls = FLOW_REGISTRY.get(flow_name)
    if not flow_cls:
        result = FlowResult(flow_name=flow_name)
        result.fail_step("setup", f"unknown flow: {flow_name}. Available: {list(FLOW_REGISTRY.keys())}")
        return result

    http = HttpClient(settings)
    try:
        flow = flow_cls(settings, http)
        log.info("Running flow: %s — %s", flow.name, flow.description)
        return flow.execute()
    finally:
        http.close()


def run_all(settings: E2ESettings) -> list[FlowResult]:
    results = []
    for name in FLOW_REGISTRY:
        results.append(run_flow(name, settings))
    return results


def run_selected(names: Iterable[str], settings: E2ESettings) -> list[FlowResult]:
    """Run a named subset, in the registry's order.

    Registry order puts the cheap, foundational flows first, so a subset stays
    diagnosable even when the caller lists it in some other order."""
    wanted = set(names)
    return [run_flow(name, settings) for name in FLOW_REGISTRY if name in wanted]
