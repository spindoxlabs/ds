"""Tests for scenario fixtures.

The scenario tool writes to and deletes from a real identity-registry, so the
properties worth pinning are the ones that make it safe to point at a shared
environment: apply is idempotent, destroy is *narrow*, and a precondition it
cannot provision stops the run instead of being papered over.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient
from ds_e2e.scenario import (
    DEFAULT_SCENARIO,
    ScenarioError,
    ScenarioRunner,
    load_scenario,
    scenarios_dir,
)

SCENARIO = {
    "name": "test-scenario",
    "requires_agreements": [
        {"id": "agr", "version": "1.0", "capacity": "processor"},
    ],
    "owners": [
        {
            "alias": "partner-org",
            "name": "Partner",
            "did": "did:web:partner.test",
            "accepts": {"agreement_id": "agr", "version": "1.0"},
            "member_of": "example-org",
        }
    ],
    "participants": [{"did": "did:web:partner.test", "roles": ["consumer"]}],
}


def _runner(raw_responses):
    """A runner whose HTTP calls are scripted by (method, url-substring)."""
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers_for.return_value = {"Authorization": "Bearer admin"}
    http.get.return_value = [{"id": "agr", "version": "1.0", "capacity": "processor"}]

    calls: list[tuple[str, str]] = []

    def raw(method, url, **kwargs):
        calls.append((method, url))
        for (m, fragment), response in raw_responses.items():
            if m == method and fragment in url:
                return response
        return 200, {}

    http.raw.side_effect = raw
    runner = ScenarioRunner(settings, http, SCENARIO)
    return runner, calls


# ── The shipped scenario ─────────────────────────────────────────────────────


def test_default_scenario_loads():
    data = load_scenario(DEFAULT_SCENARIO)
    assert data["name"] == "energy-chains"
    assert data["owners"]
    assert data["participants"]


def test_scenarios_ship_inside_the_package():
    """Resolved relative to the module, so an installed wheel finds them too."""
    assert scenarios_dir().is_dir()
    assert (scenarios_dir() / f"{DEFAULT_SCENARIO}.yaml").exists()


def test_unknown_scenario_is_an_error():
    with pytest.raises(ScenarioError):
        load_scenario("no-such-scenario")


def test_every_owner_that_accepts_names_a_seeded_agreement():
    """An acceptance pointing at an unseeded agreement fails at runtime.

    Catching it here means the mismatch surfaces on any test run rather than
    only when someone has a stack up."""
    data = load_scenario(DEFAULT_SCENARIO)
    seeded = {
        (a["id"], a["version"]) for a in data.get("requires_agreements") or []
    }
    for owner in data["owners"]:
        accepts = owner.get("accepts")
        if accepts:
            key = (accepts["agreement_id"], accepts["version"])
            assert key in seeded, f"{owner['alias']} accepts unseeded {key}"


def test_declared_capacities_cover_both_sides_of_the_circle():
    """The scenario is useless if every party resolves to the same capacity.

    The whole point of chain-partner is contrasting a processor against an
    independent controller; one capacity means the boundary is untestable."""
    data = load_scenario(DEFAULT_SCENARIO)
    capacities = {a.get("capacity") for a in data["requires_agreements"]}
    assert "processor" in capacities
    assert "independent_controller" in capacities


# ── apply ────────────────────────────────────────────────────────────────────


def test_apply_provisions_owner_agreement_membership_and_participant():
    runner, calls = _runner({("POST", "/admin/owners"): (201, {"id": "partner-org"})})
    report = runner.apply()
    assert report.ok, report.problems
    posted = [url for method, url in calls if method == "POST"]
    assert any("/admin/owners" in u for u in posted)
    assert any("/agreement" in u for u in posted)
    assert any("/admin/memberships" in u for u in posted)
    assert any("/admin/participants" in u for u in posted)


def test_apply_is_idempotent_when_everything_already_exists():
    """A 409 is 'already provisioned', not a failure — re-running must be safe."""
    runner, _ = _runner(
        {
            ("POST", "/admin/owners"): (409, {"detail": "exists"}),
            ("POST", "/agreement"): (409, {"detail": "exists"}),
            ("POST", "/admin/memberships"): (409, {"detail": "exists"}),
            ("POST", "/admin/participants"): (409, {"detail": "exists"}),
        }
    )
    report = runner.apply()
    assert report.ok, report.problems


def test_apply_stops_when_a_required_agreement_is_missing():
    """No agreement means no provable capacity — provisioning owners on top of
    that would produce chain tests that pass by asserting nothing."""
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers_for.return_value = {}
    http.get.return_value = []          # no agreements seeded
    http.raw.return_value = (200, {})
    report = ScenarioRunner(settings, http, SCENARIO).apply()
    assert not report.ok
    assert any("not seeded" in p for p in report.problems)
    assert any("ir-cli agreement import" in p for p in report.problems)
    http.raw.assert_not_called()


def test_apply_rejects_an_agreement_with_the_wrong_capacity():
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers_for.return_value = {}
    http.get.return_value = [
        {"id": "agr", "version": "1.0", "capacity": "independent_controller"}
    ]
    http.raw.return_value = (200, {})
    report = ScenarioRunner(settings, http, SCENARIO).apply()
    assert not report.ok
    assert any("capacity" in p for p in report.problems)


def test_apply_reactivates_a_participant_left_deactivated_by_destroy():
    """apply must converge, not merely create.

    Deregistration deactivates rather than deletes, so a second apply sees a
    409 and would otherwise leave the fixture inert — and a suite's second run
    would quietly assert against a deactivated party."""
    runner, calls = _runner(
        {
            ("POST", "/admin/participants"): (409, {"detail": "exists"}),
            ("GET", "/admin/participants"): (200, {"did": "did:web:partner.test", "active": False}),
            ("PATCH", "/admin/participants"): (200, {"active": True}),
        }
    )
    report = runner.apply()
    assert report.ok, report.problems
    assert any(method == "PATCH" for method, _ in calls)
    assert any("reactivated" in a for a in report.actions)


def test_apply_does_not_patch_an_already_active_participant():
    runner, calls = _runner(
        {
            ("POST", "/admin/participants"): (409, {"detail": "exists"}),
            ("GET", "/admin/participants"): (200, {"did": "did:web:partner.test", "active": True}),
        }
    )
    report = runner.apply()
    assert report.ok, report.problems
    assert not any(method == "PATCH" for method, _ in calls)


def test_apply_reports_a_failed_owner_creation():
    runner, _ = _runner({("POST", "/admin/owners"): (500, "boom")})
    report = runner.apply()
    assert not report.ok
    assert any("could not create owner" in p for p in report.problems)


# ── destroy ──────────────────────────────────────────────────────────────────


def test_destroy_touches_only_what_the_scenario_names():
    """The safety property: pointed at a shared registry, destroy must not be
    able to reach an organisation the scenario never created."""
    runner, calls = _runner({})
    report = runner.destroy()
    assert report.ok, report.problems
    deleted = [url for method, url in calls if method == "DELETE"]
    assert deleted
    for url in deleted:
        assert "partner-org" in url or "partner.test" in url or "example-org" in url


def test_destroy_removes_participants_before_owners():
    """A participant references its owner's DID; removing the owner first would
    leave a registered participant with no organisation behind it."""
    runner, calls = _runner({})
    runner.destroy()
    deletes = [url for method, url in calls if method == "DELETE"]
    participant_idx = next(i for i, u in enumerate(deletes) if "/admin/participants" in u)
    owner_idx = next(i for i, u in enumerate(deletes) if "/admin/owners" in u)
    assert participant_idx < owner_idx


def test_destroy_is_idempotent_when_nothing_exists():
    runner, _ = _runner(
        {
            ("DELETE", "/admin/participants"): (404, None),
            ("DELETE", "/admin/owners"): (404, None),
            ("DELETE", "/admin/memberships"): (404, None),
        }
    )
    report = runner.destroy()
    assert report.ok, report.problems


# ── show ─────────────────────────────────────────────────────────────────────


def test_show_makes_no_write_calls():
    runner, calls = _runner({})
    runner.show()
    assert all(method == "GET" for method, _ in calls), calls
