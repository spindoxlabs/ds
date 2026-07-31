# Introduction and Data Spaces Concept

> **Source** · Blueprint of the Common European Energy Data Space (CEEDS), int:net, v3.0, September 2025
> **Chapters** · 1. Introduction (incl. 1.1. Scope) · 2. Data Spaces Concept (incl. 2.1. Overall Strategies, 2.2. Defining Data Spaces Across Diverse Uses)

These two opening chapters state what the CEEDS blueprint is for and on what conceptual basis it rests. Chapter 1 frames the energy transition as the driver, states the blueprint's scope — a framework for economically feasible business use cases plus the general data space architecture that enables them — and positions the CEEDS architecture as an intended specialization of the mandatory part of the DSSC. Chapter 2 adopts the DSSC Blueprint v1.0 definition of a data space, sets out three transversal features and five deployment dimensions, describes the federation strategy CEEDS pursues, and catalogues the categories of data spaces across uses.

## 1. Introduction

The blueprint opens with non-normative framing prose. The shift in the energy sector, "outlined as a key aspect of the Green Deal and detailed in the REPowerEU plan", is said to necessitate a widespread substitution of fossil-fuel-based power generation with low-CO₂ technologies. Central to this transformation is the electrical grid, whose significance has heightened due to the increased electrification of sectors like mobility as well as temperature control of buildings. The source states that Europe requires an electrical network that is "resilient, cyber-secure, flexible, and reliable", and that meeting this demand is contingent on the implementation of advanced automation and power flow optimisation solutions as well as the comprehensive digitalization of entire energy systems.

Data spaces are presented as playing a pivotal role in advancing the digitalization of electrical energy systems, addressing "both the new business opportunities as well as the existing technical challenges". The stated contributions are:

- facilitating predictive analytics, enabling proactive maintenance and reducing downtime in critical components of the electrical grid;
- supporting the deployment of advanced automation and grid capacity optimisation solutions, enabling adaptive and responsive grids that can dynamically adjust to changing energy demands and supply conditions;
- promoting collaboration among various stakeholders, including utilities, regulators, technology providers, and consumers — a collaborative environment that "fosters innovation, accelerates the development of smart technologies, and ensures a more inclusive and participatory approach to the energy transition".

This chapter carries no normative statements; it is context for the chapters that follow.

### 1.1. Scope

The document addresses the concept of a Common European Energy Data Space (CEEDS), "providing detailed approaches and recommendations for its real-world realization". The main objective of the blueprint is stated as guiding on **enhancing the existing data infrastructures, the energy domain, towards the full embracement of data space solutions**. Bridging this gap is said to empower the introduction of novel energy services, increasing the efficiency and reliability of the energy systems while providing substantial benefits for every stakeholder.

The key scope is to present two things:

1. a framework for new economically feasible business use cases; and
2. the general data space architecture that can enable them.

That architecture "aims to interconnect the existing data infrastructures, composed of a diversity of heterogeneous systems operated by different actors, with federated data spaces"; technical specifications have been included at this scope.

**Origin of the architecture.** int:net has cooperated with the sister projects, forming the Energy Data Space Cluster Projects (EDSCP), and the energy community, to identify the specific vertical capabilities that are needed in an energy data space. The result is stated to be the CEEDS architecture blueprint that meets the need of the domain.

**Relationship to the DSSC.** The source states the relationship as a forward-looking objective rather than an accomplished fact:

> The objective in the future is that the CEEDS architecture is a specialization of the mandatory part of the Dataspace Support Centre (DSSC) and of future data space standards.

This "will require further coordination with future initiatives for convergence, e.g., a description of DSSC structured into a reference part and a pattern part as recommended in current standards on reference architectures (ISO/IEC/IEEE 42042 - reference architecture, ISO/IEC 40131 - guidance for reference architecture)". The blueprint then issues an explicit recommendation addressed outside itself: *"It is recommended that the European Commission start a transversal task force between the data space architects in various initiatives to enable this alignment."*

**Figure 1 — Ensuring alignment between the DSSC and the CEEDS Blueprints.** The figure is a five-box flow. Rendered as labelled edges exactly as drawn:

| From | Edge label | To |
|---|---|---|
| DSSC Reference Architecture | Includes | CEEDS Reference Architecture Patterns |
| DSSC Reference Architecture | *(unlabelled)* | CEEDS Reference Architecture |
| CEEDS Reference Architecture | Includes | CEEDS Blueprint Patterns |
| CEEDS Reference Architecture | Applies to | CEEDS Blueprint |
| CEEDS Blueprint | Guides implementation | CEEDS Based Data Space |

The accompanying prose describes the same figure as a progression "from high-level reference architectures to the implementation of a CEEDS-based data space": at the foundational level, the DSSC Reference Architecture informs the CEEDS Reference Architecture, which is further refined through CEEDS Reference Architecture Patterns and CEEDS Blueprint Patterns; these patterns contribute to the development of the CEEDS Blueprint, which ultimately serves as the basis for a CEEDS-Based Data Space, "ensuring a structured and standardized approach to data space implementation". (See "Open questions" — the figure's edges and the prose do not attach the CEEDS Reference Architecture Patterns to the same box.)

**Organization of the blueprint**, as the source states it:

- Section 2 — general insights into the data space concepts and, particularly, specifically related to the energy domain;
- Section 3 — the reference use cases for CEEDS;
- Section 4 — the proposed architecture that enables their realization;
- Section 5 — the implementations of the building blocks;
- Section 6 — Governance of the CEEDS;
- Section 7 — notable insights and references for the technical, semantic and governance interoperability of energy data spaces;
- Section 8 — conclusions.

## 2. Data Spaces Concept

The conceptualization of data spaces "was initiated several years ago, providing the basis for characterization in specific domains like energy". Taking a domain-agnostic perspective, the blueprint adopts the DSSC definition verbatim, attributing it to the DSSC Blueprint v1.0 (reference [1]):

> "Interoperable framework, based on common governance principles, standards, practices and enabling services, that enables trusted data transactions between participants."

### Transversal features

Considering this definition, **three transversal features must be considered in the data space deployment**:

| Transversal feature | Description (source's own wording) |
|---|---|
| **Security and Privacy** | Concentrating on ensuring the security and privacy of the exchanged data within the designated data space. |
| **Quality and Integrity** | Relating to the quality and integrity of the data residing within the data space. This encompasses elements associated with metadata, such as data validation, data cleansing, data accuracy, and data consistency. |
| **Governance and Policy** | Encompassing the structure of governance and policies dictating the data spaces, addressing decision-making, data governance frameworks (comprising rules and practices for management and operations), policies for data sharing and access, as well as energy-related policies and regulations. |

### Five main dimensions

"Furthermore, the deployment of a data space is performed according to five main dimensions, which reflect the transversal features described above."

| Dimension | Description (source's own wording) |
|---|---|
| **Business** | Examining the business model related to data exchange, such as utilizing consumption data for managing flexibility transactions in the wholesale market and delineating the business roles of involved parties. |
| **Legal** | Delving into the legal framework, encompassing (a) overarching legal frameworks, (b) organizational aspects, and (c) contractual instruments. |
| **Operation** | Providing insights into the operational framework, including use cases, processes, and activities. |
| **Functional** | Describing the technical and governance building blocks, deployed based on necessary technical services (and their dependencies), as well as adherence to data standards. |
| **Technology** | Offering specifications on adopted standards or required software components, as identified in the energy domain through the Smart Grid Architecture Model (SGAM). A primary objective is to ensure interoperability among internal parties and with other data spaces. |

The source then states the obligation that binds them together: the realization of a data space in the energy domain **must** address every indicated dimension and implement the required measures to achieve interoperable solutions. Even where existing solutions are already in place and well advanced for individual dimensions — the examples given are "an operational framework for grid management" and "a standardized data model, with associated data exchange profiles, that addresses a specific interoperability point" — "consistent work must be deployed to synchronize and align all the different dimensions simultaneously and in a defined system".

### 2.1. Overall Strategies

From the overall viewpoint at the highest level, the CEEDS "is foreseen as the common framework that federates different data spaces (each of which is implemented at the national, sub-national level or international level) and allows the participation of the single users". Different layers are defined, from the local data space solutions to the federated ecosystem of data spaces, following a decentralized configuration.

**Figure 2 — Possible ecosystems strategies for data spaces (adapted from [2]).** Three panels, titled in the figure as:

| Panel | Figure title | Description in the prose |
|---|---|---|
| I | i) Closed Ecosystem | The starting point, on the left. |
| II | ii) Open Ecosystem | A further expansion consisting of implementing data exchanges with external participants (who, in any case, subscribe to the governance rules), achieving an open, interoperable ecosystem. |
| III | iii) Federation of Data Exchange Platforms | The next expansion: the structured interactions among different ecosystems (i.e., following the interoperability of the specific governance rules) allow to reach the ecosystem of data space solutions, as a federation. |

The figure carries a legend, reproduced as drawn:

- **Roles**: Participants (data provider / data consumer); Federator.
- **Data exchanges**: Payload data (incl. metadata between participants); Metadata between participants and federator; Metadata between federators.
- **Ecosystems/Platforms**: Closed; Open.

"It is worth highlighting that the participation of single users, defined in the CEEDS through the Harmonised Electricity Market Role Model (HEMRM)[^1], remains a foremost feature in the federation of ecosystems."

The federation of ecosystems is stated to be "the model that will be pursued to interconnect the data space instances of the cluster projects, paving the way for the CEEDS". This federation "relies on specific measures for technical, semantic and governance interoperability, which will be described in section 5 of the present document" (see "Open questions" on that cross-reference).

[^1]: The harmonised electricity market role model (HEMRM) — https://www.entsoe.eu/data/cim/role-models/

### 2.2. Defining Data Spaces Across Diverse Uses

Data spaces "have emerged as a foundational element for fostering innovation, enhancing interoperability, and ensuring governance across various sectors". These collaborative environments[^2] enable stakeholders to share, access, and manage data securely. The concept "transcends traditional data management approaches by emphasizing user control, privacy, and the seamless exchange of information across diverse interoperable, orchestrated ecosystems".

The multifaceted roles and the objectives data spaces serve are listed as:

1. **Educational Purpose and Research**: Facilitating access to vast datasets and fostering collaborative research environments, the data spaces enhance educational outcomes and drive forward scientific inquiry and innovation.
2. **Data Exchange and Interoperability**: By enabling the secure and efficient exchange of data between actors of the energy value chain, data spaces overcome interoperability challenges, ensuring seamless interaction across different systems and platforms.
3. **Innovation and New Business Models**: Data spaces act as incubators for new business models, supporting startups and established businesses alike in developing innovative services and products through shared data insights and access.
4. **Data Analysis and Visualization**: Providing powerful tools for data analysis and visualization, data spaces empower organizations to derive meaningful insights from complex datasets, enhancing decision-making processes.
5. **Governance and Regulation**: Data spaces can act as data-driven frameworks, evidence-based for supporting public authorities and national agencies at different levels to enhance decision-making processes, streamline regulatory compliance, and foster transparent governance mechanisms. This infrastructure enables the effective monitoring, analysis, and dissemination of information critical to societal welfare, economic stability, and environmental sustainability.

**Table 1 — Categories of data spaces.** Reproduced with its own column headers ("Data Space Categories" is the table's banner row).

| Categories | Scope and Description |
|---|---|
| **Educational Purpose and Research** | Data spaces support the sharing of educational resources, academic research, and collaboration across institutions and countries. They enable access to a wide range of data, fostering innovation and knowledge dissemination. |
| **Data Exchange and Interoperability** | They are crucial for enabling the exchange of data between different entities, improving interoperability among diverse systems and platforms. This facilitates seamless data sharing and collaboration across sectors, enhancing service delivery and operational efficiency.[^3] |
| **Innovation and New Business Models** | By allowing secure and controlled access to data, data spaces drive innovation, supporting the development of new business models, products, and services. They enable companies to leverage shared data for creating value-added services and improving competitive advantage.[^4] |
| **Data Analysis and Visualization** | Data spaces facilitate the transformation of data into actionable insights through advanced analysis and visualization tools. This enables more informed decision-making and reveals hidden trends, driving efficiency and strategic initiatives. |
| **Governance and Regulation** | Data spaces can empower public authorities and agencies to enhance regulatory frameworks and improve the governance of society and systems. By providing a reliable infrastructure for data governance and compliance, they support the development of more effective policies and governance models. |

[^2]: https://datacollaboratives.org/
[^3]: https://www.gradiant.org/en/blog/data-spaces-europe/
[^4]: https://www.geograma.com/en/blog/common-data-spaces-their-usefulness-and-current-situation-in-the-european-union/

## Standards and protocols

These chapters name no data-exchange protocols. The external references they do carry are reference-architecture standards, domain models and one upstream blueprint. Names and numbers are reproduced exactly as printed.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| DSSC Blueprint | v1.0 (reference [1]) | Source of the adopted, domain-agnostic definition of a data space | required — the definition is adopted verbatim |
| Dataspace Support Centre (DSSC) | mandatory part; and "future data space standards" | The CEEDS architecture is intended, in the future, to be a specialization of it | stated as a future objective |
| ISO/IEC/IEEE 42042 | — ("reference architecture") | Cited as a current standard on reference architectures recommending a reference part / pattern part split, which convergence with DSSC would follow | referenced |
| ISO/IEC 40131 | — ("guidance for reference architecture") | Cited alongside the above for the same recommendation | referenced |
| Harmonised Electricity Market Role Model (HEMRM) | — (entsoe.eu/data/cim/role-models/) | The model through which the participation of single users is defined in the CEEDS | informative |
| Smart Grid Architecture Model (SGAM) | — | The means by which adopted standards or required software components are identified in the energy domain, under the Technology dimension | informative |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Force reflects the source's own modal wording: `must` and `recommended` are used only where the source uses them; declarative and forward-looking statements are marked `informative`.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-CON-01` | The blueprint's main objective is to guide on enhancing the existing data infrastructures, the energy domain, towards the full embracement of data space solutions. | informative | `Blueprint_CEEDS_v3.0.txt:206-212` |
| `CEEDS-CON-02` | The key scope is to present (i) a framework for new economically feasible business use cases and (ii) the general data space architecture that can enable them. | informative | `Blueprint_CEEDS_v3.0.txt:213-214` |
| `CEEDS-CON-03` | The architecture aims to interconnect the existing data infrastructures — a diversity of heterogeneous systems operated by different actors — with federated data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:214-222` |
| `CEEDS-CON-04` | The CEEDS architecture blueprint is the result of int:net cooperating with the sister projects forming the Energy Data Space Cluster Projects (EDSCP), and with the energy community, to identify the specific vertical capabilities needed in an energy data space. | informative | `Blueprint_CEEDS_v3.0.txt:224-226` |
| `CEEDS-CON-05` | The objective in the future is that the CEEDS architecture is a specialization of the mandatory part of the Dataspace Support Centre (DSSC) and of future data space standards. | informative | `Blueprint_CEEDS_v3.0.txt:227-228` |
| `CEEDS-CON-06` | That alignment will require further coordination with future initiatives for convergence — e.g. a description of DSSC structured into a reference part and a pattern part, as recommended in ISO/IEC/IEEE 42042 (reference architecture) and ISO/IEC 40131 (guidance for reference architecture). | informative | `Blueprint_CEEDS_v3.0.txt:228-232` |
| `CEEDS-CON-07` | The European Commission is recommended to start a transversal task force between the data space architects in various initiatives to enable this alignment. | recommended | `Blueprint_CEEDS_v3.0.txt:232-233` |
| `CEEDS-CON-08` | The DSSC Reference Architecture informs the CEEDS Reference Architecture. | informative | `Blueprint_CEEDS_v3.0.txt:233-239` (Figure 1, p. 7) |
| `CEEDS-CON-09` | The CEEDS Reference Architecture is further refined through CEEDS Reference Architecture Patterns and CEEDS Blueprint Patterns. | informative | `Blueprint_CEEDS_v3.0.txt:236-238` |
| `CEEDS-CON-10` | Those patterns contribute to the development of the CEEDS Blueprint. | informative | `Blueprint_CEEDS_v3.0.txt:237-239` |
| `CEEDS-CON-11` | The CEEDS Blueprint serves as the basis for — and guides the implementation of — a CEEDS-Based Data Space. | informative | `Blueprint_CEEDS_v3.0.txt:238-239` (Figure 1, p. 7) |
| `CEEDS-CON-12` | A data space is defined, domain-agnostically, as an "Interoperable framework, based on common governance principles, standards, practices and enabling services, that enables trusted data transactions between participants." (DSSC Blueprint v1.0) | informative | `Blueprint_CEEDS_v3.0.txt:262-266` |
| `CEEDS-CON-13` | Data space deployment must consider the transversal feature Security and Privacy: ensuring the security and privacy of the exchanged data within the designated data space. | must | `Blueprint_CEEDS_v3.0.txt:267-269` |
| `CEEDS-CON-14` | Data space deployment must consider the transversal feature Quality and Integrity: the quality and integrity of the data residing within the data space, including metadata-associated elements such as data validation, data cleansing, data accuracy and data consistency. | must | `Blueprint_CEEDS_v3.0.txt:267-272` |
| `CEEDS-CON-15` | Data space deployment must consider the transversal feature Governance and Policy: governance structure and policies, decision-making, data governance frameworks, policies for data sharing and access, and energy-related policies and regulations. | must | `Blueprint_CEEDS_v3.0.txt:267-276` |
| `CEEDS-CON-16` | The deployment of a data space is performed according to five main dimensions, which reflect the three transversal features. | informative | `Blueprint_CEEDS_v3.0.txt:278-279` |
| `CEEDS-CON-17` | The Business dimension examines the business model related to data exchange and delineates the business roles of involved parties. | informative | `Blueprint_CEEDS_v3.0.txt:280-282` |
| `CEEDS-CON-18` | The Legal dimension covers the legal framework, encompassing (a) overarching legal frameworks, (b) organizational aspects, and (c) contractual instruments. | informative | `Blueprint_CEEDS_v3.0.txt:283-284` |
| `CEEDS-CON-19` | The Operation dimension covers the operational framework, including use cases, processes, and activities. | informative | `Blueprint_CEEDS_v3.0.txt:285-286` |
| `CEEDS-CON-20` | The Functional dimension describes the technical and governance building blocks, deployed based on necessary technical services (and their dependencies), as well as adherence to data standards. | informative | `Blueprint_CEEDS_v3.0.txt:287-288` |
| `CEEDS-CON-21` | The Technology dimension offers specifications on adopted standards or required software components, as identified in the energy domain through the Smart Grid Architecture Model (SGAM). | informative | `Blueprint_CEEDS_v3.0.txt:289-291` |
| `CEEDS-CON-22` | A primary objective of the Technology dimension is to ensure interoperability among internal parties and with other data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:290-291` |
| `CEEDS-CON-23` | The realization of a data space in the energy domain must address every indicated dimension. | must | `Blueprint_CEEDS_v3.0.txt:292-293` |
| `CEEDS-CON-24` | The realization of a data space in the energy domain must implement the required measures to achieve interoperable solutions. | must | `Blueprint_CEEDS_v3.0.txt:292-293` |
| `CEEDS-CON-25` | Even where solutions are already in place and well advanced for individual dimensions, consistent work must be deployed to synchronize and align all the different dimensions simultaneously and in a defined system. | must | `Blueprint_CEEDS_v3.0.txt:293-297` |
| `CEEDS-CON-26` | The CEEDS is foreseen as the common framework that federates different data spaces — each implemented at the national, sub-national or international level — and allows the participation of the single users. | informative | `Blueprint_CEEDS_v3.0.txt:304-306` |
| `CEEDS-CON-27` | Different layers are defined, from the local data space solutions to the federated ecosystem of data spaces, following a decentralized configuration. | informative | `Blueprint_CEEDS_v3.0.txt:306-308` |
| `CEEDS-CON-28` | Panel I is a closed ecosystem. | informative | `Blueprint_CEEDS_v3.0.txt:308-309` (Figure 2, p. 10) |
| `CEEDS-CON-29` | Panel II, the open, interoperable ecosystem, is reached by implementing data exchanges with external participants, who in any case subscribe to the governance rules. | informative | `Blueprint_CEEDS_v3.0.txt:309-311` |
| `CEEDS-CON-30` | Panel III is reached by structured interactions among different ecosystems, following the interoperability of the specific governance rules, giving the ecosystem of data space solutions as a federation. | informative | `Blueprint_CEEDS_v3.0.txt:311-313` |
| `CEEDS-CON-31` | The participation of single users, defined in the CEEDS through the Harmonised Electricity Market Role Model (HEMRM), remains a foremost feature in the federation of ecosystems. | informative | `Blueprint_CEEDS_v3.0.txt:313-315` |
| `CEEDS-CON-32` | The federation of ecosystems is the model that will be pursued to interconnect the data space instances of the cluster projects, paving the way for the CEEDS. | informative | `Blueprint_CEEDS_v3.0.txt:322-323` |
| `CEEDS-CON-33` | That federation relies on specific measures for technical, semantic and governance interoperability. | informative | `Blueprint_CEEDS_v3.0.txt:323-325` |
| `CEEDS-CON-34` | Educational Purpose and Research is a category of data space use: supporting the sharing of educational resources, academic research, and collaboration across institutions and countries. | informative | `Blueprint_CEEDS_v3.0.txt:348-350`, `368-378` |
| `CEEDS-CON-35` | Data Exchange and Interoperability is a category of data space use: enabling the secure and efficient exchange of data between actors of the energy value chain and improving interoperability among diverse systems and platforms. | informative | `Blueprint_CEEDS_v3.0.txt:351-353`, `379-382` |
| `CEEDS-CON-36` | Innovation and New Business Models is a category of data space use: acting as incubators for new business models through secure and controlled access to shared data. | informative | `Blueprint_CEEDS_v3.0.txt:354-356`, `383-396` |
| `CEEDS-CON-37` | Data Analysis and Visualization is a category of data space use: providing tools that transform data into actionable insights, enhancing decision-making. | informative | `Blueprint_CEEDS_v3.0.txt:357-359`, `397-400` |
| `CEEDS-CON-38` | Governance and Regulation is a category of data space use: acting as evidence-based, data-driven frameworks supporting public authorities and national agencies, streamlining regulatory compliance and fostering transparent governance mechanisms. | informative | `Blueprint_CEEDS_v3.0.txt:360-365`, `401-405` |

## Open questions

> **Ambiguous:** Figure 1 and its describing prose do not agree on where the CEEDS Reference Architecture Patterns attach. The figure draws an edge labelled "Includes" from **DSSC Reference Architecture** to **CEEDS Reference Architecture Patterns**, while the prose states that the **CEEDS Reference Architecture** "is further refined through CEEDS Reference Architecture Patterns and CEEDS Blueprint Patterns". The figure's vertical edge from DSSC Reference Architecture to CEEDS Reference Architecture is unlabelled; only the prose supplies the verb ("informs").

> **Ambiguous:** Section 2.1 states that the measures for technical, semantic and governance interoperability "will be described in section 5 of the present document", but Section 1.1's own description of the document's organization assigns interoperability to Section 7 and assigns Section 5 to the implementations of the building blocks. The two cross-references cannot both be right.

> **Ambiguous:** The panels of Figure 2 are titled "i) Closed Ecosystem", "ii) Open Ecosystem" and "iii) Federation of Data Exchange Platforms", whereas the prose calls panel III "the ecosystem of data space solutions, as a federation". Whether "Federation of Data Exchange Platforms" and "ecosystem of data space solutions" name the same construct is not stated.

> **Note:** The reference-architecture standards are cited in the source as "ISO/IEC/IEEE 42042 - reference architecture" and "ISO/IEC 40131 - guidance for reference architecture". Both numbers are reproduced here exactly as printed; the source gives no edition, year or clause.

> **Note:** The definition of a data space is attributed to the DSSC Blueprint **v1.0**, and the reference list entry [1] links to the v1.0 page. The blueprint does not state whether a later DSSC Blueprint version changes the definition it adopts.

> **Gap:** Neither chapter states which parts of the DSSC constitute "the mandatory part" that CEEDS intends to specialize, nor does it enumerate the DSSC elements CEEDS adopts, extends or omits. The relationship is asserted as a future objective only.

> **Gap:** "CEEDS Reference Architecture", "CEEDS Reference Architecture Patterns" and "CEEDS Blueprint Patterns" appear in Figure 1 and its prose as distinct artefacts, but these chapters neither define them nor say where they are specified.
