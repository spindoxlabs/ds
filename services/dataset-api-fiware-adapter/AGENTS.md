# dataset-api-fiware — Agent Guide

## Service identity

- **Role**: FIWARE / QuantumLeap backend for a Dataset API deployment. Translates
  dataset queries into NGSI-LD temporal queries and normalises the results.
- **Language**: Python 3.12
- **Port**: none of its own — it is a **plugin**, not a standalone service
- **Database**: none; QuantumLeap is the store

Unlike every other directory under `services/`, this unit has no `Dockerfile` and no
`task <participant>:<name>:run`. It is packaged as a library and loaded by a host
Dataset API through setuptools entry points:

```toml
[project.entry-points."celine.dataset.routes"]
fiware = "dataset_api_fiware.routes:router"

[project.entry-points."celine.dataset.row_filters"]
fiware_entity = "dataset_api_fiware.row_filters:FiwareEntityFilterHandler"
```

The host framework (`celine.dataset`) supplies authentication, the dataset
catalogue, and governance enforcement. This adapter supplies the backend.

## Source layout

```
src/dataset_api_fiware/
├── routes.py       POST /query/fiware, GET /query/fiware/entities — registered on the host app
├── executor.py     Query execution: resolve dataset entry, apply row filters, call QuantumLeap
├── client.py       QuantumLeapClient — NGSI-LD temporal API over httpx
├── normalizer.py   NGSI-LD entity payloads → flat rows
├── row_filters.py  Governance row-filter handlers, resolved to entity-ID constraints
├── schemas.py      FiwareQueryModel and friends
└── config.py       Adapter settings
```

## Row filtering — entity IDs, not consent rows

This is the part most easily misread. The adapter's row filters resolve **which
FIWARE entity IDs a user may see**, by asking an external member registry, and then
constrain the NGSI-LD query to those URNs:

| Handler | Resolution |
|---|---|
| `rec_registry` | `GET {registry}/api/v1/members/{sub}/devices` → device IDs → URNs via `urn_template` |
| `http_in_list` | Arbitrary HTTP endpoint returning a list of IDs |
| `direct_user_match` | Post-fetch filter on an owner attribute; handled by the executor |
| `deny` | Deny outright |

Multiple filters **intersect** — an entity must be admitted by all of them — and an
empty intersection denies rather than falling through to "everything".

**This is not the consent path.** Subject consent, purposes and controller roles are
enforced upstream in ds-connector (`GET /internal/consent/check`) and applied by
whichever PEP fronts the dataset — see `services/dataset-api-mock/AGENTS.md` for the
reference implementation of that chain. If a deployment needs consent-scoped
filtering for FIWARE-backed datasets, add a handler here that calls the connector's
consent check with the query's declared `purpose`; do not assume the entity-ID
filters already cover it.

## Coding conventions

- `httpx.AsyncClient` for all HTTP; never `requests`
- Row-filter handlers return a `RowFilterPlan` from the host framework
- Unknown handlers log a warning and contribute no constraint — check that the
  resulting behaviour is still fail-closed when adding one
- `uv` for dependency management

## Testing

```bash
uv run pytest             # unit tests for client, normalizer, schemas, row filters
```

Tests use `respx` to mock QuantumLeap and the member registry. There is no e2e flow
for this adapter — it is exercised in deployments that select the FIWARE backend.

## Integration points

- **Host**: a Dataset API built on `celine.dataset`, which discovers this package's
  entry points
- **Downstream**: QuantumLeap NGSI-LD temporal API; an external member registry for
  `rec_registry` row filters
