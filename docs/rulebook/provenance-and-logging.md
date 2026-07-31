# Provenance and logging

Which events are recorded, in what model, stored where, readable by whom, and kept how long.

Covers `DSSC-PTO-01`–`89`. This is the building block where the blueprint asks the most
questions and this platform has the largest gap — observability, one of its three named
capabilities, does not exist.

## 1. The three capabilities

`DSSC-PTO-01`, `-02`, `-03` state three required capabilities. Their status here differs
sharply and that difference is the headline of this page.

| Capability | Meaning | Status |
|---|---|---|
| **Provenance** — backward-looking: where did the data come from | PROV-O graph of entities, activities and agents | **Implemented**, with defects that stop it rendering |
| **Traceability** — the whole path: how was the data handled and by whom | The same graph, plus the domain-event record | **Implemented**, with defects |
| **Observability** — monitoring and troubleshooting | — | **Absent.** No metrics pipeline, no tracing, no OpenTelemetry. `/metrics` endpoints exist, are unauthenticated, and are scraped by nothing |

Note that **CEEDS drops Observability entirely** — its building block is named "Provenance
& traceability" and the concern appears nowhere in that blueprint. So this gap costs DSSC
rows and no CEEDS rows. DSSC nonetheless states the capability as required, and this
rulebook does not pretend otherwise. See §5.

## 2. Which events are recorded

`DSSC-PTO-05`–`-09` require the data space to decide, and record, which events must be
logged, for which data products, and to identify the legal and contractual requirements
that mandate specific logging.

**Decision: sixteen event types, recorded by every participant, for every data product,
without exception.** There is no per-dataset opt-out — a selective provenance record is not
evidence.

| Event | Emitted when | Plane |
|---|---|---|
| `CataloguePublished` | a provider syncs its governance file into EDC | control |
| `CatalogViewed` | a consumer fetches a catalogue | control |
| `AccessRequested` | a consumer asks for access | control |
| `NegotiationStarted` | a contract negotiation begins | control |
| `NegotiationFinalized` | it reaches an agreement | control |
| `NegotiationTerminated` | it ends without one | control |
| `ContractAgreementSigned` | an agreement is recorded | control |
| `TransferStarted` | a transfer process starts | control |
| `DataTransferCompleted` | it completes | control |
| `QueryExecuted` | the data plane serves rows | **data** |
| `UsageObligationFulfilled` | a consumer reports meeting an obligation | control |
| `AccessRevoked` | access is withdrawn | control |
| `ConsentGranted` | a subject grants | control |
| `ConsentRevoked` | a subject revokes | control |
| `DataIngested` | an operator records a manual handover into the platform | data |
| `DataDisclosed` | data leaves the platform to a named recipient | data |

**Control-plane events** (`PTO-08`): everything above except `QueryExecuted`,
`DataIngested` and `DataDisclosed`.
**Data-transformation events** (`PTO-09`): those three.

### What mandates the logging (`PTO-06`, `PTO-07`)

| Source | Requirement | Events that serve it |
|---|---|---|
| GDPR Art. 5(2), 7(1), 30 | accountability; demonstrating consent; records of processing | `ConsentGranted`, `ConsentRevoked`, `DataDisclosed`, `QueryExecuted` |
| GDPR Art. 28 | processor instructions and records | `DataDisclosed`, `ContractAgreementSigned` |
| Contractual — billing and audit | who received what, under which agreement | `ContractAgreementSigned`, `DataTransferCompleted`, `QueryExecuted` |
| Data space governance | evidence that policies were enforced | the negotiation triple, `AccessRevoked` |

| # | Rule | Status |
|---|---|---|
| L-1 | Every participant records all sixteen types. Recording is not optional and not per-dataset (`PTO-40`, `-41`) | **Enforced** in the connector's emission path for the events it produces |
| L-2 | A `DataDisclosed` event carries a `consent_snapshot_hash` — a recomputable SHA-256 over the authorising consent tuples — proving *which* consent state backed the handover | **Enforced** |
| L-3 | Provenance records carry codes, pseudonymous DIDs and hashes only, never PII | **Enforced** — see [Personal data](personal-data.md) D-2 |
| L-4 | An event is recorded once. Re-posting the same event is a no-op, not a duplicate | **Not enforced** — an event without an `event_id` gets a fresh UUID, so the idempotency check never matches. Defect **P1-4** |
| L-5 | Every principal named in an event becomes an agent in the graph | **Not enforced** — `AccessRevoked.subject_id` and `acted_by` on two event types are never materialised. Defect **P1-4** |

## 3. The data model

`DSSC-PTO-10` requires the data space to choose a model; `-11` requires an existing open
standard; `-12` and `-13` require any extension to be a documented domain profile.

**Decision: W3C PROV-O, serialised as JSON-LD, with a documented domain profile.**

Every domain event is materialised into `prov_nodes` (Entity / Activity / Agent) and
`prov_relations` (PROV-O edges) inside a single transaction, and the validated event
payload is kept verbatim for replay.

**The domain profile** (`PTO-12`, `-13`) is the sixteen event types above plus the
platform's own vocabulary of entity and activity IRIs. It extends PROV-O rather than
replacing it: every relation is a PROV-O relation, and the extension is in *what* is named,
not *how*.

| # | Rule | Status |
|---|---|---|
| L-6 | The model is PROV-O. A participant storing logs in another model does not satisfy this rulebook | **Declared** |
| L-7 | The JSON-LD `@context` defines every relation the ingest path can produce | **Not enforced** — `PROV_CONTEXT` has no term for `invalidated`, which the ingest path writes, and the relation schema accepts two relation types no materialiser produces while rejecting one it does. Defect **P1-4** |
| L-8 | A node's PROV-O type is a property of the node, not of the position it first appeared in | **Not enforced** — `upsert_node` matches on IRI alone and never updates `node_type`, and edge endpoints are labelled by position rather than by the nodes' actual types. Defect **P1-4** |
| L-9 | All principles from the Data Models building block apply to this data too (`PTO-59`) | **Declared** — see [Data models](data-models.md) |

## 4. Storage and access

`DSSC-PTO-14` asks how logs are stored and who can access them; `-15` asks whether storage
is local to participants or with an independent third party; `-16` asks for clear rules on
who may access what, under which conditions; `-17` requires those rules to be technically
enforceable.

**Decision: local storage, per participant. There is no independent Observability Service
and no third-party clearing house.**

| Question | Answer |
|---|---|
| Where (`PTO-15`) | Each participant runs its own `ds-provenance` over its own database. Provider and consumer each hold their own half of the record |
| Redundancy (`PTO-75`) | Both parties to an exchange record it independently. Neither copy is authoritative over the other; a discrepancy is a governance matter, not a technical one |
| Who may read (`PTO-16`) | Three audiences, three mechanisms — below |
| Enforceability (`PTO-17`) | Scope-based authorisation on the service routes; VC-based authentication on the subject route |

| Audience | Surface | Authorisation |
|---|---|---|
| The participant's own operators | `/prov/*`, `/audit/*` | `provenance.read` / `provenance.write` |
| A data subject, about themselves | the subject-facing event view | VC-JWT, verified against the trust-anchor key |
| Another participant | **nothing** | There is no cross-participant provenance API |

**The third row is a decision, not an omission.** A participant's provenance store is not
readable by its counterparty. Evidence sharing between participants is a governance
process — a party requests, a party produces — not an API. `DSSC-PTO-81` asks that trust
between a third-party observer and all other parties be ensured; the way this platform
ensures it is by having no third-party observer.

| # | Rule | Status |
|---|---|---|
| L-10 | A participant's provenance store is not readable by another participant | **Enforced** — no such route exists |
| L-11 | A subject may read the record concerning themselves, authenticated by credential rather than by service scope | **Enforced** |
| L-12 | Mandatory P&T data can be accessed and presented on demand (`PTO-79`) | **Not enforced.** The lineage graph renders zero edges in the portal, and the `access_log` compliance table is never populated because nothing calls the route that writes it. Defect **P1-4** |
| L-13 | A service reading lineage holds a scope that permits it | **Not enforced** — the lineage router requires `provenance.read`; the only service client that would call it holds `provenance.write` only. Defect **P1-4** |
| L-14 | Recording must not slow the data path (`PTO-83`) | **Declared** — emission is a side call; no measurement exists |

## 5. Observability — the open gap

**Nothing here is implemented.** Recording it as a gap rather than omitting it is the point
of this section.

What `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` ask for and what exists:

| Asked | Status |
|---|---|
| Transaction observability for monitoring and troubleshooting (`-03`) | absent |
| Horizontal and vertical requirements satisfied (`-42`, `-43`) | absent |
| Security controls, audit trails, compliance documentation maintained (`-44`–`-46`) | audit trail partially — see L-12 |
| Centralised metrics collection and visualisation | absent. `/metrics` is exposed on four services, unauthenticated, and scraped by nothing |
| Real-time monitoring | absent |
| Global performance metrics, SLIs, SLOs | absent |
| Regular reports on performance, usage and security incidents | absent |

**Minimum viable close**, in order:

1. Authenticate `/metrics` or move it behind the cluster boundary — it is currently a
   security item as well as an observability one (defect P0-1).
2. A Prometheus-compatible scrape target per service with a documented metric set.
3. OpenTelemetry traces across the DSP exchange, correlated by agreement id — which
   requires settling the three-names-for-one-agreement-id problem first (defect P3-4).
4. SLIs and SLOs for the four operations that matter: catalogue fetch, negotiation to
   agreement, transfer to first row, consent decision to negotiation resume.

## 6. Governance of these rules

`DSSC-PTO-19`, `-20`, `-21` require the agreements to be governed, recorded in the rulebook,
and maintained by a defined process.

1. The event vocabulary is code (`services/provenance/src/provenance/schemas/events.py`).
   Adding an event type means adding the schema, the materialiser and the emission point in
   the same change — a schema with no materialiser produces a validated event that enters
   no graph.
2. Any change to the sixteen types is a change to this page, in the same commit.
3. Removing an event type is a breaking change for any deployment relying on it as evidence
   and requires the same notice as a protocol change.
4. Retention of the provenance record itself: **kept for the life of the deployment.** It is
   evidence about the data space, not about a participant, and survives that participant's
   departure. A deployment with a statutory retention limit must set its own and record it
   in its own agreement text.

| # | Rule | Status |
|---|---|---|
| L-15 | An event type has a schema, a materialiser and an emitter, or it does not exist | **Partly enforced** — `POST /webhooks/transfer-process` now has a producer (`TransferEventPublisher` in `services/edc-extensions`), so `TransferStarted` and `DataTransferCompleted` are reachable on the provider side. Two schema-accepted relation types still have no materialiser. Defect **P3-4** |
| L-16 | Provenance is retained for the life of the deployment and survives a participant's departure | **Declared** |

## Blueprint rows

**Closed by this page:** `DSSC-PTO-01`, `-02`, `-05`, `-06`, `-07`, `-08`, `-09`, `-10`,
`-11`, `-12`, `-13`, `-14`, `-15`, `-16`, `-17`, `-19`, `-20`, `-21`, `-40`, `-41`, `-58`,
`-59`, `-75`, `-81`, `-84`.

**Open:** `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` (observability, §5). `DSSC-PTO-79`
(defect P1-4). `DSSC-PTO-83` (declared, unmeasured).
