# ds-provenance — Agent Guide

## Service identity

- **Role**: W3C PROV-O provenance and audit logging
- **Language**: Python 3.12, FastAPI
- **Port**: 30000 (debug: 30900)
- **URL**: `http://portal.dataspaces.localhost:9010/api/provenance/` (via Caddy), direct `http://172.17.0.1:30000`
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

- All IRI identifiers use UUID-based URNs: `urn:ds:entity:<uuid>`
- Domain events are idempotent — duplicate `event_id` values are silently ignored
- BFS lineage uses raw SQL for graph traversal, not ORM queries
- JSON-LD `@context` is cached for 1 day via `jsonld_service`
- No triple store — relational tables with a `node_type` discriminator column
- PROV-O relations: `wasGeneratedBy`, `used`, `wasAssociatedWith`, `wasAttributedTo`, `wasDerivedFrom`, `actedOnBehalfOf`, `wasInformedBy`

## Domain event types

These are the events emitted by ds-connector and ingested here:

| Event | Trigger | Creates |
|-------|---------|---------|
| `CataloguePublished` | Provider syncs governance.yaml | Entity (dataset) + Activity (publish) |
| `CatalogViewed` | Consumer browses provider catalog | Activity (view) |
| `AccessRequested` | Consumer requests access to a dataset | Activity (request) + relations. Carries `purpose` (what the offer permits) **and** `declared_purpose` (what the consumer stated) — see `docs/provenance-and-lineage.md`; do not collapse them |
| `NegotiationStarted` | Contract negotiation begins | Activity (negotiation) + relations |
| `NegotiationFinalized` | Contract negotiation reaches FINALIZED | Activity (finalization) + relations |
| `NegotiationTerminated` | Contract negotiation is terminated | Activity (termination) + relations |
| `ContractAgreementSigned` | Negotiation finalized | Activity (agreement) + relations |
| `TransferStarted` | Data transfer begins | Activity (transfer) + relations |
| `DataTransferCompleted` | Transfer reaches STARTED state | Activity (transfer) + relations |
| `QueryExecuted` | Dataspace-originated query executed | Activity (query) + relations |
| `UsageObligationFulfilled` | Obligation met post-transfer | Activity (obligation) + relations |
| `AccessRevoked` | Access to a dataset is revoked | Activity (revocation) + relations |
| `ConsentGranted` | Subject's data-sharing consent granted | Activity + dataset Entity + subject Agent |
| `ConsentRevoked` | Subject withdraws consent | Activity (`invalidated` the dataset) + subject Agent |
| `DataIngested` | DSO/offline handover recorded (`POST /admin/ingestion`) | Activity + dataset Entity (`wasGeneratedBy`) |
| `DataDisclosed` | Onboarding CSV export to a named recipient | Activity + recipient Agent |

> **Block C events carry codes, DIDs and hashes only — never PII.** `subject_id`
> is the pseudonymous subject DID; `legal_basis` is the Block B evidence record;
> `consent_snapshot_hash` is a recomputable SHA-256 over the authorising consent
> tuples. See `docs/provenance-and-lineage.md` § "No PII in provenance".

## Testing

```bash
task setup          # install deps
task run            # dev server with hot-reload
task db:migrate     # apply migrations
pytest              # run tests
ruff check src/     # lint
```

Test database is SQLite (in-memory via `aiosqlite`).

## Querying events

`GET /prov/events` filters on `event_type` (repeatable), `subject_id`,
`dataset_id`, `consumer_did`, `provider_did`, `agreement_id`, `occurred_after`,
`occurred_before`, and pages with `limit`/`offset`. The response carries
`hydra:totalItems` / `hydra:limit` / `hydra:offset` beside `@graph`, matching how
the federated catalogue pages.

**The projection publishes the event's own fields**, read from the stored payload,
plus the five indexed columns. It used to emit only four fixed columns, so
`ConsentGranted`, `ConsentRevoked`, `DataIngested` and `DataDisclosed` were stored
in full and served as four empty values. Two consequences worth keeping in mind:

- A newly added event type is fully visible without touching the query route —
  **so whatever an event declares is published.** Payloads are PII-free by
  construction (`schemas/events.py`); keep them that way.
- The columns stay in the output alongside the payload fields. They are the
  *normalised* dimensions — `DataIngested.dataset_id` and
  `CataloguePublished.data_product_id` both land in `data_product_id` — so a reader
  grouping across event types keeps working. Publishing only the payload silently
  renamed `ds:dataProductId` to `ds:datasetId` for some types.

### `GET /prov/my/events` — the subject's own history

A separate route on a **separate router mounted without a scope dependency**,
because it authenticates a *person* from a verifiable credential rather than a
service from a scope (`services/subject.py`). A `provenance.read` token is not a
data subject and gets a 401.

`subject_id` is deliberately not a parameter: it comes from the verified
credential, so a subject cannot read someone else's history by changing it. The
`domain_events.subject_id` column exists for this query — filtering a person's own
view by scanning JSON is both slower and easier to get subtly wrong.

Both settings this needs (`PROVENANCE_TRUST_ANCHOR_KEY_PATH`,
`PROVENANCE_VC_INSECURE_DEV`) are registered with the `ProductionGuard`: unverified,
anyone could claim any subject id.

## Integration points

- **Upstream**: ds-connector emits domain events via `POST /prov/events`
- **Upstream**: Portal queries lineage via `GET /prov/lineage/{iri}` and events via
  `GET /prov/events`; a data subject's timeline uses `GET /prov/my/events`
- **Shared**: `ds_auth.user_credentials` — the *same* verifier the connector uses,
  so both services agree on who a subject is
- **No downstream dependencies** — this is a pure sink/query service
