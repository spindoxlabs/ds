# ds-federated-catalog

A dataspace has no central catalogue — each provider serves its own over DSP. That is correct
for authority and terrible for discovery: you cannot browse what you must already know how to
ask for.

`ds-federated-catalog` closes that gap. It periodically walks every registered provider,
collects each one's DCAT-AP catalogue, and republishes the union as a single read-only
`dcat:Catalog` with search and IRI resolution on top.

**It is an advisory index, never an authority.** An offering exists because its provider
serves it over DSP. If the index and the provider disagree, the provider is right — the index
is at most one crawl interval stale, and it says so.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Publication and Discovery](../blueprints/dssc/data-value-creation-enablers/publication-and-discovery.md) · [DSSC · Data, Services & Offerings Descriptions](../blueprints/dssc/data-value-creation-enablers/data-services-and-offerings-descriptions.md) |
| Rules it enforces | [Rulebook · Catalogue and metadata](../rulebook/catalogue-and-metadata.md) |

## What it does

**Discovers providers** from the identity registry — every participant with the `provider`
role and a DSP address.

**Fetches each catalogue through a consumer-role connector.** It does not speak DSP itself. It
posts to `POST /consumer/catalog` on a [ds-connector](connector.md), which performs the DSP
exchange with the counterparty EDC and returns the result. That is why the crawler must point
at a **consumer-role** connector — a provider-role instance does not mount that route at all.

**Optionally fetches plain DCAT-AP documents** by direct `GET`, for sources that publish a
catalogue without being DSP participants.

**Serves the union** with paging, JSON-LD context, freshness metadata and search:

| Route | Returns |
|---|---|
| `GET /catalog` | the whole catalogue, paged, as `dcat:Catalog` with `hydra:*` counters |
| `GET /catalog/{dataset_iri}` | one dataset, resolved by IRI |
| `POST /catalog/search` | narrow by free text, access level, provider or keywords |
| `GET /catalog/meta` | dataset count, providers, last crawl, crawl errors |
| `GET /catalog/context` | the JSON-LD `@context` every response points at |
| `GET /health` | includes `cache_age_seconds` — the honest staleness signal |

Everything under `/catalog` requires `catalog.read`, except `/catalog/context`.

`GET /catalog/context` is the one route outside the guard: every response advertises it as
its `@context`, so a JSON-LD processor dereferences it holding no credential.

**Ships `fc-cli`**, a read-only CLI — `crawl` and `status`. It publishes nothing; see the
unit README for why a push path does not belong here.

## How it works

### No database

Everything served comes from an in-process cache that a background task replaces **wholesale**
after each cycle. Nothing survives a restart, and there is no per-entry TTL — staleness is a
property of the whole cache.

### The crawl cycle

1. Wait `CATALOG_STARTUP_DELAY` seconds, then loop every `CATALOG_CRAWL_INTERVAL`.
2. Ask the identity registry for participants; keep those with the `provider` role and a DSP
   address. A registry error here yields an *empty* provider list, not an exception.
3. Fetch every source concurrently, capped at `CATALOG_MAX_DATASETS_PER_PROVIDER` each.
4. A failing source becomes a recorded `CrawlError` with a timestamp. **One failing provider
   never fails the cycle.**
5. Swap the cache — unless the cycle *reached nobody*, in which case the previous data and its
   `last_crawl` timestamp are left alone and only the errors are recorded, and the next cycle
   is retried after `CATALOG_CRAWL_RETRY_DELAY`.

That distinction is the design point: **"every provider is down" must not look like "the
dataspace is empty."** A service that has only ever failed reports a null cache age rather
than a confidently empty catalogue.

### The swap is a replacement, not a merge

An entry disappears by being absent from a later successful cycle. There is no deletion
protocol and none is needed.

## Configuration

`pydantic-settings`, prefix **`CATALOG_`** — not `FEDERATED_CATALOG_`.

| Variable | Default | Meaning |
|---|---|---|
| `CATALOG_CONNECTOR_URL` | `http://172.17.0.1:31001` | the **consumer-role** connector every DSP catalogue call goes through |
| `CATALOG_IDENTITY_REGISTRY_URL` | `http://identity-registry:30005` | where the provider list comes from |
| `CATALOG_PARTICIPANTS_YAML` | `""` | YAML fallback, used only when the registry URL is empty |
| `CATALOG_DCAT_SOURCES_YAML` | `""` | extra plain DCAT-AP sources to crawl |
| `CATALOG_CRAWL_INTERVAL` | `300` | seconds between cycles |
| `CATALOG_CRAWL_RETRY_DELAY` | `15` | seconds after a cycle that reached nothing |
| `CATALOG_STARTUP_DELAY` | `10` | seconds before the first cycle |
| `CATALOG_MAX_DATASETS_PER_PROVIDER` | `500` | per-provider cap |
| `CATALOG_BASE_URL` | `https://federated-catalog.dataspaces.localhost` | own base URL, used to build the `@context` URL in every response |
| `CATALOG_OIDC_ISSUER_URL` | — | Keycloak realm issuer. Set ⇒ JWTs fully verified |
| `CATALOG_OIDC_INSECURE_DEV` | `true` | accept unverified JWTs when no issuer. **Refused in production** |
| `CATALOG_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-federated-catalog` | own credentials; the id is also the expected JWT audience |
| `CATALOG_KEYCLOAK_TOKEN_URL` | Keycloak on `172.17.0.1:9080` | token endpoint for the registry call |
| `CATALOG_OIDC_GROUP_ALIASES` | `""` | JSON map: foreign group → ds role bundle |

Under `DS_ENV=production` the service refuses to start with the issuer unset, `INSECURE_DEV`
true, or the service secret still at its dev default.

## Integration

| Direction | Counterpart | For |
|---|---|---|
| out | identity registry | `GET /admin/participants` — the provider list, with a service token |
| out | ds-connector (consumer role) | `POST /consumer/catalog` — one call per provider per cycle |
| out | Keycloak | `client_credentials` for the registry call |
| in | [ds-portal](portal.md) | `GET /catalog`, `GET /catalog/{id}`, forwarding the signed-in user's token |

The portal forwards the *user's* token, so `catalog.read` must be reachable from that user's
groups — `ds-member` and every operator bundle carry it.

## Running it

| Task | Effect |
|---|---|
| `task provider:federated-catalog:run` | uvicorn on `:30003` with reload |
| `task -d services/federated-catalog debug` | debugpy on `:30903` |
| `task e2e:catalog` | the live catalogue-discovery flow |

Port **30003**. `fc-cli` is available both in a development checkout and in the container —
the image installs the package as a distribution, so the console script exists on `PATH`.
