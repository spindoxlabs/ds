# 06 — Data Exchange

> **Building block type**: Participant Agent  
> **Depends on**: 01-trust-framework, 02-identity-attestation, 03-access-usage-policies, 04-data-offerings-descriptions  
> **Required by**: 07-provenance-traceability

---

## Purpose

Data Exchange is where all preceding building blocks converge: the **actual transfer of data** from provider to consumer. This building block defines the protocols, negotiation sequence, and connector architecture that enable secure, policy-governed, auditable data transfers between participants.

The key standard is the **IDSA Dataspace Protocol (DSP)**, which governs how connectors communicate for catalogue queries, contract negotiation, and data transfers.

---

## The Dataspace Protocol (DSP)

The IDS Dataspace Protocol is the end-to-end protocol for participant-to-participant data exchange. It standardises three interaction categories:

### 1. Catalogue Protocol

```
GET  {connector-base-url}/catalog/datasets/{id}
     Returns: DCAT Dataset with embedded ODRL Offer

POST {connector-base-url}/catalog/request
     Body: { "@context": "...", "@type": "CatalogRequest", "filter": [...] }
     Returns: DCAT Catalog filtered by the query
```

### 2. Contract Negotiation Protocol

State machine with the following states:

```
REQUESTED → OFFERED → ACCEPTED → AGREED → VERIFIED → FINALIZED
         ↘                              ↗
          TERMINATED (at any point)
```

Key endpoints:

```
POST {provider-base}/negotiations
     Initiates a new negotiation
     Body: ContractRequest with ODRL Offer reference

GET  {provider-base}/negotiations/{id}
     Returns current negotiation state

POST {provider-base}/negotiations/{id}/request
     Consumer modifies or re-states their request

POST {provider-base}/negotiations/{id}/events
     Provider: sends OFFERED or AGREED event
     Consumer: sends ACCEPTED event

POST {provider-base}/negotiations/{id}/agreement/verification
     Consumer verifies the final agreement
```

### 3. Transfer Process Protocol

```
POST {provider-base}/transfers
     Initiates a data transfer under a verified agreement
     Body: TransferRequest with agreement ID and destination address

GET  {provider-base}/transfers/{id}
     Returns transfer state

POST {provider-base}/transfers/{id}/start
     Provider initiates the actual data push

POST {provider-base}/transfers/{id}/complete
     Signals transfer completion

POST {provider-base}/transfers/{id}/suspend
POST {provider-base}/transfers/{id}/terminate
```

---

## DSP Message Format

All DSP messages are JSON-LD with the IDS context:

```json
{
  "@context": "https://w3id.org/dspace/2024/1/context.json",
  "@type": "dspace:ContractRequest",
  "dspace:consumerPid": "urn:uuid:32541fe6-c580-409e-85a8-8a9a32fbe833",
  "dspace:offer": {
    "@type": "odrl:Offer",
    "@id": "https://provider.eu/policies/grid-data-v1",
    "odrl:target": "https://provider.eu/datasets/grid-frequency-2025"
  }
}
```

---

## Data Transfer Patterns

The data space does not mandate a single transfer mechanism. The agreed protocol is specified in the ODRL Agreement and the DCAT Distribution record.

### Pattern 1: HTTP Pull (REST)

```
Consumer sends TransferRequest → specifies pull destination
Provider connector authorises the request
Consumer sends GET to provider's data endpoint
Provider streams the response
```

Best for: structured datasets, one-off bulk transfers, paginated APIs

### Pattern 2: HTTP Push

```
Consumer provides a callback URL
Provider pushes data to consumer's endpoint after agreement
```

Best for: event-driven, webhook-style data delivery

### Pattern 3: Streaming (MQTT / AMQP)

```
Provider publishes to a topic / queue
Consumer subscribes post-agreement
Data flows continuously until transfer is terminated
```

Best for: IoT / sensor data, real-time telemetry, flexibility market bids

### Pattern 4: Algorithm-to-Data

```
Consumer sends an algorithm (code or container spec) to the provider
Provider executes the algorithm against local data (never transferred)
Provider returns only the computation result
```

Best for: privacy-sensitive data where raw transfer is prohibited; federated analytics

### Pattern 5: Messaging (cloud-native)

```
Provider publishes to shared message broker (Apache Kafka, RabbitMQ, Azure Event Hub)
Consumer reads from its authorised partition/topic
```

Best for: high-volume, low-latency, multi-consumer data distribution

---

## Connector Architecture

The connector is the technical unit that implements the DSP and enforces policies at the transfer boundary.

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONNECTOR                                │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ DSP Engine   │  │ Policy       │  │ Identity / Auth       │ │
│  │ - Catalogue  │  │ Enforcement  │  │ - VC wallet           │ │
│  │ - Negotiation│  │ Point (PEP)  │  │ - OIDC4VP presenter   │ │
│  │ - Transfer   │  │ - Calls PDP  │  │ - mTLS handler        │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────────────────┘ │
│         │                 │                                     │
│  ┌──────▼─────────────────▼────────────────────────────────────┐│
│  │              Data Plane                                      ││
│  │  - Actual data transfer (HTTP, MQTT, AMQP, S3, ...)         ││
│  │  - Transfer rate limiting                                   ││
│  │  - Encryption in transit                                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Audit / Provenance Logger                      ││
│  │  - Every transfer event → PROV-O record                    ││
│  │  - Every policy decision → structured log                  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Connector separation: Control Plane vs Data Plane

Most production connector implementations separate these concerns:

**Control plane** (DSP):
- Catalogue, negotiation, and transfer state machine
- Policy evaluation calls
- Credential presentation and verification
- Runs at low volume, high trust

**Data plane** (actual data transfer):
- HTTP, MQTT, AMQP endpoints
- Potentially high volume / streaming
- Authenticated by tokens issued by the control plane after agreement

This separation allows the data plane to scale independently and be implemented in the most appropriate technology for the data type.

---

## Security Requirements for Data Exchange

| Requirement | Specification |
|---|---|
| **Transport encryption** | TLS 1.3 minimum on all endpoints |
| **Connector authentication** | mTLS or DPoP (Demonstration of Proof-of-Possession) |
| **Message signing** | JWS signatures on all DSP messages |
| **Token binding** | Transfer tokens must be bound to the consumer's DID |
| **Rate limiting** | All endpoints must enforce rate limits |
| **Transfer audit log** | Every transfer event logged with timestamp, participant DIDs, data product ID, bytes transferred |

---

## Cross-Data-Space Protocol Alignment

When connecting two data spaces with potentially different governance frameworks:

- Both must agree on a common set of accepted DSP versions (`dspace:version` in connector self-description)
- Protocol negotiation happens at the beginning of the first interaction
- If the data spaces use different ODRL policy vocabularies, a mapping/bridging layer is required
- Transfer protocols (HTTP vs MQTT) must be agreed upfront — both sides list supported protocols in their self-descriptions

---

## Reference Implementations

| Implementation | Language | Maintained by |
|---|---|---|
| **Eclipse EDC (Connector)** | Java | Eclipse Foundation / IDSA |
| **Tractus-X Connector** | Java | Eclipse Tractus-X (Catena-X) |
| **FIWARE TRUE Connector** | Java | FIWARE Foundation |
| **TrueConnector** | Java | eng Ingegneria Informatica |

All of the above implement the IDSA Dataspace Protocol and are listed in the DSSC Toolbox.

---

## Implementation Checklist

- [ ] Select and deploy a DSP-compliant connector
- [ ] Implement catalogue endpoint (DSP Catalogue Protocol)
- [ ] Implement contract negotiation endpoint (DSP Negotiation Protocol)
- [ ] Implement transfer process endpoint (DSP Transfer Protocol)
- [ ] Implement control plane / data plane separation
- [ ] Configure TLS 1.3 on all endpoints
- [ ] Implement mTLS for connector-to-connector authentication
- [ ] Implement JWS message signing for all DSP messages
- [ ] Integrate PEP with PDP (policy check before every transfer)
- [ ] Implement transfer audit logging to provenance store
- [ ] Support at minimum HTTP Pull and HTTP Push transfer patterns
- [ ] Define and publish supported DSP version and transfer protocols in self-description
- [ ] Implement transfer rate limiting and circuit breakers
- [ ] Test end-to-end with a counterparty connector before go-live

---

## References

- [IDSA Dataspace Protocol Specification](https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol)
- [Eclipse EDC Connector](https://github.com/eclipse-edc/Connector)
- [IDSA Reference Architecture Model](https://docs.internationaldataspaces.org/ids-ram-4/)
- [DSP JSON-LD Context](https://w3id.org/dspace/2024/1/context.json)
- [Eclipse Tractus-X](https://eclipse-tractusx.github.io/)
