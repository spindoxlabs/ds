"""Tests for governance overlay merge (from_file_with_override, _merge_configs, _merge)."""

from __future__ import annotations


from ds.governance.resolver import GovernanceResolver


BASE_YAML = """\
defaults:
  access_level: open
  tags: [energy]

sources:
  example_meters_15m:
    title: Example Meters 15m
    access_level: internal
    dataspace:
      expose: true
  example_weather:
    title: Example Weather
    access_level: open
    tags: [weather]
    dataspace:
      expose: true
"""


class TestOverlayDefaults:
    def test_overlay_sets_defaults_ownership(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        (tmp_path / "governance.test.yaml").write_text(
            """\
defaults:
  ownership:
    - name: example-org
      type: DATA_OWNER
"""
        )
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="test"
        )
        rule = resolver.resolve("example_meters_15m")
        assert len(rule.ownership) == 1
        assert rule.ownership[0].name == "example-org"
        assert rule.access_level == "internal"

    def test_overlay_defaults_propagate_to_all_sources(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        (tmp_path / "governance.test.yaml").write_text(
            """\
defaults:
  ownership:
    - name: example-org
"""
        )
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="test"
        )
        for key in ["example_meters_15m", "example_weather"]:
            rule = resolver.resolve(key)
            assert len(rule.ownership) == 1
            assert rule.ownership[0].name == "example-org"


class TestOverlayPerDataset:
    def test_overlay_adds_new_dataset(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        (tmp_path / "governance.test.yaml").write_text(
            """\
sources:
  example_grid_data:
    title: Example Grid Data
    access_level: restricted
    dataspace:
      expose: true
"""
        )
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="test"
        )
        assert "example_grid_data" in resolver.config.sources
        rule = resolver.resolve("example_grid_data")
        assert rule.title == "Example Grid Data"
        assert rule.access_level == "restricted"

    def test_overlay_merges_into_existing_source(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        (tmp_path / "governance.test.yaml").write_text(
            """\
sources:
  example_meters_15m:
    ownership:
      - name: example-org
"""
        )
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="test"
        )
        rule = resolver.resolve("example_meters_15m")
        assert rule.title == "Example Meters 15m"
        assert len(rule.ownership) == 1
        assert rule.ownership[0].name == "example-org"


class TestMergeRuleSemantics:
    def test_nonempty_lists_replace(self, tmp_path):
        base = GovernanceResolver._parse_rule(
            {"ownership": [{"name": "old-org"}], "tags": ["a"]}
        )
        override = GovernanceResolver._parse_rule({"ownership": [{"name": "new-org"}]})
        merged = GovernanceResolver._merge(base, override)
        assert len(merged.ownership) == 1
        assert merged.ownership[0].name == "new-org"

    def test_empty_lists_preserve_base(self, tmp_path):
        base = GovernanceResolver._parse_rule({"ownership": [{"name": "org-a"}]})
        override = GovernanceResolver._parse_rule({})
        merged = GovernanceResolver._merge(base, override)
        assert len(merged.ownership) == 1
        assert merged.ownership[0].name == "org-a"

    def test_unstated_scalars_preserve_base(self):
        """**Unstated**, which is not the same as stated `null`.

        Renamed in phase 2 of `ADR-0013`, because the merge changed underneath it
        and the old name now describes the opposite case. `_parse_rule({})` declares
        nothing, so `access_level` is absent from `model_fields_set` and the base
        survives — that is this test, and it is unchanged.

        An override that states `access_level: null` is a different statement and now
        gets a different answer: it withdraws the value. Under the old `pick()` merge
        the two were indistinguishable and both inherited.
        `test_characterisation.py::test_a_scalar_set_to_null_in_an_override` pins
        that half.
        """
        base = GovernanceResolver._parse_rule({"access_level": "internal"})
        override = GovernanceResolver._parse_rule({})
        merged = GovernanceResolver._merge(base, override)
        assert merged.access_level == "internal"

        withdrawn = GovernanceResolver._parse_rule({"access_level": None})
        assert GovernanceResolver._merge(base, withdrawn).access_level is None

    def test_tags_union(self):
        base = GovernanceResolver._parse_rule({"tags": ["a", "b"]})
        override = GovernanceResolver._parse_rule({"tags": ["b", "c"]})
        merged = GovernanceResolver._merge(base, override)
        assert sorted(merged.tags) == ["a", "b", "c"]


class TestMissingOverlay:
    def test_missing_overlay_returns_base(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="nonexistent"
        )
        assert "example_meters_15m" in resolver.config.sources
        rule = resolver.resolve("example_meters_15m")
        assert len(rule.ownership) == 0

    def test_no_overlay_name_returns_base(self, tmp_path):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name=None
        )
        rule = resolver.resolve("example_meters_15m")
        assert rule.title == "Example Meters 15m"


class TestOverlayEnvVar:
    def test_overlay_from_env_var(self, tmp_path, monkeypatch):
        (tmp_path / "governance.yaml").write_text(BASE_YAML)
        (tmp_path / "governance.fromenv.yaml").write_text(
            """\
defaults:
  ownership:
    - name: env-org
"""
        )
        monkeypatch.setenv("GOVERNANCE_OVERLAY_NAME", "fromenv")
        resolver = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml"
        )
        rule = resolver.resolve("example_meters_15m")
        assert len(rule.ownership) == 1
        assert rule.ownership[0].name == "env-org"
