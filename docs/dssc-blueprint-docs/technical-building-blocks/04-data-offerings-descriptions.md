# 04 — Data, Services, and Offerings Descriptions

> **Building block type**: Participant Agent + Facilitating  
> **Depends on**: 00-foundational-standards, 03-access-usage-policies  
> **Required by**: 05-publication-discovery, 06-data-exchange

---

## Purpose

Before a consumer can discover or request data, the data and services available in the data space must be **described in a machine-readable, interoperable format**. This building block defines how data products, data services, and data space offerings are described so that:

- Consumers can discover what is available and under what conditions
- Policy engines can evaluate access rights before a transfer begins
- Cross-data-space interoperability is possible without custom adapters

The anchor standard is **W3C DCAT (Data Catalog Vocabulary)**, which provides a common understanding of data descriptions across all participants and data spaces.

---

## Core Standard: W3C DCAT

DCAT is a W3C recommendation for describing datasets and data services in machine-readable RDF/JSON-LD. The key classes are:

| DCAT class | Represents | Example |
|---|---|---|
| `dcat:Catalog` | A collection of datasets or services | The data space's catalogue |
| `dcat:Dataset` | A data product available for sharing | "EU Grid Frequency Measurements 2025" |
| `dcat:DataService` | An API or service providing access to data | "Real-time grid measurement API" |
| `dcat:Distribution` | A specific access point or download for a dataset | "CSV download" or "MQTT stream endpoint" |
| `dcat:CatalogRecord` | Metadata about how/when a dataset was catalogued | "Added 2025-01-10, last updated 2025-03-01" |

---

## DCAT Dataset Description — Minimum Viable Record

```json
{
  "@context": {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "xsd": "http://www.w3.org/2001/XMLSchema#"
  },
  "@type": "dcat:Dataset",
  "@id": "https://provider.eu/datasets/grid-frequency-2025",
  "dct:title": "EU Grid Frequency Measurements 2025",
  "dct:description": "30-second interval grid frequency readings from 47 measurement points across the synchronous European grid.",
  "dct:publisher": {
    "@id": "did:web:provider.eu",
    "dct:name": "GridOp GmbH"
  },
  "dct:issued": "2025-01-01",
  "dct:modified": "2025-03-27",
  "dct:temporal": {
    "dcat:startDate": "2025-01-01",
    "dcat:endDate": "2025-12-31"
  },
  "dct:spatial": "https://www.geonames.org/6255148",
  "dcat:keyword": ["grid frequency", "energy", "real-time", "synchronous area"],
  "dct:license": "https://creativecommons.org/licenses/by/4.0/",
  "odrl:hasPolicy": {
    "@id": "https://provider.eu/policies/grid-data-v1"
  },
  "dcat:distribution": [{
    "@type": "dcat:Distribution",
    "@id": "https://provider.eu/datasets/grid-frequency-2025/dist/mqtt",
    "dct:format": "application/octet-stream",
    "dcat:accessURL": "mqtts://stream.provider.eu:8883/grid/frequency",
    "dcat:mediaType": "application/json"
  }, {
    "@type": "dcat:Distribution",
    "@id": "https://provider.eu/datasets/grid-frequency-2025/dist/rest",
    "dcat:accessService": {
      "@type": "dcat:DataService",
      "@id": "https://provider.eu/services/grid-api",
      "dcat:endpointURL": "https://api.provider.eu/v1/grid/frequency",
      "dct:conformsTo": "https://spec.openapis.org/oas/v3.1.0"
    }
  }]
}
```

---

## Linking Policies to Dataset Descriptions

The policy (ODRL Offer) is referenced directly from the DCAT record via `odrl:hasPolicy`. This is what makes the data offer **self-describing**: a consumer querying the catalogue receives both the data description and the access terms in a single response.

```
dcat:Dataset
    └── odrl:hasPolicy → odrl:Offer
            ├── odrl:permission → who may use it and how
            ├── odrl:prohibition → what is forbidden
            └── odrl:obligation → what the consumer must do
```

This linkage is essential for the DSP contract negotiation flow — the consumer negotiates against a specific ODRL Offer ID, not against loosely defined terms.

---

## DCAT for Data Services

When the offering is an API or processing service rather than a static dataset:

```json
{
  "@type": "dcat:DataService",
  "@id": "https://provider.eu/services/flexibility-market-api",
  "dct:title": "MLF Flexibility Market API",
  "dct:description": "Real-time flexibility bids and settlement data for the local flexibility market.",
  "dcat:endpointURL": "https://api.provider.eu/v2/flexibility",
  "dcat:endpointDescription": "https://api.provider.eu/v2/openapi.json",
  "dct:conformsTo": "https://spec.openapis.org/oas/v3.1.0",
  "odrl:hasPolicy": { "@id": "https://provider.eu/policies/flexibility-api-v1" },
  "dcat:servesDataset": [{
    "@id": "https://provider.eu/datasets/flexibility-bids-2025"
  }]
}
```

---

## Self-Description for Connectors

Each **connector** (participant agent) also publishes a self-description — a DCAT record describing the participant's identity, supported protocols, and technical capabilities. This feeds the participant registry and enables federation.

```json
{
  "@type": "ids:Connector",
  "@id": "https://connector.provider.eu",
  "dct:title": "GridOp Connector",
  "ids:hasDefaultEndpoint": {
    "@type": "ids:ConnectorEndpoint",
    "ids:accessURL": "https://connector.provider.eu/api/v1"
  },
  "ids:securityProfile": "ids:BaseSecurityProfile",
  "ids:version": "4.2.0",
  "ids:supportedProtocols": ["DSP 2024-01", "OData 4.0", "MQTT 5.0"],
  "ids:maintainer": { "@id": "did:web:provider.eu" },
  "ids:curator": { "@id": "did:web:provider.eu" }
}
```

---

## Semantic Models and Vocabularies

Beyond DCAT structural metadata, data descriptions should reference shared **semantic models** so that consumers understand the meaning of data fields — not just how to access them.

### Recommended approach:

1. Reference an existing domain ontology in `dct:conformsTo` or `dcat:theme`
2. If no standard vocabulary exists, publish a SKOS concept scheme in the data space's vocabulary hub
3. Map your dataset's field names to ontology terms in the dataset's schema description

### Relevant domain ontologies:

| Domain | Ontology | Namespace |
|---|---|---|
| Energy | SAREF (Smart Applications REFerence) | `https://saref.etsi.org/core/` |
| Energy grid | CIM (Common Information Model) | IEC 61970 |
| Mobility | MobiVoc | `http://schema.mobivoc.org/` |
| Agriculture | AGROVOC | `http://aims.fao.org/aos/agrovoc/` |
| General-purpose | Schema.org | `https://schema.org/` |

---

## Cross-Data-Space Interoperability

Using DCAT as a common metadata standard is a key enabler of cross-data-space discovery:

> The use of a general standard such as W3C DCAT to generate metadata descriptions of data, services, and offerings entails a common understanding of such descriptions from participants coming from different data spaces.

This means a data consumer who has built a catalogue client for Data Space A can query Data Space B's catalogue with minimal adaptation — because both use DCAT with ODRL policies embedded.

For cross-space federation, DCAT catalogue records should be harvestable via a standardised `GET /catalogue` endpoint returning `application/ld+json`.

---

## Implementation Checklist

- [ ] Implement DCAT Dataset authoring interface for data providers
- [ ] Support minimum viable DCAT record fields (title, description, publisher, temporal, spatial, keywords, license, policy, distributions)
- [ ] Link every DCAT record to an ODRL Offer via `odrl:hasPolicy`
- [ ] Implement DCAT DataService descriptions for API-based offerings
- [ ] Publish connector self-description at a known, well-documented endpoint
- [ ] Reference domain ontology terms in dataset field descriptions
- [ ] Implement DCAT record versioning (update `dct:modified` on every change)
- [ ] Support content negotiation: `application/ld+json` and `text/turtle`
- [ ] Validate all DCAT records against SHACL shapes before publication
- [ ] Ensure `@context` URLs are cached locally (do not rely on remote resolution at runtime)

---

## References

- [W3C DCAT 3.0](https://www.w3.org/TR/vocab-dcat-3/)
- [W3C ODRL Vocabulary](https://www.w3.org/TR/odrl-vocab/)
- [ETSI SAREF Ontology](https://saref.etsi.org/)
- [IEC CIM for Energy](https://www.iec.ch/iec61970)
- [SHACL — Shapes Constraint Language](https://www.w3.org/TR/shacl/)
- [DSSC Blueprint — Data, Services and Offerings Descriptions](https://blueprint.dssc.eu/?pane=technical&technical=data-services-and-offerings-descriptions)
