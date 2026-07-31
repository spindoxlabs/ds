# Interoperability Aspects

> **Source** · Blueprint of the Common European Energy Data Space (CEEDS) v3.0, September 2025 › 7. Interoperability Aspects
> **Chapter** · 7 (pp. 71–82), including Figures 13–17

To fully achieve the deployment of CEEDS, starting from the federation of projects' data
space instances, the blueprint holds that detailed interoperability measures are necessary.
The interoperability requirements described in the blueprint are grouped into **technical
interoperability**, **semantic interoperability** and **governance interoperability**; they
refer to the European Interoperability Framework (EIF) Toolbox [9], addressing the applicable
layers.

> **Ambiguous:** the chapter has no section `7.1`. Its numbering runs directly from the
> chapter heading to `7.1.1`, and every subsection is numbered `7.1.x`. This is how the
> source's own table of contents lists it. The section headings below reproduce the
> source's numbering as published.

---

## 7.1.1. Technical Interoperability

Technical interoperability refers to the minimum technical framework that is required for all
participants of a data space in the energy domain to be able to process and understand the
information (metadata) of the services/data offered in the data space and be able to perform
data transfers between them (participants). Specifically, this technical interoperability
framework covers the following aspects:

1. Building blocks
2. Actors
3. Data formats
4. Data transmission protocols

To implement the various capabilities in a data space, technology is needed. In most of the
data spaces the component "data space connector", described as part of the CEEDS
architecture, is used to provide an endpoint, enabling actors to participate in a data space.
In addition, (shared) registries and services are needed to provide common/shared
functionalities in a data space — for example, to register the participants of a data space.

### 7.1.1.1. Building Blocks

From the technical viewpoint, **nine building blocks** are defined, which are grouped into:

- **Data interoperability:** capabilities needed for the exchange of data: (semantic) models,
  data formats and interfaces (APIs). This also includes functionalities for provenance &
  traceability.
- **Data sovereignty and trust:** capabilities needed for the identification of participants
  and assets in a data space, the establishment of trust and the possibility to define and
  enforce policies for access and usage control.
- **Data value creation:** capabilities used to enable value-creation in a data space, e.g.
  by registering and discovering data offerings or services, providing marketplace
  functionality and enabling monetization of data sharing.

The technical building blocks are described as "initially defined by OPEN DEI and included in
the DSSC analysis", and are shown in Figure 13, which the source attributes to reference [1]
(*Blueprint v1.0 — Data Spaces Support Centre*).

**The prose does not enumerate the nine building blocks.** They appear only as labels in
Figure 13. Reproduced verbatim from that figure:

| Group (as labelled in Figure 13) | Building blocks (as labelled in Figure 13) |
|---|---|
| Data Interoperability | Data Models · Data Exchange · Provenance & traceability |
| Data Sovereignty & Trust | Access & usage policies and control · Identity Management · Trust |
| Data Value Creation | Data, Services and Offerings descriptions · Publication & Discovery · Marketplaces |

Figure 13 additionally shows three elements laid over or beneath the nine, labelled **Data
Space Protocols** (spanning the diagram from the left), **Federated Services** (spanning from
the right) and **Data Space Registry** (beneath the grid), the whole grid being captioned
**Technical Building Blocks**. The text does not explain the relation of these three elements
to the nine building blocks.

> **Ambiguous:** these labels are the CEEDS figure's own wording. The source asserts no
> mapping between them and the building-block names used by the DSSC Blueprint, and the
> figure is credited to DSSC Blueprint **v1.0**. No mapping is supplied here, because the
> source does not supply one.

From an implementation standpoint, there is not a direct one-to-one correspondence between
building blocks and technical components. Often, a single technical component may be
associated with multiple building blocks.

**Control plane and data plane.** The source states it is crucial to differentiate between
the two:

- The **control plane** is responsible for determining how data is managed, routed, and
  processed, including user identification and the enforcement of access and usage policies.
- The **data plane** is tasked with the actual movement of data — the physical exchange of
  data.

Consequently, the control plane *can* be standardized at a high level, incorporating common
standards for identification and authentication. Meanwhile, the data plane *may vary* across
different data spaces, adapting to diverse data exchange requirements: some data spaces
prioritize large dataset sharing, others focus on message exchange, and some follow an
event-based approach. There is no universal solution, although certain mechanisms can
facilitate the collaboration of different data planes.

### 7.1.1.2. Actors

Apart from the building blocks, it is important to have a common definition of actors, in
line with the latest implementation plans of DERA, and their possible interactions. In this
sense, DSBA has published the technical convergence paper which has defined the main actors:

- Data Space Governance Authority
- Data Space
- Participant
- Participant Agent
- Data Space Registry
- Credential Issuer
- Identity/Authentication & Authorization, Identity provider

Figure 14, "Relations among data spaces actors", attributed to reference [10] (*Technical
Convergence – Discussion Document*, Data Spaces Business Alliance, Apr. 2023), shows the
following labelled relations:

| From | Relation | To |
|---|---|---|
| Data Space Governance Authority | governs | Data Space |
| Participant | member of | Data Space |
| Data Space | uses | Data Space Registry |
| Participant | controls | Participant Agent |
| Participant Agent | registers/uses | Data Space Registry |
| Participant Agent | verifies | Credential Issuer |
| Credential Issuer | issues | Participant Agent |
| Participant Agent | verifies | Identity Provider |
| Identity Provider | issues | Participant Agent |

### 7.1.1.3. Data Formats

As the main reference, **JSON** constitutes a lightweight, language-independent data
interchange format, easy to parse and generate. It provides a way to create a network of
standards-based machine-interpretable data across different documents. Particularly relevant,
as specific proposed solution, is the use of **JSON-LD**, which serializes linked data in
JSON.

### 7.1.1.4. Data transmission protocols

The **dataspace protocol** comprises specifications intended to facilitate interoperable data
sharing among entities governed by usage control and utilizing web technologies. These
specifications detail the necessary schemas and protocols for entities to publish data,
negotiate agreements, and access data within a data space.

To share data between autonomous entities, metadata is required to facilitate the transfer of
datasets, utilizing a data transfer (or application layer) protocol. The dataspace protocol
outlines how this metadata is provisioned, including:

- the deployment of datasets;
- the syntactic expression, and electronic negotiation, of agreements governing data usage;
- how datasets are accessed using "transfer process protocols".

To summarize, the dataspace protocol supports interoperability within data spaces. It ensures
fundamental technical interoperability for participants, **a prerequisite for joining any
data space**. The dataspace protocol aims to define the minimum standard of communication so
that each actor manages to communicate with other connectors (even if other connectors deploy
different features, semantic models, or business procedures).

The source's footnote points to the IDS knowledge base entry for the Data Space Protocol. No
version of the protocol is cited.

---

## 7.1.2. Semantic Interoperability

Semantic interoperability refers to the ability of different systems and devices to exchange
and interpret information consistently and accurately, based on a shared understanding of the
underlying meaning and context.

Harmonization frameworks for data sharing under a shared semantic context are beneficial for
interoperability as they enable consistent and standardized data exchange. These frameworks
establish common vocabularies, data models, and ontologies, ensuring a unified understanding
across different systems. Harmonization frameworks reduce complexity, improve data
compatibility, and enhance interoperability.

In this regard, **the CEEDS relies on the harmonization and usage of prominent
standards-based data models and ontologies such as**:

| Standard (verbatim) | Stated purpose (verbatim) |
|---|---|
| SAREF | for behind-the-meter-equipments |
| IEC 61970 | for grid modelling |
| IEC 62325 ESMP | for flexibility market interfaces |
| IEC 62746 | for service provided to technical aggregator communication |
| IEC 61850-7 | for advanced DER controls |
| OCPP | for Public Charging Point interfaces |
| Open Data Protocol (OData) | — |
| CIM data model and associated ontologies | "the overarching CIM data model" |

Moreover, the source highlights the **CGMES Conformity Assessment Scheme (CAS)**, developed by
ENTSO-E, **as an example** of conformity assessment in the Energy domain.

**Ontologies and RDF.** In data spaces where there is data exchange, approaches based on data
ontology (highlighting the relations among the data instances) are stated to be *a
requirement* in order to avoid silos. External systems cannot know about the relationships
unless they are provided with a machine-readable format. RDF is a framework for expressing
linked data so it can be exchanged between applications without loss of meaning. RDF allows
the expression of simple facts in the form of triples (subject, predicate and object). The
subject and the object represent the two resources being related; the predicate represents
the nature of their relationship in a directional way (from subject to object). RDF uses URIs
to name the relationship between things as well as the two ends of the link. There are
various concrete syntaxes for RDF, such as **Turtle [TURTLE]**, **TriG [TRIG]**, and
**JSON-LD [JSON-LD]**.

**Vocabulary Hubs.** Common ontologies provide a shared vocabulary and conceptual framework,
enabling a consistent understanding of data. They facilitate interoperability, integration,
and fusion of data from diverse sources. Vocabulary Hubs, where different data models are
published, are *key* to link the Marketplace for data/service offering discovery. Standards
provide a common framework for defining data models, message profile formats, and protocols.
By adhering to semantic and syntactic standards, open data sources can align their data
structures and semantics, facilitating seamless interoperability between diverse systems and
applications.

---

## 7.1.3. Governance interoperability

With respect to the **DERA 3.1 model** (developed in the Data Management working group of
Bridge, reference [11]), the governance components are depicted in Figure 15 and have been
mapped to (i) the local (the distributed data ecosystems with legacy data platforms) and
federated (the federated data space) parts, as well as (ii) the **five SGAM interoperability
layers** (vertically). In total, **ten building blocks** have been defined along the SGAM
layers to address the governance of interoperability.

The governance framework:

- **must** acknowledge the diversity of platforms and systems, tailored to various market
  designs and business processes;
- **should** promote cross-stakeholder, cross-border, and cross-sector data exchanges,
  guaranteeing convenient data access that complies with GDPR requirements;
- **should** (as governance model) facilitate coordination between TSO and DSO from a
  customer perspective, ensuring scalability through the open-interoperable principles
  leveraging common open-source components and agreed-upon rules.

**The ten governance building blocks are not listed in the prose.** Figure 15 highlights ten
blocks against a background of non-highlighted context blocks. Read from the figure, and
grouped by the SGAM layer band each sits in, the highlighted blocks are:

| SGAM layer band (Figure 15) | Highlighted governance blocks |
|---|---|
| Business | Rules and norms · Data governance business case · Orchestrated data governance |
| Function | Data access governance · Data ownership governance |
| Information | Data security governance · Data vocabulary governance |
| Comms | Interfaces (APIs, GUIs) |
| Comp. | Data platforms · Repositories |

> **Ambiguous:** this list is read off Figure 15, not stated in the text. Figure 15 also
> contains non-highlighted blocks (Actors, Energy Regulation, Local Use Cases, Regulation,
> Business needs, Marketplace Frontend, Digital Twins, Local AI/ML Services, Marketplace
> Backend, Monitoring & Orchestration, Data Persistence, Data Processing, Standard
> Communication Protocols & Formats) and a vertical band at the local/federated boundary
> whose label is partly obscured in the published figure.

### The proposed 6th SGAM layer

The source highlights the proposal from the int:net whitebook "Engagement Towards
Interoperability in Governance" [12]. The whitebook concluded that the 5th SGAM layer is much
oriented to business cases and cannot cover political or regulatory and not at all societal
interoperability in broad systems; for this reason, the inclusion of a **6th SGAM layer, named
"framework" layer**, is proposed (Figure 16). This layer addresses interoperability among a
large set of energy domain stakeholders, including:

- Policymakers in politics and public authorities on multiple levels from national to municipal
- Regulatory bodies
- Market operators (from global to national to regional and local marketplaces)
- Standardization organizations (national and international)
- Supplier associations, for energy (e.g., ENTSO-E, DSO Entity) and technology (e.g., T&D
  Europe, AIOTI, SmartEn, SolarPower Europe)
- Consumption Associations (industry and other business associations, building associations,
  consumer associations)
- Research, innovation and other funding programs (national, transnational, international)
- Institutions for education and human capital development
- Infrastructure operators (e.g., for transport, health)
- Finance and investment institutions (e.g., ECB, EIB, EU facilities, EFRAG)

The framework layer allows for the identification of specific barriers and requirements
related to the interaction among CEEDS stakeholders, hitherto often hidden, as well as to
undertake necessary actions that enhance governance fulfilment in data space solutions. A
depiction and description of the interaction among so-called "governance entities" enables
stakeholders interested in engaging with data space governance to better understand the
overarching context and goals at each level of activity and thus to improve the quality of
engagement. Such a depiction also enables improving framework-setting synergies within
various data space initiatives, allowing for tackling complexity, speed of change and
silo-development.

Through the use of **governance classes**, which serve as a means to categorize or group
governance entities, the proposal for a 6th layer aims at generalizing interactions among
stakeholders and institutions which are commonly involved in a given interoperability
framework setting. Additionally, the 6th layer framework promotes **five common frameworks**.
Namely, the **regulatory, standardization, involvement, funding and validation** frameworks.
Through an elaborate set of institutional arrangements, structures, roles, responsibilities,
guidelines, policies, agreements, processes and procedures, these frameworks may be
co-created by all relevant entities to support the emergence of data spaces. While some
governance entities will find their "natural" place in specific frameworks, framework
development can be enriched by interactions across frameworks.

> **Contradiction in the source:** Figure 16 labels the five bands of the framework layer
> *Political Framework, Standardization Framework, Validation Framework, Involvement
> Framework, Funding Framework*, whereas the prose names them *regulatory, standardization,
> involvement, funding and validation*. "Political" and "regulatory" are not reconciled.

The governance classes themselves are not enumerated in the prose. Figure 17, "Interaction of
governance classes and identification of related supporting frameworks", labels eight:
**society, technology, standards, academia, governmental, supply, testing, funding**.

### Policy and regulatory landscape

The wide policy and regulatory landscape aims at developing a data economy, e.g. through
interoperable energy services. The strategies and related pieces of legislation below have
been identified (and described) by int:net in its publication on "The regulatory framework
relevant for intent", as relevant for the development of interoperable energy services:

- **Data Economy Regulation**
  - Data Governance Act (DGA)
  - Digital Market Act
  - Data Act
  - Implementing Act on High-Value Datasets
  - Artificial Intelligence Act
- **Energy Transition Regulation**
  - Electricity Directive 2019/944
  - Implementing Regulation (EU) 2023/1162 — concerns interoperability requirements and
    non-discriminatory and transparent procedures for access to metering and consumption data
  - Network Code on Demand Response
  - Revision of the Renewable Energy Directive
  - Alternative Fuel Infrastructure Regulation
  - Energy Performance of Building Directive

As an example of institutional arrangement, the development of Commission Implementing
Regulation (EU) 2023/1162 involved governmental organisations (DG ENER, Electricity
Cross-Border Committee), energy supply associations (ENTSO-E, DSO Entity) and standards
organisations (CEN-CENELEC-ETSI Smart Grid Coordination Group). That regulation explicitly
calls for the involvement of consumer associations, electricity retailers, service and
technology providers, and component and equipment manufacturers, among other relevant
stakeholders, for and during the development of national practices by Member States.

**Data Act.** Particularly influential for data spaces are the Data Governance Act (DGA) and
the Data Act. The latter, under **Chapter VIII: Interoperability**, targets participants of
data spaces who offer data and data-based services to other participants, specifying
essential requirements to which said participants **shall be compliant**. The requirements
relate to the data sharing agreements (including for smart contracts), datasets, data
processing services, and relevant function, information and communication layer concepts.

**Data Governance Act.** The DGA is involved in the creation of a **European Data Innovation
Board (EDIB)**, as well as the definition of rules for Data Intermediation Services. As
specified under **Chapter VI: European Data Innovation Board, Article 29 (2)**, the EDIB is to
be formed of at least three subgroups, as follows:

a) a subgroup composed of the competent authorities for data intermediation services and the
   competent authorities for the registration of data altruism organisations
b) a subgroup for technical discussions on standardisation, portability and interoperability
c) a subgroup for stakeholder involvement

These three subgroups directly relate to the proposal for a 6th SGAM layer through the
consideration of regulation, standardisation and involvement frameworks. Specifically, the
third subgroup for stakeholder involvement refers to the involvement of "representatives from
industry, research, academia, civil society, standardisation organisations, relevant common
European data spaces and other relevant stakeholders and third parties", closely resembling
the proposed 6th layer roles found in the int:net Whitebook [12].

Furthermore, the DSSC categorises types of data space participants into ('highly likely to
be') private entities (e.g. gatekeepers) and public entities (e.g. public sector bodies),
while noting that the distinction between the two types is somewhat blurred (e.g. as in the
case of data intermediation service providers, data altruism organisations and researchers
and research organisations); supporting the approach of fostering interaction between
competent authorities for data intermediation (**DGA, article 13**) and for data altruism
(**DGA, article 23**), and potentially other competent authorities (**DGA, article 7**).
Finally, the European Interoperability Reference Architecture identifies target users (under
its scope of application, from within public administrations) as portfolio managers, business
analysts and architects [13].

Among other tasks (see **DGA, Article 30**), the EDIB is to advise the Commission on
cross-sector standards for the creation of common European data spaces, as well as to propose
guidelines for sector-specific and cross-sector interoperable frameworks of common standards
and practices, while ensuring adequate and non-discriminatory representation of stakeholders
in the governance of common European data spaces. In the energy sector, assisted by SGAM, the
formulation of said interoperable frameworks may be accompanied by the relevant interactions
of involved stakeholders.

While data intermediation services under the DGA have been inspired by common European data
spaces, and the corresponding set of rules aim at ensuring their adequate role within common
European data spaces, an intermediary of a data space (i.e. a party performing one, more or
all functions of a data space operator) "may, but must not necessarily be considered an
intermediation service provider", and thus fall within the scope of the Data Governance Act.
Hence, the Act's **Chapter III: Requirements applicable to data intermediation services** is
highly relevant to data spaces.

### Validation and conformance testing

Approaching the validation framework, various aspects of technical as well as semantic
interoperability for a federation of data spaces were tested by the cluster projects. The key
challenges and learnings of this interoperability testing are presented in the Position Paper
on Interoperability Framework in Energy Data Spaces [14], which also highlights the
importance of tools and standards towards achieving cross-data space interoperability.
Additionally, the EU's interoperability test bed has published a guide on governance
interoperability design and conformance testing, which **may serve as inspiration** for the
consideration of governance aspects as part of a conformance testing setup.

---

## 7.1.4. Fostering Interoperability in Organizations

Interoperability governance must find its expression in concrete action. To that end, the
int:net project has developed and tested a set of practical tools and guidelines that allow
all types of institutions testing and continuously improving their "interoperability
maturity":

### EMINENT

EMINENT is an **interoperability maturity model** developed in the int:net project, which
addresses the need for interoperability to be fostered as a business capability through
several key areas. These include:

- community facilitation — focusing on community growth and maintaining diversity of
  perspectives;
- establishing technical agreements and facilitating implementation;
- knowledge retention and operational alignment as organizations evolve their interoperability
  proficiency;
- user base growth, tool/product development, and market creation.

Essentially, the EMINENT framework highlights that interoperability isn't solely a technical
issue, but requires a holistic approach encompassing community building, technical
standardization, and strategic implementation to mature as a core organizational capability.

### IntMAS

The "Interoperability Management and Audit System" allows enterprises, associations and any
other type of institutions to implement a continuous improvement process in their management
practices and daily work. It has been modelled alongside proven management systems such as
**ISO 9001**, **ISO 14001** or **EMAS**. A comprehensive guideline (published as an annex to
the int:net Whitebook on "Engagement Towards Interoperability in Governance" [12]) describes a
step-by-step approach to implement IntMAS.

The guideline refers to a set of checklists and templates that allow for assessing the
interoperability quality level and creating the required management artefacts with limited
efforts. Upon completion of the IntMAS documentation, an AI supported assessment process
decides if the candidate will be allowed to use the respective quality label. The IntMAS
approved organizations are supposed to form a community in the framework of **IntPPC**, the
Interoperability People and Project Connector platform.

---

## 7.1.5. Joining Forces on Interoperability

Collaboration across multiple governance classes and entities is crucial. Towards the end of
the int:net project, a group of representatives from literally all governance classes formed
"The Think Tank on Interoperability Governance" (TTT). As a result of the TTT meeting in
Vienna on June 25, 2025, a joint position paper has been prepared outlining insights and
recommendations on:

- Governance is the Cornerstone of Energy Interoperability.
- Standardization Enables Global Energy Integration.
- Interoperability Accelerates Innovation and Decarbonization.
- Adaptable Governance is needed for a Dynamic Energy Landscape.
- Energy transition needs cross-sector collaboration.
- A common understanding of infrastructure makes us more resilient.

The Think Tank will be maintained and expanded as needed on the IntPPC platform after the end
of the int:net project.

---

## Standards and protocols

Identifiers are reproduced exactly as the chapter writes them. Where the "Version / profile"
cell is `—`, the source gives none.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| dataspace protocol | — | Minimum standard of communication between connectors; publish data, negotiate agreements, access data; "transfer process protocols" for access | required (prerequisite for joining any data space) |
| JSON | — | Data interchange format, named "the main reference" | recommended |
| JSON-LD | — | Serializes linked data in JSON; "specific proposed solution"; also listed as a concrete RDF syntax `[JSON-LD]` | recommended |
| RDF | — | Framework for expressing linked data as triples; ontology-based approaches are stated to be a requirement to avoid silos | recommended |
| Turtle `[TURTLE]` | — | Concrete RDF syntax | referenced |
| TriG `[TRIG]` | — | Concrete RDF syntax | referenced |
| SAREF | — | Behind-the-meter-equipments | recommended |
| IEC 61970 | — | Grid modelling | recommended |
| IEC 62325 ESMP | ESMP | Flexibility market interfaces | recommended |
| IEC 62746 | — | Service provided to technical aggregator communication | recommended |
| IEC 61850-7 | part -7 | Advanced DER controls | recommended |
| OCPP | — | Public Charging Point interfaces | recommended |
| Open Data Protocol (OData) | — | Named among the data models/protocols CEEDS relies on | recommended |
| CIM data model and associated ontologies | — | "the overarching CIM data model" | recommended |
| CGMES Conformity Assessment Scheme (CAS) | — | ENTSO-E scheme, named "as an example of conformity assessment in the Energy domain" | referenced |
| SGAM | five interoperability layers; proposed 6th "framework" layer | Layering used to map governance building blocks and to assist formulation of interoperable frameworks | referenced |
| DERA | 3.1 (governance model); "latest implementation plans" (actors) | Reference architecture whose governance components are mapped to SGAM layers; alignment target for the definition of actors | referenced |
| European Interoperability Framework (EIF) Toolbox | — | Frame of reference for the grouping of interoperability requirements | referenced |
| European Interoperability Reference Architecture (EIRA) | — | Identifies target users (portfolio managers, business analysts, architects) | referenced |
| ISO 9001 · ISO 14001 · EMAS | — | Management systems IntMAS is modelled alongside | referenced |
| EMINENT | — | int:net interoperability maturity model | referenced |
| IntMAS | — | int:net Interoperability Management and Audit System, with quality label | referenced |
| GDPR | — | Data access enabled by the governance framework must comply with it | required |
| Data Act, Chapter VIII: Interoperability | Regulation (EU) 2023/2854 | Essential requirements with which participants offering data and data-based services shall be compliant | required |
| Data Governance Act, Chapter III / Chapter VI / Articles 7, 13, 23, 29(2), 30 | Regulation (EU) 2022/868 | Rules for data intermediation services; establishment and tasks of the EDIB | required |

---

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its
requirements.*

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-INT-01` | Interoperability requirements are grouped into technical, semantic and governance interoperability, referring to the European Interoperability Framework (EIF) Toolbox. | informative | `Blueprint_CEEDS_v3.0.txt:2710-2714` |
| `CEEDS-INT-02` | A minimum technical framework is required for all participants of a data space in the energy domain. | must | `Blueprint_CEEDS_v3.0.txt:2719-2722` |
| `CEEDS-INT-03` | Participants must be able to process and understand the information (metadata) of the services/data offered in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2719-2722` |
| `CEEDS-INT-04` | Participants must be able to perform data transfers between them. | must | `Blueprint_CEEDS_v3.0.txt:2719-2722` |
| `CEEDS-INT-05` | The technical interoperability framework covers building blocks, actors, data formats and data transmission protocols. | informative | `Blueprint_CEEDS_v3.0.txt:2722-2726` |
| `CEEDS-INT-06` | A "data space connector" component provides an endpoint enabling actors to participate in a data space; it is used in most data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:2728-2730` |
| `CEEDS-INT-07` | (Shared) registries and services are needed to provide common/shared functionalities in a data space, for example to register the participants. | must | `Blueprint_CEEDS_v3.0.txt:2730-2732` |
| `CEEDS-INT-08` | Nine technical building blocks are defined, grouped into Data interoperability, Data sovereignty and trust, and Data value creation. | informative | `Blueprint_CEEDS_v3.0.txt:2737-2745` |
| `CEEDS-INT-09` | Data interoperability covers the capabilities needed for the exchange of data: (semantic) models, data formats and interfaces (APIs), including functionalities for provenance & traceability. | informative | `Blueprint_CEEDS_v3.0.txt:2738-2739` |
| `CEEDS-INT-10` | Data sovereignty and trust covers identification of participants and assets, establishment of trust, and the possibility to define and enforce policies for access and usage control. | informative | `Blueprint_CEEDS_v3.0.txt:2740-2742` |
| `CEEDS-INT-11` | Data value creation covers registering and discovering data offerings or services, providing marketplace functionality and enabling monetization of data sharing. | informative | `Blueprint_CEEDS_v3.0.txt:2743-2745` |
| `CEEDS-INT-12` | There is not a direct one-to-one correspondence between building blocks and technical components; a single technical component may be associated with multiple building blocks. | informative | `Blueprint_CEEDS_v3.0.txt:2755-2757` |
| `CEEDS-INT-13` | The control plane and the data plane must be differentiated. | must | `Blueprint_CEEDS_v3.0.txt:2758-2759` |
| `CEEDS-INT-14` | The control plane determines how data is managed, routed and processed, including user identification and the enforcement of access and usage policies. | informative | `Blueprint_CEEDS_v3.0.txt:2759-2763` |
| `CEEDS-INT-15` | The data plane performs the actual movement — the physical exchange — of data. | informative | `Blueprint_CEEDS_v3.0.txt:2761-2763` |
| `CEEDS-INT-16` | The control plane can be standardized at a high level, incorporating common standards for identification and authentication. | may | `Blueprint_CEEDS_v3.0.txt:2763-2764` |
| `CEEDS-INT-17` | The data plane may vary across different data spaces, adapting to diverse data exchange requirements. | may | `Blueprint_CEEDS_v3.0.txt:2764-2768` |
| `CEEDS-INT-18` | A common definition of actors, in line with the latest implementation plans of DERA, and of their possible interactions, is important. | should | `Blueprint_CEEDS_v3.0.txt:2773-2775` |
| `CEEDS-INT-19` | The main actors are Data Space Governance Authority, Data Space, Participant, Participant Agent, Data Space Registry, Credential Issuer, and Identity/Authentication & Authorization, Identity provider. | informative | `Blueprint_CEEDS_v3.0.txt:2775-2793` |
| `CEEDS-INT-20` | JSON is the main reference data interchange format. | recommended | `Blueprint_CEEDS_v3.0.txt:2805-2807` |
| `CEEDS-INT-21` | JSON-LD, which serializes linked data in JSON, is the specific proposed solution. | recommended | `Blueprint_CEEDS_v3.0.txt:2807-2808` |
| `CEEDS-INT-22` | To share data between autonomous entities, metadata is required to facilitate the transfer of datasets, utilizing a data transfer (or application layer) protocol. | must | `Blueprint_CEEDS_v3.0.txt:2816-2818` |
| `CEEDS-INT-23` | The dataspace protocol outlines how transfer metadata is provisioned, including dataset deployment and the syntactic expression and electronic negotiation of agreements governing data usage. | informative | `Blueprint_CEEDS_v3.0.txt:2817-2820` |
| `CEEDS-INT-24` | Datasets are accessed using "transfer process protocols". | informative | `Blueprint_CEEDS_v3.0.txt:2818-2820` |
| `CEEDS-INT-25` | The dataspace protocol ensures fundamental technical interoperability for participants, a prerequisite for joining any data space. | must | `Blueprint_CEEDS_v3.0.txt:2830-2832` |
| `CEEDS-INT-26` | The dataspace protocol defines the minimum standard of communication so that each actor manages to communicate with other connectors, even if those connectors deploy different features, semantic models or business procedures. | informative | `Blueprint_CEEDS_v3.0.txt:2832-2834` |
| `CEEDS-INT-27` | CEEDS relies on SAREF for behind-the-meter-equipments. | recommended | `Blueprint_CEEDS_v3.0.txt:2848-2851` |
| `CEEDS-INT-28` | CEEDS relies on IEC 61970 for grid modelling. | recommended | `Blueprint_CEEDS_v3.0.txt:2850-2851` |
| `CEEDS-INT-29` | CEEDS relies on IEC 62325 ESMP for flexibility market interfaces. | recommended | `Blueprint_CEEDS_v3.0.txt:2850-2851` |
| `CEEDS-INT-30` | CEEDS relies on IEC 62746 for service provided to technical aggregator communication. | recommended | `Blueprint_CEEDS_v3.0.txt:2851-2852` |
| `CEEDS-INT-31` | CEEDS relies on IEC 61850-7 for advanced DER controls. | recommended | `Blueprint_CEEDS_v3.0.txt:2851-2852` |
| `CEEDS-INT-32` | CEEDS relies on OCPP for Public Charging Point interfaces. | recommended | `Blueprint_CEEDS_v3.0.txt:2852` |
| `CEEDS-INT-33` | CEEDS relies on the Open Data Protocol (OData). | recommended | `Blueprint_CEEDS_v3.0.txt:2852-2853` |
| `CEEDS-INT-34` | CEEDS relies on the overarching CIM data model and associated ontologies. | recommended | `Blueprint_CEEDS_v3.0.txt:2853` |
| `CEEDS-INT-35` | The CGMES Conformity Assessment Scheme (CAS), developed by ENTSO-E, is named as an example of conformity assessment in the Energy domain. | informative | `Blueprint_CEEDS_v3.0.txt:2853-2855` |
| `CEEDS-INT-36` | In data spaces where there is data exchange, approaches based on data ontology are a requirement in order to avoid silos. | must | `Blueprint_CEEDS_v3.0.txt:2856-2857` |
| `CEEDS-INT-37` | Relationships among data instances must be provided in a machine-readable format, since external systems cannot otherwise know about them. | must | `Blueprint_CEEDS_v3.0.txt:2857-2858` |
| `CEEDS-INT-38` | RDF expresses linked data as triples (subject, predicate, object) and uses URIs to name the relationship and both ends of the link. | informative | `Blueprint_CEEDS_v3.0.txt:2858-2863` |
| `CEEDS-INT-39` | Concrete syntaxes for RDF include Turtle [TURTLE], TriG [TRIG] and JSON-LD [JSON-LD]. | informative | `Blueprint_CEEDS_v3.0.txt:2863-2864` |
| `CEEDS-INT-40` | Vocabulary Hubs, where different data models are published, are key to link the Marketplace for data/service offering discovery. | should | `Blueprint_CEEDS_v3.0.txt:2865-2868` |
| `CEEDS-INT-41` | By adhering to semantic and syntactic standards, open data sources can align their data structures and semantics. | informative | `Blueprint_CEEDS_v3.0.txt:2879-2881` |
| `CEEDS-INT-42` | Ten governance building blocks are defined along the SGAM layers to address the governance of interoperability. | informative | `Blueprint_CEEDS_v3.0.txt:2886-2891` |
| `CEEDS-INT-43` | The governance components are mapped to the local and federated parts and to the five SGAM interoperability layers. | informative | `Blueprint_CEEDS_v3.0.txt:2886-2890` |
| `CEEDS-INT-44` | The governance framework must acknowledge the diversity of platforms and systems, tailored to various market designs and business processes. | must | `Blueprint_CEEDS_v3.0.txt:2891-2892` |
| `CEEDS-INT-45` | The governance framework should promote cross-stakeholder, cross-border, and cross-sector data exchanges. | should | `Blueprint_CEEDS_v3.0.txt:2892-2893` |
| `CEEDS-INT-46` | The governance framework should guarantee convenient data access that complies with GDPR requirements. | should | `Blueprint_CEEDS_v3.0.txt:2893-2894` |
| `CEEDS-INT-47` | The governance model should facilitate coordination between TSO and DSO from a customer perspective. | should | `Blueprint_CEEDS_v3.0.txt:2894-2896` |
| `CEEDS-INT-48` | The governance model should ensure scalability through the open-interoperable principles, leveraging common open-source components and agreed-upon rules. | should | `Blueprint_CEEDS_v3.0.txt:2895-2896` |
| `CEEDS-INT-49` | The inclusion of a 6th SGAM layer, named "framework" layer, is proposed, because the 5th layer cannot cover political, regulatory or societal interoperability. | informative | `Blueprint_CEEDS_v3.0.txt:2903-2908` |
| `CEEDS-INT-50` | The framework layer addresses interoperability among a named set of energy domain stakeholders, from policymakers and regulatory bodies to finance and investment institutions. | informative | `Blueprint_CEEDS_v3.0.txt:2908-2925` |
| `CEEDS-INT-51` | The 6th layer framework promotes five common frameworks: regulatory, standardization, involvement, funding and validation. | informative | `Blueprint_CEEDS_v3.0.txt:2950-2958` |
| `CEEDS-INT-52` | A named set of Data Economy and Energy Transition legal instruments is identified as relevant for the development of interoperable energy services. | informative | `Blueprint_CEEDS_v3.0.txt:2966-2984` |
| `CEEDS-INT-53` | Participants of data spaces who offer data and data-based services to other participants shall be compliant with the essential requirements of the Data Act, Chapter VIII: Interoperability. | must | `Blueprint_CEEDS_v3.0.txt:3012-3015` |
| `CEEDS-INT-54` | Those essential requirements relate to data sharing agreements (including for smart contracts), datasets, data processing services, and relevant function, information and communication layer concepts. | informative | `Blueprint_CEEDS_v3.0.txt:3015-3017` |
| `CEEDS-INT-55` | The EDIB is to be formed of at least three subgroups, per Data Governance Act Chapter VI, Article 29 (2). | must | `Blueprint_CEEDS_v3.0.txt:3018-3025` |
| `CEEDS-INT-56` | The EDIB is to advise the Commission on cross-sector standards for the creation of common European data spaces. | must | `Blueprint_CEEDS_v3.0.txt:3054-3056` |
| `CEEDS-INT-57` | The EDIB is to propose guidelines for sector-specific and cross-sector interoperable frameworks of common standards and practices. | must | `Blueprint_CEEDS_v3.0.txt:3055-3056` |
| `CEEDS-INT-58` | The EDIB is to ensure adequate and non-discriminatory representation of stakeholders in the governance of common European data spaces. | must | `Blueprint_CEEDS_v3.0.txt:3056-3058` |
| `CEEDS-INT-59` | An intermediary of a data space — a party performing one, more or all functions of a data space operator — "may, but must not necessarily be considered an intermediation service provider", and thus fall within the scope of the Data Governance Act. | may | `Blueprint_CEEDS_v3.0.txt:3062-3068` |
| `CEEDS-INT-60` | The Data Governance Act's Chapter III: Requirements applicable to data intermediation services is highly relevant to data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:3067-3068` |
| `CEEDS-INT-61` | The EU interoperability test bed guide on governance interoperability design and conformance testing may serve as inspiration for considering governance aspects as part of a conformance testing setup. | may | `Blueprint_CEEDS_v3.0.txt:3071-3097` |
| `CEEDS-INT-62` | EMINENT is an interoperability maturity model addressing interoperability as a business capability across community facilitation, technical agreements, knowledge retention, user base growth, tool/product development and market creation. | informative | `Blueprint_CEEDS_v3.0.txt:3101-3119` |
| `CEEDS-INT-63` | IntMAS lets institutions implement a continuous improvement process, modelled alongside ISO 9001, ISO 14001 or EMAS. | informative | `Blueprint_CEEDS_v3.0.txt:3129-3133` |
| `CEEDS-INT-64` | Upon completion of the IntMAS documentation, an AI supported assessment process decides if the candidate will be allowed to use the respective quality label. | informative | `Blueprint_CEEDS_v3.0.txt:3144-3147` |
| `CEEDS-INT-65` | IntMAS approved organizations are supposed to form a community in the framework of IntPPC, the Interoperability People and Project Connector platform. | should | `Blueprint_CEEDS_v3.0.txt:3147-3148` |
| `CEEDS-INT-66` | The Think Tank on Interoperability Governance (TTT) position paper outlines six insights and recommendations, from "Governance is the Cornerstone of Energy Interoperability" to "A common understanding of infrastructure makes us more resilient". | informative | `Blueprint_CEEDS_v3.0.txt:3151-3164` |

---

## Open questions

1. **No section 7.1.** The chapter numbering runs from "7. Interoperability Aspects" straight
   to "7.1.1. Technical Interoperability", and every subsection is numbered `7.1.x`. The
   source's table of contents lists it the same way, so this is not a text-extraction
   artefact.

2. **The stated grouping does not cover the whole chapter.** The opening paragraph groups the
   interoperability requirements into technical, semantic and governance interoperability
   (7.1.1–7.1.3), but the chapter then continues with 7.1.4 "Fostering Interoperability in
   Organizations" and 7.1.5 "Joining Forces on Interoperability", which are outside that
   grouping.

3. **The nine technical building blocks are never named in prose.** Only Figure 13 names
   them. The figure is credited to reference [1], the DSSC Blueprint **v1.0**, and its labels
   are not the building-block names used by later DSSC Blueprint versions. CEEDS asserts no
   mapping, so none is stated on this page.

4. **Figure 13 shows three elements outside the nine** — "Data Space Protocols", "Federated
   Services" and "Data Space Registry" — whose relation to the nine building blocks is not
   explained.

5. **"Data Space Registry" is used in two senses**: as an element of Figure 13 and as one of
   the seven actors listed in 7.1.1.2.

6. **The actor list's last entry is compound.** "Identity/Authentication & Authorization,
   Identity provider" may denote one actor or two; Figure 14 shows a single box, "Identity
   Provider". The bullet list has seven entries, but the source never states an actor count.

7. **A footnote URL does not match its referent.** The footnote for the DSBA "technical
   convergence paper" points to the European Commission's Data Governance Act explainer page.
   The paper itself is reference [10] in the bibliography.

8. **The ten governance building blocks are never listed in prose.** The list in
   §7.1.3 above is read off Figure 15 by taking the ten colour-highlighted blocks; the
   figure also contains non-highlighted context blocks, and a vertical band at the
   local/federated boundary whose label is partly obscured by overlapping shapes.

9. **Figure 16 and the prose disagree on the framework names.** Figure 16 labels the 6th
   layer's five bands *Political Framework, Standardization Framework, Validation Framework,
   Involvement Framework, Funding Framework*; the prose names them *regulatory,
   standardization, involvement, funding and validation*. A third phrasing appears later —
   "regulation, standardisation and involvement frameworks".

10. **Governance classes are never enumerated in prose.** Figure 17 labels eight — society,
    technology, standards, academia, governmental, supply, testing, funding — but the text
    only refers to "governance classes" generically.

11. **"may, but must not necessarily be considered"** (on data space intermediaries and the
    Data Governance Act) reads, literally, as a prohibition, but in context appears to mean
    "need not". Quoted verbatim above rather than resolved.

12. **A footnote marker has no footnote.** The marker attached to "IntPPC, the
    Interoperability People and Project Connector platform" is numbered 27, but no footnote
    27 appears on that page or the next; the chapter's footnotes otherwise run 12–22. No URL
    or definition for IntPPC is therefore given.

13. **Standards are named without versions or profiles.** "SAREF", "OCPP", "IEC 61970",
    "OData", "CIM" and the "dataspace protocol" carry no version, edition or profile
    identifier. Only "IEC 61850-7" and "IEC 62325 ESMP" are qualified, and only to part or
    profile level.

14. **DERA is cited at two different granularities**: "the latest implementation plans of
    DERA" (7.1.1.2, no version) and "the DERA 3.1 model" (7.1.3).

15. **The EIF reference is unspecific.** The chapter says its grouping refers to the EIF
    Toolbox "addressing the applicable layers", without stating which EIF layers apply or how
    the three CEEDS groupings map onto them.

16. **Normative force is often carried by non-modal phrasing.** "As the main reference"
    (JSON), "specific proposed solution" (JSON-LD), "relies on the harmonization and usage of
    … such as" (the energy standards) and "are key to" (Vocabulary Hubs) are not expressed
    with *must*/*should*/*may*. The Force column above records the closest reading and quotes
    the governing phrase; treat those rows as weaker than an explicit modal.
