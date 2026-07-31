# Data, Services, and Offerings Descriptions

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Value Creation Enablers › Data, Services, and Offerings Descriptions
> **Category** · Data Value Creation Enablers

This building block enables data providers in a data space to publish their data, services and offerings, and enables data users to assess the relevance of what is made available. It rests on high quality metadata — on the data content, the data representation, and the technical accessibility — which come together under the umbrella of a "data product". By providing metadata, potential data users can determine the suitability of the data product (from a functional and policy point of view, e.g. licensing conditions), how they can interpret the data (semantics) and how they can technically access the data product (APIs, security mechanisms, etc.).

## Scope and objectives

The objective of this building block is to:

- Enable data providers in data spaces to publish their data, services and offerings.
- Enable data users to assess the relevance of potential data, services and offerings being made available in a data space.

High quality metadata is necessary, in particular metadata on the data content, data representation, and technical accessibility. They come together under the umbrella of a "**data product**". A data product can be a dataset, a data service or even a large single file for bulk download. This is made available in the dataspace by a data provider.

Two cross-cutting principles are stated in scope:

- **Application of FAIR principles:** Metadata must adhere to the FAIR principles — Findability, Accessibility, Interoperability, and Reusability. Compliance ensures that data products and services remain accessible, understandable, and usable by the data space participants.
- **Customer-centric Approach:** Effective metadata should be designed with the end-user (e.g., data recipients and data user) in mind. Guidelines, processes, and tools for creating and maintaining these descriptions should also be adaptive and scalable to accommodate future changes.

### Co-creation question

For this building block, data space governance authorities need to address the following co-creation question:

> **What is the minimum set of metadata which needs to be provided for the (types of) data products provided in a data space?**

The Data Act, through article 33, provides a minimum set of metadata to be provided for each data product by data providers in a data space. The rulebook of a data space can provide further (domain specific) attributes for the (types of) data products shared in the data space. The outcomes need to be documented in the rulebook of the data space.

### Implementation relations

The source states that this building block relates to the **Participant Agent service** and the **Catalogue service, which is part of the Federation Services**.

## Capabilities

To achieve the objectives, participants in dataspaces need to have the following capabilities:

- **Creating Metadata:** mechanisms for creating metadata for describing data products.
- **Validating Metadata:** metadata needs to be checked for compliance with standards, the dataspace rulebook (which can provide domain specific requirements) and completeness.
- **Updating Metadata** and version control throughout the lifetime of the data product.

The Data Act, article 33, specifies the minimum set of metadata which every data provider shall provide for each data product. This includes:

- **Data content:** functional metadata on the scope of the data product, use restrictions, licences, the used data collection methodology, data quality and uncertainty.
- **Data structures, data formats, vocabularies, classification schemes, taxonomies and code lists** applied in the data product. This is explained in more detail in the Data Models building block.
- **The technical means to access the data**, such as application programming interfaces, and their terms of use and quality of service. This is explained in more detail in the Data Exchange building block.

The building block provides the foundation for creating, validating, and updating metadata of data products, services, and offerings description. The objective is to ensure that data products are discoverable, interoperable, governed, and trustworthy.

## Standards and protocols

Names and versions below are reproduced verbatim from the source, including its inconsistent capitalisation of profile names (see "Open questions"). "referenced" means the source names the item as an example or as context, without prescribing it.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| DCAT (W3C) | v3 | Baseline vocabulary for describing datasets and related resources in a structured, machine-readable manner; RDF classes and properties to describe and include datasets and data services in a catalogue; v3 expands cataloguing to other resources including dataset series | recommended |
| DCAT-AP (EU Profile) | 3.0 (the source cites "the DCAT-AP 3.0 specification"; also notes "DCAT and DCAT-AP are already available in version 3") | Application Profile of DCAT with mandatory fields and controlled vocabularies, ensuring metadata can be aggregated across Europe, such as http://data.europa.eu, and extensible to reflect specific domains; extends DCAT "with improved definitions, usage notes and usage constraints such as cardinalities for properties and the usage of controlled vocabularies" | recommended |
| FAIR principles | — | Findability, Accessibility, Interoperability, and Reusability; metadata must adhere to them | required |
| Data Act, article 33 | — | Specifies the minimum set of metadata which every data provider shall provide for each data product | required |
| SHACL (Shapes Constraint Language) | W3C standard | DCAT-AP usage constraints are technically implemented as SHACL shapes; used for validating metadata | recommended |
| ODRL (Open Digital Rights Language) | — | Metadata should incorporate policies using ODRL; specifies permissions, prohibitions, and duties linked to datasets; DCAT integrates ODRL to define rights associated with datasets and dataset services | recommended |
| DQV (Data Quality Vocabulary) | — | Standardised modelling patterns for facets of data quality; links DCAT datasets and distributions with quality information; expresses accuracy, completeness, timeliness, provenance | referenced |
| SKOS | — | DCAT incorporates properties and classes derived from it | referenced |
| RDF | — | Serialisation basis for DCAT | referenced |
| JSON-LD (JavaScript Object Notation for Linked Data) | — | Named as a possible substitute for RDF in the serialization of DCAT | referenced |
| StatDCAT-AP | — | Domain-specific application profile refining DCAT-AP; defines temporal resolution and units for statistical data | referenced |
| GeoDCAT-AP | — | Domain-specific application profile refining DCAT-AP for geospatial datasets; incorporates INSPIRE vocabularies | referenced |
| mobilityDCAT-AP / MobilityDCAT-AP | — (the source uses both spellings) | Extension of DCAT-AP for mobility data; describes transport datasets with DATEX II or NeTEx; enables integration and referencing of DATEX, SIRI, NETEX, and GTFS | referenced |
| healthDCAT-AP / HealthDCAT-AP | ongoing extension of DCAT-AP | Used by the European Health Data Spaces (EHDS); captures health-specific properties (legal basis, retention period, population coverage); enables referencing of ICD-10-CM, SNOMED CT, and Diagnosis-Related Groups (DRGs) | referenced |
| languageDCAT-AP | — | Contains the models and constraints for "language" information, i.e., which languages are used in the metadata | referenced |
| DCAT-AP-HVD | — | Imposes more stringent metadata under the Open Data Directive (ODD) for datasets designated as strategically important by the EU | referenced |
| BRegDCAT-AP | latest version: v2.1.0; v2.0 also cited | Application profile that further refines the respective versions of DCAT-AP; European Commission standard data model/specification for base registries access and interconnection | referenced |
| DCAT-AP-NO | v2.0 | National application profile specified by the Norwegian Digitalisation Agency (Digdir) for describing datasets and data directories in the public sector, for both open and non-open data; a refinement of BRegDCAT-AP v2.0 | referenced |
| DCAT-BE | — | National profile (Belgium) | referenced |
| DCAT-AP CH | — | National profile (Switzerland) | referenced |
| DCAT-AP DE | — | National profile (Germany) | referenced |
| FAIR Digital Objects (FDOs) | — | A complementary technical framework for data, services and offerings descriptions; metadata can also be represented as FDO records tied to persistent identifiers | referenced |
| ISO 11783 | — | Agriculture: technical metadata related to machine-to-machine communication | referenced |
| AgroVoc | — | Agriculture: domain-spanning unified ontology for agricultural concepts | referenced |
| DATEX / DATEX II | — | Mobility metadata standard | referenced |
| SIRI | — | Mobility metadata standard | referenced |
| NETEX / NeTEx | — (the source uses both spellings) | Mobility metadata standard | referenced |
| GTFS | — | Mobility metadata standard | referenced |
| ICD-10-CM | — | Health coding and classification standard | referenced |
| SNOMED CT | — | Health coding and classification standard | referenced |
| Diagnosis-Related Groups (DRGs) | — | Health coding and classification standard | referenced |
| GDPR | — | Named as a regulatory standard for conformance, and as a framework to align with when updating metadata | referenced |
| Open Data Directive (ODD) / Open Data Directives | — | Regulatory framework behind DCAT-AP-HVD; named as an alignment target when updating metadata | referenced |
| DGA | — | Named as a regulatory framework to align with when updating metadata | referenced |
| SPARQL | — | Endpoints facilitate querying across metadata repositories | referenced |
| Turtle, RDF/XML, Notation3, HTML-RDFa | — | RDF serialization formats metadata should be transformable into | referenced |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-DSO-01` | The building block must enable data providers in data spaces to publish their data, services and offerings. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-02` | The building block must enable data users to assess the relevance of potential data, services and offerings being made available in a data space. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-03` | High quality metadata on the data content is necessary. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-04` | High quality metadata on the data representation is necessary. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-05` | High quality metadata on the technical accessibility is necessary. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-06` | Metadata must adhere to the FAIR principles — Findability, Accessibility, Interoperability, and Reusability. | must | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-07` | Effective metadata should be designed with the end-user (e.g., data recipients and data user) in mind. | should | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-08` | Guidelines, processes, and tools for creating and maintaining these descriptions should be adaptive to accommodate future changes. | should | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-09` | Guidelines, processes, and tools for creating and maintaining these descriptions should be scalable to accommodate future changes. | should | `data-services-and-offerings-descriptions.md` §1 |
| `DSSC-DSO-10` | Participants in dataspaces need mechanisms for creating metadata for describing data products. | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-11` | Metadata needs to be checked for compliance with standards. | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-12` | Metadata needs to be checked for compliance with the dataspace rulebook (which can provide domain specific requirements). | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-13` | Metadata needs to be checked for completeness. | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-14` | Participants need the capability of updating metadata throughout the lifetime of the data product. | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-15` | Participants need version control for metadata throughout the lifetime of the data product. | must | `data-services-and-offerings-descriptions.md` §2 |
| `DSSC-DSO-16` | Every data provider shall provide, for each data product, functional metadata on the data content: the scope of the data product, use restrictions, licences, the used data collection methodology, data quality and uncertainty. | must | `data-services-and-offerings-descriptions.md` §2 (Data Act, article 33) |
| `DSSC-DSO-17` | Every data provider shall provide, for each data product, the data structures, data formats, vocabularies, classification schemes, taxonomies and code lists applied in the data product. | must | `data-services-and-offerings-descriptions.md` §2 (Data Act, article 33) |
| `DSSC-DSO-18` | Every data provider shall provide, for each data product, the technical means to access the data, such as application programming interfaces, and their terms of use and quality of service. | must | `data-services-and-offerings-descriptions.md` §2 (Data Act, article 33) |
| `DSSC-DSO-19` | Data space governance authorities need to address the co-creation question: what is the minimum set of metadata which needs to be provided for the (types of) data products provided in a data space? | must | `data-services-and-offerings-descriptions.md` §3 |
| `DSSC-DSO-20` | The rulebook of a data space can provide further (domain specific) attributes for the (types of) data products shared in the data space. | may | `data-services-and-offerings-descriptions.md` §3 |
| `DSSC-DSO-21` | The outcomes of the co-creation question need to be documented in the rulebook of the data space. | must | `data-services-and-offerings-descriptions.md` §3 |
| `DSSC-DSO-22` | DCAT (W3C) is a recommended standard, providing the baseline vocabulary for describing datasets and related resources in a structured, machine-readable manner. | recommended | `data-services-and-offerings-descriptions.md` §4; `best-practice-creating-and-maintaining-metadata.md` §1 |
| `DSSC-DSO-23` | DCAT-AP (EU Profile) is a recommended standard: an Application Profile of DCAT with mandatory fields and controlled vocabularies, ensuring that metadata can be aggregated across Europe, such as http://data.europa.eu, and extensible to reflect specific domains. | recommended | `data-services-and-offerings-descriptions.md` §4; `best-practice-creating-and-maintaining-metadata.md` §1 |
| `DSSC-DSO-24` | This building block relates to the Participant Agent service and the Catalogue service, which is part of the Federation Services. | informative | `data-services-and-offerings-descriptions.md` §5 |
| `DSSC-DSO-25` | There is no universally mandated minimal metadata schema. | informative | `explainer-metadata-in-data-spaces.md` §3 |
| `DSSC-DSO-26` | Data product providers are strongly encouraged to include metadata elements that facilitate discoverability, interoperability, usability, data quality, data governance, and regulatory compliance. | recommended | `explainer-metadata-in-data-spaces.md` §3 |
| `DSSC-DSO-27` | Baseline metadata for discoverability, usability, and interoperability includes dataset attributes: identifier, name, description, relation, creator/owner, contact information, timestamp, current version, language, publisher, and related datasets. | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 1 |
| `DSSC-DSO-28` | Baseline metadata includes distribution attributes: format, access URL, Download URL, and size. | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 2 |
| `DSSC-DSO-29` | Baseline metadata includes Data Service attributes: endpoint URL, endpoint description, serves data. | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 3 |
| `DSSC-DSO-30` | Baseline metadata includes regulatory compliance: conformance to regulatory standards (e.g., GDPR). | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 4 |
| `DSSC-DSO-31` | Baseline metadata for data governance, usability, and interoperability includes source (data lineage), access rights, rights, license, and conformance to standards, version history. | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 5 |
| `DSSC-DSO-32` | Baseline metadata includes data quality: accuracy, completeness, and consistency. | recommended | `explainer-metadata-in-data-spaces.md` §3 Table 1 row 6 |
| `DSSC-DSO-33` | Stakeholders in the data spaces may agree on a customized metadata specification based on factors such as domain-specific needs. | may | `explainer-metadata-in-data-spaces.md` §3 |
| `DSSC-DSO-34` | The metadata schema for value creation services currently aligns with that used for data services, encompassing attributes such as endpoint URLs, publishers, theme, and languages. | informative | `explainer-metadata-in-data-spaces.md` §5 |
| `DSSC-DSO-35` | Offering descriptions should be meticulously tailored to align with the technical and functional requirements of the intended end-users. | should | `explainer-metadata-in-data-spaces.md` §6 |
| `DSSC-DSO-36` | Both the data product provider and the data product consumer must adhere to specific protocols and standards to ensure interoperability and correct data usage. | must | `explainer-metadata-in-data-spaces.md` §7 |
| `DSSC-DSO-37` | The technologies referenced in Figure 1 are illustrative examples and are not prescriptive; alternative technologies may be employed (e.g., JSON-LD as a substitute for RDF in the serialization of DCAT). | informative | `explainer-metadata-in-data-spaces.md` §7 |
| `DSSC-DSO-38` | Metadata should incorporate policies using Open Digital Rights Language (ODRL), specifying permissions, prohibitions, and duties linked to datasets. | should | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-39` | More specific application profiles, addressing e.g. requirements of specific domains or national bodies, may be applicable. | may | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-40` | DCAT-AP usage constraints (cardinalities for properties, usage of controlled vocabularies) are technically implemented as SHACL shapes, used for validating metadata. | informative | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-41` | For datasets designated as strategically important by the EU, DCAT-AP-HVD imposes more stringent metadata under the Open Data Directive (ODD). | must | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-42` | The Data Quality Vocabulary (DQV) allows structured description of quality attributes; data product providers can express accuracy, completeness, timeliness, and provenance. | informative | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-43` | Metadata can also be represented as FDO (FAIR Digital Objects) records tied to persistent identifiers, supporting machine-readability, long-term persistence, and global resolvability. | may | `explainer-dcat-and-application-profiles.md` |
| `DSSC-DSO-44` | Metadata is created for datasets, dataset series, distributions, and data services, based on standards, with different standards applied depending on the domain and the type of resource being described. | recommended | `best-practice-creating-and-maintaining-metadata.md` §1 |
| `DSSC-DSO-45` | Validation ensures metadata is complete, accurate, and compliant with DCAT/DCAT-AP and ODRL. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-46` | Validation checks that all mandatory fields are present. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-47` | Validation checks that controlled vocabularies are used. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-48` | Validation checks that linked ODRL policies are consistent and machine … (the source sentence is incomplete). | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-49` | Run automated validation. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-50` | Perform manual review for clarity and usability. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-51` | Monitor evolving DCAT-AP versions and update practices accordingly. | recommended | `best-practice-creating-and-maintaining-metadata.md` §2 |
| `DSSC-DSO-52` | Establish a continuous update process for metadata, as metadata evolves with data and regulations. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-53` | Review periodically: check descriptions against current datasets, business operations, and standards. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-54` | Modify entries: revise fields, update examples, adjust access policies. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-55` | Validate accuracy: collect feedback from data consumers and incorporate corrections. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-56` | Ensure compliance: align with regulatory frameworks such as GDPR, Open Data Directives, DGA, sectoral rules. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-57` | Adopt new methods: update formats or descriptions when new vocabularies or APIs are introduced. | recommended | `best-practice-creating-and-maintaining-metadata.md` §3 |
| `DSSC-DSO-58` | Archive previous versions for audit and rollback. | recommended | `best-practice-creating-and-maintaining-metadata.md` §4 |
| `DSSC-DSO-59` | Document rationale (e.g., regulatory update, new sensor fee). | recommended | `best-practice-creating-and-maintaining-metadata.md` §4 |
| `DSSC-DSO-60` | Ensure only authorized audits are applied. (Source wording; see "Open questions".) | recommended | `best-practice-creating-and-maintaining-metadata.md` §4 |
| `DSSC-DSO-61` | User Interfaces: provide accessible tools that enable data providers to create, validate, and update metadata without directly interacting with RDF syntax. | recommended | `best-practice-creating-and-maintaining-metadata.md` §5 |
| `DSSC-DSO-62` | File Transformation: support the serialization of metadata into multiple RDF formats (e.g., Turtle, RDF/XML, Notation3, HTML-RDFa), preserving semantic integrity. | recommended | `best-practice-creating-and-maintaining-metadata.md` §5 |
| `DSSC-DSO-63` | File Storage: repositories manage the storage of DCAT files, maintain version history, and enforce access controls for metadata records. | recommended | `best-practice-creating-and-maintaining-metadata.md` §5 |
| `DSSC-DSO-64` | SPARQL Endpoints: facilitate querying across metadata repositories, enabling discovery, validation, and integration within and across data spaces. | recommended | `best-practice-creating-and-maintaining-metadata.md` §5 |
| `DSSC-DSO-65` | Each participant agent should incorporate the appropriate components for creating, validating, storing, and updating resource descriptions, in compliance with the application profile of the specific data space. | should | `further-reading-tools-frameworks-external-links.md` |

## Explainers and best practices

### Explainer: Metadata in Data Spaces

**On the Significance of Metadata in Data Spaces.** Metadata — the structured and standardized information that describe data products and services — creates demonstrable value in a data space by strengthening discovery, interoperability, and governance.

- *Discovery:* rich descriptors such as titles, thematic keywords, temporal coverage, and access endpoints allow catalogues to index data products precisely, so that both human users and software agents can locate the relevant data or services quickly and reliably.
- *Interoperability:* metadata captures common vocabulary, data models, formats, licensing terms, giving independently built systems a common reference frame; this minimises bespoke mappings, accelerates integration, and reduces error rates when combining heterogeneous sources.
- *Governance:* metadata records provenance — lineage, version history, quality metrics — alongside machine-readable usage policies and accountability links stewards, enabling automated enforcement of contractual and regulatory obligations, supporting transparent audits, and maintaining data provider control over data sovereignty.

Together these functions ensure that data products remain discoverable, technically interoperable, and legally trustworthy as it scales.

**Data Product Metadata.** Data products are data sharing units, packaging data and metadata, and any associated license terms. The metadata description of data products covers various aspects of datasets and its associated elements including data services and policies. A dataset refers to a structured collection of data, which can exist in multiple distributions based on how it is serialized for transfer, sharing, or storage. Each distribution could be in a specific format (e.g., JSON) and optimized for particular use cases or technical requirements. A very large dataset can be divided into multiple datasets — known collectively as a dataset series — for better manageability. The datasets in a series share common characteristics. A high-quality description of a dataset is essential, as it must comprehensively capture all these aspects.

A data service provides operations for the selection, extraction, combination, processing, or transformation of datasets, which may be hosted locally or remotely. The result of any request to a data service is a representation of a part or all of a dataset. The service may be linked to specific datasets, or its source data may be configured dynamically at request- or run-time. The **description of a data service** plays a critical role in ensuring that the service can be discovered and effectively used into the data spaces. The service description clarifies how the data is accessed, transformed, and returned, providing all the essential details needed for the service to be invoked correctly.

**Minimum Metadata Requirement (MMR).** Data spaces catalogues may need a wide variety of metadata that cover various aspects of data products including descriptiveness, structural, administrative, legal, technical, usage, and quality. Unlike conventional data ecosystems — where descriptive, structural, and usage metadata suffice as a minimal set — data spaces as advanced, collaborative, decentralized ecosystems demand a more comprehensive metadata model. This is essential to enable interoperable and trusted routing of data products both within and across data spaces.

While there is no universally mandated minimal metadata schema, data product providers are strongly encouraged to include metadata elements that facilitate **discoverability**, **interoperability**, **usability**, **data quality**, **data governance**, and **regulatory compliance**. The minimum metadata requirement presented in the table are intended as recommendations. However, stakeholders in the data spaces may agree on customized metadata specification based on the factors such as domain-specific needs.

| | Metadata Dimensions | Attributes |
|---|---|---|
| 1 | Discoverability, usability, and interoperability | Dataset attributes include identifier, name, description, relation, creator/owner, contact information, timestamp, current version, language, publisher, and related datasets. |
| 2 | | Distribution attributes include format, access URL, Download URL, and size |
| 3 | | Data Service attributes include, endpoint URL, endpoint description, serves data |
| 4 | Regulatory compliance | Conformance to regulatory standards (e.g., GDPR) |
| 5 | Data governance, usability, and interoperability | Source (data lineage), access rights, rights, license, and conformance to standards, version history |
| 6 | Data quality | Accuracy, completeness, and consistency |

*Table 1: baseline set of metadata attributes recommended for all data products.*

> **Note on the table as published:** rows 2 and 3 carry no value in the "Metadata Dimensions" column in the source; they continue row 1's dimension. The source table's header row and row 1 are also misaligned by one cell upstream.

**Sectorial Data product Metadata.** Sector-specific metadata extends the common, cross-domain descriptors (identifier, title, license, provenance, temporal-spatial coverage) with elements that capture the semantics, constraints and regulatory contexts unique to a particular domain. The following examples illustrate current practices:

- Data spaces in the **agriculture** sector may include metadata describing crop species, parcel geometry and agro-environmental indicators. They often rely on different standards such as ISO 11783 for technical metadata related to machine-to-machine communication, and the AgroVoc vocabulary, which provides a domain spanning unified ontology for agricultural concepts.
- **Mobility** data spaces may include metadata such as route topology, vehicle attributes and real-time service status, traffic and travel information, and geographic location. MobilityDCAT-AP is the most recent extension of DCAT-AP, providing precise and unambiguous metadata specifications for mobility related data products. It enables the integration and referencing of widely adopted European and international mobility-specific metadata standards, including DATEX, SIRI, NETEX, and GTFS.
- Metadata for **Health** data products may include clinical codes, applicable legislation, analytical context, geographical coverage, health theme, and consent terms. Standard vocabularies offered by healthDCAT-AP — an ongoing extension of DCAT-AP for describing health data products — are used by the European Health Data Spaces (EHDS). healthDCAT-AP enables the referencing of healthcare coding and classification standards such as ICD-10-CM, SNOMED CT, and Diagnosis-Related Groups (DRGs).

Additionally, other data spaces — such as those in **Energy**, **Cultural-heritage, the Green Deal, and Finance** — use sector-specific vocabularies to describe their data products. These sector-tailored descriptors make data products discoverable through domain vocabularies. However, some of these sector-specific vocabularies are still under development or not yet formally standardized. For example, energy data spaces currently rely on heterogeneous vocabularies, which require semantic alignment and standardization through adoption of application profile (DCAT-AP) and its sector-specific extensions.

**Service Description.** In data spaces, technical services are categorized into participant agent services, federated services, and value creation services. Value creation services, which are published in service catalogs, may include various technical and support services such as software, platforms, infrastructure, security solutions, communication tools, and managed services. These services are designed to support critical operations, including enhancing data quality, performing advanced analytics, and enabling visualization.

The description of value creation services relies on metadata that captures essential technical and operational attributes. These metadata elements cover general information, access details, governance and compliance requirements, lifecycle management processes, and relationships to other services or datasets. Currently, the metadata schema for value creation services aligns with that used for data services, encompassing attributes such as endpoint URLs, publishers, theme, and languages.

**Offerings Description.** An offering consists of data products, services, or a combination of both, accompanied by a comprehensive offering description. The offering descriptions include attributes such as a detailed overview, provider information, creator identity, pricing model, licensing terms, current and previous versions, and structural details. It also specifies applicable rights and obligations, as well as the methods through which data products and services can be accessed or procured. Offerings are organized and presented within catalogs to facilitate efficient discovery by data recipients.

**Use Case Scenario.** The scenario (Figure 1 upstream) focuses on the interaction between the **data product provider** and the **data product consumer**. The data product provider is responsible for creating, managing, and publishing metadata for data products, services, and offerings. These are made available to the data product consumer, who may be an individual, organization, or system that consumes or utilizes the data and services for specific purposes.

The technologies referenced in the figure serve as illustrative examples and are not prescriptive; in practical implementations, alternative technologies may be employed (for instance, JSON-LD can be used as a substitute for RDF in the serialization of DCAT).

The scenario begins with the data product provider creating metadata for data products, services, and offerings using the DCAT. The data product provider may also establish policies (using languages like ODRL) to define access, usage rights, and other contract terms. The data recipient then interacts with the published data products and services based on these metadata descriptions — searching, discovering and accessing relevant datasets or services, depending on the terms set by the provider; interactions might include querying datasets, invoking data services, or downloading data in specific formats. Throughout this process, both parties must adhere to specific protocols and standards to ensure interoperability and correct data usage; for example, the provider might use Shapes Constraint Language (SHACL) to validate the metadata, and the recipient ensures compliance with the usage policies outlined in the metadata and may provide feedback to the provider about data quality.

> **Note:** the figure itself is not reproducible from the source text; only the narrative above is available.

### Explainer: DCAT and Application Profiles

The specifications' governance scheme is an organised framework that offers the fundamental protocols, standards, and other technologies needed to create, oversee, and maintain building blocks. The list of standards used to create the building blocks for data, services, and offering descriptions is:

- **DCAT v3:** The DCAT enables a publisher to describe datasets and data services in a catalogue using a standard model and vocabulary that facilitates the consumption and aggregation of metadata from multiple catalogues. DCAT offers RDF classes and properties to describe and include datasets and data services in a catalogue. With DCAT v3, there is an expanded capability to catalogue datasets and other resources, including dataset series. DCAT incorporates properties and classes derived from established standards such as SKOS, ODRL, and DQV. The integration of ODRL is pivotal within this building block, as it explicitly defines the relevant rights associated with resources such as datasets and dataset services. Furthermore, the DQV provides standardized modeling patterns for various facets of data quality; it facilitates the linking of DCAT datasets and distributions with diverse types of quality information.
- **The basis for data spaces: DCAT-AP:** DCAT-AP is an application profile of DCAT (cf. the Data Models building block for a definition), initially specified by the European Commission for public sector datasets in Europe, now, more generally aiming at "a minimal common basis within Europe to share Dataset and Data Services cross-border and cross-domain" (cf. the DCAT-AP 3.0 specification). Where DCAT simply provides a vocabulary in the form of an ontology, DCAT-AP extends it "with improved definitions, usage notes and usage constraints such as cardinalities for properties and the usage of controlled vocabularies". Technically, these are implemented as SHACL shapes, i.e., in the Shapes Constraint Language used for validating metadata.
- **More specific application profiles:** As "application profiling" is a general mechanism, even more specific application profiles may be applicable, addressing, e.g., requirements of specific domains or national bodies. Domain-specific application profiles refining DCAT-AP include StatDCAT-AP for statistical datasets, GeoDCAT-AP for geospatial datasets, and mobilityDCAT-AP for mobility data. As an example of a national application profile, the Norwegian Digitalisation Agency (Digdir) specified DCAT-AP-NO v2.0 as a standard for describing datasets and data directories in the public sector for both open and non-open data. DCAT-AP-NO is a refinement of BRegDCAT-AP v2.0, the European Commission's standard data model/specification for base registries access and interconnection, where base registries are "authoritative databases and a trusted source of basic information on data items such as people, companies, vehicles, licences, buildings, locations and roads".
- **BRegDCAT-AP** (latest version: v2.1.0) is an application profile that further refines the respective versions of DCAT-AP. (Footnote: the more specific an application profile, the less up-to-date it may be, as seen from these version numbers, while DCAT and DCAT-AP are already available in version 3.)
- **National Profile:** Member states developed national application profiles such as DCAT-BE (Belgium), and DCAT-AP CH (Switzerland). DCAT-AP DE (Germany), ensuring metadata is consistent and interoperable across different regions with the EU.
- **Sectoral Profile:** Sector-specific extensions define metadata requirements tailored to particular sector.
  - mobilityDCAT-AP: describes transport datasets with DATEX II or NeTEx.
  - StatDCAT-AP: defines temporal resolution and units for statistical data.
  - GeoDCAT-AP: incorporates INSPIRE vocabularies for geospatial data.
  - HealthDCAT-AP: captures health-specific properties (legal basis, retention period, population coverage).
  - languageDCAT-AP: contains the models and constraints for "language" information, i.e., which languages are used in the metadata.
  - DCAT-AP-HVD: For datasets designated as strategically important by the EU, DCAT-AP-HVD imposes more stringent metadata under the Open Data Directive (ODD). For example, a real-time dataset of electric vehicle changing stations must include machine-readable formats, clear licensing, update frequency, and geolocation — ensuring it is immediately usable for both citizens and commercial applications across Europe.
- **Data quality with DQV:** The Data Quality Vocabulary (DQV) allows structured description of quality attributes. Data product providers can express accuracy (e.g., traffic speed measurements ±3 km/h), completeness (e.g., 90% of stations reporting hourly), timeliness, and provenance. Including these attributes enables to assess whether the data is suitable for critical applications.
- **Policies with ODRL:** Metadata should incorporate policies using Open Digital Rights Language (ODRL). It specifies permissions, prohibitions, and duties linked to datasets. For example, an electric vehicle charging dataset may require attribution to the original publisher.
- **FAIR Digital Objects (FDOs):** A complementary technical framework for data, services and offerings descriptions. Metadata can also be represented as FDO (FAIR Digital Objects) records tied to persistent identifiers. Supports machine-readability, long-term persistence, and global resolvability.

This integration of standards, quality vocabularies, rights languages, and persistent identifiers, ensures that governance and compliance requirements are embedded directly in metadata and can be interpreted by both humans and machines.

> **Note on structure as published:** the list mixes bullet levels upstream — the "Sectoral Profile" bullet is followed by an un-indented `mobilityDCAT-AP` line and then by sibling bullets for the remaining profiles. The nesting shown above reflects the evident intent; no wording was changed.

### Best practice: Creating and Maintaining Metadata

**Creating Metadata.** Metadata is created for datasets, dataset series, distributions, and data services, based on standards. Different standards are applied depending on the domain and the type of resource being described.

*Recommended Standards*

- DCAT (W3C): Provides the baseline vocabulary for describing datasets and related resources in a structured, machine-readable manner.
- DCAT-AP (EU Profile): Extends DCAT with mandatory fields and controlled vocabularies, ensuring that metadata can be aggregated across Europe through platforms such as http://data.europa.eu

**Validating Metadata.** Validation ensures metadata is complete, accurate, and compliant with DCAT/DCAT-AP and ODRL.

*Tools:* DCAT Validator (`http://www.dcat.be/validator/`) and DCAT-AP Validator (`https://www.itb.ec.europa.eu/shacl/dcat-ap/upload`)

*Checks Performed:*

- All mandatory fields present.
- Controlled vocabularies used
- Linked ODRL policies are consistent and machine

*Process:*

- Run automated validation.
- Perform manual review for clarity and usability.
- Monitor evolving DCAT-AP versions and update practices accordingly

**Updating Metadata.** Metadata evolves with data and regulations. Establish a continuous update process:

- Review periodically: Check descriptions against current datasets, business operations, and standards.
- Modify entries: Revise fields, update examples, adjust access policies.
- Validate accuracy: Collect feedback from data consumers and incorporate corrections.
- Ensure compliance: Align with regulatory frameworks such as GDPR, Open Data Directives, DGA, sectoral rules.
- Adopt new methods: Update formats or descriptions when new vocabularies or APIs are introduced.

**Version Control & Documentation.** Robust version control ensures transparency, accountability, and data integrity:

- Archive previous versions for audit and rollback.
- Document rationale (e.g., regulatory update, new sensor fee).
- Ensure only authorized audits are applied.

**Supporting Functionalities and System Components.** To complement the core functions of creating, validating, and updating metadata, the framework incorporates several supporting functionalities and system components:

- **User Interfaces:** Provide accessible tools that enable data providers to create, validate, and update metadata without directly interacting with RDF syntax.
- **File Transformation:** Support the serialization of metadata into multiple RDF formats (e.g., Turtle, RDF/XML, Notation3, HTML-RDFa). Transformation processes ensure interoperability while preserving semantic integrity.
- **File Storage:** Repositories manage the storage of DCAT files, maintain version history, and enforce access controls for metadata records.
- **SPARQL Endpoints:** Facilitate querying across metadata repositories, enabling discovery, validation, and integration within and across data spaces.

The page cross-references the *Governance Scheme of Specifications*, which upstream resolves to *Explainer: DCAT and Application Profiles* (see "Open questions").

### Further reading: tools & frameworks, external links

This sub-page is illustration, not requirement: it names existing tools that "may serve as an inspiration and/or a base for adaptations/extensions". It generates no requirement rows.

**Tools and frameworks**

- **DCAT-AP Editor:** a web-based editor designed for creating and editing DCAT-AP metadata, providing a user-friendly interface for generating valid DCAT-AP metadata descriptions for datasets. BRegDCAT-AP Tools is an example of an existing solution that offers a DCAT editor.
- **Libraries for Metadata Creation:** programming libraries simplify the creation, management, and handling of DCAT metadata by providing tools for working with RDF data. In Python, `rdflib` is widely used to handle RDF data. For JavaScript developers, `RDFLib.js` serves as a library for building web applications that interact with DCAT metadata, in browser-based or Node.js environments.
- **SHACL-based Validation Tools:** SHACL (Shapes Constraint Language) is a W3C standard designed for validating and constraining RDF (Resource Description Framework) data against a set of defined "shapes" or constraints. SHACL shapes can be used to define constraints for DCAT elements, ensuring that datasets, distributions, and services in a catalog are described accurately. For example, a SHACL shape can enforce that every `dcat:Dataset` must have a `dct:title`, `dct:description`, and at least one `dcat:Distribution`. Tools and libraries that leverage SHACL include pySHACL, SHACL.js, RDF4J SHACL.
- **DCAT-AP Validator:** allows developers to validate DCAT-AP (DCAT Application Profile) metadata to ensure compliance with the standard. Web-based DCAT validator solutions offer a service for validating DCAT files.
- **Frameworks and Triple Stores:** DCAT, being built on RDF, relies on RDF-compatible technologies. Apache Jena is a Java-based framework providing tools for storing, querying, and manipulating RDF data. Blazegraph is an open-source RDF store that supports SPARQL queries, used for managing and querying DCAT datasets.
- **DCAT-AP Extension Libraries:** DCAT-AP is easily extensible to any particular domain and is in line with the guidelines. Some programming languages offer libraries or frameworks providing APIs for programmatically generating, parsing, and validating DCAT-AP metadata; examples include libraries for Python, Java, and JavaScript. DCAT-AP is also natively supported by CKAN as well as Piveau.
- **DCAT-AP reuse guideline:** guidelines for creating new DCAT-AP profiles (DCAT-AP reuse guidelines).

**External links**

- **BREG-DCAT Creator:** enables public administrations to describe base registries via a user-friendly web form and export in BRegDCAT-AP v2 format.
- **BREG DCAT mapping tool:** supports alignment of registry data models across jurisdictions with standards such as BRegDCAT-AP 2.0.
- **FRICTIONLESS:** an open-source toolkit for data packaging and interoperability. Its core specification, data package, provides a simple format for bundling and describing collections of data files.
- **The Open Data Product Specification (ODPS):** defines machine-readable data product descriptions based on JSON Schema.
- **CKAN:** an open-source platform for managing and publishing DCAT-compliant metadata, offering interfaces for catalogue creation, metadata management, discovery, and access control.
- **SODA 2.0:** a standardised API for open data services, allowing catalogues to retrieve datasets and metadata consistently via the DCAT API.

## Glossary

Terms as defined on the building block page. Definitions are not requirements and carry no requirement IDs.

| Terms | Definition |
|---|---|
| Data space | Interoperable framework, based on common governance principles, standards, practices and enabling services, that enables trusted data transactions between participants. |
| Data Space Participant | A party committed to the governance framework of a particular data space and having a set of rights and obligations stemming from this framework. Explanatory text: Depending on the scope of the said rights and obligations, participants may perform in (multiple) different roles, such as: data space members, data space users, data space service providers and others as described in this glossary. |
| Data Space Intermediary | A data space intermediary is a service provider who provides an enabling service or services in a data space. In common usage interchangeable with 'operator'. |
| Service Description | A service description is composed of attributes related to data services, including endpoint description and endpoint URL. Additionally, it may encompass a wide range of attributes related to value-added technical- and support services such as software-, platform-, infrastructure-, security-, communication-, and managed services. These services are used for various purposes, such as data quality, analysis, and visualisation. |
| Dataset Description | A description of a dataset includes various attributes, such as spatial, temporal, and spatial resolution. The description encompasses attributes related to distribution of datasets such as data format, packaging format, compression format, frequency of updates, download URL, and more. These attributes provide essential metadata that enables data recipients to understand the nature and usability of the datasets. |
| Offering | Data product(s), service(s), or a combination of these, and the offering description. Explanatory text: Offerings can be put to a catalogue. |
| Offering Description | A text that specifies the terms, conditions and other specifications, according to which an offering will be provided and can be consumed. Explanatory text: Offering descriptions contain all the information needed for a potential consumer to make a decision whether to consume the data product(s) and/or the service(s) or not. This may include information such as description, provider, pricing, license, data format, access rights, etc. The offering description can also detail the structure of the offering, how data products and services can be obtained, and applicable rights and duties. Typically offering descriptions are machine-readable metadata. |

## Tools implementing this building block

The building block page carries a directory of third-party tools, each tagged with the service category it implements. This is a vendor listing — illustration, not requirement — and generates no requirement rows. Tool names and their categories, as listed:

| Tool | Category as tagged upstream |
|---|---|
| Fair Data Publisher | Data Plane |
| NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. | Trust Service |
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
| Data Space Builder | Value-Creation Services |
| Ocean Enterprise Catalogue and Aquarius Catalogue Cache | Catalogue |
| sovity Data Space Portal (DSPortal) | Catalogue |
| Simpl-Open - Catalogue | Catalogue |

## Open questions

- **Truncated sentence in the validation checks.** The best-practice page lists as a check performed: "Linked ODRL policies are consistent and machine". The sentence ends there in the source; the intended predicate (plausibly "machine-readable") is not stated. `DSSC-DSO-48` reproduces the fragment rather than completing it.
- **"Ensure only authorized audits are applied."** In the Version Control & Documentation section, this reads as though a word is wrong — the surrounding bullets concern archiving versions and documenting rationale, i.e. changes, not audits. The source is reproduced as written (`DSSC-DSO-60`).
- **"new sensor fee".** In the same section, "Document rationale (e.g., regulatory update, new sensor fee)". Reproduced verbatim; the intended word is not determinable from the source.
- **Inconsistent capitalisation of application profile names.** The source writes `mobilityDCAT-AP` (Explainer: DCAT and Application Profiles) and `MobilityDCAT-AP` (Explainer: Metadata in Data Spaces); likewise `healthDCAT-AP` and `HealthDCAT-AP`. Both spellings are preserved where they occur. It is not determinable which is canonical for this blueprint.
- **Inconsistent mobility standard names.** `DATEX` and `DATEX II`, `NETEX` and `NeTEx` both appear. Preserved as written in each location.
- **DCAT-AP-NO as "a refinement of BRegDCAT-AP v2.0".** The source states that DCAT-AP-NO v2.0 refines BRegDCAT-AP v2.0, while also stating that BRegDCAT-AP refines DCAT-AP. The relationship as stated is reproduced without correction.
- **DCAT-AP version.** The source names "the DCAT-AP 3.0 specification" and observes that "DCAT and DCAT-AP are already available in version 3", but the "Recommended Standards" list in the building block page and in the best-practice page names DCAT-AP with no version at all. No single version is stated as the required one.
- **DCAT-AP described differently in two places.** The building block page says DCAT-AP is an "Application Profile of DCAT with mandatory fields and controlled vocabularies"; the best-practice page says it "Extends DCAT with mandatory fields and controlled vocabularies". Rendered as they stand.
- **Broken cross-reference title.** The best-practice page ends with "See also Governance Scheme of Specifications", linking to the page whose own title is *Explainer: DCAT and Application Profiles*. The two names are not reconciled upstream.
- **Recommended vs. mandated metadata.** The building block page states that the Data Act article 33 minimum set is what every data provider *shall* provide, while the metadata explainer states there is "no universally mandated minimal metadata schema" and that its Table 1 is "intended as recommendations". Both statements are rendered with their own force (`DSSC-DSO-16`–`18` as `must`; `DSSC-DSO-25`–`32` as `informative`/`recommended`). The source does not reconcile them.
- **Table 1 is misaligned in the source.** Its header row declares three columns while row 1 supplies three values and rows 2–3 supply two, leaving the "Metadata Dimensions" cell empty for the continuation rows. Rendered with the continuation cells left empty rather than inferring dimension labels.
- **Figure 1 is not reproducible.** The "Use Case Scenario" section refers to a figure that is not available as text; only the accompanying narrative is rendered.
- **A normative statement inside an otherwise illustrative sub-page.** "Further reading: tools & frameworks, external links" is a list of named tools and external links — illustration, not requirement — but it contains one genuine obligation: "Each participant agent should incorporate the appropriate components for creating, validating, storing, and updating resource descriptions, in compliance with the application profile of the specific data space." It is recorded as `DSSC-DSO-65`. The test applied here is whether a sentence states an obligation, not which page it sits on; the rest of that sub-page generates no requirement rows.
