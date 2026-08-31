"""`E2E-12` — an empty catalogue must name its own cause.

The flow's verdict used to be decided by where the catalogue's fixed crawl
interval fell relative to the run: the same build passed three times and failed
once on a stack nobody had touched. And when it did fail, the one message it had
named two mutually exclusive causes — *"the crawler reached no provider, or none
published"* — which sent two sessions after a crawler that was working.

Both are fixed in `_await_a_crawl_of_our_own`, and both are pinned here. The
live half cannot be unit-tested; the reasoning that turns an observation into a
verdict can, and it is the half that was wrong.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.catalog_discovery import CatalogDiscoveryFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr("ds_e2e.flows.catalog_discovery.time.sleep", lambda _: None)


def _flow(settings, responses):
    """A flow whose GETs are served from a url-substring → payload table.

    `responses` values may be a single payload or a list consumed in order, so a
    test can say "meta answers this, then this" — which is how a crawl
    completing mid-wait is expressed."""
    http = MagicMock(spec=HttpClient)
    state = {k: (list(v) if isinstance(v, list) else v) for k, v in responses.items()}

    def _get(url, **kwargs):
        for key, value in state.items():
            if key in url:
                if isinstance(value, list):
                    return value.pop(0) if len(value) > 1 else value[0]
                return value
        raise AssertionError(f"unexpected GET {url}")

    http.get.side_effect = _get
    return CatalogDiscoveryFlow(settings, http)


def _meta(**overrides):
    meta = {
        "dataset_count": 0,
        "providers": ["did:web:rec.test", "did:web:grid.test"],
        "last_crawl": "2026-08-06T12:00:00+00:00",
        "crawl_errors": [],
        "crawl_interval_seconds": 300,
    }
    meta.update(overrides)
    return meta


def _catalog(datasets):
    return {
        "@context": {},
        "@type": "dcat:Catalog",
        "dcat:dataset": datasets,
        "hydra:totalItems": len(datasets),
    }


# ── the timing dependency ────────────────────────────────────────────────────


def test_an_empty_catalogue_waits_for_a_crawl_this_run_did_not_inherit(settings):
    """The `E2E-12` fix: assert on a projection the run watched being built.

    An empty catalogue on arrival is not a verdict — it may simply be the last
    cycle having run before `e2e:prepare` published. So the flow waits for a
    `last_crawl` later than the one it found, and only then decides."""
    flow = _flow(
        settings,
        {
            "/catalog/meta": [_meta(), _meta(last_crawl="2026-08-06T12:05:00+00:00")],
            "/catalog": _catalog([{"@id": "datasets.silver.meters_15m"}]),
        },
    )

    result = FlowResult(flow_name="catalog-discovery")
    datasets, catalog = flow._await_a_crawl_of_our_own(result, {})

    assert datasets and len(datasets) == 1
    assert result.steps[-1].name == "crawl postdates this run"
    assert result.steps[-1].status == "PASS"


def test_a_crawl_loop_that_never_completes_a_cycle_fails(settings, monkeypatch):
    """The one thing that *is* a crawler failure, and it is now the only case
    reported as one: the interval elapsed and no new cycle landed."""
    clock = iter([float(n) for n in range(0, 4000, 20)])
    monkeypatch.setattr(
        "ds_e2e.flows.catalog_discovery.time.monotonic", lambda: next(clock)
    )
    flow = _flow(settings, {"/catalog/meta": _meta()})

    result = FlowResult(flow_name="catalog-discovery")
    datasets, _ = flow._await_a_crawl_of_our_own(result, {})

    assert datasets is None
    assert result.steps[-1].status == "FAIL"
    assert "crawl loop is not running" in result.steps[-1].detail


def test_the_wait_is_derived_from_the_catalogue_not_from_a_local_constant(settings):
    """A catalogue that does not say how often it refreshes cannot be waited on.

    Failing here rather than guessing is the point: a hardcoded interval in the
    harness is a second copy of a number the service owns, and it drifts."""
    flow = _flow(settings, {"/catalog/meta": _meta(crawl_interval_seconds=None)})

    result = FlowResult(flow_name="catalog-discovery")
    datasets, _ = flow._await_a_crawl_of_our_own(result, {})

    assert datasets is None
    assert "does not report its crawl interval" in result.steps[-1].detail


# ── attribution: an empty catalogue is not one failure ───────────────────────


def test_a_still_empty_catalogue_with_no_errors_blames_the_provider_sync(settings):
    """**The message that sent two sessions after the wrong component.**

    Every provider crawled, no errors, nothing published: the crawler did its
    job and the providers had nothing to give. Measured live — the crawler ran
    on schedule at 14:11, 14:16 and 14:21 while the providers' contract
    definitions had been wiped (`E2E-17`)."""
    flow = _flow(
        settings,
        {
            "/catalog/meta": [_meta(), _meta(last_crawl="2026-08-06T12:05:00+00:00")],
            "/catalog": _catalog([]),
        },
    )

    result = FlowResult(flow_name="catalog-discovery")
    datasets, _ = flow._await_a_crawl_of_our_own(result, {})

    assert datasets is None
    detail = result.steps[-1].detail
    assert "provider-sync failure" in detail
    assert "not a" in detail and "catalogue one" in detail


def test_a_still_empty_catalogue_with_crawl_errors_blames_the_crawler(settings):
    flow = _flow(
        settings,
        {
            "/catalog/meta": [
                _meta(),
                _meta(
                    last_crawl="2026-08-06T12:05:00+00:00",
                    crawl_errors=[
                        {"provider_id": "did:web:rec.test", "message": "timeout"}
                    ],
                ),
            ],
            "/catalog": _catalog([]),
        },
    )

    result = FlowResult(flow_name="catalog-discovery")
    flow._await_a_crawl_of_our_own(result, {})

    assert "crawler or connectivity" in result.steps[-1].detail
    assert result.steps[-1].data["crawl_errors"]


def test_a_still_empty_catalogue_with_no_providers_blames_the_registry(settings):
    """Nobody to crawl is a registry answer, not a catalogue one."""
    flow = _flow(
        settings,
        {
            "/catalog/meta": [
                _meta(),
                _meta(last_crawl="2026-08-06T12:05:00+00:00", providers=[]),
            ],
            "/catalog": _catalog([]),
        },
    )

    result = FlowResult(flow_name="catalog-discovery")
    flow._await_a_crawl_of_our_own(result, {})

    assert "no providers at all" in result.steps[-1].detail


def test_the_three_empty_cases_report_different_things(settings):
    """They are different findings, so they must not share a message.

    The old single message named two of them at once and omitted the third,
    which is how it managed to be wrong whichever one had happened."""

    def _detail(second_meta):
        flow = _flow(
            settings,
            {
                "/catalog/meta": [_meta(), second_meta],
                "/catalog": _catalog([]),
            },
        )
        result = FlowResult(flow_name="catalog-discovery")
        flow._await_a_crawl_of_our_own(result, {})
        return result.steps[-1].detail

    fresh = "2026-08-06T12:05:00+00:00"
    details = {
        _detail(_meta(last_crawl=fresh)),
        _detail(_meta(last_crawl=fresh, providers=[])),
        _detail(
            _meta(
                last_crawl=fresh,
                crawl_errors=[{"provider_id": "x", "message": "boom"}],
            )
        ),
    }
    assert len(details) == 3
