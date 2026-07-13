"""Tests for DCAT → EDC mapper."""
from __future__ import annotations

from federated_catalog.cli.mapper import dcat_to_edc_payloads


def test_odrl_passthrough(sample_dcat_catalog):
    dataset = sample_dcat_catalog["dcat:dataset"][0]
    result = dcat_to_edc_payloads(dataset, {})
    assert result is not None
    assert result["asset"]["@id"] == "https://example.com/datasets/weather"
    assert result["asset"]["properties"]["name"] == "Weather Features"

    policy = result["policy"]["policy"]
    assert policy["@type"] == "odrl:Set"
    assert "odrl:permission" in policy
    perms = policy["odrl:permission"]
    assert perms[0]["odrl:action"] == {"@id": "odrl:use"}
    constraint = perms[0]["odrl:constraint"][0]
    assert constraint["odrl:leftOperand"] == {"@id": "https://w3id.org/dsp/policy/Membership"}


def test_odrl_passthrough_sets_target():
    dataset = {
        "@id": "https://example.com/ds1",
        "dcat:distribution": [{
            "odrl:hasPolicy": {
                "@type": "odrl:Offer",
                "odrl:permission": [{"odrl:action": {"@id": "odrl:use"}}],
            }
        }],
    }
    result = dcat_to_edc_payloads(dataset, {})
    policy = result["policy"]["policy"]
    assert policy["odrl:target"] == {"@id": "https://example.com/ds1"}


def test_defaults_membership_constraint():
    dataset = {
        "@id": "https://example.com/ds1",
        "dct:title": "Test",
    }
    defaults = {"access_requirements": "partner"}
    result = dcat_to_edc_payloads(dataset, defaults)
    policy = result["policy"]["policy"]
    perms = policy["odrl:permission"]
    constraints = perms[0]["odrl:constraint"]
    assert any(
        c["odrl:leftOperand"] == {"@id": "https://w3id.org/dsp/policy/Membership"}
        for c in constraints
    )


def test_defaults_consent_constraint():
    dataset = {
        "@id": "https://example.com/ds1",
        "dct:title": "Test",
    }
    defaults = {"consent_required": True}
    result = dcat_to_edc_payloads(dataset, defaults)
    policy = result["policy"]["policy"]
    perms = policy["odrl:permission"]
    constraints = perms[0]["odrl:constraint"]
    assert any(
        c["odrl:leftOperand"] == {"@id": "https://w3id.org/dsp/policy/ConsentStatus"}
        for c in constraints
    )


def test_defaults_retention_obligation():
    dataset = {"@id": "https://example.com/ds1"}
    defaults = {"retention_days": 365}
    result = dcat_to_edc_payloads(dataset, defaults)
    policy = result["policy"]["policy"]
    obligations = policy["odrl:obligation"]
    action = obligations[0]["odrl:action"][0]
    assert action["rdf:value"] == {"@id": "odrl:delete"}
    refinement = action["odrl:refinement"][0]
    assert refinement["odrl:rightOperand"]["@value"] == "P365D"


def test_secret_access_level_skipped():
    dataset = {
        "@id": "https://example.com/secret",
        "ds:accessLevel": "secret",
    }
    assert dcat_to_edc_payloads(dataset, {}) is None


def test_no_id_skipped():
    dataset = {"dct:title": "No ID"}
    assert dcat_to_edc_payloads(dataset, {}) is None


def test_contract_definition_links_asset_and_policy():
    dataset = {"@id": "https://example.com/ds1"}
    result = dcat_to_edc_payloads(dataset, {})
    cd = result["contract_definition"]
    assert cd["accessPolicyId"] == "https://example.com/ds1:policy"
    assert cd["contractPolicyId"] == "https://example.com/ds1:policy"
    assert cd["assetsSelector"]["operandRight"] == "https://example.com/ds1"


def test_data_address_from_defaults():
    dataset = {"@id": "https://example.com/ds1"}
    defaults = {
        "data_address": {
            "base_url": "http://api.example.com/query",
            "type": "HttpData",
            "proxy_path": False,
            "proxy_query_params": True,
        }
    }
    result = dcat_to_edc_payloads(dataset, defaults)
    da = result["asset"]["dataAddress"]
    assert da["baseUrl"] == "http://api.example.com/query"
    assert da["type"] == "HttpData"
    assert da["proxyQueryParams"] == "true"


def test_data_address_from_distribution():
    dataset = {
        "@id": "https://example.com/ds1",
        "dcat:distribution": [{
            "dcat:accessURL": {"@id": "http://data.example.com/api"},
        }],
    }
    result = dcat_to_edc_payloads(dataset, {})
    da = result["asset"]["dataAddress"]
    assert da["baseUrl"] == "http://data.example.com/api"


def test_data_address_defaults_override_distribution():
    dataset = {
        "@id": "https://example.com/ds1",
        "dcat:distribution": [{
            "dcat:accessURL": {"@id": "http://data.example.com/api"},
        }],
    }
    defaults = {
        "data_address": {"base_url": "http://override.example.com/query"}
    }
    result = dcat_to_edc_payloads(dataset, defaults)
    da = result["asset"]["dataAddress"]
    assert da["baseUrl"] == "http://override.example.com/query"


def test_no_constraints_when_no_defaults():
    dataset = {"@id": "https://example.com/ds1"}
    result = dcat_to_edc_payloads(dataset, {})
    policy = result["policy"]["policy"]
    perms = policy["odrl:permission"]
    assert "odrl:constraint" not in perms[0]


def test_keywords_from_dataset():
    dataset = {
        "@id": "https://example.com/ds1",
        "dcat:keyword": ["weather", "gold"],
    }
    result = dcat_to_edc_payloads(dataset, {})
    assert result["asset"]["properties"]["dct:keyword"] == ["weather", "gold"]


def test_keywords_string_normalized_to_list():
    dataset = {
        "@id": "https://example.com/ds1",
        "dcat:keyword": "single-keyword",
    }
    result = dcat_to_edc_payloads(dataset, {})
    assert result["asset"]["properties"]["dct:keyword"] == ["single-keyword"]
