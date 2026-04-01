# 11 — Services Architecture

> **Building block type**: Reference architecture (cross-cutting)  
> **Purpose**: Ties all technical building blocks into a deployable services map  
> **Read this**: After reading all other building block files

---

## Purpose

This document maps the technical building blocks onto a concrete **deployable services architecture** — showing which services must be run, by whom, and how they interact. It answers the practical question: *what exactly do I need to deploy to build a compliant data space participant or data space platform?*

---

## The Three Service Categories

The DSSC Blueprint defines three categories of technical services. Every compliant data space deployment must cover all three.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VALUE CREATION SERVICES                          │
│           Domain applications · AI services · Analytics            │
│              (run by service providers; use all below)              │
├─────────────────────────────────────────────────────────────────────┤
│                   FACILITATING SERVICES                             │
│         (federation-level; run by governance authority or           │
│          trusted third-party service providers)                     │
│                                                                     │
│  Identity issuer  ·  Shared catalogue  ·  Consent registry         │
│  Provenance store  ·  Vocabulary hub  ·  Participant registry       │
├─────────────────────────────────────────────────────────────────────┤
│                   PARTICIPANT AGENT SERVICES                        │
│              (run by each individual participant)                   │
│                                                                     │
│  Connector  ·  VC wallet  ·  Policy engine  ·  Data adapter        │
│  Provenance logger  ·  Catalogue publisher                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Participant Agent Services — What Each Participant Runs

Every participant (data provider, data consumer, or service provider) must deploy the following:

### 1. Connector (DSP engine + PEP)

The connector is the mandatory gateway for all data exchange. It implements:
- IDSA Dataspace Protocol (catalogue, negotiation, transfer)
- Policy Enforcement Point (blocks unauthorised transfers)
- Transfer audit logging
- mTLS and token-based authentication

**Reference implementation**: Eclipse EDC, Tractus-X Connector, TRUE Connector

### 2. VC Wallet

Stores and presents Verifiable Credentials:
- Holds membership VC, role VC, compliance VCs
- Responds to OIDC4VP presentation requests from verifying connectors
- Manages key material (private keys for signing VPs)
- Monitors credential expiry and triggers renewal

### 3. Policy Engine (PAP + PDP)

The connector delegates access decisions to the policy engine:
- PAP: stores the participant's ODRL policies (for providers)
- PDP: evaluates ODRL rules against PIP-supplied context at runtime
- Integrated with PIP for VC attribute resolution

### 4. Data Adapter

Connects the connector to the participant's actual data sources:
- Abstracts databases, file systems, APIs, SCADA systems
- Applies data minimisation transformations
- Handles format conversion (e.g., raw CSV → DCAT-described JSON-LD)
- Implements schema mapping to shared vocabulary terms

### 5. DCAT Catalogue Publisher

Publishes and maintains the participant's data offerings in the catalogue:
- Generates and validates DCAT records
- Embeds ODRL Offer references in DCAT records
- Exposes `GET /catalogue` endpoint
- Updates records on data source changes

### 6. Provenance Logger (participant-side)

Records all transaction events locally:
- Emits PROV-O events for every transfer (as provider) and receipt (as consumer)
- Logs obligation scheduling and fulfilment (as consumer)
- Exports to federation provenance store if required

---

## Facilitating Services — What the Data Space Platform Runs

These are shared infrastructure services operated by the governance authority or contracted service providers. They enable the interplay between participants.

### 1. Identity Issuance Service (Trust Anchor)

- Issues membership and role VCs to verified participants
- Maintains W3C Status List 2021 for credential revocation
- Publishes DID Document at a well-known endpoint
- Integrates with eIDAS QTSP for qualified credentials

### 2. Participant Registry

- Lists all active participants with their DIDs and connector endpoints
- Exposes query API (DCAT format)
- Updated on onboarding/offboarding events
- Policy engines query this to validate membership

### 3. Shared Catalogue / Federation Index

- Harvests DCAT records from all participant catalogues
- Provides federated search and SPARQL endpoint
- Aggregates offerings across the data space
- May extend to cross-data-space federation

### 4. Consent Registry (for personal data scenarios)

- Stores consent records per data subject and processing purpose
- Exposes query API for PIP integration
- Manages consent withdrawal propagation
- Integrates with GDPR Art. 30 records-of-processing reporting

### 5. Federation Provenance Store

- Aggregates provenance records from participant connectors
- Provides SPARQL endpoint for audit and compliance queries
- Access-controlled (participants see only their own records; governance authority sees aggregate)
- Produces regulatory compliance reports on demand

### 6. Vocabulary Hub

- Hosts domain ontologies, SKOS concept schemes, credential schemas
- Exposes HTTP and SPARQL query API
- Governed by the data space community (term proposal/approval process)
- Versioned with immutable term URIs

---

## Service Interaction Map

```
Governance Authority
└── Identity Issuance Service ──────────────────────────┐
└── Participant Registry ────────────────────────────────│
└── Shared Catalogue ──────────────────────────────────  │
└── Federation Provenance Store ─────────────────────── │
└── Vocabulary Hub ───────────────────────────────────── │
                                                         │ VCs issued
                                                         ↓
Provider Participant                          Consumer Participant
├── VC Wallet  ◄── credentials                ├── VC Wallet  ◄── credentials
├── Catalogue Publisher ──► Shared Catalogue  ├── Connector ──► queries catalogue
├── Data Adapter                               ├── Policy Engine
├── Policy Engine                              ├── Provenance Logger
├── Connector                                  └── Data Adapter
└── Provenance Logger                                    
         │                                              │
         │◄──────── DSP: Catalogue Query ───────────────┤
         │◄──────── DSP: Contract Negotiation ──────────┤
         │◄──────── DSP: Data Transfer ─────────────────┤
         │                                              │
         └──► Federation Provenance Store ◄─────────────┘
```

---

## Deployment Topology Options

### Option A: Full self-hosted (maximum sovereignty)

All participant agent services run on the participant's own infrastructure. The participant has full control over keys, data, and policies. Maximum sovereignty; maximum operational burden.

```
Participant infrastructure (on-premise or dedicated cloud)
├── Connector (Docker / Kubernetes)
├── VC Wallet (HSM-backed key store)
├── Policy Engine
├── DCAT Publisher
└── Data Adapter → ERP / SCADA / Database
```

### Option B: Managed connector (reduced operational burden)

Participant uses a CaaS (Connector-as-a-Service) provider for the connector, retaining control of data and keys.

```
Participant infrastructure
├── VC Wallet (HSM-backed)
├── Data Adapter → data sources
└── Key material

CaaS Provider (trusted third party)
└── Connector (authorised by participant's credentials)
    ↓ data flows through CaaS
```

Note: CaaS providers must be registered as data intermediation service providers under the EU Data Governance Act.

### Option C: Cloud-native (for cloud-first participants)

All components deployed in a cloud tenant with managed services for key storage (KMS), container orchestration (Kubernetes), and observability.

```
Cloud tenant (e.g., Azure, AWS, GCP)
├── Connector (AKS / EKS pod)
├── VC Wallet → Cloud KMS
├── Policy Engine (serverless / containerised)
├── DCAT Publisher → object storage
└── Data Adapter → cloud data lake
```

---

## Compliance Verification Checklist — Full Architecture

Use this as a go/no-go checklist before declaring a data space solution production-ready:

### Trust and Identity
- [ ] Connector has a `did:web` DID with resolvable DID Document
- [ ] Participant holds valid membership and role VCs from governance authority
- [ ] Connector validates counterparty VCs (signature + revocation) on every interaction
- [ ] All private keys stored in HSM or cloud KMS (never in config files)

### Policy Enforcement
- [ ] Every data transfer is preceded by a DSP contract negotiation
- [ ] ODRL policy is evaluated by PDP before every transfer
- [ ] Provider-side PEP blocks any transfer not covered by a valid agreement
- [ ] Consumer-side PEP enforces usage obligations (deletion, attribution, purpose limitation)
- [ ] Every policy decision is logged

### Data Exchange
- [ ] TLS 1.3 enforced on all connector endpoints
- [ ] mTLS implemented for connector-to-connector authentication
- [ ] Transfer tokens are short-lived (max 1 hour) and bound to consumer DID
- [ ] Rate limiting and circuit breakers implemented on data plane

### Provenance and Traceability
- [ ] Every transfer event emits a PROV-O record
- [ ] PROV-O records stored in queryable triplestore
- [ ] OpenTelemetry instrumentation deployed
- [ ] W3C Trace Context propagated across all DSP requests

### Catalogue and Discovery
- [ ] DCAT catalogue endpoint live and returning valid JSON-LD
- [ ] All datasets have embedded ODRL Offer references
- [ ] Participant registered in shared participant registry

### Regulatory Compliance
- [ ] GDPR Art. 30 records-of-processing report implementable from provenance store
- [ ] Data subject rights (Art. 17 erasure) supported via credential revocation + provenance chain
- [ ] eIDAS 2.0 EUDIW compatibility assessed
- [ ] EU AI Act training data provenance chain implemented (if applicable)

---

## References

- [IDSA Architecture Reference Model 4.0](https://docs.internationaldataspaces.org/ids-ram-4/)
- [Eclipse EDC Connector](https://github.com/eclipse-edc/Connector)
- [DSSC Blueprint — Services for Implementing Technical Building Blocks](https://blueprint.dssc.eu/?pane=technical&technical=services-for-implementing-technical-building-blocks)
- [DSSC Toolbox](https://blueprint.dssc.eu/?pane=tools)
- [Gaia-X Architecture Document](https://gaia-x.eu/what-is-gaia-x/deliverables/architecture-document/)
- [EU Data Governance Act](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R0868)
