# CEEDS Blueprint v2.0 — Common European Energy Data Space
## Developer Reference for Energy Data Space Solutions

> **Source**: [Blueprint CEEDS v2.0](https://intnet.eu/images/resources/Blueprint_CEEDS_v2.pdf)  
> **Standard**: Energy-domain specialisation of the DSSC reference architecture  
> **Published**: July 2024 by int:net (Interoperability Network for the Energy Transition)  
> **License**: CC BY 4.0  
> **DOI**: 10.5281/zenodo.12609569

---

## What This Documentation Is

This folder is a structured technical reference extracted from the CEEDS Blueprint v2.0. It covers the architecture, building blocks, interoperability requirements, governance model, and business use cases specific to the **Common European Energy Data Space**. The CEEDS is explicitly designed as a specialisation of the DSSC Blueprint, layering energy-domain requirements on top of the generic data space framework.

Each topic has its own dedicated markdown file. Together they form a complete picture of how the energy sector adapts and extends the generic DSSC architecture.

---

## Documentation Structure

```
ceeds-blueprint-docs/
├── README.md                          ← This file (index + overview)
├── 01-data-space-concept.md           ← Data space definition, strategies, federation model
├── 02-business-use-cases.md           ← Five reference BUCs for energy
├── 03-architecture.md                 ← Proposed CEEDS architecture (distributed + federated)
├── 04-federated-components.md         ← Components of the federated data space side
├── 05-technical-interoperability.md   ← Building blocks, actors, data formats, protocols
├── 06-semantic-interoperability.md    ← Ontologies, CIM, SAREF, harmonisation
├── 07-governance-interoperability.md  ← Governance layers, SGAM 6th layer, rulebook
└── 08-edscp-implementations.md       ← Pilot implementations, lessons learned
```

---

## Relationship to DSSC Blueprint

The CEEDS Blueprint is explicitly positioned as a **domain specialisation** of the DSSC Blueprint. Key relationship points:

- CEEDS aims to be a specialisation of the mandatory part of DSSC and future data space standards
- It recommends alignment via ISO/IEC/IEEE 42042 (reference architecture) and ISO/IEC 40131
- The document calls for a transversal EU task force between data space architects to ensure convergence
- Building blocks map directly to OPEN DEI / DSSC technical building blocks
- The DSSC control plane / data plane separation is adopted
- CEEDS adds energy-specific layers: SGAM framework, DERA 3.0, HEMRM role model

```
┌─────────────────────────────────────────────────────────┐
│              DSSC Blueprint (generic)                   │
│  Trust · Identity · Policy · Exchange · Provenance      │
├─────────────────────────────────────────────────────────┤
│              CEEDS Specialisation (energy)               │
│  SGAM · DERA 3.0 · HEMRM · CIM/SAREF · Grid codes     │
├─────────────────────────────────────────────────────────┤
│              Energy BUCs & Pilots                        │
│  Communities · DER · TSO-DSO · E-mobility · Renewables  │
└─────────────────────────────────────────────────────────┘
```

---

## Five Key Dimensions

The CEEDS Blueprint defines five deployment dimensions (vs. the DSSC three-layer model):

| Dimension | Scope |
|---|---|
| **Business** | Business models, roles per HEMRM, value chains |
| **Legal** | Overarching legal frameworks, contractual instruments |
| **Operation** | Use cases, processes, activities |
| **Functional** | Technical and governance building blocks, data standards |
| **Technology** | Adopted standards, software components, SGAM mapping |

---

## Energy-Specific Standards Quick Reference

| Area | Standards |
|---|---|
| Grid modelling | IEC 61970 (CIM), CGMES |
| Flexibility markets | IEC 62325 (ESMP) |
| DER communication | IEC 62746, IEC 61850-7 |
| Smart appliances/IoT | ETSI SAREF, SAREF4ENER |
| EV charging | OCPP (Open Charge Point Protocol) |
| Energy metering | IEC COSEM |
| Data interchange | JSON-LD, OData |
| Role model | HEMRM (Harmonised Electricity Market Role Model) |
| Architecture framework | SGAM (Smart Grid Architecture Model) |
| Data exchange reference | DERA 3.0 (Bridge Data Management WG) |

---

## Key Actors (Energy Domain)

| Actor | Role |
|---|---|
| **TSO** | Transmission System Operator — high-voltage grid |
| **DSO** | Distribution System Operator — medium/low-voltage grid |
| **FSP** | Flexibility Service Provider — aggregates DER flexibility |
| **CPO** | Charge Point Operator — EV charging infrastructure |
| **eMSP** | e-Mobility Service Provider — EV user services |
| **EMRSP** | Electro Mobility Roaming Service Provider — CPO/eMSP intermediary |
| **OEM** | Original Equipment Manufacturer — equipment suppliers |
| **Prosumer** | Consumer + producer of energy (e.g., residential PV) |
| **Energy Community** | REC/CEC — collective self-consumption entities |

---

*This documentation is derived from the CEEDS Blueprint v2.0, published by int:net under Horizon Europe grants (101070086, 101069831, 101069694, 101069839, 101069287, 101069510).*
