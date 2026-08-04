"""A crawl that reached nothing must not be published as an empty catalogue.

The failure this prevents was reproducible on every cold `task docker:restart`:
the crawler starts `startup_delay` after itself, fires before ds-connector (or
the EDC behind it) accepts connections, records "All connection attempts
failed" — and the unconditional swap then served a *fresh, empty* catalogue for
a full 300s interval. Downstream that reads as "the provider published nothing",
which is the opposite of what happened.
"""
from __future__ import annotations

from federated_catalog.cache import CatalogCache, CrawlError

PROVIDER = "did:web:rec.dataspaces.localhost"


def _datasets(*iris: str) -> list[dict]:
    return [{"@id": iri} for iri in iris]


def test_a_successful_crawl_replaces_and_timestamps():
    cache = CatalogCache()
    assert cache.swap({PROVIDER: _datasets("urn:a")}, []) is True
    assert len(cache.all_datasets()) == 1
    assert cache.meta["last_crawl"] is not None


def test_a_crawl_that_reached_nobody_keeps_the_previous_catalogue():
    cache = CatalogCache()
    cache.swap({PROVIDER: _datasets("urn:a", "urn:b")}, [])
    crawled_at = cache.meta["last_crawl"]

    applied = cache.swap(
        {}, [CrawlError(provider_id=PROVIDER, message="All connection attempts failed")]
    )

    assert applied is False
    assert len(cache.all_datasets()) == 2, "good data was discarded over one bad cycle"
    assert (
        cache.meta["last_crawl"] == crawled_at
    ), "an attempt that returned nothing counted as a crawl"


def test_the_errors_are_still_reported():
    """Keeping the data must not hide why the refresh failed."""
    cache = CatalogCache()
    cache.swap({PROVIDER: _datasets("urn:a")}, [])
    cache.swap({}, [CrawlError(provider_id=PROVIDER, message="boom")])

    assert [e["message"] for e in cache.meta["crawl_errors"]] == ["boom"]


def test_a_failed_first_crawl_leaves_freshness_unset():
    """With no previous data there is nothing to keep — but it still must not
    claim to have crawled. A freshness check should fail loudly rather than pass
    on an empty catalogue."""
    cache = CatalogCache()

    applied = cache.swap({}, [CrawlError(provider_id=PROVIDER, message="refused")])

    assert applied is False
    assert cache.meta["last_crawl"] is None
    assert cache.all_datasets() == []


def test_a_reachable_provider_publishing_nothing_does_empty_the_catalogue():
    """The distinction that makes the rule safe: "nobody answered" is not the
    same as "everybody answered, with nothing"."""
    cache = CatalogCache()
    cache.swap({PROVIDER: _datasets("urn:a")}, [])

    applied = cache.swap({PROVIDER: []}, [])

    assert applied is True
    assert cache.all_datasets() == []


def test_no_providers_configured_is_not_treated_as_an_outage():
    """`crawl_all` returns ({}, []) when nothing is configured — no errors, so
    an empty catalogue is the honest answer."""
    cache = CatalogCache()
    cache.swap({PROVIDER: _datasets("urn:a")}, [])

    assert cache.swap({}, []) is True
    assert cache.all_datasets() == []
