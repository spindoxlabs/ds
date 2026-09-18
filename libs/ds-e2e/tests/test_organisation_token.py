"""The `organisation-token` flow's own reasoning (ADR-0014, `D-20`).

The live properties need a stack. What is pinned here is how the flow reads what
it observes: which statuses count as refusals, what counts as an unreachable
management port, and that a token whose `sub` is not the consumer's context ends
the flow before anything is attempted with it.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock

import httpx
import pytest

from ds_e2e.cli import FlowName
from ds_e2e.config import E2ESettings
from ds_e2e.flows import FAST_FLOWS, FLOW_REGISTRY
from ds_e2e.flows.organisation_token import OrganisationTokenFlow, _claims
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _jwt(**claims) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    return f"e30.{body.decode()}.sig"


def _flow(settings: E2ESettings, http: MagicMock) -> OrganisationTokenFlow:
    return OrganisationTokenFlow(settings, http)


def _step(result: FlowResult, name: str):
    return next(s for s in result.steps if s.name == name)


# ── registration ─────────────────────────────────────────────────────────────


def test_the_flow_is_registered_and_runs_after_the_person_driven_exchanges():
    names = list(FLOW_REGISTRY)
    assert FLOW_REGISTRY["organisation-token"] is OrganisationTokenFlow
    assert names.index("organisation-token") > names.index("consent-withdrawal")
    # `fail-closed` negotiates for the same asset as a person; it runs last.
    assert names.index("organisation-token") < names.index("fail-closed")
    assert "organisation-token" in {f.value for f in FlowName}


def test_it_is_not_a_fast_flow():
    """It needs the EDCs and a completed exchange."""
    assert "organisation-token" not in FAST_FLOWS


@pytest.mark.rule("D-20")
def test_it_declares_the_rule_it_evidences():
    assert "D-20" in OrganisationTokenFlow.rules


# ── the token ────────────────────────────────────────────────────────────────


def test_claims_are_read_from_the_payload():
    assert _claims(_jwt(sub="did:web:c", iss="https://kc/realms/x")) == {
        "sub": "did:web:c",
        "iss": "https://kc/realms/x",
    }
    assert _claims("not-a-jwt") == {}


def test_a_token_naming_another_context_ends_the_flow(settings):
    """The mapper is what binds the client to its participant; without it
    every later refusal would be measured against the wrong identity."""
    http = MagicMock(spec=HttpClient)
    http.get.return_value = {}
    http.token_for.return_value = _jwt(sub="0f3c-service-account-uuid")
    flow = _flow(settings, http)
    flow._check_refusals = MagicMock()

    result = flow.execute()

    assert _step(result, "organisation token").status == "FAIL"
    flow._check_refusals.assert_not_called()
    http.post.assert_not_called()


# ── refusals ─────────────────────────────────────────────────────────────────


def _refusal_http(statuses: dict[tuple[str, str], int]) -> MagicMock:
    http = MagicMock(spec=HttpClient)
    http.bearer_headers_for.return_value = {"Authorization": "Bearer other"}
    http.bearer_headers.return_value = {"Authorization": "Bearer svc"}

    def raw(method, url, *, body=None, form=None, headers=None):
        auth = (headers or {}).get("Authorization", "")
        path = url.split(":", 2)[-1].split("/", 1)[-1]
        return statuses.get((auth, path), 200), None

    http.raw.side_effect = raw
    return http


def _all_refused(settings: E2ESettings) -> dict[tuple[str, str], int]:
    other, svc, org = "Bearer other", "Bearer svc", "Bearer org"
    return {
        (other, "consumer/catalog"): 403,
        (other, "consumer/negotiate"): 403,
        (other, "consumer/requests"): 403,
        (svc, "consumer/negotiate"): 403,
        ("", "consumer/negotiate"): 401,
        (org, "consent/my"): 401,
        (org, "consent/my/shares"): 401,
    }


@pytest.mark.rule("D-20")
def test_every_refusal_is_recognised(settings):
    http = _refusal_http(_all_refused(settings))
    result = FlowResult(flow_name="organisation-token")
    _flow(settings, http)._check_refusals(result, {"Authorization": "Bearer org"})

    assert result.steps, "no step recorded"
    assert all(s.status == "PASS" for s in result.steps), [
        (s.name, s.status, s.detail) for s in result.steps
    ]


@pytest.mark.rule("D-20")
@pytest.mark.parametrize(
    "key,status,step",
    [
        (("Bearer other", "consumer/negotiate"), 200, "another participant's token"),
        (("Bearer other", "consumer/catalog"), 401, "another participant's token"),
        (
            ("Bearer svc", "consumer/negotiate"),
            422,
            "a ds permission is not EDC's scope",
        ),
        (("", "consumer/negotiate"), 403, "no credential"),
        (("Bearer org", "consent/my"), 200, "never a person's consents"),
        (("Bearer org", "consent/my/shares"), 403, "never a person's consents"),
    ],
)
def test_anything_but_the_exact_refusal_fails(settings, key, status, step):
    """A 401 where a 403 is due means the token was not even read as an
    organisation's; a 403 where a 401 is due means the subject surface looked
    at a bearer token at all. Both are the wrong reason to be refused."""
    statuses = _all_refused(settings)
    statuses[key] = status
    http = _refusal_http(statuses)
    result = FlowResult(flow_name="organisation-token")
    _flow(settings, http)._check_refusals(result, {"Authorization": "Bearer org"})

    assert _step(result, step).status == "FAIL"


# ── the management port ──────────────────────────────────────────────────────


def test_an_unreachable_port_passes(settings):
    http = MagicMock(spec=HttpClient)
    http.raw.side_effect = httpx.ConnectError("refused")
    result = FlowResult(flow_name="organisation-token")
    _flow(settings, http)._check_management_port(result)

    assert _step(result, "management port unreachable").status == "PASS"
    assert http.raw.call_count == len(settings.edc_management_host_urls) == 3


@pytest.mark.parametrize("status", [401, 403, 404, 200])
def test_any_answer_from_a_management_port_fails(settings, status):
    """A 401 is the port being reachable: the token is then the only check,
    and EDC does not bind it to an audience."""
    http = MagicMock(spec=HttpClient)
    http.raw.side_effect = [httpx.ConnectError("refused"), (status, None)] + [
        httpx.ConnectError("refused")
    ]
    result = FlowResult(flow_name="organisation-token")
    _flow(settings, http)._check_management_port(result)

    step = _step(result, "management port unreachable")
    assert step.status == "FAIL"


def test_no_probe_urls_is_a_declared_skip(monkeypatch):
    monkeypatch.setenv("E2E_EDC_MANAGEMENT_HOST_URLS", "")
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    result = FlowResult(flow_name="organisation-token")
    _flow(settings, http)._check_management_port(result)

    assert _step(result, "management port unreachable").status == "SKIP"
    http.raw.assert_not_called()


# ── housekeeping ─────────────────────────────────────────────────────────────


def test_it_revokes_only_its_own_revocable_requests_for_the_asset(settings):
    http = MagicMock(spec=HttpClient)
    asset = settings.organisation_asset_id
    listing = [
        {"id": "a", "asset_id": asset, "can_revoke": True},
        {"id": "b", "asset_id": asset, "can_revoke": False},
        {"id": "c", "asset_id": "datasets.other", "can_revoke": True},
    ]
    http.raw.side_effect = [(200, listing), (200, {"status": "revoked"})]

    revoked, error = _flow(settings, http)._revoke_own({})

    assert (revoked, error) == (["a"], None)
    revoke_call = http.raw.call_args_list[1]
    assert revoke_call.args[1].endswith("/consumer/requests/a/revoke")


def test_a_failed_revoke_is_reported(settings):
    http = MagicMock(spec=HttpClient)
    asset = settings.organisation_asset_id
    http.raw.side_effect = [
        (200, [{"id": "a", "asset_id": asset, "can_revoke": True}]),
        (502, {"detail": "EDC transfer revoke failed"}),
    ]
    result = FlowResult(flow_name="organisation-token")
    assert _flow(settings, http)._clear(result, {}, "clear") is False
    assert _step(result, "clear").status == "FAIL"


def test_the_data_step_asks_the_mock_plane_whatever_the_suite_plane(monkeypatch):
    """Only the mock serves the target dataset. `.env.local` points the suite
    at the real plane alone, and the first live run failed exactly there."""
    monkeypatch.setenv("E2E_DATA_PLANES", "http://172.17.0.1:30002")
    monkeypatch.setenv("CONNECTOR_DATASET_API_URL", "http://172.17.0.1:30002")
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.raw.return_value = (200, {"authorization": "edr", "agreement_id": "ag"})
    http.post_raw.return_value = (200, {"count": 3})
    result = FlowResult(flow_name="organisation-token")

    _flow(settings, http)._query(result, {}, "ag", "tp")

    assert http.post_raw.call_args.args[0] == "http://172.17.0.1:30022/query"
    assert _step(result, "data").status == "PASS"
