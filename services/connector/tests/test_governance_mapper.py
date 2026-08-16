"""Tests for ConnectorGovernanceMapper."""
import pytest

from connector.services.governance import ConnectorGovernanceMapper, load_exposed_datasets
from ds.governance.models import GovernanceOwner, GovernanceRuleV2, DataspaceSpec, DataspaceDataAddress


def _mapper(**kwargs):
    return ConnectorGovernanceMapper("provider", "https://rec.dataspaces.localhost", **kwargs)


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
    assert asset.id.startswith("https://rec.dataspaces.localhost")
    assert asset.properties["name"] == "Test Dataset"
    # Asset properties are namespaced by the **active profile's** prefix, which a
    # deployment may change (`CONNECTOR_ODRL_PROFILE_PATH`). Asserting the literal
    # `ds:` was how this test came to disagree with every writer and reader of the
    # property — `dependencies._asset_owner` matches on the local name for the
    # same reason. Read the prefix off the mapper under test.
    pfx = mapper.profile.prefix
    assert asset.properties[f"{pfx}:medallion"] == "gold"


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


def test_policy_assigner_uses_owner_did():
    owner_did = "did:web:example-org.dataspaces.localhost"
    mapper = _mapper(owner_did_resolver=lambda name: owner_did if name == "example-org" else None)
    rule = _rule(
        access_level="internal",
        classification="green",
        ownership=[GovernanceOwner(name="example-org")],
        dataspace=DataspaceSpec(expose=True),
    )
    policy = mapper.to_policy_create("datasets.gold.test", rule)
    assert policy.policy["odrl:assigner"]["@id"] == owner_did


def test_policy_assigner_falls_back_to_participant():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        classification="green",
        dataspace=DataspaceSpec(expose=True),
    )
    policy = mapper.to_policy_create("datasets.gold.test", rule)
    assert "provider" in policy.policy["odrl:assigner"]["@id"]


def test_policy_assigner_unknown_owner_falls_back():
    mapper = _mapper(owner_did_resolver=lambda name: None)
    rule = _rule(
        access_level="internal",
        classification="green",
        ownership=[GovernanceOwner(name="unknown-org")],
        dataspace=DataspaceSpec(expose=True),
    )
    policy = mapper.to_policy_create("datasets.gold.test", rule)
    assert "provider" in policy.policy["odrl:assigner"]["@id"]


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


# ── What the sync actually publishes ─────────────────────────────────────────
#
# `GOV-…`/`M-4`: this class held a **second copy** of the property dict, and the
# copies disagreed — the library mapper emitted `dct:conformsTo` and this one did
# not, while this one is what `provider_service` calls. Every test asserting the
# property was emitted asserted it against the library, so all of them passed
# while nothing reached EDC. These assert the object the sync hands to the EDC
# client, which is the artefact that was wrong.


def _dcat_rule(**dcat) -> GovernanceRuleV2:
    from ds.governance.models import DcatSpec

    return _rule(
        title="Meter readings",
        access_level="restricted",
        classification="pii",
        dataspace=DataspaceSpec(expose=True),
        dcat=DcatSpec(**dcat),
    )


@pytest.mark.rule("M-4")
def test_the_published_asset_carries_the_declared_payload_model():
    """`M-4`. A consumer discovers the model at browse time or not at all — after
    negotiating is too late to decide whether it can parse the rows."""
    mapper = _mapper()
    iri = "https://rec.dataspaces.localhost/ns/meter-readings"
    asset = mapper.to_asset_create(
        "datasets.silver.meters_15m", _dcat_rule(conforms_to=iri)
    )
    assert asset.properties["dct:conformsTo"] == iri


@pytest.mark.rule("M-4")
def test_the_context_declares_dct_so_the_curie_expands():
    """Without the declaration EDC keeps `dct:conformsTo` as an opaque string key
    and the CURIE expands to nothing — a property that looks like a DCAT-AP term
    and is a private one."""
    mapper = _mapper()
    asset = mapper.to_asset_create(
        "datasets.silver.meters_15m",
        _dcat_rule(conforms_to="https://rec.dataspaces.localhost/ns/meter-readings"),
    )
    assert asset.context and asset.context.get("dct") == "http://purl.org/dc/terms/"
    assert asset.to_edc()["@context"]["dct"] == "http://purl.org/dc/terms/"


@pytest.mark.rule("M-4")
def test_a_dataset_declaring_no_model_publishes_no_key_rather_than_a_null():
    """A dataset that states no model and one that states "no model" are
    different claims, and only the first is what silence means."""
    mapper = _mapper()
    asset = mapper.to_asset_create("datasets.gold.test", _dcat_rule())
    assert "dct:conformsTo" not in asset.to_edc()["properties"]
    assert "dct" not in asset.to_edc()["@context"]


def test_the_owner_the_connector_resolves_survives_the_delegation():
    """The two properties only the connector knows. Delegating the rest must not
    drop them — they are what `dependencies._asset_owner` matches on."""
    mapper = _mapper(owner_did_resolver=lambda alias: f"did:web:{alias}.test")
    rule = _rule(
        access_level="internal",
        classification="green",
        ownership=[GovernanceOwner(name="example-org", type="Organization")],
        dataspace=DataspaceSpec(expose=True),
    )
    asset = mapper.to_asset_create("datasets.gold.test", rule)
    pfx = mapper.profile.prefix
    assert asset.properties[f"{pfx}:owner"] == "example-org"
    assert asset.properties[f"{pfx}:ownerDid"] == "did:web:example-org.test"
