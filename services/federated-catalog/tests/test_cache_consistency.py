"""One dataset, one answer — whichever door the catalogue is asked through.

An entry with no `@id` used to be dropped from the flat IRI view and kept in the
per-provider bucket, so the same record was simultaneously findable through
`POST /catalog/search` with a `provider` filter, unresolvable through
`GET /catalog/{iri}`, and absent from `GET /catalog` and from `dataset_count`.
"""
from __future__ import annotations

from federated_catalog.cache import CatalogCache, SourceEndpoint

PROVIDER = "did:web:provider.dataspaces.localhost"


def test_an_entry_with_no_iri_is_absent_from_every_view():
    cache = CatalogCache()
    cache.swap(
        {PROVIDER: [{"@id": "urn:a"}, {"dct:title": "no identifier"}]},
        [],
    )

    assert len(cache.all_datasets()) == 1
    assert cache.meta["dataset_count"] == 1
    # The per-provider bucket is what search reads, and it used to keep the
    # id-less entry — search returned two where the catalogue held one.
    assert len(cache.search(provider=PROVIDER)) == 1


def test_the_drop_is_reported_rather_than_silent():
    """A dropped entry is a crawl finding, not a detail.

    Silently discarding it would make a provider's malformed record
    indistinguishable from a record it never published, which is the same class
    of mistake as publishing an empty catalogue after reaching nobody.
    """
    cache = CatalogCache()
    cache.swap({PROVIDER: [{"dct:title": "no identifier"}]}, [])
    messages = [e["message"] for e in cache.meta["crawl_errors"]]
    assert any("no @id or id" in m for m in messages)


def test_a_bare_id_key_still_counts_as_an_identifier():
    cache = CatalogCache()
    cache.swap({PROVIDER: [{"id": "urn:legacy"}]}, [])
    assert cache.get_by_iri("urn:legacy") is not None
    assert cache.meta["dataset_count"] == 1


def test_endpoints_and_source_attribution_survive_the_swap():
    cache = CatalogCache()
    cache.swap(
        {PROVIDER: [{"@id": "urn:a"}]},
        [],
        {PROVIDER: SourceEndpoint(url="http://edc:19194/protocol", conforms_to="dsp")},
    )
    assert cache.source_of("urn:a") == PROVIDER
    assert cache.endpoints()[PROVIDER].url == "http://edc:19194/protocol"
    assert cache.dataset_ids_by_source() == {PROVIDER: ["urn:a"]}
