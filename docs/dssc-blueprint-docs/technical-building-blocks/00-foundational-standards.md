# 00 — Foundational Standards

> **Building block type**: Base layer — all other building blocks depend on this  
> **Maturity**: Stable (these are established open standards, not data-space specific)

---

## Purpose

The foundational standards layer defines the open, vendor-neutral protocols and vocabularies on which every other DSSC building block is constructed. The key principle is that **no data space component should depend on proprietary formats or closed protocols**. Interoperability across organisations, sectors, and national borders requires a shared, publicly governed technical baseline.

---

## Protocol Stack Overview

```
Application layer (data space logic)
    ↕
Semantic layer       →  RDF · JSON-LD · SPARQL · SKOS · OWL
    ↕
Policy layer         →  ODRL · DPV · XACML
    ↕
Identity layer       →  W3C DID · W3C VC · OIDC · OAuth 2.0
    ↕
Data exchange layer  →  HTTP/S · REST · WebSocket · MQTT · AMQP
    ↕
Security layer       →  TLS 1.3 · mTLS · X.509 PKI · JWS/JWE
    ↕
Network layer        →  TCP/IP · DNS
```

---

## Core Standards by Category

### Identity and Security

| Standard | Version | Role in data spaces |
|---|---|---|
| **TLS** | 1.3 (minimum) | All connector-to-connector communication |
| **mTLS** | — | Mutual authentication for machine-to-machine connector calls |
| **X.509** | v3 | Certificate format for PKI-based participant identity |
| **OAuth 2.0** | RFC 6749 | Token-based authorisation for API access |
| **OpenID Connect** | 1.0 | Identity federation layer over OAuth 2.0 |
| **JWT / JWS / JWE** | RFC 7519/7515/7516 | Signed and encrypted token format |
| **PKCE** | RFC 7636 | Required for public OAuth clients |

### Decentralised Identity

| Standard | Version | Role in data spaces |
|---|---|---|
| **W3C DID** | 1.0 | Decentralised, self-sovereign participant identifier |
| **W3C Verifiable Credentials** | 1.1 / 2.0 | Signed credential format for identity claims and attestations |
| **DID:web** | Community spec | URL-based DID method (most practical for legal entities) |
| **DID:key** | Community spec | Self-contained DID for ephemeral / machine identities |
| **OIDC4VP** | Draft | Presentation of VCs over OpenID Connect flows |

### Semantic Web / Metadata

| Standard | Version | Role in data spaces |
|---|---|---|
| **RDF** | 1.1 | Graph data model — foundation for all semantic standards |
| **JSON-LD** | 1.1 | JSON serialisation of RDF — used for VCs, DCAT, PROV-O, ODRL |
| **OWL 2** | — | Ontology language for data model definitions |
| **SKOS** | — | Vocabulary/taxonomy representation |
| **SPARQL** | 1.1 | RDF query language — used in catalogue federation |
| **Turtle** | 1.1 | Compact RDF serialisation (used in policy and provenance records) |

### Data Exchange Protocols

| Standard | Version | Role in data spaces |
|---|---|---|
| **HTTP/S** | 1.1 / 2 | Base protocol for all REST-based data exchange |
| **REST** | — | Architectural style for connector and catalogue APIs |
| **WebSocket** | RFC 6455 | Bidirectional channel for streaming data |
| **MQTT** | 5.0 | IoT / sensor streaming protocol |
| **AMQP** | 1.0 | Message queue protocol for asynchronous exchange |
| **OData** | 4.0 | Protocol for structured data API access |
| **GraphQL** | — | Flexible query protocol for complex data structures |

### Provenance and Observability

| Standard | Version | Role in data spaces |
|---|---|---|
| **W3C PROV-O** | 1.0 | Provenance ontology — lineage across data spaces |
| **OpenTelemetry** | 1.x | Structured logs, traces, and metrics |
| **W3C Trace Context** | 1.0 | Distributed request correlation across connector hops |

---

## Interoperability-by-Design Principle

The DSSC Blueprint's central recommendation is **interoperability-by-design**: selecting the standards above from the start of a data space initiative, rather than retrofitting them later. This means:

- Using JSON-LD for all credential, policy, and metadata documents (not proprietary JSON schemas)
- Implementing TLS 1.3 with certificate pinning on all connector endpoints
- Expressing all identifiers as URIs (enabling RDF linking across organisations)
- Serialising provenance records as PROV-O graphs (not custom audit log formats)
- Using established OAuth 2.0 / OIDC flows rather than bespoke authentication mechanisms

---

## Implementation Notes

**TLS configuration**: All connector-to-connector endpoints must enforce TLS 1.3 minimum. TLS 1.2 should be disabled. Certificate chains must be rooted in a trust anchor recognised by the data space's trust framework (see `01-trust-framework.md`).

**JSON-LD context management**: Every JSON-LD document (VCs, DCAT entries, ODRL policies, PROV-O records) requires a resolvable `@context` URL. For production deployments these contexts must be cached locally — do not rely on remote context resolution at runtime.

**Content negotiation**: Connector APIs should support at minimum `application/json` and `application/ld+json`. SPARQL endpoints should support `application/sparql-results+json` and `text/turtle`.

**Protocol versioning**: Document the exact version of each standard in your connector's self-description (DCAT metadata). This is required for the policy negotiation step in the Dataspace Protocol.

---

## References

- [W3C DID Core](https://www.w3.org/TR/did-core/)
- [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model-2.0/)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [W3C DCAT](https://www.w3.org/TR/vocab-dcat-3/)
- [W3C ODRL](https://www.w3.org/TR/odrl-model/)
- [IETF OAuth 2.0 RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
- [OpenTelemetry](https://opentelemetry.io/docs/)
- [ISO/IEC 19941 — Cloud interoperability](https://www.iso.org/standard/66639.html)
