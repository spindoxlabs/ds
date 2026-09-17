"""`onboarding-seam` after the plain-service consent path was removed.

The onboarding client's own token must be refused on the consent write, for the
right reason, and the decision is then registered with the community's
organisation client, stating whose decision it is.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.onboarding_seam import OnboardingSeamFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult

ONBOARDING = {"Authorization": "Bearer onboarding"}
ORG = {"Authorization": "Bearer org"}


def _flow(first):
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers_for.return_value = ORG
    calls = []

    def raw(method, url, body=None, headers=None, **_):
        calls.append((headers, body))
        if headers == ONBOARDING:
            return first
        return 200, [{"id": "c1"}]

    http.raw.side_effect = raw
    return OnboardingSeamFlow(settings, http), http, calls


def _step(result, name):
    return next(s for s in result.steps if s.name == name)


@pytest.mark.parametrize(
    "refusal",
    [
        "consent is registered by an organisation's own client",
        "Missing required permission: connector.consent.provision",
    ],
    ids=["classifier", "permission"],
)
def test_the_onboarding_client_is_refused_and_the_org_client_writes(refusal):
    flow, http, calls = _flow((403, {"detail": refusal}))
    result = FlowResult(flow_name="onboarding-seam")
    assert flow._provision_the_decision(
        result, ONBOARDING, {"id": "o", "dataset_count": 1}
    )
    assert _step(result, "a plain service does not register consent").status == "PASS"
    http.bearer_headers_for.assert_called_with(
        flow.settings.provider_org_client_id, flow.settings.provider_org_client_secret
    )
    [(_, refused), (headers, written)] = calls
    assert "decided_by" not in refused
    assert headers == ORG and written["decided_by"] == "collector"


@pytest.mark.parametrize(
    "first",
    [(200, [{"id": "c1"}]), (403, {"detail": "the dataset is unknown"}), (500, {})],
    ids=["accepted", "refused-for-another-reason", "server-error"],
)
def test_anything_but_the_organisation_refusal_fails(first):
    flow, _, _ = _flow(first)
    result = FlowResult(flow_name="onboarding-seam")
    assert not flow._provision_the_decision(
        result, ONBOARDING, {"id": "o", "dataset_count": 1}
    )
    assert _step(result, "a plain service does not register consent").status == "FAIL"
