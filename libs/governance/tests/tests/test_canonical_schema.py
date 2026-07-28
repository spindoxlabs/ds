"""Governance authored to the canonical schema must work here unchanged.

`celine-utils/schema/governance.schema.json` is the format every governance.yaml
in demo3 and celine-pipelines is written to. ds historically kept the same facts
in its own `policy:` block, and the two never met — until a dataset authored
elsewhere had to be exposed through this connector.

The failure that motivates these tests is quiet: a canonical file declares
`dataspace.purpose`, ds reads `policy.purpose`, finds nothing, publishes an ODRL
policy with **no purpose constraint**, and every consent check then denies for
want of a stated reason. Nothing errors. Nothing logs. The dataset simply never
returns a row.
"""
from __future__ import annotations

import yaml

from ds.governance.resolver import GovernanceResolver


def _resolve(doc: dict, dataset: str, tmp_path=None):
    """Round-trip through YAML, the way a real file arrives.

    Parsing the dict directly would skip `from_file`, which is where the
    canonical fields are read — and that is the code under test.
    """
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(doc, fh)
        path = Path(fh.name)
    try:
        return GovernanceResolver.from_file(path).resolve(dataset)
    finally:
        path.unlink(missing_ok=True)


CANONICAL = {
    "defaults": {
        # demo3 puts these in `defaults`, exactly like this.
        "dataspace": {"odrl_action": "use", "purpose": ["EnergyCommunityOperation"]},
    },
    "sources": {
        "datasets.raw.meters_data": {
            "access_level": "restricted",
            "classification": "pii",
            "row_filters": [
                {"handler": "rec_registry", "args": {"column": "device_id"}}
            ],
            "dataspace": {"consent_required": True},
        }
    },
}


def test_purpose_is_read_from_the_canonical_location():
    rule = _resolve(CANONICAL, "datasets.raw.meters_data")
    assert rule.policy.purpose == ["EnergyCommunityOperation"]


def test_consent_required_is_read_from_the_canonical_location():
    rule = _resolve(CANONICAL, "datasets.raw.meters_data")
    assert rule.policy.consent.required is True


def test_row_filters_survive_and_name_the_column():
    from ds.governance import subject_column

    rule = _resolve(CANONICAL, "datasets.raw.meters_data")
    assert rule.row_filters[0].handler == "rec_registry"
    assert subject_column(rule) == "device_id"


def test_contract_required_is_read_from_the_canonical_location():
    doc = {
        "sources": {
            "d": {"dataspace": {"contract_required": True}},
        }
    }
    assert _resolve(doc, "d").policy.obligations.contract_required is True


def test_the_legacy_policy_block_still_works():
    """Deployed ds files use `policy:`; they must not break on this change."""
    doc = {
        "sources": {
            "d": {
                "policy": {
                    "purpose": ["GridMonitoring"],
                    "consent": {"required": True},
                }
            }
        }
    }
    rule = _resolve(doc, "d")
    assert rule.policy.purpose == ["GridMonitoring"]
    assert rule.policy.consent.required is True


def test_canonical_wins_when_a_file_says_both():
    """A file carrying both should behave the way the schema says.

    Not an academic case: a ds file being migrated will pass through a state
    where both are present, and the migration is only safe if the destination
    is the one that counts.
    """
    doc = {
        "sources": {
            "d": {
                "policy": {"purpose": ["GridMonitoring"]},
                "dataspace": {"purpose": ["EnergyCommunityOperation"]},
            }
        }
    }
    assert _resolve(doc, "d").policy.purpose == ["EnergyCommunityOperation"]
