"""`M-15` — what `smoke` asserts about the rows it just received.

The live half needs an EDR and a plane with `CONFORMANCE_ENABLED=true`. What is
pinned here is the reasoning that turns a report into a verdict, and in
particular the two ways this step could report success while having verified
nothing: a plane that does not expose the endpoint, and a plane that validated an
empty sample.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.smoke import SmokeFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult

ASSET = "datasets.silver.meters_15m"
PATH = "/catalogue/{dataset_id}/conformance"
LABEL = "real celine dataset-api at http://plane.test"


def _report(**overrides):
    report = {
        "dataset_id": ASSET,
        "conforms": True,
        "sample_size": 100,
        "violations": [],
        "profile_name": "celine",
        "profile_version": "v0.10",
        "profile_pinned": True,
    }
    report.update(overrides)
    return report


def _flow(*, exposes: bool, response=(200, None), require=False):
    settings = E2ESettings(_env_file=None, E2E_REQUIRE_CONFORMANCE=require)
    http = MagicMock(spec=HttpClient)
    http.get.return_value = {"paths": {PATH: {}} if exposes else {}}
    http.post_raw.return_value = response
    return SmokeFlow(settings, http)


def _run(flow) -> FlowResult:
    result = FlowResult(flow_name="smoke")
    flow._conformance(result, LABEL, "http://plane.test", ASSET, {"Authorization": "x"})
    return result


def _step(result):
    steps = [s for s in result.steps if "conform" in s.name]
    assert steps, "the step was not recorded at all"
    return steps[0]


# ── Where the endpoint is not there ──────────────────────────────────────────


def test_a_plane_without_the_endpoint_says_it_validated_nothing():
    """The mock is the normal case here, and it is not a failure — it stands in
    for the query surface, and mapping rows into RDF is not part of that surface.

    What matters is that the step says so: `validated=False` in the report, not a
    pass that reads like the rows were checked."""
    step = _step(_run(_flow(exposes=False)))
    assert step.status == "PASS"
    assert step.data.get("validated") is False
    assert "nothing was validated" in step.detail


def test_absence_is_a_failure_once_a_deployment_declares_it_should_be_there():
    """`E2E_REQUIRE_CONFORMANCE`. Without it, switching `CONFORMANCE_ENABLED` off
    by accident reads as a green suite — the endpoint simply stops being probed,
    and every other step still passes."""
    step = _step(_run(_flow(exposes=False, require=True)))
    assert step.status == "FAIL"


def test_presence_is_read_from_the_plane_not_from_a_404():
    """An unregistered route and a wrong path both answer 404, so a status code
    cannot tell "not deployed" from "the harness is calling the wrong URL". The
    OpenAPI document can."""
    flow = _flow(exposes=True, response=(200, _report()))
    _run(flow)
    assert "openapi.json" in flow.http.get.call_args[0][0]


# ── Where it is ──────────────────────────────────────────────────────────────


def test_conforming_rows_pass_and_the_step_names_the_version():
    """Conforming to v0.8 and to v0.10 are different claims about the same rows,
    so the version that ran belongs in the evidence."""
    step = _step(_run(_flow(exposes=True, response=(200, _report()))))
    assert step.status == "PASS"
    assert "v0.10" in step.detail


def test_non_conforming_rows_fail_and_carry_the_violations():
    """The finding this whole endpoint exists to surface: rows that do not mean
    what the catalogue says they mean."""
    report = _report(conforms=False, violations=["kwh: value is not xsd:decimal"] * 9)
    step = _step(_run(_flow(exposes=True, response=(200, report))))
    assert step.status == "FAIL"
    # Bounded: a broken mapping produces one violation per row, and a step's
    # evidence is for reading.
    assert len(step.data["violations"]) == 5


def test_an_empty_sample_is_not_a_pass():
    """Conforming over zero rows is a true statement about nothing. The endpoint
    reports `sample_size` precisely so a caller can refuse to read it as
    evidence, and this is the caller."""
    step = _step(_run(_flow(exposes=True, response=(200, _report(sample_size=0)))))
    assert step.status == "FAIL"


def test_a_report_naming_no_profile_version_is_not_a_pass():
    report = _report(profile_version=None)
    step = _step(_run(_flow(exposes=True, response=(200, report))))
    assert step.status == "FAIL"


@pytest.mark.parametrize("status", [400, 401, 403, 503])
def test_a_non_200_is_the_endpoint_failing_not_the_data(status):
    """A non-conforming dataset answers 200 with `conforms: false`. So a 4xx or
    5xx never means "the rows are bad" — it means the check did not run, and
    reporting it as a data-quality finding would file a broken deployment as one.
    """
    step = _step(_run(_flow(exposes=True, response=(status, {"detail": "nope"}))))
    assert step.status == "FAIL"
    assert "did not run" in step.detail
