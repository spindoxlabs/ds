"""Tests for ds.governance.owners — OwnerEntry, OwnersRegistry, load_owners_yaml."""
from __future__ import annotations

from pathlib import Path

import pytest

from ds.governance.owners import OwnerEntry, OwnersRegistry, load_owners_yaml


class TestOwnerEntry:
    def test_defaults(self):
        entry = OwnerEntry(id="example-org")
        assert entry.type == "schema:Organization"
        assert entry.name == ""
        assert entry.did is None
        assert entry.url is None
        assert entry.aliases == []
        assert entry.organization_config is None

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
    did: did:web:provider.dataspaces.localhost
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
        assert org.did == "did:web:provider.dataspaces.localhost"
        assert org.canonical_uri == "did:web:provider.dataspaces.localhost"
        assert registry.canonical_uri("example") == "did:web:provider.dataspaces.localhost"

        odp = registry.by_id("open-data-provider")
        assert odp is not None
        assert odp.canonical_uri == "https://open-data.example.org"

    def test_missing_file(self, tmp_path):
        registry = load_owners_yaml(tmp_path / "nonexistent.yaml")
        assert len(registry.all()) == 0
