# DSSC ↔ CEEDS comparison

This page compares the two blueprints as rendered in [`dssc/`](dssc/index.md) and
[`ceeds/`](ceeds/index.md). It is derived from those pages, not from the sources again.

It makes **no claim about any implementation**, including this codebase. Assessing an
implementation against these requirements is separate work.

## Read this first: the version problem

**CEEDS v3.0 never cites DSSC v3.0.** Across the CEEDS chapters, every attribution points
backwards:

| CEEDS material | Attributed to |
|---|---|
| The adopted data-space definition (ch. 2) | DSSC Blueprint **v1.0** |
| The nine technical building blocks, Figure 13 (ch. 7) | DSSC Blueprint **v1.0** |
| The control-plane / data-plane approach (ch. 4) | DSSC Blueprint **v1.0** |
| The §4.1 component list (ch. 4) | DSSC Blueprint **v1.0**, jointly with IDS-RAM 4 |
| The governance baseline (ch. 6) | DSSC Blueprint **v2.0**, accessed Mar. 2025 |

CEEDS is dated September 2025; DSSC v2.0 was released in March 2025 and v3.0 is the
concluding version. So this page compares **DSSC v3.0 against a CEEDS written against
v1.0 and v2.0**.

The consequence is load-bearing and applies to every row below: **an apparent divergence
may be version drift rather than a deliberate energy-domain choice, and the source never
says which.** Nothing here is presented as an intentional CEEDS decision unless CEEDS
itself says so.

A second qualification: **CEEDS frames its specialisation of the DSSC as an intention,
not an accomplished fact.** Its words are "the objective in the future is that the CEEDS
architecture is a specialization of the mandatory part" of the DSSC. It also never states
which parts of the DSSC constitute "the mandatory part", and never defines *CEEDS
Reference Architecture*, *CEEDS Reference Architecture Patterns* or *CEEDS Blueprint
Patterns*, which appear only in a figure and its caption.

## 1. Structural comparison

**CEEDS reproduces the DSSC's building-block structure.** Not approximately — it
reproduces the three-by-three grid, group by group and position by position. This is the
clearest structural fact in the comparison, and it is visible in CEEDS's own Figure 13:

| CEEDS group (Figure 13) | CEEDS building blocks (Figure 13) | DSSC v3.0 category |
|---|---|---|
| Data Interoperability | Data Models · Data Exchange · Provenance & traceability | **Data Interoperability** |
| Data Sovereignty & Trust | Access & usage policies and control · Identity Management · Trust | **Data Sovereignty and Trust** |
| Data Value Creation | Data, Services and Offerings descriptions · Publication & Discovery · Marketplaces | **Data Value Creation Enablers** |

Three observations qualify that:

- **CEEDS never names its building blocks in prose.** They exist only as labels inside
  Figure 13. A reader of the text alone would not learn what the nine are.
- **CEEDS's chapter 4 and chapter 7 do not agree with each other.** Chapter 4's §4.1
  component list names *Trust Framework*, *Log*, *Vocabulary Hub*, *Contracting* and
  *Publication & Discovery* — a different decomposition, at a different level, from
  chapter 7's nine. Two of chapter 4's components (*Vocabulary Hub*, *Contracting*) have no
  counterpart among the nine, and *Log* is a component whose building block is named as
  *Provenance & Traceability*. The blueprint does not reconcile the two views.
- **Figure 13 shows three elements outside the grid** — *Data Space Protocols*,
  *Federated Services* and *Data Space Registry* — whose relation to the nine is never
  explained.

DSSC's structure has content CEEDS has no counterpart for at all: the **two framing
sections** ([Foundational Standards](dssc/foundational-standards.md), [Control and Data
Plane](dssc/control-and-data-plane.md)), the **eleven Service Definitions**, the
**business, governance and legal building blocks**, and the **co-creation method**. CEEDS
addresses governance in its own chapter 6 but has nothing corresponding to DSSC's
service-definition or co-creation layers.

### The building-block name mapping

CEEDS asserts no mapping between its labels and the DSSC's. **The pairing below is ours,
inferred from grid position and subject matter.** It is offered so the coverage matrix can
be read, not as a claim about the source.

| DSSC v3.0 building block | CEEDS label (Fig. 13) | Delta |
|---|---|---|
| Data Models | Data Models | — |
| Data Exchange | Data Exchange | — |
| Provenance, Traceability & Observability | Provenance & traceability | **drops Observability** |
| Identity & Attestation Management | Identity Management | **drops Attestation** |
| Trust Framework | Trust | narrower term |
| Access & Usage Policies Enforcement | Access & usage policies and control | enforcement → **control** |
| Data, Services, and Offerings Descriptions | Data, Services and Offerings descriptions | punctuation only |
| Publication and Discovery | Publication & Discovery | — |
| Value creation services | **Marketplaces** | **largest delta** — a marketplace is one kind of value creation service, not the category |

The three substantive deltas — Observability, Attestation, and Value creation services →
Marketplaces — are each a **narrowing**. Whether CEEDS narrowed deliberately or inherited
a v1.0-era vocabulary cannot be determined from the source.

## 2. Coverage matrix

One row per DSSC v3.0 building block. "CEEDS treatment" describes what the CEEDS pages
actually contain; the relationship is judged against that content.

| DSSC building block | CEEDS treatment | Relationship | Note |
|---|---|---|---|
| **Data Models** | Extensive. Names CIM, IEC 61970, COSEM, SAREF and associated ontologies; requires ontology-based approaches "in order to avoid silos"; assigns a Vocabulary Hub component | **CEEDS extends** | The one area where CEEDS is materially more specific than DSSC, because it supplies the domain vocabulary DSSC deliberately leaves open |
| **Data Exchange** | Adopts the dataspace protocol as "a prerequisite for joining any data space"; REST / Pub-Sub APIs for bilateral platform exchange | **aligned** | Both mandate a protocol; neither pins a version. CEEDS adds the platform-to-platform exchange pattern |
| **Provenance, Traceability & Observability** | A *Log* component, building block named "Provenance & Traceability", associated with a Clearing House | **CEEDS defers to DSSC**, and narrows | **Observability is absent from CEEDS entirely** — not renamed, not deferred, simply not present |
| **Identity & Attestation Management** | Identity Management component with Identity Register / Identity Manager / Identity Provider; DID, VC, SSI, eIDAS, wallets named in ch. 6 | **aligned**, narrower | Attestation is not treated as a named concern. Ch. 6 also describes an "API key" onboarding conclusion alongside DID/VC without explaining the relationship |
| **Trust Framework** | A Trust Framework component containing Identity Management and Access & Usage groups | **CEEDS defers to DSSC** | CEEDS gives it a structural position but no compliance-criteria or trust-service content of its own |
| **Access & Usage Policies Enforcement** | Access & Usage, Policies and Control group with Usage / Contract / Access Policies | **CEEDS defers to DSSC** | CEEDS supplies no policy language. DSSC's ODRL treatment has no CEEDS counterpart. CEEDS's ch. 4 text says "two types of policies" while its figure shows three |
| **Data, Services, and Offerings Descriptions** | DCAT recommended for describing datasets and data services; FAIR principles "as much as possible" | **aligned**, thinner | DSSC's DCAT-AP / application-profile treatment is far more developed |
| **Publication and Discovery** | A federated catalogue spanning the architecture; data indexing and data discovery as named exchanges; IDSA Metadata Broker named as an example | **aligned** | CEEDS adds the federated indexing/discovery flow; DSSC adds the protocol-level catalogue behaviour |
| **Value creation services** | Recast as **Marketplaces**; marketplace functionality, monetization, and a compensation/clearing arrangement | **CEEDS extends in one direction, drops the rest** | CEEDS supplies market and compensation content DSSC lacks, but has no counterpart to DSSC's service taxonomy, information model or services-management framework |

DSSC content with **no CEEDS counterpart**: the two framing sections, the eleven service
definitions, cross-cutting personal-data guidance, the business/legal building blocks
(contractual clauses, regulatory-compliance triggers), and the co-creation method.

## 3. What CEEDS adds

Everything in this section is domain content the DSSC Blueprint does not contain. Each
item is anchored to the CEEDS requirement IDs that carry it.

| Addition | CEEDS requirement IDs |
|---|---|
| **Energy standards and ontologies** — CIM / IEC 61970, IEC 62325 ESMP, IEC 62746, IEC 61850-7, COSEM, SAREF, SAREF4ENER, OCPP, OData, CGMES Conformity Assessment Scheme | `CEEDS-STD-05`, `-11`, `-12`, `-21`, `-23`; `CEEDS-INT-27`, `-34`, `-36` |
| **HEMRM** — the Harmonised Electricity Market Role Model, through which CEEDS defines the participation of single users | `CEEDS-STD-04`; `CEEDS-CON-31` |
| **SGAM**, and the proposed **6th "framework" layer** covering political, regulatory and societal interoperability, which the five existing layers cannot | `CEEDS-STD-07`, `-25`, `-26`, `-28`; `CEEDS-INT-42`, `-43`, `-49` |
| **DERA** (Data Exchange Reference Architecture, Bridge Data Management WG) | `CEEDS-STD-06`; `CEEDS-ARC-02` |
| **Marketplace and monetization** functionality on the federated side | `CEEDS-INT-11`, `-40`; `CEEDS-ARC-08` |
| **Clearing House**, attached to the Log / Provenance & Traceability component | `CEEDS-ARC` (Figure 12 decomposition) |
| **Five energy business use cases** — collective self-consumption for energy communities; residential home energy management with DER flexibility aggregation; TSO–DSO coordination for flexibility; electromobility roaming and load forecasting; renewables O&M optimization | `CEEDS-BUC-01`–`100` |
| **Network codes** as a requirements source | `CEEDS-BUC-88`–`100` |
| **Member-State data-management models** — decentralized, centralized, hybrid | `CEEDS-ARC` (§4 models) |
| **Regulated / unregulated platform distinction** — EMS, ADMS, meter data hubs, flexibility registers versus DERMS, VPP, charge-point management | `CEEDS-ARC-01`ff |

The **6th SGAM layer** is the most substantive original contribution: it is a considered
argument that interoperability frameworks cannot stop at the technical and organisational
layers, and it has no analogue anywhere in the DSSC Blueprint.

**Real-time constraints** are *not* a CEEDS addition in the sense of a stated requirement.
Latency-sensitive scenarios appear inside the business use cases, but the blueprint states
no real-time obligation on any building block.

## 4. Where DSSC is more prescriptive

This is the larger direction of difference, and it is a difference of *kind*, not only of
degree. **DSSC specifies; CEEDS surveys.**

The evidence is in the force distributions of the rendered pages:

| | CEEDS | DSSC |
|---|---|---|
| Ch. 5 (EDSCP implementations) | 55 standards named, **none mandated**; 90 of 135 rows `informative` | — |
| Ch. 6 (governance) | **one `must`** across 40 rows | — |
| Business & governance material | — | `DSSC-BIZ-01`–`371`, with article-level citations throughout |
| Access & usage policy | no policy language at all | `DSSC-AUP-01`–`91`, incl. the full ODRL treatment |
| Service definitions | no counterpart | `DSSC-SVD-01`–`92` |

Areas where DSSC is materially more prescriptive, with the anchoring IDs:

- **Policy expression and enforcement.** ODRL, and the PAP / PIP / PDP / PEP chain —
  `DSSC-AUP-38`–`91`. CEEDS names policy types but supplies no language, no model and no
  enforcement architecture.
- **Catalogue behaviour at protocol level.** Publication, update, removal, and the denial
  paths when a provider is not authorised — `DSSC-PUB-14`–`28`. CEEDS has nothing at this
  granularity.
- **Legal and contractual detail.** Article-level citations to the Data Act, GDPR, DGA,
  DMA, NIS-2, EHDS, ePrivacy and the AI Act, plus a 55-row contractual-clause table —
  `DSSC-BIZ-*`. CEEDS names instruments but cites articles only for eIDAS.
- **Deployable-component definitions.** The eleven service definitions —
  `DSSC-SVD-01`–`92`. CEEDS's component lists are architectural sketches by comparison.
- **Personal data and natural persons.** `DSSC-XCT-01`–`29`, an entire cross-cutting
  treatment CEEDS does not attempt.
- **Value creation as a discipline.** Taxonomy, information model and services-management
  framework — `DSSC-VCS-16`–`71`. CEEDS reduces this to marketplace functionality.

**The qualification that keeps this honest:** DSSC's prescriptiveness is itself limited in
a specific way. Several building blocks state that capabilities are *required* while also
stating that no specifications are mandatory for them — `DSSC-DMO-21` and `DSSC-VCS-08`
say so in as many words. So DSSC is more prescriptive than CEEDS about *what* a data space
must be able to do, and often no more prescriptive about *how* to verify it.

## 5. Contradictions

Genuine conflicts between the two, as opposed to differences of depth, are few — mostly
because CEEDS rarely asserts anything strongly enough to conflict. Those that exist:

1. **Observability.** DSSC makes it one third of a building block and states the
   capability is *required* (`DSSC-PTO-01`–`03`). CEEDS omits it from the building-block
   name and treats it nowhere. This is not a deferral — CEEDS's own ch. 5 lists a Logging
   implementation per project, so the concern was in scope and the observability half of
   it was dropped.
2. **Value creation services versus Marketplaces.** DSSC states explicitly that value
   creation services are *not* a mandatory capability (`DSSC-VCS-01`) and then supplies a
   full taxonomy and information model. CEEDS makes marketplace functionality integral to
   its federated architecture (`CEEDS-ARC-08`, `CEEDS-INT-11`) while dropping the
   taxonomy. The two are pulling in opposite directions on the same building block.
3. **The Dataspace Protocol's force.** CEEDS calls it "a prerequisite for joining any data
   space" (`CEEDS-STD-19`, `CEEDS-INT-25`). DSSC says both `shall` (`DSSC-DEX-20`) and
   `recommended` (`DSSC-DEX-23`) in the same building block. CEEDS is *firmer* here than
   DSSC's own weaker statement — the only place in the comparison where that happens.

**Not contradictions, though they look like them:** the building-block name deltas in §1.
Those are attributable to CEEDS working from DSSC v1.0, and the source gives no basis for
calling them disagreements.

## 6. Requirement-level reconciliation

Pairs where a CEEDS requirement specialises a DSSC one — the DSSC statement is
domain-agnostic, the CEEDS statement supplies the energy-domain instance. **These pairings
are ours; neither source asserts them.**

The table below is a **cross-reference, not a requirements table** — the IDs in it are
pointers to rows defined on the DSSC and CEEDS pages, and nothing here defines a
requirement.

| Relation | DSSC anchor | CEEDS rows | What the pair says |
|:--|:--|:--|:--|
| specialised by | `DSSC-DMO-27` | `CEEDS-INT-34` | DSSC: participants must semantically define offerings using a standardised data model agreed within the data space. CEEDS: that model is the CIM data model and associated ontologies |
| specialised by | `DSSC-DMO-27` | `CEEDS-INT-27` | Same DSSC anchor; CEEDS names SAREF for behind-the-meter equipment |
| specialised by | `DSSC-DMO-08` | `CEEDS-STD-11`, `CEEDS-STD-12` | DSSC: provide standardized discovery of data models across data spaces. CEEDS: the vocabulary module is expected to rely on IEC (CIM, 61850, COSEM) and ETSI (SAREF) standards |
| specialised by | `DSSC-DMO-01` | `CEEDS-STD-23`, `CEEDS-INT-36` | DSSC: data providers must describe structures, formats and vocabularies. CEEDS: ontology-based approaches are a requirement in order to avoid silos |
| specialised by | `DSSC-DEX-20` | `CEEDS-STD-19`, `CEEDS-INT-25` | DSSC: exchanges between control planes shall use the Dataspace protocol. CEEDS: it is a prerequisite for joining any data space |
| specialised by | `DSSC-DEX-23` | `CEEDS-INT-23`, `CEEDS-INT-26` | DSSC recommends DSP for discovery, negotiation and transfer initiation; CEEDS restates its scope as the minimum standard of communication between connectors |
| specialised by | `DSSC-PUB-08` | `CEEDS-STD-10` | DSSC: within DSP, DCAT-AP is the syntax for exchanging data-product metadata. CEEDS: DCAT is recommended for describing datasets and data services — **note CEEDS says DCAT, not DCAT-AP** |
| specialised by | `DSSC-PUB-01` | `CEEDS-STD-13` | DSSC: offerings must be exposed via a catalogue interface. CEEDS: the catalogue follows FAIR principles "as much as possible" |
| illustrated by | `DSSC-PUB-06` | `CEEDS-STD-14` | DSSC: the governance authority must decide the catalogue architecture. CEEDS names the IDSA Metadata Broker as one example — illustration, not obligation |
| specialised by | `DSSC-VCS-04` | `CEEDS-ARC-08`, `CEEDS-INT-11` | DSSC: the data space must determine what value creation services it includes. CEEDS: marketplace functionality and monetization on the federated side |
| no counterpart | *(none)* | `CEEDS-STD-04`, `CEEDS-CON-31` | HEMRM role definition — pure CEEDS addition |
| no counterpart | *(none)* | `CEEDS-STD-25`, `CEEDS-STD-26`, `CEEDS-INT-42`, `CEEDS-INT-43`, `CEEDS-INT-49` | SGAM governance layers and the proposed 6th layer |
| no counterpart | *(none)* | `CEEDS-BUC-01` … `CEEDS-BUC-100` | The five energy business use cases |

**What makes this set usable as one benchmark rather than two overlapping ones:** where a
pair exists, the DSSC row states the obligation and the CEEDS row states the energy-domain
instance, so a single check can test both. Where no pair exists, the requirement stands
alone. **Where a pairing is marked as ours, it must be re-derived rather than trusted if
the version gap in the preamble is ever closed** — a CEEDS release citing DSSC v3.0 could
map differently.

## Summary

CEEDS is a faithful but thin specialisation of an older DSSC. It reproduces the structure
exactly, contributes real and irreplaceable domain content — energy standards, HEMRM,
SGAM and its proposed 6th layer, five concrete use cases — and defers or omits most of the
mechanism. It narrows three building blocks, drops Observability entirely, and recasts
value creation as marketplaces.

For benchmarking, the practical consequence is that **the DSSC pages carry the
obligations and the CEEDS pages carry the domain bindings**, and the two are only loosely
joined — by our inference, across a version gap the sources never acknowledge.
