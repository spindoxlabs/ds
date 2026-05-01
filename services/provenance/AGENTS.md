# ds-provenance — Agent Guide

## Service identity

- **Role**: W3C PROV-O provenance and audit logging
- **Language**: Python 3.12, FastAPI
- **Port**: 30000 (debug: 30900)
- **URL**: `https://provenance.dataspaces.localhost`
- **Database**: PostgreSQL (`provenance` DB), async SQLAlchemy + Alembic

## Source layout

```
src/provenance/
├── main.py              FastAPI app factory with lifespan hooks
├── config.py            Pydantic settings (ProvenanceSettings)
├── api/v1/
│   ├── nodes.py         CRUD for entities, activities, agents
│   ├── relations.py     Assert and query PROV-O edges
│   ├── events.py        Domain event ingest (idempotent via event_id)
│   ├── lineage.py       BFS graph traversal (upstream/downstream/both)
│   └── audit.py         Event audit log queries
├── services/
│   ├── prov_service.py      Entity/Activity/Agent CRUD
│   ├── relation_service.py  PROV-O relation queries
│   ├── event_service.py     Domain event ingest with idempotency
│   ├── lineage_service.py   BFS traversal for ancestry/descent graphs
│   └── jsonld_service.py    JSON-LD @context serialization
├── schemas/
│   ├── prov.py          PROV-O Pydantic models (Entity, Activity, Agent, Relations)
│   ├── events.py        Domain event types (CataloguePublished, ContractAgreementSigned, etc.)
│   └── context.py       JSON-LD @context definition
└── db/
    ├── engine.py        async engine + session factory
    └── models.py        prov_nodes, prov_relations, domain_events tables
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new PROV-O node type | `schemas/prov.py`, `services/prov_service.py`, `api/v1/nodes.py` |
| Add a new domain event type | `schemas/events.py`, `services/event_service.py` |
| Change lineage traversal | `services/lineage_service.py` |
| Add a new relation type | `schemas/prov.py`, `services/relation_service.py` |
| Modify JSON-LD output | `services/jsonld_service.py`, `schemas/context.py` |
| Database schema change | `db/models.py` → run `task db:revision MESSAGE=description` |

## Coding conventions

- All IRI identifiers use ULID-based URNs: `urn:ds:entity:<ulid>`
- Domain events are idempotent — duplicate `event_id` values are silently ignored
- BFS lineage uses raw SQL for graph traversal, not ORM queries
- JSON-LD `@context` is cached for 1 day via `jsonld_service`
- No triple store — relational tables with a `node_type` discriminator column
- PROV-O relations: `wasGeneratedBy`, `used`, `wasAssociatedWith`, `wasAttributedTo`, `wasDerivedFrom`, `actedOnBehalfOf`

## Domain event types

These are the events emitted by ds-connector and ingested here:

| Event | Trigger | Creates |
|-------|---------|---------|
| `CataloguePublished` | Provider syncs governance.yaml | Entity (dataset) + Activity (publish) |
| `ContractAgreementSigned` | Negotiation finalized | Activity (agreement) + relations |
| `DataTransferCompleted` | Transfer reaches STARTED state | Activity (transfer) + relations |
| `UsageObligationFulfilled` | Obligation met post-transfer | Activity (obligation) + relations |

## Testing

```bash
task setup          # install deps
task run            # dev server with hot-reload
task db:migrate     # apply migrations
pytest              # run tests
ruff check src/     # lint
```

Test database is SQLite (in-memory via `aiosqlite`).

## Integration points

- **Upstream**: ds-connector emits domain events via `POST /prov/events`
- **Upstream**: Portal queries lineage via `GET /prov/lineage/{iri}`
- **No downstream dependencies** — this is a pure sink/query service
