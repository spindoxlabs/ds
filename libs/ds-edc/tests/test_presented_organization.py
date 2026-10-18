"""`ContractNegotiationEvent.presented_organization_*` — what the extension forwards.

`NegotiationEventPublisher` sends `presentedOrganization` with two lists. The
connector decides what they mean; this only reads them, and anything that is not
a list of strings reads as nothing rather than as a value.
"""

from __future__ import annotations

from ds_edc.webhooks import ContractNegotiationEvent


def _event(presented) -> ContractNegotiationEvent:
    payload = {"contractAgreementId": "agr-1"}
    if presented is not None:
        payload["presentedOrganization"] = presented
    return ContractNegotiationEvent(
        type="CONTRACT_NEGOTIATION_FINALIZED", payload=payload
    )


def test_the_lists_are_read():
    event = _event({"organizationId": ["example-org"], "organizationType": ["rec"]})
    assert event.presented_organization_ids == ["example-org"]
    assert event.presented_organization_types == ["rec"]


def test_duplicates_collapse_and_order_is_kept():
    event = _event({"organizationId": ["b-org", "a-org", "b-org"]})
    assert event.presented_organization_ids == ["b-org", "a-org"]


def test_an_older_extension_forwards_nothing():
    event = _event(None)
    assert event.presented_organization_ids == []
    assert event.presented_organization_types == []


def test_a_malformed_field_reads_as_nothing():
    assert _event("example-org").presented_organization_ids == []
    assert _event({"organizationId": "example-org"}).presented_organization_ids == []
    assert _event({"organizationId": [1, "", None]}).presented_organization_ids == []
