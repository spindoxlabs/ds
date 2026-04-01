"""Background crawl loop — fetches catalogs from all registered providers."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .cache import CatalogCache, CrawlError
from .config import Settings
from .registry import Provider, load_providers

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


async def crawl_all(settings: Settings) -> tuple[dict[str, list[dict]], list[CrawlError]]:
    """Crawl all registered providers. Returns (datasets_by_provider, errors)."""
    providers = load_providers(settings.participants_yaml)
    if not providers:
        log.warning("No providers found in %s — catalog will be empty", settings.participants_yaml)
        return {}, []

    results: dict[str, list[dict]] = {}
    errors: list[CrawlError] = []

    tasks = [
        crawl_provider(p, settings.connector_url, settings.max_datasets_per_provider)
        for p in providers
    ]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for provider, outcome in zip(providers, outcomes):
        if isinstance(outcome, Exception):
            log.warning("Crawl failed for provider %s: %s", provider.id, outcome)
            errors.append(CrawlError(provider_id=provider.id, message=str(outcome)))
        else:
            pid, datasets = outcome
            results[pid] = datasets
            log.info("Crawled %d datasets from %s", len(datasets), provider.id)

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
