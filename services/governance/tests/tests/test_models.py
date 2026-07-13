"""Tests for GovernanceRule v1/v2 model parsing and defaults."""
import pytest

from ds.governance.models import (
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRule,
    GovernanceRuleV2,
    OdrlProfile,
    PolicyConsent,
    load_odrl_profile,
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
    assert "rec" in profile.tag_to_purpose
    assert profile.tag_to_purpose["rec"] == "EnergyBalancing"
    assert len(profile.purposes) == 3


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
    assert "rec" in profile.tag_to_purpose
