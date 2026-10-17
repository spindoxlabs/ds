"""Which row filter the PDP puts on the wire, by what it binds (celine-utils REQ-0010).

A consent-gated dataset sends its filter binding a person: the decision has one
`row_filter` slot, and an organization filter names no data subject to narrow by.
A dataset that is **not** consent-gated sends its filter binding an organization, with
nobody in it, so the agreement does not serve every organization's rows; a data plane
that cannot apply it refuses.
"""

from __future__ import annotations

import pytest
from ds.governance.models import GovernanceRuleV2

from connector.api.v1 import internal

PERSON = {"handler": "rec_registry", "args": {"column": "device_id"}}
ORGANIZATION = {
    "handler": "organization_match",
    "binds": "organization",
    "args": {"column": "rec_id"},
}


def _spec(*filters: dict):
    return internal._row_filter_spec(
        GovernanceRuleV2.model_validate({"row_filters": list(filters)})
    )


@pytest.mark.rule("D-15")
def test_the_person_filter_is_sent_whatever_its_position():
    assert _spec(ORGANIZATION, PERSON) == {
        "handler": "rec_registry",
        "args": {"column": "device_id"},
    }


@pytest.mark.rule("D-15")
def test_an_organization_filter_is_never_the_person_filter():
    assert _spec(ORGANIZATION) is None
    assert _spec({"handler": "member_wide", "binds": "organization"}) is None


def _organization_spec(*filters: dict):
    return internal._organization_filter_spec(
        GovernanceRuleV2.model_validate({"row_filters": list(filters)})
    )


@pytest.mark.rule("X-5")
def test_the_organization_filter_is_found_whatever_its_position():
    assert _organization_spec(PERSON, ORGANIZATION) == {
        "handler": "organization_match",
        "args": {"column": "rec_id"},
    }


@pytest.mark.rule("X-5")
def test_of_several_organization_filters_the_first_is_sent():
    """Filters AND, and a PEP refuses any one it cannot apply: one is enough."""
    wide = {"handler": "member_wide", "binds": "organization"}
    assert _organization_spec(ORGANIZATION, wide)["handler"] == "organization_match"
    assert _organization_spec(wide, ORGANIZATION)["handler"] == "member_wide"


@pytest.mark.rule("X-5")
def test_a_person_filter_is_never_the_organization_filter():
    assert _organization_spec(PERSON) is None
    assert _organization_spec() is None
