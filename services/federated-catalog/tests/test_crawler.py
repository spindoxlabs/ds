"""Tests for crawler — crawl_dcat_source and crawl_all integration."""
from __future__ import annotations

import textwrap

import httpx
import pytest
import respx

from federated_catalog.config import Settings
from federated_catalog.crawler import crawl_all, crawl_dcat_source
from federated_catalog.registry import DcatSource

CONNECTOR_URL = "http://ds-connector:30001"


def _yaml_only_settings(participants_yaml, catalogues_yaml) -> Settings:
    """Settings for the YAML-fallback path, with the registry explicitly off.

    Two defaults made these tests unrunnable and neither is visible from the
    test body. `identity_registry_url` defaults to a **non-empty** URL, so
    leaving it alone sent `crawl_all` down the registry branch and straight into
    an unmocked HTTP call — the trap `AGENTS.md` warns about. And `connector_url`
    defaults to `172.17.0.1:31001` while the mock below answers on
    `ds-connector:30001`, so the one test that reaches a provider missed it too.
    """
    return Settings(
        identity_registry_url="",
        connector_url=CONNECTOR_URL,
        participants_yaml=str(participants_yaml),
        dcat_sources_yaml=str(catalogues_yaml),
    )


@respx.mock
async def test_crawl_dcat_source_success(sample_dcat_catalog):
    source = DcatSource(id="test-api", url="http://api.test/catalogue")
    respx.get("http://api.test/catalogue").mock(
        return_value=httpx.Response(200, json=sample_dcat_catalog)
    )
    source_id, datasets = await crawl_dcat_source(source, max_datasets=500)
    assert source_id == "test-api"
    assert len(datasets) == 2
    assert datasets[0]["@id"] == "https://example.com/datasets/weather"
    assert datasets[1]["@id"] == "https://example.com/datasets/meters"


@respx.mock
async def test_crawl_dcat_source_tags_publisher():
    catalog = {
        "dcat:dataset": [{"@id": "https://example.com/ds1", "dct:title": "DS1"}]
    }
    source = DcatSource(id="src-1", url="http://api.test/cat")
    respx.get("http://api.test/cat").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    _, datasets = await crawl_dcat_source(source, max_datasets=500)
    assert datasets[0]["dct:publisher"] == {"@id": "src-1"}


@respx.mock
async def test_crawl_dcat_source_preserves_existing_publisher():
    catalog = {
        "dcat:dataset": [
            {"@id": "https://example.com/ds1", "dct:publisher": {"@id": "did:web:orig"}}
        ]
    }
    source = DcatSource(id="src-1", url="http://api.test/cat")
    respx.get("http://api.test/cat").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    _, datasets = await crawl_dcat_source(source, max_datasets=500)
    assert datasets[0]["dct:publisher"] == {"@id": "did:web:orig"}


@respx.mock
async def test_crawl_dcat_source_http_error():
    source = DcatSource(id="fail-src", url="http://api.test/fail")
    respx.get("http://api.test/fail").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(httpx.HTTPStatusError):
        await crawl_dcat_source(source, max_datasets=500)


@respx.mock
async def test_crawl_dcat_source_single_dataset_dict():
    catalog = {
        "dcat:dataset": {"@id": "https://example.com/single", "dct:title": "Single"}
    }
    source = DcatSource(id="single-src", url="http://api.test/cat")
    respx.get("http://api.test/cat").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    _, datasets = await crawl_dcat_source(source, max_datasets=500)
    assert len(datasets) == 1
    assert datasets[0]["@id"] == "https://example.com/single"


@respx.mock
async def test_crawl_dcat_source_respects_max_datasets():
    catalog = {
        "dcat:dataset": [
            {"@id": f"https://example.com/ds{i}", "dct:title": f"DS{i}"}
            for i in range(10)
        ]
    }
    source = DcatSource(id="many-src", url="http://api.test/cat")
    respx.get("http://api.test/cat").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    _, datasets = await crawl_dcat_source(source, max_datasets=3)
    assert len(datasets) == 3


@respx.mock
async def test_crawl_all_includes_dcat_sources(tmp_path, sample_dcat_catalog):
    participants_yaml = tmp_path / "participants.yaml"
    participants_yaml.write_text("participants: []\n")

    catalogues_yaml = tmp_path / "catalogues.yaml"
    catalogues_yaml.write_text(textwrap.dedent("""\
        catalogues:
          - id: test-api
            url: http://api.test/catalogue
            type: dcat-ap
    """))

    respx.get("http://api.test/catalogue").mock(
        return_value=httpx.Response(200, json=sample_dcat_catalog)
    )

    settings = _yaml_only_settings(participants_yaml, catalogues_yaml)
    results, errors, _ = await crawl_all(settings)
    assert "test-api" in results
    assert len(results["test-api"]) == 2
    assert errors == []


@respx.mock
async def test_crawl_all_dcat_error_is_failsafe(tmp_path):
    participants_yaml = tmp_path / "participants.yaml"
    participants_yaml.write_text("participants: []\n")

    catalogues_yaml = tmp_path / "catalogues.yaml"
    catalogues_yaml.write_text(textwrap.dedent("""\
        catalogues:
          - id: broken-api
            url: http://api.broken/catalogue
    """))

    respx.get("http://api.broken/catalogue").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    settings = _yaml_only_settings(participants_yaml, catalogues_yaml)
    results, errors, _ = await crawl_all(settings)
    assert results == {}
    assert len(errors) == 1
    assert errors[0].provider_id == "broken-api"


@respx.mock
async def test_crawl_all_mixed_dsp_and_dcat(tmp_path, sample_dcat_catalog):
    participants_yaml = tmp_path / "participants.yaml"
    participants_yaml.write_text(textwrap.dedent("""\
        participants:
          - id: did:web:provider
            role: provider
            dsp_address: http://edc:19194/protocol
    """))

    catalogues_yaml = tmp_path / "catalogues.yaml"
    catalogues_yaml.write_text(textwrap.dedent("""\
        catalogues:
          - id: dcat-api
            url: http://api.test/catalogue
    """))

    respx.post(f"{CONNECTOR_URL}/consumer/catalog").mock(
        return_value=httpx.Response(200, json={
            "dcat:dataset": [
                {"@id": "https://dsp.example/ds1", "dct:title": "DSP Dataset"}
            ]
        })
    )
    respx.get("http://api.test/catalogue").mock(
        return_value=httpx.Response(200, json=sample_dcat_catalog)
    )

    settings = _yaml_only_settings(participants_yaml, catalogues_yaml)
    results, errors, _ = await crawl_all(settings)
    assert "did:web:provider" in results
    assert "dcat-api" in results
    assert errors == []
