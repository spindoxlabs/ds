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

The provenance graph uses three W3C PROV-O node types and seven relation types:

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
| `wasInformedBy` | Activity → Activity | This activity was informed by another activity |

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

### CatalogViewed

Emitted when a consumer browses a provider's catalog.

Creates:
- Activity (the view action)

### AccessRequested

Emitted when a consumer requests access to a dataset.

Creates:
- Activity (the access request)
- Relations to the dataset entity and participant agents

### NegotiationStarted

Emitted when a contract negotiation begins.

Creates:
- Activity (the negotiation)
- Relations to the dataset entity and participant agents

### NegotiationFinalized

Emitted when a contract negotiation reaches `FINALIZED` state.

Creates:
- Activity (the finalization)
- Relations to the dataset entity and participant agents

### NegotiationTerminated

Emitted when a contract negotiation is terminated.

Creates:
- Activity (the termination)
- Relations to the negotiation activity

### ContractAgreementSigned

Emitted when a contract negotiation reaches `FINALIZED` state.

Creates:
- Activity (the agreement)
- Relations to the dataset entity and both participant agents

### TransferStarted

Emitted when a data transfer begins.

Creates:
- Activity (the transfer start)
- Relations to the agreement and participant agents

### DataTransferCompleted

Emitted when a data transfer reaches `STARTED` state.

Creates:
- Activity (the transfer)
- Entity (the EDR/data access)
- Relations linking transfer to agreement and participants

### QueryExecuted

Emitted when a dataspace-originated query is executed.

Creates:
- Activity (the query execution)
- Relations to the dataset, agreement, and participant agents

### UsageObligationFulfilled

Emitted when a post-transfer obligation is met (e.g. audit logging, data deletion).

Creates:
- Activity (the obligation fulfilment)
- Relations linking to the original transfer

### AccessRevoked

Emitted when access to a dataset is revoked.

Creates:
- Activity (the revocation)
- Relations to the dataset, agreement, and participant agents

### ConsentGranted

Emitted by the connector when a subject's data-sharing consent is granted —
`approve_consent`, `set_subject_data_sharing`, and offer provisioning via
`POST /consent/admin/shares`. Emitted from the API layer *after* the write
commits (the `AccessRevoked` pattern) with a deterministic `event_id`, so an
idempotent re-provision is deduplicated rather than double-counted.

Creates:
- Activity (the consent grant)
- Entity (the dataset the consent is about)
- Agent (the pseudonymous subject DID)
- Relations: `used`, `wasAssociatedWith`

Key fields: `subject_id`, `dataset_id`, `consumer_did` (may be the scoped
wildcard `*`), `offer_id`, `purpose`, `controller_role`, `legal_basis`.

### ConsentRevoked

Emitted when a subject withdraws consent — `revoke_consent` or
`set_subject_data_sharing(enabled=False)`.

Creates:
- Activity (the consent revocation)
- Entity (the dataset)
- Agent (the subject DID)
- Relations: `invalidated`, `wasAssociatedWith`

Adds `reason` to the `ConsentGranted` field set.

### DataIngested

Emitted when a DSO / offline data handover is recorded via
`POST /admin/ingestion` (guard `connector.ingestion.record`). The DSO leg is
manual in phase A, so the operator records the handover as they perform it. The
connector computes the `consent_snapshot_hash` itself from its consent DB.

Creates:
- Activity (the ingestion)
- Entity (the ingested dataset, `wasGeneratedBy` the activity)
- Agent (the provider), when known

Key fields: `dataset_id`, `source_ref`, `record_count`, `consent_snapshot_hash`,
`agreement_ref`.

### DataDisclosed

Emitted by the onboarding service after a successful CSV export names a
recipient (`ir-cli`/`export-csv --recipient …`). It documents an offline,
DPA-governed disclosure.

Creates:
- Activity (the disclosure)
- Agent (the recipient; and the disclosing controller, when known)
- Entity (the source, e.g. a REC slug), when given

Key fields: `recipient_ref`, `purpose`, `columns[]` (column *names*, not
values), `subject_count`, `consent_snapshot_hash`, `agreement_ref`.

### No PII in provenance

The Block C events carry **codes, pseudonymous DIDs and hashes only — never a
name, email, fiscal code or POD**. `subject_id` is the subject DID (as on
`AccessRevoked`); `legal_basis` is the Block B evidence record (basis IRI,
versions, hashes); `recipient_ref` and `agreement_ref` identify a party and its
DPA, never their contents. The `consent_snapshot_hash` is a SHA-256 over the
sorted `(subject_did, dataset_id, purpose, controller_role, consent_text_version)`
tuples that authorised a handover — it proves *which* consent state was in force,
verifiable by recomputation from the connector DB, while the provenance store
holds none of the underlying subject data.

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

The portal's lineage view (`/lineage/[iri]`) renders the provenance graph using Cytoscape.js with a dagre (directed acyclic graph) layout.

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
