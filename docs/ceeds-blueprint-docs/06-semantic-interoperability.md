# 06 — Semantic Interoperability

## Overview

Semantic interoperability ensures different systems and devices exchange and interpret information consistently and accurately based on shared understanding of meaning and context. This is a critical area where the CEEDS adds significant energy-domain specificity beyond the generic DSSC framework.

## Harmonisation Frameworks

Harmonisation frameworks for data sharing under a shared semantic context:
- Establish common vocabularies, data models, and ontologies
- Ensure unified understanding across different systems
- Reduce complexity and improve data compatibility
- Enable seamless interactions within the smart grid ecosystem

## Energy-Domain Standards and Ontologies

| Standard | Scope | Application |
|---|---|---|
| **SAREF** | Smart Appliances REFerence ontology | Behind-the-meter equipment |
| **SAREF4ENER** | SAREF extension for energy domain | Energy-specific IoT devices |
| **IEC 61970 (CIM)** | Common Information Model | Grid modelling |
| **IEC 62325 (ESMP)** | Energy Schedule and Market Profile | Flexibility market interfaces |
| **IEC 62746** | Systems interface between customer and grid | Service provided to technical aggregator communication |
| **IEC 61850-7** | Communication networks in substations | Advanced DER controls |
| **IEC COSEM** | Companion Specification for Energy Metering | Smart metering data exchange |
| **OCPP** | Open Charge Point Protocol | Public charging point interfaces |
| **OData** | Open Data Protocol | Standardised data access |
| **CIM** | Overarching Common Information Model | Overarching data model and ontologies |
| **CGMES** | Common Grid Model Exchange Standard | Grid model exchange (ENTSO-E) |

## CGMES Conformity Assessment Scheme (CAS)

Developed by ENTSO-E as an example of conformity assessment in the energy domain. Demonstrates how semantic conformance can be validated at scale.

## Ontology-Based Data Exchange

For data spaces with data exchange, approaches based on data ontology (highlighting relations among data instances) are mandatory to avoid data silos.

**Key technologies**:
- **RDF** — Framework for expressing linked data (triples: subject, predicate, object)
- **URIs** — For naming relationships and endpoints
- **Serialisation formats**: Turtle, TriG, JSON-LD
- **Common ontologies** — Shared vocabulary and conceptual framework

## Vocabulary Hub Role

Vocabulary Hubs publish different data models and are key to linking the marketplace for data/service offering discovery. Standards provide a common framework for:
- Data model definitions
- Message profile formats
- Protocol specifications

By adhering to semantic and syntactic standards, data sources align their data structures and semantics for seamless interoperability.

## Differences from DSSC BB-08 (Vocabulary Hub)

| Aspect | DSSC BB-08 | CEEDS |
|---|---|---|
| **Domain focus** | Generic (references SAREF, CIM, Schema.org) | Energy-specific (CIM, SAREF, IEC standards detailed) |
| **Governance** | Term proposal/approval process, semantic versioning | Not detailed |
| **Multilingual** | Required (EN + national language minimum) | Not explicitly addressed |
| **SKOS/OWL** | Detailed specification of concept schemes and ontologies | References RDF/ontologies generally |
| **SHACL validation** | Specified for data product validation | Not detailed |
| **Conformity assessment** | Not specifically addressed | CGMES CAS as energy-domain example |
