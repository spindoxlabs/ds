"""The `collector-holder` flow's own reasoning.

Plan `a-collector-registers-consent-at-the-holder`. The live properties need a
stack; pinned here is how the flow reads what it observes — which answers count
as the right refusal, what a registration must echo, and which plane the data
step asks.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.cli import FlowName
from ds_e2e.config import E2ESettings
from ds_e2e.flows import FAST_FLOWS, FLOW_REGISTRY
from ds_e2e.flows.collector_holder import (
    POD_DUAL,
    POD_MEMBER,
    POD_UNADMITTED,
    CollectorHolderFlow,
)
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _flow(settings, raw) -> tuple[CollectorHolderFlow, MagicMock]:
    http = MagicMock(spec=HttpClient)
    http.raw.side_effect = raw
    http.bearer_headers.return_value = {"Authorization": "Bearer e2e"}
    http.user_headers.return_value = {"Authorization": "Bearer person"}
    flow = CollectorHolderFlow(settings, http)
    flow.collector = {"Authorization": "Bearer community"}
    flow.consumer = {"Authorization": "Bearer consumer"}
    return flow, http


def _step(result: FlowResult, name: str):
    return next(s for s in result.steps if s.name == name)


def test_the_flow_is_registered_after_the_organisation_token_flow():
    names = list(FLOW_REGISTRY)
    assert FLOW_REGISTRY["collector-holder"] is CollectorHolderFlow
    assert names.index("organisation-token") < names.index("collector-holder")
    assert names.index("collector-holder") < names.index("fail-closed")
    assert "collector-holder" in {f.value for f in FlowName}
    assert "collector-holder" not in FAST_FLOWS


@pytest.mark.rule("D-20", "D-21", "D-15c")
def test_it_declares_the_rules_it_evidences():
    assert {"D-15c", "D-20", "D-21"} <= set(CollectorHolderFlow.rules)


def test_the_unadmitted_supply_point_is_the_fixture_row_nobody_owns():
    """If the prerequisite were ignored, this row would come back — which is
    what makes the negative case observable in the data step."""
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "services/dataset-api-mock/src/dataset_api_mock/main.py"
    ).read_text()
    [pods] = [
        ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "GRID_PODS" for t in node.targets)
    ]
    assert {POD_MEMBER, POD_DUAL, POD_UNADMITTED} == set(pods)


def _refusals(**override):
    answers = {
        "consumer": (403, {"detail": "'x' is not an accepted consent collector"}),
        "partner": (403, {"detail": "Subject 'y' is not a member of organisation 'z'"}),
        "seat": (
            403,
            {"detail": "Missing required permission: connector.consent.provision"},
        ),
    }
    answers.update(override)

    def raw(method, url, body=None, headers=None, **_):
        if headers and headers.get("Authorization") == "Bearer consumer":
            return answers["consumer"]
        if headers and headers.get("Authorization") == "Bearer person":
            return answers["seat"]
        return answers["partner"]

    return raw


def test_the_refusals_pass_only_with_their_own_causes(settings):
    flow, _ = _flow(settings, _refusals())
    result = FlowResult(flow_name="collector-holder")
    flow._check_refusals(result)
    assert _step(result, "refused writers").status == "PASS"


@pytest.mark.parametrize(
    "override",
    [
        {"consumer": (200, [])},
        {"partner": (403, {"detail": "not an accepted consent collector"})},
        {"seat": (422, {"detail": "decided_by is stated by an organisation"})},
        {"seat": (500, {"detail": "Missing required permission"})},
    ],
    ids=["unlisted-accepted", "wrong-cause", "seat-reached-validation", "server-error"],
)
def test_a_refusal_for_another_reason_fails(settings, override):
    flow, _ = _flow(settings, _refusals(**override))
    result = FlowResult(flow_name="collector-holder")
    flow._check_refusals(result)
    assert _step(result, "refused writers").status == "FAIL"


def test_a_registration_must_echo_the_collector_and_the_member(settings):
    def raw(method, url, body=None, headers=None, **_):
        return 200, [
            {
                "collector": settings.provider_did,
                "decided_by": "service",  # not the member's
                "keys_supplied": True,
                "missing_prerequisites": [],
            }
        ]

    flow, _ = _flow(settings, raw)
    result = FlowResult(flow_name="collector-holder")
    assert flow._register(result) is False
    assert _step(result, "register").status == "FAIL"


def test_the_seat_probe_sends_no_decided_by(settings):
    """A seat that got past the guard must meet a 403, not a 422 about the body."""
    sent = []

    def raw(method, url, body=None, headers=None, **_):
        sent.append((headers, body))
        return 403, {"detail": "Missing required permission"}

    flow, _ = _flow(settings, raw)
    flow._check_refusals(FlowResult(flow_name="collector-holder"))
    seat_bodies = [b for h, b in sent if h == {"Authorization": "Bearer person"}]
    assert seat_bodies and all("decided_by" not in b for b in seat_bodies)


def test_the_data_step_asks_the_grid_operator_s_own_plane(settings):
    flow, http = _flow(settings, lambda *a, **k: (200, {}))
    http.post_raw.return_value = (
        200,
        {"items": [{"pod": POD_MEMBER}, {"pod": POD_DUAL}], "count": 2},
    )
    result = FlowResult(flow_name="collector-holder")
    flow._expect_pods(
        result,
        "rows",
        {"authorization": "tok", "agreement_id": "agr"},
        "agr",
        "tp",
        {POD_MEMBER, POD_DUAL},
    )
    url = http.post_raw.call_args.args[0]
    assert url.startswith(settings.grid_operator_mock_data_plane_url)
    assert (
        http.post_raw.call_args.kwargs["headers"]["Edc-Purpose"]
        == "FlexibilityResearch"
    )
    assert _step(result, "rows").status == "PASS"


def test_an_extra_supply_point_fails_the_data_step(settings):
    flow, http = _flow(settings, lambda *a, **k: (200, {}))
    http.post_raw.return_value = (
        200,
        {"items": [{"pod": POD_DUAL}, {"pod": POD_UNADMITTED}], "count": 2},
    )
    result = FlowResult(flow_name="collector-holder")
    flow._expect_pods(result, "rows", {"authorization": "t"}, "a", "t", {POD_DUAL})
    assert _step(result, "rows").status == "FAIL"


def test_cleanup_withdraws_as_the_collector_and_revokes_its_requests(settings):
    calls = []

    def raw(method, url, body=None, headers=None, **_):
        calls.append((method, url, body))
        if url.endswith("/consumer/requests"):
            return 200, [
                {
                    "id": "r1",
                    "can_revoke": True,
                    "asset_id": settings.grid_meter_asset_id,
                },
                {"id": "r2", "can_revoke": True, "asset_id": "other"},
            ]
        return 200, [{}]

    flow, http = _flow(settings, raw)
    http.bearer_headers_for.return_value = {"Authorization": "Bearer x"}
    flow.cleanup()
    withdrawals = [b for m, u, b in calls if u.endswith("/consent/admin/shares")]
    assert withdrawals and all(
        b["enabled"] is False and b["decided_by"] == "collector" for b in withdrawals
    )
    revoked = [u for m, u, b in calls if u.endswith("/revoke")]
    assert revoked == [f"{settings.consumer_connector_url}/consumer/requests/r1/revoke"]


# ── the list read (ADR-0021) ─────────────────────────────────────────────────


def _holder_lists(settings, **override):
    """A grid operator answering `GET /consent/admin/decisions` page by page,
    and `subject-shares` for the withdrawn member, as the connector does."""
    import urllib.parse as up

    member_row = "row-member"
    entries = {
        settings.data_subject_id: [
            {
                "dataset_id": "grid-meters",
                "consent_id": member_row,
                "state": "withdrawn",
                "decided_by": "subject",
                "keys": [],
            }
        ],
        settings.dual_subject_id: [
            {
                "dataset_id": "grid-meters",
                "consent_id": "row-dual",
                "state": "granted",
                "decided_by": "subject",
                "keys": [f"pod:{POD_DUAL}"],
            }
        ],
    }
    entries.update(override.pop("entries", {}))
    unlisted = override.pop(
        "unlisted", (403, {"detail": "not an accepted consent collector"})
    )
    ordered = sorted(entries)

    def raw(method, url, body=None, headers=None, **_):
        query = dict(up.parse_qsl(up.urlparse(url).query))
        if "/consent/admin/subject-shares" in url:
            return 200, [{"offer_id": settings.grid_release_offer_id, "id": member_row}]
        if headers == {"Authorization": "Bearer consumer"}:
            return unlisted
        start = ordered.index(query["cursor"]) + 1 if "cursor" in query else 0
        limit = int(query["limit"])
        page = ordered[start : start + limit]
        more = start + limit < len(ordered)
        return 200, {
            "subjects": [{"subject_id": s, "decisions": entries[s]} for s in page],
            "next_cursor": page[-1] if more else None,
        }

    return raw


def test_the_list_read_passes_when_it_agrees_with_the_read_back(settings):
    flow, _ = _flow(settings, _holder_lists(settings))
    result = FlowResult(flow_name="collector-holder")
    flow._check_decisions_list(result)
    step = _step(result, "the list read says who withdrew")
    assert step.status == "PASS", step


@pytest.mark.parametrize(
    "case",
    ["unlisted-empty", "member-granted", "other-row", "partner-listed"],
)
def test_the_list_read_fails_on_what_it_exists_to_catch(settings, case):
    member = settings.data_subject_id
    override = {
        "unlisted-empty": {"unlisted": (200, {"subjects": [], "next_cursor": None})},
        "member-granted": {
            "entries": {member: [{"consent_id": "row-member", "state": "granted"}]}
        },
        "other-row": {
            "entries": {
                member: [
                    {
                        "consent_id": "the-collector-s-row",
                        "state": "withdrawn",
                        "decided_by": "collector",
                    }
                ]
            }
        },
        "partner-listed": {
            "entries": {settings.partner_member_id: [{"state": "granted"}]}
        },
    }[case]
    flow, _ = _flow(settings, _holder_lists(settings, **override))
    result = FlowResult(flow_name="collector-holder")
    flow._check_decisions_list(result)
    assert _step(result, "the list read says who withdrew").status == "FAIL"


def test_a_page_that_repeats_a_subject_fails(settings):
    listed = _holder_lists(settings)

    def raw(method, url, body=None, headers=None, **kwargs):
        status, answer = listed(method, url, body, headers, **kwargs)
        if isinstance(answer, dict) and "cursor" in url:
            # Every page after the first starts over: a cursor that is ignored.
            return listed(method, url.split("&cursor=")[0], body, headers)
        return status, answer

    flow, _ = _flow(settings, raw)
    result = FlowResult(flow_name="collector-holder")
    flow._check_decisions_list(result)
    assert _step(result, "the list read says who withdrew").status == "FAIL"
