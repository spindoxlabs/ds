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
import time
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

# A crawl older than this means the catalogue is serving a stale projection.
MAX_CACHE_AGE_SECONDS = 900

#: Slack over the catalogue's own crawl interval before giving up on a new
#: cycle. Covers the crawl's own duration and the poll granularity — this is
#: waiting for a **scheduled** event, so it must not fail on the schedule
#: merely being met exactly.
CRAWL_WAIT_MARGIN_S = 60

#: How often to re-read `/catalog/meta` while waiting for that cycle.
CRAWL_POLL_S = 5.0


class CatalogDiscoveryFlow(BaseFlow):
    name = "catalog-discovery"
    description = (
        "Federated catalogue: crawl freshness, DCAT-AP shape, dataset resolution, "
        "search narrowing and paging"
    )
    rules = ("C-1", "C-3", "C-18", "C-19")

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        base = s.federated_catalog_url

        try:
            health = self.http.get(f"{base}/health") or {}
            result.pass_step("health", "federated catalog reachable")
        except Exception as exc:
            result.fail_step(
                "health", f"federated catalog unreachable at {base}: {exc}"
            )
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
                "catalogue shape",
                "the response is not a dcat:Catalog",
                type=catalog.get("@type"),
            )
            return result
        if not datasets:
            # **An empty catalogue is not one failure, it is four** (`E2E-12`),
            # and the catalogue already knows which. Waiting for a crawl this
            # run did not see is what removes the timing dependency; naming the
            # cause is what stops the next reader debugging the crawler when the
            # crawler is fine.
            retried, catalog = self._await_a_crawl_of_our_own(result, headers)
            if retried is None:
                return result
            datasets = retried
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
                "provider dataset discoverable",
                "the dataset has no IRI",
                dataset=target,
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

        # ── 3b. Its operands survived the round trip ─────────────────────────
        unreadable = _unreadable_operands(target)
        if unreadable:
            result.fail_step(
                "policy operands are readable",
                "a right operand reached the catalogue as a stringified object "
                "instead of a value — a counterparty cannot read these terms",
                iri=iri,
                operands=unreadable[:3],
            )
            return result
        result.pass_step(
            "policy operands are readable",
            "every right operand published for the dataset is a value, not an "
            "object dump",
            iri=iri,
        )

        # ── 4. That IRI resolves to the same dataset ─────────────────────────
        status, single = self.http.raw("GET", f"{base}/catalog/{iri}", headers=headers)
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
                "dataset resolution",
                "the resolved document is not a dcat:Dataset",
                type=single.get("@type"),
            )
            return result
        result.pass_step(
            "dataset resolution",
            "the advertised IRI dereferences to its dataset",
            iri=iri,
        )

        # ── 5. Search narrows ────────────────────────────────────────────────
        #     A search that returns everything is not a search. The negative
        #     term is the assertion that matters: it proves filtering happens
        #     rather than the full cache being returned regardless of the query.
        nonsense = (
            self.http.post(
                f"{base}/catalog/search",
                {"q": "zzz-no-such-dataset-zzz"},
                headers=headers,
            )
            or {}
        )
        nonsense_count = len(self._datasets(nonsense))
        if nonsense_count != 0:
            result.fail_step(
                "search narrows",
                "a query matching nothing returned results — the filter is not applied",
                results=nonsense_count,
            )
            return result

        term = str(s.asset_id).split(".")[-1]
        hits = (
            self.http.post(f"{base}/catalog/search", {"q": term}, headers=headers) or {}
        )
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

    # ── an empty catalogue, attributed ───────────────────────────────────────

    def _await_a_crawl_of_our_own(
        self, result: FlowResult, headers: dict[str, str]
    ) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
        """Wait for a crawl this run did not inherit, then say what is wrong.

        **The `E2E-12` fix, and both halves matter.**

        *Timing.* The catalogue refreshes on a fixed interval, so a flow that
        asserts on whatever the last cycle happened to catch has a verdict
        decided by where that boundary fell — the same build passed three times
        and failed once on a stack nobody touched. Waiting for a crawl whose
        timestamp is later than this step began removes that: the catalogue
        being asserted on is one that ran *after* `e2e:prepare` published.

        Not "a crawl it caused", which is what the row asked for — there is no
        way to cause one, and adding a refresh route to make a test convenient
        is a route a deployment then has to guard. Postdating the run is the
        same guarantee for this purpose, and the wait is bounded by the
        interval the catalogue itself reports.

        *Attribution.* An empty catalogue had one message naming two causes —
        *"the crawler reached no provider, or none published"* — and the
        catalogue already distinguishes them: `providers` says who was crawled,
        `crawl_errors` says who failed. It sent the last two sessions after the
        crawler, which was working correctly the whole time; the providers had
        stopped publishing (`E2E-17`).
        """
        s = self.settings
        base = s.federated_catalog_url
        meta = self.http.get(f"{base}/catalog/meta", headers=headers) or {}
        before = str(meta.get("last_crawl") or "")
        interval = int(meta.get("crawl_interval_seconds") or 0)
        if not interval:
            result.fail_step(
                "catalogue shape",
                "the catalogue is empty and does not report its crawl interval, "
                "so this run cannot tell an unlucky boundary from a real gap",
                meta=meta,
            )
            return None, {}

        deadline = time.monotonic() + interval + CRAWL_WAIT_MARGIN_S
        waited = 0.0
        started = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(min(CRAWL_POLL_S, max(1.0, deadline - time.monotonic())))
            meta = self.http.get(f"{base}/catalog/meta", headers=headers) or {}
            waited = time.monotonic() - started
            if str(meta.get("last_crawl") or "") != before:
                break
        else:
            result.fail_step(
                "catalogue shape",
                f"the catalogue was empty and no new crawl completed in "
                f"{round(waited)}s, longer than its own {interval}s interval — "
                "the crawl loop is not running",
                last_crawl=before or None,
                crawl_interval_seconds=interval,
            )
            return None, {}

        catalog = self.http.get(f"{base}/catalog", headers=headers) or {}
        datasets = self._datasets(catalog)
        if datasets:
            result.pass_step(
                "crawl postdates this run",
                f"the catalogue was empty on arrival and populated after a crawl "
                f"that completed {round(waited)}s into this flow — the verdict "
                "below is about a projection this run watched being built",
                waited_seconds=round(waited),
                datasets=len(datasets),
            )
            return datasets, catalog

        # Still empty after a crawl we watched complete. Now it is a finding,
        # and the meta says whose.
        errors = meta.get("crawl_errors") or []
        providers = meta.get("providers") or []
        if errors:
            result.fail_step(
                "catalogue shape",
                "the catalogue is empty because the crawler could not reach or "
                "read every provider — this is a crawler or connectivity "
                "failure, not a publishing one",
                crawl_errors=errors,
                providers=providers,
            )
        elif not providers:
            result.fail_step(
                "catalogue shape",
                "the catalogue is empty and crawled **no providers at all** — "
                "the participant registry returned nobody to crawl",
            )
        else:
            result.fail_step(
                "catalogue shape",
                "the catalogue is empty although every provider was crawled "
                "without error — the providers published nothing, so this is a "
                "provider-sync failure (`task e2e:sync-providers`) and not a "
                "catalogue one",
                providers=providers,
                waited_seconds=round(waited),
            )
        return None, {}

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


# ── policy operand round trip ────────────────────────────────────────────────
#
# EDC's `JsonObjectFromPolicyTransformer` collapses a multi-valued ODRL right
# operand with `toString()`, so a multi-purpose dataset was published as
#
#   "rightOperand": "[{@value={valueType=STRING, chars=https://…}}, …]"
#
# Enforcement was unaffected — the provider unwraps it in-JVM — which is exactly
# why nothing noticed: the damage is only visible to a reader outside that JVM,
# and nothing read the published policy back. A patched transformer is carried in
# `services/edc-extensions` until the fix lands upstream.
#
# This asserts the *property* (operands are readable values) rather than a
# particular shape, so it also catches the next operand EDC cannot serialise.

_DUMP_MARKERS = ("valueType=", "@value=", "chars=")


def _unreadable_operands(dataset: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("rightOperand"):
                    for item in value if isinstance(value, list) else [value]:
                        text = item if isinstance(item, str) else ""
                        if any(marker in text for marker in _DUMP_MARKERS):
                            found.append(text[:120])
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(dataset)
    return found
