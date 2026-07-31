# Blueprint of the Common European Energy Data Space v3.0

> **Source** · Blueprint of the Common European Energy Data Space, version 3.0, September 2025
> **Publisher** · Interoperability Network for the Energy Transition (int:net), c/o Fraunhofer-Gesellschaft
> **DOI** · [`10.5281/zenodo.17116750`](https://doi.org/10.5281/zenodo.17116750) · **Licence** · CC BY 4.0

CEEDS is an energy-domain **specialisation** of the DSSC Blueprint. It adopts the
DSSC's data-space concept and building-block structure and adds what the energy sector
needs on top: its standards, its role models, its market and compensation arrangements,
and five concrete business use cases.

## Contents

| Page | Source chapters | Requirement IDs |
|---|---|---|
| **[Introduction and Data Spaces Concept](data-space-concept.md)** | 1, 2 | `CEEDS-CON-01`–`38` |
| **[Business Use Cases for Energy](business-use-cases.md)** | 3, incl. 3.6 Network codes | `CEEDS-BUC-01`–`100` |
| **[Proposed Architecture for CEEDS](architecture.md)** | 4, incl. 4.1 Federated Side | `CEEDS-ARC-01`–`77` |
| **[EDSCP Implementation Details](edscp-implementations.md)** | 5 | `CEEDS-IMP-01`–`135` |
| **[CEEDS Governance](governance.md)** | 6 | `CEEDS-GOV-01`–`40` |
| **[Interoperability Aspects](interoperability.md)** | 7 | `CEEDS-INT-01`–`66` |
| **[Energy standards, abbreviations and glossary](energy-standards.md)** | standards cited throughout, 12, 13 | `CEEDS-STD-01`–`30` |

Requirement IDs are a local index for benchmarking. The source does not number its
requirements.

Chapter 8 (Conclusions) is summarised on this page. Chapters 9–11 (references, list of
figures, list of tables) are apparatus and are not rendered as pages; individual
references are cited inline wherever a page depends on one.

**EDSCP** expands to **Energy Data Space Cluster Projects**. The blueprint's own §5.1
heading spells it "Energy Dataspace Cluster Projects"; both spellings are preserved where
they occur.

## What the blueprint concludes

The blueprint states its contribution as twofold. **First**, it defines complementary
reference use cases for energy, chosen against the sector's existing challenges and the
directions of the EU action plan *Digitalising the energy system* — spanning mobility,
energy communities, TSO–DSO interactions, residential energy optimisation, and renewables
O&M. **Second**, it proposes an architecture for the CEEDS to implement those use cases:
a federated data space integrating existing data platforms, consistent with reference
architectures already used in the energy domain, namely SGAM and Bridge DERA. It then
addresses interoperability challenges at technical, semantic and governance levels.

Looking forward, the blueprint says further improvements should build on the CEI Sphere
Hourglass© model and should draw on the work of the DSSC and O-CEI to create reusable
building blocks, with a pathway to standardisation through submission to the 2026
standardisation rolling plan and to ISO/IEC JTC 1/SC 41. It names the ongoing project
**INSIEME** (Digital Europe Programme call DIGITAL-2024-CLOUD-AI-06-ENERSPACE) as the
initiative deploying a CEEDS from these use cases, and **TwinEU** as applying data-space
principles to digital-twin exchange for the energy system.

## Reading these pages

**CEEDS is substantially less prescriptive than the DSSC Blueprint.** Its chapters
survey what five projects built rather than specifying what an implementation must do,
and the requirement rows reflect that: chapter 5 names 55 standards and mandates none of
them, chapter 6 contains a single `must` across 40 rows, and roughly two-thirds of all
CEEDS rows are `informative`. The genuinely mandatory statements in the whole document
are few — principally that a dataspace protocol is "a prerequisite for joining any data
space" and that data-ontology approaches "are a requirement in order to avoid silos". The
only named standard the blueprint actually recommends is DCAT.

**Almost nothing about the energy standards is normative.** `IEC 61970`, `IEC 62325
ESMP`, `IEC 62746`, `IEC 61850-7`, `OCPP` and `OData` all appear in a *single sentence*,
introduced by "such as", with no version, edition or profile. See
[Energy standards](energy-standards.md), which records the force of each identifier
individually and lists the identifiers CEEDS does **not** use.

**Figures carry content the prose does not.** Unlike the DSSC pages, these were rendered
with the source PDF available, so figures that the text layer drops entirely have been
recovered and reproduced as tables and ordered lists — including the architecture's
component decomposition (Figure 12), the building-block grid (Figure 13), the governance
building blocks (Figure 15), and every business-use-case sequence diagram (Figures 4–9).
In several places this is the *only* place the content exists: chapter 7 never names its
nine technical building blocks in prose, and chapter 3 carries no actor or data-flow
detail outside its figures.

## Its relationship to the DSSC Blueprint

CEEDS reproduces the DSSC's three-by-three building-block grid, and its
[Interoperability Aspects](interoperability.md) page renders that grid from the source's
own figure. But three qualifications must travel with any comparison:

- **CEEDS v3.0 never cites DSSC v3.0.** It attributes its data-space definition and its
  building-block grid to DSSC Blueprint **v1.0**, and its governance baseline to
  **v2.0** — in a document dated September 2025.
- **The specialisation is stated as an intention, not a fact.** The source's words are
  "the objective in the future is that the CEEDS architecture is a specialization of the
  mandatory part" of the DSSC.
- **The blueprint never says which parts of the DSSC constitute "the mandatory part"**,
  and never defines the terms *CEEDS Reference Architecture*, *CEEDS Reference
  Architecture Patterns* or *CEEDS Blueprint Patterns*, which appear only in a figure and
  its caption.

[`comparison.md`](../comparison.md) works through the relationship in detail and carries
these caveats into every claim it makes.

## Legal instruments named

The blueprint names the following EU instruments; each is treated on the page where CEEDS
invokes it. Note that only eIDAS carries full citations in the source (Regulation
910/2014 and the 2024 amendment 2024/1183); the rest are named by title or category
without article-level citation.

| Instrument | Treated in |
|---|---|
| Data Act | [Interoperability](interoperability.md) (Ch. VIII), [Governance](governance.md), [Energy standards](energy-standards.md) |
| Data Governance Act (DGA) | [Interoperability](interoperability.md), [Governance](governance.md), [EDSCP implementations](edscp-implementations.md) |
| GDPR | [Business use cases](business-use-cases.md), [EDSCP implementations](edscp-implementations.md), [Interoperability](interoperability.md), [Governance](governance.md) |
| eIDAS (Reg. 910/2014; amendment Reg. 2024/1183) | [Governance](governance.md), [EDSCP implementations](edscp-implementations.md) |
| Electricity Directive (EU) 2019/944 | [Architecture](architecture.md), [Interoperability](interoperability.md) |
| Implementing Regulation (EU) 2023/1162 | [Interoperability](interoperability.md) |
| NIS / NIS-2 | [Governance](governance.md) |

Energy network codes are discussed in [Business use cases](business-use-cases.md) §3.6.
**The blueprint names them without instrument numbers or articles** — "network code on
demand response", "new demand side flexibility code" and "recent flexibility code
deployment" all appear uncited, and the source never states whether they refer to the
same instrument.
