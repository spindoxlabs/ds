"""A consumer's declared intent: extraction, validation, refusal.

Two properties are under test, and they fail in opposite directions:

- ``_extract_purposes`` must read *every* purpose an offer permits. Missing one
  understates what the offer allows and, worse, silently empties the check the
  declaration is validated against.
- ``_validated_declaration`` must refuse anything the offer does not permit.
  A declaration recorded without that check is an unverified claim sitting in an
  audit record, which later reads as a verified one.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from connector.api.v1.consumer import (
    NegotiateRequest,
    _extract_purposes,
    _validated_declaration,
)

IRI = "https://w3id.org/dsp/policy/purpose/"


def _policy(operator: str, right) -> dict:
    return {
        "odrl:permission": [
            {
                "odrl:action": {"@id": "odrl:use"},
                "odrl:constraint": [
                    {
                        "odrl:leftOperand": {"@id": "odrl:purpose"},
                        "odrl:operator": {"@id": operator},
                        "odrl:rightOperand": right,
                    }
                ],
            }
        ]
    }


def _request(**kwargs) -> NegotiateRequest:
    return NegotiateRequest(
        counter_party_address="http://provider/protocol",
        offer_id="offer-1",
        asset_id="datasets.silver.meters",
        assigner="did:web:provider.dataspaces.localhost",
        **kwargs,
    )


# ── reading the offer's purposes ─────────────────────────────────────────────


def test_single_valued_isa_is_read():
    policy = _policy("odrl:isA", {"@id": f"{IRI}FlexibilityResearch"})
    assert _extract_purposes(policy) == [f"{IRI}FlexibilityResearch"]


def test_multi_valued_isanyof_is_read():
    """The regression this module exists for.

    A multi-purpose dataset is published as one ``isAnyOf`` constraint over a
    list — the shape the ODRL Information Model prescribes for set-based
    operators. Reading only the scalar form returned an empty list for exactly
    the datasets whose purpose is ambiguous.
    """
    policy = _policy(
        "odrl:isAnyOf",
        [
            {"@id": f"{IRI}EnergyCommunityOperation"},
            {"@id": f"{IRI}IncentiveCalculation"},
            {"@id": f"{IRI}FlexibilityResearch"},
        ],
    )
    assert _extract_purposes(policy) == [
        f"{IRI}EnergyCommunityOperation",
        f"{IRI}IncentiveCalculation",
        f"{IRI}FlexibilityResearch",
    ]


def test_expanded_left_operand_is_read():
    """ODRL's context expands ``odrl:purpose``; the catalogue may serve either."""
    policy = {
        "odrl:permission": [
            {
                "odrl:constraint": [
                    {
                        "odrl:leftOperand": {
                            "@id": "http://www.w3.org/ns/odrl/2/purpose"
                        },
                        "odrl:operator": {"@id": "odrl:isA"},
                        "odrl:rightOperand": {"@id": f"{IRI}GridMonitoring"},
                    }
                ]
            }
        ]
    }
    assert _extract_purposes(policy) == [f"{IRI}GridMonitoring"]


def test_other_operands_are_not_purposes():
    policy = _policy("odrl:eq", "true")
    policy["odrl:permission"][0]["odrl:constraint"][0]["odrl:leftOperand"] = {
        "@id": "ds:contractRequired"
    }
    assert _extract_purposes(policy) == []


# ── validating the declaration ───────────────────────────────────────────────


def test_no_declaration_is_allowed():
    """Declaring is optional — silence is recorded as silence, not as consent."""
    assert _validated_declaration(_request()) == []


def test_declared_purpose_within_the_offer_is_accepted():
    req = _request(
        declared_purpose=[f"{IRI}FlexibilityResearch"],
        odrl_policy=_policy(
            "odrl:isAnyOf",
            [
                {"@id": f"{IRI}EnergyCommunityOperation"},
                {"@id": f"{IRI}FlexibilityResearch"},
            ],
        ),
    )
    assert _validated_declaration(req) == ["FlexibilityResearch"]


def test_narrower_purpose_than_the_offer_names_is_accepted():
    """``odrl:isA`` over the local ``broader`` chain.

    ``FlexibilityResearch`` is narrower than ``EnergyCommunityOperation``, so an
    offer permitting the broader purpose permits the narrower declaration. The
    reverse must not hold — see the next test.
    """
    req = _request(
        declared_purpose=["FlexibilityResearch"],
        odrl_policy=_policy(
            "odrl:isA", {"@id": f"{IRI}EnergyCommunityOperation"}
        ),
    )
    assert _validated_declaration(req) == ["FlexibilityResearch"]


def test_broader_purpose_than_the_offer_permits_is_refused():
    req = _request(
        declared_purpose=["EnergyCommunityOperation"],
        odrl_policy=_policy("odrl:isA", {"@id": f"{IRI}FlexibilityResearch"}),
    )
    with pytest.raises(HTTPException) as exc:
        _validated_declaration(req)
    assert exc.value.status_code == 422
    assert "not permitted by this offer" in exc.value.detail


def test_unknown_purpose_is_refused():
    req = _request(
        declared_purpose=["SellingItOn"],
        odrl_policy=_policy("odrl:isA", {"@id": f"{IRI}FlexibilityResearch"}),
    )
    with pytest.raises(HTTPException) as exc:
        _validated_declaration(req)
    assert exc.value.status_code == 422
    assert "not in the ODRL profile taxonomy" in exc.value.detail


def test_declaration_without_a_policy_is_refused():
    """Nothing to check against means the claim cannot be verified.

    Recording it anyway would put an unverified assertion in the audit record,
    indistinguishable later from one the offer actually permitted.
    """
    req = _request(declared_purpose=["FlexibilityResearch"])
    with pytest.raises(HTTPException) as exc:
        _validated_declaration(req)
    assert exc.value.status_code == 422
    assert "requires odrl_policy" in exc.value.detail


def test_justification_ref_rejects_an_email():
    with pytest.raises(ValidationError):
        _request(justification_ref="analyst@example.test")


def test_justification_ref_accepts_an_opaque_reference():
    assert _request(justification_ref="TICKET-4417").justification_ref == "TICKET-4417"
