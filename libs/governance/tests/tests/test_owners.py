"""Tests for ds.governance.owners — OwnerEntry, OwnersRegistry, load_owners_yaml.

The three names under test are `celine.governance.owners`' since phase 4 of
`ADR-0013`, re-exported by `ds.governance.owners`. These tests stay because they
are what says the re-export kept ds's public surface — `services/identity-registry`
and `compliance/runtime.py` both import them by name — and because two of ds's own
behaviours changed with the adoption, which is worth an assertion each rather than
a paragraph in a status file.
"""

from __future__ import annotations


import pytest

from ds.governance.owners import OwnerEntry, OwnersRegistry, load_owners_yaml


class TestOwnerEntry:
    def test_defaults(self):
        entry = OwnerEntry(id="example-org")
        assert entry.type == "schema:Organization"
        # `None`, not `""`. ds defaulted it to the empty string, which reads as
        # "has a name and it is blank"; nothing here distinguished the two, and
        # upstream's optional is the more honest default.
        assert entry.name is None
        assert entry.did is None
        assert entry.url is None
        assert entry.aliases == []
        assert entry.organization is None

    def test_the_keycloak_block_is_read_from_both_spellings(self):
        """**The silent drop phase 4 fixed.** One model, two sources.

        `owners.yaml` — the file a human writes — says `organization`. The
        identity-registry's API says `organization_config`, because that is its
        column name. ds declared only the second, so `OwnerEntry` read an IR
        response correctly and **discarded the block when loading a YAML**, which is
        the only place it is authored. `services/identity-registry` passes those
        files to `OwnerEntry(**entry)` when it decides which organisations to
        onboard, so what was lost was a provisioning instruction.
        """
        from_yaml = OwnerEntry(id="a", organization={"create": True, "role": "rec"})
        from_ir = OwnerEntry(
            id="a", organization_config={"create": True, "role": "rec"}
        )

        assert from_yaml.organization is not None
        assert from_yaml.organization.create is True
        assert from_yaml.organization.role == "rec"
        assert from_ir.organization == from_yaml.organization

    def test_canonical_uri_prefers_did(self):
        entry = OwnerEntry(
            id="org",
            did="did:web:org.example",
            url="https://org.example",
        )
        assert entry.canonical_uri == "did:web:org.example"

    def test_canonical_uri_falls_back_to_url(self):
        entry = OwnerEntry(id="org", url="https://org.example")
        assert entry.canonical_uri == "https://org.example"

    def test_canonical_uri_none_when_empty(self):
        entry = OwnerEntry(id="org")
        assert entry.canonical_uri is None

    def test_extra_fields_ignored(self):
        entry = OwnerEntry(
            id="org",
            name="Org",
            some_extra_field="should be ignored",
        )
        assert entry.id == "org"


class TestOwnersRegistry:
    @pytest.fixture
    def registry(self):
        return OwnersRegistry(
            [
                OwnerEntry(
                    id="example-org",
                    name="Example Org",
                    did="did:web:example-org.dataspaces.localhost",
                    aliases=["example", "ex-org"],
                ),
                OwnerEntry(
                    id="open-data-provider",
                    name="Open Data Provider",
                    url="https://open-data.example.org",
                ),
            ]
        )

    def test_by_id_direct(self, registry):
        entry = registry.by_id("example-org")
        assert entry is not None
        assert entry.name == "Example Org"

    def test_by_id_alias(self, registry):
        entry = registry.by_id("example")
        assert entry is not None
        assert entry.id == "example-org"

    def test_by_id_second_alias(self, registry):
        entry = registry.by_id("ex-org")
        assert entry is not None
        assert entry.id == "example-org"

    def test_by_id_missing(self, registry):
        assert registry.by_id("nonexistent") is None

    def test_by_uri_did(self, registry):
        entry = registry.by_uri("did:web:example-org.dataspaces.localhost")
        assert entry is not None
        assert entry.id == "example-org"

    def test_by_uri_url(self, registry):
        entry = registry.by_uri("https://open-data.example.org")
        assert entry is not None
        assert entry.id == "open-data-provider"

    def test_by_uri_missing(self, registry):
        assert registry.by_uri("did:web:unknown") is None

    def test_canonical_uri_resolves(self, registry):
        assert (
            registry.canonical_uri("example-org")
            == "did:web:example-org.dataspaces.localhost"
        )

    def test_canonical_uri_alias(self, registry):
        assert (
            registry.canonical_uri("example")
            == "did:web:example-org.dataspaces.localhost"
        )

    def test_canonical_uri_missing(self, registry):
        assert registry.canonical_uri("nonexistent") is None

    def test_all(self, registry):
        assert len(registry.all()) == 2


class TestLoadOwnersYaml:
    def test_round_trip(self, tmp_path):
        yaml_content = """\
owners:
  - id: example-org
    type: schema:NGO
    name: Example Organization
    did: did:web:rec.dataspaces.localhost
    aliases: [example]
    organization:
      create: true
      role: community
  - id: open-data-provider
    type: schema:Organization
    name: Open Data Provider
    url: https://open-data.example.org
"""
        path = tmp_path / "owners.yaml"
        path.write_text(yaml_content)

        registry = load_owners_yaml(path)
        assert len(registry.all()) == 2

        org = registry.by_id("example-org")
        assert org is not None
        assert org.type == "schema:NGO"
        assert org.did == "did:web:rec.dataspaces.localhost"
        assert org.canonical_uri == "did:web:rec.dataspaces.localhost"
        assert registry.canonical_uri("example") == "did:web:rec.dataspaces.localhost"

        odp = registry.by_id("open-data-provider")
        assert odp is not None
        assert odp.canonical_uri == "https://open-data.example.org"

    def test_the_keycloak_block_survives_the_round_trip(self, tmp_path):
        """What `test_round_trip`'s fixture has always declared and never checked.

        Its YAML carries `organization: {create: true, role: community}`. Under ds's
        own model that block was dropped on the way in and the test could not have
        noticed — nothing asserted it. See
        `TestOwnerEntry.test_the_keycloak_block_is_read_from_both_spellings`.
        """
        path = tmp_path / "owners.yaml"
        path.write_text(
            "owners:\n"
            "  - id: example-org\n"
            "    organization:\n"
            "      create: true\n"
            "      role: community\n"
        )

        entry = load_owners_yaml(path).by_id("example-org")
        assert entry is not None
        assert entry.organization is not None
        assert entry.organization.create is True
        assert entry.organization.role == "community"

    def test_missing_file_raises(self, tmp_path):
        """**A behaviour ds changed on purpose in phase 4.**

        This returned an empty registry. Upstream's loader raises unless the caller
        passes `missing_ok=True`, and it takes that parameter because the two
        implementations it consolidates disagreed — so the choice had to be made
        rather than inherited.

        ds takes the raise. An owners file that was asked for and is not there would
        otherwise leave every owner check resolving nothing and reporting a pass it
        did not make, which is the `CI-02` shape `resolver.from_file` has now deleted
        twice. The only caller is the CLI, and it passes a path only when `--owners`
        named one.
        """
        with pytest.raises(FileNotFoundError):
            load_owners_yaml(tmp_path / "nonexistent.yaml")
