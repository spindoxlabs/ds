# Provenance & Lineage

This document describes the W3C PROV-O provenance system: how dataspace events are logged, how the provenance graph is structured, and how lineage traversal works.

---

## Design decisions

- **No triple store** — provenance is stored in PostgreSQL using relational tables with a `node_type` discriminator. This avoids the operational complexity of a triple store while supporting the graph queries needed for lineage.
- **JSON-LD REST API** — responses are W3C PROV-O compatible JSON-LD, but the storage layer is relational.
- **Idempotent event ingest** — duplicate `event_id` values are silently ignored, making it safe to retry event emission.
- **BFS lineage** — graph traversal uses breadth-first search implemented in raw SQL, not ORM queries.

---

## PROV-O data model

The provenance graph uses three W3C PROV-O node types and six relation types:

### Node types

| Type | Description | Example |
|------|------------|---------|
| `Entity` | A data artifact | A published dataset, an EDR token |
| `Activity` | An action that transforms or uses entities | Catalogue publication, contract agreement, data transfer |
| `Agent` | An actor responsible for activities | A participant DID, a service |

### Relation types

| Relation | From → To | Meaning |
|----------|----------|---------|
| `wasGeneratedBy` | Entity → Activity | This entity was produced by this activity |
| `used` | Activity → Entity | This activity consumed this entity |
| `wasAssociatedWith` | Activity → Agent | This agent was responsible for this activity |
| `wasAttributedTo` | Entity → Agent | This entity is attributed to this agent |
| `wasDerivedFrom` | Entity → Entity | This entity was derived from another entity |
| `actedOnBehalfOf` | Agent → Agent | This agent acted on behalf of another agent |

---

## Domain events

ds-connector emits structured domain events to ds-provenance via `POST /prov/events`. Each event creates a set of PROV-O nodes and relations.

### CataloguePublished

Emitted when `POST /provider/sync` pushes datasets to EDC.

Creates:
- Entity (the published dataset)
- Activity (the publication action)
- Agent (the provider participant)
- Relations: `wasGeneratedBy`, `wasAssociatedWith`, `wasAttributedTo`

### ContractAgreementSigned

Emitted when a contract negotiation reaches `FINALIZED` state.

Creates:
- Activity (the agreement)
- Relations to the dataset entity and both participant agents

### DataTransferCompleted

Emitted when a data transfer reaches `STARTED` state.

Creates:
- Activity (the transfer)
- Entity (the EDR/data access)
- Relations linking transfer to agreement and participants

### UsageObligationFulfilled

Emitted when a post-transfer obligation is met (e.g. audit logging, data deletion).

Creates:
- Activity (the obligation fulfilment)
- Relations linking to the original transfer

---

## Database schema

Three main tables in the `provenance` PostgreSQL database:

### `prov_nodes`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID (ULID) | Primary key |
| `iri` | TEXT | Unique PROV-O IRI (e.g. `urn:ds:entity:01HX...`) |
| `node_type` | TEXT | `entity`, `activity`, `agent` |
| `label` | TEXT | Human-readable label |
| `attributes` | JSONB | Arbitrary PROV-O attributes |
| `created_at` | TIMESTAMP | Creation timestamp |

### `prov_relations`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Primary key |
| `relation_type` | TEXT | PROV-O relation (e.g. `wasGeneratedBy`) |
| `source_iri` | TEXT | Subject of the relation |
| `target_iri` | TEXT | Object of the relation |
| `attributes` | JSONB | Relation metadata |

### `domain_events`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Primary key |
| `event_id` | TEXT | Idempotency key (unique) |
| `event_type` | TEXT | Event discriminator |
| `payload` | JSONB | Full event data |
| `processed_at` | TIMESTAMP | When the event was ingested |

---

## Lineage traversal

`GET /prov/lineage/{iri}` performs BFS graph traversal from a starting node.

### Parameters

| Parameter | Default | Values |
|-----------|---------|--------|
| `direction` | `both` | `upstream`, `downstream`, `both` |
| `max_depth` | `5` | Integer (max traversal depth) |
| `relation_types` | all | Comma-separated filter |
| `format` | `graph` | `graph` (nodes + edges), `flat` (node list) |

### Example

```
GET /prov/lineage/urn:ds:entity:01HX123?direction=upstream&max_depth=3
```

Returns the full ancestry graph: which activities produced this entity, which entities those activities consumed, and so on — up to 3 hops.

### Graph response format

```json
{
  "@context": { ... },
  "nodes": [
    { "iri": "urn:ds:entity:01HX123", "type": "entity", "label": "Energy Metrics" },
    { "iri": "urn:ds:activity:01HX456", "type": "activity", "label": "CataloguePublished" }
  ],
  "edges": [
    { "source": "urn:ds:entity:01HX123", "target": "urn:ds:activity:01HX456", "relation": "wasGeneratedBy" }
  ]
}
```

---

## Portal visualization

The portal's admin lineage view (`/admin/lineage`) renders the provenance graph using Cytoscape.js with a dagre (directed acyclic graph) layout.

- **Entities** are shown as blue rectangles
- **Activities** are shown as orange ellipses
- **Agents** are shown as green diamonds
- Edges are labeled with the PROV-O relation type
- Users can click a node to see its full attributes
- The graph can be exported as SVG

---

## JSON-LD context

All provenance API responses include a `@context` that maps short property names to W3C PROV-O IRIs. The context is served at `GET /prov/context` and cached for 24 hours.

---

## Audit log

`GET /prov/events` returns the raw domain event audit log with filtering:

| Filter | Example |
|--------|---------|
| `event_type` | `CataloguePublished`, `ContractAgreementSigned` |
| `agreement_id` | Filter by contract agreement UUID |
| `after` / `before` | Timestamp range |

---

## DSSC Blueprint alignment

| Building Block | Implementation |
|---------------|---------------|
| BB07 (Provenance & Traceability) | W3C PROV-O JSON-LD API with BFS lineage traversal |
