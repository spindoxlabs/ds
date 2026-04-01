"""In-memory catalog cache with atomic swap on each crawl cycle."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CrawlError:
    provider_id: str
    message: str
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CatalogCache:
    """Thread-safe in-memory catalog store.

    Datasets are keyed by their IRI (@id). Atomically replaced after each
    full crawl cycle so readers never see a partial update.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # provider_id → list of dataset dicts
        self._datasets_by_provider: dict[str, list[dict]] = {}
        # flat IRI → dataset dict (merged view)
        self._by_iri: dict[str, dict] = {}
        self._last_crawl: datetime | None = None
        self._crawl_errors: list[CrawlError] = []

    def swap(
        self,
        datasets_by_provider: dict[str, list[dict]],
        errors: list[CrawlError],
    ) -> None:
        """Atomically replace the catalog contents after a crawl cycle."""
        merged: dict[str, dict] = {}
        for datasets in datasets_by_provider.values():
            for ds in datasets:
                iri = ds.get("@id") or ds.get("id") or ""
                if iri:
                    merged[iri] = ds
        with self._lock:
            self._datasets_by_provider = datasets_by_provider
            self._by_iri = merged
            self._last_crawl = datetime.now(timezone.utc)
            self._crawl_errors = errors

    def all_datasets(self) -> list[dict]:
        with self._lock:
            return list(self._by_iri.values())

    def get_by_iri(self, iri: str) -> dict | None:
        with self._lock:
            return self._by_iri.get(iri)

    def search(
        self,
        q: str | None = None,
        access_level: str | None = None,
        provider: str | None = None,
        keywords: list[str] | None = None,
    ) -> list[dict]:
        with self._lock:
            if provider:
                datasets = list(self._datasets_by_provider.get(provider, []))
            else:
                datasets = list(self._by_iri.values())

        results = []
        for ds in datasets:
            if access_level:
                ds_access = ds.get("ds:accessLevel") or ds.get("accessLevel", "")
                if ds_access != access_level:
                    continue
            if q:
                q_lower = q.lower()
                title = str(ds.get("dct:title") or ds.get("title") or "").lower()
                desc = str(ds.get("dct:description") or ds.get("description") or "").lower()
                if q_lower not in title and q_lower not in desc:
                    continue
            if keywords:
                ds_keywords = ds.get("dcat:keyword") or ds.get("keywords") or []
                if isinstance(ds_keywords, str):
                    ds_keywords = [ds_keywords]
                if not any(kw in ds_keywords for kw in keywords):
                    continue
            results.append(ds)
        return results

    @property
    def meta(self) -> dict:
        with self._lock:
            return {
                "dataset_count": len(self._by_iri),
                "providers": list(self._datasets_by_provider.keys()),
                "last_crawl": self._last_crawl.isoformat() if self._last_crawl else None,
                "crawl_errors": [
                    {"provider_id": e.provider_id, "message": e.message, "at": e.at}
                    for e in self._crawl_errors
                ],
            }

    @property
    def cache_age_seconds(self) -> float | None:
        with self._lock:
            if self._last_crawl is None:
                return None
            return (datetime.now(timezone.utc) - self._last_crawl).total_seconds()
