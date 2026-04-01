# DSSC Blueprint v3.0 — Technical Building Blocks
## Developer Reference for Compliant Data Space Solutions

> **Source**: [DSSC Blueprint v3.0](https://blueprint.dssc.eu/?pane=technical)  
> **Standard**: Europe's shared reference architecture for building, governing, and scaling data spaces  
> **Version documented**: Blueprint 3.0 (concluding version of the DSSC project, March 2025)

---

## What This Documentation Is

This folder is a structured technical reference for engineers and architects building compliant European data space solutions. It covers all **Technical Building Blocks** defined in the DSSC Blueprint v3.0, with implementation-level detail on standards, protocols, architectures, and compliance requirements.

Each building block has its own dedicated markdown file. Together they form a complete picture of what must be implemented — and how — to achieve technical interoperability with Common European Data Spaces (CEDS).

---

## Documentation Structure

```
dssc-blueprint-docs/
├── README.md                          ← This file (index + overview)
└── technical-building-blocks/
    ├── 00-foundational-standards.md   ← Base layer: W3C, IETF, ISO protocols
    ├── 01-trust-framework.md          ← Trust anchors, PKI, eIDAS, onboarding
    ├── 02-identity-attestation.md     ← DID, VC, OIDC4VP, lifecycle management
    ├── 03-access-usage-policies.md    ← ODRL, DPV, enforcement (PAP/PIP/PDP/PEP)
    ├── 04-data-offerings-descriptions.md ← DCAT, metadata, semantic models
    ├── 05-publication-discovery.md    ← Catalogues, federated search, SPARQL
    ├── 06-data-exchange.md            ← DSP, IDS protocol, REST, streaming
    ├── 07-provenance-traceability.md  ← W3C PROV-O, audit logs, observability
    ├── 08-vocabulary-hub.md           ← Ontologies, SKOS, semantic alignment
    ├── 09-data-sovereignty.md         ← Connectors, policy enforcement, ABAC
    ├── 10-value-creation-services.md  ← AI analytics, domain apps, service taxonomy
    └── 11-services-architecture.md    ← Participant agent / federation / value-creation services
```

---

## The Three-Layer Mental Model

Every compliant data space solution must implement capabilities across three conceptual layers:

```
┌─────────────────────────────────────────────────────────┐
│              GOVERNANCE LAYER                           │
│  Rulebook · Trust framework · Participation rules       │
├─────────────────────────────────────────────────────────┤
│              IDENTITY & POLICY LAYER                    │
│  DID/VC · ODRL policies · Consent · Enforcement        │
├─────────────────────────────────────────────────────────┤
│              DATA LAYER                                 │
│  DCAT metadata · Catalogues · DSP exchange · PROV-O    │
└─────────────────────────────────────────────────────────┘
```

---

## Service Types: What You Need to Deploy

The Blueprint defines three categories of technical services:

| Service Type | Who runs it | What it does |
|---|---|---|
| **Participant Agent Services** | Each participant | Connector, VC wallet, policy engine, data source adapter |
| **Facilitating Services** | Data space / federation | Identity issuer, shared catalogue, consent registry, provenance store |
| **Value Creation Services** | Service providers | Domain apps, AI analytics, processing pipelines |

---

## Key Standards Quick Reference

| Building block | Primary standard(s) |
|---|---|
| Trust framework | eIDAS 2.0 · X.509 PKI · W3C VC |
| Identity & attestation | W3C DID · W3C VC · OIDC4VP |
| Access & usage policies | W3C ODRL · W3C DPV · XACML |
| Data descriptions | W3C DCAT · JSON-LD · RDF/OWL |
| Publication & discovery | W3C DCAT · SPARQL · OpenSearch |
| Data exchange | IDSA DSP · REST · OData · MQTT/AMQP |
| Provenance & traceability | W3C PROV-O · OpenTelemetry · W3C Trace Context |
| Vocabulary hub | SKOS · RDF/OWL · JSON-LD |
| Sovereignty & enforcement | XACML · ABAC · IDS Connector spec |

---

## Regulatory Compliance Touchpoints

Implementing these building blocks must account for:

- **GDPR** — identity management, consent, data subject rights, purpose limitation
- **EU Data Governance Act (DGA)** — trust service providers, data intermediaries
- **EU Data Act** — interoperability requirements (Article 33), fair access conditions
- **eIDAS 2.0** — qualified trust service providers, EU Digital Identity Wallet
- **EU AI Act** — training data provenance for high-risk AI systems

---

## How to Use This Documentation

1. Start with `00-foundational-standards.md` to understand the base protocol stack
2. Read `01-trust-framework.md` and `02-identity-attestation.md` — these are prerequisites for everything else
3. `03-access-usage-policies.md` is the core of data sovereignty — read it carefully before designing your connector
4. Use `06-data-exchange.md` for the DSP connector implementation spec
5. `07-provenance-traceability.md` is required reading for any regulated domain or AI use case
6. `11-services-architecture.md` ties all building blocks into a deployable services map

---

*This documentation is derived from the DSSC Blueprint v3.0, published by the Data Spaces Support Centre under the EU Digital Europe Programme (grant agreement nº 101083412).*
