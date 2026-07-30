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
| `verify_edr` | `true` | Verify the EDR token against ds's JWKS. Off is dev-only and refused in production — with it off, a bearer string is an assertion |
| `enforce_consent` | `true` | When false, consent filtering is skipped — dev only |
| `external_query_url` | `None` | Proxy a dataset to a real upstream dataset-api |
| `extra_datasets_path` | `None` | JSON file adding datasets at startup |

## The `/query` enforcement chain

`POST /query` runs in one of **two modes**, chosen by a header, and both are
first-class.

### The signature is the real dataset-api's, not this service's own

This service exists to stand in for the sibling `dataset-api` (`DATASET_API_PATH`
— see *Assumed workspace layout* in the root `AGENTS.md`). Its route, request
model and response model therefore mirror that service field for field — `POST /query` with `{sql, limit, offset, skip_count}`, answering
`{items, offset, limit, count, total}`.

**Any divergence makes every green ds flow evidence about an API nobody runs.**
It previously took `dataset_name`, `consumer_id`, `subject_id`, `agreement_id`,
`transfer_id` and `purpose` as query parameters — a contract production has never
implemented. The datasets now come from the query itself, as they do there.

### Mode 1 — dataspace (`Edc-Contract-Agreement-Id` present)

```
POST /query
Authorization: Bearer <EDR JWT>
Edc-Contract-Agreement-Id: <shared DSP agreement id>
Edc-Transfer-Process-Id: <transfer id>          (optional)
Edc-Purpose: FlexibilityResearch                 (why this query is made)

{"sql": "SELECT * FROM datasets.silver.meters_15m", "limit": 100}
```

1. **Verify the EDR token** against `GET /internal/edr-jwks`. Nothing else does:
   upstream removed the data-plane proxy (`data-plane-public-api-v2`, deprecated),
   so the EDR endpoint *is* this service, and the token carries no `exp`. The
   verified `aud` is the consumer DID — the one identity fact that never comes
   from a header.
2. **Ask ds** — `POST /internal/dataplane/authorize` with the verified consumer,
   the agreement from the header, the purpose, and the datasets from the SQL.
   One call, one decision: ds checks the agreement is live **and belongs to this
   consumer**, that it covers these datasets, that the transfer is usable, that
   the purpose is one the agreement permits, and returns the consent row filter.
3. **Enforce** — `deny` → 403; a `row_filter` → keep only rows whose column value
   is in `subject_ids`.
4. **Audit** — `POST /internal/audit/query` emits `QueryExecuted`.

This service assembles nothing. ds is the control plane and decides; this is the
data plane and enforces. A ds that is unreachable is a **denial**, never an allow.

### Mode 2 — no header

Today's non-dataspace behaviour: rows are served without contacting ds at all. A
deployment that never joins a dataspace is unaffected by any of the above.

**Dataspace mode never falls back to mode 2.** A fallback between two
authorization regimes is a bypass with extra steps.

### Two agreement ids, and only one of them crosses

EDC 0.16 keeps `ContractAgreement.getId()` (this runtime's own, **different on
each side**) apart from `getAgreementId()` (shared, identical on both). A client
must send the **shared** one; ds resolves either, and the consumer connector
returns the right one on `GET /consumer/edr/{id}`. Sending the local id is
refused as `agreement_unknown` — which is exactly how this was found.

### Purpose is required for consent-gated datasets

`Edc-Purpose` carries **the reason this query is made**. ds fails closed when it
is absent: for a consent-required dataset an undeclared purpose means the caller
never said why it wants the data, so the request is refused rather than served.

The same consumer, agreement and transfer return **different rows** for a
different purpose: a subject who consented to flexibility research contributes
nothing to an incentive-calculation query. The `smoke` flow asserts exactly this,
plus the refusal of an agreement the caller does not hold.

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
- **Downstream**: ds-connector `/internal/*` — the PEP authenticates **as itself**,
  with `svc-ds-dataset-api`'s Keycloak client credentials (scope `connector.internal`,
  audience `svc-ds-connector`). It used to present a static `X-Api-Key` that was the
  *same value* as EDC's Management API key, so one leak crossed two trust boundaries
  and every `/internal/*` call arrived as the same anonymous bearer

## Testing

```bash
task setup
task run                    # dev server with hot-reload
curl 'http://172.17.0.1:30002/query?dataset_name=datasets.gold.om_weather_features'
```

There is no unit suite; the behaviour that matters is covered end to end by
`ds-e2e run -f smoke`, which asserts both the allow and the deny paths.
