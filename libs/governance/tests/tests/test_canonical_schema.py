"""Governance authored to the canonical schema must work here unchanged.

`celine-utils/schema/governance.schema.json` is the format every governance.yaml
in the producer pipelines is written to. ds historically kept the same facts
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
        # Producer files put these in `defaults`, exactly like this.
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


# ── The `dcat:` block ─────────────────────────────────────────────────────────
#
# `governanceBlock.dcat` has been in the canonical schema all along; ds carried no
# `dcat` field, so Pydantic's default `extra="ignore"` dropped the whole block.
# A producer authoring against the published schema got a valid file, no warning
# and no effect.
#
# These read the *canonical* spelling only. There is no ds-side alternative
# spelling to reconcile, which is the one way this differs from `purpose` above.

DCAT_BLOCK = {
    "publisher_uri": "https://example.test/org/grid-operator",
    "themes": ["http://publications.europa.eu/resource/authority/data-theme/ENER"],
    "language_uris": ["http://publications.europa.eu/resource/authority/language/ENG"],
    "spatial_uris": ["http://publications.europa.eu/resource/authority/atu/ITA"],
    "accrual_periodicity": (
        "http://publications.europa.eu/resource/authority/frequency/QUARTER_HOURLY"
    ),
    "conforms_to": "https://saref.etsi.org/saref4ener/",
    "temporal": {"start": "2020-01-01", "end": "2026-01-01"},
}


def test_the_whole_dcat_block_survives_the_load():
    """Every field, because the failure mode was losing all of them at once."""
    rule = _resolve({"sources": {"d": {"dcat": DCAT_BLOCK}}}, "d")
    assert rule.dcat.publisher_uri == "https://example.test/org/grid-operator"
    assert rule.dcat.themes == DCAT_BLOCK["themes"]
    assert rule.dcat.language_uris == DCAT_BLOCK["language_uris"]
    assert rule.dcat.spatial_uris == DCAT_BLOCK["spatial_uris"]
    assert rule.dcat.accrual_periodicity == DCAT_BLOCK["accrual_periodicity"]
    assert rule.dcat.conforms_to == "https://saref.etsi.org/saref4ener/"
    assert rule.dcat.temporal is not None
    assert rule.dcat.temporal.start == "2020-01-01"
    assert rule.dcat.temporal.end == "2026-01-01"


def test_conforms_to_is_read_from_the_canonical_location():
    """`M-4` — the payload semantic model, the field the whole CEEDS layer needs.

    Called out separately from the sweep above because this is the one a
    deployment binds SAREF or CIM with, and a regression here is the difference
    between a declared semantic model and a silently domain-less catalogue.
    """
    rule = _resolve(
        {"sources": {"d": {"dcat": {"conforms_to": "https://saref.etsi.org/saref4ener/"}}}},
        "d",
    )
    assert rule.dcat.conforms_to == "https://saref.etsi.org/saref4ener/"


def test_a_file_with_no_dcat_block_still_loads():
    """The block is optional and always was — every existing file omits it."""
    rule = _resolve({"sources": {"d": {"access_level": "open"}}}, "d")
    assert rule.dcat.conforms_to is None
    assert rule.dcat.themes == []
    assert rule.dcat.temporal is None


def test_dcat_defaults_are_inherited_like_every_other_block():
    """`defaults:` is where a producer puts publisher and language, once."""
    doc = {
        "defaults": {"dcat": {"publisher_uri": "https://example.test/org/grid-operator"}},
        "sources": {"d": {"dcat": {"conforms_to": "https://saref.etsi.org/saref4ener/"}}},
    }
    rule = _resolve(doc, "d")
    assert rule.dcat.conforms_to == "https://saref.etsi.org/saref4ener/"
    assert rule.dcat.publisher_uri == "https://example.test/org/grid-operator"
