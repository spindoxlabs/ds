# Data exchange

Which protocols this data space accepts, at which version, and under what conditions data
may move.

Covers `DSSC-DEX-01`–`09`, `-18`–`-26`, `-29`–`-39`, `-50`–`-65` and the framing section
`DSSC-CDP`.

## 1. Accepted protocols

**Decision.** Two protocols, at two layers, and nothing else is accepted.

| Layer | Protocol | Version | Transport |
|---|---|---|---|
| **Control plane** — catalogue, negotiation, transfer initiation | Dataspace Protocol (DSP) | `dataspace-protocol-http:2025-1` | HTTPS |
| **Data plane** — the transfer itself | HTTP, pull, via an Endpoint Data Reference | — | HTTPS |
| **Identity** (control plane) | Decentralized Claims Protocol (DCP) | as implemented by EDC 0.16.0 | HTTPS |

`DSSC-DEX-20` requires the Dataspace Protocol between control planes and `CEEDS-STD-19`
calls it a prerequisite for joining any data space. This platform treats it as mandatory,
matching the firmer of the two statements.

**The version is pinned and the pin is load-bearing.** `dataspace-protocol-http:2025-1`
appears once in the codebase (`libs/ds-edc/src/ds_edc/schemas.py`) and the DSP endpoint path
carries the `/2025-1` suffix. A counterparty on a different DSP version is not
interoperable, and nothing negotiates the version down.

| # | Rule | Status |
|---|---|---|
| X-1 | Control-plane exchanges between participants use DSP `2025-1`. No other control protocol is accepted | **Enforced** — no other client exists |
| X-2 | A participant advertising a DSP endpoint without the `/2025-1` suffix is not reachable | **Enforced, and now checked.** `libs/ds-edc/tests/test_protocol_pin.py` derives the segment from the pin and fails on any configured DSP address in the tree that omits it, or that names a different version. The three files of defect P2-2 no longer omit it; the check is what stops a fourth appearing |
| X-3 | The data plane is HTTP pull. Push, streaming and file-drop transfers are not supported | **Enforced** — no other `DataAddress` type is emitted |

## 2. The control plane / data plane split

**Decision: the split is mandatory and structural** (`DSSC-DEX-18`, `-19`, `DSSC-CDP`).

```
consumer control plane ──DSP──▶ provider control plane
        │                              │
        │                              ├─ policy evaluation (edc-extensions → ds-connector /internal/*)
        │                              └─ EDR issued on agreement
        ▼
consumer data plane ──HTTP + EDR bearer──▶ provider data plane (participant-operated dataset API)
                                                    │
                                                    └─ PEP: POST /internal/dataplane/authorize
```

| # | Rule | Status |
|---|---|---|
| X-4 | No data moves before the control plane has completed identification, authentication and authorisation (`DSSC-DEX-36`) | **Enforced** on both paths since defect **P0-1** closed. The plain path — no `Edc-Contract-Agreement-Id` — now refuses any consent-gated dataset with a 403 naming what to send, so the gate is no longer opt-in for the party it constrains. Datasets with no data subject behind them still flow, which is what that path is for. `services/dataset-api-mock/tests/test_query_routing.py` |
| X-5 | The data plane re-checks the decision on every request rather than trusting the EDR alone | **Enforced** — `POST /internal/dataplane/authorize` is called per query |
| X-6 | The data plane must fail closed when the control plane is unreachable | **Enforced** — the 500s on the other paths are gone. An unreachable or refusing Keycloak, an unreachable connector on the EDR key fetch, an unreadable decision and an unrecordable query audit each produce a 502 and serve no rows; the audit failure policy does not depend on how it failed. `services/dataset-api-mock/tests/test_fail_closed.py`. **Note the scope:** that is the *mock*, and it is a unit test. The real data plane is the celine `dataset-api`, out of this repo, and this rule binds it identically — so there is **no live assertion** of this rule against a deployed PEP (`E2E-16`). `ds-e2e --flow fail-closed` deliberately stops at the negotiation gate (X-6b) rather than adding a per-query leg that would only exercise the mock |
| X-6b | **The negotiation gate must fail closed when the policy decision point is unreachable** | **Enforced, and asserted live** — with `ds-connector` stopped, a negotiation for a membership-gated dataset is TERMINATED on the unfulfilled constraint, and service resumes when it returns. `ds-e2e --flow fail-closed` (`task e2e:fail-closed`) proves it against a control plane that is actually stopped rather than a mocked failure, and brackets the outage so a refusal from a stale fixture cannot pass for one. **Bounded by `ds.access.scope.cache.ttl.seconds`** (default 60): a decision taken while the connector was reachable is reused for that long after it stops being, and recovery is bounded by the same window. That is the platform's blind interval, in both directions, and it is a deployment choice rather than a defect |
| X-6c | **The per-query gate must fail closed when the policy decision point is unreachable** | **Enforced, and asserted live since 2026-08-10.** The other half of `X-6`, and it was asserted by nothing: `X-6b` covers the *negotiation* gate, and a query is decided separately — the data plane asks `/internal/dataplane/authorize` per query. With `ds-connector` stopped, **both** data planes answer `502 ds-connector unreachable` for a live EDR-gated transfer on a consent-gated dataset. Asserted on the real celine `dataset-api` *and* on the mock (`T-1`), because testing one implementation is evidence about that implementation — which is why this waited. **Two gates, two clocks:** the negotiation gate reuses a decision for `ds.access.scope.cache.ttl.seconds` (60s) and the per-query gate caches nothing, so the flow asserts this *before* waiting the cache out. `ds-e2e --flow fail-closed`, step *per-query gate fails closed*; the refusal must name the connector, since a 403 is also what an unrelated denial produces and a transfer the policy monitor terminated would look the same |
| X-7 | The data-plane endpoint handed to a consumer is the participant's own, not the provider's EDC | **Declared**, and now asserted — this is why `ds.edr.endpoint.public.baseurl` is rewritten. The dev/Helm disagreement (defect P1-7) is resolved: every dev participant names the dataset API, Helm leaves it unset so the asset's own `base_url` reaches the consumer verbatim, and `RuntimeContractTest` fails the build if the value names anything but a consumer-reachable data plane |

## 3. Interaction patterns

`DSSC-DEX-06`, `-07`, `-08`, `-09` require these to be decided explicitly.

| Question | Decision |
|---|---|
| Push or pull? | **Pull.** The consumer retrieves; the provider never initiates |
| Finite or continuous? | **Finite.** One agreement, one transfer process, a bounded result set. Continuous subscription is out of scope |
| Transmission method | **HTTP** with JSON payloads. No MQTT, AVRO, Thrift or Protocol Buffers |
| Payload specification | A dataset-scoped query — `POST /query` with `{sql, limit, offset, skip_count}` — returning a flat row list. The schema of the rows is the dataset's, declared in the catalogue |
| Synchronous or asynchronous? | Negotiation and transfer are **asynchronous** (EDC state machines, polled); the data query itself is **synchronous** |
| Pagination | `limit` / `offset`, provider-capped |

| # | Rule | Status |
|---|---|---|
| X-8 | A query result is bounded. A provider may cap `limit` and must not be obliged to return an unbounded set | **Declared** — enforced by the data plane, which is the celine `dataset-api` and lives outside this repository. Nothing here can evidence it: `services/dataset-api-mock` is a stand-in and deliberately not evidence (`docs/development/conformance.md`), so borrowing its tests would convert an honest gap into a false green. A deployment's own data plane owes this check |
| X-9 | The query surface is dataset-scoped: a query naming a dataset the agreement does not cover is refused | **Enforced, untested** — and the dataset is currently selected by plain substring match against the SQL, so a comment or alias containing a dataset key selects it (defect P3-5 cluster) |

## 4. Quality of service

`DSSC-DEX-37` requires the protocol to maintain a consistent quality of service, for
example by defining what happens when a connection is lost.

| Situation | Behaviour |
|---|---|
| Negotiation stalls | Polled to a timeout; the consumer sees a terminal result, never an indefinite wait |
| Negotiation parked on a consent question | State `pending`, cleared by a resume call when the subject decides. Not a failure |
| Transfer interrupted | The agreement survives; the consumer re-requests. Transfers are idempotent from the provider's side because the query is |
| Consent revoked mid-transfer | The transfer is **terminated** through EDC's own state machine, not by a side-channel call |
| Provider unreachable | The consumer's poll times out. No partial result is reported as complete |

| # | Rule | Status |
|---|---|---|
| X-10 | A timeout is reported as a timeout, never as a terminal protocol state | **Enforced.** Both polls raise `EdcPollTimeout`, which is a `TimeoutError` and carries the last state actually observed; the connector answers **504**, not 502. The deadline is monotonic, so a slow control plane no longer extends the wait past what the caller asked for. `libs/ds-edc/tests/test_polling.py` |
| X-11 | A failed termination is reported as failed | **Enforced.** `404`, `405` and `409` all raise. The one tolerated case is a `409` on an entity that reads back as `TERMINATED` — a termination *observed* rather than assumed, which keeps the TTL sweep idempotent without covering the case that mattered: a `409` on a `FINALIZED` negotiation, where the refusal could not undo the agreement and the subject was told it had. `libs/ds-edc/tests/test_termination.py` |

## 5. The specification inventory

`DSSC-DEX-33` makes the governance authority responsible for a precise inventory of the
technical specifications in use, and `DSSC-DEX-34` requires it to be available to
participants through the vocabulary or catalogue services.

**Decision: the inventory is this table, and it is published in the docs site.**

| Specification | Version | Where it binds |
|---|---|---|
| Dataspace Protocol | `2025-1` | EDC protocol endpoint, `libs/ds-edc` |
| DCAT-AP | as emitted by the governance mapper | catalogue responses |
| ODRL | 2.2 core plus this data space's profile | offers, policy definitions |
| Decentralized Claims Protocol | EDC 0.16.0 implementation | `/sts/*`, `/credentials/*` |
| W3C Verifiable Credentials | 1.1, JWT serialisation | credential issuance |
| StatusList2021 | — | `/status/{list_id}` |
| W3C PROV-O | — | provenance events and lineage |
| DPV | 2.3 | purpose alignment, legal-basis IRIs |
| OpenID Connect | Keycloak realm | human and service authentication |

| # | Rule | Status |
|---|---|---|
| X-12 | The inventory above is authoritative and is updated in the same commit as any version change | **Declared** |
| X-13 | The protocol publishes a machine-readable description of its capabilities and endpoints (`DSSC-DEX-38`) | **Partly enforced.** The *protocol's* capability description is served: the DSP version endpoint (`DspVersionApiExtension`, on the protocol context) answers what protocol versions this connector speaks, which is the description `DSSC-DEX-38` asks a participant to publish. The ds services each serve a FastAPI OpenAPI document. What is absent is an OpenAPI document for EDC's own Management API — and the reason recorded here was wrong: `connector.jar` packages **no** `OpenApiResource` and no OpenAPI document of any kind, so there is nothing "registered on no context". Adding one means packaging an EDC module that is not currently in the BOMs, which is a capability decision rather than a defect fix — and the Management API is a private surface no counterparty reads |

## 6. Governance of the protocol

`DSSC-DEX-60`, `-61` require a governance process keeping the protocol up to date, recorded
in the rulebook.

**Decision.**

1. A protocol version change is a **breaking change** and requires a major release of this
   platform.
2. The version pin lives in exactly one place (`libs/ds-edc/src/ds_edc/schemas.py`); changing
   it anywhere else is a defect. `test_protocol_pin.py` asserts that the string occurs in no
   other file, and that every DSP address in the tree carries the version derived from it —
   so a bump is a one-line edit plus whatever that test then names.
3. Before a version change ships, `task e2e:all` must pass against a two-participant stack
   on the new version — the DSP exchange is the one thing no unit test can substitute for.
4. Participants get notice equal to one release cycle. There is no in-band version
   negotiation, so an unannounced change disconnects the data space.

| # | Rule | Status |
|---|---|---|
| X-14 | The DSP version is changed only by the governance authority, never per participant | **Declared** |
| X-15 | A version change is announced before it ships | **Declared** — no mechanism; the platform has no participant notification channel for governance events |

## 7. Federation with other data spaces

`DSSC-DEX-50`, `-51`, `-52`, `-64` and `DSSC-XCT-30`, `-31`, `-41`, `-43`.

**Decision: not in scope for this platform version.** The federated catalogue federates
*participants within one data space*, not data spaces with each other. A participant joining
a second data space runs a second participant agent; nothing here supports one agent
spanning two.

Recorded in [Scope and deviations](scope-and-deviations.md) §2.

## Blueprint rows

**Closed by this page:** `DSSC-DEX-01`, `-06`, `-07`, `-08`, `-09`, `-18`, `-19`, `-20`,
`-22`, `-25`, `-26`, `-31`, `-32`, `-33`, `-34`, `-36`, `-37`, `-39`, `-55`, `-56`, `-57`,
`-58`, `-60`, `-61`; `DSSC-CDP-*` (framing, no mandatory rows); `DSSC-SVD-34`, `-41`;
`CEEDS-STD-19`, `CEEDS-INT-23`, `-25`, `-26`.

**Open:** `DSSC-DEX-38` — partly enforced, and no longer a defect: see `X-13` for what is
served and why the residual is a capability decision. `DSSC-DEX-50`, `-51`, `-52`, `-64`,
`-65` (federation — out of scope).

**`DSSC-DEX-09` closed** — `X-10` and `X-11` are both enforced, defect P3-4 with them.

**`DSSC-DEX-02`** — a data provider describing the technical means of access — is answered
in [Catalogue and metadata](catalogue-and-metadata.md) §3.
