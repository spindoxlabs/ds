# 08 — Vocabulary Hub

> **Building block type**: Facilitating (federation-level)  
> **Depends on**: 00-foundational-standards, 04-data-offerings-descriptions  
> **Required by**: 04-data-offerings-descriptions, 05-publication-discovery, 06-data-exchange

---

## Purpose

For data to be *useful* — not just *exchangeable* — participants must share a common understanding of what the data means. A temperature reading means nothing without knowing the unit, the measurement context, and how "temperature" is defined in this domain. A vocabulary hub provides the **shared semantic layer** that enables this common understanding, making data interoperable not just technically but *semantically*.

Without shared vocabularies, every bilateral data exchange requires custom mapping and translation. With them, a consumer can query any compatible data source without prior knowledge of its internal naming conventions.

---

## What a Vocabulary Hub Contains

A vocabulary hub in a data space context serves as the authoritative registry for:

| Content type | Description | Format |
|---|---|---|
| **Ontologies** | Formal definitions of concepts and their relationships | OWL 2 / RDF |
| **Concept schemes** | Controlled vocabularies and taxonomies | SKOS |
| **Data models** | Structural schemas for specific data product types | JSON Schema / SHACL / XSD |
| **Code lists** | Enumerated values (status codes, unit codes, country codes) | SKOS / CSV |
| **Mappings** | Equivalence relations between concepts in different vocabularies | SKOS mappings / R2RML |
| **Credential schemas** | VC field definitions for identity and attestation | JSON-LD / JSON Schema |

---

## Core Standards

### SKOS — Simple Knowledge Organization System

SKOS is the W3C standard for representing controlled vocabularies, taxonomies, and thesauri. It is lightweight, well-tooled, and widely adopted.

```turtle
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix energy: <https://dataspace.energy.eu/vocab/> .

energy:FlexibilityService
    a skos:Concept ;
    skos:prefLabel "Flexibility Service"@en, "Servizio di Flessibilità"@it ;
    skos:definition "A service that provides adjustable power consumption or generation in response to grid operator signals."@en ;
    skos:broader energy:GridService ;
    skos:narrower energy:UpwardFlexibility, energy:DownwardFlexibility ;
    skos:exactMatch <https://saref.etsi.org/saref4ener/FlexibilityService> .
```

### OWL 2 — Web Ontology Language

For richer semantic relationships and inference:

```turtle
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix energy: <https://dataspace.energy.eu/vocab/> .

energy:FlexibilityBid
    a owl:Class ;
    rdfs:subClassOf energy:MarketOffer ;
    rdfs:label "Flexibility Bid"@en ;
    rdfs:comment "An offer to provide upward or downward flexibility at a given price."@en .

energy:offeredPower
    a owl:DatatypeProperty ;
    rdfs:domain energy:FlexibilityBid ;
    rdfs:range xsd:decimal ;
    rdfs:label "offered power (MW)"@en .
```

### SHACL — Shapes for Data Validation

SHACL defines validation rules for RDF data graphs — used to validate that data products conform to their declared schema before publication:

```turtle
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix energy: <https://dataspace.energy.eu/vocab/> .

energy:FlexibilityBidShape
    a sh:NodeShape ;
    sh:targetClass energy:FlexibilityBid ;
    sh:property [
        sh:path energy:offeredPower ;
        sh:datatype xsd:decimal ;
        sh:minInclusive 0 ;
        sh:maxInclusive 1000 ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
    ] ;
    sh:property [
        sh:path energy:activationPeriod ;
        sh:datatype xsd:duration ;
        sh:minCount 1 ;
    ] .
```

---

## Vocabulary Hub API

The vocabulary hub must be queryable by participants and their connectors:

```
GET  /vocabulary/concepts/{scheme}
     Returns: SKOS Concept Scheme in text/turtle or application/ld+json

GET  /vocabulary/ontologies/{name}
     Returns: OWL ontology document

GET  /vocabulary/schemas/{type}
     Returns: JSON Schema or SHACL Shapes for a data product type

GET  /vocabulary/mappings/{source-vocab}/{target-vocab}
     Returns: SKOS mapping document

POST /vocabulary/sparql
     Body: SPARQL query against the vocabulary graph
     Returns: query results

GET  /vocabulary/concepts/{scheme}/concept/{id}
     Returns: individual concept with labels, definitions, relations
```

---

## Cross-Data-Space Semantic Alignment

For cross-space interoperability, vocabulary hubs must support **concept mappings** between different data spaces' vocabularies:

```turtle
# Energy data space concept
energy:DownwardFlexibility
    skos:exactMatch <https://mobility.eu/vocab/DemandReduction> ;
    skos:closeMatch <https://health.eu/vocab/CapacityReduction> .
```

SKOS mapping properties:

| Property | Meaning |
|---|---|
| `skos:exactMatch` | The two concepts are equivalent in all contexts |
| `skos:closeMatch` | Similar but not identical — use with caution for automated mapping |
| `skos:broadMatch` | One concept is broader than the other |
| `skos:narrowMatch` | One concept is more specific |
| `skos:relatedMatch` | Related but neither broader nor narrower |

The Blueprint explicitly states that data spaces should be able to **exchange their data models in a standardised manner** to establish agreements on their usage, with vocabulary services federated between them.

---

## Domain Ontologies to Reuse (Not Reinvent)

Before creating new vocabulary terms, check whether an established domain ontology already covers the concept:

| Domain | Ontology | Coverage |
|---|---|---|
| **Energy / IoT** | SAREF + SAREF4ENER | Smart appliances, energy flexibility, grid services |
| **Energy grid** | IEC CIM (CGMES) | Grid topology, power flow, measurements |
| **Flexibility markets** | USEF Framework | Flexibility market actors, products, processes |
| **Mobility** | MobiVoc | Transport modes, stops, routes |
| **Agriculture** | AGROVOC | Agricultural commodities, practices |
| **General data** | DCAT | Datasets, catalogues, distributions |
| **General business** | Schema.org | Organizations, products, events |
| **Organisations** | W3C ORG | Organizational structures |
| **Time** | OWL-Time | Temporal concepts and intervals |
| **Measurement** | QUDT | Units of measurement, quantities |

---

## Multilingual Support

Data spaces spanning multiple EU member states must support multilingual vocabulary labels. SKOS `prefLabel` and `altLabel` support language tags:

```turtle
energy:GridFrequency
    skos:prefLabel "Grid Frequency"@en ;
    skos:prefLabel "Frequenza di Rete"@it ;
    skos:prefLabel "Netzfrequenz"@de ;
    skos:prefLabel "Fréquence du Réseau"@fr ;
    skos:definition "The frequency of the alternating current in the electricity grid, expressed in Hz."@en .
```

---

## Governance of the Vocabulary Hub

The vocabulary hub is a shared infrastructure asset — its governance is as important as its technical implementation:

| Governance aspect | Recommendation |
|---|---|
| **Term proposal** | Any participant can propose new terms via a defined process |
| **Term approval** | Governance authority reviews and approves; community comment period |
| **Versioning** | Semantic versioning (MAJOR.MINOR.PATCH); never silently change term meaning |
| **Deprecation** | Deprecated terms remain accessible for 2+ years with `owl:deprecated true` |
| **URI stability** | Term URIs must be permanent; use a dedicated namespace you control |
| **Change log** | Every release documented in a public SKOS change note |

---

## Implementation Checklist

- [ ] Deploy a vocabulary hub with resolvable HTTP URIs for all terms
- [ ] Implement SKOS concept scheme for domain-specific vocabulary
- [ ] Reference established domain ontologies (SAREF, CIM, QUDT) rather than inventing duplicates
- [ ] Implement SHACL shapes for all data product types and publish in vocabulary hub
- [ ] Implement multilingual labels for all terms (at minimum EN + national language)
- [ ] Implement SPARQL endpoint for semantic queries over vocabulary graph
- [ ] Implement mapping service for cross-data-space concept alignment
- [ ] Implement versioning with immutable, dereferenceable term URIs
- [ ] Publish vocabulary hub location in data space rulebook
- [ ] Reference vocabulary hub terms in DCAT dataset descriptions (`dct:conformsTo`, `dcat:theme`)
- [ ] Implement credential schema registry as part of vocabulary hub

---

## References

- [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)
- [W3C OWL 2 Primer](https://www.w3.org/TR/owl2-primer/)
- [W3C SHACL](https://www.w3.org/TR/shacl/)
- [ETSI SAREF Ontology](https://saref.etsi.org/)
- [QUDT Ontologies](https://qudt.org/)
- [IEC CIM / CGMES](https://www.iec.ch/iec61970)
- [USEF Flexibility Framework](https://www.usef.energy/)
- [Apache Jena (RDF/OWL/SPARQL)](https://jena.apache.org/)
