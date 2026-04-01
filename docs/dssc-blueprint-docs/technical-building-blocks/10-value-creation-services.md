# 10 — Value Creation Services

> **Building block type**: Value Creation (application layer)  
> **Depends on**: All preceding building blocks  
> **Note**: This building block is domain-specific. The Blueprint provides a taxonomy and design guidance, not a fixed technical specification.

---

## Purpose

Value creation services are the **application layer of a data space** — the services that transform raw data access into business value. They operate within the governance framework of the data space, consuming data products via the exchange protocols defined in the preceding building blocks, and producing outputs that justify the data space's existence.

The DSSC Blueprint provides a taxonomy for classifying value creation services and recommends using DCAT to describe them — enabling their discovery and interoperability across data spaces.

---

## Service Taxonomy

The Blueprint organises value creation services into categories:

### 1. Analytics and Intelligence Services

Services that process data to generate insights:

| Service type | Description | Example |
|---|---|---|
| Descriptive analytics | Summarise historical data | Grid frequency statistics dashboard |
| Diagnostic analytics | Explain why something happened | Root-cause analysis of frequency deviations |
| Predictive analytics | Forecast future states | Day-ahead flexibility demand forecasting |
| Prescriptive analytics | Recommend actions | Optimal dispatch scheduling |
| AI/ML models | Trained on data space data | Anomaly detection, load forecasting |

### 2. Data Processing and Transformation Services

Services that enrich, clean, or transform data:

| Service type | Description |
|---|---|
| Data quality assessment | Profiling, completeness checks, outlier detection |
| Data harmonisation | Convert between data models (CIM ↔ SAREF mapping) |
| Aggregation | Combine data from multiple providers into composite datasets |
| Anonymisation / pseudonymisation | Privacy-preserving transformations |
| Format conversion | CSV → RDF, JSON → Parquet |

### 3. Domain Application Services

Sector-specific applications built on data space data:

| Sector | Example service |
|---|---|
| **Energy** | Local flexibility market platform (MLF), EV charging optimisation, demand response |
| **Mobility** | Multimodal journey planning, congestion prediction, emissions monitoring |
| **Agriculture** | Precision farming advisory, yield prediction, water usage optimisation |
| **Health** | Clinical decision support, epidemiological monitoring |
| **Manufacturing** | Supply chain visibility, predictive maintenance |

### 4. Intermediary and Brokering Services

Services that facilitate connections between participants:

| Service type | Description |
|---|---|
| Data marketplace | Matchmaking between data providers and consumers |
| API gateway | Managed access to multiple data sources under one interface |
| Consent broker | Cross-organisational consent collection and management |
| Escrow service | Trusted third-party holding data during disputes |

---

## How Value Creation Services Fit in the Data Space

```
Data Providers (raw data)
        ↓ DSP data exchange
Value Creation Service (processes data)
        ↓ DCAT-described output
Data Consumers (insight/product)
```

Value creation services are themselves **both consumers and providers** in the data space:
- They consume data from providers (via DSP, governed by ODRL access policies)
- They produce derived datasets or service outputs (described in DCAT, with their own ODRL policies)

---

## Describing Value Creation Services with DCAT

The Blueprint recommends using DCAT (and its extension for services) to describe value creation services, making them discoverable in the catalogue:

```json
{
  "@type": "dcat:DataService",
  "@id": "https://analytics.eu/services/flexibility-forecasting",
  "dct:title": "Day-Ahead Flexibility Demand Forecast",
  "dct:description": "Hourly probabilistic flexibility demand forecast for the next 24 hours, derived from grid measurements and weather data.",
  "dcat:endpointURL": "https://api.analytics.eu/v1/flexibility/forecast",
  "dcat:endpointDescription": "https://api.analytics.eu/v1/openapi.json",
  "odrl:hasPolicy": { "@id": "https://analytics.eu/policies/forecast-api-v1" },
  "dcat:servesDataset": [
    { "@id": "https://analytics.eu/datasets/flexibility-forecast-output" }
  ],
  "dct:conformsTo": "https://saref.etsi.org/saref4ener/",
  "dcat:keyword": ["flexibility", "forecast", "day-ahead", "energy"],
  "dcat:theme": { "@id": "https://eurovoc.europa.eu/energy" },
  "dct:hasVersion": "1.3.0"
}
```

---

## AI Services — Special Considerations

AI and ML services consuming data space data require additional governance:

### Training data governance

```
Training dataset selection
        ↓ DCAT discovery + DSP access
Data access under ODRL policy
        ↓ Requires: purpose=modelTraining (DPV purpose)
Model training
        ↓ PROV-O training data lineage record
Trained model
        ↓ Model card with training data provenance (EU AI Act)
Model deployment as value creation service
```

### EU AI Act compliance requirements for high-risk AI

Services deployed as high-risk AI systems (as defined in EU AI Act Annex III) must:
- Maintain provenance records of all training data (source, version, processing applied)
- Document data quality measures applied
- Implement monitoring for model drift
- Register in the EU AI Act database

### Federated learning pattern

When training data cannot leave its source (personal data, competitively sensitive data):

```
Coordinator service
├── Sends model parameters to each data owner
├── Data owners train locally
├── Data owners return model updates (not data)
└── Coordinator aggregates updates into global model
```

This pattern enables AI model training across a data space without any raw data transfer.

---

## Sector-Specific Implementation: Local Flexibility Market (Energy)

A Local Flexibility Market (MLF) is a canonical value creation service for energy data spaces:

```
Components:
├── Flexibility catalogue (DCAT descriptions of flexibility offers)
├── Bid submission API (DSO and BSP submit bids via DSP-governed access)
├── Market clearing algorithm (processes bids against grid constraints)
├── Settlement service (records outcomes, triggers payments)
└── Reporting service (provides transparency data to ARERA/regulators)

Data flows:
  CER/BSP → submits flexibility bid → market platform
  Grid measurement system → provides real-time grid data → market platform  
  Market platform → clearing decision → DSO activation signal
  Market platform → settlement record → PROV-O audit trail
```

Standards relevant to MLF:
- USEF Framework for flexibility market roles and processes
- IEC CIM for grid topology and measurement data
- ENTSO-E TIDE for European network code alignment
- ARERA 352/2021 (Italian regulatory framework)

---

## Design Principles for Value Creation Services

1. **Express as DCAT**: Every service must have a DCAT DataService description in the catalogue. A service that isn't discoverable isn't part of the data space.

2. **ODRL-governed access**: Service access must be governed by ODRL policies, negotiated via DSP. No out-of-band API keys or bilateral agreements outside the data space governance framework.

3. **Provenance preservation**: Services that derive outputs from data space inputs must preserve lineage via `prov:wasDerivedFrom` in their output dataset descriptions.

4. **Usage obligation propagation**: If input data carries an ODRL obligation (e.g., delete after 30 days), the derived output must carry at least an equally restrictive obligation.

5. **Algorithm-to-data first**: For privacy-sensitive inputs, prefer running analytics at the data source over transferring raw data to the analytics service.

---

## Implementation Checklist

- [ ] Define the value creation services the data space will support (as part of use case development)
- [ ] Publish each service as a DCAT DataService in the catalogue
- [ ] Govern service access via ODRL policies and DSP contract negotiation
- [ ] Implement PROV-O lineage tracking for all derived outputs
- [ ] For AI services: implement training data provenance chain
- [ ] For high-risk AI: comply with EU AI Act requirements (data documentation, monitoring, registration)
- [ ] For flexibility market: align with USEF framework and relevant regulatory requirements
- [ ] For personal data processing: implement federated learning or A2D patterns
- [ ] Propagate ODRL usage obligations to derived outputs

---

## References

- [USEF Flexibility Framework](https://www.usef.energy/)
- [ENTSO-E TIDE — Transparency and data exchange](https://www.entsoe.eu/)
- [EU AI Act](https://artificialintelligenceact.eu/)
- [Federated Learning — Google Research](https://research.google/pubs/pub45648/)
- [DSSC Blueprint — Value Creation Services](https://blueprint.dssc.eu/?pane=technical&technical=value-creation-services)
- [ARERA 352/2021 — MLF Framework (Italy)](https://www.arera.it/it/docs/21/352-21.htm)
