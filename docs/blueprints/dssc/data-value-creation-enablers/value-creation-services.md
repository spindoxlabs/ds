# Value creation services

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Value Creation Enablers › Value creation services
> **Category** · Data Value Creation Enablers

Value creation services are (technical) elements or components designed to unlock, generate and maximize the value of data shared within a data space, providing additional functionalities on top of the core process of data sharing or data transaction. In this sense, they complement other services facilitating individual participants and their collaboration (see *Services for Implementing Technical Building Blocks*).

## Scope and objectives

The building block covers two directions of value creation, stated by the source as:

- Enabling services for added value to individual data space participants, e.g. to facilitate data transformations.
- "Provide value to the whole of the data space to the whole of the data space: services which e.g. combine data from multiple sources to deliver insights or other forms of value for all participants."

> **Ambiguous:** the second bullet is reproduced verbatim; the phrase "to the whole of the data space" is duplicated in the source. The intended reading is not stated.

The source further distinguishes value creation services from **use cases** (see *Use Case Development* in the business pane): value creation services are technical capabilities that process, analyze, manage, … data to generate value and that, although they obey a specific purpose and can be decomposed into atomic services, are generic enough to be used across multiple use cases and data spaces. By contrast, use cases refer to real-world scenarios where participants apply one or more services to achieve a concrete goal or outcome, and are specific to a context, domain, or participant needs.

The glossary definition (upstream §7, reproduced under [Glossary](#glossary) below) adds that value creation services act over data products, are combined with them in data space offerings, and complement the capabilities provided by the "federation services" and the "participant agent" services.

## Capabilities

**Capabilities (upstream §2).** Having value creation services is *not* a mandatory capability for data spaces. Nevertheless, based on the *data space offerings*, *use cases* or *business model*, they might be necessary or can be added. Value creation services are provided by *intermediaries or operators*.

**Specifications (upstream §4).** There are no mandatory specifications for value creation services, as they will depend on the specific context and functionality provided. Guidance is nevertheless provided for defining and setting-up value creation services, through four documents:

- Tangible examples clarifying how such services can function and operate within data spaces — *Value Creation in Data Spaces through services*.
- A taxonomy of atomic Value creation services. This taxonomy ensures that: (i) services effectively cover a wide range of requirements coming from other building blocks or components of the data space, data-driven applications and initiatives, and (ii) services from different data spaces follow a similar classification — *Taxonomy of Value Creation Services*.
- An information model of a Value Creation Service, aimed to support the description, specification and implementation of these services — *Information model of Value Creation Services*.
- A service management framework, needed to manage value creation services — *Services Management Framework*.

**Implementation (upstream §5).** This building block implements the *Value-Creation Services* as is specified in *Services for Implementing Technical Building Blocks*.

## Co-creation questions

For this building block the following co-creation question applies:

**What value creation services are considered in the data space?**

Aspects for answering this question include:

- How do value creation services relate to the business model (costs and revenues) and use case(s) of the data space?
- How are they governed (who provides them and under what conditions)?
- Will value creation services be visible and available to all data space participants? or specific subsets of services will be restricted to just a group of participants?

## Standards and protocols

The source names no mandatory specification for this building block. Every entry below is named by the source as guidance, reference or reading material; "referenced" means the source names it without requiring it.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| ISO/IEC 20000 | Series; Parts 1, 2 and 5 named (developed 2005) | International standard for IT service management; specifies requirements for "establishing, implementing, maintaining and continually improving a service management system (SMS)" (Part 1), guidance on application (Part 2), guidance to service providers on implementing an SMS based on ISO/IEC 20000-1 (Part 5) | referenced |
| Information Technology Infrastructure Library (ITIL) | not stated | Set of best practices for the management of IT services; framework focused on aligning IT services with the need of the business | referenced |
| FitSM — Standards for lightweight IT Service Management | not stated | Designed to be compatible with ISO/IEC 20000-1 and ITIL | referenced |
| TM Forum Open APIs (ODA) | Open API directory; "services APIs" set | Accelerating the deployment of new services and products by enabling plug-and-play software integration to support the software lifecycle, mostly for the telecom sector; the services APIs can implement some specifications of the service management framework | referenced |
| Services Oriented Architecture (SOA) | The Open Group | Architectural style oriented to services, service-based development and the outcomes of the services | referenced |
| Hardware-based Trusted Execution Environments (TEE) | not stated | Ensure that code and data are protected during execution; and / or virtualization based security tools | recommended |
| DCAT(-AP) — `dcat:DataService` class | not stated | Describing value creation services; direct and inherited properties can describe many properties of the information model | recommended, with stated limitations |
| `dcat:endpointURL`, `dcat:endpointDescription`, `dcat:servesDataset` | DCAT | The three specific properties of the `dcat:DataService` class; `dcat:servesDataset` takes a `dcat:Dataset` as range | referenced; `dcat:servesDataset` restricted (see `DSSC-VCS-73`) |
| `dcterms:type` | DCMI Metadata Terms | Indicating the type of Value Creation Service in the taxonomy; requires a "recognised and controlled vocabulary" for the taxonomy | may |
| `dcterms:description` | DCMI Metadata Terms | Carrying, "for the time being", any additional information not covered by the DCAT "Data service" class | recommended |
| TOSCA (Topology and Orchestration Specification for Cloud Applications) | Version 1.0 | Services management (further reading) | referenced |
| IDS-RAM 4 | Section 3.4.5 "Publishing and using Data Apps" | Services management (further reading) | referenced |
| ISO/IEC DIS 5259 | Draft International Standard | "Artificial intelligence — Data quality for analytics and machine learning (ML)"; quality assessment and validation (further reading) | referenced |
| ISO 8000-61:2016 | 2016 | Data quality; quality assessment and validation (further reading) | referenced |
| `ISO/IEC 25…:2008` "Software engineering", Software product Quality Requirements and Evaluation (SQuaRE), Data quality model | 2008 | Quality assessment and validation (further reading) | referenced |
| CEN JTC21 — Specific Task Group (part of WG3) | not stated | Focused on Data Governance and Data Quality (further reading) | referenced |
| PWI JTC1-SC41-17 | Preliminary Work Item | "Guidance on the integration of IoT and digital twins in data spaces"; applications in data spaces (further reading) | referenced |
| CEN JTC21 work on the implementation of AI Act and trustworthiness | not stated | Applications in data spaces (further reading) | referenced |

> **Ambiguous:** the ISO SQuaRE data quality standard identifier is corrupted in the source. The page reads, literally: `ISO/IEC 25https://standards.cencenelec.eu/dyn/www/f?p=205:7:0::::FSP_ORG_ID:3125028&cs=1B85B1ABC4F454B7CB352839242CD794412:2008 "Software engineering", Software product Quality Requirements and Evaluation (SQuaRE), Data quality model` — a URL has been spliced into the middle of the standard number, leaving the digits after `25` unrecoverable from the page text. The accompanying catalogue link is `https://www.iso.org/standard/35736.html`. The number is not reproduced here beyond what the source unambiguously states.

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

This building block is largely non-normative: the source states outright that value creation services are not a mandatory capability and that there are no mandatory specifications. **Force** is therefore read from the source's own wording — explicit modals (*should*, *can*, *may*, *we would recommend*, *consider*) are carried across unchanged; statements of necessity or of fact about a definition ("is needed", "includes the following properties", "will be described and made available") are recorded as `must`; purely descriptive prose is recorded as `informative`.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-VCS-01` | Having value creation services is not a mandatory capability for data spaces. | may | `value-creation-services.md` §2 |
| `DSSC-VCS-02` | A data space may add value creation services where its data space offerings, use cases or business model make them necessary. | may | `value-creation-services.md` §2 |
| `DSSC-VCS-03` | Value creation services are provided by intermediaries or operators. | informative | `value-creation-services.md` §2 |
| `DSSC-VCS-04` | The data space must determine what value creation services are considered in the data space. | must | `value-creation-services.md` §3 |
| `DSSC-VCS-05` | The answer must state how value creation services relate to the business model (costs and revenues) and use case(s) of the data space. | must | `value-creation-services.md` §3 |
| `DSSC-VCS-06` | The answer must state how value creation services are governed — who provides them and under what conditions. | must | `value-creation-services.md` §3 |
| `DSSC-VCS-07` | The answer must state whether value creation services are visible and available to all data space participants, or whether specific subsets of services are restricted to just a group of participants. | must | `value-creation-services.md` §3 |
| `DSSC-VCS-08` | There are no mandatory specifications for value creation services; specifications depend on the specific context and functionality provided. | informative | `value-creation-services.md` §4 |
| `DSSC-VCS-09` | The taxonomy of atomic value creation services is applied so that services from different data spaces follow a similar classification. | must | `value-creation-services.md` §4 |
| `DSSC-VCS-10` | A service management framework is needed to manage value creation services. | must | `value-creation-services.md` §4; `services-management-framework.md` |
| `DSSC-VCS-11` | This building block implements the Value-Creation Services as is specified in Services for Implementing Technical Building Blocks. | informative | `value-creation-services.md` §5 |
| `DSSC-VCS-12` | A value creation service is data centric: it has data at the core, and performs actions over data (processes, analyzes, manages, …) to generate value out of them. | must | `value-creation-in-data-spaces-through-services.md` (principles) |
| `DSSC-VCS-13` | A value creation service's functionality cannot be performed without data sharing, or in isolation by a single party. | must | `value-creation-in-data-spaces-through-services.md` (principles) |
| `DSSC-VCS-14` | A value creation service is purpose-driven, addressing a recognizable functional need, but defined at a generic enough level to be instantiated across multiple use cases and data spaces. | must | `value-creation-in-data-spaces-through-services.md` (principles) |
| `DSSC-VCS-15` | A value creation service's ultimate objective is to generate value from the data it works with. | must | `value-creation-in-data-spaces-through-services.md` (principles) |
| `DSSC-VCS-16` | The taxonomy provides a first layer based on the services' role and purpose within the overall data space, and a second layer focused on their specific functionality within it. | informative | `taxonomy-of-value-creation-services.md` §1 |
| `DSSC-VCS-17` | The taxonomy is defined at an architectural level rather than as a catalog of concrete tools or implementations. | informative | `taxonomy-of-value-creation-services.md` §1 |
| `DSSC-VCS-18` | Core services are common to, and required by, many data spaces, are transversal to use cases and not tied to any particular dataset. | informative | `taxonomy-of-value-creation-services.md` §2 |
| `DSSC-VCS-19` | Value added services will be described and made available for participants in the use case. | must | `taxonomy-of-value-creation-services.md` §4 |
| `DSSC-VCS-20` | Bridge services connecting the data space to simulation environments and digital twins should include real-time synchronization and alignment of the digital twin representation with data models in the data space. | should | `taxonomy-of-value-creation-services.md` §5 |
| `DSSC-VCS-21` | Services often need to be combined to serve the needs of specific use cases. | informative | `taxonomy-of-value-creation-services.md` "Combining services" |
| `DSSC-VCS-22` | A Value Creation Service description includes service global information: name and type of the service, what the service is and its purpose. | must | `information-model-of-value-creation-services.md` §1 |
| `DSSC-VCS-23` | A Value Creation Service description includes lifecycle management information, to keep track of versions, releases, etc. | must | `information-model-of-value-creation-services.md` §1 |
| `DSSC-VCS-24` | A Value Creation Service description includes service governance, specifying owner and provider of the service. | must | `information-model-of-value-creation-services.md` §1 |
| `DSSC-VCS-25` | A Value Creation Service description includes service compliance, indicating how the service complies with regulation. | must | `information-model-of-value-creation-services.md` §1 |
| `DSSC-VCS-26` | A Value Creation Service description includes service monitoring and maintenance. | must | `information-model-of-value-creation-services.md` §1 |
| `DSSC-VCS-27` | A Value Creation Service description includes the service architecture: technical components of the service, their relationships and connection with the data flow. | must | `information-model-of-value-creation-services.md` §2 |
| `DSSC-VCS-28` | The data flow and management description includes mechanisms aimed at accessing and importing data from various sources. | must | `information-model-of-value-creation-services.md` §2 |
| `DSSC-VCS-29` | The data flow and management description includes mechanisms aimed at ensuring that data from various origins is properly harmonized and cleansed. | must | `information-model-of-value-creation-services.md` §2 |
| `DSSC-VCS-30` | The data flow and management description includes mechanisms aimed at making internally managed or generated data available to users when necessary. | must | `information-model-of-value-creation-services.md` §2 |
| `DSSC-VCS-31` | The data flow and management description includes mechanisms aimed at ensuring the confidentiality, inviolability, and integrity of the data ingested, manipulated and provided by the service. | must | `information-model-of-value-creation-services.md` §2 |
| `DSSC-VCS-32` | A Value Creation Service description includes service interfaces: APIs, protocols and data exchange. | must | `information-model-of-value-creation-services.md` §3 |
| `DSSC-VCS-33` | A Value Creation Service description includes security and access control: authentication and authorization. | must | `information-model-of-value-creation-services.md` §3 |
| `DSSC-VCS-34` | A Value Creation Service description includes access to the service. | must | `information-model-of-value-creation-services.md` §3 |
| `DSSC-VCS-35` | A Value Creation Service description includes service usability: user interfaces and user documentation. | must | `information-model-of-value-creation-services.md` §3 |
| `DSSC-VCS-36` | A Value Creation Service description includes services composition: dependencies with higher and lower tier services, and integration points. | must | `information-model-of-value-creation-services.md` §4 |
| `DSSC-VCS-37` | Trusted execution aligns with the trust framework of the data space, and with its capabilities to identify, authenticate and authorize users. | must | `services-management-framework.md` (Trusted execution) |
| `DSSC-VCS-38` | Trusted execution ensures, for the execution, compliance with the data space rulebook and existing regulations. | must | `services-management-framework.md` (Trusted execution) |
| `DSSC-VCS-39` | If required and possible, consider the use of hardware-based Trusted Execution Environments (TEE) and / or virtualization based security tools. | recommended | `services-management-framework.md` (Trusted execution) |
| `DSSC-VCS-40` | Depending on the requirements and storage resources in the data space, consider the containerization of services for their provisioning and deployment, to ensure portability, scalability, and resource efficiency. | recommended | `services-management-framework.md` (Services provisioning and delivery) |
| `DSSC-VCS-41` | An API gateway implements client requests to services. | must | `services-management-framework.md` (Services provisioning and delivery) |
| `DSSC-VCS-42` | Consider whether client requests to services can be included in the data plane of the data space. | recommended | `services-management-framework.md` (Services provisioning and delivery) |
| `DSSC-VCS-43` | An artifact repository stores, manages, and distributes the services, to facilitate version control, dependency management, and services retrieval. | must | `services-management-framework.md` (Services provisioning and delivery) |
| `DSSC-VCS-44` | A dedicated services registry exists as part of the general data space registry / data space wallet. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-45` | Connection with the data space catalogue enables mechanisms to register and locate services, with detailed descriptions, usage instructions, and access policies. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-46` | Use specific tools for services orchestration to manage the deployment, scaling, and operation of services, and for load balancing. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-47` | Implement workflow automation tools to coordinate complex service interactions. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-48` | Include alerting systems to notify administrators of service issues or performance degradation. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-49` | Apply tools like service mesh or dependency graphs to manage dependencies and relationships between services. | must | `services-management-framework.md` (Services management) |
| `DSSC-VCS-50` | Align with authentication mechanisms of the data space and the service itself to secure service access. | must | `services-management-framework.md` (Security) |
| `DSSC-VCS-51` | Include security audits and vulnerability assessments. | must | `services-management-framework.md` (Security) |
| `DSSC-VCS-52` | Ensure data at rest and in motion is encrypted. | must | `services-management-framework.md` (Security) |
| `DSSC-VCS-53` | Implement necessary controls. | must | `services-management-framework.md` (Security) |
| `DSSC-VCS-54` | Provide elastic access to compute resources, that enable their dynamic allocation. | must | `services-management-framework.md` (Scalability) |
| `DSSC-VCS-55` | Consider at governance / legal level to include auto-scaling policies, that based on metrics can automatically adjust resource allocation and service usage. | recommended | `services-management-framework.md` (Scalability) |
| `DSSC-VCS-56` | Apply resource quotas to ensure fair distribution of resources and use of services. | must | `services-management-framework.md` (Scalability) |
| `DSSC-VCS-57` | Provide a centralized monitoring system to collect, aggregate, and visualize performance metrics from all services and infrastructure components. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-58` | Align with the provenance and traceability components of the data space for logs of services use, performance, access attempts, and configuration changes, incorporating aggregation, search and visualization functionalities. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-59` | Provide tools for real time monitoring and visualization. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-60` | Define global performance metrics. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-61` | Define Service Level Indicators (SLI) to measure the availability and performance of a service. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-62` | Define Service Level Objectives (SLO) to guide internal process towards the Service Level Agreements. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-63` | Produce regular reports on system performance, service usage, and security incidents. | must | `services-management-framework.md` (Performance, monitoring and logging) |
| `DSSC-VCS-64` | Keep a regular maintenance schedule for updates. | must | `services-management-framework.md` (Maintenance) |
| `DSSC-VCS-65` | Apply version control for all service components. | must | `services-management-framework.md` (Maintenance) |
| `DSSC-VCS-66` | Provide back-up and recovery. | must | `services-management-framework.md` (Maintenance) |
| `DSSC-VCS-67` | Use deployment models suitable for the data space, depending on objectives, scalability and operational requirements (cloud-native architectures, hybrid cloud solutions, in-premises, serverless deployment). | must | `services-management-framework.md` (Deployment and use of services) |
| `DSSC-VCS-68` | Define and adhere to Service Level Agreements that specify service availability, performance metrics, and support response times. | must | `services-management-framework.md` (Deployment and use of services) |
| `DSSC-VCS-69` | Consider the SLA baseline of the specific service. | recommended | `services-management-framework.md` (Deployment and use of services) |
| `DSSC-VCS-70` | Provide intuitive user interfaces (UI) and user experience design to make services easy to use and navigate. | must | `services-management-framework.md` (Deployment and use of services) |
| `DSSC-VCS-71` | Part of these specifications are associated with a Service Management System: a structured and systematic approach that includes practices, procedures, and resources to ensure the effective and efficient delivery of services. | informative | `services-management-framework.md` |
| `DSSC-VCS-72` | The direct and inherited properties of the DCAT(-AP) "Data service" class can be used to describe many of the properties considered in the information model of Value Creation Services. | may | `explainer-dcat-to-describe-value-creation-services.md` |
| `DSSC-VCS-73` | The direct property `dcat:servesDataset` can only be considered when talking about the "data handling services" type. | must | `explainer-dcat-to-describe-value-creation-services.md` |
| `DSSC-VCS-74` | The type of Value Creation Service in the taxonomy can be indicated using the `dcterms:type` property. | may | `explainer-dcat-to-describe-value-creation-services.md` |
| `DSSC-VCS-75` | Using `dcterms:type` for the taxonomy requires the definition of a "recognised and controlled vocabulary" for the taxonomy. | must | `explainer-dcat-to-describe-value-creation-services.md` |
| `DSSC-VCS-76` | For properties of Value Creation Services not considered in the DCAT(-AP) "Data service" class, it is recommended, for the time being, to use the property `dcterms:description` to include any additional information. | recommended | `explainer-dcat-to-describe-value-creation-services.md` |
| `DSSC-VCS-77` | It is recommended to consider the development of a new extension or application profile, or to extend the existing "data service" class to include all properties of Value Creation Services. | recommended | `explainer-dcat-to-describe-value-creation-services.md` |

## Explainers and best practices

Six sub-pages sit beneath this building block upstream, each rendered as its own section below:
*Value Creation in Data Spaces through services* · *Taxonomy of Value Creation Services* · *Information model of Value Creation Services* · *Services Management Framework* · *Explainer: DCAT to describe Value Creation Services* · *Links to other documents*.

## Value Creation in Data Spaces through services

This section provides some examples of how value creation can be generated in data spaces through elaborated services that obey to a specific purpose. The source focuses on services that really and clearly benefit from data shared in the data space, and that, consequently, cannot be performed without data sharing: they generate value only because multiple participants share their data, often combining datasets that individually are insufficient.

Value creation services in this section obey the following principles:

| Principle | Statement |
|---|---|
| Data centric | They have data at the core, and perform actions over data (processes, analyzes, manages, …) to generate value out of them. |
| Data sharing | Their functionality can not be performed without data sharing or in isolation by a single party. |
| Purpose driven / generic | They are purpose-driven, addressing a recognizable functional need, but defined at a generic enough level to be instantiated across multiple use cases and data spaces. |
| Value creation | Their ultimate objective is to generate value from the data they work with. |

Examples of this type of service are: a data marketplace; a predictive maintenance service; a collaborative scheduling and optimization service; a simulation and impact analysis service. Each is worked through against the four principles below. (These are the source's examples — illustration, not requirements.)

### 1. Data Marketplace

A Data Marketplace is a service within a data space that enables participants to publish, discover, and exchange data products under transparent and agreed conditions. The marketplace aims at establishing a trusted relationship between a data product provider and any user who has searched, found and selected one or more data products from this provider in the data space. The marketplace provides the tools required to negotiate conditions for the delivery (pricing, licencing, access control) and use of the products, monitor the process and store all the relevant information, i.e. everything needed to ensure the journey of the provider and the user goes smoothly. It may also support advanced features such as dynamic pricing, quality certification, or usage-based billing.

*Data Marketplace as a value creation service*

| Principle | Assessment |
|---|---|
| Principle 1 – Data-centric | At its core, a marketplace manages data products<br>Its entire functionality is about publishing, discovering, exchanging data products, negotiate pricing, licencing, access control and usage of the data products |
| Principle 2 – Data sharing | A marketplace only creates value if multiple participants share data products through it. If operated by a single party in isolation, it degenerates into a private repository and loses its marketplace nature. The very essence of the service depends on data sharing across participants |
| Principle 3 – Purpose-driven / generic | Its recognizable functional need is clear: to facilitate the exchange of data products under agreed conditions. However, a marketplace can be instantiated in many domains (mobility, health, manufacturing, energy, smart cities) with minimal adaptation, as the core mechanisms (catalogue, search, pricing, policy enforcement) remain the same. |
| Principle 4 - Value creation | For data product providers, it comes directly from the monetization of the data products included in the marketplace<br>For data product users, value comes from the specific application they give to the data product |

### 2. Predictive maintenance service

A value creation service that supports predictive maintenance strategies by collecting and analyzing operational data from multiple sources in a system, to detect patterns and anticipate system behavior, and predict potential failures.

*Predictive maintenance as a value creation service*

| Principle | Assessment |
|---|---|
| Principle 1 – Data-centric | Collect and analyze data from multiple sources, and produce output data in the form of failure patterns, maintenance schedule and failure notifications |
| Principle 2 – Data sharing | The service collects data across the whole value chain of the system<br>By leveraging data from multiple participants, the service increases its efficiency identifying early warnings that would be invisible to a single participant |
| Principle 3 – Purpose-driven / generic | Its main purpose is to optimize the maintenance activities and resources, and increase the system lifetime<br>Can be applied to multiple sectors, like manufacturing, transport, energy, health, etc … |
| Principle 4 - Value creation | Lower maintenance costs, access to predictive insights from the system behaviour, extended lifetime of the system and safety improvement |

### 3. Collaborative scheduling and optimization service

A Value creation service that uses shared data from multiple participants to jointly schedule resources, tasks, or events under distributed constraints and objectives. This service transforms fragmented, local scheduling into global, optimized coordination.

*Collaborative scheduling and optimization as a value creation service*

| Principle | Assessment |
|---|---|
| Principle 1 – Data-centric | Continuously consumes, analyzes, and updates shared data (availability, capacity, priorities, demand, etc.)<br>Produces new data in the form of coordinated decisions, potential schedules and system-level insights |
| Principle 2 – Data sharing | Requires access to multi-party data (from suppliers, operators, clients, or infrastructure owners), since local data alone is not enough |
| Principle 3 – Purpose-driven / generic | Specific purpose: optimize schedule or any structured task or process under different constraints and for a concrete objective<br>Scheduling is a universal optimization problem — reusable in transport, manufacturing, healthcare, energy, etc. |
| Principle 4 - Value creation | Increased utilization / capacity of shared and limited resources (vehicles, machines, energy, personnel). Reduced idle times, delays, and conflicts. Enhanced predictability in multi-party operations |

### 4. Simulation and impact analysis service

A Value creation service that simulates complex systems, scenarios, or policy options by combining real world shared data and domain models, and to analyze the resulting impacts via performance indicators.

*Simulation and impact analysis as a value creation service*

| Principle | Assessment |
|---|---|
| Principle 1 – Data-centric | Processes large volumes of shared operational, contextual, and model data<br>Generates new and high-value data assets (synthetic datasets and scenario features) |
| Principle 2 – Data sharing | Accurate simulation requires input data and models from multiple participants, along the different stages and dimensions of the process to simulate |
| Principle 3 – Purpose-driven / generic | Simulation and impact evaluation are applicable for different use cases (e.g. digotal twin) and across domains (mobility, energy, manufacturing, environment, health, etc.) |
| Principle 4 - Value creation | Optimization, forecasting, or digital twin services<br>Enables reproducibility and comparison & benchmarking<br>Supports decision making and model improvement |

## Taxonomy of Value Creation Services

This taxonomy for Value Creation Services provides a first layer based on their role and purpose within the overall data space, and a second layer focused on their specific functionality within it.

The taxonomy is intentionally defined at an architectural level rather than as a catalog of concrete tools or implementations. Its purpose is to provide a common reference structure that can be consistently applied across different data space implementations, sectors, and maturity levels. For this reason, the taxonomy is meant to serve as a stable conceptual foundation that can support implementation choices, onboarding of new services, governance decisions, and future standardization or policy efforts. It ensures that services effectively cover a wide range of requirements coming from other building blocks or components of the data space, data-driven applications and initiatives, and facilitate the discovery and use by data space participants.

The proposed taxonomy of services responds to the different ways of value creation in data spaces (the source refers here to Figure 1, not reproducible from the source text).

The six first-layer categories, and their second-layer entries, are:

### Core services

Complement the essential capabilities of the data space and contribute to running the data space in a smooth and efficient way. These services are identified to be common to, and required by, many data spaces, are transversal to use cases and not tied to any particular dataset.

| Second-layer service | Description in the source |
|---|---|
| Data visualization | *(no description given)* |
| Data quality management, assessment and validation | *(no description given)* |
| Technical enablers for automatic compliance | *(no description given)* |
| Security, including anonymization and pseudonymization | *(no description given)* |
| Monitoring and reporting | *(no description given)* |
| Others | *(no description given)* |

In addition to supporting participants and enabling use cases, core services can also enhance the performance and scope of all other technical building blocks.

### Data handling services

Act directly over specific datasets that these services are tied to, performing some specific action over them, in order to facilitate their acces and use.

| Second-layer service | Description in the source |
|---|---|
| Data selection, extraction, combination and packaging | To help users identify, filter, and extract specific data sets (or subsets of from a large dataset) included in the data product, to retrieve efficiently and in a customized way data from the data product that they need for their purposes, to combine data from different datasets in the data product, and to organize, structure and present the data in the data product to improve its usability and accessibility for users |
| Data processing and transformation | To allow the processing of datasets in the data product |
| Data delivery | Combining some of the above, it guarantees that users efficiently access, retrieve and consume the data in the data product |
| Data interpretation and reuse | To support users on the understanding of data inside the data product, drawing insights, and facilitate the reuse of these data |
| Others | *(no description given)* |

### Value added services

Add value on top of data products and data transactions, to facilitate the cost-efficient technical implementation of use cases. These services will be described and made available for participants in the use case.

| Second-layer service | Description in the source |
|---|---|
| Data fusion and enrichment | To combine information from multiple sources, and to complement datasets with additional information to produce a more comprehensive and valuable dataset |
| Collaborative data analytics | Facilitate involvement of different stakeholders in the use case to jointly analyze and draw insights from data, fostering cooperation, knowledge sharing and collective decision-making towards the objectives of the use case |
| Training and education | Methods and tools to train use case participants about technical different aspects of the use case |
| Data innovation labs | Initially conceived as environments to foster data-driven innovation and experimentation, in a data space these labs would include collaboration among different participants in the use case, customizing this approach to tailor processes, tools, and methodologies to address use case challenges and objectives |
| Data ethics, fairness, and transparency | Services providing the tools and suppport needed to comply with ethics requirements |
| Others | *(no description given)* |
| Artificial Intelligence (AI) driven services | Aimed at leverage capabilities of datasets for AI specific purposes (prediction, prescription, content generation…) |
| Federated / distributed learning | Allow to train a machine learning model across multiple decentralized nodes, using local data samples without exchanging them |
| Customizable and on-demand services | Services that offer customizable workflows, where users can assemble their own specific data pipelines or models on-demand, or access custom versions of AI/ML models tailored to their needs |
| Machine Learning (ML) models hosting | Make available and accessible pre-trained ML models, allowing users to customize them based on the needs of the use case |
| Others | *(no description given)* |

> **Ambiguous:** the "Value added services" list contains "Others" twice — once after "Data ethics, fairness, and transparency" and once at the end of the list. The list order is reproduced exactly as the source gives it. The source does not state whether the four AI/ML entries following the first "Others" form a separate sub-grouping.

### Infrastructure integration services

Enable the connection to external infrastructures, required to, among others, process, store and collect data, either as part of the normal operation of the data space or as needed by some use cases.

| Second-layer service | Description in the source |
|---|---|
| Infrastructure catalogue | Comprehensive repository that catalogs and organizes information about external infrastructures connected to the data space |
| Infrastructure orchestration and load balancing | Orchestrating the seamless connection between the data space and external infrastructures, ensuring the coordinated execution of integration tasks, data flows, and efficient communication between different systems |
| Provisioning (cloud, edge, HPC, …) | Automating the allocation and scaling of resources required for operations in the data space, ensuring optimal resource utilization based on demand |
| Others | *(no description given)* |

### Application integration services

These services ensure that both external applications can leverage data space assets and that insights generated within the data space are seamlessly operationalized in real-world systems or simulations. This capability implies a comprehensive and seamless interaction between the data space and those external applications. The need to connect with those external applications corresponds to the definition of use cases under specific business models.

| Second-layer service | Description in the source |
|---|---|
| ERP/CRM integration | To connect traditional enterprise systems with the data space |
| Simulation environments (e.g. digital twins) and virtual worlds | Bridge services to connect data spaces to simulation environments in general, and digital twin in particular. It should include real-time synchronization and alignment of digital twin representation with data models in the data space. Services to ensure that the data space seamlessly integrates with virtual landscapes, fostering synergies between the physical and digital dimensions |
| Vertical industry solutions | Prebuilt integrations targeting specific sectors |
| AI integration services | Aimed to connect and interact with AI systems in a seamless manner, including the connection with popular AI development frameworks, libraries, and tools |
| Services embeding sectorial AI capabilities | *(no description given)* |
| Others | *(no description given)* |

### Business enablement services

Services supporting business models within the data space.

| Second-layer service | Description in the source |
|---|---|
| Billing | Services to provide automated payment and invoicing systems for transactions |
| Smart contracts | Services to automate and secure the legal agreements between buyers and sellers, ensuring trust and efficiency in transactions |
| Certifications | Related to data or services quality, aligned with regulatory or business-specific requirements |
| Others | *(no description given)* |

### Combining services

Often, services need to be combined to serve the needs of specific use cases. The source illustrates such a service composition in Figure 2 (not reproducible from the source text).

> **Ambiguous:** the source's own section numbering for this taxonomy is inconsistent. Headings run "2. Core services", "3.Data handling services", "4. Value added services", then "Infrastructure integration services" (unnumbered), "5. Application integration services", "6. Business enablement services", "Combining services" (unnumbered). Whether "Infrastructure integration services" is intended as a peer first-layer category or as something else is not stated; it is rendered here as a peer, matching its heading level and its parallel structure.

## Information model of Value Creation Services

This section provides an information model of a Value Creation Service, aimed to support the description, specification and implementation of these services. A Value Creation Service includes the following properties (shown in the source's Figure 1, not reproducible from the source text):

### 1. General information of the service

| Property | Content |
|---|---|
| Service global information | Including name and type of the service, what the service is and its purpose |
| Lifecycle management | Including information to keep track of versions, releases, etc. |
| Service governance | Specifying owner and provider of the service |
| Service compliance | Indicating how the service complies with regulation |
| Service monitoring and maintenance | *(no further detail given)* |

### 2. Service architecture and data flow

| Property | Content |
|---|---|
| Service architecture | Including technical components of the service, their relationships and connection with the data flow |
| Data flow and management | Including mechanisms aimed at (i) accessing and importing data from various sources, (ii) ensuring that data from various origins is properly harmonized and cleansed, (iii) making internally managed or generated data available to users when necessary, and (iv) ensuring the confidentiality, inviolability, and integrity of the data ingested, manipulated and provided by the service |

### 3. Access and usage

| Property | Content |
|---|---|
| Service interfaces | Including APIs, protocols and data exchange |
| Security and access control | Including authentication and authorization |
| Access to the service | *(no further detail given)* |
| Service usability | Including user interfaces and user documentation |

### 4. Services composition

| Property | Content |
|---|---|
| Services composition | Including dependencies with higher and lower tier services, and integration points |

## Services Management Framework

To manage value creation services, a service management framework is needed. This typically consists of several elements:

*Services management framework: technical specifcations*

| Framework capability | Specifications |
|---|---|
| Trusted execution | Allign with the trust framework of the data space, and on its capabilities to identify, autenticate and authorize users<br>Ensure, for the execution, compliance with the data space rulebook and existing regulations<br>If required and possible, consider the use of hardware-based Trusted Execution Environments (TEE), to ensure that code and data are protected during execution, and / or virtualization based security tools. |
| Services provisioning and delivery | Depending on the requirements and storage resources in the data space, consider the containerization of services for their provisioning and deployment, to ensure portability, scalability, and resource efficiency.<br>API gateway, to implement client requests to services. To consider if those requests can be included in the data plane of the data space<br>Artifact repository, to store, manage, and distribute the services, to facilitate version control, dependency management, and services retrieval. |
| Services management | Dedicated services registry as part of the general data space registry / data space wallet<br>Connection with data space catalogue, to enable mechanisms to register and locate services, with detailed descriptions, usage instructions, and access policies.<br>Use specific tools for services orchestration to manage the deployment, scaling, and operation of services, and for load balancing<br>Implement workflow automation tools to coordinate complex service interactions.<br>Include alerting systems to notify administrators of service issues or performance degradation<br>Apply tools like service mesh or dependency graphs to manage dependencies and relationships between services |
| Security | Align with authentication mechanisms of the data space and the service itself to secure service access.<br>Include security audits and vulnerability assessments<br>Ensure data at rest and in motion is encrypted<br>Implement necessary controls |
| Scalability | Elastic access to compute resources, that enable their dynamically allocation<br>Consider at governance / legal level to include auto-scaling policies, that based on metrics can automatically adjust resource allocation and service usage<br>Resource quotas to ensure fair distribution of resources and use of services |
| Performance, monitoring and logging | Centralized monitoring system to collect, aggregate, and visualize performance metrics from all services and infrastructure components<br>Align with the provenance and traceability components of the data space for logs for services use, performance, access attempts, and configuration changes, incoprorating aggregation, search and visualization functionalities<br>Tools for real time monitorig and visualization<br>Define global performance metrics<br>Define Service Level Indicators (SLI) to measure the availability and performance of a service.<br>Define Service Level Objectives (SLO) to guide internal process towards the Service Level Agreements.<br>Regular reports on system performance, service usage, and security incidents |
| Maintenance | Regular maintenance schedule for updates<br>Version control for all service components<br>Back-up and recovery |
| Deployment and use of services | Deployment models suitable for the data space, depending on objectives, scalability and operational requirements (cloud-native architectures, hybrid cloud solutions, in-premises, serverless deployment)<br>Define and adhere to Service Level Agreements that specify service availability, performance metrics, and support response times. Consider the SLA baseline of the specific service.<br>Intuitive user interfaces (UI) and user experience design to make services easy to use and navigate |

The table above reproduces the source's own wording, including its spelling ("specifcations", "Allign", "autenticate", "dynamically allocation", "incoprorating", "monitorig").

Part of these specifications are associated with a **Service Management System**, which can be defined as a structured and systematic approach that includes practices, procedures, and resources to ensure the effective and efficient delivery of services. The importance of service management frameworks and benefits of their adoption by companies have been longely studied on the literature.

**ISO/IEC 20000** is the international standard for **IT service management**. It was developed in 2005 and aims to be generic and intended to apply to any organisation using a service management system, regardless of the organisation's type or size or the nature of the services delivered. It excludes the specification of products or tools. The ISO / IEC 2000 series is composed of different parts, being the most representative for this work the following:

- **Part 1. Service management** (the source's Figure 5): specifies requirements for "establishing, implementing, maintaining and continually improving a service management system (SMS)".
- **Part 2.** Guidance on the application of service management system, based on the requirements of part 1.
- **Part 5.** Provides guidance to service providers on how to implement a Service Management System (SMS) based on ISO/IEC 20000-1. According to this part, "an SMS supports the management of the service lifecycle, including the planning, design, transition, delivery and improvement of services, which meet agreed requirements and deliver value for customers, users and the organization delivering the services".

> **Ambiguous:** the source writes both "ISO/IEC 20000" and "The ISO / IEC 2000 series" in adjacent sentences; the latter appears to be a typographic slip but the source does not correct it.

The **Information Technology Infrastructure Library (ITIL)** includes a set of best practices for the management of IT services, that result in a framework for IT services management, that focuses on aligning IT services with the need of the business (<https://www.axelos.com/certifications/itil-service-management/>).

In this way, **Standards for lightweight IT Service Management** (FitSM, <https://www.fitsm.eu/>) are designed to be compatible with the International Standard ISO/IEC 20000-1 (requirements for a service management system) and the IT Infrastructure Library (ITIL).

**TM Forum provides a set of APIs** aimed at, among others, accelerating the deployment of new services and products by enabling plug-and-play software integration to support the software lifecycle mostly for the telecom sector (<https://www.tmforum.org/oda/open-apis/directory>). Among those APIs, there is a whole set (services APIs) that can be applied to implement some of the specifications of the service management framework mentioned above (notice that TM Forum describes its own model of "service", with specific fields appropriate for their use by these APIs).

Finally, and as mentioned before, **Services Oriented Architecture** (SOA) is an architectural style oriented to services, service-based development and the outcomes of the services.

## Explainer: DCAT to describe Value Creation Services

"Data service" in DCAT(-AP) "represents a collection of operations accessible through an interface (API) that provide access to one or more datasets or data processing functions". Some considerations:

- DCAT(-AP) "Data service" definition is quite limited when compared to that of Value Creation Services (only covering partially our taxonomy type of "Data handling" services). In general, Value Creation Services might be accessible in different means that just an API, does not have to provide access to any specific dataset, and can provide other than just processing functions.
- DCAT(-AP) "Data service" class includes 3 specific properties: `dcat:endpointURL`, `dcat:endpointDescription` and `dcat:servesDataset`. As mentioned in the previous point, this last property takes as range a `dcat:Dataset`. But for value creation services what is needed is to describe not one or more datasets but the "characteristics" of the dataset they can be used with; e.g., the modality, format of data they can process, take as input or output. For instance, an anonymization service that takes as input text in TXT format, or a transformation service that transforms format files, a classifier for audiovisual files (video in AVI), etc.
- DCAT(-AP) "Data service" inherits 32 more properties from the super-class `dcat:Resource` that are also available for use.

The source's Figure 1 (not reproducible from the source text) shows how all these DCAT Data Service class properties can be used to describe those presented in the information model of a "Value Creation Service".

Given all the above, the source draws the following conclusions:

- Even though the definition of DCAT(-AP) class "Data Service" is a bit limited when compared to the scope of Value Creation Services, we can use the (direct and inherited) properties of this class to describe many of the properties considered in the information model of Value Creation Services.
- We can only consider the direct property `dcat:servesDataset` when talking about our specific type of "data handling services" (e.g. "if a `dcat:DataService` is bound to one or more specified Datasets, they are indicated by the `dcat:servesDataset` property").
- The type of Value Creation Service in our taxonomy can be indicated using the `dcterms:type` property. However, it would require from our side the definition of a "recognised and controlled vocabulary" for our taxonomy.
- For the properties of Value Creation Services not considered in DCAT(-AP) "Data service" class, we would recommend:
    - For the time being, to use the property `dcterms:description` to include any additional information.
    - To consider the development of a new extension or application profile, or extend the existing "data service" class to include all properties of Value Creation Services.

> **Ambiguous:** the explainer's cross-reference to the information model points at a section numbered "2.4 Information model of services" on the building-block page. The building-block page as published is numbered 1–7 and contains no §2.4; the information model is a separate sub-page. The section numbering referenced does not match the current page structure.

## Links to other documents

Reading material named by the source, grouped under its own headings.

**Services management**

- TOSCA (Topology and Orchestration Specification for Cloud Applications) — Topology and Orchestration Specification for Cloud Applications Version 1.0
- IDS-RAM 4. Publishing and using Data Apps — <https://docs.internationaldataspaces.org/ids-knowledgebase/ids-ram-4/layers-of-the-reference-architecture-model/3-layers-of-the-reference-architecture-model/3_4_process_layer/3_4_5_publishing_and_using_data_apps>

**Quality assessment and validation**

- ISO/IEC DIS 5259 Artificial intelligence — Data quality for analytics and machine learning (ML) — <https://www.iso.org/standard/81088.html>
- ISO 8000-61:2016 - Data quality — <https://www.iso.org/standard/63086.html>
- `ISO/IEC 25…:2008` "Software engineering", Software product Quality Requirements and Evaluation (SQuaRE), Data quality model — <https://www.iso.org/standard/35736.html> (the standard number is corrupted in the source; see the note under "Standards and protocols")
- CEN JTC21 – Specific Task Group (part of WG3: <https://standards.cencenelec.eu/dyn/www/f?p=205:7:0::::FSP_ORG_ID:3125028&cs=1B85B1ABC4F454B7CB352839242CD7944>), focused on Data Governance and Data Quality

**Applications in data spaces**

- PWI JTC1-SC41-17 "Guidance on the integration of IoT and digital twins in data spaces" — <https://www.iec.ch/dyn/www/f?p=103:38:9406018951756::::FSP_ORG_ID,FSP_APEX_PAGE,FSP_PROJECT_ID:20486,23,118815>
- CEN JTC21 work on the implementation of AI Act and trustworthiness — <https://standards.cencenelec.eu/dyn/www/f?p=CEN:6>

## Tools implementing this building block

The source's building-block page lists tools said to implement this building block. These are illustrations, not requirements; the descriptions are the source's own. The category label shown after each name is the source's.

| Tool | Category (as labelled by the source) | Description |
|---|---|---|
| Sitra Rulebook model for a fair data economy | Business and Organisational Services | The Sitra Rulebook model provides a manual for establishing a data space and to set out general terms and conditions for data sharing agreements. Rulebook Part 2 includes editable frameworks and templates including: Data Space Canvas; Checklists: Business, Governance, Legal, and Technical; Ethical maturity model; Rolebook; Servicebook; General Terms and Conditions (to be used as-is); template for the Constitutive Agreement; template for the Accession Agreement; template for the Governance Model; and template for the Dataset Terms of Use |
| PETSpaces (Privacy-Enhancing Data App for Secure Computations in Data Spaces) | Value-Creation Services | This data app focuses on enabling privacy-preserving computations in data spaces. It leverages advanced Privacy-Enhancing Technologies (PETs), currently featuring Fully Homomorphic Encryption (FHE) and planned support for approaches like anonymization techniques and Zero-Knowledge Proofs (ZKPs). It is offered in the data space and delivered as a ready-to-deploy app to be instantiated in EDC connectors. It allows participants to process and compute encrypted data, preserving data privacy and enhancing data owners' sovereignty over their data. |
| IFLEX (Ikerlan Federated Learning EXtensible kit) | Value-Creation Services | Ikerlan Federated Learning Extensible KIT provides a solution designed to collaboratively improve AI models across multiple participants in a secure and privacy-preserving manner. Service providers use the KIT to publish a specific asset containing configuration files that deploy federated learning client components, which are automatically integrated with consumer's EDC connector, enabling authorized participants to securely access federated learning service. Clients download these components, which establish secure gRPC-based data plane connecting clients to the provider's aggregation services. This allows participants to train models locally and request aggregated model updates on-demand. |
| Ocean Enterprise Market | Value-Creation Services | The Ocean Enterprise Market or Ocean Enterprise Portal is a Graphical User Interface (GUI) which provides Data Space Participants with the ability to publish, manage, discover, and consume data products and service offerings. The Market allows Data Space Participants, especially Data Service Providers, to present target group specific information to potential Data Product Consumers. |
| WISEPHERE | Value-Creation Services | WISEPHERE is a technological environment developed by ITI that, once deployed, allows organizations to manage, share and exploit data in a reliable and secure environment, with the aim of transforming this data into knowledge and value. WISEPHERE helps companies create Data Spaces and adopt data technologies, offering a response to their technological, legal and economic uncertainties, thus facilitating the path towards the data economy. |
| Data Space Builder | Value-Creation Services | The Data Space Builder is a suite composed by the different data spaces components and technical building blocks such as catalogs, vocabulary services, trust framework & usage, policies and identity management, and data exchange including connectors and agents, also focused on semantic data management, data models management and NLP (Natural Language Process) intelligence. |
| PURIS - Predictive Unit Realtime Information Service | Value-Creation Services | The introduction of the Predictive Unit Real-Time Information Service (PURIS) enriches a company's resilience strategy through standardized data sharing, giving stakeholders heightened transparency and comprehensive information. This clarity allows PURIS users to detect supply chain issues earlier, initiate solution-finding more swiftly, and access a wider array of options, leading to more effective, cost-efficient, and environmentally friendly outcomes. By facilitating proactive anticipation, concurrent management, and reactive recovery, PURIS supports the supply chain across pre-, during-, and post-disruption phases, thereby improving operational efficiency and resilience within the Catena-X network. |

## Glossary

Upstream §7 of the building-block page. Definitions are not requirements and carry no requirement IDs.

| Term | Definition |
|---|---|
| Value creation services | (technical) elements or components designed to unlock, generate and maximize the value of data shared within a data space, providing additional functionalities on top of the core process of data sharing or data transaction. Explanatory Text: This value is delivered both for (i) data space participants (by enabling services and applications that operate on top of data exchanges and transactions), and (ii) for the data space itself (supporting and enhancing core functionalities, such as semantic interoperability, data quality, discoverability, trust mechanisms and others) Value creation services act over data products, and are combined with them in data space offerings, to perfom the functionalities required by the defined use cases. Value creation services complement the capabilities provided by the "federation services" and the "participant agent" services This value creation can come from different sides: complementing the essential capabilities of the data space, acting directly over datasets that these services are tied to, as part of data products, adding value on top of data products and data transactions, enabling the connection to external infrastructures, required to, among others, process, store and collect data, either as part of the normal operation of the data space or as needed by some use cases, enabling the connection to external applications, which are required for the complete development of use cases, facilitating by any other means the materialization of the business models considered in the data space. |

## Open questions

- **No mandatory content.** The source states both that value creation services are not a mandatory capability (§2) and that there are no mandatory specifications for them (§4). Everything in the sub-pages is therefore guidance. Where this page records a `must`, that force is derived from the source's phrasing of necessity ("is needed", "includes the following properties"), not from a modal verb the source used — see the note in the Requirements section.
- **Taxonomy numbering is inconsistent.** Categories are numbered 2, 3, 4, (unnumbered), 5, 6, and "Infrastructure integration services" carries no number while sitting at the same heading level as the numbered categories. See the note in that section.
- **"Others" appears twice in the "Value added services" list**, suggesting a lost sub-grouping around the four AI/ML entries. The source does not say.
- **Duplicated phrase in the scope statement**: "Provide value to the whole of the data space to the whole of the data space" (§1, second bullet).
- **Corrupted standard identifier**: the SQuaRE data quality standard number in "Links to other documents" has a URL spliced into it, leaving the digits after `ISO/IEC 25` unrecoverable from the page.
- **"ISO / IEC 2000 series"** is written for what the preceding sentence calls ISO/IEC 20000.
- **Broken internal cross-reference**: the DCAT explainer points to a section "2.4 Information model of services" that does not exist in the building-block page's current numbering (1–7).
- **Figures are not reproducible from the source text.** The source relies on figures at five points: Taxonomy Figure 1 (the ways of value creation) and Figure 2 (an example service composition); Information model Figure 1 (the full property model); Services Management Framework Figure 5 (ISO/IEC 20000 Part 1); DCAT explainer Figure 1 (mapping DCAT properties onto the information model). In each case the surrounding prose is rendered above, but the figure content itself is not available.
- **Whether the four principles are definitional or descriptive** is unclear. The source says "value creation services *in this section* obey to the following principles", scoping them to its four worked examples rather than stating them as criteria for all value creation services. They are recorded as `must` here on the reading that they are qualifying criteria; the scoping qualifier is the source's.
- **Cross-category label on a listed tool.** "Sitra Rulebook model for a fair data economy" appears in the building-block page's tools list but is labelled "Business and Organisational Services", not "Value-Creation Services" like every other entry. The source does not explain the mismatch.
- **Second-layer entries without descriptions.** Several taxonomy entries ("Data visualization", "Technical enablers for automatic compliance", "Services embeding sectorial AI capabilities", and every "Others") are named with no explanatory text. They are rendered as named, undescribed entries rather than being interpreted.
