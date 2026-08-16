# dataset-api-fiware-adapter

A **plugin, not a service** — no `main`, no port, no Dockerfile. It adds FIWARE/QuantumLeap
query support to a host dataset-api by advertising a FastAPI `APIRouter` and a row-filter
handler through setuptools entry points (`celine.dataset.routes`, `celine.dataset.row_filters`).
The host supplies authentication, the catalogue and governance enforcement; this supplies the
backend.

> **Nothing in this repository builds, installs, imports or runs it.** Before working on it,
> settle whether it is being adopted or removed — the question is an open issue
> (ADR-0012). Work on an unwired unit is unverifiable by construction.

## References

| | |
|---|---|
| Requirements | [DSSC · Data Exchange](../../docs/blueprints/dssc/data-interoperability/data-exchange.md) · [CEEDS · Energy standards](../../docs/blueprints/ceeds/energy-standards.md) |
| Rules | [Rulebook · Data exchange](../../docs/rulebook/data-exchange.md) · [Rulebook · Data models](../../docs/rulebook/data-models.md) |
| Code as committed | [docs/services/dataset-api-fiware-adapter.md](../../docs/services/dataset-api-fiware-adapter.md) |

## Row filtering resolves entity IDs, not consent

This is the part most easily misread. The row filters resolve **which FIWARE entity IDs a
user may see** by asking an external member registry, then constrain the NGSI-LD query to
those URNs. Multiple filters **intersect**, and an empty intersection **denies** rather than
falling through to everything.

**This is not the consent path.** Subject consent, purposes and controller roles are decided
by ds-connector (`GET /internal/consent/check`) and applied by whichever PEP fronts the
dataset — `services/dataset-api-mock/AGENTS.md` is the reference implementation of that
chain. If a deployment needs consent-scoped filtering for FIWARE-backed datasets, add a
handler that calls the connector's consent check with the query's declared purpose; **do not
assume the entity-ID filters already cover it.**

A handler's arguments must be ones `ds.governance.RowFilterArgs` actually carries — extra
keys are dropped, and a handler requiring a dropped key resolves to an empty set, which
denies.

## Conventions

`httpx.AsyncClient`, never `requests`. Handlers return a `RowFilterPlan` from the host
framework. An unknown handler contributes no constraint — check the resulting behaviour is
still fail-closed before adding one.

`uv run pytest` — `respx` mocks QuantumLeap and the member registry. There is no e2e flow;
the adapter is exercised only in deployments that select the FIWARE backend.
