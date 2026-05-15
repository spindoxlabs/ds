"""Tests for ConnectorGovernanceMapper."""
import pytest

from connector.services.governance import ConnectorGovernanceMapper, load_exposed_datasets
from ds.governance.models import GovernanceRuleV2, DataspaceSpec, DataspaceDataAddress


def _mapper():
    return ConnectorGovernanceMapper("provider", "https://provider.dataspaces.localhost")


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def test_asset_create_basic():
    mapper = _mapper()
    rule = _rule(
        title="Test Dataset",
        access_level="internal",
        classification="green",
        dataspace=DataspaceSpec(expose=True),
    )
    asset = mapper.to_asset_create("datasets.gold.test", rule)
    assert asset.id.startswith("https://provider.dataspaces.localhost")
    assert asset.properties["name"] == "Test Dataset"
    assert asset.properties["ds:medallion"] == "gold"


def test_asset_data_address_query_params():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        classification="green",
        dataspace=DataspaceSpec(
            expose=True,
            data_address=DataspaceDataAddress(
                query_params={"dataset_name": "datasets.gold.test"}
            ),
        ),
    )
    asset = mapper.to_asset_create("datasets.gold.test", rule)
    assert "queryParam:dataset_name" in asset.data_address.extra


def test_policy_create_has_odrl_set():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green", dataspace=DataspaceSpec(expose=True))
    policy = mapper.to_policy_create("datasets.gold.test", rule)
    assert "odrl:Set" in str(policy.policy.get("@type", ""))


def test_contract_definition_links_asset():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green", dataspace=DataspaceSpec(expose=True))
    asset = mapper.to_asset_create("datasets.gold.test", rule)
    policy = mapper.to_policy_create("datasets.gold.test", rule)
    contract = mapper.to_contract_definition("datasets.gold.test", rule, policy.id, asset.id)
    assert len(contract.assets_selector) == 1
    assert contract.assets_selector[0]["operandRight"] == asset.id


def test_load_exposed_datasets(tmp_path):
    import textwrap
    yaml_path = tmp_path / "governance.yaml"
    yaml_path.write_text(textwrap.dedent("""
        defaults:
          access_level: internal
          classification: green
        sources:
          datasets.gold.exposed:
            title: Exposed Dataset
            dataspace:
              expose: true
          datasets.gold.hidden:
            title: Hidden Dataset
            dataspace:
              expose: false
          datasets.gold.secret:
            access_level: secret
            dataspace:
              expose: true
    """))
    result = load_exposed_datasets(str(yaml_path))
    assert "datasets.gold.exposed" in result
    assert "datasets.gold.hidden" not in result
    assert "datasets.gold.secret" not in result
