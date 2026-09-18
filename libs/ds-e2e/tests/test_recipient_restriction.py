"""The reasoning that turns an observation into a verdict, for the access policy.

The live half needs a running exchange. What can be tested here is the half that
was wrong in every flow this suite has had to repair: **which side refused**, and
whether an observation is allowed to stand in for a decision it does not prove.

Two asymmetries are deliberate and both are pinned below:

- On the **positive** half, our own connector declining to open the negotiation
  is a `FAIL`. The provider never answered, so there is nothing to conclude —
  the same trap `fail-closed` names as `not-started`.
- On the **negative** half, the same local refusal is a `PASS`, because there it
  *is* the observation: an offer id is the provider's to mint and must match the
  policy it carries, so a consumer excluded from the catalogue cannot form the
  request at all. The step says that rather than claiming the provider refused.

The provider-side negative is the catalogue step, and it is asserted before
either negotiation: filtering a *published* dataset out of a catalogue is
something only the access policy can do.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.recipient_restriction import RecipientRestrictionFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _flow(settings) -> RecipientRestrictionFlow:
    return RecipientRestrictionFlow(settings, MagicMock(spec=HttpClient))


def _last(result: FlowResult):
    return result.steps[-1]


# ── the catalogue, which is the provider-side assertion ──────────────────────


def test_a_recipient_missing_from_its_own_catalogue_fails(settings):
    """The control. Without it, "hidden" and "nothing was published" are one."""
    result = FlowResult(flow_name="recipient-restriction")
    assert (
        _flow(settings)._assert_visible(result, {"something.else"}, "datasets.a")
        is False
    )
    assert _last(result).status == "FAIL"


def test_a_restricted_dataset_in_the_catalogue_fails(settings):
    result = FlowResult(flow_name="recipient-restriction")
    assert (
        _flow(settings)._assert_hidden(result, {"datasets.b"}, "datasets.b") is False
    )
    assert _last(result).status == "FAIL"


def test_the_two_directions_pass_together(settings):
    flow = _flow(settings)
    result = FlowResult(flow_name="recipient-restriction")
    published = {"datasets.a"}
    assert flow._assert_visible(result, published, "datasets.a") is True
    assert flow._assert_hidden(result, published, "datasets.b") is True
    assert [s.status for s in result.steps] == ["PASS", "PASS"]


# ── which side refused ───────────────────────────────────────────────────────


def test_a_local_refusal_fails_the_positive_half(settings):
    """`not-started` proves nothing about the provider's policy."""
    flow = _flow(settings)
    flow._negotiate = MagicMock(return_value=None)
    result = FlowResult(flow_name="recipient-restriction")

    flow._assert_negotiable(result, {}, [], "datasets.a")
    assert _last(result).status == "FAIL"
    assert "own connector" in _last(result).detail


def test_a_provider_refusal_fails_the_positive_half(settings):
    """A named recipient being refused a contract is the failure this half exists
    for — and it must not be confused with the negative half passing."""
    flow = _flow(settings)
    flow._negotiate = MagicMock(return_value="neg-1")
    flow._settle = MagicMock(return_value={"state": "TERMINATED"})
    result = FlowResult(flow_name="recipient-restriction")

    flow._assert_negotiable(result, {}, [], "datasets.a")
    assert _last(result).status == "FAIL"


def test_a_local_refusal_passes_the_negative_half_and_says_what_it_saw(settings):
    flow = _flow(settings)
    flow._negotiate = MagicMock(return_value=None)
    result = FlowResult(flow_name="recipient-restriction")

    flow._assert_no_usable_offer(result, {}, "datasets.b")
    assert _last(result).status == "PASS"
    assert "offer id" in _last(result).detail


def test_an_agreement_for_a_restricted_dataset_fails(settings):
    """The one outcome that means the restriction is not enforced."""
    flow = _flow(settings)
    flow._negotiate = MagicMock(return_value="neg-2")
    flow._settle = MagicMock(return_value={"contractAgreementId": "agr-1"})
    result = FlowResult(flow_name="recipient-restriction")

    flow._assert_no_usable_offer(result, {}, "datasets.b")
    assert _last(result).status == "FAIL"


def test_the_two_assets_are_different_by_default(settings):
    """One dataset proves nothing: a restriction that hides everything and one
    that hides nothing both pass a single-dataset check."""
    assert settings.recipient_asset_id != settings.non_recipient_asset_id
