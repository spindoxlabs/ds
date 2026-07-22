# 03 — Proposed Architecture for CEEDS

## Two-Sided Architecture Model

The CEEDS architecture combines two layers:

1. **Distributed Data Exchange Platforms** — Existing data platforms (both regulated and unregulated)
2. **Federated Data Space** — Overarching orchestration framework (centralised or distributed)

This reflects DERA 3.0 (Data Exchange Reference Architecture), developed in the Bridge Data Management WG based on SGAM.

## Distributed Data Exchange Platforms

### Regulated Platforms
- Grid control room platforms (EMS, ADMS)
- Market platforms
- Meter data hubs
- Flexibility registers

### Unregulated Platforms
- DERMS (Distributed Energy Resource Management Systems)
- VPP (Virtual Power Plants)
- Charging Point Management systems
- Community Energy Management systems
- DER Technical Aggregators
- Building Energy Management systems

### Data Endpoints
Field devices providing real-time measurements:
- Sensors, voltage/current transformers, PMUs, RTUs
- Smart metering devices, embedded measurement devices
- IEDs, tap-changers, switching devices, behind-the-meter DERs

Data sources:
- SCADA, EMS, ADMS (real-time databases, forecast data)
- Prosumer inputs (load schedules, EV/DER consumption/generation)

### Communication Technologies
5G, LTE, fiber optics, PLC, secured internet

### Data Management Approaches (per Member State)
Three architectural patterns observed across EU, often applied in parallel for different data types:

| Model | Description | Examples |
|---|---|---|
| **Decentralised** | Data remains at point of origin; standardised market communication with explicit consent | Austria (EDA), Germany, France |
| **Centralised** | Data hub receives and stores data; all business processes operate within hub | Finland, Estonia |
| **Hybrid** | Decentralised communication with specific central structures for compliance/brokerage | Spain (DataDis) |

## Federated Data Space Layer

Where data is indexed, made discoverable, and traded. Data space participants federate through **data space connectors** and offer data under:
- Pre-recorded policies
- Verified credentials
- Data models
- Contractual agreements

### Data Space Connector

The central software component connecting participants to the federated data space. It:
- Enables identification, data harmonisation, and brokerage
- Uses standardised data exchange protocols
- Ensures data consistency and accuracy across connected systems
- Can be run by a participant or on their behalf

**Capabilities beyond connectivity**:
- Data interoperability functions
- Authentication interfacing with trust services
- Authorisation
- Data product self-description
- Contract negotiation

### Three Data Exchange Patterns

1. **Data indexing** — Participant -> federated data space (publishing own data)
2. **Data discovery** — Federated data space -> participant (finding available data)
3. **Bilateral exchange** — Between two data exchange platforms via REST or Pub-Sub APIs

## Control Plane vs Data Plane

Adopted from DSSC Blueprint v1.0:

| Plane | Responsibility | Standardisation |
|---|---|---|
| **Control Plane** | Data management, routing, processing decisions; user identification; access/usage policy enforcement (metadata) | Standardised at high level with common identification/authentication standards |
| **Data Plane** | Physical movement of data; actual exchange of energy-related data | May vary across data spaces (large datasets, message exchange, event-based) |

## Architecture Diagram Components

The complete CEEDS architecture (Figure 12) includes:

```
┌──────────────────────────────────────────────────────┐
│           FEDERATED DATA SPACE SIDE                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐    │
│  │  Trust    │ │   Log    │ │  Vocabulary Hub   │    │
│  │ Framework │ │(Prov &   │ │  (CIM, SAREF,     │    │
│  │ • Access  │ │ Trace)   │ │   IEC, DCAT)      │    │
│  │   Policy  │ │          │ │                   │    │
│  │ • Identity│ └──────────┘ └───────────────────┘    │
│  │   Mgmt    │                                       │
│  └──────────┘ ┌──────────┐ ┌───────────────────┐    │
│               │Contracting│ │  Publication &    │    │
│               │(Smart     │ │  Discovery        │    │
│               │ Contracts)│ │  (Catalogue)      │    │
│               └──────────┘ └───────────────────┘    │
├──────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────┐  │
│  │          DATA SPACE CONNECTORS                 │  │
│  │  (Control Plane + Data Plane)                  │  │
│  └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│        DISTRIBUTED DATA EXCHANGE PLATFORMS           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Regulated│ │Unregulated│ │  Field   │            │
│  │ Platforms│ │ Platforms │ │ Devices  │            │
│  │ (EMS,    │ │ (DERMS,  │ │ (SCADA,  │            │
│  │  ADMS,   │ │  VPP,    │ │  Smart   │            │
│  │  Markets)│ │  CPM)    │ │  Meters) │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└──────────────────────────────────────────────────────┘
```
