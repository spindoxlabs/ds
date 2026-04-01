# ds-provenance

A W3C PROV-O compatible REST API for the dataspaces provenance logger (DSSC Blueprint BB07). Stores and queries provenance graphs as JSON-LD using a relational database — no triple store required.

Port: `30000`
URL: `https://provenance.dataspaces.localhost`

---

## Purpose

Every significant event in the dataspace — a dataset being published, a contract being signed, data being transferred, an obligation being fulfilled — is captured as a PROV-O graph. This service is the central sink for those events.

Consumers of the API can reconstruct the full lineage of any data product: who generated it, who it was attributed to, what it was derived from, and what agreements governed its use.

---

## Core concepts

The data model follows W3C PROV-O with three node types and seven relation types.

Node types:
- `prov:Entity` — a data product, dataset, contract agreement, or other artefact
- `prov:Activity` — a time-bounded process (catalogue publication, negotiation, transfer)
- `prov:Agent` — a participant, system, or organisation

Relation types:
- `prov:wasGeneratedBy` — entity produced by activity
- `prov:wasAttributedTo` — entity attributed to agent
- `prov:wasDerivedFrom` — entity derived from another entity
- `prov:wasAssociatedWith` — activity associated with agent
- `prov:used` — activity consumed an entity
- `prov:actedOnBehalfOf` — agent delegated to another agent
- `prov:wasInformedBy` — activity was triggered by another activity

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
cd src/ds/provenance
task install
task dev         # hot reload on :30000
task db:migrate  # alembic upgrade head
task test
task seed        # insert sample PROV-O graph
```

```bash
docker compose -f docker-compose.yml up
```
