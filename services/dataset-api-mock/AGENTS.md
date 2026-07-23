# dataset-api-mock — Agent Guide

## Service identity

- **Role**: Stand-in data plane for local development and the e2e flows. Serves dataset rows and acts as the **Policy Enforcement Point** for consent-gated data.
- **Language**: Python 3.12, FastAPI
- **Port**: 30002
- **URL**: `http://172.17.0.1:30002`, container-internal `http://dataset-api:30002`
- **Database**: none — datasets are in-process fixtures

This service is small, but it is not a toy: it is where consent enforcement actually
removes rows. The EDC gates *whether* a transfer may happen; this service decides
*which rows* leave, per subject and per purpose. A mistake here leaks personal data
even though every negotiation looked correct.

## Source layout

```
src/dataset_api_mock/
├── main.py       FastAPI app, dataset fixtures, /query PEP, catalogue endpoints
└── metrics.py    Prometheus instrumentation
```

Everything lives in `main.py` on purpose — the file is meant to be readable end to
end when reasoning about an authorization decision.

## Configuration

Settings use the `DATASET_API_` env prefix.

| Setting | Default | Purpose |
|---|---|---|
| `connector_internal_url` | `http://172.17.0.1:30001` | ds-connector base URL for `/internal/*` calls |
| `connector_api_key` | `insecure-dev-key` | `X-Api-Key` for `/internal/*` (equals `EDC_API_KEY`) |
| `enforce_consent` | `true` | When false, consent filtering is skipped — dev only |
| `external_query_url` | `None` | Proxy a dataset to a real upstream dataset-api |
| `extra_datasets_path` | `None` | JSON file adding datasets at startup |

## The `/query` enforcement chain

`GET|POST /query` applies four independent gates, in order. Each one can only
*remove* access:

1. **Transfer** — `GET /internal/transfers/{id}/status`. A stale EDR cannot keep
   querying after the consumer revokes; a terminated transfer is `403`.
2. **Agreement** — `GET /internal/agreements/{id}/status`.
3. **Consent + purpose** — for datasets with `requires_consent`, calls
   `GET /internal/consent/check?dataset_id=…&consumer_id=…&purpose=…` and keeps only
   rows whose `subject_column` value is in the returned `subject_ids`.
4. **Audit** — `POST /internal/audit/query` emits a `QueryExecuted` provenance event
   with the authorized subject list.

### Purpose is required for consent-gated datasets

The `purpose` query parameter carries **the reason this query is made** — a
comma-separated list of purpose slugs from the ODRL profile taxonomy.

ds-connector fails closed when it is absent: for a consent-required dataset an
undeclared purpose means the caller never said why it wants the data, so the
subject list comes back **empty** and the query returns zero rows. This is
deliberate — a caller that predates the purpose chain receives nothing rather than
everything.

```
GET /query?dataset_name=datasets.silver.meters_15m
          &consumer_id=did:web:consumer.dataspaces.localhost
          &agreement_id=…&transfer_id=…
          &purpose=FlexibilityResearch
```

The same consumer, agreement and transfer return **different rows** for a different
purpose: a subject who consented to flexibility research contributes nothing to an
incentive-calculation query. The e2e `smoke` flow asserts exactly this.

### Dataset id resolution

`_granted_subject_ids` tries the dataset name first, then the asset id. The consent
row is keyed on the governance key, which is usually — but not necessarily — equal
to the EDC asset id.

## Adding a dataset

Add an entry to `DATASETS` in `main.py`, or ship a JSON file via
`DATASET_API_EXTRA_DATASETS_PATH`:

```python
"datasets.silver.example": {
    "asset_id": "datasets.silver.example",
    "requires_consent": True,     # turns on the consent gate
    "subject_column": "sub",      # the column holding the subject DID
    "rows": [...],
}
```

**`requires_consent` must agree with `governance.yaml`.** A dataset that is
`classification: pii` there but `requires_consent: false` here would be served
unfiltered. `task compliance:validate` checks the governance side; the two are
matched by dataset key.

## Integration points

- **Upstream**: EDC data plane (proxied consumer queries), ds-e2e flows, the portal's
  `/my-data` detail view (`GET /subjects/{id}/datasets`)
- **Downstream**: ds-connector `/internal/*` — authenticated with `X-Api-Key`, one of
  the three auth mechanisms in this repo (see the root `AGENTS.md`)

## Testing

```bash
task setup
task run                    # dev server with hot-reload
curl 'http://172.17.0.1:30002/query?dataset_name=datasets.gold.om_weather_features'
```

There is no unit suite; the behaviour that matters is covered end to end by
`ds-e2e run -f smoke`, which asserts both the allow and the deny paths.
