# ds-provenance

A W3C PROV-O compatible REST API for the dataspaces provenance logger (DSSC Blueprint BB07). Stores and queries provenance graphs as JSON-LD using a relational database — no triple store required.

Port: `30000`
URL: `http://portal.dataspaces.localhost/api/provenance/`

---

## Purpose

Every significant event in the dataspace — a dataset being published, a contract being signed, data being transferred, an obligation being fulfilled — is captured as a PROV-O graph. This service is the central sink for those events.

Consumers of the API can reconstruct the full lineage of any data product: who generated it, who it was attributed to, what it was derived from, and what agreements governed its use.

> **Concepts live in the docs site, not here.** This README is the local entry
> point: what runs, which endpoints exist, how to configure and start it. The
> reasoning is published at **<https://spindoxlabs.github.io/ds/>** — start with
> [Provenance & Lineage](https://spindoxlabs.github.io/ds/provenance-and-lineage/).
> Working on the code? Read `AGENTS.md` in this directory first.

---

## Core concepts

W3C PROV-O: three node types (`Entity`, `Activity`, `Agent`) and seven relation
types. The node and relation catalogue, the domain events the connector emits,
the acting-principal attribution on policy-authoring events, and the
no-PII rule are documented at
[Provenance & Lineage](https://spindoxlabs.github.io/ds/provenance-and-lineage/).

---

## API

All responses use `Content-Type: application/ld+json` with the `@context` served at `GET /prov/context`.

### Record endpoints

- `POST /prov/entities` — ingest a `prov:Entity`
- `POST /prov/activities` — ingest a `prov:Activity`
- `POST /prov/agents` — ingest a `prov:Agent`
- `POST /prov/relations` — assert a directed PROV-O edge between two nodes
- `POST /prov/events` — ingest a domain event; auto-materialises the corresponding PROV-O graph within a single transaction

Domain event types:
- `CataloguePublished` — creates Entity + CatalogPublicationActivity + wasGeneratedBy + wasAttributedTo
- `ContractAgreementSigned` — creates NegotiationActivity + ContractAgreement entity + two wasAssociatedWith edges
- `DataTransferCompleted` — creates DataTransferActivity + derived Entity at consumer + wasGeneratedBy + wasDerivedFrom + wasAttributedTo
- `UsageObligationFulfilled` — creates ObligationFulfilmentActivity + wasAssociatedWith
- `ConsentGranted` / `ConsentRevoked` — consent Activity + dataset Entity + subject Agent (`used`/`invalidated` + `wasAssociatedWith`)
- `DataIngested` — Ingestion Activity + dataset Entity (`wasGeneratedBy`); records a DSO/offline handover
- `DataDisclosed` — Disclosure Activity + recipient Agent; records an offline CSV export

The consent/ingestion/disclosure events (Block C) carry **codes, DIDs and hashes only, never PII** — a `consent_snapshot_hash` fingerprints the authorising consent state without storing it.

Domain event ingest is idempotent via `event_id`.

### CRUD

`GET`, `PUT`, `PATCH`, `DELETE` on `/prov/entities/{iri}`, `/prov/activities/{iri}`, `/prov/agents/{iri}`. Delete is soft — sets `invalidated_at`.

### Collection queries

Rich query parameters on all collection endpoints, ANDed across params and ORed within multi-valued params:

- `GET /prov/entities?attributed_to=<iri>&energy_type=GridFrequencyDataset&limit=50`
- `GET /prov/activities?associated_with=<agent_iri>&started_after=2025-01-01T00:00:00Z`
- `GET /prov/events?event_type=DataTransferCompleted&agreement_id=urn:uuid:...`

### Lineage traversal

`GET /prov/lineage/{iri}` performs an async BFS traversal from the given node. Parameters:

- `direction` — `upstream`, `downstream`, or `both` (default)
- `max_depth` — maximum BFS depth (default 5, configurable up to `PROVENANCE_MAX_LINEAGE_DEPTH`)
- `relation_types` — comma-separated filter (e.g. `wasGeneratedBy,wasDerivedFrom`)
- `format` — `graph` or `flat`

Returns a JSON-LD `@graph` containing all reachable nodes and edges with depth annotations.

### Complex query

`POST /prov/query` accepts a `QueryRequest` body with filter, sort, limit, offset, and optional `lineage` options. Internally uses the same `FluentQueryBuilder` as the REST layer.

---

## FluentQueryBuilder

A chainable Python SDK importable from `ds.provenance.query.builder`:

```python
results = await (
    FluentQueryBuilder(session)
    .entities()
    .attributed_to("did:web:provider.dataspaces.localhost")
    .energy_type(EnergyNodeType.GRID_FREQUENCY_DATASET)
    .started_after(datetime(2025, 1, 1))
    .sort(SortField.STARTED_AT, SortOrder.DESC)
    .limit(20)
    .with_relations()
    .execute()
)
```

Relation filters use `EXISTS` subqueries — no N+1 queries.

---

## Database schema

Three tables in PostgreSQL (or SQLite for dev):

`prov_nodes` — unified Entity/Activity/Agent table with `iri` unique key, `node_type`, `energy_type`, temporal fields, and `external_meta` JSONB.

`prov_relations` — directed edges with `relation_type`, `subject_id`, `object_id`, `role`, `extra`. Unique on `(relation_type, subject_id, object_id)`.

`domain_events` — raw event log with `event_type`, `event_id` (idempotency key), `payload` JSONB, and extracted fields for fast filtering (`agreement_id`, `data_product_id`, `provider_did`, `consumer_did`).

---

## Configuration

Settings use the `PROVENANCE_` prefix:

- `PROVENANCE_DATABASE_URL` — SQLAlchemy async URL (default `sqlite+aiosqlite:///./provenance.db`)
- `PROVENANCE_BASE_URL` — base URL for IRI generation (default `https://provenance.dataspaces.localhost`)
- `PROVENANCE_CONTEXT_URL` — JSON-LD context URL
- `PROVENANCE_MAX_LINEAGE_DEPTH` — BFS depth cap (default 20)
- `PROVENANCE_DEBUG` — enable debug logging

---

## Development

```bash
cd services/provenance
task setup       # uv sync
task run         # hot reload on :30000
task debug       # same, waiting for a debugpy attach on :30900
task db:migrate  # alembic upgrade head

uv run pytest
```

```bash
docker compose -f docker-compose.yml up
```
