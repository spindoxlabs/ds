"""Tests for GovernanceRule v1/v2 model parsing and defaults."""
import logging

import pytest

from ds.governance.models import (
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRule,
    GovernanceRuleV2,
    OdrlProfile,
    PolicyConsent,
    load_odrl_profile,
    profile_path_is_missing,
)


def test_v1_rule_loads_with_defaults():
    rule = GovernanceRule(access_level="open", classification="green")
    assert rule.access_level == "open"
    assert rule.classification == "green"
    assert rule.tags == []
    assert rule.user_filter_column is None


def test_v2_rule_has_safe_defaults():
    rule = GovernanceRuleV2()
    assert rule.policy == DataspacePolicy()
    assert rule.dataspace == DataspaceSpec()
    assert rule.policy.consent.required is False


def test_v2_consent_auto_schema():
    """Consent model fields are correct."""
    consent = PolicyConsent(required=True, scope="per_subject", on_revocation="terminate")
    assert consent.required is True
    assert consent.scope == "per_subject"
    assert consent.on_revocation == "terminate"


def test_v2_rule_inherits_v1_fields():
    rule = GovernanceRuleV2(
        title="My Dataset",
        access_level="restricted",
        classification="pii",
        user_filter_column="sub",
        tags=["rec", "meters"],
    )
    assert rule.title == "My Dataset"
    assert rule.user_filter_column == "sub"
    assert "rec" in rule.tags


def test_dataspace_spec_defaults():
    spec = DataspaceSpec()
    assert spec.expose is False
    assert spec.data_address.base_url == "http://dataset-api:30002"
    assert spec.data_address.proxy_path is True


# ── OdrlProfile loading ──────────────────────────────────────────────────────

def test_load_default_profile():
    profile = load_odrl_profile()
    assert profile.namespace == "https://w3id.org/dsp/policy/"
    assert "meters" in profile.tag_to_purpose
    assert profile.tag_to_purpose["meters"] == "EnergyCommunityOperation"
    assert {c.slug for c in profile.purposes} == {
        "EnergyCommunityOperation",
        "IncentiveCalculation",
        "CostOptimization",
        "FlexibilityResearch",
        "GridMonitoring",
        "GridResilience",
        "EnergyForecasting",
        "EnergyPlanning",
        "PVPotentialAssessment",
    }


@pytest.mark.rule("A-2", "M-13")
def test_default_profile_roots_are_not_mutually_reachable():
    """The five roots must stay siblings — `is_a` must not cross between them.

    `is_a` walks the local `broader` chain upward, so a consent recorded at one
    root would cover every request under it. Grid monitoring and grid resilience
    are the pair most likely to be "tidied" into a parent/child later: observing
    the network and acting on infrastructure risk are different reasons, and
    making resilience narrower would let a monitoring consent admit a resilience
    request. This test is what makes that a deliberate decision rather than a
    refactor.
    """
    profile = load_odrl_profile()
    roots = [
        "EnergyCommunityOperation",
        "GridMonitoring",
        "GridResilience",
        "EnergyForecasting",
        "EnergyPlanning",
    ]
    for concept in roots:
        assert profile.purpose_index[concept].broader is None
    for requested in roots:
        for consented in roots:
            if requested == consented:
                continue
            assert not profile.is_a(requested, consented), (
                f"{requested} must not satisfy a consent for {consented}"
            )


@pytest.mark.rule("A-1", "M-13")
def test_default_profile_children_are_covered_by_their_root():
    """Consent to a root covers a narrower request, never the reverse."""
    profile = load_odrl_profile()
    for child, root in (
        ("IncentiveCalculation", "EnergyCommunityOperation"),
        ("CostOptimization", "EnergyCommunityOperation"),
        ("FlexibilityResearch", "EnergyCommunityOperation"),
        ("PVPotentialAssessment", "EnergyPlanning"),
    ):
        assert profile.is_a(child, root)
        assert not profile.is_a(root, child)


@pytest.mark.rule("M-13")
def test_default_profile_dpv_mappings_are_dpv_iris():
    """Every concept declares an alignment, and it points at DPV.

    `check_purpose_taxonomy` only asserts the IRI is absolute and the relation is
    a SKOS match property, so a plausible-looking IRI from anywhere passes. The
    alignments and the reasoning behind each are in `docs/taxonomies/dpv-2.3.md`.
    """
    profile = load_odrl_profile()
    for concept in profile.purposes:
        assert concept.dpv_mapping is not None, f"{concept.slug} declares no alignment"
        assert concept.dpv_mapping.iri.startswith("https://w3id.org/dpv#")
        # Never exactMatch: DPV is domain-neutral and has no energy vocabulary,
        # so every concept here is narrower than the term it cites.
        assert concept.dpv_mapping.relation == "broadMatch"


def test_load_profile_from_yaml(tmp_path):
    p = tmp_path / "mfg-profile.yaml"
    p.write_text("""\
namespace: "https://example.org/mfg/"
prefix: "mfg"
tag_to_purpose:
  quality: QualityAssurance
purposes:
  - slug: QualityAssurance
    label: Quality Assurance
    definition: Ensuring product quality standards.
""")
    profile = load_odrl_profile(p)
    assert profile.namespace == "https://example.org/mfg/"
    assert profile.prefix == "mfg"
    assert profile.tag_to_purpose == {"quality": "QualityAssurance"}
    assert len(profile.purposes) == 1
    assert profile.purposes[0].slug == "QualityAssurance"


def test_load_profile_missing_path_falls_back_to_default():
    profile = load_odrl_profile("/nonexistent/path.yaml")
    assert profile.namespace == "https://w3id.org/dsp/policy/"
    assert "meters" in profile.tag_to_purpose


def test_configured_but_missing_profile_path_warns(caplog):
    """The fallback is invisible otherwise, and now expensive.

    A typo'd path yields the *platform* vocabulary, so every purpose the deployer
    declared fails to resolve — and the sync gate then refuses to publish any of
    their datasets. At `debug` nothing would explain that.
    """
    with caplog.at_level(logging.WARNING, logger="ds.governance.models"):
        load_odrl_profile("/nonexistent/path.yaml")
    assert any("falling back to the bundled energy profile" in r.message for r in caplog.records)


@pytest.mark.rule("M-13")
def test_default_profile_load_does_not_warn(caplog):
    """Using the bundled profile is the documented default, not a misconfiguration."""
    with caplog.at_level(logging.WARNING, logger="ds.governance.models"):
        load_odrl_profile()
    assert caplog.records == []


def test_profile_path_is_missing_only_flags_configured_paths():
    assert profile_path_is_missing("/nonexistent/path.yaml") is True
    assert profile_path_is_missing(None) is False
    assert profile_path_is_missing("") is False
