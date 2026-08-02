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
| **Provenance** — backward-looking: where did the data come from | PROV-O graph of entities, activities and agents | **Implemented.** The defects that stopped it rendering are closed (`L-5`, `L-7`, `L-8`, `L-12`) |
| **Traceability** — the whole path: how was the data handled and by whom | The same graph, plus the domain-event record | **Implemented.** The remaining gap is `L-2` and the two event types `L-1` names, not the graph |
| **Observability** — monitoring and troubleshooting | — | **Absent.** No metrics pipeline, no tracing, no OpenTelemetry. `/metrics` endpoints exist and are scraped by nothing. They are unauthenticated *by design* — reachability is a NetworkPolicy question, not an application one (§5 step 1) |

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
| L-1 | Every participant records all sixteen types. Recording is not optional and not per-dataset (`PTO-40`, `-41`) | **Partly enforced.** Fourteen of the sixteen have a reachable emitter in the connector, asserted by `services/connector/tests/test_prov_bridge_emitters.py`. `DataDisclosed` is emitted **out of this repository**, by the onboarding service after a CSV export — it holds `provenance.write` and posts to `POST /prov/events` directly, so a deployment without that service records none. `UsageObligationFulfilled` is emitted by **nothing, anywhere**: it is a consumer *reporting* an obligation it met, and no inbound route exists to receive that report. Both had a dead method on `ProvBridge` that made them look covered from inside the connector; the methods are gone and the gap is here instead |
| L-2 | A `DataDisclosed` event carries a `consent_snapshot_hash` — a recomputable SHA-256 over the authorising consent tuples — proving *which* consent state backed the handover | **Not enforced.** The field is `str \| None = None` in `services/provenance/src/provenance/schemas/events.py`, so an event omitting it is accepted and stored; and per `L-1` the connector emits no `DataDisclosed` at all, so the only producer is out of repo and nothing here can compute the hash for it. The *mechanism* exists and works — `consent_service.dataset_consent_snapshot` / `consent_snapshot_hash`, used by `DataIngested` — it is the requirement that is unasserted. A `services/provenance` row |
| L-3 | Provenance records carry codes, pseudonymous DIDs and hashes only, never PII | **Enforced** — see [Personal data](personal-data.md) D-2 |
| L-4 | An event is recorded once. Re-posting the same event is a no-op, not a duplicate | **Enforced.** An event without an `event_id` now gets a key derived from its own canonical payload (`sha256:<hex>`, `occurred_at` included), so the idempotency check matches on a retry. Emission is non-fatal and therefore retried, which made a duplicate the ordinary outcome of a timeout rather than an edge case. `services/provenance/tests/test_event_idempotency.py` |
| L-5 | Every principal named in an event becomes an agent in the graph | **Enforced.** `AccessRevoked.subject_id` becomes an agent linked with `prov:role: dataSubject` — distinguishing "it was about them" from the two parties that performed it — and `acted_by` on `CataloguePublished` / `DataIngested` becomes a pseudonymous `urn:ds:principal:<issuer>:<sub>` agent, with `actedOnBehalfOf` to the owner it claimed to act for. `services/provenance/tests/test_event_agents.py` |

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
| L-7 | The JSON-LD `@context` defines every relation the ingest path can produce | **Enforced, by a sweep rather than by review.** `invalidated` is defined in `PROV_CONTEXT` and accepted by `POST /prov/relations`, which used to reject the one term its own ingest path writes. `services/provenance/tests/test_relation_vocabulary.py` scans the materialisers and fails on any relation the schema or the context does not also carry. `actedOnBehalfOf` and `wasInformedBy` remain accepted without a materialiser deliberately: this is a general PROV-O graph API, and the manual door should not be narrower than the vocabulary it publishes |
| L-8 | A node's PROV-O type is a property of the node, not of the position it first appeared in | **Enforced.** `upsert_node` reclassifies a node when a later event names a different type, and `relation_to_jsonld` labels each endpoint from the node's own `node_type` — `prov:entity` / `prov:activity` / `prov:agent` — instead of hardcoding subject→entity, object→activity. Direction moved to `ds:source` / `ds:target`, which is what `services/portal` now splits the graph on: the typed keys cannot carry direction when both ends share a type. `services/provenance/tests/test_jsonld_service.py`, `services/portal/tests/unit/lineage.test.ts` |
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
| L-12 | Mandatory P&T data can be accessed and presented on demand (`PTO-79`) | **Enforced.** The lineage graph renders edges (see `L-8`), and `access_log` is written from `QueryExecuted` — the connector's PEP route `POST /internal/audit/query` already forwards it, so the compliance log is derived from the event that arrives rather than from a second caller nothing was ever taught to make. `GET /audit/log`'s `subject_id` parameter, declared since the route was written and never applied, now narrows the log. `services/provenance/tests/test_audit_log.py` |
| L-13 | A service reading lineage holds a scope that permits it | **Enforced.** The lineage router accepts `provenance.read` **or** `.write`, as the nodes and events routers already did. `svc-ds-connector` holds `provenance.write` and nothing else here, so requiring `.read` alone 403'd the only service that would call it — and a caller trusted to write the graph is not a narrower principal than one trusted to read it |
| L-14 | Recording must not slow the data path (`PTO-83`) | **Declared** — emission is a side call; no measurement exists |

## 5. Observability — the open gap

**Still an open gap.** Two of the four steps below have moved and none is closed; recording
that precisely, rather than omitting the section or claiming the capability, is its point.

What `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` ask for and what exists:

| Asked | Status |
|---|---|
| Transaction observability for monitoring and troubleshooting (`-03`) | **absent for transactions; the troubleshooting floor now exists.** Until `libs/ds-obs`, *no Python service configured logging at all* — the root logger dropped INFO, so every service's own `log.info` reached nobody and only failures were visible. A successful crawl and no crawl were indistinguishable in `docker logs`. That is now one configured, level-controlled format across every service (`DS_LOG_LEVEL`, `DS_LOG_FORMAT`, `DS_LOG_ACCESS_HEALTH`). It is a floor, not the capability: nothing correlates a transaction across services |
| Horizontal and vertical requirements satisfied (`-42`, `-43`) | absent |
| Security controls, audit trails, compliance documentation maintained (`-44`–`-46`) | audit trail partially — see L-12 |
| Centralised metrics collection and visualisation | **absent, but the targets are now worth collecting.** `/metrics` is served by four services and scraped by nothing: no collector is deployed and **no chart emits a ServiceMonitor** — `global.monitoring.serviceMonitor` gates only the NetworkPolicy, so with it on the network path opens and nothing walks through it. `ds-identity-registry` serves no `/metrics` at all |
| Real-time monitoring | absent |
| Global performance metrics, SLIs, SLOs | **possible, not built.** Latency was a bare `_sum` with no `_count`, no buckets and no path label, so no quantile was derivable from any service. `libs/ds-obs` makes it a histogram, which is what an SLI needs. Nothing consumes it yet, and the three *cross-service* operations below are still unmeasurable |
| Regular reports on performance, usage and security incidents | absent |

**Minimum viable close**, in order:

1. ~~Authenticate `/metrics`~~ — **done, and not the way this said.** Exposure is a
   deployment concern, answered by the chart: `global.networkPolicy.enabled` (true by
   default) applies default-deny and `ds.networkPolicy.metricsFromPrometheus` opens the port
   to the Prometheus namespace only, gated on `global.monitoring.serviceMonitor` (false by
   default). With chart defaults `/metrics` is reachable by nobody. Requiring a Keycloak
   token instead would **break** collection — a scraper holds none — replacing a working
   production control with a broken one; see decision `D-2` under `services/connector`.
   What was actually missing was narrower: `ds-provenance`'s chart omitted the
   `metricsFromPrometheus` include the connector and federated-catalogue charts carry, so
   with `serviceMonitor` on, its pod was still refused by default-deny. Added.

   **Correction:** an earlier draft of this step said that enabling `serviceMonitor`
   "produced a ServiceMonitor". It does not — **no chart in this repository emits a
   `ServiceMonitor` resource**, and the flag gates the NetworkPolicy alone. That is part of
   step 2, not a detail of step 1.
2. A Prometheus-compatible scrape target per service with a documented metric set.
   **Half done.** `libs/ds-obs` replaced four byte-identical copies of a per-service
   `metrics.py` with one implementation, and fixed the two things that made the targets not
   worth scraping: latency is a **histogram** (`_bucket`/`_sum`/`_count`, labelled by method
   and path) instead of a bare sum, and an unmatched route reports `<unmatched>` instead of
   its raw URL — which had been minting one permanent Prometheus series per URL anyone
   tried. The redundant `ds_http_5xx_total` family is gone.

   Still open, and all three are needed before a collector is useful:
   `ds-identity-registry` serves no `/metrics` and its chart carries no
   `metricsFromPrometheus`; **no chart emits a `ServiceMonitor`**, so nothing tells
   Prometheus what to scrape; and the metric set is described in `libs/ds-obs/AGENTS.md` but
   is **not documented in `docs/`**, which is what this step asks for.
3. OpenTelemetry traces across the DSP exchange, correlated by agreement id — which
   requires settling the three-names-for-one-agreement-id problem first (defect P3-4).
4. SLIs and SLOs for the four operations that matter: catalogue fetch, negotiation to
   agreement, transfer to first row, consent decision to negotiation resume.
   **Unblocked for one of the four.** *Catalogue fetch* is a single HTTP request and the new
   histogram measures it directly. The other three are **cross-service business latencies** —
   they span the connector, the EDC, the data plane and a human consent decision, and no
   per-request HTTP histogram can express them. They need either step 3's traces or
   purpose-built domain timers, and they remain unmeasurable.

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
| L-15 | An event type has a schema, a materialiser and an emitter, or it does not exist | **Partly enforced** — `POST /webhooks/transfer-process` now has a producer (`TransferEventPublisher` in `services/edc-extensions`), so `TransferStarted` and `DataTransferCompleted` are reachable on the provider side. `UsageObligationFulfilled` has a schema and a materialiser and **no emitter in any component**, which by this rule means it does not exist; see `L-1`. Two schema-accepted relation types still have no materialiser. Defect **P3-4** |
| L-16 | Provenance is retained for the life of the deployment and survives a participant's departure | **Declared** |

## Blueprint rows

**Closed by this page:** `DSSC-PTO-01`, `-02`, `-05`, `-06`, `-07`, `-08`, `-09`, `-10`,
`-11`, `-12`, `-13`, `-14`, `-15`, `-16`, `-17`, `-19`, `-20`, `-21`, `-40`, `-41`, `-58`,
`-59`, `-75`, `-81`, `-84`.

**Open:** `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` (observability, §5). `DSSC-PTO-79`
(defect P1-4). `DSSC-PTO-83` (declared, unmeasured).
