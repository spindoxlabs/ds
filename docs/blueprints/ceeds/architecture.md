# Proposed Architecture for CEEDS

> **Source** · Blueprint of the Common European Energy Data Space (CEEDS), v3.0, September 2025 › 4. Proposed Architecture for CEEDS
> **Includes** · 4.1. Components of the Data Space Federated Side
> **Figures** · Figure 11 — *Exchange of energy-related data among different data platforms (as data space participants)* · Figure 12 — *Complete CEEDS architecture*

This chapter describes the architecture proposed to realize the CEEDS. It takes the existing
solutions for energy data exchange as a starting point and describes "the necessary adaptations
to realize the CEEDS through implementing the proposed energy data space infrastructure". The
structural claim of the chapter is that the energy data space is "the combination of (1) multiple
'distributed data exchange platforms' with (2) overarching layers defined as the 'federated data
space' orchestration framework (centralized or distributed)". Section 4.1 then decomposes the
federated side into individual components and states, for each, the building block it is
associated with.

> **Note on headings** · The source numbers only one subsection in this chapter (4.1). The
> headings below for the unnumbered body of chapter 4 are an editorial grouping of that body;
> where a heading quotes the source, the quotation marks are the source's own emphasis. Section
> 4.1 and its component list carry the source's own names.

## Basis of the proposed architecture

The reference BUCs for CEEDS, described in Section 3 of the source document, "are based on an
ecosystem of data spaces (following the approaches presented in section 2.1) that is strictly
necessary to deploy regulated and efficient exchange of energy-related data". The BUC scenarios
"exploit the availability of data and services, indexed, and discovered in the data spaces
catalogues, to operate the energy services". Implementing the data space approach "allows,
moreover, to enlarge the set of involved actors as active participants in the energy systems
operations, with socio-economic benefits (in terms of monetary savings as well as the quality of
the services and reliability of electricity distribution) for every actor of the energy value
chain".

The data spaces ecosystem "will not be constructed entirely from scratch". It "will constitute an
extension and enhancement of the prevailing data exchange ecosystem, which presently operates in
isolation in countries with very limited pan-European interconnections". The objective is "to
establish a data infrastructure that facilitates the seamless and equitable exchange of data at
pan-European level, transcending local barriers and limitations".

The proposed model "corresponds to the creation of an energy data space as the combination of
(1) multiple 'distributed data exchange platforms' with (2) overarching layers defined as the
'federated data space' orchestration framework (centralized or distributed)". This approach
"reflects the concept of DERA 3.0 (Data Exchange Reference Architecture 3.0), which has been
defined in the Bridge Data Management WG based on SGAM".

## (1) The "distributed data exchange platforms" layer

The layer "refers to data platforms (including the already existing ones), either associated with
(i) regulated infrastructures or (ii) unregulated actors and entities, in line with the key
applications and functions defined in the SGAM".

| Category | Examples given by the source |
|---|---|
| Regulated data exchange platforms | "grid control room platforms – such as EMS and ADMS - market platforms, meter data hubs and flexibility registers" |
| Unregulated actors and entities | "DERMS, VPP, Charging Point Management, Community Energy Management, DER Technical Aggregators, Building Energy Management" |

These existing platforms "are already capturing and persisting their own data, which is usually
inputted into tailored applications; they are typically operated by energy stakeholders that
assume the roles of actors as presented in the BUCs scenarios, each data exchange platform
behaving as data providers and/or data consumers". The set of energy stakeholders "typically
include all actors defined through the HEMRM; namely, among many others: DSOs, TSOs, market
operators, OEMs, energy communities, charge point operators, customers, BRPs and BSPs". "Since
different data space participants are associated with different data exchange platforms, the
CEEDS guarantees data exchange among them."

### Endpoints for energy-related data

The endpoints "correspond to entities that act as sources and/or receivers of data", for example:

- "field devices that provide real-time measurements (sensors, voltage and current transformers,
  PMUs, RTUs, smart metering devices and embedded dedicated measurement devices) and receive
  actuating commands, scheduled operational setpoints or price-based transactive controls (IEDs,
  tap-changers, switching devices, behind-the-meter DERs)"
- "SCADA, EMS and ADMS infrastructures that contains real-time databases and forecasts data"
- "inputs from prosumers regarding the loads schedule, EVs and DERs actual and forecasted power
  consumption and generation"

"These data are bidirectionally exchanged with the distributed data ecosystems via the existing
communication infrastructures, which accommodate different technologies such as 5G, LTE, fiber
optics, PLC, secured internet, etc."

### Data management approaches observed in Member States

Existing strategies for data management "are described by two significant sources: the TSO-DSO
Data Management Report and the GEODE Data Management Fact Sheet". The latter "extensively
explores the implications of adhering to Article 23 of Directive (EU) 2019/944, which delegates
the responsibility for shaping the approach to data management for energy services to Member
States". The strategies result in "three primary architectural approaches observed in numerous
Member States, often applied in parallel for different types of data (i.e., from different sectors
or applications)". These are presented by the source as observed models, not as requirements.

| Model | Description (source) | Examples named |
|---|---|---|
| a) **decentralized model** | "data remains at its point of origin (e.g., metering information at DSO, contract information at the supplier and generation for DER). Collaborative efforts among market actors are underway to establish standardized market communication and exchange data, either with explicit consent from the data subject or within clearly defined business processes." | "Austria (EDA), the German market communication, and France" |
| b) **centralized model** | "involves a data hub that receives and stores data. All business processes operate within this hub, and outcomes are transmitted back to its clients. This model is managed and developed by a specific entity or service provider, with market participants utilizing its functionalities." | "Finland and Estonia" |
| c) **hybrid model** | "combines elements from both previous models. While all market participants can communicate in a decentralized manner, specific central structures are employed in certain use cases (e.g., compliance monitoring or facilitating access to data brokerage)." | Spain — "data remains with the DSO as the 'metered data administrator,' and access for end customers and third parties is facilitated through the AELEC-operated DataDis" |

## (2) The "Federated Data Space" side

The federated side "refers to where data is indexed, making it discoverable and providing a sort
of marketplace for sharing (and, possibly, trading) both data and data services". "In doing so,
the data space will rely on multiple actors and data platforms (the previously described ones, in
the distributed data ecosystems side) federating through the data space connectors and offering
their data under pre-recorded policies, verified credentials, data models and contractual
agreements." The federated data space side "includes a set of components to implement foundational
building blocks that perform the required functionalities of the data space"; those components are
the subject of section 4.1.

## Figure 11 — Exchange of energy-related data among different data platforms (as data space participants)

Rendering of the figure's content. Enclosing frame: **Common European Energy Data Space
Infrastructures**.

**Federated Data Space Layers (centralized or distributed)**

| Element | Label as shown |
|---|---|
| Spanning bar | Publication and Discovery: catalog for data and services |
| Box | Trust Framework |
| Box | Log |
| Box | Vocabulary Hub (Data Models & Formats, CIM Based Ontologies) |
| Box | Contracting |

**Distributed Data Exchange Platform Layers**

| Element | Label as shown |
|---|---|
| Blue box above each platform | Data Space Connector (one per platform) |
| Platform box (left) | Platform X — OnPrem or Cloud data infrastructure |
| Platform box (right) | Platform Y — OnPrem or Cloud data infrastructure |
| Side note | "Examples of data exchange platforms: • <u>Regulated</u>: EMS, ADMS, Market Platforms, Meter Data Hubs, Flexibility Registers, … • <u>Unregulated</u>: DERMS, VPP, Charging Point Management, Community Energy Management, DER Technical Aggregators, Building Energy Management" |

**Red arrows** (the three exchange cases the text enumerates):

| # | Arrow label | Direction shown | Text of the source |
|---|---|---|---|
| 1 | 1. Data Indexing | left Data Space Connector → federated layers (upward) | "**Data indexing** of own data in a data space (between a data space participant and the federated data space)" |
| 2 | 2. Data Discovery | federated layers → right Data Space Connector (downward) | "**Data discovery** in data space (between the federated data space and a data space participant)" |
| 3 | 3. Energy Flexibility & Cross-sectorial Data Exchange, sub-labelled *REST or Pub-Sub APIs* | bidirectional, connector ↔ connector | "**Bilateral exchange of the traded data** among two data exchange platforms, based on REST or Pub-Sub APIs; the traded data can be associated, for example, with energy flexibility, also in cross-sector implementations" |

**Lower bands** (connected to the platforms by green arrows):

| Band | Content as shown |
|---|---|
| Communication Infrastructure | 5G · PLC · LTE |
| Data Endpoints | "Data Endpoints: network sensors, edge IoT and AI, smart meters and Dedicated Measurement Devices" |
| Energy Stakeholders | TSOs and DSOs · Market Operators · Energy Communities · Charge Point Operators · BRPs and BSPs · Customers · OEMs |

## The data space connector

The different data space participants "are connected through a software component commonly
referred to as 'data space connector' (the blue box in Figure 11), which realizes the
interconnection and data exchange". "In particular, the data space connector should be
incorporated into the (pre-existing) platforms to enable identification, data harmonization and
brokerage towards data spaces." This "can be useful for integrating data from different sources,
or for allowing multiple applications to access the same data without having to duplicate it in
multiple places". "Data space connectors typically use standardized data exchange protocols to
facilitate the transfer of data between different systems. This can help to ensure that the data
remains consistent and accurate across all the connected systems. Beyond trustworthy and
interoperable data exchanges, it can provide seamless service utilization."

When implemented in the proposed model for the CEEDS, the connector "also enables the exchange of
energy data and execution of services among the existing platforms (in the 'distributed data
exchange platform' layers) and through the federated, overarching layer of the data space". "The
data connector can be run by a participant (i.e., a data platform) or on its behalf. That provides
connectivity with similar data connectors run by (or on behalf of) other participants."

The connector "provides more functionality than is strictly related to connectivity, for example:
data interoperability functions, authentication interfacing with trust services and authorization,
data product self-description, contract negotiation, etc." It "therefore has links to many
different building blocks located in the federated data space side (e.g., trust framework and
vocabulary hub); this includes, in addition to the data exchange, the components reported in the
federated side of the data space."

The source calls out "the key role of the data spaces connector to operate the exchange of
metadata (e.g., via the identity manager and credential manager components) and traded data (e.g.,
via the publication and discovery – catalog - component)".

## Figure 12 — Complete CEEDS architecture

"The complete CEEDS architecture is shown in Figure 12. In this case, additional details are added
for the components of the federated data space (i.e., for the trust framework as well as the log
and contracting components), which are described in detail in Section 4.1; moreover, the
representation of existing data platforms is enriched: the inner components manage the
acquisition/provision of data, together with their storage and process in the dedicated analytics
and energy services."

Rendering of the figure's federated portion (the distributed portion, the communication
infrastructure, data endpoints and energy stakeholders bands are identical to Figure 11, including
the same three red arrows):

**Federated Data Space Layers (centralized or distributed)** — drawn as a stack of several
overlapping layers.

| Level | Component box | Adjacent / nested label as shown |
|---|---|---|
| 1 (spanning bar) | Publication and Discovery: catalog for data and services | — |
| 2 | Log | Provenance & Traceability (Clearing House) |
| 2 | Vocabulary Hub (Data Models & Formats) | — |
| 2 | Contracting | Contractual Framework |
| 3 | Trust Framework | contains the two groups below |
| 3a | Identity Management | Identity Register · Identity Manager · Identity Provider |
| 3b | Access & Usage, Policies and Control | Usage Policies · Contract Policies · Access Policies |

> **Ambiguous:** Figure 12 labels the first identity sub-component **Identity Register**, whereas
> the text of section 4.1 names **Identity Governor** in that position. The figure and the text do
> not agree.

> **Ambiguous:** Figure 12 labels the group **Access & Usage, Policies and Control**, whereas the
> text of section 4.1 names the building block **"Access & usage policies and control"**.

### Control plane and data plane

"Regarding the data exchanged between the different instances of data spaces connectors and the
federated data spaces, the approach of the control plane and data plane, proposed in the DSSC
Blueprint v1.0, is deployed."

| Plane | Responsibility (source) |
|---|---|
| **control plane** | "oversees decisions related to the management, routing, and processing of data, including tasks such as user identification and the enforcement of access and usage policies (i.e., commonly referred to as metadata)" |
| **data plane** | "is tasked with the physical movement of data, encompassing the actual exchange of information (i.e., the energy-related data)" |

"With respect to the specific data exchange instances reported in Figure 11, on the contrary,
Figure 12 maintains a generic configuration while locating the use of control and data planes."

> **Ambiguous:** the text states that Figure 12 locates the use of control and data planes, but
> Figure 12 as printed carries no control-plane or data-plane label; its arrows are the same three
> numbered exchanges (Data Indexing, Data Discovery, Energy Flexibility & Cross-sectorial Data
> Exchange / REST or Pub-Sub APIs) as Figure 11. Which arrows belong to which plane is not shown.

## 4.1. Components of the Data Space Federated Side

"With respect to the proposed architecture for CEEDS, represented in Figure 12, the components
that form the federated data space side are hereafter individually described [1], [3]."

Reference [1] is "Blueprint v1.0 - Data Spaces Support Centre"; reference [3] is "IDS-RAM 4 -
Roles in the International data spaces". The two references are cited jointly for the whole
component list; the source does not attribute individual components to one or the other.

### Component-to-building-block map

The source states an explicit association between component and building block for four of the
five listed components.

| Component (source's own name) | Associated building block(s), as named by the source |
|---|---|
| **Trust Framework** | "Access & usage policies and control" and "Identity Management" |
| **Log** | "Provenance & Traceability" |
| **Vocabulary Hub** | *(none stated)* |
| **Contracting** | "Contractual Framework" |
| **Publication & Discovery** | *(the source calls this item itself "the publication and discovery building block")* |

### Trust Framework

"Trust Framework, which is associated with two building blocks: 'Access & usage policies and
control' and 'Identity Management'."

#### Access & usage policies and control

"This building block is connected to the concept of data sovereignty which, in the context of data
spaces, is about the control of access and usage of data. Different policies are normally used to
express the rights and obligations to maintain the control of data usage; hence, one objective in
data space management is the definition of interoperable policies, i.e. rules to give access to a
specific energy service (e.g., booking a charging slot with a eMSP or executing a saving
estimation in an energy community) and understanding the rules for the usage of the data (i.e.,
which energy services they enable, the privacy rules with respect to other energy stakeholders)."

"Two types of policies are defined:"

| Policy type | Definition (source) |
|---|---|
| **Access policies** | "which specify the conditions to access services and data" |
| **Usage Policies** | "which specify rights and obligations for the usage of the data, including the future usage of data" |

"To enable the decision-making process in evaluation policies, connection to other building blocks
is required for identification, authentication and authorization. Expression of policies and rules
are provided from different contexts (e.g. data space level, contractual relationship, law) and
must be consolidated into a machine-readable and executable way. In addition, during a data
transaction, the policies need to be evaluated and decisions on access to data and services and
data usage need to be taken."

"Access and usage policies in a data space ensure a trusted data ecosystem within a data space;
the two main policy groups that are central to the functionality of a data space are access
policies (which control access to data and services), which can be included in the contract
policies (which review attributes that must be provided at the contract negotiation)."

> **Ambiguous:** the sentence above announces "two main policy groups" but names only access
> policies clearly, then places them inside contract policies. Contract policies are not among the
> "two types of policies" defined earlier in the same subsection, yet Figure 12 shows three boxes
> — Usage Policies, Contract Policies, Access Policies. The relationship among the three is not
> resolved by the text.

"While the trust framework provides the existing possibilities for policies in the different
categories, the implementation is performed via the data space connectors."

#### Identity Management

"This concept relates to many practical use-cases:"

1. "identifying data space participants, via an identity registry in which parties are registered
   that have committed to the data space governance framework and comply with any other
   requirements"
2. "identifying connectors and other technical components"
3. "identifying trusted data providers (such instances enable data space participants to learn
   which parties have been certified to provide particular data)"

"Multiple sub-components form the identity management building block:"

| Sub-component | Definition (source) |
|---|---|
| **Identity Governor** | "the data space role that is used to refer to the party that performs the identity governance function for a specific identity registry" |
| **Identity Manager** | "which is used to refer to the party that performs the identity management function for a specific identity registry" |
| **Identity Provider** | "the data space role that is used to refer to the party that performs the identity provisioning function for a specific identity registry" |

"The identity management enables authorization mechanisms based on identity attributes. The
deployed functionalities are:"

| Functionality | Statement (source) |
|---|---|
| **Security/Resilience** | "Identity provision and management are critical parts of a cyber-secure system." |
| **Open Source** | "The way to implement identification, at any potentially interested infrastructure, should be kept as simple and as open as possible." |
| **Interoperability** | "It is very important not just to enable easy federation, but also to make sure the identification mechanism proposed is aligned at European level, maximizing the interoperability with other data spaces, either in the energy or different sectors." |

"In OPEN DEI building blocks the identity management is associated with the 'Trust' category,
whereas GAIA-X deploys a decentralized approach based on self-sovereign identity."

### Log

"Log. This component is used to log information or store information about data usage (e.g.,
incidents) and is associated with the building block 'Provenance & Traceability'. Logs may be
implemented centrally or in a distributed manner. This element is linked to the need to specify
the information stored for each transaction, as well as how access and usage are regulated and
controlled."

"Both traceability and provenance serve as vital functional requirements for every participant in
a data value chain, particularly one involving multiple data transactions. In data spaces, the
observability of each transaction activity, including the provision of evidence, is often
essential. This need for observability may arise from legal mandates, the governance framework of
the data space, contractual agreements, or other policies."

"The Provenance & Traceability component is closely associated with the concept of a 'Clearing
House,' defined as an intermediary that offers clearing and settlement services for financial and
data exchange transactions. It records all activities during a data exchange, which subsequently
proves useful for billing and conflict resolution. Additionally, the Clearing House monitors and
logs data transactions, enforces policies, and provides a platform for data accounting."

### Vocabulary Hub

"It provides endpoints to enable seamless communication with data space connectors and
infrastructure components. Vocabularies are defined as commonly known, standardized terms to
describe data, services, and contracts; hence the vocabulary hubs give access to the defined terms
and their descriptions present changes and outline the different versions. Moreover, it provides
information about the ontology/language used for data and, on the other hand, checks that the data
being indexed is compliant with the provided vocabulary."

"DCAT (Data Catalog Vocabulary) is recommended as a publisher to describe datasets and data
services. Again, being this an energy oriented approach, IEC (CIM, 61850, COSEM, etc.) and ETSI
(SAREF, etc.) standards are what this vocabulary module is expected to be reliant on."

"The different functions of this component include:"

| Function | Statement (source) |
|---|---|
| **Storing vocabularies** | "the Vocabulary Hub stores and lists valid vocabularies, making them available for the public and long-term use" |
| **Search on the semantic sources** | "the Vocabulary Hub allows data space participants to search for semantic resources based on specified criteria, providing a qualified results list with links to vocabularies and other semantic resources" |
| **Documenting non-standardized data** | "the Vocabulary Hub permits data space participants to include semantic information about non-standardized data during ingestion, making this information discoverable within the data space" |
| **Export semantic sources** | "the Vocabulary Hub enables data space participants to export semantic sources in various formats, including serialization options or human-readable formats" |
| **Automatic integration with the catalog** | "the Vocabulary Hub offers continuous integration, ensuring that the catalog of vocabularies has complete access to the semantic information of a vocabulary with appropriate user permissions" |
| **Validation of data** | "the Vocabulary Hub allows data space participants to validate their data against specific vocabularies" |

### Contracting

"Contracting, which is linked with the building block 'Contractual Framework'. The foundational
element of the contractual framework encompasses contract templates, model clauses, or modules
that empower transaction participants to manage and execute specific data transactions.
Integrating tools to automate various stages of the contracting process, such as concluding
contracts, monitoring compliance, and terminating agreements, can further streamline data
transactions while upholding the legal validity of the agreed-upon terms."

"This framework delineates the rights and responsibilities of participants within the data space,
including providers of enabling energy services (e.g., the data analytics service provider) and
the governing authority of the data space. Its primary objective is to translate agreements among
these entities into unambiguous and legally binding contractual obligations."

"Additionally, this component may embed elements of contract automation, utilizing technologies
like smart contracts to simplify and automate the creation and execution of contracts. Through the
reduction of transaction costs and the enhancement of overall efficiency, contract automation
contributes to the improved functioning of the energy data space."

"As in the Energy sector much data exchange is done in the course of regulated processes, often
contractual considerations are implicitly covered, so not every data exchange covered by the CEEDS
will explicitly show this building block."

### Publication & Discovery

"The publication and discovery building block acts as a catalogue containing self-descriptions of
the data products available in a data space. These descriptions are published in the catalogue by
the providers of these products so that they become discoverable for potential users. In order to
allow this, the publication and discovery building block provides the following key capabilities:"

| Key capability | Statement (source) |
|---|---|
| Management of self-descriptions | "including publication, update and removal of self-descriptions by the providers" |
| Facilitate discovery of self-descriptions | "by potential users, so the catalogue follows as much as possible the FAIR (Findable, Accessible, Interoperable, Reusable) principles" |
| Enable dynamic transactions | "bringing together providers and potential users and paving the way for them to establish a relationship that will end up in a provisioning and/or transaction" |
| Manage the access to self-descriptions | "since the catalogue may contain descriptions accessible just to a specific group of participants (access control to descriptions and policies to determine access rights)" |

"This building block, necessary to ensure loose coupling between data providers and potential
users, is critical for facilitating dynamic data transactions between these participants in the
data space. It can be implemented through two different scenarios:"

| Implementation scenario | Statement (source) |
|---|---|
| **Centralized or distributed catalogue** | "which includes all descriptions coming from the providers, and publishes them either in a centralized (a unique catalogue for the whole data space) or distributed (several catalogues that will have to implement some kind of synchronization) way. An example of such implementation could be the Metadata Broker specifications provided by IDSA, which contain an endpoint for the registration, publication, maintenance and query of Self-Descriptions." |
| **Decentralized or p2p catalogue** | "where the capabilities are included as part of the data connector used by each participant in the data space. In this case, participants directly contact each other on a p2p basis and establish the relationship by using the functionalities defined in the control plane of the connector." |

## Standards and protocols

Names, versions and citations are verbatim from the chapter. In the "Normative force" column,
*referenced* means the source names it as a basis, an example or an external description without
requiring it; *adopted* means the source states the CEEDS architecture deploys or reflects it.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| DERA 3.0 (Data Exchange Reference Architecture 3.0) | 3.0 | Concept the proposed model reflects; "defined in the Bridge Data Management WG based on SGAM" | adopted |
| SGAM | — | Basis of DERA 3.0; the distributed platform layer follows "the key applications and functions defined in the SGAM" | referenced |
| DSSC Blueprint v1.0 | v1.0 (reference [1], "Blueprint v1.0 - Data Spaces Support Centre") | Source of the "control plane and data plane" approach, which "is deployed"; jointly cited as the basis of the §4.1 component descriptions | adopted |
| IDS-RAM 4 — "Roles in the International data spaces" | IDS-RAM 4 (reference [3]) | Jointly cited with [1] as the basis of the §4.1 component descriptions | referenced |
| HEMRM | — | Defines the set of energy stakeholders / actors ("DSOs, TSOs, market operators, OEMs, energy communities, charge point operators, customers, BRPs and BSPs") | referenced |
| DCAT (Data Catalog Vocabulary) | DCAT — `https://w3.org/TR/vocab-dcat-3/#Class:Catalog` | "recommended as a publisher to describe datasets and data services" (Vocabulary Hub) | recommended |
| IEC (CIM, 61850, COSEM, etc.) | as listed | "what this vocabulary module is expected to be reliant on" | recommended |
| ETSI (SAREF, etc.) | as listed | "what this vocabulary module is expected to be reliant on" | recommended |
| CIM (Common Information Model) | — | Figure 11 labels the Vocabulary Hub "(Data Models & Formats, CIM Based Ontologies)" | referenced |
| FAIR (Findable, Accessible, Interoperable, Reusable) principles | — | The catalogue "follows as much as possible" them, to facilitate discovery of self-descriptions | recommended |
| Metadata Broker specifications provided by IDSA | — | Named as "an example of such implementation" of a centralized or distributed catalogue; "contain an endpoint for the registration, publication, maintenance and query of Self-Descriptions" | referenced |
| OPEN DEI building blocks | — | "the identity management is associated with the 'Trust' category" | referenced |
| GAIA-X | — | "deploys a decentralized approach based on self-sovereign identity" | referenced |
| REST or Pub-Sub APIs | — | Basis of the bilateral exchange of traded data among two data exchange platforms (Figure 11, arrow 3) | adopted |
| 5G, LTE, fiber optics, PLC, secured internet | — | Communication technologies accommodated by the existing communication infrastructures (Figure 11/12 band shows 5G, PLC, LTE) | referenced |
| Directive (EU) 2019/944, Article 23 | — | "delegates the responsibility for shaping the approach to data management for energy services to Member States" | referenced |
| TSO-DSO Data Management Report | — | One of "two significant sources" describing existing data management strategies | referenced |
| GEODE Data Management Fact Sheet | — | One of "two significant sources"; explores the implications of Article 23 of Directive (EU) 2019/944 | referenced |

> **Gap:** the chapter names no protocol for the interaction between a data space connector and
> the federated data space side. The only wire-level statement in the chapter is "REST or Pub-Sub
> APIs" for the bilateral traded-data exchange, plus the generic "Data space connectors typically
> use standardized data exchange protocols".

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

Chapter 4 is predominantly descriptive architectural prose. Rows marked `informative` are
statements the source makes without normative modality; rows marked `must` / `should` / `may` /
`recommended` carry the source's own modal wording, quoted or closely tracked in the requirement
text.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-ARC-01` | The energy data space is created as the combination of multiple "distributed data exchange platforms" and overarching layers defined as the "federated data space" orchestration framework (centralized or distributed). | informative | `Blueprint_CEEDS_v3.0.txt:1345-1348` |
| `CEEDS-ARC-02` | The approach reflects the concept of DERA 3.0 (Data Exchange Reference Architecture 3.0), defined in the Bridge Data Management WG based on SGAM. | informative | `Blueprint_CEEDS_v3.0.txt:1348-1350` |
| `CEEDS-ARC-03` | The distributed data exchange platforms layer covers data platforms associated with either regulated infrastructures or unregulated actors and entities, in line with the key applications and functions defined in the SGAM. | informative | `Blueprint_CEEDS_v3.0.txt:1352-1355` |
| `CEEDS-ARC-04` | Each data exchange platform behaves as data provider and/or data consumer. | informative | `Blueprint_CEEDS_v3.0.txt:1360-1374` |
| `CEEDS-ARC-05` | The CEEDS guarantees data exchange among data space participants associated with different data exchange platforms. | informative | `Blueprint_CEEDS_v3.0.txt:1378-1379` |
| `CEEDS-ARC-06` | Endpoints for energy-related data are entities that act as sources and/or receivers of data. | informative | `Blueprint_CEEDS_v3.0.txt:1379-1386` |
| `CEEDS-ARC-07` | Data are bidirectionally exchanged with the distributed data ecosystems via the existing communication infrastructures, which accommodate different technologies such as 5G, LTE, fiber optics, PLC and secured internet. | informative | `Blueprint_CEEDS_v3.0.txt:1386-1388` |
| `CEEDS-ARC-08` | The federated data space side indexes data, making it discoverable, and provides a sort of marketplace for sharing and, possibly, trading both data and data services. | informative | `Blueprint_CEEDS_v3.0.txt:1427-1429` |
| `CEEDS-ARC-09` | Actors and data platforms federate through the data space connectors and offer their data under pre-recorded policies, verified credentials, data models and contractual agreements. | informative | `Blueprint_CEEDS_v3.0.txt:1429-1432` |
| `CEEDS-ARC-10` | The federated data space side includes a set of components to implement foundational building blocks that perform the required functionalities of the data space. | informative | `Blueprint_CEEDS_v3.0.txt:1432-1434` |
| `CEEDS-ARC-11` | Data space participants are connected through a software component commonly referred to as "data space connector", which realizes the interconnection and data exchange. | informative | `Blueprint_CEEDS_v3.0.txt:1450-1452` |
| `CEEDS-ARC-12` | The data space connector should be incorporated into the pre-existing platforms to enable identification, data harmonization and brokerage towards data spaces. | should | `Blueprint_CEEDS_v3.0.txt:1452-1453` |
| `CEEDS-ARC-13` | Data space connectors typically use standardized data exchange protocols to facilitate the transfer of data between different systems. | informative | `Blueprint_CEEDS_v3.0.txt:1455-1457` |
| `CEEDS-ARC-14` | The data connector can be run by a participant (i.e., a data platform) or on its behalf. | may | `Blueprint_CEEDS_v3.0.txt:1462-1463` |
| `CEEDS-ARC-15` | The data connector provides connectivity with similar data connectors run by, or on behalf of, other participants. | informative | `Blueprint_CEEDS_v3.0.txt:1463-1464` |
| `CEEDS-ARC-16` | The data connector provides more functionality than is strictly related to connectivity, for example data interoperability functions, authentication interfacing with trust services and authorization, data product self-description and contract negotiation. | informative | `Blueprint_CEEDS_v3.0.txt:1464-1466` |
| `CEEDS-ARC-17` | The data space connector has links to many different building blocks located in the federated data space side (e.g., trust framework and vocabulary hub). | informative | `Blueprint_CEEDS_v3.0.txt:1466-1469` |
| `CEEDS-ARC-18` | The data space connector operates the exchange of metadata, e.g. via the identity manager and credential manager components. | informative | `Blueprint_CEEDS_v3.0.txt:1470-1472` |
| `CEEDS-ARC-19` | The data space connector operates the exchange of traded data, e.g. via the publication and discovery (catalog) component. | informative | `Blueprint_CEEDS_v3.0.txt:1470-1472` |
| `CEEDS-ARC-20` | Data indexing of own data in a data space takes place between a data space participant and the federated data space. | informative | `Blueprint_CEEDS_v3.0.txt:1475-1476` |
| `CEEDS-ARC-21` | Data discovery in the data space takes place between the federated data space and a data space participant. | informative | `Blueprint_CEEDS_v3.0.txt:1477-1478` |
| `CEEDS-ARC-22` | Bilateral exchange of the traded data among two data exchange platforms is based on REST or Pub-Sub APIs. | informative | `Blueprint_CEEDS_v3.0.txt:1479-1481` |
| `CEEDS-ARC-23` | The approach of the control plane and data plane, proposed in the DSSC Blueprint v1.0, is deployed for the data exchanged between the different instances of data space connectors and the federated data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:1488-1495` |
| `CEEDS-ARC-24` | The control plane oversees decisions related to the management, routing and processing of data, including tasks such as user identification and the enforcement of access and usage policies (commonly referred to as metadata). | informative | `Blueprint_CEEDS_v3.0.txt:1495-1497` |
| `CEEDS-ARC-25` | The data plane is tasked with the physical movement of data, encompassing the actual exchange of information (the energy-related data). | informative | `Blueprint_CEEDS_v3.0.txt:1497-1499` |
| `CEEDS-ARC-26` | The Trust Framework component is associated with two building blocks: "Access & usage policies and control" and "Identity Management". | informative | `Blueprint_CEEDS_v3.0.txt:1511-1512` |
| `CEEDS-ARC-27` | One objective in data space management is the definition of interoperable policies, i.e. rules to give access to a specific energy service and to understand the rules for the usage of the data. | informative | `Blueprint_CEEDS_v3.0.txt:1520-1526` |
| `CEEDS-ARC-28` | Access policies specify the conditions to access services and data. | informative | `Blueprint_CEEDS_v3.0.txt:1528-1529` |
| `CEEDS-ARC-29` | Usage Policies specify rights and obligations for the usage of the data, including the future usage of data. | informative | `Blueprint_CEEDS_v3.0.txt:1530-1531` |
| `CEEDS-ARC-30` | Connection to other building blocks is required for identification, authentication and authorization, to enable the decision-making process in evaluating policies. | must | `Blueprint_CEEDS_v3.0.txt:1533-1534` |
| `CEEDS-ARC-31` | Expression of policies and rules provided from different contexts (e.g. data space level, contractual relationship, law) must be consolidated into a machine-readable and executable way. | must | `Blueprint_CEEDS_v3.0.txt:1535-1537` |
| `CEEDS-ARC-32` | During a data transaction, the policies need to be evaluated and decisions on access to data and services and on data usage need to be taken. | must | `Blueprint_CEEDS_v3.0.txt:1537-1539` |
| `CEEDS-ARC-33` | The trust framework provides the existing possibilities for policies in the different categories, while the implementation is performed via the data space connectors. | informative | `Blueprint_CEEDS_v3.0.txt:1543-1545` |
| `CEEDS-ARC-34` | Identity Management identifies data space participants via an identity registry in which parties are registered that have committed to the data space governance framework and comply with any other requirements. | informative | `Blueprint_CEEDS_v3.0.txt:1546-1549` |
| `CEEDS-ARC-35` | Identity Management identifies connectors and other technical components. | informative | `Blueprint_CEEDS_v3.0.txt:1549-1550` |
| `CEEDS-ARC-36` | Identity Management identifies trusted data providers, enabling data space participants to learn which parties have been certified to provide particular data. | informative | `Blueprint_CEEDS_v3.0.txt:1550-1551` |
| `CEEDS-ARC-37` | The Identity Governor is the data space role that performs the identity governance function for a specific identity registry. | informative | `Blueprint_CEEDS_v3.0.txt:1554-1555` |
| `CEEDS-ARC-38` | The Identity Manager is the party that performs the identity management function for a specific identity registry. | informative | `Blueprint_CEEDS_v3.0.txt:1556-1557` |
| `CEEDS-ARC-39` | The Identity Provider is the data space role that performs the identity provisioning function for a specific identity registry. | informative | `Blueprint_CEEDS_v3.0.txt:1558-1559` |
| `CEEDS-ARC-40` | Identity management enables authorization mechanisms based on identity attributes. | informative | `Blueprint_CEEDS_v3.0.txt:1565-1566` |
| `CEEDS-ARC-41` | Identity provision and management are critical parts of a cyber-secure system (Security/Resilience). | informative | `Blueprint_CEEDS_v3.0.txt:1567-1568` |
| `CEEDS-ARC-42` | The way to implement identification, at any potentially interested infrastructure, should be kept as simple and as open as possible (Open Source). | should | `Blueprint_CEEDS_v3.0.txt:1569-1570` |
| `CEEDS-ARC-43` | The identification mechanism proposed should be aligned at European level, maximizing the interoperability with other data spaces, either in the energy or different sectors (Interoperability). Source wording: "It is very important … to make sure". | should | `Blueprint_CEEDS_v3.0.txt:1571-1574` |
| `CEEDS-ARC-44` | The Log component logs or stores information about data usage (e.g., incidents) and is associated with the building block "Provenance & Traceability". | informative | `Blueprint_CEEDS_v3.0.txt:1579-1581` |
| `CEEDS-ARC-45` | Logs may be implemented centrally or in a distributed manner. | may | `Blueprint_CEEDS_v3.0.txt:1581` |
| `CEEDS-ARC-46` | The information stored for each transaction, and how access and usage are regulated and controlled, needs to be specified. | must | `Blueprint_CEEDS_v3.0.txt:1581-1583` |
| `CEEDS-ARC-47` | Traceability and provenance are vital functional requirements for every participant in a data value chain, particularly one involving multiple data transactions. | informative | `Blueprint_CEEDS_v3.0.txt:1583-1584` |
| `CEEDS-ARC-48` | In data spaces the observability of each transaction activity, including the provision of evidence, is often essential; this need may arise from legal mandates, the governance framework of the data space, contractual agreements, or other policies. | informative | `Blueprint_CEEDS_v3.0.txt:1584-1587` |
| `CEEDS-ARC-49` | The Provenance & Traceability component is closely associated with the concept of a "Clearing House", an intermediary that offers clearing and settlement services for financial and data exchange transactions. | informative | `Blueprint_CEEDS_v3.0.txt:1587-1590` |
| `CEEDS-ARC-50` | The Clearing House records all activities during a data exchange, which subsequently proves useful for billing and conflict resolution. | informative | `Blueprint_CEEDS_v3.0.txt:1590-1591` |
| `CEEDS-ARC-51` | The Clearing House monitors and logs data transactions, enforces policies, and provides a platform for data accounting. | informative | `Blueprint_CEEDS_v3.0.txt:1591-1592` |
| `CEEDS-ARC-52` | The Vocabulary Hub provides endpoints to enable seamless communication with data space connectors and infrastructure components. | informative | `Blueprint_CEEDS_v3.0.txt:1593-1594` |
| `CEEDS-ARC-53` | Vocabulary hubs give access to the defined terms and their descriptions, present changes and outline the different versions. | informative | `Blueprint_CEEDS_v3.0.txt:1594-1597` |
| `CEEDS-ARC-54` | The Vocabulary Hub provides information about the ontology/language used for data. | informative | `Blueprint_CEEDS_v3.0.txt:1597-1598` |
| `CEEDS-ARC-55` | The Vocabulary Hub checks that the data being indexed is compliant with the provided vocabulary. | informative | `Blueprint_CEEDS_v3.0.txt:1598` |
| `CEEDS-ARC-56` | DCAT (Data Catalog Vocabulary) is recommended as a publisher to describe datasets and data services. | recommended | `Blueprint_CEEDS_v3.0.txt:1599-1600` |
| `CEEDS-ARC-57` | The vocabulary module is expected to be reliant on IEC (CIM, 61850, COSEM, etc.) and ETSI (SAREF, etc.) standards. | recommended | `Blueprint_CEEDS_v3.0.txt:1600-1612` |
| `CEEDS-ARC-58` | Storing vocabularies: the Vocabulary Hub stores and lists valid vocabularies, making them available for the public and long-term use. | informative | `Blueprint_CEEDS_v3.0.txt:1613-1614` |
| `CEEDS-ARC-59` | Search on the semantic sources: the Vocabulary Hub allows data space participants to search for semantic resources based on specified criteria, providing a qualified results list with links to vocabularies and other semantic resources. | informative | `Blueprint_CEEDS_v3.0.txt:1615-1617` |
| `CEEDS-ARC-60` | Documenting non-standardized data: the Vocabulary Hub permits data space participants to include semantic information about non-standardized data during ingestion, making this information discoverable within the data space. | informative | `Blueprint_CEEDS_v3.0.txt:1618-1620` |
| `CEEDS-ARC-61` | Export semantic sources: the Vocabulary Hub enables data space participants to export semantic sources in various formats, including serialization options or human-readable formats. | informative | `Blueprint_CEEDS_v3.0.txt:1621-1623` |
| `CEEDS-ARC-62` | Automatic integration with the catalog: the Vocabulary Hub offers continuous integration, ensuring that the catalog of vocabularies has complete access to the semantic information of a vocabulary with appropriate user permissions. | informative | `Blueprint_CEEDS_v3.0.txt:1624-1626` |
| `CEEDS-ARC-63` | Validation of data: the Vocabulary Hub allows data space participants to validate their data against specific vocabularies. | informative | `Blueprint_CEEDS_v3.0.txt:1627-1628` |
| `CEEDS-ARC-64` | The Contracting component is linked with the building block "Contractual Framework". | informative | `Blueprint_CEEDS_v3.0.txt:1629-1630` |
| `CEEDS-ARC-65` | The foundational element of the contractual framework encompasses contract templates, model clauses, or modules that empower transaction participants to manage and execute specific data transactions. | informative | `Blueprint_CEEDS_v3.0.txt:1630-1632` |
| `CEEDS-ARC-66` | Integrating tools to automate stages of the contracting process — concluding contracts, monitoring compliance, and terminating agreements — can further streamline data transactions while upholding the legal validity of the agreed-upon terms. | may | `Blueprint_CEEDS_v3.0.txt:1632-1634` |
| `CEEDS-ARC-67` | The contractual framework delineates the rights and responsibilities of participants within the data space, including providers of enabling energy services and the governing authority of the data space. | informative | `Blueprint_CEEDS_v3.0.txt:1634-1637` |
| `CEEDS-ARC-68` | The primary objective of the contractual framework is to translate agreements among these entities into unambiguous and legally binding contractual obligations. | informative | `Blueprint_CEEDS_v3.0.txt:1637-1638` |
| `CEEDS-ARC-69` | The Contracting component may embed elements of contract automation, utilizing technologies like smart contracts to simplify and automate the creation and execution of contracts. | may | `Blueprint_CEEDS_v3.0.txt:1638-1641` |
| `CEEDS-ARC-70` | Not every data exchange covered by the CEEDS will explicitly show the Contractual Framework building block, because in the Energy sector much data exchange is done in the course of regulated processes where contractual considerations are often implicitly covered. | informative | `Blueprint_CEEDS_v3.0.txt:1642-1645` |
| `CEEDS-ARC-71` | The publication and discovery building block acts as a catalogue containing self-descriptions of the data products available in a data space, published by the providers of these products so that they become discoverable for potential users. | informative | `Blueprint_CEEDS_v3.0.txt:1646-1649` |
| `CEEDS-ARC-72` | Publication and discovery provides management of self-descriptions, including publication, update and removal of self-descriptions by the providers. | informative | `Blueprint_CEEDS_v3.0.txt:1656-1657` |
| `CEEDS-ARC-73` | Publication and discovery facilitates discovery of self-descriptions by potential users, the catalogue following as much as possible the FAIR (Findable, Accessible, Interoperable, Reusable) principles. | recommended | `Blueprint_CEEDS_v3.0.txt:1658-1659` |
| `CEEDS-ARC-74` | Publication and discovery enables dynamic transactions, bringing together providers and potential users and paving the way for them to establish a relationship that will end up in a provisioning and/or transaction. | informative | `Blueprint_CEEDS_v3.0.txt:1660-1662` |
| `CEEDS-ARC-75` | Publication and discovery manages the access to self-descriptions, since the catalogue may contain descriptions accessible just to a specific group of participants (access control to descriptions and policies to determine access rights). | informative | `Blueprint_CEEDS_v3.0.txt:1663-1665` |
| `CEEDS-ARC-76` | Publication and discovery may be implemented as a centralized or distributed catalogue including all descriptions coming from the providers, published either in a unique catalogue for the whole data space or in several catalogues that will have to implement some kind of synchronization. | may | `Blueprint_CEEDS_v3.0.txt:1670-1675` |
| `CEEDS-ARC-77` | Publication and discovery may be implemented as a decentralized or p2p catalogue, where the capabilities are included as part of the data connector used by each participant and participants directly contact each other on a p2p basis, establishing the relationship by using the functionalities defined in the control plane of the connector. | may | `Blueprint_CEEDS_v3.0.txt:1676-1679` |

## Open questions

1. **Identity Governor vs Identity Register.** The text of §4.1 names three sub-components of the
   identity management building block: *Identity Governor*, *Identity Manager*, *Identity
   Provider* (`1554-1559`). Figure 12 shows *Identity Register*, *Identity Manager*, *Identity
   Provider*. The figure and the text disagree on the first sub-component; a register (an
   artefact) and a governor (a role) are not the same kind of thing. The text elsewhere uses
   "identity registry" (lowercase) for the artefact (`1547`).

2. **Building block naming: "Access & usage policies and control".** The text writes *"Access &
   usage policies and control"* (`1511`, `1513`); Figure 12 writes *"Access & Usage, Policies and
   Control"*. Neither spelling is reconciled with the other.

3. **Two or three policy types.** §4.1 defines "Two types of policies" — Access policies and Usage
   Policies (`1528-1531`) — but then refers to "contract policies (which review attributes that
   must be provided at the contract negotiation)" (`1540-1543`), and Figure 12 shows three boxes:
   *Usage Policies*, *Contract Policies*, *Access Policies*. The sentence at `1539-1543` announces
   "the two main policy groups" and then names only access policies, placing them inside contract
   policies; the sentence is grammatically incomplete and its meaning cannot be recovered from the
   source.

4. **Figure 12 does not show the control and data planes.** The text says "Figure 12 maintains a
   generic configuration while locating the use of control and data planes" (`1499-1500`), but the
   printed figure carries no control-plane or data-plane label. Its arrows are identical to
   Figure 11's three numbered exchanges. Which exchanges are control plane and which are data
   plane is therefore not established anywhere in the chapter.

5. **Figure 12 does not show the enriched platform representation the text describes.** The text
   says "the representation of existing data platforms is enriched: the inner components manage
   the acquisition/provision of data, together with their storage and process in the dedicated
   analytics and energy services" (`1485-1487`). In the printed figure, Platform X and Platform Y
   carry the same label as in Figure 11 ("OnPrem or Cloud data infrastructure") with no inner
   components drawn.

6. **Vocabulary Hub has no associated building block.** Every other component in §4.1 is stated to
   be associated with, or to be, a building block (Trust Framework → "Access & usage policies and
   control" + "Identity Management"; Log → "Provenance & Traceability"; Contracting →
   "Contractual Framework"; Publication & Discovery is itself called a building block). The
   Vocabulary Hub is described without any such association.

7. **Component versus building block is used inconsistently.** *Publication & Discovery* is
   introduced in the same bulleted list as the components but is described throughout as "the
   publication and discovery building block". *Log* is a component whose associated building block
   is *Provenance & Traceability*, yet the following paragraphs speak of "the Provenance &
   Traceability component".

8. **Vocabulary Hub label differs between the two figures.** Figure 11 reads "Vocabulary Hub (Data
   Models & Formats, CIM Based Ontologies)"; Figure 12 reads "Vocabulary Hub (Data Models &
   Formats)". The CIM qualifier is dropped without comment.

9. **Automatic compliance checking versus participant-invoked validation.** The Vocabulary Hub
   both "checks that the data being indexed is compliant with the provided vocabulary" (`1598`)
   and offers a *Validation of data* function that "allows data space participants to validate
   their data against specific vocabularies" (`1627-1628`). Whether these are the same mechanism
   is not stated.

10. **Terminology drift for the participant-side layer.** The same layer is called "distributed
    data exchange platforms" (`1346`, `1352`), "distributed data ecosystems" (`1389`, `1430`) and
    "distributed data exchange platform" layers (`1460-1461`); the figures label it "Distributed
    Data Exchange Platform Layers".

11. **DSSC version referenced.** The chapter adopts the control plane / data plane approach "of
    the DSSC Blueprint v1.0" (`1489-1495`) and cites reference [1] ("Blueprint v1.0 - Data Spaces
    Support Centre") for the §4.1 component list, although the document's reference list also
    carries "Data Spaces Blueprint v2.0". The chapter does not say which DSSC version governs the
    component decomposition it presents.

12. **Joint citation of [1] and [3].** §4.1 attributes the entire component list to "[1], [3]"
    (DSSC Blueprint v1.0 and IDS-RAM 4 — Roles in the International data spaces) without saying
    which description comes from which. The Identity Governor / Identity Manager / Identity
    Provider definitions are phrased as data space *roles*, consistent with [3], but this is not
    stated.

13. **DSSC building block names are not verified against DSSC.** The building block names used in
    this chapter — "Access & usage policies and control", "Identity Management", "Provenance &
    Traceability", "Contractual Framework", "publication and discovery building block" — are
    reproduced here exactly as CEEDS v3.0 spells them. Whether these match the building block
    names used by the DSSC Blueprint itself was not checked in producing this page, and CEEDS
    does not print a mapping.

14. **No protocol specified for connector-to-federated-side interaction.** See the gap note under
    "Standards and protocols".

15. **The chapter names no interfaces beyond three.** The only interface-level nouns in the
    chapter are: the Vocabulary Hub's "endpoints to enable seamless communication with data space
    connectors and infrastructure components" (unspecified), the "REST or Pub-Sub APIs" of the
    bilateral traded-data exchange, and the IDSA Metadata Broker's "endpoint for the registration,
    publication, maintenance and query of Self-Descriptions" (cited as an example implementation,
    not as a CEEDS interface). No signatures, schemas or bindings are given.

16. **"credential manager" component is named once and never defined.** The chapter refers to the
    connector operating the exchange of metadata "via the identity manager and credential manager
    components" (`1470-1471`), but no *credential manager* appears in the §4.1 component list or
    in either figure.
