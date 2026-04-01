# 05 — Publication and Discovery

> **Building block type**: Facilitating (federation-level)  
> **Depends on**: 04-data-offerings-descriptions, 01-trust-framework  
> **Required by**: 06-data-exchange

---

## Purpose

Once data products and services are described (DCAT), they must be **published in a discoverable way** so that potential consumers can find them. This building block defines how catalogues are structured, how participants publish offerings, and how consumers search across the data space — including across multiple federated data spaces.

---

## Catalogue Architectures

The Blueprint defines three catalogue models. The choice depends on the data space's governance model and scale.

### Model 1: Centralised Catalogue

```
All participants → publish DCAT records → Central catalogue service
Consumer → queries central catalogue → finds data products
```

- Simple to operate; single query endpoint
- Governance authority controls the catalogue
- Risk: single point of failure; bottleneck at scale
- Suitable for: small to medium data spaces with strong governance authority

### Model 2: Decentralised Catalogue (Federated)

```
Each participant → maintains own catalogue endpoint
Federation service → crawls / harvests all participant catalogues
Consumer → queries federation index → discovers across all participants
```

- Participants retain control of their own catalogue entries
- More resilient; no single point of failure
- Higher operational complexity (harvest scheduling, consistency)
- Suitable for: large data spaces; federations of data spaces

### Model 3: Hybrid

```
Participants → push DCAT records to federation broker
Federation broker → aggregates and indexes
Consumer → queries broker with full-text + faceted search
```

- Combines ease of querying with decentralised ownership
- Widely used in practice (e.g., Gaia-X Federated Catalogue, FIWARE Smart Data Models catalogue)

---

## Catalogue API Specification

Every participant's catalogue and every federation index must implement a standardised query interface:

### Core endpoints:

```
GET  /catalogue
     Returns: application/ld+json DCAT Catalog document
     Lists all datasets and services the participant offers

GET  /catalogue/datasets/{id}
     Returns: application/ld+json DCAT Dataset with embedded ODRL Offer

GET  /catalogue/services/{id}
     Returns: application/ld+json DCAT DataService

POST /catalogue/search
     Body: { "q": "grid frequency", "theme": "energy", "spatial": "DE" }
     Returns: matching DCAT records with pagination
```

### SPARQL endpoint (for semantic querying):

```
POST /catalogue/sparql
Content-Type: application/sparql-query

SELECT ?dataset ?title ?modified WHERE {
  ?dataset a dcat:Dataset ;
           dct:title ?title ;
           dct:modified ?modified ;
           dcat:theme <https://eurovoc.europa.eu/energy> .
}
ORDER BY DESC(?modified)
LIMIT 20
```

---

## DCAT Catalogue Record

A well-formed catalogue document links to its datasets and services:

```json
{
  "@context": {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/"
  },
  "@type": "dcat:Catalog",
  "@id": "https://provider.eu/catalogue",
  "dct:title": "GridOp Data Catalogue",
  "dct:publisher": { "@id": "did:web:provider.eu" },
  "dct:issued": "2025-01-01",
  "dct:modified": "2025-03-27",
  "dcat:dataset": [
    { "@id": "https://provider.eu/datasets/grid-frequency-2025" },
    { "@id": "https://provider.eu/datasets/capacity-data-q1-2025" }
  ],
  "dcat:service": [
    { "@id": "https://provider.eu/services/grid-api" }
  ]
}
```

---

## Faceted Search — Recommended Query Dimensions

Consumer-facing catalogue search should support filtering across these dimensions:

| Dimension | DCAT/DCT property | Example values |
|---|---|---|
| **Theme** | `dcat:theme` | Energy, Mobility, Health (EuroVoc URIs) |
| **Keyword** | `dcat:keyword` | "grid frequency", "flexibility", "SCADA" |
| **Spatial coverage** | `dct:spatial` | ISO 3166-1 country codes, GeoNames URIs |
| **Temporal coverage** | `dct:temporal` | Date ranges |
| **Format** | `dct:format` | CSV, JSON, RDF, MQTT |
| **Publisher** | `dct:publisher` | DID of the publishing participant |
| **License** | `dct:license` | CC-BY, proprietary, custom ODRL offer |
| **Update frequency** | `dct:accrualPeriodicity` | Monthly, daily, real-time |

---

## Federation of Catalogues

For cross-data-space discovery, catalogues must be harvestable:

```
Data Space A catalogue (DCAT)
        ↓  OAI-PMH harvest or DCAT pull
Federation index (aggregates DS-A + DS-B + DS-C)
        ↓  SPARQL / full-text search
Cross-space consumer
```

**Harvesting protocol**: The Blueprint references DCAT federation as the mechanism. In practice, the two most common approaches are:

1. **DCAT pull**: Federation index periodically fetches `GET /catalogue` from each member and merges into its index
2. **Event-driven push**: Participants publish catalogue update events to a shared message bus; the index subscribes

**Provenance preservation**: When harvesting, the federation index must preserve `dct:publisher` and `dct:source` from the original record. A consumer finding a dataset in the federated catalogue must be able to trace it back to the originating participant.

---

## Participant Registry

Separate from the data catalogue, a data space needs a **participant registry** — a catalogue of who is in the data space:

```json
{
  "@type": "dcat:Catalog",
  "@id": "https://dataspace.eu/participants",
  "dcat:dataset": [{
    "@type": "ids:Participant",
    "@id": "did:web:provider.eu",
    "dct:title": "GridOp GmbH",
    "ids:connectorEndpoint": "https://connector.provider.eu",
    "ids:membershipStatus": "active",
    "ids:roles": ["DataProvider", "ServiceProvider"]
  }]
}
```

This registry is consumed by:
- Consumers to discover available providers
- Policy engines to validate that a counterparty is an active member
- Governance authority for oversight and monitoring

---

## Implementation Checklist

- [ ] Implement DCAT catalogue endpoint (`GET /catalogue` returning `application/ld+json`)
- [ ] Implement dataset and service detail endpoints
- [ ] Implement full-text search endpoint with faceted filtering
- [ ] Implement SPARQL endpoint for semantic queries (at least SPARQL 1.1 SELECT)
- [ ] Implement pagination on all list endpoints (cursor-based recommended)
- [ ] Support content negotiation: `application/ld+json`, `text/turtle`, `application/json`
- [ ] Implement DCAT record validation (SHACL shapes) before publication
- [ ] Implement participant registry with membership status
- [ ] Implement catalogue harvesting client (for federation scenarios)
- [ ] Implement catalogue change events (webhook or message bus) for real-time federation
- [ ] Index `dcat:theme` using EuroVoc URIs for cross-space thematic interoperability
- [ ] Cache DCAT `@context` documents locally

---

## References

- [W3C DCAT 3.0](https://www.w3.org/TR/vocab-dcat-3/)
- [EuroVoc — EU Controlled Vocabulary](https://op.europa.eu/en/web/eu-vocabularies/concept-scheme/-/resource?uri=http://eurovoc.europa.eu/100141)
- [GeoNames — Spatial Coverage URIs](https://www.geonames.org/)
- [SHACL Shapes for DCAT](https://joinup.ec.europa.eu/collection/semantic-interoperability-community-semic/solution/dcat-application-profile-data-portals-europe/release/200)
- [Gaia-X Federated Catalogue](https://gaia-x.eu/what-is-gaia-x/deliverables/federation-services/)
- [FIWARE Smart Data Models](https://smartdatamodels.org/)
