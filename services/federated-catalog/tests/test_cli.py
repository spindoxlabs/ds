"""Tests for fc-cli commands."""

from __future__ import annotations

import textwrap

from typer.testing import CliRunner

from federated_catalog.cli.main import app

runner = CliRunner()


def test_status_no_sources():
    """`status` with no arguments reports no sources instead of crashing.

    `participants_yaml` defaults to `""`, and `Path("")` is `Path(".")`, which
    exists — so the "no file configured" case reached `open()` on a directory
    and raised `IsADirectoryError`. The one command a person runs first was the
    one that could not run.
    """
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_cli_exposes_no_publication_command():
    """The index never publishes — `DSSC-PUB-12`, rulebook `C-2`.

    A `sync` command used to push crawled DCAT-AP datasets into this
    participant's EDC, which is the blueprint's *centralized/broker* model. This
    dataspace's recorded decision is distributed catalogues with a pull-crawled
    advisory index, so publication belongs to the provider's own participant
    agent. This test is what stops the command coming back by accident.
    """
    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    assert names == {"crawl", "status"}


def test_status_with_sources(tmp_path):
    participants = tmp_path / "participants.yaml"
    participants.write_text(
        textwrap.dedent("""\
        participants:
          - id: did:web:rec
            role: provider
            dsp_address: http://edc:19194/protocol
    """)
    )

    catalogues = tmp_path / "catalogues.yaml"
    catalogues.write_text(
        textwrap.dedent("""\
        catalogues:
          - id: test-api
            url: http://api.test/catalogue
    """)
    )

    result = runner.invoke(
        app,
        [
            "status",
            "--participants-yaml",
            str(participants),
            "--dcat-sources-yaml",
            str(catalogues),
        ],
    )
    assert result.exit_code == 0
    assert "did:web:rec" in result.output
    assert "test-api" in result.output
