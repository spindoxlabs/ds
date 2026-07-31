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
- **Events are idempotent on `event_id`.** A caller that omits it defeats the check.
- **`AccessRequested` carries `purpose` (what the offer permits) and `declared_purpose`
  (what the consumer stated).** Two different facts; do not collapse them.
- Both settings the subject route needs (`PROVENANCE_TRUST_ANCHOR_KEY_PATH`,
  `PROVENANCE_VC_INSECURE_DEV`) are registered with `ProductionGuard` — unverified, anyone
  could claim any subject id.

## Conventions

IRIs are UUID-based URNs (`urn:ds:entity:<uuid>`). BFS lineage uses raw SQL, not the ORM. No
triple store — relational tables with a `node_type` discriminator.

`task -d services/provenance run|test|lint|db:migrate`. Tests use SQLite via `aiosqlite`.
