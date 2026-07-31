# DSSC Blueprint v3.0

> **Source** · DSSC Blueprint, version 3.0, Data Spaces Support Centre — <https://blueprint.dssc.eu/>

The DSSC Blueprint is a domain-agnostic reference for designing and operating a data
space. Version 3.0 is **the concluding version of the DSSC project**. These pages render
it in full: every published document is either represented here or listed below as a
deliberate exclusion with a reason.

## The blueprint in its broader context

The Data Spaces Support Centre situates the blueprint within the **European strategy for
data**, which aims to create a single market for data ensuring Europe's global
competitiveness and data sovereignty. Through the **Digital Europe Programme**, the
European Commission invests in Common European Data Spaces across strategic economic
sectors and domains; the blueprint targets emerging data spaces and supports development
across the phases of the data-space development cycle.

The blueprint is one asset in the DSSC's asset-based approach, ranging from introductory
material to in-depth treatment of standards. The DSSC began in October 2022 and released
v0.5 in September 2023, v1.0 in March 2024, v1.5 in September 2024 and v2.0 in March
2025; **v3.0 is the concluding version and its own material gives no publication month**.

The methodology behind the identification of the building blocks is published separately
as DSSC Deliverable D4.1, *Methodology for the identification of the Blueprint building
blocks*.

## Structure

The blueprint's technical pane is organised as **three categories of three building
blocks each**, plus **two framing sections** that are deliberately not building blocks.

| Category | Building blocks |
|---|---|
| **[Data Interoperability](data-interoperability/index.md)** | [Data Models](data-interoperability/data-models.md) · [Data Exchange](data-interoperability/data-exchange.md) · [Provenance, Traceability & Observability](data-interoperability/provenance-traceability-observability.md) |
| **[Data Sovereignty and Trust](data-sovereignty-and-trust/index.md)** | [Identity & Attestation Management](data-sovereignty-and-trust/identity-and-attestation-management.md) · [Trust Framework](data-sovereignty-and-trust/trust-framework.md) · [Access & Usage Policies Enforcement](data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) |
| **[Data Value Creation Enablers](data-value-creation-enablers/index.md)** | [Data, Services, and Offerings Descriptions](data-value-creation-enablers/data-services-and-offerings-descriptions.md) · [Publication and Discovery](data-value-creation-enablers/publication-and-discovery.md) · [Value creation services](data-value-creation-enablers/value-creation-services.md) |

### Framing sections — not building blocks

- **[Building on Top of Foundational Standards](foundational-standards.md)** — the
  standards layer the building blocks are built on.
- **[How a Data Plane and Control Plane Work Together](control-and-data-plane.md)** — the
  plane separation that the service definitions and Data Exchange both depend on.

Both sit in the technical pane alongside the nine building blocks and at the same level
as the three categories, but the blueprint presents them as framing rather than as
building blocks. Each page states this at its head.

### The rest of the blueprint

| Page | What it covers |
|---|---|
| **[Service Definitions](service-definitions.md)** | The eleven deployable-component definitions — the view an implementation is most directly benchmarked against. |
| **[Cross-cutting concerns](cross-cutting.md)** | Personal data and natural persons; cross-data-space interoperability. Both cut across the building blocks rather than belonging to one. |
| **[Business and Organisational Building Blocks](business.md)** | Business, governance and legal building blocks — use-case development, offerings, intermediaries and operators, organisational form, participation management, regulatory compliance, contractual framework. |
| **[Co-Creation Method](co-creation.md)** | The A / B.1–B.5 development process for building a data space. |
| **[Glossary](glossary.md)** | All 281 defined terms from the thematic and consolidated glossary documents, alphabetically, verbatim. |

## Requirement ID codes

Requirement IDs are a local index for benchmarking. The source does not number its
requirements.

| Code | Page | Code | Page |
|---|---|---|---|
| `DMO` | Data Models | `TRF` | Trust Framework |
| `DEX` | Data Exchange | `AUP` | Access & Usage Policies Enforcement |
| `PTO` | Provenance, Traceability & Observability | `DSO` | Data, Services, and Offerings Descriptions |
| `IAM` | Identity & Attestation Management | `PUB` | Publication and Discovery |
| `VCS` | Value creation services | `FND` | Building on Top of Foundational Standards |
| `CDP` | How a Data Plane and Control Plane Work Together | `SVD` | Service Definitions |
| `XCT` | Cross-cutting concerns | `BIZ` | Business and Organisational Building Blocks **and** Co-Creation Method |

`BIZ` runs as one continuous sequence across two pages: `DSSC-BIZ-01`–`269` on
*Business and Organisational Building Blocks*, `DSSC-BIZ-270`–`371` on *Co-Creation
Method*. The glossary carries **no** requirement IDs — definitions are not requirements.

## Source coverage

The published blueprint comprises **82 documents** across six panes. All 82 are accounted
for:

| Pane | Documents | Rendered in |
|---|---|---|
| `technical` | 33 | the 9 building-block pages + the 2 framing pages |
| `business` | 14 | [Business and Organisational Building Blocks](business.md) |
| `glossary` | 13 | [Glossary](glossary.md) |
| `service-definitions` | 11 | [Service Definitions](service-definitions.md) |
| `co-creation` | 7 | [Co-Creation Method](co-creation.md) |
| `intro` | 4 | 2 in [Cross-cutting concerns](cross-cutting.md); 2 on this page (see below) |

**Nothing is excluded.** The two `intro` documents not rendered as their own page are
folded in here: *Blueprint in the broader context* is the "broader context" section
above, and *Blueprint V3.0 Contributors* is the contributor note below. Every explainer
and best-practice sub-page nested beneath a building block is rendered within its
parent's page, under "Explainers and best practices".

## Known limitations of this rendering

- **Figures are not available.** The blueprint's figures are images, and the material
  these pages were built from carries text only. Roughly fifteen figures are referenced
  in prose but cannot be reproduced — including the control-plane interaction diagram,
  the Publication and Discovery swimlanes, the Value creation services information model
  and its DCAT property mapping, the Trust Framework's ArchiMate layer diagram, and the
  Regulatory Compliance flowcharts. Where a figure carries content the prose does not,
  the affected page says so under "Open questions". This limitation does not apply to the
  [CEEDS pages](../ceeds/index.md), whose source is a PDF.
- **Section-level cross-references are rendered as text, not links**, where upstream's own
  link targets are broken or point at pages marked `_archived` / `_old`. Those cases are
  recorded rather than silently retargeted.

## Blueprint-wide inconsistencies

These are properties of the source, recorded once here because they recur across pages:

- **"Facilitating Services" and "Federation Services" are used interchangeably**, including
  within single sentences and across the glossary's own thematic documents. The service
  definitions pane's URL slug is `federation` while its heading reads *Facilitating
  Services*, and the two glossary documents that define the term disagree with each other.
- **The blueprint's own "complete" term list is not complete.** *Alphabetical List of All
  Defined Terms in Blueprint v3.0* omits the entire EU-legal-definition table from
  *11 Foundation of the European Data Economy Concepts* — eleven terms including *Data*,
  *Data holder*, *Personal data*, *Data subject* and *Consent*. Our
  [Glossary](glossary.md) carries all of them.
- **Specification versions are mostly absent from prose**, appearing — when at all — only
  inside hyperlinks. See the note in [the section landing page](../index.md).
- **The Service Definitions pane's grouping is four-way**, not the two-way Participant
  Agent Services / Facilitating Services split it is sometimes described as. Eight of its
  eleven documents carry no breadcrumb, so group membership is inferred from two overview
  pages and the pane navigation rather than declared. [Service
  Definitions](service-definitions.md) states the evidence.

## Contributors

Blueprint v3.0 names the following **authors and contributors**: Alberto Abella (FIWARE),
Arjan Stoter (TNO), Bert Verdonck (LNDS), Claire Stolwijk (TNO), Daham Mustafa
(Fraunhofer), Daniel Alonso (BDVA), David Regeczi (TNO), Frank Berkers (TNO), Frank
Drijfhout (TNO), Gabriella Laatikainen (VTT), Geert Lamerichs (TNO), Giuditta del Buono
(Gaia-X), Heidi Korhonen (VTT), Kai Kuikkaniemi (MyData), Jelte Bootsma (TNO), Mario
Holesch (IDSA), Marta Musidlowska (KUL), Matteo Frigeri (KUL), Matthijs Punter (TNO),
Michiel Stornebrink (TNO), Mirjam Huis in 't Veld (TNO), Natalie Bertels (KUL), Niklas
Schulte (Fraunhofer), Olga Batura (TNO), Rafiqul Hague (Insight), Viivi Lähteenoja
(MyData).

Its **Architecture Board**: Bert Verdonck (LNDS), Chandra Challagonda (FIWARE), Christoph
Strnadl (Gaia-X), Claire Stolwijk (TNO), Daniel Alonso (BDVA), Frank Drijfhout (TNO),
Heidi Korhonen (VTT), Kai Kuikkaniemi (MyData), Matthijs Punter (TNO), Natalie Bertels
(KUL), Sebastian Steinbuss (IDSA), Tobias Moritz Guggenberger (Fraunhofer).
