"""Tests for fc-cli commands."""
from __future__ import annotations

import textwrap

import httpx
import respx
from typer.testing import CliRunner

from federated_catalog.cli.main import app

runner = CliRunner()


def test_status_no_sources():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_status_with_sources(tmp_path):
    participants = tmp_path / "participants.yaml"
    participants.write_text(textwrap.dedent("""\
        participants:
          - id: did:web:rec
            role: provider
            dsp_address: http://edc:19194/protocol
    """))

    catalogues = tmp_path / "catalogues.yaml"
    catalogues.write_text(textwrap.dedent("""\
        catalogues:
          - id: test-api
            url: http://api.test/catalogue
    """))

    result = runner.invoke(app, [
        "status",
        "--participants-yaml", str(participants),
        "--dcat-sources-yaml", str(catalogues),
    ])
    assert result.exit_code == 0
    assert "did:web:rec" in result.output
    assert "test-api" in result.output


def test_sync_missing_sources():
    result = runner.invoke(app, [
        "sync",
        "--sources", "/nonexistent/catalogues.yaml",
        "--connector-url", "http://localhost:30001",
    ])
    assert result.exit_code == 1
    assert "No DCAT sources" in result.output


@respx.mock
def test_sync_success(tmp_path):
    catalogues = tmp_path / "catalogues.yaml"
    catalogues.write_text(textwrap.dedent("""\
        catalogues:
          - id: test-api
            url: http://api.test/catalogue
            defaults:
              data_address:
                base_url: http://api.test/query
    """))

    catalog = {
        "dcat:dataset": [
            {"@id": "https://example.com/ds1", "dct:title": "Dataset 1"},
        ]
    }

    respx.get("http://api.test/catalogue").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    respx.post("http://localhost:30001/provider/sync").mock(
        return_value=httpx.Response(200, json={"synced": ["ds1"]})
    )

    result = runner.invoke(app, [
        "sync",
        "--sources", str(catalogues),
        "--connector-url", "http://localhost:30001",
    ])
    assert result.exit_code == 0
    assert "1 synced" in result.output


@respx.mock
def test_sync_fetch_error(tmp_path):
    catalogues = tmp_path / "catalogues.yaml"
    catalogues.write_text(textwrap.dedent("""\
        catalogues:
          - id: broken
            url: http://api.broken/catalogue
    """))

    respx.get("http://api.broken/catalogue").mock(
        return_value=httpx.Response(503, text="Unavailable")
    )

    result = runner.invoke(app, [
        "sync",
        "--sources", str(catalogues),
        "--connector-url", "http://localhost:30001",
    ])
    assert result.exit_code == 1
    assert "1 errors" in result.output


@respx.mock
def test_sync_skips_secret_datasets(tmp_path):
    catalogues = tmp_path / "catalogues.yaml"
    catalogues.write_text(textwrap.dedent("""\
        catalogues:
          - id: test-api
            url: http://api.test/catalogue
    """))

    catalog = {
        "dcat:dataset": [
            {"@id": "https://example.com/secret", "ds:accessLevel": "secret"},
            {"@id": "https://example.com/open", "ds:accessLevel": "open"},
        ]
    }

    respx.get("http://api.test/catalogue").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    respx.post("http://localhost:30001/provider/sync").mock(
        return_value=httpx.Response(200, json={"synced": []})
    )

    result = runner.invoke(app, [
        "sync",
        "--sources", str(catalogues),
        "--connector-url", "http://localhost:30001",
    ])
    assert result.exit_code == 0
    assert "1 synced" in result.output
    assert "1 skipped" in result.output
