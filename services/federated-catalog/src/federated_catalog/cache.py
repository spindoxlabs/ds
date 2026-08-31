"""In-memory catalog cache with atomic swap on each crawl cycle."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class CrawlError:
    provider_id: str
    message: str
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class SourceEndpoint:
    """Where a crawled source's datasets are actually served from.

    The index serves nothing itself — it republishes descriptions — so this is
    what its ``dcat:DataService`` entries point at (`DSSC-PUB-41`). ``conforms_to``
    is the DSP protocol IRI for a participant crawled over DSP and ``None`` for a
    plain DCAT-AP source, because only the first is negotiable.
    """

    url: str
    conforms_to: str | None = None


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
        # source_id → where that source's datasets are served from
        self._endpoints: dict[str, SourceEndpoint] = {}

    def swap(
        self,
        datasets_by_provider: dict[str, list[dict]],
        errors: list[CrawlError],
        endpoints: dict[str, SourceEndpoint] | None = None,
    ) -> bool:
        """Atomically replace the catalog contents after a crawl cycle.

        Returns whether the contents were replaced.

        **A crawl that reached no source at all is not a crawl.** It is evidence
        about the network, not about the catalogue, and it must not be published
        as "the catalogue is empty, as of now":

        - Any previously crawled datasets are **kept**. Discarding good data
          because one cycle could not connect turns a transient outage into an
          empty federated catalogue for a full interval.
        - ``last_crawl`` is **not advanced**, so a freshness check cannot pass on
          the strength of an attempt that returned nothing. Reporting a fresh,
          empty catalogue is the worst of both: it reads as "the provider
          published nothing" when the truth is "we could not ask".

        The errors are always recorded, so ``/catalog/meta`` shows what happened
        either way.

        A provider that is reachable and genuinely publishes nothing is a
        different case and swaps normally — it appears in *datasets_by_provider*
        with an empty list, so the catalogue correctly becomes empty.
        """
        reached_nobody = not datasets_by_provider and bool(errors)
        if reached_nobody:
            with self._lock:
                self._crawl_errors = errors
            return False

        # An entry with no IRI is dropped from **both** views, not just the flat
        # one. Keeping it in the per-provider bucket alone made one dataset three
        # different things at once: findable through `POST /catalog/search` with
        # a `provider` filter, unresolvable through `GET /catalog/{iri}` because
        # there is no IRI to ask for, and absent from `dataset_count` and from
        # `GET /catalog`. A consumer cannot negotiate for something it cannot
        # name, so an entry with no `@id` is not an offering — it is a
        # malformed record, and the catalogue says so on `/catalog/meta`.
        merged: dict[str, dict] = {}
        kept: dict[str, list[dict]] = {}
        dropped = 0
        for provider_id, datasets in datasets_by_provider.items():
            kept_for_provider: list[dict] = []
            for ds in datasets:
                iri = ds.get("@id") or ds.get("id") or ""
                if not iri:
                    dropped += 1
                    continue
                merged[iri] = ds
                kept_for_provider.append(ds)
            kept[provider_id] = kept_for_provider

        errors = list(errors)
        if dropped:
            errors.append(
                CrawlError(
                    provider_id="*",
                    message=f"{dropped} crawled dataset(s) dropped: no @id or id",
                )
            )

        with self._lock:
            self._datasets_by_provider = kept
            self._by_iri = merged
            self._last_crawl = datetime.now(UTC)
            self._crawl_errors = errors
            self._endpoints = dict(endpoints or {})
        return True

    def all_datasets(self) -> list[dict]:
        with self._lock:
            return list(self._by_iri.values())

    def dataset_ids_by_source(self) -> dict[str, list[str]]:
        """source_id → the IRIs currently published for it."""
        with self._lock:
            return {
                source_id: [
                    iri for ds in datasets if (iri := ds.get("@id") or ds.get("id"))
                ]
                for source_id, datasets in self._datasets_by_provider.items()
            }

    def endpoints(self) -> dict[str, SourceEndpoint]:
        with self._lock:
            return dict(self._endpoints)

    def source_of(self, iri: str) -> str | None:
        """Which crawled source published this IRI, if any."""
        with self._lock:
            for source_id, datasets in self._datasets_by_provider.items():
                for ds in datasets:
                    if (ds.get("@id") or ds.get("id")) == iri:
                        return source_id
        return None

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
                # The identifier is searchable too. A consumer who knows a
                # dataset only as `datasets.silver.meters_15m` — which is how it
                # is advertised, referenced in an offer and named in a
                # negotiation — must be able to find it by that name; matching
                # only prose made the catalogue's own IRIs unsearchable.
                haystack = [
                    str(ds.get("@id") or ""),
                    str(ds.get("dct:identifier") or ds.get("identifier") or ""),
                    str(ds.get("dct:title") or ds.get("title") or ""),
                    str(ds.get("dct:description") or ds.get("description") or ""),
                ]
                if not any(q_lower in field.lower() for field in haystack):
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
                "last_crawl": (
                    self._last_crawl.isoformat() if self._last_crawl else None
                ),
                "crawl_errors": [
                    {"provider_id": e.provider_id, "message": e.message, "at": e.at}
                    for e in self._crawl_errors
                ],
            }

    @property
    def last_crawl_iso(self) -> str | None:
        with self._lock:
            return self._last_crawl.isoformat() if self._last_crawl else None

    @property
    def cache_age_seconds(self) -> float | None:
        with self._lock:
            if self._last_crawl is None:
                return None
            return (datetime.now(UTC) - self._last_crawl).total_seconds()
