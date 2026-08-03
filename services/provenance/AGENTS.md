# ds-provenance

Stores one participant's provenance record as a W3C PROV-O graph and serves it as JSON-LD.
Sixteen typed domain events in, `prov_nodes` + `prov_relations` + a verbatim `domain_events`
row out, in one transaction. Two instances (provider 30000, consumer 31000), two databases.

## References

| | |
|---|---|
| Requirements | [DSSC · Provenance, Traceability & Observability](../../docs/blueprints/dssc/data-interoperability/provenance-traceability-observability.md) |
| Rules | [Rulebook · Provenance and logging](../../docs/rulebook/provenance-and-logging.md) — the event list, the storage and access decisions, and the observability gap |
| Code as committed | [docs/services/provenance.md](../../docs/services/provenance.md) |

## Where to work

| Task | Start at |
|---|---|
| New domain event type | `schemas/events.py` **and** `services/event_service.py` **and** the emitter in ds-connector — a schema with no materialiser produces a validated event that enters no graph |
| New PROV-O node or relation type | `schemas/prov.py`, `services/{prov,relation}_service.py`, `schemas/context.py` |
| Lineage traversal | `services/lineage_service.py` |
| JSON-LD output | `services/jsonld_service.py` + `schemas/context.py` |
| Schema change | `db/models.py` + `task db:revision MESSAGE=...` |

## Rules that are not visible from the code

- **No PII, ever.** Codes, pseudonymous DIDs and hashes only. The event-query projection
  publishes an event's *own* fields from the stored payload, so **whatever an event declares
  is published** — that is why payloads are PII-free by construction and must stay that way.
- **A participant's provenance store is not readable by another participant.** There is no
  cross-participant route and adding one is a rulebook change, not a feature.
- **`GET /prov/my/events` is a separate router mounted without a scope dependency**, because
  it authenticates a *person* from a verifiable credential. `subject_id` is deliberately not
  a parameter — it comes from the verified credential, so a subject cannot read someone
  else's history by changing it. A `provenance.read` token is not a data subject and gets 401.
- **Events are idempotent on `event_id`.** A caller that omits it gets one derived from the
  event's canonical payload, so a retry is still a no-op — but the caller no longer decides
  what "the same event" means, which is why every emitter should supply its own.
- **`AccessRequested` carries `purpose` (what the offer permits) and `declared_purpose`
  (what the consumer stated).** Two different facts; do not collapse them.
- The settings the subject route needs (`PROVENANCE_TRUST_ANCHOR_DID`,
  `PROVENANCE_TRUST_LIST_URL`, `PROVENANCE_DID_WEB_USE_HTTPS`, `PROVENANCE_VC_INSECURE_DEV`)
  are registered with `ProductionGuard` — unverified, anyone could claim any subject id. The
  key is **resolved from the anchor's DID document** (`DID-17`), never mounted here.

- **A lineage edge publishes direction and type separately, and both have consumers.**
  `ds:source`/`ds:target` carry direction — `services/portal`'s `classifyLineageGraph` splits
  the graph on them. `prov:entity`/`prov:activity`/`prov:agent` say what each end *is*, read
  off the node. Changing either shape changes the portal in the same commit.
- **`access_log` is derived from `QueryExecuted`, not only from `POST /audit/log`.** The
  direct route has no caller in the platform; the compliance log would otherwise be empty.

## Conventions

IRIs are URNs: `urn:activity:<kind>:<id>`, `urn:entity:agreement:<id>`,
`urn:ds:principal:<issuer>:<sub>`, `urn:ds:owner:<id>`. Datasets and participants keep the
IRI/DID the emitting event supplies. BFS lineage walks the edge table through the ORM. No
triple store — relational tables with a `node_type` discriminator.

Every edge points backwards in time, so `direction=upstream` follows subject→object
("how this came to be") and `downstream` follows object→subject ("what was made from it").

`task -d services/provenance run|test|lint|db:migrate`. Tests use SQLite via `aiosqlite`.
