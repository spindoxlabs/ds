# ds-federated-catalog

Crawls the registered participants through a **consumer-capable** ds-connector, and
republishes the union as one read-only `dcat:Catalog`. Port 30003 (debug 30903). No
database — an in-memory cache the crawl replaces wholesale. Also ships `fc-cli`.

**It is an advisory index, never an authority.** An offering exists because its provider
serves it over DSP; a discrepancy resolves in favour of the provider.

## References

| | |
|---|---|
| Requirements | [DSSC · Publication and Discovery](../../docs/blueprints/dssc/data-value-creation-enablers/publication-and-discovery.md) · [DSSC · Data, Services & Offerings Descriptions](../../docs/blueprints/dssc/data-value-creation-enablers/data-services-and-offerings-descriptions.md) |
| Rules | [Rulebook · Catalogue and metadata](../../docs/rulebook/catalogue-and-metadata.md) — the catalogue-architecture decision and the deny paths |
| Code as committed | [docs/services/federated-catalog.md](../../docs/services/federated-catalog.md) |

## Where to work

| Task | Start at |
|---|---|
| Crawl logic or schedule | `crawler.py`, `config.py` |
| Cache behaviour | `cache.py` |
| Search / filter | `api/catalog.py` |
| Participant discovery | `registry.py` |

Configuration is in `.env.example` under the `CATALOG_` prefix.

## Rules that are not visible from the code

- **A crawl that reached nothing is not a crawl.** `CatalogCache.swap` refuses to publish a
  cycle in which *every* source errored: previous datasets are kept, `last_crawl` is not
  advanced, and the loop retries after `CATALOG_CRAWL_RETRY_DELAY`. Errors always land on
  `/catalog/meta`.

  This is not padding. `CATALOG_STARTUP_DELAY` is a guess about how long the connector and
  its EDC take to accept connections, and on a cold boot it is regularly wrong. Swapping the
  failure in stamped a fresh **empty** catalogue that stood for a full interval, so consumers
  read "the provider published nothing" when the truth was "we could not ask" — and a
  freshness check passed while the content check failed.

  The distinction that keeps the rule safe: *no source answered* is not *every source
  answered, with nothing*. A reachable provider publishing nothing still empties the
  catalogue, as it should.
- **The crawl is an authenticated call.** It targets a route on someone else's connector; it
  must present a credential and must send `counter_party_id`, or the connector attributes
  every crawled provider to itself.
- **This unit never publishes.** `fc-cli` is read-only and the service has no write route.
  The recorded architecture is distributed catalogues with a pull-crawled advisory index
  (rulebook §1); publication belongs to the Participant Agent (`DSSC-PUB-12`) and to the
  provider that owns the offering. A `sync` command that pushed crawled DCAT-AP datasets
  into this participant's EDC was deleted for that reason, not repaired — see the README.
- **`dcat:DataService` names the *source's* endpoint, never this service's.** The index
  provides nothing; it republishes descriptions. `DSSC-PUB-41` asks for the service
  *providing* the datasets, so a consumer following it arrives at the provider it must
  negotiate with. Shape lives in `ds.governance.dcat`, shared with the compliance evidence
  catalogue — do not grow a second copy here.
- **Route order under `/catalog` is behaviour.** `GET /catalog/{dataset_iri:path}` is a
  catch-all, so anything mounted under `/catalog` must be declared before it. `main.py`
  includes the unguarded `public_router` (which carries `/catalog/context`) first for
  exactly this reason; `tests/test_routing.py` pins it.

## Testing

`task -d services/federated-catalog test|lint`. `respx` mocks the registry and the connector
— a test that leaves `identity_registry_url` at its non-empty default will make a real call
and fail on the unmocked request.
