"""Tests for registry — load_providers and load_dcat_sources."""
from __future__ import annotations

import textwrap

from federated_catalog.registry import DcatSource, Provider, load_dcat_sources, load_providers


def test_load_providers(tmp_path):
    yaml_file = tmp_path / "participants.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        participants:
          - id: did:web:rec.example
            role: provider
            dsp_address: http://edc-rec:19194/protocol
          - id: did:web:consumer.example
            role: consumer
            dsp_address: http://edc-consumer:29194/protocol
    """))
    providers = load_providers(str(yaml_file))
    assert len(providers) == 1
    assert providers[0] == Provider(id="did:web:rec.example", dsp_address="http://edc-rec:19194/protocol")


def test_load_providers_missing_file():
    assert load_providers("/nonexistent/path.yaml") == []


def test_load_dcat_sources(tmp_path):
    yaml_file = tmp_path / "catalogues.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        catalogues:
          - id: dataset-api
            url: http://api.example.com/datasets/catalogue
            type: dcat-ap
          - id: ext-source
            url: http://ext.example.com/catalogue
            defaults:
              consent_required: true
              data_address:
                base_url: http://ext.example.com/query
    """))
    sources = load_dcat_sources(str(yaml_file))
    assert len(sources) == 2
    assert sources[0] == DcatSource(id="dataset-api", url="http://api.example.com/datasets/catalogue", type="dcat-ap")
    assert sources[1].defaults == {
        "consent_required": True,
        "data_address": {"base_url": "http://ext.example.com/query"},
    }


def test_load_dcat_sources_empty_string():
    assert load_dcat_sources("") == []


def test_load_dcat_sources_missing_file():
    assert load_dcat_sources("/nonexistent/path.yaml") == []


def test_load_dcat_sources_skips_invalid_entries(tmp_path):
    yaml_file = tmp_path / "catalogues.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        catalogues:
          - id: valid
            url: http://example.com/cat
          - id: no-url
          - url: http://no-id.example.com
    """))
    sources = load_dcat_sources(str(yaml_file))
    assert len(sources) == 1
    assert sources[0].id == "valid"
