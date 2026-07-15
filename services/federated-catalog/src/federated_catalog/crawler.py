"""Background crawl loop — fetches catalogs from all registered providers."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .cache import CatalogCache, CrawlError
from .config import Settings
from .registry import DcatSource, Provider, load_dcat_sources, load_providers, load_providers_from_registry

log = logging.getLogger(__name__)


async def crawl_provider(
    provider: Provider,
    connector_url: str,
    max_datasets: int,
) -> tuple[str, list[dict]]:
    """Fetch catalog for a single provider via ds-connector /consumer/catalog.

    Returns (provider_id, list_of_dataset_dicts).
    Raises on failure — caller handles and records the error.
    """
    url = f"{connector_url.rstrip('/')}/consumer/catalog"
    payload = {"counter_party_address": provider.dsp_address}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Extract dcat:dataset array from the catalog response
    datasets: list[dict] = []
    raw_datasets = data.get("dcat:dataset") or data.get("dataset") or []
    if isinstance(raw_datasets, dict):
        raw_datasets = [raw_datasets]

    for ds in raw_datasets[:max_datasets]:
        # Tag with publisher DID if not already set
        if not ds.get("dct:publisher"):
            ds["dct:publisher"] = {"@id": provider.id}
        datasets.append(ds)

    return provider.id, datasets


async def crawl_dcat_source(
    source: DcatSource,
    max_datasets: int,
) -> tuple[str, list[dict]]:
    """Fetch a DCAT-AP catalogue directly via GET.

    Returns (source_id, list_of_dataset_dicts).
    Raises on failure — caller handles and records the error.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(source.url, headers={"Accept": "application/ld+json"})
        resp.raise_for_status()
        data = resp.json()

    raw_datasets = data.get("dcat:dataset") or data.get("dataset") or []
    if isinstance(raw_datasets, dict):
        raw_datasets = [raw_datasets]

    datasets: list[dict] = []
    for ds in raw_datasets[:max_datasets]:
        if not ds.get("dct:publisher"):
            ds["dct:publisher"] = {"@id": source.id}
        datasets.append(ds)

    return source.id, datasets


async def crawl_all(settings: Settings) -> tuple[dict[str, list[dict]], list[CrawlError]]:
    """Crawl all registered providers and DCAT sources. Returns (datasets_by_source, errors)."""
    if settings.identity_registry_url:
        providers = load_providers_from_registry(settings.identity_registry_url)
    else:
        providers = load_providers(settings.participants_yaml)
    dcat_sources = load_dcat_sources(settings.dcat_sources_yaml)

    if not providers and not dcat_sources:
        log.warning("No providers or DCAT sources configured — catalog will be empty")
        return {}, []

    results: dict[str, list[dict]] = {}
    errors: list[CrawlError] = []

    tasks: list[asyncio.Task] = []
    source_ids: list[str] = []

    for p in providers:
        tasks.append(crawl_provider(p, settings.connector_url, settings.max_datasets_per_provider))
        source_ids.append(p.id)

    for s in dcat_sources:
        tasks.append(crawl_dcat_source(s, settings.max_datasets_per_provider))
        source_ids.append(s.id)

    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for source_id, outcome in zip(source_ids, outcomes):
        if isinstance(outcome, Exception):
            log.warning("Crawl failed for source %s: %s", source_id, outcome)
            errors.append(CrawlError(provider_id=source_id, message=str(outcome)))
        else:
            sid, datasets = outcome
            results[sid] = datasets
            log.info("Crawled %d datasets from %s", len(datasets), sid)

    return results, errors


async def crawl_loop(cache: CatalogCache, settings: Settings) -> None:
    """Async background task: wait startup_delay, then crawl on interval."""
    log.info(
        "Federated catalog crawler starting (startup delay: %ds, interval: %ds)",
        settings.startup_delay,
        settings.crawl_interval,
    )
    await asyncio.sleep(settings.startup_delay)

    while True:
        log.info("Starting catalog crawl cycle…")
        try:
            datasets_by_provider, errors = await crawl_all(settings)
            cache.swap(datasets_by_provider, errors)
            total = sum(len(v) for v in datasets_by_provider.values())
            log.info(
                "Crawl complete: %d datasets from %d providers (%d errors)",
                total,
                len(datasets_by_provider),
                len(errors),
            )
        except Exception as exc:
            log.exception("Crawl loop encountered an unexpected error: %s", exc)
        await asyncio.sleep(settings.crawl_interval)
