"""fc-cli — Federated Catalog CLI for the dataspaces platform."""
from __future__ import annotations

import asyncio
import logging
import sys

import httpx
import typer

from ..cache import CatalogCache
from ..config import Settings
from ..crawler import crawl_all, crawl_dcat_source
from ..registry import load_dcat_sources
from .mapper import dcat_to_edc_payloads

app = typer.Typer(name="fc-cli", help="Federated Catalog CLI")
log = logging.getLogger(__name__)


@app.command()
def sync(
    sources: str = typer.Option(
        ...,
        help="Path to catalogues.yaml with DCAT source definitions.",
    ),
    connector_url: str = typer.Option(
        "http://ds-connector:30001",
        help="ds-connector base URL for registering assets.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fetch DCAT sources and register datasets in EDC via ds-connector."""
    _setup_logging(verbose)
    asyncio.run(_sync(sources, connector_url))


async def _sync(sources_path: str, connector_url: str) -> None:
    dcat_sources = load_dcat_sources(sources_path)
    if not dcat_sources:
        typer.echo(f"No DCAT sources found in {sources_path}")
        raise typer.Exit(1)

    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for source in dcat_sources:
        typer.echo(f"Fetching {source.id} ({source.url})…")
        try:
            source_id, datasets = await crawl_dcat_source(source, max_datasets=500)
        except Exception as exc:
            msg = f"{source.id}: fetch failed — {exc}"
            typer.echo(f"  ERROR: {msg}", err=True)
            errors.append(msg)
            continue

        typer.echo(f"  Found {len(datasets)} datasets")
        for ds in datasets:
            payloads = dcat_to_edc_payloads(ds, source.defaults)
            if payloads is None:
                ds_id = ds.get("@id") or ds.get("id") or "unknown"
                skipped.append(ds_id)
                continue

            ds_id = payloads["asset"]["@id"]
            try:
                await _register_in_edc(connector_url, payloads)
                synced.append(ds_id)
                typer.echo(f"  ✓ {ds_id}")
            except Exception as exc:
                msg = f"{ds_id}: {exc}"
                typer.echo(f"  ✗ {ds_id}: {exc}", err=True)
                errors.append(msg)

    typer.echo(f"\nDone: {len(synced)} synced, {len(skipped)} skipped, {len(errors)} errors")
    if errors:
        raise typer.Exit(1)


async def _register_in_edc(connector_url: str, payloads: dict) -> None:
    """Register asset, policy, and contract definition via ds-connector /provider/sync."""
    url = f"{connector_url.rstrip('/')}/provider/sync"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payloads)
        resp.raise_for_status()


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
    datasets_by_source, errs = asyncio.run(crawl_all(settings))
    cache.swap(datasets_by_source, errs)

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
