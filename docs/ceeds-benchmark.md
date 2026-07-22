# Benchmark of CEEDS Blueprint v2.0 and DSSC Blueprint v3.0 

> **Purpose**: Identify key deviations between our DSSC-based approach and the CEEDS energy-domain specialisation to assess alignment and surface gaps.  
> **CEEDS version**: Blueprint v2.0 (July 2024, based on DSSC v1.0)  
> **DSSC version**: Blueprint v3.0 (March 2025, concluding version)  
> **Our approach**: Based on DSSC Blueprint v3.0 technical building blocks

---

## Executive Summary

The CEEDS Blueprint is a **domain specialisation** of the DSSC, not an alternative architecture. Our DSSC v3.0-based approach is broadly aligned with CEEDS requirements, with the DSSC providing a more mature and prescriptive technical foundation (evolved from v1.0 to v3.0 since CEEDS was written). The key deviations fall into three categories:

1. **Areas where CEEDS adds energy-specific requirements** we need to accommodate
2. **Areas where DSSC v3.0 has evolved beyond** what CEEDS references (v1.0)
3. **Structural/architectural differences** in how building blocks are organised

**Overall risk**: LOW — The CEEDS explicitly aims to be a specialisation of DSSC. Our DSSC v3.0 implementation is a superset of what CEEDS requires at the generic level. The main work is adding energy-domain layers on top.

---

## Deviation Matrix

### Legend
- **Aligned** — No significant deviation; our approach covers the requirement
- **CEEDS adds** — CEEDS requires energy-specific capabilities beyond generic DSSC
- **DSSC ahead** — DSSC v3.0 has evolved beyond what CEEDS references
- **Structural diff** — Same concepts, different organisation

---

### 1. Architecture Model

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Conceptual layers** | Three-layer model (Governance / Identity & Policy / Data) | Five deployment dimensions (Business / Legal / Operation / Functional / Technology) | Structural diff | LOW — CEEDS dimensions map onto DSSC layers; the five-dimension model adds Business and Legal explicitly |
| **Service categories** | Three types (Participant Agent / Facilitating / Value Creation) | Two-sided model (Distributed Data Platforms + Federated Data Space) | Structural diff | LOW — Both describe the same participant-federation split; DSSC is more prescriptive on per-service deployment |
| **Control/Data plane** | Detailed separation with specific protocol assignments | Adopted from DSSC v1.0; acknowledges data plane may vary | Aligned | NONE — Same concept, DSSC v3.0 is more detailed |
| **Reference architecture** | IDSA RAM 4.0, Gaia-X, DSSC-specific | DERA 3.0 (Bridge), SGAM, HEMRM | CEEDS adds | MEDIUM — Our implementation needs to map onto SGAM zones/domains and DERA 3.0 for energy-domain credibility |
| **Existing platform integration** | Assumes greenfield connector deployment | Explicitly models integration with existing EMS, ADMS, SCADA, market platforms | CEEDS adds | MEDIUM — Our connector architecture needs clear integration patterns for legacy energy platforms |

---

### 2. Trust Framework & Identity

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Trust anchors** | eIDAS 2.0 QTSP, CA, VC issuance service (detailed) | CA + DAPS (IDSA pattern); Gaia-X trust framework; moving to W3C DID/VC | DSSC ahead | LOW — Our W3C VC + eIDAS approach is the direction EDSCP projects are converging toward |
| **Identity standards** | W3C DID Core 1.0, W3C VC 2.0, OIDC4VP, eIDAS EUDIW | DID + VC (W3C), OpenID, SAML, OAuth; DAPS as interim | DSSC ahead | LOW — CEEDS pilots use DAPS as bridge; our OIDC4VP approach is forward-looking |
| **Identity sub-components** | Detailed VC lifecycle (issuance → storage → presentation → verification → revocation) | Identity Governor / Manager / Provider roles (more organisational) | Structural diff | LOW — Both cover the same ground; DSSC is technically detailed, CEEDS is organisationally detailed |
| **Credential types** | Membership VC, Role VC, Compliance VC, Capability VC, Consent VC | Not enumerated — relies on IDSA/Gaia-X credential patterns | DSSC ahead | LOW — Our VC type taxonomy is more complete |
| **Revocation** | W3C Status List 2021 (specified) | Not detailed | DSSC ahead | NONE — Our approach is compliant |

---

### 3. Access & Usage Policies

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Policy language** | W3C ODRL (specified), W3C DPV extension for GDPR | Not specified — mentions "machine-readable, executable" policies | DSSC ahead | LOW — Our ODRL approach is compliant; CEEDS doesn't contradict it |
| **Enforcement architecture** | XACML pattern (PAP/PIP/PDP/PEP) detailed | Enforcement via data space connectors (general) | DSSC ahead | LOW — CEEDS doesn't specify an alternative |
| **Consent management** | Cross-organisational consent with Consent VC, GDPR Art. 7 | Consent mentioned in BUC context (data owner consent for sharing) | DSSC ahead | LOW — Our consent model covers CEEDS requirements |
| **Contract negotiation** | DSP contract negotiation protocol (state machine) | Contracting component with smart contract automation | CEEDS adds | MEDIUM — Smart contract settlement (Ethereum, ERC721/ERC20 tokens) is an energy-domain innovation not in DSSC. We may need to support token-based compensation models |
| **Policy types** | Access policies + Usage policies (same distinction) | Access policies + Usage policies (same distinction) | Aligned | NONE |

---

### 4. Data Descriptions & Discovery

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Metadata standard** | W3C DCAT 3.0 (detailed record structure, SHACL validation) | DCAT recommended; self-descriptions follow FAIR principles | Aligned | NONE — Same standard |
| **Catalogue model** | Three options: centralised, decentralised/federated, hybrid | Two options: centralised/distributed or decentralised/P2P | Aligned | NONE — Same concept |
| **Marketplace** | Not a first-class concept (value creation services host marketplace logic) | Marketplace is a core component with specific functionality (search, request, contracting, payment) | CEEDS adds | MEDIUM — CEEDS treats marketplace as a distinct architectural component with brokering, bidding, and compensation features. Our catalogue may need marketplace extensions |
| **Gaia-X Marketplace Federator** | Not specifically referenced | Used by OMEGA-X, ENERSHARE, Data Cellar for cross-data-space catalogue federation | CEEDS adds | LOW — Implementation pattern, not architectural requirement |

---

### 5. Data Exchange

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Protocol** | IDSA Dataspace Protocol (DSP) — detailed state machine | DSP referenced as minimum standard; EDSCP projects transitioning to DSP | Aligned | NONE |
| **Transfer patterns** | Five: HTTP Pull, HTTP Push, Streaming, A2D, Messaging | REST + Pub-Sub APIs mentioned; Kafka-based streaming in BUC #2 | Aligned | LOW — CEEDS doesn't contradict DSSC patterns; Kafka is a concrete implementation of the streaming pattern |
| **Connector implementations** | Eclipse EDC, Tractus-X, TRUE Connector referenced | IDSA connector spec; multiple implementations in EDSCP pilots | Aligned | NONE |
| **Real-time requirements** | Streaming pattern mentioned (MQTT/AMQP) | Strong emphasis on real-time/near-real-time data exchange (IoT, SCADA, smart meters, 15-min intervals) | CEEDS adds | MEDIUM — Energy domain has strict latency requirements (15-min intervals for grid operations, real-time for SCADA). Our streaming/messaging implementation must meet these SLAs |
| **Edge computing** | Not specifically addressed | Emphasised for residential DER management (BUC #2) | CEEDS adds | LOW — Architectural pattern for deployment, not a protocol concern |

---

### 6. Provenance & Traceability

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Standard** | W3C PROV-O, OpenTelemetry, W3C Trace Context | "Log" component — clearing house concept | DSSC ahead | LOW — CEEDS uses more abstract model; our PROV-O approach is forward-looking |
| **Clearing House** | Not a first-class concept (provenance store serves similar function) | Explicit Clearing House: records activities, billing, conflict resolution, policy enforcement, data accounting | CEEDS adds | MEDIUM — The Clearing House concept adds billing/settlement functions beyond pure provenance. May need to extend our provenance store with financial settlement capabilities |
| **Observability** | OpenTelemetry instrumentation, Grafana dashboards | Not detailed | DSSC ahead | NONE |

---

### 7. Vocabulary & Semantics

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Generic standards** | SKOS, OWL 2, SHACL, SPARQL | RDF, JSON-LD, ontologies (general reference) | DSSC ahead | NONE — Same foundation |
| **Domain ontologies** | References SAREF, CIM, Schema.org, QUDT (as examples) | **Mandates** energy-specific: CIM (IEC 61970), IEC 61850, IEC 62325, IEC 62746, COSEM, SAREF/SAREF4ENER, OCPP, CGMES | CEEDS adds | HIGH — Energy domain requires specific IEC/ETSI ontologies. Our vocabulary hub must host and validate against these standards |
| **Conformity assessment** | Not specifically addressed | CGMES Conformity Assessment Scheme (CAS) by ENTSO-E as reference model | CEEDS adds | MEDIUM — Energy data spaces may require formal conformity assessment against CIM/CGMES schemas |
| **Vocabulary governance** | Detailed: term proposal/approval, semantic versioning, deprecation, URI stability | Functions listed (store, search, document, export, validate, auto-integrate with catalogue) | Structural diff | LOW — Both cover governance; DSSC is more prescriptive on process |

---

### 8. Data Sovereignty

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Sovereignty principles** | Six principles (no central copy, provider-controlled, usage control, auditability, revocability, portability) | Data sovereignty via connector + policies (conceptual) | DSSC ahead | NONE — Our approach is more detailed |
| **ABAC** | Detailed attribute-based access control with VC attribute resolution | Not specified | DSSC ahead | NONE |
| **Algorithm-to-data** | Specified as maximum sovereignty pattern | Not explicitly mentioned | DSSC ahead | LOW — May be relevant for energy AI use cases (cross-portfolio learning without data sharing) |
| **Deployment patterns** | Three: full self-hosted, managed connector, cloud-native | Connector run by participant or on their behalf | Aligned | NONE |

---

### 9. Governance

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Governance structure** | Rulebook, trust framework, participation rules | Four governance layers + ten building blocks across SGAM | Structural diff | LOW — Both address governance comprehensively; CEEDS adds SGAM-specific layering |
| **6th SGAM layer** | Not applicable (domain-agnostic) | Proposed "Framework" layer for political, regulatory, societal interoperability | CEEDS adds | LOW — Relevant for energy governance stakeholder mapping, not for our technical implementation |
| **Regulatory scope** | GDPR, DGA, Data Act, eIDAS, AI Act | Same + energy-specific: Directive 2019/944 Art. 23, demand side flexibility code, ENTSO-E/DSO Entity network codes | CEEDS adds | MEDIUM — Energy-specific regulations affect data management approaches (meter data, flexibility registers) |
| **Role model** | Generic (governance authority, participants, service providers) | HEMRM (Harmonised Electricity Market Role Model) — detailed energy actor taxonomy | CEEDS adds | MEDIUM — Our participant model needs to map onto HEMRM roles for energy-domain deployments |
| **Onboarding/Offboarding** | Detailed (VCs, trust framework, credential lifecycle) | Detailed (application → evaluation → API key → terms & conditions; offboarding with data deletion and access revocation) | Aligned | LOW — Different detail levels but compatible approaches |

---

### 10. Value Creation & Compensation

| Aspect | DSSC v3.0 | CEEDS v2.0 | Deviation | Impact |
|---|---|---|---|---|
| **Service taxonomy** | Analytics, data processing, domain apps, intermediary/brokering | Marketplace functionality, value-added services, AI services, application services | Aligned | NONE |
| **Compensation models** | Not specified (domain-neutral) | Three models: data-by-tokens (crypto), data-by-data (barter), data-by-currency (FIAT) | CEEDS adds | MEDIUM — Energy data spaces introduce novel compensation mechanisms. Token-based and barter models require marketplace extensions |
| **Smart contracts** | Not addressed | Ethereum-based (SYNERGIES: Contract Settlement Engine; Data Cellar: ERC721/ERC20) | CEEDS adds | LOW — Implementation choice, not architectural requirement for our generic platform. Energy deployments may layer this on top |
| **Federated learning** | Mentioned as pattern for privacy-sensitive AI | ENERSHARE implements federated learning platform for cross-device model training | Aligned | LOW — Concrete implementation of the A2D/federated pattern |

---

## Key Deviations Requiring Action

### HIGH Impact

| # | Deviation | Action Required |
|---|---|---|
| 1 | **Energy-domain ontologies are mandatory** (CIM, IEC 61850, SAREF, COSEM, CGMES) | Our vocabulary hub must be extensible to host and validate against IEC/ETSI energy standards. Design the hub with domain-specific schema plug-in support |

### MEDIUM Impact

| # | Deviation | Action Required |
|---|---|---|
| 2 | **SGAM/DERA 3.0 mapping** | For energy-domain credibility, document how our architecture maps to SGAM zones/domains and DERA 3.0 layers |
| 3 | **Legacy platform integration** | Our connector architecture should define clear integration patterns for existing EMS, ADMS, SCADA, market platforms |
| 4 | **Marketplace as first-class component** | Evaluate whether our catalogue needs marketplace extensions (bidding, compensation, contract settlement) |
| 5 | **Clearing House with financial settlement** | Extend our provenance/traceability model to support billing, conflict resolution, and data accounting use cases |
| 6 | **Real-time/streaming SLAs** | Define specific SLAs for energy data exchange (15-min intervals, SCADA real-time) in our streaming/messaging implementation |
| 7 | **Smart contract compensation** | Design compensation model extensibility (token-based, barter, FIAT) for energy marketplace deployments |
| 8 | **HEMRM role mapping** | Map our participant model onto HEMRM roles for energy-domain identity and access control |
| 9 | **Energy-specific regulation compliance** | Ensure our governance model accounts for Directive 2019/944, demand side flexibility code, and network codes |
| 10 | **CGMES conformity assessment** | Consider supporting formal conformity assessment workflows for CIM/CGMES schema validation |

### LOW Impact (Aligned or DSSC Ahead)

Our DSSC v3.0-based approach is ahead of CEEDS in these areas (no action needed):
- Trust framework (W3C VC 2.0, eIDAS 2.0, OIDC4VP — more mature than DAPS)
- Policy language (ODRL + DPV — more prescriptive than CEEDS)
- Enforcement architecture (XACML PAP/PIP/PDP/PEP — more detailed)
- Provenance (PROV-O + OpenTelemetry — more specified)
- Sovereignty (six principles, ABAC, A2D — more detailed)
- Deployment topologies (three patterns — more prescriptive)

---

## Conclusion

Our DSSC v3.0-based approach provides a **strong foundation** that is already aligned with CEEDS at the generic data space level. The main work to achieve full CEEDS compatibility is **additive, not corrective**:

1. **Add energy-domain semantic layers** (CIM, SAREF, IEC standards in vocabulary hub)
2. **Add marketplace/compensation capabilities** (token, barter, FIAT models)
3. **Add legacy integration patterns** (EMS, ADMS, SCADA connectors)
4. **Add energy governance mapping** (SGAM, HEMRM, energy regulations)
5. **Define real-time SLAs** for energy streaming use cases

The CEEDS Blueprint was written against DSSC v1.0. Our v3.0-based implementation is already ahead in most technical areas. The gap is purely on the domain-specific side.
