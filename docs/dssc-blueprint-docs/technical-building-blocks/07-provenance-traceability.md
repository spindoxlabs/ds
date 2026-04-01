# 07 — Provenance, Traceability, and Observability

> **Building block type**: Participant Agent + Facilitating  
> **Depends on**: 02-identity-attestation, 03-access-usage-policies, 06-data-exchange  
> **Required by**: Regulatory compliance in all scenarios; mandatory for GDPR, Data Act, AI Act contexts

---

## Purpose

Trust in a data space cannot rest on goodwill or contractual declarations alone. Without a technical record of what happened — what data was shared, with whom, under which contract, and how it was subsequently used — there is no basis for compliance verification, dispute resolution, or accountability.

This building block defines the **accountability layer** of a data space: how data lineage, transaction history, and system health are captured, stored, and made queryable in a standardised, interoperable way.

---

## Three Distinct Concepts

| Concept | Question answered | Time horizon |
|---|---|---|
| **Provenance** | Where did this data originate? Who created it? What processes transformed it? | Lineage — from origin to current state |
| **Traceability** | Who accessed this data, when, under which contract, and was the policy honoured? | Transaction history — all access events |
| **Observability** | Are connectors, catalogues, and trust services functioning correctly? | Operational — health of the data space |

These are related but distinct: provenance is about *data lineage*, traceability is about *transaction history*, and observability is about *system health*. A complete implementation needs all three.

---

## W3C PROV-O — The Provenance Standard

The DSSC Blueprint explicitly references W3C PROV-O as the standard for provenance interchange across data spaces, because it enables the interchange of provenance information generated in different systems and under different contexts.

### Core PROV-O Model

PROV-O defines three entity types and the relationships between them:

```
prov:Entity      — a data product, dataset, or artefact
prov:Activity    — a process, transformation, or data transfer
prov:Agent       — a participant, service, or person
```

Key relationships:

```
Entity   --wasGeneratedBy-->  Activity
Entity   --wasAttributedTo--> Agent
Entity   --wasDerivedFrom-->  Entity (for derived datasets)
Activity --wasAssociatedWith-> Agent
Activity --used-->            Entity (input consumed by the activity)
Agent    --actedOnBehalfOf--> Agent (delegation)
```

### Example: A Data Transfer as PROV-O

```turtle
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ds:   <https://dataspace.energy.eu/> .

# The data product transferred
ds:GridFrequency2025-2025-03-27
    a prov:Entity ;
    prov:wasAttributedTo <did:web:provider.eu> ;
    prov:wasGeneratedBy  ds:DataCollectionActivity-2025 .

# The transfer activity
ds:Transfer-a3f5c2d1
    a prov:Activity ;
    prov:startedAtTime   "2025-03-27T14:23:11Z"^^xsd:dateTime ;
    prov:endedAtTime     "2025-03-27T14:23:45Z"^^xsd:dateTime ;
    prov:wasAssociatedWith <did:web:consumer.eu> ;
    ds:underAgreement    ds:Agreement-x9k2p7m4 ;
    prov:used            ds:GridFrequency2025-2025-03-27 .

# The derived dataset at the consumer
ds:GridFrequency2025-consumer-copy
    a prov:Entity ;
    prov:wasDerivedFrom  ds:GridFrequency2025-2025-03-27 ;
    prov:wasGeneratedBy  ds:Transfer-a3f5c2d1 ;
    prov:wasAttributedTo <did:web:consumer.eu> .
```

---

## Events to Capture Across a Transaction Lifecycle

Every data space connector should generate provenance/traceability events at these points:

### Catalogue Event

```json
{
  "eventType": "CataloguePublished",
  "timestamp": "2025-01-10T09:00:00Z",
  "dataProductId": "https://provider.eu/datasets/grid-frequency-2025",
  "publisherDID": "did:web:provider.eu",
  "policyId": "https://provider.eu/policies/grid-data-v1",
  "policyHash": "sha256:a3f5c2d1..."
}
```

### Contract Negotiation Event

```json
{
  "eventType": "ContractAgreementSigned",
  "timestamp": "2025-03-27T14:22:55Z",
  "agreementId": "urn:uuid:x9k2p7m4-...",
  "providerDID": "did:web:provider.eu",
  "consumerDID": "did:web:consumer.eu",
  "dataProductId": "https://provider.eu/datasets/grid-frequency-2025",
  "offerId": "https://provider.eu/policies/grid-data-v1",
  "agreedTermsHash": "sha256:b7e9d4f2..."
}
```

### Transfer Event

```json
{
  "eventType": "DataTransferCompleted",
  "timestamp": "2025-03-27T14:23:45Z",
  "transferId": "urn:uuid:a3f5c2d1-...",
  "agreementId": "urn:uuid:x9k2p7m4-...",
  "protocol": "HTTPS/1.1",
  "bytesTransferred": 1482390,
  "resultCode": "SUCCESS"
}
```

### Post-Transfer Usage Event (consumer-side)

```json
{
  "eventType": "UsageObligationFulfilled",
  "timestamp": "2025-04-27T00:00:00Z",
  "agreementId": "urn:uuid:x9k2p7m4-...",
  "obligation": "odrl:delete",
  "dataProductId": "https://provider.eu/datasets/grid-frequency-2025",
  "fulfilledBy": "did:web:consumer.eu"
}
```

---

## Observability — System Health Layer

Beyond data lineage, the data space needs operational visibility:

### What to monitor

| Component | Key metrics | Alerting threshold |
|---|---|---|
| Connector | Request rate, error rate, latency | 5xx rate > 1% |
| Catalogue | Query response time, record count, last updated | Response > 2s |
| Identity/VC service | Credential issuance rate, revocation check latency | Revocation check > 500ms |
| Policy engine (PDP) | Decision latency, deny rate, error rate | Decision latency > 200ms |
| Trust anchor | Certificate expiry, CRL/OCSP availability | Cert expiry < 30 days |

### OpenTelemetry for structured observability

```python
# Python example using OpenTelemetry SDK
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider

tracer = trace.get_tracer("dssc.connector.transfer")

with tracer.start_as_current_span("data-transfer") as span:
    span.set_attribute("transfer.agreement_id", agreement_id)
    span.set_attribute("transfer.provider_did", provider_did)
    span.set_attribute("transfer.consumer_did", consumer_did)
    span.set_attribute("transfer.data_product_id", data_product_id)
    # ... execute transfer ...
    span.set_attribute("transfer.bytes", bytes_sent)
    span.set_attribute("transfer.result", "success")
```

### W3C Trace Context for distributed tracing

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate:  dssc=connector.provider.eu
```

Every DSP HTTP request must propagate W3C Trace Context headers so that a single end-to-end data transaction can be correlated across provider connector → data plane → consumer connector.

---

## Cross-Data-Space Provenance

When data crosses data space boundaries, the PROV-O lineage must survive the boundary:

```
Data Space A (Energy)
  prov:Entity: GridData-2025
  prov:wasGeneratedBy: Measurement-Activity-A

           ↓ transferred to

Data Space B (Mobility)
  prov:Entity: EnergySignal-for-EVCharging
  prov:wasDerivedFrom: GridData-2025     ← preserves cross-space lineage
  prov:wasGeneratedBy: Adaptation-Activity-B
```

The `prov:wasDerivedFrom` relationship preserves the lineage chain. Because PROV-O is a W3C standard, the graph is interpretable by both data spaces without custom adapters.

---

## Regulatory Use Cases

| Regulation | Provenance/Traceability requirement |
|---|---|
| **GDPR Art. 17** (right to erasure) | Must know where personal data was transferred to trigger deletion across the chain |
| **GDPR Art. 30** (records of processing) | Machine-readable record of all processing activities and data flows |
| **EU Data Act Art. 33** | Demonstrate fair access conditions and policy compliance per transaction |
| **EU AI Act** (high-risk AI) | Training data provenance required — which datasets, from which sources, at which version |
| **Dispute resolution** | Signed ODRL Agreement + PROV-O transfer record = evidentiary foundation |
| **Governance authority oversight** | Aggregate transaction metrics without seeing data content |

---

## Access Control for Provenance Records

Provenance records themselves are sensitive — they reveal who is sharing data with whom. Access must be governed:

| Role | Can query |
|---|---|
| **Data provider** | Own issuance events + all transfers of their data |
| **Data consumer** | Own access events + transfers where they are the consumer |
| **Governance authority** | Aggregate statistics + anomaly detection (not individual data content) |
| **Auditor (regulatory)** | Specific records requested under legal obligation |

Implement provenance record access control using the same ODRL + PEP pattern as data access.

---

## Storage Architecture

```
Connector events (PROV-O JSON-LD + OpenTelemetry)
        ↓
Message bus (Apache Kafka / RabbitMQ)
        ↓        ↓
  PROV-O store   Metrics store
  (RDF triplestore  (Prometheus /
   or graph DB)      InfluxDB)
        ↓              ↓
  SPARQL query    Grafana dashboard
  API             (operational view)
```

---

## Implementation Checklist

- [ ] Instrument connector to emit PROV-O events at all transaction lifecycle points
- [ ] Implement OpenTelemetry SDK in connector (traces + metrics + logs)
- [ ] Propagate W3C Trace Context headers on all DSP HTTP requests
- [ ] Deploy PROV-O store (RDF triplestore: Apache Jena, Virtuoso, or GraphDB)
- [ ] Implement SPARQL endpoint for provenance queries
- [ ] Implement access control on provenance store (ODRL-governed)
- [ ] Deploy metrics store (Prometheus) and dashboards (Grafana)
- [ ] Implement alerting on connector health metrics
- [ ] Implement consumer-side PEP obligation fulfilment logging
- [ ] For personal data scenarios: implement GDPR Art. 30 records-of-processing report from provenance store
- [ ] For AI use cases: implement training data provenance chain for EU AI Act compliance
- [ ] Test cross-data-space provenance preservation (`prov:wasDerivedFrom` survives boundary crossing)

---

## References

- [W3C PROV-O Ontology](https://www.w3.org/TR/prov-o/)
- [W3C PROV Primer](https://www.w3.org/TR/prov-primer/)
- [OpenTelemetry](https://opentelemetry.io/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Apache Jena TDB2 (RDF Store)](https://jena.apache.org/documentation/tdb2/)
- [GDPR Article 30](https://gdpr-info.eu/art-30-gdpr/)
- [EU AI Act — training data requirements](https://artificialintelligenceact.eu/)
