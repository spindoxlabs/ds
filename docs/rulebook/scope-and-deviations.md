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

### 3.1 Centralised trust anchor and credential store

**Blueprint:** `DSSC-IAM-06`, `-07`, `-29`, `DSSC-TRF-41` and `DSSC-SVD-30` describe
*participant-controlled* credential stores as part of each participant agent, used for
issuing, storing, managing and presenting credentials.

**This platform:** one centralised identity-registry acts as trust anchor, participant
registry, credential issuer, Secure Token Service and Credential Service for **every**
participant. DID private keys never leave it, and are encrypted at rest.

**Why:** it collapses what were three per-participant services into one operable component
and makes a small deployment tractable.

**This deviation used to claim more than it delivered.** It said "DCP is spoken correctly at
the protocol level — a counterparty cannot tell the difference", and that was false: the
credential service authorized the credential *holder* where DCP authorizes the **verifier**, so
no conformant counterparty could complete a presentation query at all. The protocol is now
spoken correctly and the full end-to-end suite runs on it, with no signature bypass anywhere.
What remains deviant is **custody**, not protocol: one registry still holds every participant's
private key.

**What a deployment must accept:** the trust anchor can impersonate any participant. It is a
single point of compromise, and losing `IDENTITY_REGISTRY_ENCRYPTION_KEY` makes every DID
key unrecoverable. Any deployment where participants are mutually distrustful should treat
this as disqualifying and externalise the credential stores.

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

**What a deployment must accept:** a strict `PUB-45` reader that asserts the *absence* of
inlined metadata will not see conformance here. Nothing in DCAT-3 forbids both properties
on one `dcat:Catalog`, and a consumer that only follows `dcat:record` is unaffected.

**How to close it properly, if wanted:** serve records by default and inline datasets only
under an explicit `?inline=true`, then migrate the portal and `ds-e2e` to the record path.
That is a breaking change to a published surface and wants its own decision.

## 4. Known non-conformances

Distinct from §2 and §3: rows this rulebook **states as rules** and the code does not keep.
They are defects, not decisions, and each is tracked in `.agents/defects.md`.

| Row | Rule stated in | Defect |
|---|---|---|
| `DSSC-IAM-05`, `DSSC-TRF-05` | [Participation](participation.md) P-9, P-10 | **P0-3** — credential revocation is unusable |
| `DSSC-AUP-06`, `-07` | [Policies](policies.md) A-11, A-12 | **P0-2**, **P1-1** — enforcement fails open and the consent constraint never reaches the connector |
| `DSSC-PUB-27`, `-31`, `-32` | [Catalogue and metadata](catalogue-and-metadata.md) C-19 | **P0-1** — the catalogue route has no guard |
| `DSSC-PTO-79` | [Provenance and logging](provenance-and-logging.md) L-12 | **P1-4** — lineage renders no edges, audit log is never written |
| `DSSC-DEX-38` | [Data exchange](data-exchange.md) X-13 | **P1-7** — the OpenAPI surface 404s |
| `DSSC-TRF-02`, `-03`, `-04` | [Participation](participation.md) §5 | no defect — never built. §5 states what would close it |

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
