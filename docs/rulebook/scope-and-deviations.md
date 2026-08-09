# Scope and deviations

What this platform deliberately does not do, and where it departs from the blueprints.

A gap that is declared is a scope decision. A gap that is undeclared is a defect. This page
exists so that every gap is one or the other, and a reader can tell which.

## 1. Value creation services — out of scope

`DSSC-VCS-04`–`-07` require the data space to state what value creation services it
includes, how they relate to its business model, how they are governed, and whether they
are available to all participants.

**Decision: this platform includes no value creation services.**

| Question (`DSSC-VCS`) | Answer |
|---|---|
| What services are considered? | None. The platform provides exchange, sovereignty and trust capabilities; it provides no service that processes data to generate value |
| Relation to business model? | Not applicable |
| How governed, by whom, under what conditions? | Not applicable |
| Visible and available to which participants? | Not applicable |

**This is a legitimate scope decision, not a gap.** `DSSC-VCS-01` states in as many words
that value creation services are **not a mandatory capability**. The remaining 56 `must`
rows in that building block — the service taxonomy, information model, services registry,
API gateway, artifact repository, orchestration, SLIs, SLOs, SLAs, service-level monitoring
— are conditional on including such services, and none applies.

**What this costs.** CEEDS recasts this building block as **Marketplaces** and makes
marketplace functionality and monetization integral to its federated architecture
(`CEEDS-ARC-08`, `CEEDS-INT-11`), along with a Clearing House attached to the Log
component. A deployment needing any of that builds it above this platform. The two
blueprints pull in opposite directions here — DSSC says optional, CEEDS says integral — and
this platform follows DSSC.

**If that changes**, the entry point is a service registry alongside the dataset catalogue,
and `DSSC-VCS-45` (connect the services registry to the data space catalogue) is the row to
design against first.

## 2. Other out-of-scope declarations

| Capability | Blueprint rows | Decision |
|---|---|---|
| **Cross-data-space federation** | `DSSC-DEX-50`–`-52`, `-64`, `-65`; `DSSC-XCT-30`, `-31`, `-41`, `-43` | Out of scope. The federated catalogue federates *participants within one data space*. A participant joining a second data space runs a second participant agent |
| **Anonymisation capability** | `DSSC-XCT-27` | Out of scope. A deployment needing intermediated sharing of anonymised data must anonymise before ingest; this platform cannot prove effective anonymisation |
| **Push and streaming transfers** | `DSSC-DEX-06`, `-07` (as options) | Out of scope. HTTP pull, finite datasets, one agreement per transfer |
| **A marketplace or clearing house** | `CEEDS-ARC-08`, `CEEDS-INT-11` | Out of scope — follows from §1 |
| **Payload semantic models** | `DSSC-DMO-27`; `CEEDS-STD-11`, `-12`, `-23`; `CEEDS-INT-27`, `-34`, `-36` | Deferred to the deployment, not to nobody. See [Data models](data-models.md) §2. **This is the largest CEEDS gap** |
| **HEMRM role model** | `CEEDS-STD-04`, `CEEDS-CON-31` | Not adopted. The platform's role model is a platform role model; a deployment needing HEMRM must map onto it |
| **SGAM, and the proposed 6th layer** | `CEEDS-STD-07`, `-25`, `-26`, `-28`; `CEEDS-INT-42`, `-43`, `-49` | Not referenced. These are architectural framing rather than implementable obligations |
| **Observability** | `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` | **Not a scope decision — an unfilled gap.** Recorded in [Provenance and logging](provenance-and-logging.md) §5 with a minimum-viable close. Listed here so it is not mistaken for a declared exclusion |

## 3. Deviations from the blueprints

Cases where this platform does something the blueprint describes differently, deliberately.

### 3.1 Credential stores — **closed for participants**

**Blueprint:** `DSSC-IAM-06`, `-07`, `-29`, `DSSC-TRF-41` and `DSSC-SVD-30` describe
*participant-controlled* credential stores as part of each participant agent, used for
issuing, storing, managing and presenting credentials.

**This platform, now:** one trust anchor per dataspace (issuer, participant registry,
StatusList) and **one identity-registry instance per participant**, holding that participant's
own key. An organisation generates its own keypair, publishes its own DID document, and proves
control of it at enrolment; the anchor records the **public** half. Its STS and its credential
service are its own.

`DSSC-IAM-06`, `-07`, `-29` and `TRF-41` are satisfied. This section is kept rather than deleted
because two narrower deviations remain, and because the history is the point — see below.

**What this deviation used to be, and why it is worth remembering.** It claimed twice as much as
it delivered, twice:

1. It said *"DCP is spoken correctly at the protocol level — a counterparty cannot tell the
   difference"*. False: the credential service authorized the credential *holder* where DCP
   authorizes the **verifier**, so no conformant counterparty could complete a presentation
   query at all. Five defects sat in series behind that one, each hidden by the one in front.
2. Corrected to *"what remains deviant is custody, not protocol: one registry still holds every
   participant's private key"* — true, and the thing a deployment had to accept was that **the
   trust anchor can impersonate any participant**.

Both are now closed, and closure is **checked rather than asserted**: every instance audits its
own key custody at startup and refuses to start in production holding a private key for a DID it
does not publish (`P-7`). Measured on the dev stack: the anchor holds one private key, its own,
and serves zero presentations and zero STS tokens.

**What a deployment must still accept:** each instance's encryption key is a single point of
unrecoverable loss **for that instance**. The blast radius is one participant, not the dataspace.

### 3.1.1 Credential issuance — **closed**

**Blueprint:** `DSSC-IAM-25`, `-30`, `-33` — a common credential-exchange protocol.

**This platform:** enrolment and delivery are the Credential Issuance Protocol's own two legs —
a holder-initiated `CredentialRequestMessage` authenticated by a self-issued token and validated
by resolving the requester's DID, then an asynchronous `CredentialMessage` pushed to the holder's
Credential Service — and the message bodies are now checked against **the DCP repository's own
JSON schemas** rather than against a reading of its prose (`tests/test_cip_conformance.py`). The
anchor's DID document publishes its Issuer Service, so an organisation holding nothing but the
anchor's DID can find where to enrol.

This deviation is kept rather than deleted because what closing it turned up is worth stating.
Three things were wrong, and **each of them read correctly**:

- `issuerPid` and `holderPid` carried **DIDs**. The schema defines them as the *request ids* on
  each side. Nothing failed — the fields were strings, the messages validated, and correlation
  simply never worked: a holder with two requests in flight could not tell which one a delivery
  answered.
- `credentialsSupported` omitted `credentialSchema`, which every `CredentialObject` in that array
  must carry.
- The `IssuerService` entry pointed at a URL that **neither the dev proxy nor the production
  Ingress routed**. The document advertised the right thing and the endpoint behind it answered
  404, in both environments — the shape of failure that looks most like success.

**What a deployment must accept:** nothing at the issuance step. Where the schemas leave a
property optional this platform sends it (the `credentialsSupported` rule above), which is
additive for a strict counterparty.

### 3.1.2 A natural person's credentials are held by the organisation that onboarded them

**Blueprint:** `DSSC-IAM-29` requires a credential store per **participant agent**;
`DSSC-IAM-16` and eIDAS 2 point at wallets for natural persons.

**This platform:** a natural person is a **data rights holder, not a participant** — they run no
agent, present nothing and sign nothing, and they hold **no key**. Their `DataSubjectCredential`
is signed by the trust anchor and verified against the anchor's key; the organisation that
onboarded them holds it on their behalf.

**Why:** this is the blueprint's own **four-corner model** — a participant agent service
provider operating credential stores for parties who do not run their own (`DSSC-SVD-25`, and
the *ParticipantConnect GmbH* example in the business building block). For CEEDS BUC#1 the
parties are households in an energy community; expecting each to run a credential store is not a
design.

Generating a key for them anyway would not have made it more decentralized — it would have
created custody nobody exercises, which is an impersonation surface with no upside. It was
there, it was read by nothing, and it is gone.

**What a deployment must accept:** identity assurance for a person is **whatever the onboarding
process established** (`DSSC-IAM-14`). ds does not perform KYC. The credential records *who
attested and by what method* rather than implying a level — see `P-5`. When wallets arrive the
person supplies their own public key and the hosted store becomes a fallback; nothing here has
to be undone.

### 3.2 Catalogue visibility is enforced at negotiation, not at discovery

**Blueprint:** `DSSC-PUB-03` requires visibility *and* access management, where offerings
may be visible or accessible to all participants or to a subset.

**This platform:** access restriction is expressed as ODRL membership constraints, which
gate **negotiation**. A restricted offering is visible in the catalogue to any data space
participant and refuses when negotiated.

**What this leaks:** the existence, title, description and terms of an offering — never its
data. For most deployments that is acceptable and arguably desirable. For one where the
existence of a dataset is itself sensitive, it is not, and the offering should not be
published.

### 3.3 No cross-participant provenance or consent API

**Blueprint:** `DSSC-PTO` describes shared or third-party-held provenance as an option
(`PTO-15`), and treats evidence availability as a technical property (`PTO-79`).

**This platform:** each participant's provenance store is local and readable by nobody else.
Evidence sharing between participants is a governance process, not an API. Likewise, there
is no cross-participant consent API: a consumer asks by negotiating, and the identity
recorded is the DCP-verified counterparty, because re-deriving it from a header proved it
more weakly.

**Why:** having no third-party observer is how `PTO-81` (trust between observer and all
parties) is satisfied. Both parties record independently and neither copy is authoritative.

### 3.4 The consent model exceeds the blueprint

Recorded as a deviation because it imposes rules on participants that no blueprint row
requires, and a participant must know about them:

- the consent key includes a **controller-role**, so one legal entity's two functions are
  distinct controllers
- contract-based processing is **disclosed without a control**; only `dpv:Consent` offers
  get one
- a **covered processor** is disclosed, never asked
- consent evidence records the **hash of the rendered text** the person actually saw
- an **opt-out overrides a wildcard**, symmetrically with a grant

All of it is in [Personal data](personal-data.md). None of it is in DSSC.

### 3.5 CEEDS: DCAT-AP, not DCAT

`CEEDS-STD-10` recommends DCAT; `DSSC-PUB-08` requires DCAT-AP within DSP. This platform
follows the stricter statement. Not a conflict, recorded for completeness.

### 3.6 `dcat:record` is emitted *alongside* the inlined datasets, not instead of them

**Blueprint:** `DSSC-PUB-45` — a catalogue request returns an instance of `dcat:Catalog`
which points to the identifiers of its catalogue records via `dcat:record` "**rather than**
containing all the metadata of its entries".

**This platform:** every catalogue response — the federated index and the compliance
evidence bundle — carries a `dcat:CatalogRecord` per entry **and** keeps `dcat:dataset`
inlined.

**Why:** the two properties answer different questions and only one of them was missing. A
record carries what the *catalogue* knows about an entry (`dct:modified` = when this
catalogue last saw it, `dct:source` = which catalogue it came from); a dataset carries what
the *publisher* says about the data. Withholding the second buys no conformance the first
does not already deliver, and it would break every consumer of the index — the portal's
catalogue pages and `ds-e2e` both read `dcat:dataset` — in exchange for one extra round
trip per entry.

**And DSP requires the inlining, which settles it** — checked 2026-08-09 against
`eclipse-edc/DataspaceProtocol`. `specifications/catalog/catalog.protocol.md` states *"A
Catalog **MUST** have zero to many Datasets"*, and a DSP catalogue response is exactly what a
counterparty fetches over the protocol. So for that surface `PUB-45`'s *"rather than"* cannot be
satisfied without breaking a **MUST** in the protocol this platform is built on. The spec says
nothing about `dcat:record` at all.

That reframes this row: it is not an unfinished item, it is **two normative sources
disagreeing**, and for a DSP catalogue response DSP wins. Emitting both is the only reading
that conforms to both as far as either can be conformed to.

**What a deployment must accept:** a strict `PUB-45` reader that asserts the *absence* of
inlined metadata will not see conformance here — and could not, against any DSP-conformant
connector.

**Decided 2026-08-09: not to be closed.** The earlier note here proposed serving records by
default behind an `?inline=true` flag; that would make the DSP surface non-conformant to reach
a blueprint row, which is the wrong trade. The one place `PUB-45`'s form *is* achievable is
ds's own federated index, which is not a DSP response — but the index exists to be read by the
portal and `ds-e2e`, so changing it buys conformance with nobody's reader in exchange for
breaking two of our own.

## 4. Known non-conformances

Distinct from §2 and §3: rows this rulebook **states as rules** and the code does not keep.
They are defects, not decisions.

**Re-verified against the code on 2026-08-08.** Five of the ten rows this table carried were
already closed — the code moved and this page did not, which for a compliance artifact is the
failure mode that matters most: it is the page an assessor reads, and it understated the
platform in every one of the five. They are listed at the bottom rather than deleted.

**A re-verification by hand is a re-verification that happens once.** Every row below that
cites rule ids is now checked against the status of those rules on every CI run: if all of
them read `Enforced`, the row is closed and the build says so
(`libs/ds-e2e/tests/test_rulebook_projection.py`, `C-13`). It caught this table's next drift
the day it was written — `DSSC-TRF-02`/`-03`/`-04` had been closed and was still listed. A row
citing only a *section* names nothing that check can look up, so those are pinned to a
declared list rather than left as a way to opt out.

| Row | Rule stated in | What is missing |
|---|---|---|
| `DSSC-AUP-06` | [Policies](policies.md) `A-9` | A policy's validity window is declared, reported by the `declared-not-enforced` check, and **not emitted** — because emitting a term nothing enforces is what this very row forbids. **Decided 2026-08-09: it stays declared.** Closing it means binding a date operand in `services/edc-extensions` first, and until something asks for date-bounded policies that is a Java change bought for a term no deployment uses. This is a stated incapacity, not a silent one |
| `DSSC-DSO-14`, `-15` | [Catalogue and metadata](catalogue-and-metadata.md) §4 | Metadata versioning is not implemented: a consumer cannot ask what an offering said when they negotiated. Blocked on a design decision — version the offering, or snapshot it into the agreement |
| `DSSC-PTO-03`, `-42`–`-46`, `-57`–`-63` | [Provenance and logging](provenance-and-logging.md) §5 | Observability. Listed in §2 so it is not mistaken for a declared exclusion, and here because it is a rule the code does not keep. Steps 1 and 2 are done — reachability is gated per deployment, all four service charts emit a `ServiceMonitor` under the same flag, and the metric set is a table in the rulebook. **No tracing**: `OpenTelemetry` spans correlated by `dsp_agreement_id` are not started, and three of the four SLIs need them |
| `DSSC-DEX-38` | [Data exchange](data-exchange.md) `X-13` | No OpenAPI document for EDC's Management API. **Decided 2026-08-09: none will be published.** It needs a module outside the BOMs, and the surface is private to the deployment — a document describing an admin API nobody outside the deployment may call is documentation of an attack surface, not of an interface. The APIs a counterparty uses are DSP and DCP, and both are specified elsewhere |

**Closed since this table was last accurate.** Listed so a reader who remembers them does not
go looking, and because four of the five were closed by work that never updated this page:

| Row | Was | Now |
|---|---|---|
| `DSSC-AUP-13` | no policy carries a version | `{prefix}:profileVersion` is emitted from `OdrlProfile.version`, as metadata beside `@context` rather than as a constraint |
| `DSSC-AUP-16` | the retention duty uses an `rdf:` prefix the emitted `@context` never declares | declared when an obligation uses it, on the same rule `dct` follows |
| `DSSC-AUP-38`–`-91` | the compliance matrix filters CURIEs while the mapper emits IRIs, so membership and consent are missing from every entry | **the matrix is gone.** It had no consumer — no route, no CLI output, no importer in any sibling checkout — and a report confidently wrong about enforcement is worse than none. See [Policies](policies.md) §6 |
| `DSSC-DSO-11` | metadata is not checked against DCAT-AP | the `dcat-ap` check runs in `task compliance:validate`, splitting DCAT-AP's own obligation levels: mandatory → error, recommended → warning |
| `DSSC-DEX-09` | `ds-edc` synthesises `state="TIMEOUT"` into the namespace of real EDC states, and reports a failed termination as success | `EdcPollTimeout` carries the last state observed and the connector answers **504**; every terminate path raises, the one tolerated `409` being on an entity that *reads back* as `TERMINATED` |
| `DSSC-TRF-02`, `-03`, `-04` | two of three built; suspension was a slower revocation — one shared body under two labels, with no transition out of either | suspension is a state a verifier can read (`/status/2`, `statusPurpose: suspension`) and `reinstate` lifts it on the credential the holder already has. [Participation](participation.md) `P-25`, `P-26` |
| `DSSC-DSO-12` | the rulebook was machine-readable and no metadata check consulted it — every check carried its own private copy of the rule it came from | findings **cite rule ids**, from one map (`compliance/rulebook.py`), with every id asserted to resolve in the projection. The gap was attribution rather than coverage: most metadata rules already had a named check. [Catalogue and metadata](catalogue-and-metadata.md) `C-13` |
| `DSSC-PTO-40`, `-41` | fifteen of sixteen event types had an emitter; the sixteenth, `UsageObligationFulfilled`, had a schema and a materialiser and no producer anywhere | **all fifteen have one, and the sixteenth was deleted** rather than implemented. A consumer's unverifiable self-report that it met an obligation is not provenance — and neither DSP (11 messages, none a post-agreement report in that direction) nor EDC's policy monitor models one. [Provenance and logging](provenance-and-logging.md) `L-1`, `L-1a`, `L-15` |
| `DSSC-AUP-45`, `-46` | the gate ran on one producer, skipped its participant checks in silence, and its two live-registry checks had never executed anywhere | both CI and `task compliance:validate:runtime` iterate every producer; a named-but-unreadable participants path or registry is a hard failure; the runtime task carries a credential, which it never did; and `controller_role` moved off the runtime path because comparing it to a participant's DSP roles was unsatisfiable. [Policies](policies.md) `A-4`, [Personal data](personal-data.md) `D-11a` |

Earlier closures, from before that: **P0-1** (unguarded catalogue route — C-19, X-4), **P0-2**
(enforcement failed open — A-11), **P1-1** (the consent constraint never reached the connector
— A-12, A-14), **P0-3** (credential revocation unusable — P-16), **P1-3**'s catalogue half
(P-12), **P1-4** (lineage and audit log — L-12) and **P1-7** (the EDR endpoint disagreement —
X-7).

## 5. Reviewing this page

Every entry here is a claim that a gap is intentional. That claim decays: a scope decision
taken when the platform served one use case may not survive the second. Review this page
whenever a new deployment is onboarded, and specifically re-ask:

1. Does this deployment need value creation services? (§1)
2. Does it need a payload semantic model, and is the profile mechanism able to carry one?
   ([Data models](data-models.md) §3)
3. Are its participants mutually distrustful enough that the centralised trust anchor is
   disqualifying? (§3.1)
4. Is the existence of any of its datasets sensitive? (§3.2)

**And re-verify §4 against the code, not against memory.** On 2026-08-08 five of its ten
rows were closed and the page still carried them, every one understating the platform. A
non-conformance table is a claim about *now*; it decays faster than the deviations above it,
because a deviation closes by decision and a defect closes by someone fixing it in another
unit and not thinking to come here. Until `DSSC-DSO-12` gives this rulebook a machine-readable
projection, that re-check is manual and belongs in this list.
