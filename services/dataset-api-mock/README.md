# dataset-api-mock

A stand-in data plane for local development and the end-to-end verification flows.
It serves dataset rows over HTTP and acts as the **Policy Enforcement Point** for
consent-gated data: the EDC decides whether a transfer may happen, this service
decides which rows actually leave.

- **Port**: 30002
- **Stack**: Python 3.12, FastAPI

## Run

```bash
task setup
task run          # http://172.17.0.1:30002
```

It also runs as `dataset-api-provider` in `docker-compose.provider.yml`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET \| POST /query` | Query a dataset. Applies transfer, agreement and consent gates |
| `GET /catalogue` | List available datasets |
| `GET /catalogue/{asset_id}` | One dataset's catalogue entry |
| `GET /subjects/{subject_id}/datasets` | Datasets containing rows for a subject |
| `GET /health` | Liveness |
| `GET /metrics` | Prometheus metrics (currently unauthenticated — a known gap) |

## Querying consent-gated data

Datasets marked `requires_consent` are filtered per subject **and per purpose**:

```bash
curl 'http://172.17.0.1:30002/query\
?dataset_name=datasets.silver.meters_15m\
&consumer_id=did:web:consumer.dataspaces.localhost\
&purpose=FlexibilityResearch'
```

`purpose` is the reason the query is made, as a comma-separated list of slugs from
the ODRL profile taxonomy (`GET /ns/policy` on ds-connector).

**Omitting it returns zero rows, not all rows.** For a consent-required dataset an
undeclared purpose means the caller never said why it wants the data, so ds-connector
fails closed. Likewise, a purpose that a subject did not consent to excludes that
subject's rows even when the contract agreement and transfer are perfectly valid.

The response carries an `authorization` block showing which gates ran and which
subjects were authorized.

## Configuration

Environment variables use the `DATASET_API_` prefix.

| Variable | Default | Purpose |
|---|---|---|
| `DATASET_API_CONNECTOR_INTERNAL_URL` | `http://172.17.0.1:30001` | ds-connector base URL |
| `DATASET_API_CONNECTOR_API_KEY` | `insecure-dev-key` | `X-Api-Key` for `/internal/*` |
| `DATASET_API_ENFORCE_CONSENT` | `true` | Set false to bypass consent filtering — dev only |
| `DATASET_API_EXTERNAL_QUERY_URL` | — | Proxy a dataset to a real upstream dataset-api |
| `DATASET_API_EXTRA_DATASETS_PATH` | — | JSON file adding datasets at startup |

## See also

- [`AGENTS.md`](AGENTS.md) — enforcement chain, adding datasets, integration points
- [Consent & Sovereignty](../../docs/consent-and-sovereignty.md) — the purpose chain and enforcement matrix
