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
| **Traceability** — the whole path: how was the data handled and by whom | The same graph, plus the domain-event record | **Implemented.** `L-2` is closed, `DataDisclosed` has an in-repo emitter, and since 2026-08-09 every event type this rulebook names has one — see `L-1` |
| **Observability** — monitoring and troubleshooting | — | **Absent.** No metrics pipeline, no tracing, no OpenTelemetry. `/metrics` endpoints exist on all five services and are scraped by nothing. They are unauthenticated *by design* — reachability is a NetworkPolicy question, not an application one (§5 step 1) |

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
| L-1 | Every participant records all **fifteen** types. Recording is not optional and not per-dataset (`PTO-40`, `-41`) | **Enforced** since 2026-08-09, and the count changed because a type was **removed**. All fifteen have a reachable emitter in the connector, asserted by `services/connector/tests/test_prov_bridge_emitters.py`, whose `NOT_EMITTED_BY_THIS_CONNECTOR` set is now empty. `DataDisclosed` gained `POST /admin/disclosure` — previously emitted **out of this repository** by the onboarding service, which no deployment without that service recorded, and which could not satisfy `L-2` either since the hash it requires is computable only from the connector's own consent DB. **`UsageObligationFulfilled` was deleted rather than implemented**, and the reasoning is under `L-1a` |
| L-1a | A consumer's *self-report* that it met an obligation is not provenance, and this platform records none | **Enforced**, as a deliberate absence — decided 2026-08-09. `UsageObligationFulfilled` had a schema and a materialiser and no emitter anywhere; it is deleted. A provider cannot verify such a report — the obligations this platform declares (`notify_on_access`, `anonymize_before_use`, retention) are ones no third party can attest — so the record's only content would be that somebody said so, which is what `PROV-01` was with a hash. **Checked before deleting:** DSP has 11 messages and none is a post-agreement report in this direction, and EDC's policy monitor evaluates the *provider's own* view of the policy and accepts nothing from a counterparty — so no standard shape was declined. If a deployment ever has an obligation with a real attestor, the way back is a presented credential over the fulfilment, not a self-asserted event |
| L-2 | A `DataDisclosed` event carries a `consent_snapshot_hash` — a recomputable SHA-256 over the authorising consent tuples — proving *which* consent state backed the handover | **Enforced.** `consent_snapshot_hash` and `dataset_id` are both **required** on `DataDisclosed`, and the hash is pattern-checked as a bare lowercase SHA-256 digest — `"unknown"` and `"pending"` satisfy "the field is present" and prove nothing. The two are one requirement: a digest with no dataset id is a number nobody can recompute, and the dataset was not on the event at all. `POST /admin/disclosure` computes the hash from `consent_service.dataset_consent_snapshot` — the same function `DataIngested` uses — so the ordinary path cannot omit it, and a caller could not honestly supply one anyway. **Since 2026-08-27 that route also takes an `offer_id`**, because its caller has one and cannot have a dataset key: `D-13` keeps those out of the public projection deliberately, so an export scoped to one sharing offer had no way to name the argument the route demanded. The offer is resolved through `consent_vocabulary.datasets_for_offer` — the same authority `POST /consent/admin/shares` expands an offer with — and **one `DataDisclosed` is emitted per resolved dataset**, each with that dataset's own hash. Nothing about this rule moves: the hash stays dataset-scoped and stays recomputable. The expansion is server-side rather than in the caller because `datasets_for_offer` returns a **list**, and a caller reading its first element is correct until a second dataset declares the same offer and then silently wrong. `services/provenance/tests/test_events_consent.py`, `services/connector/tests/test_provenance_events.py`, `ds-e2e --flow onboarding-seam` |
| L-3 | Provenance records carry codes, pseudonymous DIDs and hashes only, never PII | **Enforced** — see [Personal data](personal-data.md) D-2 |
| L-4 | An event is recorded once. Re-posting the same event is a no-op, not a duplicate | **Enforced.** An event without an `event_id` now gets a key derived from its own canonical payload (`sha256:<hex>`, `occurred_at` included), so the idempotency check matches on a retry. Emission is non-fatal and therefore retried, which made a duplicate the ordinary outcome of a timeout rather than an edge case. `services/provenance/tests/test_event_idempotency.py` |
| L-5 | Every principal named in an event becomes an agent in the graph | **Enforced.** `AccessRevoked.subject_id` becomes an agent linked with `prov:role: dataSubject` — distinguishing "it was about them" from the two parties that performed it — and `acted_by` on `CataloguePublished` / `DataIngested` becomes a pseudonymous `urn:ds:principal:<issuer>:<sub>` agent, with `actedOnBehalfOf` to the owner it claimed to act for. `services/provenance/tests/test_event_agents.py` |

### When recording fails: two correct answers, chosen by position

`L-1` says recording is not optional; `L-4` says emission is non-fatal and therefore retried.
Read together those look contradictory, and a reader who "aligns" one code path with the other
will break it. The rule that reconciles them is **where the emitter sits relative to the thing
being recorded**:

| The event describes | Correct failure policy | Where |
|---|---|---|
| Something that **has already happened** — a negotiation concluded, a transfer started | **Non-fatal, retried.** It cannot be un-happened, so refusing records nothing and loses the fact as well | `services/connector`'s `ProvBridge` |
| Something **about to happen**, which this component still controls | **Fatal.** Refuse, and there is nothing to record | a data-plane PEP's `QueryExecuted` |

A `QueryExecuted` from a PEP is the second kind: the rows are read and narrowed but not yet
returned, so a request that fails at the audit step discloses nothing. Serving them anyway
would leave a disclosure with no record, which is precisely what `L-1` forbids.

`services/dataset-api-mock` — the reference PEP — refuses, uniformly, for every shape of audit
failure. It previously had three policies for one event: a non-2xx was ignored, a connection
error was swallowed, and a token-fetch failure raised a 500. Two of the three served the rows.

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

**Narrowing, and no longer the same gap.** Three of the four steps below are closed; step 4
is the one left, and one of its four SLIs was already derivable. Recording that precisely,
rather than omitting the section or claiming the whole capability, is its point.

What `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` ask for and what exists:

| Asked | Status |
|---|---|
| Transaction observability for monitoring and troubleshooting (`-03`) | **present as of 2026-08-09** — traces span the services and the DSP hop, correlated by `ds.dsp.agreement_id`; see step 3. Before that: the troubleshooting floor only.** Until `libs/ds-obs`, *no Python service configured logging at all* — the root logger dropped INFO, so every service's own `log.info` reached nobody and only failures were visible. A successful crawl and no crawl were indistinguishable in `docker logs`. That is now one configured, level-controlled format across every service (`DS_LOG_LEVEL`, `DS_LOG_FORMAT`, `DS_LOG_ACCESS_HEALTH`). It is a floor, not the capability: nothing correlates a transaction across services |
| Horizontal and vertical requirements satisfied (`-42`, `-43`) | absent |
| Security controls, audit trails, compliance documentation maintained (`-44`–`-46`) | audit trail partially — see L-12 |
| Centralised metrics collection and visualisation | **absent, but every service is now a target.** `/metrics` is served by **all five** — `ds-identity-registry` was the last without one and gained it 2026-08-07, endpoint and `metricsFromPrometheus` NetworkPolicy in the same change — and scraped by nothing: no collector is deployed and **no chart emits a ServiceMonitor**, so `global.monitoring.serviceMonitor` opens the network path and nothing walks through it. That flag is now the only thing left between the targets and a collector |
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

   **`ds-identity-registry` closed 2026-08-07** — it served no `/metrics` at all, so the one
   component every participant depends on for identity was the only one nothing could
   observe. Endpoint and NetworkPolicy landed together, which is the lesson `ds-provenance`
   left one step earlier: *a target needs a path to it in the same change*, or turning
   `serviceMonitor` on aims a scrape at a pod default-deny still refuses and the only signal
   is a metric that never appears. Verified live on the dev stack — request counters and the
   latency histogram labelled by **route template**, `<unmatched>` for an unrouted URL — and
   the registry's own role sweep classifies the path, so an instance that mounted it without
   classifying it refuses to start (`roles.APP_PATHS`).

   **Closed 2026-08-08.** All four service charts emit a `ServiceMonitor`, gated on the same
   `global.monitoring.serviceMonitor` flag as the NetworkPolicy — both halves or neither, since
   a policy without a monitor opens a path nothing walks through (which is what this platform
   shipped) and a monitor without a policy is refused by default-deny (which is what
   `ds-provenance` did). It selects the Service by label and scrapes the **port name** `http`,
   not a number: a ServiceMonitor naming a port that does not exist scrapes nothing and reports
   nothing, which is the same silence this closes. Off by default, because a `ServiceMonitor`
   referencing a CRD the cluster lacks is a failed install.

   **The metric set**, served by every ds service at `GET /metrics` in Prometheus text format
   `0.0.4`:

   | Metric | Type | Labels | Meaning |
   |---|---|---|---|
   | `ds_service_up` | gauge | `service` | 1 while the process serves |
   | `ds_service_uptime_seconds` | gauge | `service` | seconds since start |
   | `ds_http_requests_total` | counter | `service`, `method`, `path`, `status` | requests, by outcome |
   | `ds_http_request_duration_seconds_bucket` / `_sum` / `_count` | histogram | `service`, `method`, `path` | latency, from which a quantile is derivable |

   **`path` is the route template, never the request URL** — `/admin/participants`, not
   `/admin/participants/did:web:…`. An unmatched request reports `<unmatched>`. The distinction
   is load-bearing: the version this replaces labelled by raw URL and minted one permanent
   series per URL anyone tried, which is a cardinality leak reachable by an anonymous caller.
3. OpenTelemetry traces across the DSP exchange, correlated by agreement id.
   **Done 2026-08-09.** The three-names-for-one-agreement-id problem it waited on was
   settled by `EDCL-06`: `dsp_agreement_id` is the *shared* id, `agreement_id` is local,
   and the correlation key has to be the first.

   **One switch, two languages.** `OTEL_EXPORTER_OTLP_ENDPOINT` — OpenTelemetry's own
   variable name, deliberately not a `DS_` alias — turns tracing on for the Python services
   through `ds_obs.tracing` and for the EDCs through the OpenTelemetry Java agent, which
   `services/edc-connector/entrypoint.sh` attaches on the same condition. So a deployment
   cannot enable half an exchange, which is the one failure mode that would leave the DSP
   hop dark while everything else looked instrumented. Unset means off everywhere, and each
   process says which at startup: *"no spans arriving"* and *"never switched on"* are
   otherwise the same observation.

   **The DSP hop is the EDCs' to produce, not ours.** A negotiation runs consumer EDC →
   provider EDC and neither is instrumented in this repository's code. EDC's own decision
   record (`2022-02-07-tracing`) settles the mechanism as the Java agent and propagates W3C
   trace context across the boundary — which is why the agent is in the image rather than a
   Python span pretending to cover a hop it cannot see.

   **Correlation is by attribute, not by parent span**, and that is what makes it survive a
   real dataspace. A counterparty exports to its own backend and may run no tracing at all,
   so a trace that needs both halves joinable works in dev and nowhere else. Every span a ds
   service emits while an agreement is in scope carries `ds.dsp.agreement_id`, stamped by a
   span processor rather than by tagging call sites — a hand-kept set of tag sites is the
   shape `E2E-03` and `E2E-14` both had to fix. The consumer's and provider's spans then
   carry the same value even when their traces never meet.

   | Property | Value |
   |---|---|
   | Protocol | OTLP over HTTP (`/v1/traces`) |
   | Server spans | named by **route template**, `/health` and `/metrics` excluded |
   | Client spans | every outbound `httpx` call, in all four Python services |
   | EDC spans | the Java agent's, including the DSP hop, named per participant via `OTEL_SERVICE_NAME` |
   | Correlation | `ds.dsp.agreement_id` on every span in scope |
   | Not covered | database spans. Deferred rather than half-installed: the instrumentation hooks engine *creation*, and `connector.db.engine` builds its engine at import, before any app factory runs — installing it yields a working import, no spans, and nothing saying so |

   **The two mechanisms are complementary, and it is worth knowing which does what.** The
   attribute is on ds's own spans; the EDCs' spans are the Java agent's and carry no ds
   vocabulary. Inside one deployment they still land in the same trace, because the agent
   propagates trace context across the DSP hop — so "find the agreement, then read the whole
   exchange" is one query on the attribute followed by the trace id. Across two independently
   operated participants only the attribute survives, which is why it is the recorded key.

   **Measured on the dev stack, 2026-08-09**, after a full `task e2e:all`: seven services
   reporting (`ds-connector`, `ds-identity-registry`, `ds-provenance`,
   `ds-federated-catalog`, and `edc-rec`, `edc-third-party`, `edc-grid-operator`), **12
   traces spanning two EDCs plus three ds services** — both provider pairs among them — and
   `ds.dsp.agreement_id` present on the connector's spans for every agreement the run
   signed.

   Dev runs a Jaeger all-in-one at `http://tracing.dataspaces.localhost`, in the root
   compose, for the reason step 2 learned the hard way: **a target needs something to send
   to, in the same change**, or the only signal is a span that never appears.
4. SLIs and SLOs for the four operations that matter: catalogue fetch, negotiation to
   agreement, transfer to first row, consent decision to negotiation resume.
   **The only step still open, and now unblocked for all four.** *Catalogue fetch* is a
   single HTTP request the histogram measures directly. The other three are cross-service
   business latencies that no per-request histogram can express — they needed step 3, which
   now exists: each is the span of a trace filtered by `ds.dsp.agreement_id`.

   **Decided 2026-08-09: adopt provisional targets, then measure reality against them.**
   The alternative — measure first, commit later — sounds more rigorous and is how a platform
   ends up with four dashboards and no obligation. A number somebody can be wrong about is
   what makes the measurement worth reading.

   | SLI | Measured from | Provisional SLO |
   |---|---|---|
   | Catalogue fetch | `ds_http_request_duration_seconds{path="/consumer/catalog"}` | p95 < **2s** |
   | Negotiation → agreement | trace span set for one `ds.dsp.agreement_id`, request → FINALIZED | p95 < **30s** |
   | Transfer → first row | trace, transfer-start → first `/internal/dataplane/authorize` | p95 < **10s** |
   | Consent decision → negotiation resume | trace, consent write → negotiation leaves `pending` | p95 < **90s** |

   **These are provisional and labelled as such.** They are engineering judgement, not
   measurement: nothing has been observed against them yet, and the point of writing them down
   is that the first month's data will move them.

   **One of them is bounded below by the platform, and that is not negotiable by an SLO.**
   `DS_ACCESS_SCOPE_CACHE_TTL_SECONDS` is 60s, and `fail-closed` measures the consequence: a
   decision the EDC has cached is reused for up to that long, so *consent decision → resume*
   cannot beat 60s by construction. A target under it would be unachievable however well the
   platform performed — the same class of error as an SLO on a path whose retry budget exceeds
   it. Tightening that one means shortening the cache first, and the cache is also the window
   in which the platform cannot fail closed.

   **Not yet decided, and it changes where these belong:** whether these are internal health
   indicators or something a participant is promised. If the latter they are a rulebook
   obligation with a counterparty; if the former they are an operations concern and this table
   is documentation. They are recorded here as the former until somebody commits them.

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
| L-15 | An event type has a schema, a materialiser and an emitter, or it does not exist | **Enforced** since 2026-08-09. `POST /webhooks/transfer-process` has a producer (`TransferEventPublisher` in `services/edc-extensions`), so `TransferStarted` and `DataTransferCompleted` are reachable on the provider side, and `DataDisclosed` has one in `POST /admin/disclosure`. `UsageObligationFulfilled` was the one type this rule said did not exist while the schema still accepted it — **the schema is gone**, and `services/provenance/tests/test_events.py` asserts the event type is now refused, which is also the guard against it returning as a write-only surface. Two schema-accepted relation types still have no materialiser (defect **P3-4**) |
| L-16 | Provenance is retained for the life of the deployment and survives a participant's departure | **Declared** |

## Blueprint rows

**Closed by this page:** `DSSC-PTO-01`, `-02`, `-05`, `-06`, `-07`, `-08`, `-09`, `-10`,
`-11`, `-12`, `-13`, `-14`, `-15`, `-16`, `-17`, `-19`, `-20`, `-21`, `-40`, `-41`, `-58`,
`-59`, `-75`, `-81`, `-84`.

**Open:** `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` (observability, §5). `DSSC-PTO-83`
(declared, unmeasured). `DSSC-PTO-79` is **closed** — defect `P1-4` is fixed and `L-12` now
records how.

**Closed, and without the caveat this paragraph used to carry.** `-40` and `-41` are claimed on
all fifteen event types having a reachable emitter (`L-1`). The sixteenth,
`UsageObligationFulfilled`, was **deleted** rather than implemented (`L-1a`): a consumer's
unverifiable self-report is not provenance, and neither DSP nor EDC models one.
