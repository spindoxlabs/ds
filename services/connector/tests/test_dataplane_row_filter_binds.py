"""The PDP puts only a filter binding a person on the wire (celine-utils REQ-0010).

An organization filter is the provider platform's own access control: the data plane
refuses it on a delegated request, so sending it with the consenting subjects would
serve no rows — and it names no data subject to narrow by.
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
def test_an_organization_filter_alone_is_never_sent():
    assert _spec(ORGANIZATION) is None
    assert _spec({"handler": "member_wide", "binds": "organization"}) is None
