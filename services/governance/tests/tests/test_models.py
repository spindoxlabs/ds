"""Tests for GovernanceRule v1/v2 model parsing and defaults."""
import pytest

from ds.governance.models import (
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRule,
    GovernanceRuleV2,
    PolicyConsent,
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
