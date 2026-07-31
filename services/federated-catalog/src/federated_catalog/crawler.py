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
    headers: dict[str, str] | None = None,
) -> tuple[str, list[dict]]:
    """Fetch catalog for a single provider via ds-connector /consumer/catalog.

    ``headers`` carries the crawler's own client-credentials token. It is not
    optional in a real deployment: the route requires ``connector.consumer.read``
    (rulebook `C-4`, `C-19`). The crawl used to send nothing and succeeded only
    because the route was unguarded — defects **P0-1** and **P1-3**.

    ``counter_party_id`` is sent so the connector attributes the catalogue to the
    provider being crawled. Without it the connector substitutes its **own**
    ``participant_did`` for every provider, so every crawled dataset was recorded
    as coming from the crawler's participant.

    Returns (provider_id, list_of_dataset_dicts).
    Raises on failure — caller handles and records the error.
    """
    url = f"{connector_url.rstrip('/')}/consumer/catalog"
    payload = {
        "counter_party_address": provider.dsp_address,
        "counter_party_id": provider.id,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers or {})
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


async def crawl_all(
    settings: Settings,
    token_provider=None,
) -> tuple[dict[str, list[dict]], list[CrawlError]]:
    """Crawl all registered providers and DCAT sources. Returns (datasets_by_source, errors)."""
    # One token for the whole cycle, used for both the registry read and every
    # connector call. Minted once rather than per provider: the crawl fans out,
    # and a token request per provider would multiply Keycloak load by the
    # participant count for no gain.
    headers: dict[str, str] | None = None
    if token_provider:
        headers = {"Authorization": f"Bearer {await token_provider()}"}

    if settings.identity_registry_url:
        providers = load_providers_from_registry(settings.identity_registry_url, headers=headers)
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
        tasks.append(
            crawl_provider(
                p,
                settings.connector_url,
                settings.max_datasets_per_provider,
                headers=headers,
            )
        )
        source_ids.append(p.id)

    for s in dcat_sources:
        tasks.append(crawl_dcat_source(s, settings.max_datasets_per_provider))
        source_ids.append(s.id)

    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for source_id, outcome in zip(source_ids, outcomes):
        if isinstance(outcome, Exception):
            err_msg = str(outcome) or type(outcome).__name__
            log.warning("Crawl failed for source %s: %s", source_id, err_msg)
            errors.append(CrawlError(provider_id=source_id, message=err_msg))
        else:
            sid, datasets = outcome
            results[sid] = datasets
            log.info("Crawled %d datasets from %s", len(datasets), sid)

    return results, errors


async def crawl_loop(cache: CatalogCache, settings: Settings, token_provider=None) -> None:
    """Async background task: wait startup_delay, then crawl on interval."""
    log.info(
        "Federated catalog crawler starting (startup delay: %ds, interval: %ds)",
        settings.startup_delay,
        settings.crawl_interval,
    )
    await asyncio.sleep(settings.startup_delay)

    while True:
        log.info("Starting catalog crawl cycle…")
        delay = settings.crawl_interval
        try:
            datasets_by_provider, errors = await crawl_all(settings, token_provider=token_provider)
            applied = cache.swap(datasets_by_provider, errors)
            total = sum(len(v) for v in datasets_by_provider.values())
            if applied:
                log.info(
                    "Crawl complete: %d datasets from %d providers (%d errors)",
                    total,
                    len(datasets_by_provider),
                    len(errors),
                )
            else:
                # Reached nothing. The usual cause is ordering, not breakage: the
                # crawler starts `startup_delay` after itself, which on a cold
                # boot can be before ds-connector or the EDC behind it accepts
                # connections. Waiting a full interval to find out would leave the
                # catalogue empty for minutes after everything came up healthy.
                delay = min(settings.crawl_retry_delay, settings.crawl_interval)
                log.warning(
                    "Crawl reached no source (%d errors) — keeping the previous "
                    "catalogue and retrying in %ds",
                    len(errors),
                    delay,
                )
        except Exception as exc:
            log.exception("Crawl loop encountered an unexpected error: %s", exc)
        await asyncio.sleep(delay)
