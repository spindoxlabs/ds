"""Every flow resolves a person by ``POST /users/resolve``, never ``GET ?email=``.

An email in a query string is recorded by every access log, proxy and trace on
the path, and the identity registry withdraws the GET form (410 outside dev
after its sunset). The flows share one helper, `BaseFlow._resolve_user`, so
these tests pin it and pin that no flow sources still build the old URL.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.fail_closed import FailClosedFlow
from ds_e2e.flows.recipient_restriction import RecipientRestrictionFlow
from ds_e2e.flows.two_providers import TwoProvidersFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult

EMAIL = "member+tag@example.org"


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _flow(settings: E2ESettings, cls: type = RecipientRestrictionFlow):
    http = MagicMock(spec=HttpClient)
    return cls(settings, http), http


def test_resolve_posts_the_email_in_the_body(settings):
    flow, http = _flow(settings)
    http.post.return_value = {"vc_jws": "vc"}

    assert flow._resolve_user(EMAIL, {"Authorization": "Bearer t"}) == {"vc_jws": "vc"}

    http.get.assert_not_called()
    http.post.assert_called_once_with(
        f"{settings.identity_registry_url}/users/resolve",
        {"email": EMAIL},
        headers={"Authorization": "Bearer t"},
    )
    url = http.post.call_args.args[0]
    assert "?" not in url and "@" not in url


@pytest.mark.parametrize("answer", [None, "", [], "not-json"])
def test_an_empty_or_non_object_answer_reads_as_no_mapping(settings, answer):
    flow, http = _flow(settings)
    http.post.return_value = answer
    assert flow._resolve_user(EMAIL, {}) == {}


def test_resolve_user_vc_returns_the_newest_vc(settings):
    flow, http = _flow(settings)
    http.post.return_value = {"vc_jws": "eyJ.vc", "credentials": []}
    assert flow._resolve_user_vc(EMAIL, {}) == "eyJ.vc"


def test_resolve_user_vc_without_a_vc_raises(settings):
    flow, http = _flow(settings)
    http.post.return_value = {"did": "did:web:example.org:users:ex-00001"}
    with pytest.raises(RuntimeError, match="No VC found"):
        flow._resolve_user_vc(EMAIL, {})


def test_a_registry_error_propagates(settings):
    flow, http = _flow(settings)
    http.post.side_effect = RuntimeError("404 No mapping found")
    with pytest.raises(RuntimeError, match="404"):
        flow._resolve_user_vc(EMAIL, {})


@pytest.mark.parametrize(
    "cls, method",
    [
        (RecipientRestrictionFlow, "_consumer_credential"),
        (TwoProvidersFlow, "_consumer_credential"),
    ],
)
def test_consumer_credential_callers_use_the_post(settings, cls, method):
    flow, http = _flow(settings, cls)
    http.bearer_headers.return_value = {"Authorization": "Bearer t"}
    http.post.return_value = {"vc_jws": "vc"}

    assert getattr(flow, method)(FlowResult(flow_name="t")) == "vc"

    http.get.assert_not_called()
    assert http.post.call_args.args == (
        f"{settings.identity_registry_url}/users/resolve",
        {"email": settings.consumer_email},
    )


def test_fail_closed_consumer_headers_use_the_post(settings):
    flow, http = _flow(settings, FailClosedFlow)
    http.bearer_headers.return_value = {"Authorization": "Bearer t"}
    http.post.return_value = {}

    assert flow._consumer_headers(FlowResult(flow_name="t")) is None

    http.get.assert_not_called()
    assert http.post.call_args.args[1] == {"email": settings.consumer_email}


def test_no_flow_builds_the_query_form():
    flows = Path(__file__).resolve().parents[1] / "src" / "ds_e2e" / "flows"
    offenders = [
        p.name for p in flows.glob("*.py") if "users/resolve?" in p.read_text()
    ]
    assert offenders == []
