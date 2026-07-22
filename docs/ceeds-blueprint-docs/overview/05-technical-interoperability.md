# 05 — Technical Interoperability

## Overview

Technical interoperability defines the minimum technical framework required for all energy data space participants to process and understand metadata of offered services/data and perform data transfers. It covers four aspects: building blocks, actors, data formats, and data transmission protocols.

## Building Blocks

Nine technical building blocks, grouped into three categories:

### Data Interoperability
Capabilities for data exchange: semantic models, data formats, interfaces (APIs), provenance & traceability.

### Data Sovereignty and Trust
Capabilities for participant/asset identification, trust establishment, and policy definition/enforcement for access and usage control.

### Data Value Creation
Capabilities for value creation: registering and discovering data offerings/services, marketplace functionality, data sharing monetisation.

**Relationship to implementation**: No direct one-to-one correspondence between building blocks and technical components. A single technical component may implement multiple building blocks.

## Actors

Based on the DSBA Technical Convergence Paper v2.0:

| Actor | Role |
|---|---|
| **Data Space Governance Authority** | Defines and enforces rules for the data space |
| **Data Space** | The distributed system itself |
| **Participant** | Entity joining and operating within the data space |
| **Participant Agent** | Technical component acting on behalf of a participant (e.g., connector) |
| **Data Space Registry** | Registry of participants and their metadata |
| **Credential Issuer** | Issues and manages credentials for participants |
| **Identity/AuthN&AuthZ, Identity Provider** | Handles identification, authentication, and authorisation |

## Data Formats

- **Primary format**: JSON — lightweight, language-independent data interchange
- **Recommended**: JSON-LD — serialises linked data in JSON, enabling machine-interpretable semantic networks across documents

## Data Transmission Protocols

### Dataspace Protocol (DSP)

Specifications for interoperable data sharing among entities governed by usage control using web technologies. Covers:

1. **Dataset deployment** — How metadata is provisioned
2. **Agreement negotiation** — Syntactic expression and electronic negotiation of usage agreements
3. **Dataset access** — Via "transfer process protocols"

**Key properties**:
- Ensures fundamental technical interoperability for participants — a prerequisite for joining any data space
- Defines minimum standard of communication between connectors
- Connectors may deploy different features, semantic models, or business procedures beyond the minimum

### Control Plane vs Data Plane

| Aspect | Control Plane | Data Plane |
|---|---|---|
| **Scope** | Data management, routing, processing; user identification; access/usage policy enforcement | Physical movement and exchange of data |
| **Standardisation** | High-level common standards (identification, authentication) | Variable — adapts to data space requirements |
| **Patterns** | Standardised across data spaces | Large dataset sharing, message exchange, event-based (no universal solution) |

## Comparison with DSSC Building Blocks

| DSSC Building Block | CEEDS Coverage | Gap |
|---|---|---|
| BB-00 Foundational Standards | Implicit (JSON-LD, TLS mentioned) | No explicit protocol stack enumeration |
| BB-01 Trust Framework | Covered via Identity Management component | Less prescriptive on W3C VC, eIDAS specifics |
| BB-02 Identity & Attestation | Covered via Identity Management component | DID/VC lifecycle not detailed |
| BB-03 Access & Usage Policies | Covered via Access & Usage Policies component | ODRL/XACML/DPV not specified |
| BB-04 Data Descriptions | Covered via self-descriptions + DCAT reference | Less prescriptive on DCAT record structure |
| BB-05 Publication & Discovery | Covered via Publication & Discovery component | SPARQL, faceted search not detailed |
| BB-06 Data Exchange | Covered via DSP reference + connector architecture | Transfer patterns (A2D, streaming) less detailed |
| BB-07 Provenance & Traceability | Covered via Log component + Clearing House | PROV-O, OpenTelemetry not specified |
| BB-08 Vocabulary Hub | Covered with energy-specific emphasis (CIM, SAREF) | Similar scope, different domain focus |
| BB-09 Data Sovereignty | Covered conceptually via connector + policies | ABAC, token-based data plane not detailed |
| BB-10 Value Creation Services | Covered via BUCs and marketplace | Aligned conceptually |
| BB-11 Services Architecture | Covered via two-sided architecture model | Less prescriptive on deployment topologies |
