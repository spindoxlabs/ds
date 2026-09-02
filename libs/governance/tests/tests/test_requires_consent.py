"""`requires_consent` — one predicate deciding whether a dataset is consent-gated.

It had two implementations. The mapper's decided whether the published offer
carries a consent constraint; `matrix.py`'s decided whether the compliance
report called the dataset gated. They differed by one clause — the matrix
included `classification == "pii"` and the mapper did not — so a `pii` dataset
with no filter and no `consent.required` was **reported gated and published
ungated**, the divergence pointing the wrong way.

`matrix.py` has since been deleted (nothing consumed it). The predicate stays,
because the `pii` clause is the half that was live: it changes what goes on the
wire, and `pii` is the rulebook's own switch — *"`classification: pii` on a
dataset is the switch. A dataset carrying that classification is subject to
everything on this page"* (Rulebook · Personal data).
"""

from __future__ import annotations

import pytest

from ds.governance.mapper import GovernanceMapper, requires_consent
from ds.governance.models import (
    DataspaceSpec,
    GovernanceRuleV2,
    OdrlProfile,
    RowFilter,
    RowFilterArgs,
)

PARTICIPANT = "rec"
BASE_URL = "https://rec.dataspaces.localhost"

_P = OdrlProfile()


def _mapper(**kwargs) -> GovernanceMapper:
    return GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL, **kwargs)


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def _consent_constraints(offer: dict) -> list[dict]:
    return [
        c
        for perm in offer.get("odrl:permission", [])
        for c in perm.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == _P.term(_P.consent_operand)
    ]


@pytest.mark.parametrize(
    "rule,expected",
    [
        (_rule(), False),
        (_rule(dataspace=DataspaceSpec(consent_required=True)), True),
        (_rule(user_filter_column="subject_did"), True),
        (
            _rule(
                row_filters=[
                    RowFilter(handler="subject", args=RowFilterArgs(column="did"))
                ]
            ),
            True,
        ),
        # The clause the two implementations disagreed on.
        (_rule(classification="pii"), True),
    ],
    ids=["plain", "declared", "user-filter", "row-filter", "pii"],
)
def test_predicate(rule, expected):
    assert requires_consent(rule) is expected


@pytest.mark.parametrize(
    "rule,expected",
    [
        (_rule(), False),
        (_rule(dataspace=DataspaceSpec(consent_required=True)), True),
        (_rule(user_filter_column="subject_did"), True),
        (_rule(classification="pii"), True),
    ],
    ids=["plain", "declared", "user-filter", "pii"],
)
def test_the_offer_follows_the_predicate(rule, expected):
    """Whatever the predicate says, the published offer must carry."""
    offer = _mapper().to_odrl_offer("datasets.gold.meters", rule)
    assert bool(_consent_constraints(offer)) is expected


def test_pii_dataset_is_gated_in_the_published_offer():
    """A `pii` dataset with no filter and no declaration used to publish ungated."""
    offer = _mapper().to_odrl_offer("datasets.gold.meters", _rule(classification="pii"))
    assert _consent_constraints(offer)
    # And the duty that goes with the constraint.
    assert any(
        duty["odrl:action"]["@id"] == "odrl:obtainConsent"
        for perm in offer["odrl:permission"]
        for duty in perm.get("odrl:duty", [])
    )


def test_the_consent_operand_comes_from_the_profile():
    """Not a literal `ds:consentStatus` — that form is what the drift was made of."""
    other = OdrlProfile(
        prefix="acme",
        namespace="https://acme.example/ns/",
        consent_operand="Permission",
    )
    offer = _mapper(profile=other).to_odrl_offer(
        "datasets.gold.meters",
        _rule(dataspace=DataspaceSpec(consent_required=True)),
    )
    operands = {
        c.get("odrl:leftOperand", {}).get("@id")
        for perm in offer["odrl:permission"]
        for c in perm.get("odrl:constraint", [])
    }
    assert other.term("Permission") in operands
    assert "ds:consentStatus" not in operands


def test_a_pii_dataset_without_a_filter_still_warns():
    """Gating it does not make the gate enforceable — that stays a separate defect.

    `check_consent_coherence` warns *"classified 'pii' but declares no row-level
    filtering"*, because a consent gate with no per-subject column cannot be
    evaluated per subject. The offer no longer under-claims; the warning still
    names what is missing.
    """
    from ds.governance.compliance.checks import (
        ValidationResult,
        check_consent_coherence,
    )

    class _Item:
        key = "datasets.gold.meters"
        rule = _rule(classification="pii")

    result = ValidationResult(governance_path="x")
    check_consent_coherence(result, [_Item()])
    assert any("pii" in str(w) for w in result.warnings)
