# dataset-api-mock

Stand-in for the celine `dataset-api` in local and CI runs. Port 30002 (30022 when the real
one holds 30002). No database — datasets are in-process fixtures. Everything is in `main.py`
on purpose: the file is meant to be readable end to end when reasoning about an
authorization decision.

**It is not a deployed component** — exclude it from assessments. But it is the reference
implementation of the data-plane PEP, and the real dataset-api is written against the same
contract, so **keep it aligned in the same commit as any `/internal/*` change**. A flow that
passes only against the mock is evidence about an API nobody runs.

## References

| | |
|---|---|
| Requirements | [DSSC · Data Exchange](../../docs/blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Control and Data Plane](../../docs/blueprints/dssc/control-and-data-plane.md) |
| Rules | [Rulebook · Data exchange](../../docs/rulebook/data-exchange.md) — the plane split and what may not start before the control plane has decided |
| Code as committed | [docs/services/dataset-api-mock.md](../../docs/services/dataset-api-mock.md) |

## The signature is the real dataset-api's, not its own

`POST /query` with `{sql, limit, offset, skip_count}`, answering `{items, offset, limit,
count, total}`. Datasets come from the SQL, not from query parameters. It previously took
`dataset_name`, `consumer_id`, `subject_id`, `agreement_id`, `transfer_id` and `purpose` as
parameters — a contract production has never implemented.

## The `/query` enforcement chain

Two modes, chosen by the presence of `Edc-Contract-Agreement-Id`.

**Dataspace mode:**

1. **Verify the EDR token** against `GET /internal/edr-jwks`. Nothing else does — upstream
   removed the data-plane proxy, so the EDR endpoint *is* this service. The verified `aud`
   is the consumer DID: the one identity fact that never comes from a header.
2. **Ask ds** — `POST /internal/dataplane/authorize`. One call, one decision: agreement live
   and belonging to this consumer, covering these datasets, transfer usable, purpose
   permitted, plus the row filter. Parsed as `ds.governance.DataplaneDecision` — the shared
   shape, not this service's reading of it.
3. **Enforce** — `deny` → 403; a row filter narrows the rows. `_apply_row_filter` dispatches
   on the filter's `handler`.
4. **Audit** — `POST /internal/audit/query` emits `QueryExecuted`.

**No-header mode** is the non-dataspace path and contacts ds not at all. **Dataspace mode
never falls back to it** — a fallback between two authorization regimes is a bypass with
extra steps.

Four things that are easy to get wrong:

- **An unreachable ds is a denial, never an allow** — and so is an *unreadable* one. This
  service assembles nothing; ds decides and this enforces.
- **An allow carrying a row filter says *these rows*, not *all rows*.** A filter this plane
  cannot apply withholds everything; it is never a permission to serve unfiltered.
- **Send the shared agreement id.** EDC keeps `ContractAgreement.getId()` (runtime-local,
  different on each side) apart from `getAgreementId()` (shared). The local one is refused
  as `agreement_unknown`.
- **`Edc-Purpose` is required for a consent-gated dataset.** The same consumer, agreement
  and transfer return **different rows** for a different purpose; an absent purpose means
  the caller never said why, so it is refused.

## Adding a dataset

An entry in `DATASETS`, or a JSON file via `DATASET_API_EXTRA_DATASETS_PATH`.
**`requires_consent` must agree with `governance.yaml`** — `classification: pii` there with
`requires_consent: false` here would serve unfiltered. Matched by dataset key;
`task compliance:validate` checks the governance side.

## Testing

`task -d services/dataset-api-mock test` — what this PEP does with a decision, the half of
the `/internal/*` contract the connector's own tests cannot reach. `ds-e2e run -f smoke`
covers the rest, against a live stack.

The fixture's subject vocabulary does not line up with `governance.yaml`'s or ds's, so
`datasets.silver.meters_15m` refuses rather than guessing. Tracked in
`.agents/defect-per-service.md`.
