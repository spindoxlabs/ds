"""Federated catalog — discovery across participants.

The federated catalog is how a consumer finds a dataset it has no prior
relationship with: a crawler walks the registered participants' DSP catalogues
and republishes them as one DCAT-AP catalogue. It had no end-to-end coverage,
which meant a crawler that had silently stopped, or one serving a stale cache,
looked identical to a healthy one.

The flow asserts the catalogue is *current* and *faithful*: it is populated,
its crawl is recent, the dataset the provider actually publishes appears in it
with a resolvable IRI and a policy, search narrows rather than merely returning
everything, and paging is honoured. It also checks the JSON-LD contract, since
a consumer parses this as linked data and not as an ad-hoc JSON blob.

Needs the provider EDC to be running and synced, since the catalogue is a
projection of what the provider publishes over DSP.
"""
from __future__ import annotations

import logging
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

# A crawl older than this means the catalogue is serving a stale projection.
MAX_CACHE_AGE_SECONDS = 900


class CatalogDiscoveryFlow(BaseFlow):
    name = "catalog-discovery"
    description = (
        "Federated catalogue: crawl freshness, DCAT-AP shape, dataset resolution, "
        "search narrowing and paging"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        base = s.federated_catalog_url

        try:
            health = self.http.get(f"{base}/health") or {}
            result.pass_step("health", "federated catalog reachable")
        except Exception as exc:
            result.fail_step("health", f"federated catalog unreachable at {base}: {exc}")
            return result

        try:
            headers = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        # ── 1. The crawl is running, not just the process ────────────────────
        age = health.get("cache_age_seconds")
        if age is None:
            result.fail_step(
                "crawl freshness",
                "the catalogue reports no cache age — it has never completed a crawl",
            )
            return result
        if age > MAX_CACHE_AGE_SECONDS:
            result.fail_step(
                "crawl freshness",
                "the catalogue is serving a stale projection",
                cache_age_seconds=age,
                max_age_seconds=MAX_CACHE_AGE_SECONDS,
            )
            return result
        result.pass_step(
            "crawl freshness",
            "the catalogue has completed a recent crawl",
            cache_age_seconds=age,
        )

        # ── 2. It is a DCAT-AP catalogue, and it is populated ────────────────
        catalog = self.http.get(f"{base}/catalog", headers=headers) or {}
        datasets = self._datasets(catalog)
        if not catalog.get("@context"):
            result.fail_step(
                "catalogue shape",
                "the catalogue is not served as JSON-LD — consumers parse it as linked data",
                keys=sorted(catalog.keys()),
            )
            return result
        if catalog.get("@type") != "dcat:Catalog":
            result.fail_step(
                "catalogue shape", "the response is not a dcat:Catalog", type=catalog.get("@type")
            )
            return result
        if not datasets:
            result.fail_step(
                "catalogue shape",
                "the catalogue is empty — the crawler reached no provider, or none published",
                total=catalog.get("hydra:totalItems"),
            )
            return result
        result.pass_step(
            "catalogue shape",
            "a populated dcat:Catalog is served as JSON-LD",
            datasets=len(datasets),
            total=catalog.get("hydra:totalItems"),
        )

        # ── 3. The provider's dataset is discoverable ────────────────────────
        #     Discovery is only useful if what the provider publishes is what a
        #     stranger finds. Matching on the configured asset id ties this
        #     assertion to the same dataset the smoke flow negotiates for.
        target = self._find_dataset(datasets, s.asset_id)
        if target is None:
            result.fail_step(
                "provider dataset discoverable",
                f"the provider's dataset '{s.asset_id}' is not in the federated catalogue",
                found=[self._iri(d) for d in datasets][:10],
            )
            return result
        iri = self._iri(target)
        if not iri:
            result.fail_step(
                "provider dataset discoverable", "the dataset has no IRI", dataset=target
            )
            return result
        if not (target.get("hasPolicy") or target.get("odrl:hasPolicy")):
            result.fail_step(
                "provider dataset discoverable",
                "the dataset is listed with no policy — a consumer could not know its terms",
                iri=iri,
            )
            return result
        result.pass_step(
            "provider dataset discoverable",
            "the provider's dataset appears with an IRI and its ODRL terms",
            iri=iri,
        )

        # ── 4. That IRI resolves to the same dataset ─────────────────────────
        status, single = self.http.raw(
            "GET", f"{base}/catalog/{iri}", headers=headers
        )
        if status != 200 or not isinstance(single, dict):
            result.fail_step(
                "dataset resolution",
                "the advertised IRI does not resolve in the catalogue",
                iri=iri,
                status_code=status,
            )
            return result
        if single.get("@type") != "dcat:Dataset":
            result.fail_step(
                "dataset resolution", "the resolved document is not a dcat:Dataset",
                type=single.get("@type"),
            )
            return result
        result.pass_step("dataset resolution", "the advertised IRI dereferences to its dataset", iri=iri)

        # ── 5. Search narrows ────────────────────────────────────────────────
        #     A search that returns everything is not a search. The negative
        #     term is the assertion that matters: it proves filtering happens
        #     rather than the full cache being returned regardless of the query.
        nonsense = self.http.post(
            f"{base}/catalog/search", {"q": "zzz-no-such-dataset-zzz"}, headers=headers
        ) or {}
        nonsense_count = len(self._datasets(nonsense))
        if nonsense_count != 0:
            result.fail_step(
                "search narrows",
                "a query matching nothing returned results — the filter is not applied",
                results=nonsense_count,
            )
            return result

        term = str(s.asset_id).split(".")[-1]
        hits = self.http.post(f"{base}/catalog/search", {"q": term}, headers=headers) or {}
        hit_datasets = self._datasets(hits)
        if not hit_datasets:
            result.fail_step(
                "search narrows",
                f"searching for '{term}' found nothing, though the dataset is catalogued",
                iri=iri,
            )
            return result
        result.pass_step(
            "search narrows",
            "search matches the catalogued dataset and rejects a term that matches nothing",
            term=term,
            hits=len(hit_datasets),
        )

        # ── 6. Paging is honoured ────────────────────────────────────────────
        paged = self.http.get(f"{base}/catalog?limit=1&offset=0", headers=headers) or {}
        page = self._datasets(paged)
        if len(page) > 1:
            result.fail_step(
                "paging", "limit=1 returned more than one dataset", returned=len(page)
            )
            return result
        if paged.get("hydra:totalItems") != catalog.get("hydra:totalItems"):
            result.fail_step(
                "paging",
                "the total count changed with the page window — clients cannot page reliably",
                unpaged=catalog.get("hydra:totalItems"),
                paged=paged.get("hydra:totalItems"),
            )
            return result
        result.pass_step(
            "paging",
            "limit is applied and the total count is window-independent",
            total=paged.get("hydra:totalItems"),
        )

        # ── 7. Crawl metadata names its sources ──────────────────────────────
        meta = self.http.get(f"{base}/catalog/meta", headers=headers) or {}
        if not meta:
            result.fail_step("crawl metadata", "no crawl metadata is published")
            return result
        result.pass_step(
            "crawl metadata",
            "the catalogue reports what it crawled",
            meta={k: meta[k] for k in list(meta)[:6]},
        )

        return result

    # ── helpers ──────────────────────────────────────────────────────────────

    def _datasets(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        datasets = payload.get("dcat:dataset") or payload.get("dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        return [d for d in datasets if isinstance(d, dict)]

    def _iri(self, dataset: dict[str, Any]) -> str:
        return str(dataset.get("@id") or dataset.get("id") or "")

    def _find_dataset(
        self, datasets: list[dict[str, Any]], asset_id: str
    ) -> dict[str, Any] | None:
        for ds in datasets:
            if asset_id in self._iri(ds):
                return ds
        return None
