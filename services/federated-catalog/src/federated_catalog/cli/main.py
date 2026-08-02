"""fc-cli — Federated Catalog CLI for the dataspaces platform.

**Read-only, and that is the architecture rather than an omission.** This
dataspace's recorded catalogue decision is *distributed catalogues with an
optional federated index*, pull-synchronised (`docs/rulebook/catalogue-and-metadata.md`
§1, answering `DSSC-PUB-06`/`-46`). Publication belongs to the Participant Agent
(`DSSC-PUB-12`) and only an authenticated, authorized **data provider** may
publish its own offering (`DSSC-PUB-13`/`-14`/`-19`).

A `sync` command lived here that pushed crawled DCAT-AP datasets into *this*
participant's EDC — the push/broker model of the blueprint's centralized option,
which this dataspace did not choose. It is deleted rather than fixed; see the
ledger's `services/federated-catalog` decisions. An external DCAT-AP catalogue is
folded in through the **read** side (`crawl_dcat_source`), where the index is
advisory and claims no authority over what it republishes.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import typer

from ..cache import CatalogCache
from ..config import Settings
from ..crawler import crawl_all
from ..registry import load_dcat_sources

app = typer.Typer(name="fc-cli", help="Federated Catalog CLI")
log = logging.getLogger(__name__)


@app.command()
def crawl(
    participants_yaml: str = typer.Option(
        "",
        help="Path to participants.yaml (DSP providers).",
    ),
    dcat_sources_yaml: str = typer.Option(
        "",
        help="Path to catalogues.yaml (DCAT sources).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Trigger one crawl cycle (read-only cache refresh) and print results."""
    _setup_logging(verbose)
    settings = Settings()
    if participants_yaml:
        settings.participants_yaml = participants_yaml
    if dcat_sources_yaml:
        settings.dcat_sources_yaml = dcat_sources_yaml

    cache = CatalogCache()
    datasets_by_source, errs, endpoints = asyncio.run(crawl_all(settings))
    cache.swap(datasets_by_source, errs, endpoints)

    total = sum(len(v) for v in datasets_by_source.values())
    typer.echo(f"Crawled {total} datasets from {len(datasets_by_source)} sources")
    for src_id, ds_list in datasets_by_source.items():
        typer.echo(f"  {src_id}: {len(ds_list)} datasets")
    if errs:
        typer.echo(f"\n{len(errs)} errors:")
        for e in errs:
            typer.echo(f"  {e.provider_id}: {e.message}", err=True)
        raise typer.Exit(1)


@app.command()
def status(
    participants_yaml: str = typer.Option(
        "",
        help="Path to participants.yaml (DSP providers).",
    ),
    dcat_sources_yaml: str = typer.Option(
        "",
        help="Path to catalogues.yaml (DCAT sources).",
    ),
) -> None:
    """Show configured sources and cached catalogue stats."""
    from ..registry import load_providers

    settings = Settings()
    if participants_yaml:
        settings.participants_yaml = participants_yaml
    if dcat_sources_yaml:
        settings.dcat_sources_yaml = dcat_sources_yaml

    providers = load_providers(settings.participants_yaml)
    dcat_sources = load_dcat_sources(settings.dcat_sources_yaml)

    typer.echo("DSP providers:")
    if providers:
        for p in providers:
            typer.echo(f"  {p.id} → {p.dsp_address}")
    else:
        typer.echo("  (none)")

    typer.echo("\nDCAT sources:")
    if dcat_sources:
        for s in dcat_sources:
            typer.echo(f"  {s.id} → {s.url} (type: {s.type})")
    else:
        typer.echo("  (none)")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def run() -> None:
    app()
