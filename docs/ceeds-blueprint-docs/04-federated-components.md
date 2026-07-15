# 04 — Components of the Data Space Federated Side

## Overview

The federated data space side of the CEEDS architecture contains six key components, each mapping to DSSC building blocks.

## Trust Framework

Groups two building blocks: Access & Usage Policies and Identity Management.

### Access & Usage Policies and Control

Connected to the concept of data sovereignty — control of access and usage of data.

**Two policy types**:
- **Access policies** — Conditions to access services and data
- **Usage policies** — Rights and obligations for data usage, including future usage

**Policy evaluation** requires connection to other building blocks for identification, authentication and authorisation. Policies are expressed from different contexts (data space level, contractual relationship, law) and must be consolidated into machine-readable, executable form.

**Implementation**: Performed via data space connectors, not directly in the trust framework.

### Identity Management

Covers three practical use cases:
1. **Identifying data space participants** — Via identity registry of governance-framework-compliant parties
2. **Identifying connectors and technical components** — Machine identity
3. **Identifying trusted data providers** — Certification of data provision capabilities

**Sub-components**:
- **Identity Governor** — Party performing identity governance function for a specific identity registry
- **Identity Manager** — Party performing identity management function
- **Identity Provider** — Party performing identity provisioning function

**Key properties**:
- Security/Resilience — Critical for cyber-secure systems
- Open Source — Keep identification implementation simple and open
- Interoperability — Alignment at European level, cross-data-space and cross-sector

**Reference frameworks**: OPEN DEI (identity in "Trust" category), Gaia-X (decentralised approach based on self-sovereign identity).

## Log (Provenance & Traceability)

Logs information about data usage, incidents, and transaction activities.

**Functions**:
- Provide evidence of each transaction activity
- Meet requirements from legal mandates, governance framework, contractual agreements, or policies
- Associated with "Clearing House" concept — intermediary for clearing/settlement of financial and data exchange transactions

**Clearing House capabilities**:
- Records all activities during data exchange
- Useful for billing and conflict resolution
- Monitors and logs data transactions
- Enforces policies
- Provides platform for data accounting

## Vocabulary Hub

Provides endpoints for seamless communication with data space connectors and infrastructure components.

**Functions**:
1. **Storing vocabularies** — Store and list valid vocabularies for public and long-term use
2. **Search on semantic sources** — Search for semantic resources based on criteria
3. **Documenting non-standardised data** — Include semantic information about non-standardised data during ingestion
4. **Export semantic sources** — Export in various formats (serialisation, human-readable)
5. **Automatic integration with catalogue** — Continuous integration with catalogue of vocabularies
6. **Validation of data** — Validate data against specific vocabularies

**Recommended standards**: DCAT for describing datasets/services. Energy-domain standards: IEC (CIM, 61850, COSEM), ETSI (SAREF).

## Contracting (Contractual Framework)

Encompasses contract templates, model clauses, and modules for managing specific data transactions.

**Capabilities**:
- Concluding contracts
- Monitoring compliance
- Terminating agreements
- Translating agreements into legally binding contractual obligations

**Contract automation**: May embed smart contracts to simplify and automate creation and execution, reducing transaction costs.

## Publication & Discovery (Catalogue)

Acts as a catalogue of self-descriptions for available data products.

**Key capabilities**:
1. **Management of self-descriptions** — Publication, update, removal by providers
2. **Facilitate discovery** — Following FAIR principles (Findable, Accessible, Interoperable, Reusable)
3. **Enable dynamic transactions** — Bringing together providers and users for establishing relationships
4. **Manage access to self-descriptions** — Access control for group-specific visibility

**Implementation options**:

| Option | Description | Reference |
|---|---|---|
| **Centralised/distributed catalogue** | Single or multiple catalogues with synchronisation | IDSA Metadata Broker specifications |
| **Decentralised/P2P catalogue** | Catalogue capabilities embedded in each participant's data connector | Control plane peer-to-peer discovery |

## Component Mapping to DSSC

| CEEDS Component | DSSC Building Block(s) | Notes |
|---|---|---|
| Trust Framework — Access & Usage Policies | BB-03 (Access and Usage Policies) | CEEDS less prescriptive on ODRL/XACML specifics |
| Trust Framework — Identity Management | BB-01 (Trust Framework) + BB-02 (Identity & Attestation) | CEEDS groups trust and identity together |
| Log | BB-07 (Provenance, Traceability, Observability) | CEEDS adds "Clearing House" concept |
| Vocabulary Hub | BB-08 (Vocabulary Hub) | CEEDS emphasises IEC/ETSI energy standards |
| Contracting | BB-03 partial (Contract Negotiation via DSP) | CEEDS adds smart contract automation |
| Publication & Discovery | BB-05 (Publication and Discovery) | Largely aligned |
