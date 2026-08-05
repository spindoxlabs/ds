"""Tests for the compliance matrix — the report, against the offer it describes.

**This module had no tests**, which is the reason the defect below survived.

`build_policy_matrix_entry` sorts an offer's constraints into two buckets — what
the EDC policy engine enforces, and what this platform's own services enforce —
and it did that against a hand-written list of operand names. Two of the four
names were terms the mapper has never emitted:

    matrix said            mapper emits
    ds:accessScope         {namespace}Membership   (profile.membership_operand)
    ds:consentStatus       {namespace}ConsentStatus (profile.consent_operand)
    ds:contractRequired    ds:contractRequired      ✓
    odrl:purpose           odrl:purpose             ✓

Every operand built through `profile.term()` was missing and every hardcoded one
was present, so the matrix reported **no membership and no consent constraint on
any dataset** while EDC enforced both. Nothing was wrong with either side on its
own: the report was internally consistent, the offer was correct, and the two
were about different vocabularies.

**Scope, stated honestly:** nothing in this repository consumes the matrix right
now. `GET /governance/matrix` was removed as an over-broad disclosure and the
`evidence` command does not emit it, so this was a latent defect in an exported
API rather than a wrong report anyone read. It is fixed here because
`build_policy_matrix` is public, is the documented starting point for rebuilding
that route, and would have carried the defect into whatever consumed it next.

The tests here are therefore mostly *agreement* tests, and the one that matters
most is `test_every_emitted_operand_is_classified` — it fails when a new
constraint is emitted and classified nowhere, which is the general form of the
defect rather than the instance.
"""
from __future__ import annotations

import pytest

from ds.governance.mapper import GovernanceMapper
from ds.governance.matrix import build_policy_matrix, build_policy_matrix_entry
from ds.governance.models import (
    DataspacePolicy,
    GovernanceRuleV2,
    OdrlProfile,
    PolicyConsent,
    PurposeConcept,
    RowFilter,
    RowFilterArgs,
)

PARTICIPANT = "rec"
BASE_URL = "https://rec.dataspaces.localhost"

_P = OdrlProfile()

# A second profile, to prove the buckets follow the profile rather than a literal.
_OTHER = OdrlProfile(
    prefix="acme",
    namespace="https://acme.example/ns/",
    membership_operand="Belonging",
    consent_operand="Permission",
    purposes=[PurposeConcept(slug="Research", label="Research")],
)


def _mapper(**kwargs) -> GovernanceMapper:
    return GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL, **kwargs)


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def _edc_operands(entry: dict) -> list[str]:
    return [c["left_operand"] for c in entry["edc_policy"]["enforced_constraints"]]


def _connector_operands(entry: dict) -> list[str]:
    return [c["left_operand"] for c in entry["connector_enforcement"]["constraints"]]


# ── The membership constraint reaches the report ─────────────────────────────


class TestMembershipIsReported:
    def test_internal_dataset_reports_its_membership_constraint(self):
        mapper = _mapper()
        entry = build_policy_matrix_entry(
            "datasets.gold.meters", _rule(access_level="internal"), mapper
        )
        assert _P.term(_P.membership_operand) in _edc_operands(entry)

    def test_the_bucket_follows_the_profile(self):
        """A deployment with its own profile gets its own operand reported."""
        mapper = _mapper(profile=_OTHER)
        entry = build_policy_matrix_entry(
            "datasets.gold.meters", _rule(access_level="internal"), mapper
        )
        reported = _edc_operands(entry)
        assert _OTHER.term("Belonging") in reported
        # And emphatically not the retired literal the matrix used to name.
        assert "ds:accessScope" not in reported


class TestConsentIsReported:
    def test_consent_constraint_reaches_the_connector_bucket(self):
        mapper = _mapper()
        rule = _rule(policy=DataspacePolicy(consent=PolicyConsent(required=True)))
        entry = build_policy_matrix_entry("datasets.gold.meters", rule, mapper)
        assert _P.term(_P.consent_operand) in _connector_operands(entry)

    def test_the_bucket_follows_the_profile(self):
        mapper = _mapper(profile=_OTHER)
        rule = _rule(policy=DataspacePolicy(consent=PolicyConsent(required=True)))
        entry = build_policy_matrix_entry("datasets.gold.meters", rule, mapper)
        reported = _connector_operands(entry)
        assert _OTHER.term("Permission") in reported
        assert "ds:consentStatus" not in reported


# ── The general form: nothing is emitted into a bucket that does not exist ────


def _all_kinds_rule() -> GovernanceRuleV2:
    """One rule that exercises every constraint the mapper knows how to emit."""
    return _rule(
        access_level="restricted",  # membership + contract gate
        classification="pii",
        tags=["meters"],  # purpose, via the profile's tag map
        user_filter_column="subject_did",  # consent
        policy=DataspacePolicy(consent=PolicyConsent(required=True)),
    )


class TestEveryOperandIsClassified:
    """The guard, not the instance.

    A constraint the mapper emits and the matrix classifies nowhere disappears
    from the compliance report without any test failing — which is exactly what
    happened. This asserts the classification is *exhaustive*, so the next
    operand added has to declare where it is enforced.
    """

    @pytest.mark.parametrize("profile", [_P, _OTHER], ids=["default", "custom"])
    def test_every_emitted_operand_is_classified(self, profile):
        mapper = _mapper(profile=profile)
        entry = build_policy_matrix_entry(
            "datasets.gold.meters", _all_kinds_rule(), mapper
        )
        emitted = {c["left_operand"] for c in entry["odrl_constraints"]}
        classified = mapper.edc_enforced_operands | mapper.connector_enforced_operands
        assert emitted, "the fixture must emit at least one constraint"
        assert emitted <= classified, (
            f"emitted but classified nowhere: {sorted(emitted - classified)} — "
            f"add it to GovernanceMapper.edc_enforced_operands or "
            f".connector_enforced_operands"
        )

    def test_the_two_buckets_do_not_overlap(self):
        mapper = _mapper()
        assert not (
            mapper.edc_enforced_operands & mapper.connector_enforced_operands
        ), "an operand enforced in two places makes the report ambiguous"

    def test_nothing_emitted_falls_out_of_both_buckets(self):
        """Every emitted constraint appears in exactly one reported bucket."""
        mapper = _mapper()
        entry = build_policy_matrix_entry(
            "datasets.gold.meters", _all_kinds_rule(), mapper
        )
        emitted = [c["left_operand"] for c in entry["odrl_constraints"]]
        reported = _edc_operands(entry) + _connector_operands(entry)
        assert sorted(emitted) == sorted(reported)


# ── `requires_consent`: one predicate, two readers ───────────────────────────


class TestConsentAgreement:
    """What the report claims and what the offer carries must be one decision."""

    @pytest.mark.parametrize(
        "rule,expected",
        [
            (_rule(), False),
            (_rule(policy=DataspacePolicy(consent=PolicyConsent(required=True))), True),
            (_rule(user_filter_column="subject_did"), True),
            (
                _rule(
                    row_filters=[
                        RowFilter(handler="subject", args=RowFilterArgs(column="did"))
                    ]
                ),
                True,
            ),
            # The divergence this fixes: reported gated, published ungated.
            (_rule(classification="pii"), True),
        ],
        ids=["plain", "declared", "user-filter", "row-filter", "pii"],
    )
    def test_report_and_offer_agree(self, rule, expected):
        mapper = _mapper()
        entry = build_policy_matrix_entry("datasets.gold.meters", rule, mapper)
        offer_has_consent = _P.term(_P.consent_operand) in {
            c["left_operand"] for c in entry["odrl_constraints"]
        }
        assert entry["consent"]["required"] is expected
        assert offer_has_consent is expected

    def test_pii_dataset_is_gated_in_the_published_offer(self):
        """The rulebook's switch: `classification: pii` makes it personal data.

        A `pii` dataset with no filter and no `consent.required` used to publish
        an offer with no consent term while the report said it was gated. The
        report was right — the rulebook's Personal data page makes `pii` the
        switch for everything on it.
        """
        mapper = _mapper()
        rule = _rule(classification="pii")
        offer = mapper.to_odrl_offer("datasets.gold.meters", rule)
        constraints = [
            c
            for perm in offer["odrl:permission"]
            for c in perm.get("odrl:constraint", [])
        ]
        assert any(
            c["odrl:leftOperand"]["@id"] == _P.term(_P.consent_operand)
            for c in constraints
        )
        # And the duty that goes with it.
        assert any(
            duty["odrl:action"]["@id"] == "odrl:obtainConsent"
            for perm in offer["odrl:permission"]
            for duty in perm.get("odrl:duty", [])
        )


def test_matrix_is_sorted_by_dataset_key():
    mapper = _mapper()
    rules = {"b.two": _rule(), "a.one": _rule()}
    assert [e["dataset_key"] for e in build_policy_matrix(rules, mapper)] == [
        "a.one",
        "b.two",
    ]
