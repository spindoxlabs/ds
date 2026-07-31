# Data Models

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Data Models
> **Category** · Data Interoperability

This building block enables semantic interoperability among data space participants through the use of shared data models. It explains how data models, which are structured representations of data elements stored in a common vocabulary service, act as dictionaries to facilitate data exchange. It addresses both top-down (adopting standard models) and bottom-up approaches (specifically helping data providers new to semantic technologies), and provides practical guidance on how data models can be implemented, reused, and governed, by whom, and with what tools.

## Scope and objectives

The objective of this building block is to enable semantic interoperability among data space participants through the use of shared data models. This allows:

- participants of dataspaces to interpret each other's data.
- the development, reuse and governance of data models within and across data spaces.
- the semantic annotations of datasets.

This building block supports compliance with [article 33, point b, of the EU Data Act](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202302854), which requires data providers to describe their data structures, data formats, vocabularies, classification schemes, taxonomies and code lists, where available, in a publicly available and consistent manner.

## Capabilities

The source states explicitly that **it is not mandatory to define a common (domain) data model in a dataspace, as part of the rulebook**. Every participant can specify the data model of their own data, as far as this is not limited by the dataspace rulebook to a certain (set of) data model(s).

Nevertheless, the following capabilities in a dataspace **can contribute** to achieving semantic interoperability:

- **Data model development**: Reuse or develop data models to ensure uniformity and interoperability.
- **Data model governance**: Governance and management aspect of data models, including tools and processes to maintain data models and to ensure wide consensus regarding the data model used in the data space.
- **Data model integration**: The description of the data offering should include a reference to the data model that explains the structure and semantics of the datasets.
- **Data model abstraction**: Transition from semantic to technical interoperability, enabling exchanging data conform the data models (see also: Data Exchange building block).
- **Data models across data spaces**: Standardized discovery of data models across data spaces, support multiple data spaces to become semantic interoperable.

## Co-creation questions

Upstream identifies co-creation method questions to semantically express the datasets in an offering and enhance semantic interoperability between participants within a data space (the source refers to *Figure 1*, which is not reproduced in the text). The answers to each of the co-creation questions should land in the rulebook of the data space.

**For which (categories of) data products does the data space need to manage semantics?**

Start by creating a clear overview of the information exchange processes to identify which data offerings are being exchanged. The data space offerings building block explains this topic. Based on this overview, you can then analyze each (category of) data products in your offering to decide which data elements and concepts are required to be semantically expressed. Clearly identifying the required data elements and concepts helps evaluate the suitability of existing models.

**Which data models are already available and can be re-used? Which new (shared) data models need to be created?**

First evaluate the suitability of existing models. If existing models do not suffice, explore the ability to extend and existing model. Only if this is not viable, create a new model reusing existing concepts from existing standards where possible. The reusing of a data models depends on different factors:

- The standardization organizations behind the data models (for example W3C).
- Their level of maturity and adoption (the W3C Community is very large).
- The integration of the data models with others (some data models already use concepts used in many other data models).
- The constraints that a data model imposes (for example specific cardinality constraints).

**What kind of meta-standard will be used to express the data models in the data space?**

Data models are expressed in one or more meta-standards. Try to follow some best practices where the data models adhere to open metamodel standards, depending on the domain and application requirements. Best practices of metamodel to set up and/or annotate a domain-specific data model:

- RDF Schema and SHACL for RDF (Resource Description Framework).
- OWL (Web Ontology Language) also for RDF.
- SKOS (Simple Knowledge Organization System).
- JSON Schema.
- XML Schema (XSD), Schematron for XML-oriented data models.
- CSVW for CSV-oriented tabular data.
- XSLT, R2RML, RML, and CSVW for data transformation specification.

Data models might refer to one or more reference datasets. Reference data means data that are used to characterise or relate to other data, such as codelist about country codes. Try to follow commonly used reference datasets as defined by the European commission: EU controlled vocabularies.

**How will data models be managed within the data space?**

A data model management process is required for maintaining the data models. This includes engaging key stakeholders who must collaborate throughout this process (e.g., standard development organisations). For existing standards, one could use the existing process set up for this. This role is often fulfilled collectively by business communities and delegated to a Standards Development Organisation (SDO), depending on whether data models are based on existing standards and their governance framework.

To support the adoption of a data model and the management process, a data spaces requires a tool for publishing, editing, browsing and maintaining vocabularies and related documentation. A vocabulary service, as described in this building block and the DSSC Toolbox, is an example of such a tooling.

## Standards and protocols

Upstream is explicit under its "Specifications" heading: **"There are no mandatory specifications a dataspace shall follow for implementing this capability."** The standards below are therefore named as best practice or as illustration, not as mandated profiles. Where the source supplies a version or a release link, it is reproduced verbatim; where it does not, the version column is left empty.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| RDF Schema | — | Meta-standard for RDF-expressed data models; used in the source's ontology example | recommended |
| SHACL | — | Meta-standard for RDF; expresses application-profile cardinalities, data types and constraints | recommended |
| OWL (Web Ontology Language) | — | Meta-standard for RDF; ontology layer | recommended |
| RDF (Resource Description Framework) | — | Open metamodel standard for expressing ontologies | recommended |
| SKOS (Simple Knowledge Organization System) | — | Meta-standard for the vocabulary layer (taxonomies, classification schemes) | recommended |
| JSON Schema | draft-07 (in the source's data schema example) | Meta-standard for the data schema layer | recommended |
| XML Schema (XSD) | — | Meta-standard for XML-oriented data models / data schema layer | recommended |
| Schematron | — | Meta-standard for XML-oriented data models | recommended |
| CSVW | — | CSV-oriented tabular data models; also named for data transformation specification | recommended |
| XSLT | — | Data transformation specification | recommended |
| R2RML | — | Data transformation specification | recommended |
| RML | — | Data transformation specification | recommended |
| UML (Unified Modelling Language) | — | Open metamodel standard named for expressing ontologies | referenced |
| LinkML | — | Named as a meta-standard in which an application profile can be expressed | referenced |
| Excel | — | Named as a means in which an application profile can be expressed | referenced |
| DCAT | — | Exchange of metadata about data models between data spaces via the Vocabulary Service | should |
| DCAT-AP | [3.0.0](https://semiceu.github.io/DCAT-AP/releases/3.0.0/) | Linking each dataset offered to the data model describing its structure and semantics | may |
| [`dcterms:conformsTo`](https://www.w3.org/TR/vocab-dcat-3/#Property:resource_conforms_to) | DCAT 3 property | Property by which a dataset or data service in DCAT references a data model in the vocabulary service | may |
| [Data Space Protocol](https://internationaldataspaces.org/offers/dataspace-protocol/) | — | Cataloguing and exchanging data models as datasets, making them findable and accessible across data spaces | may |
| EU controlled vocabularies (EU reference datasets) | — | Commonly used reference datasets as defined by the European Commission | recommended |
| [EU Data Act](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202302854), article 33, point b | — | Legal obligation this building block supports compliance with | must |

## Implementation

This building block relates primarily to the following service:

- **Vocabulary service**: The storage and publication of all data models are centralised within a vocabulary service. Each Vocabulary Service should provide an API through which data models can be retrieved. It should allow access to the different abstraction levels of a data model and enable the exchange of metadata for these models using the DCAT standard. That latter enables the exchange of data models between data spaces.

Other services, such as the participant agent, can use the data models managed through the vocabulary service.

## Glossary

The terms being used in this page and conceptual model are specified below.

| Term | Definition |
|---|---|
| Data Model | A structured representation of data elements and relationships used to facilitate semantic interoperability within and across domains, encompassing vocabularies, ontologies, application profiles and schema specifications for annotating and describing data sets and services. These abstraction levels may not need to be hierarchical; they can exist independently. |
| Data element | the smallest units of data that carry a specific meaning within a dataset. Each data element has a name, a defined data type (such as text, number, or date), and often a description that explains what it represents. |
| Data model provider | An entity responsible for creating, publishing, and maintaining data models within data spaces. This entity facilitates the management process of vocabulary creation, management, and updates. |
| Vocabulary service | A technical component providing facilities for publishing, editing, browsing and maintaining vocabularies and related documentation. |
| Meta-standard | A standard designed to define or annotate data models within a particular domain or across multiple domains. These meta-standards provide a framework or guidelines for creating and annotating other standards (data models), ensuring consistency, interoperability, and compatibility. |
| Vocabulary | A data model that contains basic concepts and relationships expressed as terms and definitions within a domain or across domains, typically described in a meta-standard like SKOS. |
| Ontology | A data model that defines knowledge within and across domains by modelling information objects and their relationships, often expressed in open metamodel standards like OWL, RDF, or UML. |
| Application Profile | A data model that specifies the usage of information in a particular application or domain, often customised from existing data models (e.g., ontologies) to address specific application needs and domain requirements. |
| Reference datasets | Reference data, such as code lists and authority tables, means data that are used to characterise or relate to other data. Such a reference data, defines the permissible values to be used in a specific field for example as metadata. Reference data vocabularies are fundamental building blocks of most information systems. Using common interoperable reference data is essential for achieving interoperability. |
| Data Schema | A data model that defines the structure, data types, and constraints. Such a schema includes the technical details of the data structure for the data exchange, usually expressed in metamodel standards like JSON or XML Schema. |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Section numbers in the Source column are the upstream document's own numbered headings.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-DMO-01` | Data providers must describe their data structures, data formats, vocabularies, classification schemes, taxonomies and code lists, where available, in a publicly available and consistent manner (EU Data Act, article 33, point b). | must | `data-models.md` §1 |
| `DSSC-DMO-02` | Defining a common (domain) data model in a dataspace, as part of the rulebook, is not mandatory. | may | `data-models.md` §2 |
| `DSSC-DMO-03` | Every participant can specify the data model of their own data, as far as this is not limited by the dataspace rulebook to a certain (set of) data model(s). | may | `data-models.md` §2 |
| `DSSC-DMO-04` | Data model development: reuse or develop data models to ensure uniformity and interoperability. | may | `data-models.md` §2 |
| `DSSC-DMO-05` | Data model governance: provide tools and processes to maintain data models and to ensure wide consensus regarding the data model used in the data space. | may | `data-models.md` §2 |
| `DSSC-DMO-06` | The description of the data offering should include a reference to the data model that explains the structure and semantics of the datasets. | should | `data-models.md` §2 |
| `DSSC-DMO-07` | Data model abstraction: enable the transition from semantic to technical interoperability, so that data can be exchanged conform the data models. | may | `data-models.md` §2 |
| `DSSC-DMO-08` | Data models across data spaces: provide standardized discovery of data models across data spaces. | may | `data-models.md` §2 |
| `DSSC-DMO-09` | Decide for which (categories of) data products the data space needs to manage semantics, and record the answer in the rulebook. | should | `data-models.md` §3 |
| `DSSC-DMO-10` | Start by creating a clear overview of the information exchange processes to identify which data offerings are being exchanged. | should | `data-models.md` §3 |
| `DSSC-DMO-11` | First evaluate the suitability of existing models. | should | `data-models.md` §3 |
| `DSSC-DMO-12` | If existing models do not suffice, explore the ability to extend an existing model. | should | `data-models.md` §3 |
| `DSSC-DMO-13` | Only if extending an existing model is not viable, create a new model reusing existing concepts from existing standards where possible. | should | `data-models.md` §3 |
| `DSSC-DMO-14` | Data models should adhere to open metamodel standards, depending on the domain and application requirements. | recommended | `data-models.md` §3 |
| `DSSC-DMO-15` | Follow commonly used reference datasets as defined by the European Commission (EU controlled vocabularies). | recommended | `data-models.md` §3 |
| `DSSC-DMO-16` | A data model management process is required for maintaining the data models. | must | `data-models.md` §3 |
| `DSSC-DMO-17` | Key stakeholders (e.g., standard development organisations) must collaborate throughout the data model management process. | must | `data-models.md` §3 |
| `DSSC-DMO-18` | For existing standards, the management process already set up for those standards may be used. | may | `data-models.md` §3 |
| `DSSC-DMO-19` | A data space requires a tool for publishing, editing, browsing and maintaining vocabularies and related documentation. | must | `data-models.md` §3 |
| `DSSC-DMO-20` | The answers to each of the co-creation questions should land in the rulebook of the data space. | should | `data-models.md` §3 |
| `DSSC-DMO-21` | There are no mandatory specifications a dataspace shall follow for implementing this capability. | informative | `data-models.md` §4 |
| `DSSC-DMO-22` | The storage and publication of all data models are centralised within a vocabulary service. | informative | `data-models.md` §5 |
| `DSSC-DMO-23` | Each Vocabulary Service should provide an API through which data models can be retrieved. | should | `data-models.md` §5 |
| `DSSC-DMO-24` | The Vocabulary Service should allow access to the different abstraction levels of a data model. | should | `data-models.md` §5 |
| `DSSC-DMO-25` | The Vocabulary Service should enable the exchange of metadata for data models using the DCAT standard. | should | `data-models.md` §5 |
| `DSSC-DMO-26` | Other services, such as the participant agent, can use the data models managed through the vocabulary service. | may | `data-models.md` §5 |
| `DSSC-DMO-27` | Data space participants must semantically define the data in their offerings by using a standardised data model, agreed within the data space. | must | `best-practice-building-data-models-for-dataspaces.md` §2 |
| `DSSC-DMO-28` | Data models are published and stored in a vocabulary service that enables data models to be discovered throughout a data space. | informative | `best-practice-building-data-models-for-dataspaces.md` §2 |
| `DSSC-DMO-29` | Linking each dataset offered to a data model that describes its structure and semantics can be achieved by using the DCAT-AP standard. | may | `best-practice-building-data-models-for-dataspaces.md` §2 |
| `DSSC-DMO-30` | Each dataset or data service in DCAT can reference a data model in the vocabulary service using the property `dcterms:conformsTo`. | may | `best-practice-building-data-models-for-dataspaces.md` §2 |
| `DSSC-DMO-31` | Data models, being data themselves, can be cataloged and exchanged using the DCAT standard and the Data Space Protocol, making them findable and accessible across data spaces. | may | `best-practice-building-data-models-for-dataspaces.md` §2 |
| `DSSC-DMO-32` | Data schemas should be used during data exchange, as specified in the data exchange protocol outlined by the Data Exchange building block. | should | `best-practice-building-data-models-for-dataspaces.md` §2.1 |
| `DSSC-DMO-33` | The different data models should be aligned between each other so that each representation of the same data model is coherent. | should | `best-practice-building-data-models-for-dataspaces.md` §2.1 |
| `DSSC-DMO-34` | Data spaces should make use of existing data models and the corresponding management process defined by the data model provider. | should | `best-practice-building-data-models-for-dataspaces.md` §4, §5 |
| `DSSC-DMO-35` | Agreements on the use of existing models in the data space must be documented in the governance framework. | must | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-36` | Only if reusing existing models is not viable, a data space should create a new model reusing existing concepts from existing standards where possible. | should | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-37` | A data space that creates its own model needs to set up a data model management process itself. | must | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-38` | Setting up a data model management process involves setting guidelines for creating and maintaining data models. | must | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-39` | Setting up a data model management process involves establishing processes for resolving conflicts or inconsistencies. | must | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-40` | The development perspective — the design of data models as artifacts — should be taken into account, supported by a Vocabulary service. | should | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-41` | The governance perspective — the application and lifecycle management of the data models — should be taken into account, supported by a Vocabulary service. | should | `best-practice-building-data-models-for-dataspaces.md` §4 |
| `DSSC-DMO-42` | A vocabulary service can provide functionalities that enable users to generate a preliminary data model directly from their sample data, whether it is in CSV, JSON, or XML format. | may | `best-practice-building-data-models-for-dataspaces.md` §5 |
| `DSSC-DMO-43` | A data model generated bottom-up from sample data is not a formal standard. | informative | `best-practice-building-data-models-for-dataspaces.md` §5 |

## Explainers and best practices

Upstream nests one explainer beneath this building block, rendered in full below.

## Best practice: Building Data Models for dataspaces

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Data Models › Best practice: Building Data Models for dataspaces

Data models will differ for each dataspace and can even differ for various dataspace participants. Best practices are available for defining and managing these data models.

### 1. Key concepts

The explainer distinguishes between the following key concepts:

- **Data models**: a structured representation of data elements and relationships used to facilitate semantic interoperability within and across domains. Data models are vocabularies, ontologies, application profiles, and schema specifications that can be used to annotate and describe the datasets in the data offerings.
- **Data model management process**: The management process for creating, managing, and updating data models within data spaces. This is performed by a data model provider, an entity responsible for providing (creating, versioning, publishing and maintaining) the data model. This role is often fulfilled collectively by business communities and delegated to a Standards Development Organisation (SDO), or other consortia (e.g., W3C, OASIS) but can also be undertaken by a data space governance authority itself.
- **Vocabulary service**: A technical component providing facilities for publishing, editing, browsing and maintaining data models and related documentation. This service may also support the transition from more conceptual data models to technical data models that can be used in actual data exchange.

### 2. Building a data model for data spaces

Data space participants must semantically define the data in their offerings by using a standardised data model, agreed within the data space. Based on the governance of the data space, data model providers supply these data models. The data models are published and stored in a vocabulary service that enables data models to be discovered throughout a data space. This ensures that each dataset offered can be linked to a data model that describes its structure and semantics. As mentioned in the building block about Data, Service and Offerings Descriptions, this can be achieved by using the [DCAT-AP standard](https://semiceu.github.io/DCAT-AP/releases/3.0.0/). Each dataset or data service in DCAT can reference a data model in the vocabulary service using the property [`dcterms:conformsTo`](https://www.w3.org/TR/vocab-dcat-3/#Property:resource_conforms_to).

However, this is a challenge for federated data spaces, as data models need to be discovered across data spaces. By expressing data models in DCAT, data models can be discoverable across data spaces. Since data models are also just a piece of data, they can also be seen as data sets, which allows them to be cataloged and exchanged using the DCAT standard and the [Data Space Protocol](https://internationaldataspaces.org/offers/dataspace-protocol/), making them findable and accessible across data spaces. An example of this is provided in the first paper in the further reading list at the bottom of this building block.

#### 2.1 What is a data model?

There are **multiple abstraction layers** when it comes to data models. While semantic interoperability focuses on the meaning of **concepts**, technical interoperability is concerned with a specific **syntax**. These abstraction levels of data models transition from semantic to technical interoperability, with the latter detailing the precise representation that the exchanged data must adhere to.

It's important to note that not every data space needs to navigate through this complexity. Often, existing standards and their governance processes as provided by a data model provider can be reused. Additionally, service providers can facilitate the transition from semantic to technical interoperability.

This building block distinguishes between the following abstraction layer of a data model, where each layer consists of metadata about the shared data.

**Vocabulary**

Basic concepts and relationships expressed as terms and definitions within or across domains, typically described in a meta-standard such as Simple Knowledge Organization System (SKOS), a common data model for sharing and linking taxonomies, classification schemes, etc.

**Ontology**

Knowledge within and across domains by modelling information objects and their relationships, often expressed in open metamodel standards like OWL (Web Ontology Language), RDF (Resource Description Framework), or UML (Unified Modelling Language).

*More information and examples:* Ontologies define 'what' information plays a role within or across domains. It models information and its relations as information objects with properties/attributes and describes what the objects mean and how they relate to each other. Ontologies can be expressed in open metamodel standards like OWL, RDFS, UML, etc.

By providing a common data model and formalised relationships between entities, ontologies enable consistent interpretation of exchanged data between different systems and datasets.

In the context of the Semantic Interoperability Community (SEMIC) [1], this level would refer to a Core Vocabulary. This basic, reusable and scalable data specification captures an entity's fundamental characteristics and relations. Its main objective is to provide terms to be reused in the broadest possible context.

*Example.* This example defines an RDF Schema (a subset of the above-mentioned OWL), serialised as Turtle. This basic ontology describes houses, rooms, and addresses, where houses can have rooms and are associated with specific addresses.

```turtle
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>.
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix myhouse: <http://example.org/house#>.
# Concepts
myhouse:House rdf:type rdfs:Class; rdfs:comment "A residential building where people live."@en.
myhouse:Room rdf:type rdfs:Class; rdfs:comment "A room in a house."@en.
myhouse:Address rdf:type rdfs:Class; rdfs:comment "An address for a location."@en.
# Relationships
myhouse:hasRoom rdf:type rdf:Property; rdfs:comment "Indicates that a house has a room."@en; rdfs:domain myhouse:House; rdfs:range myhouse:Room.
myhouse:address rdf:type rdf:Property; rdfs:comment "Specifies the address of a house."@en; rdfs:domain myhouse:House; rdfs:range myhouse:Address.
```

[1] [Application Profiles: What are they and how to model and reuse them properly? A look through the DCAT-AP example. | Joinup (europa.eu)](https://joinup.ec.europa.eu/collection/semic-support-centre/application-profiles-what-are-they-and-how-model-and-reuse-them-properly-look-through-dcat-ap)

**Application Profile**

An application profile is a data model for applications that fulfill a particular use case. In addition to shared semantics, it also allows additional restrictions to be imposed, such as recording cardinalities or the use of certain code lists. An application profile can serve as documentation for analysts and developers.

*More information and examples — Description:* Application Profiles delve into the 'how' of information usage in system interactions. This level often involves customising one or more existing vocabularies (e.g., ontologies) for specific use cases or domains. This can be expressed in a SHACL, XSD, JSON Schema, and more.

In practice, an application profile may overlap with and build upon an ontology to specify the application of a particular ontology in a specific domain. Therefore, in this context, an application profile may reuse concepts of an ontology that is represented in a certain meta-standard (e.g., OWL). The application profile identifies mandatory, recommended, and optional elements, addresses specific application needs, and offers recommendations for the ontology's usage within a particular domain. This entails defining cardinalities, expected data types, and other constraints of existing classes and properties, which can be expressed in meta-standards such as SHACL, LinkML, XSD, JSON Schema, or Excel.

*Example.* This example adds upon the example specified beneath the ontology layer. Moreover, it includes defining cardinalities, expected data types, and other constraints in SHACL of existing classes and properties in the example of an ontology.

```turtle
# SHACL Shapes
@prefix sh: <http://www.w3.org/ns/shacl#>.
@prefix myhouse: <http://example.org/house#>.
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>.
myhouse:HouseShape rdf:type sh:NodeShape; sh:targetClass myhouse:House;
sh:property [ sh:path myhouse:hasRoom; sh:minCount 1; sh:message "Every house should at least consist of one room." ];
sh:property [ sh:path myhouse:address; sh:maxCount 1; sh:message "A house should have only one address." ].
```

**Data Schema**

Data exchange technology specific representation of the application profile, including the syntax, structure, data types, and constraints for the data exchange. These data schemas should be used during data exchange, as specified in the data exchange protocol outlined by the Data Exchange building block.

*More information and examples:* An ontology and a data schema serve different purposes and operate at different levels of abstraction. A data schema defines the data structure for a database or dataset, specifying the structure, data types, and constraints for storing and accessing data in a structured manner. Data schemas deal with the technical details of how the data is syntactically stored and exchanged, and they are usually expressed in metamodel standards like JSON Schema and XML Schema. Ontologies or application profiles (for specific application needs) operate at a higher abstraction level, specifying only the knowledge and relations within a particular domain.

Data schemas can represent some aspects of the knowledge captured in an ontology or an application profile, particularly regarding the data structure and cardinalities needed for data exchange. However, a data schema may not capture the full semantics of the domain represented in an ontology. Therefore, while they complement each other, they are not interchangeable and serve their own purposes. This ensures that the aforementioned layers are not independent but rather interconnected, building upon each other.

*Example.* This example of a JSON Schema defines the technical details like the data structure and cardinalities of the concepts described in the other examples above.

```json
{ "$schema": "https://json-schema.org/draft-07/schema",
  "$id": "https://example.org/house-v1.schema.json",
  "title": "HouseSchema",
  "version": "1.0",
  "description": "Schema for myhouse data.",
  "type": "object",
  "properties": { "address": { "type": "string" }, "hasRoom": { "type": "number" } },
  "required": ["address"] }
```

The above concepts and relationships come together in the conceptual model and its corresponding terms and definitions, which the source presents as *Figure 2* (not reproduced in the text). In general, all data models depicted have different purposes but they should be aligned between each other so that each representation of the same data model should be coherent.

In addition to the various abstraction levels of data models, it is important to note that each of these data models can also refer to specific datasets, such as reference datasets or code lists. These datasets help establish standards for describing data to be used in a specific field, such as metadata. Examples of reference datasets include code lists and authority tables, such as country codes, which provide a consistent way of describing data about countries.

### 3. Linking the data model to technical exchange

**Data schema incorporated in data exchange protocol**: In a data exchange protocol (e.g., REST API specification), a data schema defines the structure and format of data exchanged between clients and servers. This schema outlines the properties, types, and constraints of data fields. Incorporating a schema ensures data consistency, facilitates validation, enhances documentation, and ensures effective exchange between clients and servers. By making all abstraction layers accessible, the Vocabulary Service bridges the gap between semantic and technical interoperability, allowing the data schema to be retrieved for direct use in the data exchange protocol. This marks the transition from semantic interoperable towards technical interoperable for the actual data exchange compliant to the specified data models.

The source illustrates this with one example:

- For example, the 'Order message' data model, defined within the Smart Connected Supplier Network (SCSN) to exchange order data in a standardised manner, is incorporated into the data exchange protocol implemented by users to exchange data.
- In this case, the data exchange protocol within SCSN is a REST API specification that provides information on how an order (compliant with the Order message data model) can be exchanged.

### 4. Governing data models

Data spaces should make use of existing data models and the corresponding management process defined by the data model provider. For example, a data space can adopt standards from established organisations like ISO or GS1 and align with their existing governance processes. Agreements on the use of these models in the data space must be documented in the governance framework. Only if reusing existing models is not viable, a data space should create a new model reusing existing concepts from existing standards where possible. Only then, a data space needs to set up a data model management process itself. This involves setting guidelines for creating and maintaining data models, as well as establishing processes for resolving conflicts or inconsistencies, see the different life cycle stage in *Figure 2*. Two perspectives, supported by a Vocabulary service, should then be taken into account:

- **Development perspective**: Focuses on the design of data models as artifacts.
- **Governance perspective**: Focuses on the application and lifecycle management (*Figure 3*) of the data models.

Data models are living documents that evolve over time, passing through various lifecycle phases from development to termination. Governance of semantic standards is important to ensure they are technically sound, reliable, and adaptable to the changing needs of users. This includes decisions on initiating development work, approving changes in new versions, and managing a suitable release scheme. This is specifically for the data model provider, which is some cases is the data space, depending on whether data models are based on existing standards and their governance framework.

### 5. A bottom-up approach to create a data model

While data spaces should prioritise the reuse of existing data models, there are situations where no suitable models exist, which requires the data space to develop its own. The conventional method for this is the **top-down approach**, which starts with a formal data model that participants are expected to adopt. These models are typically created through open standardisation, meaning that they're created 'by the users, for the users'. However, this top-down approach can be challenging. It demands significant semantic expertise and the standardisation process is often time consuming. An alternative, more agile method is the **bottom-up approach**. This less formal path allows a data space to get started quickly, especially when participants have limited resources or knowledge of semantic technologies.

A bottom-up approach is particularly useful in emerging data spaces where the community is still forming and common standards have not yet been established. This approach allows participants to use their own data as the basis for creating an initial data model. To facilitate this, a vocabulary service can provide functionalities that enable users to generate a preliminary data model directly from their sample data, whether it is in CSV, JSON, or XML format. It is important to recognise that the resulting model is not a formal standard. Instead, it serves two valuable purposes:

- It acts as a practical starting point for mapping the data space's specific data elements to concepts in more common, existing data models.
- It provides a real world example that can guide and inform a future open standardisation process.

For example, energy communities can upload their own CSV or JSON files describing local energy production and consumption. A vocabulary service then derives a preliminary shared data model from these datasets, highlighting common concepts that can later be aligned with formal standards.

This bottom-up process can significantly accelerate the semantic interoperability within data spaces. Looking ahead, AI might streamline this even further, with the potential for tools that can automatically suggest mappings to existing concepts and further speed up the creation of interoperable data model.

### 6. Further reading

- Centre of Excellence of Data Sharing and Cloud: Paper on Establishing Semantic Interoperability across Data Space. This paper describes how data models can be findable, accessible and usable across data spaces.
- IDS RAM-4: Explaining the meaning for data models and their governance process.
- Reference datasets: EU reference datasets containing a consistent way to describe data. They are standardized and organized arrangements of words and phrases presented as alphabetical lists of terms or as thesauri and taxonomies with a hierarchical structure of broader and narrower terms.
- The ENERSHARE D3.3: European Common Energy Data Space Framework Enabling Data Sharing - Driven Across – and Beyond – Energy Services

## Tools implementing this building block

The source lists the following tools under "Tools implementing this building block", grouped by the service they implement. These are catalogue entries and illustration; the source attaches no requirement to using any of them.

| Tool | Service |
|---|---|
| SEMIC SHACL Validator (Unified Validator) | Value-Creation Services |
| SEMIC XML Validator | Value-Creation Services |
| Interoperability Test Bed | Value-Creation Services |
| Data Space Builder | Value-Creation Services |
| Ocean Enterprise Provider | Participant Agent Services |
| Nautilus Participant Agent | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| FIWARE Data Space Framework (FDF) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |
| Simpl-Open – Participant Agent | Participant Agent Services |
| Semantic Treehouse | Vocabulary |
| Smart Data Models | Vocabulary |
| AgroPortal | Vocabulary |
| OntoPortal | Vocabulary |
| Simpl-Open - Vocabulary Service | Vocabulary |
| Ocean Enterprise Catalogue and Aquarius Catalogue Cache | Catalogue |
| sovity Data Space Portal (DSPortal) | Catalogue |
| Simpl-Open - Catalogue | Catalogue |

## Open questions

> **Ambiguous:** The building block page states under "Specifications" that *"There are no mandatory specifications a dataspace shall follow for implementing this capability"*, and under "Capabilities" that defining a common data model is *not mandatory*. The nested best-practice explainer nevertheless uses unqualified `must`: *"Data space participants must semantically define the data in their offerings by using a standardised data model, agreed within the data space"* and *"Agreements on the use of these models in the data space must be documented in the governance framework"*. The source does not say whether the explainer's `must` is binding or is best-practice phrasing. `DSSC-DMO-21`, `DSSC-DMO-27` and `DSSC-DMO-35` are recorded with the force each statement carries in its own location; they are not reconciled here.

> **Ambiguous:** The building block glossary defines a Data Model as encompassing abstraction levels that *"may not need to be hierarchical; they can exist independently"*, while the explainer §2.1 concludes that *"the aforementioned layers are not independent but rather interconnected, building upon each other"*. The source does not resolve the tension.

> **Ambiguous:** Vocabulary service is described in the singular and as centralising *"all data models"* (building block §5), but the next sentence reads *"Each Vocabulary Service should provide an API"*, implying more than one per data space. Whether a data space has exactly one vocabulary service is not stated.

> **Gap — figures.** The source refers to *Figure 1* (co-creation questions, building block §3), *Figure 2* (conceptual model with terms and definitions, explainer §2.1; also cited in explainer §4 for *"the different life cycle stage"*) and *Figure 3* (lifecycle management, explainer §4). The figures themselves are not part of the text and are not reproduced here. *Figure 2* is additionally cited for two different things — the conceptual model and the lifecycle stages — which the text does not reconcile.

> **Gap — DCAT version.** The Implementation section requires metadata exchange *"using the DCAT standard"* without naming a version; the explainer links DCAT-AP release 3.0.0 and the DCAT 3 recommendation for `dcterms:conformsTo`. Whether plain DCAT, DCAT 3 or DCAT-AP 3.0.0 is intended in the Implementation section is not stated.

> **Gap — further reading citations.** The four further-reading items are given as titles only (CoE-DSC paper on Establishing Semantic Interoperability across Data Space; IDS RAM-4; EU reference datasets; ENERSHARE D3.3), without publication identifiers, versions or URLs.

> **Note — source typography.** The building block §3 contains several apparent typographic errors preserved verbatim above: *"explore the ability to extend and existing model"*, *"a data spaces requires a tool"*, *"The reusing of a data models"*, and in §4 *"setting-up ad managing data models"*. The list nesting in §3 is also inconsistent in the source: the factors affecting reuse and the meta-standard best practices each begin with an unbulleted line followed by bulleted siblings.
