# dataset-api-fiware-adapter

A **plugin, not a service.** It has no `main`, no port, no Dockerfile and no chart.

It adds FIWARE/QuantumLeap query support to a *host* dataset API — the celine `dataset-api`,
which lives outside this repository — by advertising a FastAPI router and a row-filter handler
through setuptools entry points. The host discovers both, mounts the router and supplies
everything else: authentication, the dataset catalogue, and governance enforcement.

Its job is translation. It takes a dataset-scoped query in the host's vocabulary, turns it
into a QuantumLeap NGSI time-series request, and folds the response back into the flat row
list the host's result model expects.

!!! note "Currently unwired"
    Nothing in this repository builds, installs, imports or runs it. The host it plugs into is
    built from a sibling checkout, and that build does not install this package. Treat it as a
    component awaiting adoption rather than as part of the running platform.

## Role in the blueprint

| | |
|---|---|
| Relates to | [DSSC · Data Exchange](../blueprints/dssc/data-interoperability/data-exchange.md) · [CEEDS · Energy standards](../blueprints/ceeds/energy-standards.md) |
| Rules it relates to | [Rulebook · Data exchange](../rulebook/data-exchange.md) · [Rulebook · Data models](../rulebook/data-models.md) |

FIWARE NGSI-LD is a CEEDS-relevant energy data model. This adapter is how a dataset backed by
a FIWARE context broker becomes queryable through the same dataset API as a SQL-backed one.

## What it provides

| Entry point group | Name | Target |
|---|---|---|
| `celine.dataset.routes` | `fiware` | a FastAPI `APIRouter` under `/query/fiware` |
| `celine.dataset.row_filters` | `fiware_entity` | a row-filter handler class |

Two routes, both returning the host's `DatasetQueryResult`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/query/fiware` | the translated time-series query |
| `GET` | `/query/fiware/entities` | list the entities behind a dataset |

## How it works

### Row filtering resolves entity IDs, not consent

This is the part most easily misread.

The row filters answer **which FIWARE entity IDs may this user see** by asking an external
member registry, then constrain the NGSI query to exactly those URNs. Multiple filters
**intersect**, and an intersection that comes out empty **denies** — it does not fall through
to everything.

**This is not the consent path.** Subject consent, purposes and controller roles are decided
by [`ds-connector`](connector.md) and applied by whichever PEP fronts the dataset;
[`dataset-api-mock`](dataset-api-mock.md) is the reference implementation of that side.

| Handler | Behaviour |
|---|---|
| `deny` | immediate denial, empty result |
| `rec_registry` | resolve device ids through the member registry, using `args.urn_template` |
| `http_in_list` | fetch ids from `args.url` |
| `direct_user_match` | no-op |
| anything else | logged and skipped |

### The query translation

The endpoint is picked from the shape of the request, not from a parameter:

| `entity_id` given | exactly one attribute | QuantumLeap path |
|---|---|---|
| yes | yes | `/v2/entities/{id}/attrs/{attr}` |
| yes | no | `/v2/entities/{id}` |
| no | yes | `/v2/types/{type}/attrs/{attr}` |
| no | no | `/v2/types/{type}` |

Query parameters map straight through: `from_date`/`to_date` → `fromDate`/`toDate`,
`aggr_method`/`aggr_period` → `aggrMethod`/`aggrPeriod`, plus `limit`, `offset`, `lastN`,
the comma-joined allowed entity ids as `id`, and the comma-joined `attrs`.

Responses come back in three shapes — single entity, multi entity, plain entity list — and
each is flattened into rows carrying `entity_id`, `timestamp` and one column per attribute.

### Error handling

| Upstream | Becomes |
|---|---|
| `404` | an empty successful result |
| other `4xx` | `400`, with the QuantumLeap message |
| `5xx` | `502` |
| transport failure | `502` |

## Configuration

The package reads **no environment variables**. `FiwareSettings` is a plain Pydantic model,
not a settings class — values arrive from a caller constructing one.

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | `true` | false ⇒ the query route answers `404` |
| `default_timeout_ms` | `10000` | QuantumLeap request timeout, minimum 1000 |
| `max_limit` | `10000` | clamps the requested limit |
| `jwt_forwarding` | `false` | forward the caller's bearer to QuantumLeap |

**Connection details are per dataset**, not global. They come from the host's
`DatasetEntry.backend_config`:

| Key | Required | Used for |
|---|---|---|
| `base_url` | yes | the QuantumLeap root URL |
| `fiware_service` | yes | the `fiware-Service` request header |
| `entity_type` | no | overrides the entity type in the request body |
| `fiware_service_path` | no | the `fiware-ServicePath` header |

`backend_type` must be `quantumleap` or `context_broker`.

## What it expects from the host

The hard coupling. The package imports these from the host's `celine.dataset.*` namespace; a
rename on either side breaks it at import.

| Symbol | Used for |
|---|---|
| `get_session` | the async DB session dependency |
| `get_optional_user`, `AuthenticatedUser` | the route guard and the caller's identity |
| `enforce_dataset_access` | **authorisation** — the adapter never decides this itself |
| `load_dataset_entry`, `DatasetEntry` | the catalogue lookup, and `backend_type` / `backend_config` |
| `get_row_filter_specs`, `RowFilterPlan`, `is_admin_user` | governance row filtering |
| `get_settings` | the host's config, for the member-registry URL |
| `DatasetQueryResult` | the response model |
