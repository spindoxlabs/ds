# EDSCP Implementation Details

> **Source** · Blueprint of the Common European Energy Data Space (int:net), Version 3.0, September 2025 › Chapter 5, "EDSCP Implementation Details" (pp. 48–65)
> **Category** · Implementation details — reference implementations of the CEEDS building blocks by the Energy Data Space Cluster Projects

"EDSCP" is expanded by the source as **Energy Data Space Cluster Projects**: "int:net has cooperated with the sister projects, forming the Energy Data Space Cluster Projects (EDSCP), and the energy community to identify the specific vertical capabilities that are needed in an energy data space."

Chapter 5 states its own purpose as follows: "This section provides a concise overview of the ongoing projects associated with BUCs, followed by a description of the various building blocks utilized in the implementation of these projects. This section presents how the building blocks are being implemented by the EDSCP in their pilots, deriving approaches for further replication in the CEEDS."

> **Reading note on normative force.** This chapter is predominantly *descriptive*. Named connectors, identity providers, catalogues, marketplaces and projects are reference implementations and pilot deployments, not obligations. They are recorded below as context and, where they are specifications, in "Standards and protocols" with the force `referenced`. Only the explicit modal statements — chiefly the business-use-case preconditions and the optional building-block uses in §5.3, and the marketplace/compensation statements in §5.4 — carry normative force, and they are preserved with the exact modal the source uses.

## 5.1. Energy Dataspace Cluster Projects

This section of the source describes five cluster projects. All content in this section is descriptive project context; it generates no requirements.

### Project EDDIE

Project EDDIE has developed the Open-Source **EDDIE Framework**, to facilitate energy data exchanges across EU member states. Key in the EDDIE Framework is a consent-based European-wide interoperable mechanism which allows the consumer to independently manage data exchange with energy service providers, energy community operators, flexibility service providers and grid operators.

EDDIE Framework currently supports connectivity with validated consumption and accounting point master data for 7 Member States and United States (US)/Canada (CAN) **Green Button CMD** with a common and easily integrable API, standardized data and a common process, with most remaining member states to be attached soon.

Furthermore, EDDIE Framework features the **Administrative Interface for In-house Data Access (AIIDA)**, a secure and reliable tool for accessing data from smart meters and behind-the-meter assets close to real-time, based on customer consent and tailored to the respective use case.

The **EDDIE Marketplace**, an off-the-shelve data marketplace for entities involved in energy data management (e.g., DSOs, TSOs, Energy Communities (ECs), etc.), provides facilitation services for new data-based solutions.

**EDDIE Online** is a Platform as a Service (PaaS) to allow for energy data-driven services achieve data integration within minutes — is in development and close-to-production mode since March 2023. In parallel to the development of the EDDIE technical components, a multidisciplinary analysis is ongoing to examine the economic properties and commercial opportunities arising from the establishment of an energy data space; assess the behavioural aspects associated with the availability and use of energy data; clarify rights, duties and principles of consumers' energy data sharing; investigate alternative regulatory arrangements; and explore security and safety aspects of alternative data-sharing options.

EDDIE's innovative approach significantly reduces data integration costs, allowing energy service companies to operate and compete seamlessly in a unified European market. This not only enhances the operational efficiency of these companies but also promotes a more cohesive and integrated energy sector across Europe. Additionally, AIIDA ensures secure and reliable access to valuable real-time data from smart meters strictly based on customer consent. EDDIE components are LIVE and usable by a broad audience already and they have led to smart and close-to-industrialization solutions.

### Project SYNERGIES

SYNERGIES has introduced a reference Energy Data Space Implementation to unleash the data-driven innovation and sharing potential across the energy data value chain by leveraging on data and intelligence coming from diverse energy actors (prioritizing on consumers and introducing them as data owners/providers) and coupled sectors (buildings, mobility) and effectively making them reachable and widely accessible.

In turn, it has facilitated the transition from siloed data management approaches to collaborative ones which promotes the creation of a data and intelligence ecosystem around energy (and other types of) data and enables the realization of data (intelligence)-driven innovative energy services that:

1. value the flexibility capacity of consumers in optimizing energy networks' operation, maximizing RES integration and self-consumption at different levels of the system (community, building);
2. evidently support network operators in optimally monitoring, operating, maintaining and planning their assets and coordinating between each other (TSO-DSO collaboration) for enhancing system resilience;
3. create an inclusive pathway towards the energy transition, through consumer empowerment, awareness and informed involvement in flexibility market transactions;
4. step on real data streams and intelligence to deliver personalized and automated features to increase prosumer acceptance and remove intrusiveness;
5. facilitate the establishment of sustainable Local Energy Communities (LECs) by enhancing their role with Aggregator and BSP functions; and
6. establish solid grounds for the creation of a new economy around energy data produced and shared across a complex value chain, in a secure, trustful, fair and acceptable manner.

### Project DATA CELLAR

DATA CELLAR has created a federated energy dataspace that will support the creation, development and management of local energy communities in the EU. The data space population was facilitated via an innovative rewarded private metering approach, with a focus on an easy onboarding and interaction, guaranteeing a smooth integration with other EU energy data spaces, providing to LEC stakeholders services and tools for developing their activities.

The DATA CELLAR platform is built around a collection of data sources — such as Local Energy Communities and energy installations — referred to as **Validation Cases** within the project. These sources deploy software services designed to process and expose raw datasets for integration into the DATA CELLAR ecosystem. The services include adapting data to the project's model, integrating with a **Dataspace Protocol-compliant connector**, and publishing datasets in a **Gaia-X federated catalogue**.

In addition, DATA CELLAR implements data-driven, energy-related services, such as a Decision-Support System, which utilise the Validation Case data sources to generate valuable insights for users of the data space. Users can access these through a user-friendly web Dashboard that serves as a gateway, abstracting the complexities of data space concepts and protocols. Advanced users, however, have the option to deploy their own wallet, connector, and related services to interact directly with the data space if they wish.

### Project OMEGA-X

OMEGA-X has developed an Energy Data Space that enables multiple actors to share data and services while ensuring privacy, security and sovereignty. This specifically addressed the current problem of low availability of data for innovative uses in the energy sector and beyond. OMEGA-X collaborated with stakeholders to identify where energy-based service improvements and innovation are required to guarantee that companies and organizations can share their data safely.

At the same time, the OMEGA-X solution helped existing market actors (including SMEs and start-ups) to have access to a variety of datasets to improve their AI models and thus be able to upgrade existing services and/or bring innovative services that otherwise could not be developed. The availability of data empowers new participants and market roles such as aggregators and local energy community managers. This has the potential to facilitate the large-scale penetration of renewables in the local grid without significant investments in grid infrastructure and will also create an opportunity for new business models to emerge. OMEGA-X put a prominent focus on developing and promoting inclusive and collaborative behaviours, which will lead to a multitude of societal and economic benefits, such as an increase in energy autonomy and a reduction in CO2 emissions.

### Project Enershare

Enershare has leveraged the potential of energy data by developing a reference architecture for a European Energy Data Space. This architecture integrates cloud security solutions with digital security, artificial intelligence, and data exchange frameworks globally. By enhancing interoperability, establishing trust, and increasing the value of data building blocks, Enershare has tailored its solutions to the specific needs of the energy sector.

The project has tested its innovative solutions and approaches in seven pilot sites across eleven use cases. These use cases demonstrated the value of energy data in providing services within and beyond the energy sector. Enershare demonstrated the potential to positively impact the development of new economic activities and cross-sector services by creating new business opportunities and jobs in the energy sector. Additionally, it enhanced awareness and engagement among energy consumers and communities. The project also envisioned creating new value-added services based on energy data, such as energy management, efficiency, auditing, forecasting, and trading.

## 5.2. Technical Building Blocks Implementations across Projects

"Table 9 summarizes the implementation of each building block (BB) within the individual cluster projects. If an implementation for a specific building block does not exist within a project, the corresponding field is left blank in the table."

### Table 9 — Project specific implementations of CEEDS Building Blocks

Reproduced from the source's own table layout (the column headings and project spellings are the source's).

| CEEDS Building Block | EDDIE | Synergies | DataCellar | Omega-X | Enershare |
|---|---|---|---|---|---|
| Connector | EDDIE Framework | Synergies Dataspace Connector | Eclipse Dataspace Components | Eclipse Dataspace Components (via Sovity connector) | TNO Security Gateway & Energy Dataspace Connector |
| Identity Management | Keycloak, eID | Security, Authentication & Authorisation Engine based on Keycloak | Hybrid approach with OIDC (Keycloak) and Gaia-X-compliant Verifiable Credentials via OID4VC | IDSA – DAPS plus Gaia-X Verifiable Credentials | Keycloak and TSG Identity Provider |
| Logging | Standard Logging Frameworks | Contract Settlement Engine | Eclipse Dataspace Components system monitoring interface | Kubernetes Logging operator | Clearing House |
| Vocabulary Hub | European Master Data Model | CIM Network Manager | Custom Implementation | Common Semantic Data Model (CSDM) | Semantic Treehouse |
| Contract Framework | Data Marketplace | DLT Smart Contract Management Engine | IDS Contract Negotiation | Gaia-X specifications | Blockchain |
| Publication & Discovery | European Master Data Model | Data Marketplace | XFSC | Gaia-X Federated Catalogue | The Metadata Broker |
| Provenance & Traceability | X.509 | Contract Settlement Engine | Gaia-X Digital Clearing House | Gaia-X Digital Clearing House | Clearing House |
| Access & Usage Policy | *(blank)* | Access Policy Engine | Eclipse Dataspace Components | Gaia-X Digital Clearing House | Eclipse Dataspace Components |

"Further details on as well as the rationale behind choosing specific implementation is explained below."

### EDDIE

- **Data Space Connector** — built on the EDDIE Framework and AIIDA, avoiding commercialized connectors due to their limited maturity and applicability to the project's use cases. Instead, interoperability is ensured through **Kafka connectors**, particularly for cross-sectoral data integration with other projects such as SYNERGIES. It follows the **IEC CIM** standard for the information model and supports multiple communication protocols, including **OASIS AS4**, **REST**, **Kafka**, **AMQP**, and **MQTT5** for edge deployments. Maturity **TRL7+**; well-suited for data-driven companies and ensures seamless integration across different domains.
- **Identity Management** — Keycloak and **OpenID Connect** for centralized identity and access management (IAM), with connections to **eID** and **eIDAS** wherever applicable. The implementation aligns with the **DSSC reference architectures** followed by many connected data spaces, ensuring compatibility across various identity frameworks. Maturity **TRL9**; "it meets all necessary requirements for authentication and authorization, providing a secure and scalable solution for federated data access."
- **Logging** — standard logging frameworks designed for integration into modern containerized infrastructures. Adapts to the logging requirements of each connected data space, ensuring compliance with **AS4** standards for features such as repeatability, non-reputability, and auditability. Maturity **TRL9**.
- **Vocabulary Hub** — the EDDIE Framework translates national information models into **IEC CIM** where needed and provides a **European Master Data Model**, ensuring a unified data representation across different energy systems. Maturity **TRL7+**.
- **Contracting Framework** — managed through the **EDDIE Data Marketplace**, which enables the definition and execution of contracts for data transactions. "While specific standards are not mentioned, the implementation follows DSSC practices to ensure structured and legally sound agreements." Supports data monetization and crowdsourcing valuable datasets.
- **Publication & Discovery** — the EDDIE Framework employs a **European Master Data Model** to connect multiple data spaces. Datasets are made available through standardized publication and consumption methods. Maturity **TRL7+**.
- **Provenance & Traceability** — trust between federated components established using **X.509**-based signing and encryption; follows **eIDAS** and **X.509** standards. Maturity **TRL9**.
- **Access & Usage Policies** — the project translates national regulations into enforceable access rules using the **EDDIE Data Needs definition language**, ensuring compliance with **GDPR** and the **Data Governance Act**, embedding usage policies and consent mechanisms within the system. Maturity **TRL9**.

> **Contradiction with Table 9:** Table 9 leaves the EDDIE cell for *Access & Usage Policy* blank, which per the source's own convention means "an implementation for a specific building block does not exist within a project", yet the narrative describes a TRL9 EDDIE implementation of Access & Usage Policies.

### Synergies

- **Data Space Connector** — builds upon the implementation validated in the **SYNERGY** project and has been extended to support the data-sharing needs of the energy value chain. Aligns with the **Gaia-X architecture (22.10 Release)** and **IDS RAM**, ensuring compliance, interoperability, and data sovereignty. Maturity **TRL6**, "expected to reach TRL7 after validation in large-scale demonstrators."
- **Identity Management** — the **Security, Authentication & Authorization Engine**, which centralizes user and organization authentication using **Keycloak**, currently integrated with **OpenID Connect**. Complies with **OAuth 2.0** and aligns with the **Gaia-X Trust Framework** and **IDS RAM**. Maturity **TRL6**, expected to reach TRL7.
- **Logging** — managed by the **Contract Settlement Engine**, which oversees data transaction contracts, ensuring compliance and settlement monitoring. "Fully compliant with the IDS Clearing House, it verifies contract terms, supports crypto-payments, and tracks remuneration." Maturity **TRL6**, progressing toward TRL7.
- **Vocabulary Hub** — the **CIM Network Manager** maintains and harmonizes cross-sectoral Common Information Models (CIM), ensuring semantic interoperability. Supports **IEC 62325**, **OpenADR3.0**, **SAREF4ENER**, and **OCPP**, aligning with **IDS RAM** and **Gaia-X**. Maturity **TRL7**.
- **Contracting Framework** — the **DLT Smart Contract Management Engine**, leveraging **Ethereum** for automated and legally binding data-sharing agreements. Aligns with the **IDS RAM** and **Gaia-X Clearing House**, enabling contract negotiation, execution, and compliance tracking. Maturity **TRL6**, advancing to TRL7.
- **Publication & Discovery** — a **Data Marketplace** providing a centralized catalogue for data asset exploration. "It fully aligns with the specifications of the IDS RAM Metadata Broker and App Store, ensuring metadata-level transparency." Maturity **TRL6**, progressing to TRL7.
- **Provenance & Traceability** — mechanisms build on the Logging and Contracting Framework, ensuring transaction accountability through distributed ledger technologies and smart contracts. Comply with **IDS RAM** and **Gaia-X**.
- **Access & Usage Policies** — enforced by the **Access Policy Engine**, enabling fine-grained control over dataset access and usage permissions. Supports organization-based access, confidentiality settings, and policy enforcement in alignment with **DSSC** and **IDS RAM**. Maturity **TRL7**.

### Data Cellar

- **Data Space Connector** — implemented using the **Eclipse Dataspace Components (EDC)** framework, which provides modular building blocks for data exchange. Follows the **International Data Spaces (IDS) Dataspace Protocol**. Maturity **TRL5**, "chosen for its maturity, available documentation, and acceptance within related projects."
- **Identity Management** — a hybrid approach using **OpenID Connect (Keycloak)** for centralized authentication and the **walt.id** framework for issuing **Verifiable Credentials (VCs)** and **Decentralized Identifiers (DIDs)**. Complies with the **Gaia-X Trust Framework** and **OpenID Connector for Verifiable Credentials (OID4VC)**. Maturity **TRL5**.
- **Logging** — "Logging in Data Cellar lacks a unified implementation, as different services utilize independent logging mechanisms, making it non-applicable (N/A) in terms of maturity and standards compliance."
- **Vocabulary Hub** — a bespoke ontology using **OWL**, **RDF**, **JSON-LD**, and well-known vocabularies like **SAREF** and **ThinkHome**. "However, it lacks collaborative editing and curation features, making it N/A in maturity level and standard compliance applicability."
- **Contracting Framework** — based on the **IDS Dataspace Protocol's Contract Negotiation Protocol**, implemented via the **EDC Connector** framework. Enables automated contract negotiation between connectors and integrates a custom **Marketplace Ecosystem** for dataset access. Maturity **TRL5**.
- **Publication & Discovery** — a modified fork of the **XFSC Federated Catalogue**, ensuring compliance with the **Gaia-X Trust Framework**. Provides a standardized way for participants to publish and query data offerings. Maturity **TRL5**.
- **Provenance & Traceability** — indirectly supported through the **Gaia-X Digital Clearing House (GXDCH)** for verifying dataset provenance and the Marketplace for transaction tracking. "Though not explicitly developed for this function, they provide a baseline for trust and accountability." Maturity **TRL5**.
- **Access & Usage Policies** — enforced using the **EDC policy engine**, complemented by a custom extension for **Verifiable Presentation** exchange. Follows **ODRL**, **JWT**, and **W3C Verifiable Credentials**. Maturity **TRL5**, "with an external Policy Decision Point (PDP) planned to enhance decision-making capabilities."

> **Contradiction with Table 9:** Table 9 records DataCellar Logging as "Eclipse Dataspace Components system monitoring interface", while the narrative states that Logging in Data Cellar "lacks a unified implementation" and is N/A.

### Omega-X

- **Data Space Connector** — **Eclipse Dataspace Components (EDC)**, with an extended enterprise-ready "Connector-as-a-Service" (CaaS) provided by **sovity**. Follows the **Data Space Protocol (DSP)** for contract negotiation and secure data transfers. Maturity **TRL7**; "this approach simplifies adoption for non-technical partners, broadening participation in data space solutions."
- **Identity Management** — an **IDSA-compatible DAPS**, a **PKI based on EJBCA**, and a **Verifiable Credential (VC) issuer using OID4VCI**. Complies with both **IDSA** and **Gaia-X Trust Frameworks**. Maturity **TRL5**, "chosen for its seamless integration with the connector and interoperability with other projects."
- **Logging** — a **Kubernetes logging operator using Fluentd and Fluentbit** provides memory- and file-based buffering to prevent data loss. Follows standard logging practices. Maturity **TRL4**, "as further development is needed for full-scale implementation."
- **Vocabulary Hub** — a **Common Semantic Data Model (CSDM)**, available on GitHub, "and will later be published in the Semantic Treehouse of the ENERSHARE project". Follows ontology-based REST API standards such as **OPENAPI** and **JSON-LD**. Maturity **TRL5**.
- **Contracting Framework** — based on **Gaia-X specifications** and implemented as a **marketplace federator** for managing offerings and transactions. Maturity **TRL4**.
- **Publication & Discovery** — a **Gaia-X Federated Catalogue** instance, "compliant with Docker and Python v3.12". Maturity **TRL5**.
- **Provenance & Traceability** — managed through the **Gaia-X Digital Clearing House (GXDCH)**, which ensures data integrity, traceability, and auditability across providers. Maturity **TRL4**; "it supports secure and immutable transaction logging."
- **Access & Usage Policies** — also governed by the **GXDCH**, providing a standardized framework for managing data flow, ensuring compliance, and enforcing security measures. Maturity **TRL4**.

### Enershare

- **Dataspace connector** — Enershare primarily uses the **TNO Security Gateway (TSG) version 1**. "The TSG is an IDSA-certified connector aligned with the IDSA Reference Architecture Model v4, with a high maturity level (TRL 8-9). The Energy Data Space Connector v1.1 is also used, based on the OneNet Connector, but it does not yet support the Data Space Protocol (DSP); its TRL is 7-8, with full DSP integration planned for 2025."
- **Identity Management** — **Keycloak** for individual users and the **TSG identity provider (IDP)** for data space participants, with compliance to **IDSA RAM v4**. Keycloak TRL **9**; TSG IDP TRL **8-9**.
- **Logging** — the **Clearing House** logs metadata and transaction details, ensuring compliance with data usage policies and contract agreements. "It does not follow specific standards beyond REST APIs and has a TRL of 5-6, chosen for its ability to integrate with connectors and marketplaces to provide verifiable transaction records."
- **Vocabulary Hub** — **Semantic Treehouse**, compliant with **IDSA RAM v4** and supporting various open standards like **RDFS/OWL**, **SHACL**, and **JSON schema**. Core modules TRL **9**; newer modules like the message model wizard TRL **5-7**.
- **Contracting Framework** — blockchain and smart contracts based on the **ERC20** standard for tokenized transactions. TRL **6-7**.
- **Publication & Discovery** — the **TSG-based Metadata Broker**, compliant with **IDS-RAM v4**. TRL **7-8**. "It enables structured metadata management and integrates with the marketplace for efficient data discovery."
- **Access & Usage Policies** — enforced using **TSG** and **Energy Data Space Connector** modules, with **XACML**-based policies, and **Eclipse Dataspace Components (EDC)**, using **ODRL**. "The TSG- and TRUE-based implementations have a TRL of 6-7, while the EDC-based implementation is at TRL 5-6."

## 5.3. Business Use Case Realization in CEEDS Architecture

"This section explains the realization of selected BUC scenarios using the CEEDS architecture and deployed building blocks. The corresponding sequence diagrams (in section 3) illustrate the data exchange within these scenarios, providing insight into how CEEDS can facilitate seamless data flow."

### BUC#1: Collective self-consumption and optimized sharing for energy communities

**Scenario 1** — DER sizing and economic evaluation of the REC/CEC business model.

- *Trigger:* a consumer requests the service.
- *Actors:* energy service companies, traders, market information aggregators, resource aggregators, FSPs, and sub-meter data hub operators.
- *Preconditions:* "consumption and generation profiles, as well as tariff data, must already be available in the data space."
- *Realization:* these inputs are accessed using the **Publication & Discovery** building block "to ensure the right datasets are discoverable and accessible to authorized service providers." The **Data Space Connector** enables secure data exchange between the data providers (such as sub-metering hubs or aggregators) and the analytics services operated by ESCOs or aggregators. **Identity Management** is used to verify and authorize the requesting service provider and ensure trusted access to consumer data.
- *Outcome and optional blocks:* once the necessary data is retrieved and processed, the optimal REC/CEC sizing information is produced. "To ensure the output data and any contractual terms (if applicable) are verifiable and traceable, **Provenance & Traceability** and **Logging** components may be used. If the service is offered through a marketplace model, the **Contracting Framework** could be used to formalize service agreements or pricing models associated with the sizing recommendations."

"These CEEDS components, working together, facilitate secure, discoverable, and interoperable data access while preserving trust and transparency across the involved actors in the data space."

**Scenario 2: Estimation of Flexibility Potential and Energy Cost Savings from Thermal Domestic Loads**

- *Trigger:* a consumer requests the service.
- *Actors:* energy service companies, traders, market information aggregators, resource aggregators, flexibility service providers (FSPs), and sub-meter data hub operators.
- *Preconditions:* "The successful execution of this use case requires that technical metadata about the EWH (e.g. tank volume, heating power), historical shower patterns (duration and timing), and sensor data (such as outlet water temperature) are already available in the data space."
- *Realization:* these inputs are discovered through the **Publication & Discovery** building block, ensuring authorized actors can identify and access the necessary datasets. Data exchange between the sub-meter data hub and the analytical services run by ESCOs or aggregators is secured using a **Connector**. **Identity Management** components authenticate and authorize access "to ensure only verified entities interact with sensitive household-level data."
- *Processing:* "Once retrieved, the data is analysed—typically through digital twins or load disaggregation models—to estimate thermal flexibility and compute potential cost savings by shifting EWH operation to off-peak hours or aligning with dynamic pricing."
- *Trust and optional blocks:* "To ensure auditability and trust, **Provenance & Traceability** components record data flows and transformations. **Logging** mechanisms further reinforce transparency in data processing. If the service is offered commercially, a **Contract Framework** may be employed to automate pricing and formalize agreements for ongoing flexibility service provision."

**Scenario 3: Evaluation of Potential Revenues from Flexibility Market Participation**

- *Trigger:* a consumer request.
- *Actors:* energy service companies, traders, market information aggregators, resource aggregators, FSPs, and sub-meter data hub operators.
- *Data relied upon:* consumption and generation series, along with relevant tariff data, accessed through the **Publication & Discovery** component.
- *Realization:* "Data exchange is secured using a **Connector**, and **Identity Management**) ensures authorized access to sensitive consumption data." Once collected, these datasets are processed by the ESCO or aggregator to compute individual and collective energy bills within the community. "The **Contract Framework** may define billing logic or compensation models among members. **Provenance & Traceability** supports transparency in data origin and processing, while **Logging** mechanisms ensure auditability of the billing computation process."
- *Outcome:* "This combination of CEEDS components enables trusted, automated, and transparent energy pricing within REC/CEC communities."

### BUC#2: Residential home energy management integrating DER flexibility aggregation

The source presents one scenario, flexibility registration and activation, as a sequence:

1. A resource operator — such as a prosumer or device manufacturer — registers a DER unit into the flexibility registry. "This registration uses the **Connector** building block (e.g., TNO Security Gateway, Eclipse Dataspace Components) to enable secure data exchange between the prosumer and service platforms."
2. **Identity Management** (e.g., Keycloak, Gaia-X Verifiable Credentials) "ensures proper authentication and authorization of the actor submitting the data."
3. "Access permissions for DER metadata and control preferences are managed through **Access & Usage Policy** enforcement (e.g., Eclipse Dataspace Components' policy engine)."
4. "Once registered, the system proceeds to baseline calculation by aggregating weather data, carbon impact estimates, and historical DER profiles. Provenance of these data flows is maintained using **Provenance & Traceability** mechanisms (e.g., X.509 certificates), ensuring data lineage and auditability."
5. "To harmonize data inputs across participants, the **Vocabulary Hub** (e.g., Semantic Treehouse) supports semantic alignment."
6. "**Logging** activities (e.g., Clearing House) document the analytics and processing stages."
7. "When flexibility potential is established, the FSP initiates a bidding process via a **Contract Framework** (e.g., EDDIE Data Marketplace or Smart Contract Engine), allowing automated contract generation between the FSP and grid operators (TSO/DSO)."
8. "Upon bid acceptance, flexibility is activated through market signals or direct control. The **Connector** ensures secure communication between service provider systems and DERs."
9. "Finally, observed flexibility delivery is reported via **Publication & Discovery** (e.g., Metadata Broker), and data logs are captured again via **Logging** to support settlement and compliance."

"The coordinated use of CEEDS building blocks in this scenario enables trusted, policy-compliant, and interoperable DER-based flexibility management."

### BUC#3: TSO-DSO co-ordination for flexibility

**Scenario 1** — Performant data search across federated data spaces.

- *Trigger:* a data asset consumer — such as a TSO, DSO, or FSP — seeks to create a new service but lacks access to all the necessary datasets.
- *Precondition:* "the data space must already contain diverse asset types including raw data, processed analytics, reports, and visualizations, all structured for automated consumption."
- *Realization:*
  1. "The process begins with the **Publication & Discovery** building block, which allows the consumer to identify and locate suitable data assets across multiple federated spaces."
  2. "Once discovered, the **Connector** facilitates secure access to the selected asset."
  3. "Authentication and authorization are enforced through **Identity Management** components, ensuring that only verified actors can proceed."
  4. "Prior to access, a valid usage agreement is formalized using the **Contract Framework**, specifying the terms and conditions under which the asset may be consumed."
  5. "To guarantee compliance and trust, **Access & Usage Policy** governs how the data may be used once shared."
  6. "Throughout the process, **Logging** records search actions and access events for traceability."
  7. "The **Provenance & Traceability** building block ensures that any analysis built on the retrieved asset maintains a verifiable data lineage."

**Scenario 2** — Sharing, trading, and bartering of raw or derivative data assets.

- *Trigger:* a TSO, DSO, or FSP requests access to previously unreachable data held in federated hubs or OEM platforms.
- *Realization:* "Using the **Publication & Discovery** block (e.g., Gaia-X Federated Catalogue or Metadata Broker), the requester locates the desired dataset or visualization. Secure exchange is established through a **Connector**, while **Identity Management** authenticates both the provider and consumer. A usage agreement is formalized by the **Contract Framework**, and permissions are enforced via the **Access & Usage Policy** engine. Throughout the transaction, **Logging** and **Provenance & Traceability** components record events and data lineage."
- *Outcome:* "one or more stakeholders successfully exchange raw data or analytics products under a verifiable and contractually compliant framework."

**Scenario 3** — AI-enabled grid-level energy demand and generation forecasting.

- *Trigger:* a DSO or TSO requiring updated forecasts to support operational or planning decisions.
- *Precondition as stated:* "The process begins with the availability of metering data and DER-specific datasets used to train and execute AI models."
- *Realization:* "These datasets are located and retrieved using the **Publication & Discovery** building block, ensuring access to both raw input and prior analytics results. Data exchange between metering infrastructure, DER platforms, and AI forecasting services is securely managed via the **Connector**, while access rights are governed by the **Access & Usage Policy** component. Identity verification of DSOs and TSOs is ensured through **Identity Management** systems."
- *Processing and optional blocks:* "Once data is accessed, AI services process individual and aggregated DER inputs to generate network-level demand and generation forecasts. These results may be logged and tracked using **Logging** and **Provenance & Traceability** to ensure auditability and compliance with regulatory frameworks."
- *Outcome:* "the CEEDS building blocks collectively enable TSOs and DSOs to access distributed, high-quality data and generate consolidated forecasts that support secure, efficient grid operations."

**Scenario 4** — AI-enabled grid-level flexibility profiling and forecasting.

- *Trigger:* initiated on demand by a Flexibility Service Provider (FSP) "seeking to assess both individual DER capabilities and aggregated flexibility potential across the grid."
- *Data relied upon:* DER data — such as technical metadata, usage history, and real-time measurements — accessed via the **Publication & Discovery** building block "to ensure discoverability across federated data spaces."
- *Realization:* "Data exchange for training and inference is securely facilitated through a **Connector**, while **Identity Management** ensures only the authorized FSP can access the required datasets. Permissions for data use are enforced through **Access & Usage Policy** mechanisms, leveraging policy engines integrated into the **Connector**. Once retrieved, the data is processed by AI models to generate flexibility forecasts, which may be supported semantically using a **Vocabulary** to harmonize data structures. **Logging** of key access and execution steps is maintained through the Logging component, while **Provenance & Traceability** ensures all analytics outcomes are auditable."
- *Outcome:* "the FSP obtains detailed, trustworthy flexibility profiles and forecasts, enabling more precise and proactive participation in flexibility markets."

**Scenario 5** — Operational events identification in the short and mid-term.

- *Trigger:* "a TSO or DSO seeking early insights into potential grid issues, such as overloads or voltage instabilities."
- *Preconditions:* "The process requires detailed data on the current transmission and distribution network topology and infrastructure, as well as access to reliable short- and mid-term demand and generation forecasts."
- *Realization:* "These datasets are located using the **Publication & Discovery** building block to ensure comprehensive and authorized access across domains. Data transfer between grid models, forecast systems, and analytics platforms is handled securely via the **Connector**, while **Identity Management** verifies that only authorized operators can initiate the request and retrieve sensitive network data. **Access & Usage Policy** enforcement ensures that data is consumed in compliance with contractual and regulatory rules. AI-based or rule-based analytics services then process the data to identify critical operational events and calculate the probability of their occurrence. **Logging** tracks the sequence of data access and analyses."

### BUC#4: Electromobility: services roaming, load forecasting and schedule planning

**Scenario 1** — EV Booking Roaming Service.

*Actors:* EV Users (EVU), eMobility Service Providers (eMSP), eMobility Roaming Service Providers (EMRSP), and Charge Point Operators (CPOs). *Trigger:* "The service is triggered when the EVU initiates a booking request through the eMSP app."

"To ensure seamless execution, the following preconditions must be met:"

1. "The EVU is authenticated to the eMSP App, which is facilitated by the **Identity Management** building block."
2. "The eMSP must be registered as a consumer of EMRSP services, supported by **Publication & Discovery** mechanisms such as the Metadata Broker."
3. "CPOs must be registered as providers on the EMRSP app, which is managed through the **Contracting Framework**."
4. "Optionally, EMRSPs can be registered as providers of other EMRSPs, requiring a **Data Space Connector** for cross-platform integration."

"Upon successful booking, the following postconditions are achieved:"

1. "A reservation contract is established between the eMSP, EMRSP, and CPO. This is managed by the **Contracting Framework**, ensuring automated and secure agreements through smart contract execution."
2. "The DSO/TSO receives data on energy consumption, which is enabled by **Provenance & Traceability** mechanisms that securely log and verify energy transactions. Additionally, **Logging** ensures compliance and transaction monitoring."

"By leveraging these CEEDS building blocks, the EV Booking Roaming Service ensures secure authentication, seamless service discovery, automated contract negotiation, and transparent energy consumption tracking, all while maintaining interoperability within the European data space framework."

**Scenario 2** — EV Flexibility Service.

*Actors:* TSOs, DSOs, and eMSPs. *Trigger:* "The scenario starts when the TSO/DSO detects a flexibility need in the grid, requiring adjustments in EV charging schedules."

"The following precondition must be met to fulfil:"

1. "The TSO/DSO has received the baseline data on energy consumption from the EMSP, which is facilitated through the **Provenance & Traceability** building block to ensure data integrity and auditability."

"On completion of the flexibility request, the following postconditions would be achieved:"

1. "The EMSP sends the modified charging schedule of EVs, managed via the **Data Space Connector**, ensuring secure and interoperable data exchange."
2. "The DSO/TSO receives the updated data on energy consumption, supported by **Logging** (Clearing House) and **Publication & Discovery** to track and distribute real-time energy adjustments."

### BUC#5: Renewables O&M Optimization and Smart Grid Integration

**Scenario 1** — RES O&M Optimization.

- *Actors:* OEMs, RES plant owners/operators, Tier 2–3 component manufacturers, and data analytics service providers.
- *Trigger:* "the RES plant owner or operator requests predictive maintenance or performance optimization."
- *Precondition:* "operational data from RES assets must be available in the data space."
- *Realization:* "This is facilitated by a **Data Space Connector** to securely exchange data among actors. The **Vocabulary** could ensure the alignment of data semantics between manufacturers and analytics providers. **Identity Management** blocks guarantee only authorized participants get to query for the sensitive O&M data. **Access & Usage Policies** ensure data sovereignty by defining the rules and conditions for how this data should be used."
- *Postconditions:* "early detection of equipment failures, optimized maintenance scheduling, and generation of operational prescriptions."

**Scenario 2** — RES Smart Grid Integration.

- *Actors:* RES plant operators, prosumers, and DSOs.
- *Trigger:* "a DSO requests a service to manage grid constraints or balance voltage."
- *Precondition:* "This requires smart meter data and RES operational data to be accessible via the data space."
- *Realization:* "A **Metadata Broker** supports **Publication & Discovery** of such datasets, while secure exchange is facilitated by a **Data Space Connector**. Semantic alignment is handled through the **Vocabulary Hub** to ensure the interoperability of grid and RES datasets. **Identity Management** ensures authorized access for DSOs and plant operators, while **Access & Usage Policies** protect user data."
- *Postcondition:* "the anticipation of congestion or voltage issues, with corrective prescriptions communicated in real-time. **Provenance & Traceability** components and **Logging** tools document the data transactions and ensure regulatory compliance throughout the interaction."

**Scenario 3: Optimal RES Sizing (Prosumer/Community)**

- *Actors:* consumers/producers, data analytics service providers, and DSOs.
- *Trigger:* "a customer or energy community requests an optimal sizing recommendation for local RES installation."
- *Preconditions:* "generation, consumption, storage, geographic, EV usage, and pricing data must be available in the data space."
- *Realization:* "These datasets are accessed via a **Data Space Connector** (e.g., EDDIE Framework, Eclipse Dataspace Components), ensuring secure and interoperable exchange. The **Vocabulary Hub** (e.g., Semantic Treehouse) harmonizes diverse data sources, including geospatial and behavioural models. Access to personal or sensitive energy data is governed through **Access & Usage Policies**, implemented using ODRL (EDC) or XACML (TSG), aligned with GDPR. **Identity Management** (Keycloak or Gaia-X Verifiable Credentials) ensures that only verified users and analytics providers participate in the exchange."
- *Postcondition:* "the generation of an optimal configuration for RES capacity tailored to the user's demand, usage profile, and infrastructure context. All inputs and outputs are transparently logged using **Provenance & Traceability** services (e.g., Gaia-X Clearing House) to ensure trust and compliance."

**Scenario 4: DSO Resources Optimal Location**

- *Actors:* DSOs, consumers/producers, and data analytics service providers.
- *Trigger:* "the DSO requests a planning tool to determine optimal siting of new grid assets."
- *Preconditions:* "the availability of generation, consumption, and storage data; grid models (for digital twin simulation); existing grid issues; and available asset inventories in the data space."
- *Realization:* "These datasets are securely integrated using a **Data Space Connector**. Discovery of needed datasets is supported by **Publication & Discovery** mechanisms like Metadata Brokers. **Vocabulary Hub** components ensure the semantic alignment of grid topologies and asset specifications. Access to grid planning data is governed by **Access & Usage Policies**, while **Identity Management** ensures the right actors are granted access based on role and function."
- *Postcondition:* "a validated recommendation for the optimal location of DSO resources, derived through simulation and data analysis. The process is tracked using **Logging** and **Provenance & Traceability** components, ensuring transparency and the ability to audit planning decisions."

### Building blocks named per BUC scenario

Tabulation of the building blocks each §5.3 scenario explicitly names. Cells marked *(may)* are the ones the source states with an optional modal ("may be used", "could be used").

| Scenario | Publication & Discovery | Connector | Identity Management | Access & Usage Policy | Contract(ing) Framework | Vocabulary (Hub) | Logging | Provenance & Traceability |
|---|---|---|---|---|---|---|---|---|
| BUC#1 S1 | yes | yes | yes | — | *(may)* | — | *(may)* | *(may)* |
| BUC#1 S2 | yes | yes | yes | — | *(may)* | — | yes | yes |
| BUC#1 S3 | yes | yes | yes | — | *(may)* | — | yes | yes |
| BUC#2 | yes | yes | yes | yes | yes | yes | yes | yes |
| BUC#3 S1 | yes | yes | yes | yes | yes | — | yes | yes |
| BUC#3 S2 | yes | yes | yes | yes | yes | — | yes | yes |
| BUC#3 S3 | yes | yes | yes | yes | — | — | *(may)* | *(may)* |
| BUC#3 S4 | yes | yes | yes | yes | — | *(may)* | yes | yes |
| BUC#3 S5 | yes | yes | yes | yes | — | — | yes | — |
| BUC#4 S1 | yes | *(may)* | yes | — | yes | — | yes | yes |
| BUC#4 S2 | yes | yes | — | — | — | yes | — | yes |
| BUC#5 S1 | — | yes | yes | yes | — | *(may)* | — | — |
| BUC#5 S2 | yes | yes | yes | yes | — | yes | yes | yes |
| BUC#5 S3 | — | yes | yes | yes | — | yes | — | yes |
| BUC#5 S4 | yes | yes | yes | yes | — | yes | yes | yes |

## 5.4. Data value creation aspects

"The EDSCP address data value creation as one fundamental pillar of their data space implementations. The data value creation is pursued in a trustworthy data space implementation according to three different aspects: (i) the publication and discovery of data and services, (ii) the value-added mechanisms, and (iii) the business mechanisms of the compensations."

### The publication and discovery of data and services

"The publication and discovery of data and services is pursued with data cataloguing, implementing dedicated marketplaces. The Gaia-X specifications constitute a valid reference for the implementation (as for OMEGA-X, ENERSHARE, DATA CELLAR and the EDDIE Data Marketplace), specifically the so-called 'marketplace federator' (or 'federator'), which is an entity dealing with managing a set of marketplace functionalities (e.g., inviting administrators, approving the registration of users, accepting offering descriptions uploaded by users, and accepting the deletion of offerings). Moreover, this eases interoperability as the federated catalogue can sync with multiple provider catalogues from any other data space. SYNERGIES' data marketplace on the other hand is compliant with IDS RAM specifications and supports data cataloguing, search, request and contracting features similar to the other marketplaces."

Marketplace functionality, per the source:

1. data search;
2. data request, "with specifications regarding the desired duration of use for the dataset, and the expected use of the dataset";
3. data contracting;
4. the data contracting payment.

"The data contracting is based on a draft contract that includes (i) predefined terms, (ii) free-text terms (to allow the data providers to include their own terms) and (iii) reimbursement details — either the monetary cost or the profile of the dataset expected to be exchanged in a bartering transaction."

"Multiple projects opt for the centralized configuration of both the catalogue and the data exploration services, with a strong focus on the human- and machine-readability of look-up mechanisms and result formats. Moreover, the marketplace in DATA CELLAR and SYNERGIES is built around a push approach, meaning that each data/service provider is solely responsible for publishing, updating, and revoking their listings in the catalogue; this approach excludes the need for a catalogue maintainer or a sophisticated synchronization mechanism. The implemented approach is facilitated using the catalogue's API in authorized mode (which exposes endpoints otherwise not available in the public/non-authorized mode). The syntactic and semantic verification of any submitted self-description against predefined schemas (aligned with the released GAIA-X schemas) can be performed using SHACL checks; security measures include the cryptographic verification of DIDs and VC/VPs."

### The value-added mechanisms

"The value-added mechanisms involve a variety of services." SYNERGIES categorizes them in:

1. **data services** — including the monitoring and certification of data asset origins as well as data observability service to monitor the status of each active data check-in pipeline;
2. **generic services** — e.g., privacy preservation services, encryption service, access policy service (which define the resolution and which part of the data asset is accessed), security, authentication & authorisation services;
3. **AI services**; and
4. **application services** — dedicated to the data analysis, insight extraction (even pre-trained for energy applications) also related to the project use cases.

"ENERSHARE identifies two added-value services to support the roll-out of services in the CEEDS: (i) barter monetization and incentives module, which evaluates the intrinsic data value and enabling data monetization schemes, and (ii) data transformation service, based on a syntactic model to translate primary data into a semantic data representation. For example, ENERSHARE's federated learning platform enables training decentralized data across multiple devices, allowing seamless aggregation of models trained on local data while promoting knowledge sharing. Additionally, the added value of the enhanced service for multi-energy flexibility potential assessment is the support of data-driven models for user profiling, rather than just statistically-based models of the household. In general, the projects highlight the need to establish clear incentives for data sharing, while still ensuring data privacy as a complement for plain data exchange."

"Additionally, DATA CELLAR project delivers a comprehensive suite of value-added services, strategically designed to maximize the benefits of rich data transactions within the data space. Reflecting on the crucial aspects of participation management and user interaction, the project focuses on enhancing user training and engagement to maximize the adoption and usability of the deployed technologies."

### The business mechanisms of the compensations

"The business mechanisms of the compensations rely on transaction schemes that will be regulated by formalized data contract templates and enable secure and trusted data asset sharing, trading and bartering, while allowing energy data value chain stakeholders to efficiently search for data assets of interest and providing them with intelligent recommendations for relevant data assets or data assets' providers."

"The compensation is implemented with three different approaches:"

- **Data by tokens** — "in which the access to assets (data, apps, services) is granted based on payment using a cryptographic token (specific for each data space)".
- **Data by data** — "in which the access to assets (data, apps, services) is granted according to intrinsic value of data (through the barter exchange and incentives module) allowing a data set to be exchange for another data set with equivalent value."
- **Data by currency** (limited to ENERSHARE) — "in which the access to assets (data, apps, services) is granted based on payment on FIAT currency (which can be handled through the marketplace)."

"Moreover, the marketplace can generate revenues charging a small percentage as a transaction fee for each transaction; as the platform also accommodates auctions, which do not involve token transactions, a fee is applied for the participation in it. To incentivize platform usage, a strategy could be to offer free access to auctions for a user's initial participation and then, a fixed subscription cost."

**SYNERGIES Contract Settlement Engine** (project context). "SYNERGIES implements a 'Contract Settlement Engine' which is responsible for handling the payment of the monetary cost or the fulfilment of the counter price (e.g. other dataset) in order to activate a smart contract that has been already duly signed by the legal representatives of the involved parties." The Contract Settlement Engine enables:

1. settlement of data bartering agreements (e.g., granularity levels and time frames);
2. settlement of monetary transactions of data sharing agreements (verifying the money exchange between the related data asset provider(s) and data consumer);
3. monitoring of any active contract to ensure compliance with the agreed terms (e.g., consistent data quality, freshness, and update rate as agreed), issuing alerts in case the terms of a data sharing contract are not respected, and terminating a contract in case of breached terms.

"The Smart Contract Settlement Engine consists of: (a) a back-end component that is developed on NodeJS and in particular on the NestJS framework, (b) a blockchain layer, leveraging the Ethereum distributed platform and (c) a front-end component that builds on VueJS and TailwindCSS."

**DATA CELLAR licensing** (project context). "DATA CELLAR solutions work with licenses associated with the digitized objects that represent energy assets (both datasets and AI models). It works with blockchain, using specific smart contracts written in Solidity that administer the exchanges in terms of economics and assets. In particular, two main standards have been used to define the digitization of assets, licenses and the currency used to buy and sell on the platform: ERC721 and ERC20, associated with the creation of non-fungible and fungible tokens, respectively. Licenses can be of two types: 'period' or 'usage'; the former allows the associated energy data to be used an unlimited number of times, while usage licenses are consumed each time they are used. Every license will be associated with a specific amount of DATA CELLAR Token, which represents the license price. The setup includes also a 'balancer', which handles the monetary exchange between tokens and licenses. This component is responsible for making the practical exchange between these two assets, verifying all the constraints associated with the payment (buyer's funds and availability of the license)."

**EDDIE Data Marketplace** (project context). "EDDIE features a Data Marketplace, where data consumers can submit their data needs in a feature-based way, enabling e.g. machine-learning based solutions to crowd-source data based on characteristics of electricity prosumers. As the access to realising, tailored, high-quality data is an important pre-requisite for trustworthy models, the EDDIE Data Marketplace closes a very important gap. Apart from the access to real-world crowd-sourced data it offers compensation mechanisms for distributed data providers and data-service vendors, whilst preserving customer sovereignty and full GDPR compliance."

## Standards and protocols

Every entry below is named by chapter 5 as part of a pilot implementation or as a compliance target of one. The chapter mandates none of them for CEEDS; the force is therefore `referenced` throughout. Names, versions and spellings are the source's.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| IEC CIM | — | EDDIE Data Space Connector information model; EDDIE Framework translates national information models into IEC CIM | referenced |
| OASIS AS4 | — | EDDIE communication protocol | referenced |
| AS4 | — | EDDIE Logging compliance for repeatability, non-reputability and auditability | referenced |
| REST | — | EDDIE communication protocol; ENERSHARE Clearing House "does not follow specific standards beyond REST APIs" | referenced |
| Kafka | — | EDDIE communication protocol; Kafka connectors ensure cross-sectoral interoperability | referenced |
| AMQP | — | EDDIE communication protocol | referenced |
| MQTT5 | — | EDDIE communication protocol for edge deployments | referenced |
| Green Button CMD | US / CAN | EDDIE Framework connectivity beyond EU Member States | referenced |
| OpenID Connect | — | EDDIE, SYNERGIES and Data Cellar Identity Management | referenced |
| eID | — | EDDIE IAM connections | referenced |
| eIDAS | — | EDDIE IAM connections; EDDIE Provenance & Traceability standard compliance | referenced |
| X.509 | — | EDDIE Provenance & Traceability signing and encryption; BUC#2 provenance mechanisms | referenced |
| DSSC | reference architectures; practices | EDDIE Identity Management alignment; EDDIE Contracting Framework practices; SYNERGIES Access Policy Engine alignment | referenced |
| GDPR | — | EDDIE Access & Usage Policies compliance; BUC#5 Scenario 3 policy alignment; EDDIE Data Marketplace | referenced |
| Data Governance Act | — | EDDIE Access & Usage Policies compliance | referenced |
| Gaia-X architecture | 22.10 Release | SYNERGIES Data Space Connector alignment | referenced |
| IDS RAM | — | SYNERGIES connector, IAM, Vocabulary Hub, Contracting Framework, Provenance & Traceability, Access Policy Engine | referenced |
| IDSA Reference Architecture Model | v4 | TSG connector certification; ENERSHARE Identity Management ("IDSA RAM v4"), Semantic Treehouse | referenced |
| IDS-RAM | v4 | ENERSHARE TSG-based Metadata Broker compliance | referenced |
| OAuth 2.0 | — | SYNERGIES Identity Management compliance | referenced |
| Gaia-X Trust Framework | — | SYNERGIES IAM alignment; Data Cellar IAM and XFSC Federated Catalogue compliance; OMEGA-X Identity Management | referenced |
| IDS Clearing House | — | SYNERGIES Contract Settlement Engine full compliance | referenced |
| IEC 62325 | — | SYNERGIES CIM Network Manager supported standard | referenced |
| OpenADR3.0 | — | SYNERGIES CIM Network Manager supported standard | referenced |
| SAREF4ENER | — | SYNERGIES CIM Network Manager supported standard | referenced |
| OCPP | — | SYNERGIES CIM Network Manager supported standard | referenced |
| Ethereum | — | SYNERGIES DLT Smart Contract Management Engine; blockchain layer of the Smart Contract Settlement Engine | referenced |
| IDS RAM Metadata Broker and App Store | — | SYNERGIES Data Marketplace specification alignment | referenced |
| Gaia-X Clearing House | — | SYNERGIES Contracting Framework alignment | referenced |
| International Data Spaces (IDS) Dataspace Protocol | — | Data Cellar Data Space Connector (EDC) | referenced |
| IDS Dataspace Protocol's Contract Negotiation Protocol | — | Data Cellar Contracting Framework, implemented via the EDC Connector framework | referenced |
| Dataspace Protocol | — | DATA CELLAR "Dataspace Protocol-compliant connector" for Validation Case services | referenced |
| Data Space Protocol (DSP) | — | OMEGA-X EDC contract negotiation and secure data transfers; not yet supported by the Energy Data Space Connector v1.1 | referenced |
| OpenID Connector for Verifiable Credentials (OID4VC) | — | Data Cellar Identity Management compliance; Table 9 DataCellar Verifiable Credentials | referenced |
| OID4VCI | — | OMEGA-X Verifiable Credential issuer | referenced |
| W3C Verifiable Credentials | — | Data Cellar Access & Usage Policies | referenced |
| Decentralized Identifiers (DIDs) | — | Data Cellar walt.id issuance; cryptographic verification of DIDs and VC/VPs in §5.4 | referenced |
| OWL | — | Data Cellar bespoke ontology | referenced |
| RDF | — | Data Cellar bespoke ontology | referenced |
| JSON-LD | — | Data Cellar bespoke ontology; OMEGA-X CSDM REST API standard | referenced |
| SAREF | — | Data Cellar well-known vocabulary | referenced |
| ThinkHome | — | Data Cellar well-known vocabulary | referenced |
| ODRL | — | Data Cellar EDC policy engine; ENERSHARE EDC-based enforcement; BUC#5 Scenario 3 (EDC) | referenced |
| JWT | — | Data Cellar Access & Usage Policies | referenced |
| OPENAPI | — | OMEGA-X CSDM ontology-based REST API standard | referenced |
| Docker | — | OMEGA-X Gaia-X Federated Catalogue instance compliance | referenced |
| Python | v3.12 | OMEGA-X Gaia-X Federated Catalogue instance compliance | referenced |
| RDFS/OWL | — | ENERSHARE Semantic Treehouse supported open standard | referenced |
| SHACL | — | ENERSHARE Semantic Treehouse supported open standard; syntactic and semantic verification of submitted self-descriptions (§5.4) | referenced |
| JSON schema | — | ENERSHARE Semantic Treehouse supported open standard | referenced |
| GAIA-X schemas | released | predefined schemas against which self-descriptions are verified (§5.4) | referenced |
| XACML | — | ENERSHARE TSG and Energy Data Space Connector policies; BUC#5 Scenario 3 (TSG) | referenced |
| ERC20 | — | ENERSHARE tokenized transactions; DATA CELLAR fungible tokens | referenced |
| ERC721 | — | DATA CELLAR non-fungible tokens for assets and licenses | referenced |
| Solidity | — | DATA CELLAR smart contracts administering exchanges | referenced |

Named components and tooling that chapter 5 cites but that are products rather than specifications — EDDIE Framework, AIIDA, EDDIE Data Marketplace, EDDIE Online, EDDIE Data Needs definition language, Synergies Dataspace Connector, Security, Authentication & Authorization Engine, Contract Settlement Engine, CIM Network Manager, DLT Smart Contract Management Engine, Access Policy Engine, Eclipse Dataspace Components (EDC), sovity Connector-as-a-Service (CaaS), Keycloak, walt.id, IDSA – DAPS, EJBCA, Kubernetes logging operator with Fluentd and Fluentbit, Common Semantic Data Model (CSDM), Gaia-X Federated Catalogue, XFSC Federated Catalogue, Gaia-X Digital Clearing House (GXDCH), TNO Security Gateway (TSG), TSG Identity Provider, Energy Data Space Connector v1.1 (based on the OneNet Connector), Semantic Treehouse, Metadata Broker, NodeJS/NestJS, VueJS, TailwindCSS — are recorded in the sections above as project context.

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

**Conventions used in this table.** Force is the source's own. Where the source labels a statement a *precondition* for a business use case scenario, force is recorded as `must`, because the chapter states "the following preconditions must be met" or "requires" in the majority of cases; where the source labels a statement a *postcondition*, force is likewise recorded as `must`, although the source phrases postconditions in the indicative ("the following postconditions are achieved") rather than with a modal — see "Open questions". Everything else that is plain descriptive prose is recorded as `informative`, never promoted. Statements that name only which tool a specific pilot chose are project context and appear in the body and in "Standards and protocols", not here.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-IMP-01` | The implementation survey tracks eight CEEDS Building Blocks: Connector, Identity Management, Logging, Vocabulary Hub, Contract Framework, Publication & Discovery, Provenance & Traceability, Access & Usage Policy. | informative | `Blueprint_CEEDS_v3.0.txt:1811-1857` |
| `CEEDS-IMP-02` | If an implementation for a specific building block does not exist within a project, the corresponding field is left blank in Table 9. | informative | `Blueprint_CEEDS_v3.0.txt:1803-1805` |
| `CEEDS-IMP-03` | BUC#1 Scenario 1 — consumption and generation profiles must already be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2072-2073` |
| `CEEDS-IMP-04` | BUC#1 Scenario 1 — tariff data must already be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2072-2073` |
| `CEEDS-IMP-05` | BUC#1 Scenario 1 — inputs are accessed using the Publication & Discovery building block, to ensure the right datasets are discoverable and accessible to authorized service providers. | informative | `Blueprint_CEEDS_v3.0.txt:2073-2075` |
| `CEEDS-IMP-06` | BUC#1 Scenario 1 — the Data Space Connector enables secure data exchange between the data providers and the analytics services operated by ESCOs or aggregators. | informative | `Blueprint_CEEDS_v3.0.txt:2076-2077` |
| `CEEDS-IMP-07` | BUC#1 Scenario 1 — Identity Management verifies and authorizes the requesting service provider and ensures trusted access to consumer data. | informative | `Blueprint_CEEDS_v3.0.txt:2077-2084` |
| `CEEDS-IMP-08` | BUC#1 Scenario 1 — Provenance & Traceability may be used to ensure the output data and any contractual terms are verifiable and traceable. | may | `Blueprint_CEEDS_v3.0.txt:2085-2087` |
| `CEEDS-IMP-09` | BUC#1 Scenario 1 — Logging may be used to ensure the output data and any contractual terms are verifiable and traceable. | may | `Blueprint_CEEDS_v3.0.txt:2085-2087` |
| `CEEDS-IMP-10` | BUC#1 Scenario 1 — if the service is offered through a marketplace model, the Contracting Framework could be used to formalize service agreements or pricing models. | may | `Blueprint_CEEDS_v3.0.txt:2087-2089` |
| `CEEDS-IMP-11` | BUC#1 Scenario 2 — technical metadata about the EWH (e.g. tank volume, heating power) must already be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2097-2100` |
| `CEEDS-IMP-12` | BUC#1 Scenario 2 — historical shower patterns (duration and timing) must already be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2097-2100` |
| `CEEDS-IMP-13` | BUC#1 Scenario 2 — sensor data (such as outlet water temperature) must already be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2097-2100` |
| `CEEDS-IMP-14` | BUC#1 Scenario 2 — inputs are discovered through the Publication & Discovery building block, ensuring authorized actors can identify and access the necessary datasets. | informative | `Blueprint_CEEDS_v3.0.txt:2100-2101` |
| `CEEDS-IMP-15` | BUC#1 Scenario 2 — data exchange between the sub-meter data hub and the analytical services is secured using a Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2101-2102` |
| `CEEDS-IMP-16` | BUC#1 Scenario 2 — Identity Management components authenticate and authorize access so that only verified entities interact with sensitive household-level data. | informative | `Blueprint_CEEDS_v3.0.txt:2103-2104` |
| `CEEDS-IMP-17` | BUC#1 Scenario 2 — Provenance & Traceability components record data flows and transformations, to ensure auditability and trust. | informative | `Blueprint_CEEDS_v3.0.txt:2106-2107` |
| `CEEDS-IMP-18` | BUC#1 Scenario 2 — Logging mechanisms reinforce transparency in data processing. | informative | `Blueprint_CEEDS_v3.0.txt:2108` |
| `CEEDS-IMP-19` | BUC#1 Scenario 2 — if the service is offered commercially, a Contract Framework may be employed to automate pricing and formalize agreements for ongoing flexibility service provision. | may | `Blueprint_CEEDS_v3.0.txt:2108-2110` |
| `CEEDS-IMP-20` | BUC#1 Scenario 3 — consumption and generation series and relevant tariff data are accessed through the Publication & Discovery component. | informative | `Blueprint_CEEDS_v3.0.txt:2116-2117` |
| `CEEDS-IMP-21` | BUC#1 Scenario 3 — data exchange is secured using a Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2117-2118` |
| `CEEDS-IMP-22` | BUC#1 Scenario 3 — Identity Management ensures authorized access to sensitive consumption data. | informative | `Blueprint_CEEDS_v3.0.txt:2118-2119` |
| `CEEDS-IMP-23` | BUC#1 Scenario 3 — the Contract Framework may define billing logic or compensation models among members. | may | `Blueprint_CEEDS_v3.0.txt:2120-2121` |
| `CEEDS-IMP-24` | BUC#1 Scenario 3 — Provenance & Traceability supports transparency in data origin and processing. | informative | `Blueprint_CEEDS_v3.0.txt:2121-2122` |
| `CEEDS-IMP-25` | BUC#1 Scenario 3 — Logging mechanisms ensure auditability of the billing computation process. | informative | `Blueprint_CEEDS_v3.0.txt:2122-2128` |
| `CEEDS-IMP-26` | BUC#2 — DER unit registration into the flexibility registry uses the Connector building block to enable secure data exchange between the prosumer and service platforms. | informative | `Blueprint_CEEDS_v3.0.txt:2135-2138` |
| `CEEDS-IMP-27` | BUC#2 — Identity Management ensures proper authentication and authorization of the actor submitting the data. | informative | `Blueprint_CEEDS_v3.0.txt:2138-2140` |
| `CEEDS-IMP-28` | BUC#2 — access permissions for DER metadata and control preferences are managed through Access & Usage Policy enforcement. | informative | `Blueprint_CEEDS_v3.0.txt:2141-2142` |
| `CEEDS-IMP-29` | BUC#2 — provenance of the baseline-calculation data flows is maintained using Provenance & Traceability mechanisms, ensuring data lineage and auditability. | informative | `Blueprint_CEEDS_v3.0.txt:2143-2145` |
| `CEEDS-IMP-30` | BUC#2 — the Vocabulary Hub supports semantic alignment, to harmonize data inputs across participants. | informative | `Blueprint_CEEDS_v3.0.txt:2146-2147` |
| `CEEDS-IMP-31` | BUC#2 — Logging activities document the analytics and processing stages. | informative | `Blueprint_CEEDS_v3.0.txt:2147-2148` |
| `CEEDS-IMP-32` | BUC#2 — when flexibility potential is established, the FSP initiates a bidding process via a Contract Framework, allowing automated contract generation between the FSP and grid operators (TSO/DSO). | informative | `Blueprint_CEEDS_v3.0.txt:2148-2150` |
| `CEEDS-IMP-33` | BUC#2 — observed flexibility delivery is reported via Publication & Discovery. | informative | `Blueprint_CEEDS_v3.0.txt:2151-2153` |
| `CEEDS-IMP-34` | BUC#2 — data logs are captured via Logging to support settlement and compliance. | informative | `Blueprint_CEEDS_v3.0.txt:2153-2154` |
| `CEEDS-IMP-35` | BUC#3 Scenario 1 — the data space must already contain diverse asset types including raw data, processed analytics, reports and visualizations. | must | `Blueprint_CEEDS_v3.0.txt:2162-2163` |
| `CEEDS-IMP-36` | BUC#3 Scenario 1 — those asset types must all be structured for automated consumption. | must | `Blueprint_CEEDS_v3.0.txt:2162-2163` |
| `CEEDS-IMP-37` | BUC#3 Scenario 1 — Publication & Discovery allows the consumer to identify and locate suitable data assets across multiple federated spaces. | informative | `Blueprint_CEEDS_v3.0.txt:2164-2165` |
| `CEEDS-IMP-38` | BUC#3 Scenario 1 — the Connector facilitates secure access to the selected asset. | informative | `Blueprint_CEEDS_v3.0.txt:2166` |
| `CEEDS-IMP-39` | BUC#3 Scenario 1 — authentication and authorization are enforced through Identity Management components, ensuring that only verified actors can proceed. | informative | `Blueprint_CEEDS_v3.0.txt:2166-2168` |
| `CEEDS-IMP-40` | BUC#3 Scenario 1 — prior to access, a valid usage agreement is formalized using the Contract Framework, specifying the terms and conditions under which the asset may be consumed. | informative | `Blueprint_CEEDS_v3.0.txt:2168-2169` |
| `CEEDS-IMP-41` | BUC#3 Scenario 1 — Access & Usage Policy governs how the data may be used once shared. | informative | `Blueprint_CEEDS_v3.0.txt:2175-2176` |
| `CEEDS-IMP-42` | BUC#3 Scenario 1 — Logging records search actions and access events for traceability. | informative | `Blueprint_CEEDS_v3.0.txt:2176-2177` |
| `CEEDS-IMP-43` | BUC#3 Scenario 1 — the Provenance & Traceability building block ensures that any analysis built on the retrieved asset maintains a verifiable data lineage. | informative | `Blueprint_CEEDS_v3.0.txt:2177-2178` |
| `CEEDS-IMP-44` | BUC#3 Scenario 2 — the requester locates the desired dataset or visualization using the Publication & Discovery block. | informative | `Blueprint_CEEDS_v3.0.txt:2183-2185` |
| `CEEDS-IMP-45` | BUC#3 Scenario 2 — secure exchange is established through a Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2185` |
| `CEEDS-IMP-46` | BUC#3 Scenario 2 — Identity Management authenticates both the provider and the consumer. | informative | `Blueprint_CEEDS_v3.0.txt:2185-2186` |
| `CEEDS-IMP-47` | BUC#3 Scenario 2 — a usage agreement is formalized by the Contract Framework. | informative | `Blueprint_CEEDS_v3.0.txt:2186-2187` |
| `CEEDS-IMP-48` | BUC#3 Scenario 2 — permissions are enforced via the Access & Usage Policy engine. | informative | `Blueprint_CEEDS_v3.0.txt:2187` |
| `CEEDS-IMP-49` | BUC#3 Scenario 2 — throughout the transaction, Logging and Provenance & Traceability components record events and data lineage. | informative | `Blueprint_CEEDS_v3.0.txt:2188-2189` |
| `CEEDS-IMP-50` | BUC#3 Scenario 3 — the process begins with the availability of metering data and DER-specific datasets used to train and execute AI models. | informative | `Blueprint_CEEDS_v3.0.txt:2195-2196` |
| `CEEDS-IMP-51` | BUC#3 Scenario 3 — datasets are located and retrieved using the Publication & Discovery building block, ensuring access to both raw input and prior analytics results. | informative | `Blueprint_CEEDS_v3.0.txt:2196-2198` |
| `CEEDS-IMP-52` | BUC#3 Scenario 3 — data exchange between metering infrastructure, DER platforms and AI forecasting services is securely managed via the Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2199-2200` |
| `CEEDS-IMP-53` | BUC#3 Scenario 3 — access rights are governed by the Access & Usage Policy component. | informative | `Blueprint_CEEDS_v3.0.txt:2200-2201` |
| `CEEDS-IMP-54` | BUC#3 Scenario 3 — identity verification of DSOs and TSOs is ensured through Identity Management systems. | informative | `Blueprint_CEEDS_v3.0.txt:2201` |
| `CEEDS-IMP-55` | BUC#3 Scenario 3 — forecast results may be logged and tracked using Logging and Provenance & Traceability, to ensure auditability and compliance with regulatory frameworks. | may | `Blueprint_CEEDS_v3.0.txt:2203-2204` |
| `CEEDS-IMP-56` | BUC#3 Scenario 4 — DER data (technical metadata, usage history, real-time measurements) is accessed via the Publication & Discovery building block, to ensure discoverability across federated data spaces. | informative | `Blueprint_CEEDS_v3.0.txt:2212-2214` |
| `CEEDS-IMP-57` | BUC#3 Scenario 4 — data exchange for training and inference is securely facilitated through a Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2215` |
| `CEEDS-IMP-58` | BUC#3 Scenario 4 — Identity Management ensures only the authorized FSP can access the required datasets. | informative | `Blueprint_CEEDS_v3.0.txt:2215-2216` |
| `CEEDS-IMP-59` | BUC#3 Scenario 4 — permissions for data use are enforced through Access & Usage Policy mechanisms, leveraging policy engines integrated into the Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2216-2222` |
| `CEEDS-IMP-60` | BUC#3 Scenario 4 — flexibility forecasts may be supported semantically using a Vocabulary to harmonize data structures. | may | `Blueprint_CEEDS_v3.0.txt:2223-2224` |
| `CEEDS-IMP-61` | BUC#3 Scenario 4 — logging of key access and execution steps is maintained through the Logging component. | informative | `Blueprint_CEEDS_v3.0.txt:2224-2225` |
| `CEEDS-IMP-62` | BUC#3 Scenario 4 — Provenance & Traceability ensures all analytics outcomes are auditable. | informative | `Blueprint_CEEDS_v3.0.txt:2225-2226` |
| `CEEDS-IMP-63` | BUC#3 Scenario 5 — detailed data on the current transmission and distribution network topology and infrastructure is required. | must | `Blueprint_CEEDS_v3.0.txt:2233-2235` |
| `CEEDS-IMP-64` | BUC#3 Scenario 5 — access to reliable short- and mid-term demand and generation forecasts is required. | must | `Blueprint_CEEDS_v3.0.txt:2233-2235` |
| `CEEDS-IMP-65` | BUC#3 Scenario 5 — datasets are located using the Publication & Discovery building block, to ensure comprehensive and authorized access across domains. | informative | `Blueprint_CEEDS_v3.0.txt:2235-2237` |
| `CEEDS-IMP-66` | BUC#3 Scenario 5 — data transfer between grid models, forecast systems and analytics platforms is handled securely via the Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2238-2239` |
| `CEEDS-IMP-67` | BUC#3 Scenario 5 — Identity Management verifies that only authorized operators can initiate the request and retrieve sensitive network data. | informative | `Blueprint_CEEDS_v3.0.txt:2239-2240` |
| `CEEDS-IMP-68` | BUC#3 Scenario 5 — Access & Usage Policy enforcement ensures that data is consumed in compliance with contractual and regulatory rules. | informative | `Blueprint_CEEDS_v3.0.txt:2240-2241` |
| `CEEDS-IMP-69` | BUC#3 Scenario 5 — Logging tracks the sequence of data access and analyses. | informative | `Blueprint_CEEDS_v3.0.txt:2243-2244` |
| `CEEDS-IMP-70` | BUC#4 Scenario 1 precondition 1 — the EVU is authenticated to the eMSP App, facilitated by the Identity Management building block. | must | `Blueprint_CEEDS_v3.0.txt:2256-2258` |
| `CEEDS-IMP-71` | BUC#4 Scenario 1 precondition 2 — the eMSP must be registered as a consumer of EMRSP services, supported by Publication & Discovery mechanisms such as the Metadata Broker. | must | `Blueprint_CEEDS_v3.0.txt:2259-2260` |
| `CEEDS-IMP-72` | BUC#4 Scenario 1 precondition 3 — CPOs must be registered as providers on the EMRSP app, managed through the Contracting Framework. | must | `Blueprint_CEEDS_v3.0.txt:2261-2262` |
| `CEEDS-IMP-73` | BUC#4 Scenario 1 precondition 4 — optionally, EMRSPs can be registered as providers of other EMRSPs, requiring a Data Space Connector for cross-platform integration. | may | `Blueprint_CEEDS_v3.0.txt:2268-2269` |
| `CEEDS-IMP-74` | BUC#4 Scenario 1 postcondition 1 — a reservation contract is established between the eMSP, EMRSP and CPO, managed by the Contracting Framework, ensuring automated and secure agreements through smart contract execution. | must | `Blueprint_CEEDS_v3.0.txt:2271-2274` |
| `CEEDS-IMP-75` | BUC#4 Scenario 1 postcondition 2 — the DSO/TSO receives data on energy consumption, enabled by Provenance & Traceability mechanisms that securely log and verify energy transactions. | must | `Blueprint_CEEDS_v3.0.txt:2275-2277` |
| `CEEDS-IMP-76` | BUC#4 Scenario 1 postcondition 2 — Logging ensures compliance and transaction monitoring. | must | `Blueprint_CEEDS_v3.0.txt:2275-2277` |
| `CEEDS-IMP-77` | BUC#4 Scenario 2 precondition — the TSO/DSO has received the baseline data on energy consumption from the EMSP, facilitated through the Provenance & Traceability building block to ensure data integrity and auditability. | must | `Blueprint_CEEDS_v3.0.txt:2287-2289` |
| `CEEDS-IMP-78` | BUC#4 Scenario 2 postcondition — the EMSP sends the modified charging schedule of EVs, managed via the Data Space Connector, ensuring secure and interoperable data exchange. | must | `Blueprint_CEEDS_v3.0.txt:2290-2292` |
| `CEEDS-IMP-79` | BUC#4 Scenario 2 postcondition — the DSO/TSO receives the updated data on energy consumption, supported by Logging (Clearing House) and Publication & Discovery to track and distribute real-time energy adjustments. | must | `Blueprint_CEEDS_v3.0.txt:2293-2294` |
| `CEEDS-IMP-80` | BUC#5 Scenario 1 precondition — operational data from RES assets must be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2301-2303` |
| `CEEDS-IMP-81` | BUC#5 Scenario 1 — a Data Space Connector securely exchanges data among actors. | informative | `Blueprint_CEEDS_v3.0.txt:2303-2304` |
| `CEEDS-IMP-82` | BUC#5 Scenario 1 — the Vocabulary could ensure the alignment of data semantics between manufacturers and analytics providers. | may | `Blueprint_CEEDS_v3.0.txt:2304-2305` |
| `CEEDS-IMP-83` | BUC#5 Scenario 1 — Identity Management blocks guarantee only authorized participants get to query for the sensitive O&M data. | informative | `Blueprint_CEEDS_v3.0.txt:2305-2306` |
| `CEEDS-IMP-84` | BUC#5 Scenario 1 — Access & Usage Policies ensure data sovereignty by defining the rules and conditions for how the data should be used. | informative | `Blueprint_CEEDS_v3.0.txt:2306-2307` |
| `CEEDS-IMP-85` | BUC#5 Scenario 2 precondition — smart meter data must be accessible via the data space. | must | `Blueprint_CEEDS_v3.0.txt:2318-2319` |
| `CEEDS-IMP-86` | BUC#5 Scenario 2 precondition — RES operational data must be accessible via the data space. | must | `Blueprint_CEEDS_v3.0.txt:2318-2319` |
| `CEEDS-IMP-87` | BUC#5 Scenario 2 — a Metadata Broker supports Publication & Discovery of such datasets. | informative | `Blueprint_CEEDS_v3.0.txt:2319-2320` |
| `CEEDS-IMP-88` | BUC#5 Scenario 2 — secure exchange is facilitated by a Data Space Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2320-2321` |
| `CEEDS-IMP-89` | BUC#5 Scenario 2 — semantic alignment is handled through the Vocabulary Hub, to ensure the interoperability of grid and RES datasets. | informative | `Blueprint_CEEDS_v3.0.txt:2321-2322` |
| `CEEDS-IMP-90` | BUC#5 Scenario 2 — Identity Management ensures authorized access for DSOs and plant operators. | informative | `Blueprint_CEEDS_v3.0.txt:2322-2323` |
| `CEEDS-IMP-91` | BUC#5 Scenario 2 — Access & Usage Policies protect user data. | informative | `Blueprint_CEEDS_v3.0.txt:2323` |
| `CEEDS-IMP-92` | BUC#5 Scenario 2 — Provenance & Traceability components and Logging tools document the data transactions and ensure regulatory compliance throughout the interaction. | informative | `Blueprint_CEEDS_v3.0.txt:2325-2326` |
| `CEEDS-IMP-93` | BUC#5 Scenario 3 precondition — generation, consumption, storage, geographic, EV usage and pricing data must be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2332-2334` |
| `CEEDS-IMP-94` | BUC#5 Scenario 3 — those datasets are accessed via a Data Space Connector, ensuring secure and interoperable exchange. | informative | `Blueprint_CEEDS_v3.0.txt:2334-2336` |
| `CEEDS-IMP-95` | BUC#5 Scenario 3 — the Vocabulary Hub harmonizes diverse data sources, including geospatial and behavioural models. | informative | `Blueprint_CEEDS_v3.0.txt:2336-2337` |
| `CEEDS-IMP-96` | BUC#5 Scenario 3 — access to personal or sensitive energy data is governed through Access & Usage Policies, implemented using ODRL (EDC) or XACML (TSG), aligned with GDPR. | informative | `Blueprint_CEEDS_v3.0.txt:2337-2339` |
| `CEEDS-IMP-97` | BUC#5 Scenario 3 — Identity Management ensures that only verified users and analytics providers participate in the exchange. | informative | `Blueprint_CEEDS_v3.0.txt:2338-2340` |
| `CEEDS-IMP-98` | BUC#5 Scenario 3 — all inputs and outputs are transparently logged using Provenance & Traceability services, to ensure trust and compliance. | informative | `Blueprint_CEEDS_v3.0.txt:2341-2343` |
| `CEEDS-IMP-99` | BUC#5 Scenario 4 precondition — generation, consumption and storage data must be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2351-2353` |
| `CEEDS-IMP-100` | BUC#5 Scenario 4 precondition — grid models (for digital twin simulation) must be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2351-2353` |
| `CEEDS-IMP-101` | BUC#5 Scenario 4 precondition — existing grid issues must be available in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2351-2353` |
| `CEEDS-IMP-102` | BUC#5 Scenario 4 precondition — available asset inventories must be in the data space. | must | `Blueprint_CEEDS_v3.0.txt:2351-2353` |
| `CEEDS-IMP-103` | BUC#5 Scenario 4 — datasets are securely integrated using a Data Space Connector. | informative | `Blueprint_CEEDS_v3.0.txt:2353-2354` |
| `CEEDS-IMP-104` | BUC#5 Scenario 4 — discovery of needed datasets is supported by Publication & Discovery mechanisms. | informative | `Blueprint_CEEDS_v3.0.txt:2354-2355` |
| `CEEDS-IMP-105` | BUC#5 Scenario 4 — Vocabulary Hub components ensure the semantic alignment of grid topologies and asset specifications. | informative | `Blueprint_CEEDS_v3.0.txt:2355-2356` |
| `CEEDS-IMP-106` | BUC#5 Scenario 4 — access to grid planning data is governed by Access & Usage Policies. | informative | `Blueprint_CEEDS_v3.0.txt:2356-2357` |
| `CEEDS-IMP-107` | BUC#5 Scenario 4 — Identity Management ensures the right actors are granted access based on role and function. | informative | `Blueprint_CEEDS_v3.0.txt:2362` |
| `CEEDS-IMP-108` | BUC#5 Scenario 4 — the process is tracked using Logging and Provenance & Traceability components, ensuring transparency and the ability to audit planning decisions. | informative | `Blueprint_CEEDS_v3.0.txt:2363-2365` |
| `CEEDS-IMP-109` | Data value creation is pursued in a trustworthy data space implementation according to three aspects: (i) the publication and discovery of data and services, (ii) the value-added mechanisms, and (iii) the business mechanisms of the compensations. | informative | `Blueprint_CEEDS_v3.0.txt:2371-2374` |
| `CEEDS-IMP-110` | The publication and discovery of data and services is pursued with data cataloguing, implementing dedicated marketplaces. | informative | `Blueprint_CEEDS_v3.0.txt:2376-2377` |
| `CEEDS-IMP-111` | The Gaia-X specifications constitute a valid reference for the implementation, specifically the so-called "marketplace federator" (or "federator"). | recommended | `Blueprint_CEEDS_v3.0.txt:2377-2380` |
| `CEEDS-IMP-112` | A marketplace federator is an entity dealing with managing a set of marketplace functionalities (e.g., inviting administrators, approving the registration of users, accepting offering descriptions uploaded by users, and accepting the deletion of offerings). | informative | `Blueprint_CEEDS_v3.0.txt:2379-2381` |
| `CEEDS-IMP-113` | The federated catalogue can sync with multiple provider catalogues from any other data space, which eases interoperability. | may | `Blueprint_CEEDS_v3.0.txt:2381-2383` |
| `CEEDS-IMP-114` | Marketplace functionality includes data search. | informative | `Blueprint_CEEDS_v3.0.txt:2387-2389` |
| `CEEDS-IMP-115` | Marketplace functionality includes data request, with specifications regarding the desired duration of use for the dataset and the expected use of the dataset. | informative | `Blueprint_CEEDS_v3.0.txt:2387-2389` |
| `CEEDS-IMP-116` | Marketplace functionality includes data contracting. | informative | `Blueprint_CEEDS_v3.0.txt:2387-2389` |
| `CEEDS-IMP-117` | Marketplace functionality includes the data contracting payment. | informative | `Blueprint_CEEDS_v3.0.txt:2387-2389` |
| `CEEDS-IMP-118` | The data contracting is based on a draft contract that includes predefined terms. | informative | `Blueprint_CEEDS_v3.0.txt:2389-2392` |
| `CEEDS-IMP-119` | The draft contract includes free-text terms, to allow the data providers to include their own terms. | informative | `Blueprint_CEEDS_v3.0.txt:2389-2392` |
| `CEEDS-IMP-120` | The draft contract includes reimbursement details — either the monetary cost or the profile of the dataset expected to be exchanged in a bartering transaction. | informative | `Blueprint_CEEDS_v3.0.txt:2389-2392` |
| `CEEDS-IMP-121` | Multiple projects opt for the centralized configuration of both the catalogue and the data exploration services, with a strong focus on the human- and machine-readability of look-up mechanisms and result formats. | informative | `Blueprint_CEEDS_v3.0.txt:2394-2396` |
| `CEEDS-IMP-122` | The syntactic and semantic verification of any submitted self-description against predefined schemas (aligned with the released GAIA-X schemas) can be performed using SHACL checks. | may | `Blueprint_CEEDS_v3.0.txt:2400-2403` |
| `CEEDS-IMP-123` | Security measures include the cryptographic verification of DIDs and VC/VPs. | informative | `Blueprint_CEEDS_v3.0.txt:2403` |
| `CEEDS-IMP-124` | Clear incentives for data sharing need to be established. | should | `Blueprint_CEEDS_v3.0.txt:2424-2426` |
| `CEEDS-IMP-125` | Data privacy is to be ensured as a complement for plain data exchange. | should | `Blueprint_CEEDS_v3.0.txt:2424-2426` |
| `CEEDS-IMP-126` | The transaction schemes underlying the compensation mechanisms will be regulated by formalized data contract templates. | informative | `Blueprint_CEEDS_v3.0.txt:2434-2436` |
| `CEEDS-IMP-127` | Those transaction schemes enable secure and trusted data asset sharing, trading and bartering. | informative | `Blueprint_CEEDS_v3.0.txt:2434-2436` |
| `CEEDS-IMP-128` | Those transaction schemes allow energy data value chain stakeholders to efficiently search for data assets of interest. | informative | `Blueprint_CEEDS_v3.0.txt:2436-2438` |
| `CEEDS-IMP-129` | Those transaction schemes provide stakeholders with intelligent recommendations for relevant data assets or data assets' providers. | informative | `Blueprint_CEEDS_v3.0.txt:2436-2438` |
| `CEEDS-IMP-130` | Compensation approach "Data by tokens" — access to assets (data, apps, services) is granted based on payment using a cryptographic token (specific for each data space). | informative | `Blueprint_CEEDS_v3.0.txt:2440-2443` |
| `CEEDS-IMP-131` | Compensation approach "Data by data" — access to assets is granted according to intrinsic value of data (through the barter exchange and incentives module), allowing a data set to be exchanged for another data set with equivalent value. | informative | `Blueprint_CEEDS_v3.0.txt:2445-2447` |
| `CEEDS-IMP-132` | Compensation approach "Data by currency" (limited to ENERSHARE) — access to assets is granted based on payment on FIAT currency, which can be handled through the marketplace. | informative | `Blueprint_CEEDS_v3.0.txt:2449-2451` |
| `CEEDS-IMP-133` | The marketplace can generate revenues charging a small percentage as a transaction fee for each transaction. | may | `Blueprint_CEEDS_v3.0.txt:2457-2458` |
| `CEEDS-IMP-134` | As the platform also accommodates auctions, which do not involve token transactions, a fee is applied for the participation in it. | informative | `Blueprint_CEEDS_v3.0.txt:2457-2459` |
| `CEEDS-IMP-135` | To incentivize platform usage, a strategy could be to offer free access to auctions for a user's initial participation and then a fixed subscription cost. | may | `Blueprint_CEEDS_v3.0.txt:2459-2460` |

## Open questions

Ambiguities, contradictions and gaps found in chapter 5. These are reported, not resolved.

- **Table 9 contradicts the EDDIE narrative on Access & Usage Policy.** Table 9 leaves the EDDIE / Access & Usage Policy cell blank, which by the source's own stated convention (`Blueprint_CEEDS_v3.0.txt:1803-1805`) means no implementation exists in that project; the narrative at `Blueprint_CEEDS_v3.0.txt:1905-1909` describes a TRL9 EDDIE implementation based on the EDDIE Data Needs definition language, GDPR and the Data Governance Act.
- **Table 9 contradicts the Data Cellar narrative on Logging.** Table 9 records "Eclipse Dataspace Components system monitoring interface" for DataCellar Logging (`Blueprint_CEEDS_v3.0.txt:1829-1834`), while the narrative states "Logging in Data Cellar lacks a unified implementation … making it non-applicable (N/A) in terms of maturity and standards compliance" (`Blueprint_CEEDS_v3.0.txt:1968-1969`).
- **Preconditions carry an explicit modal, postconditions do not.** BUC#4 Scenario 1 and Scenario 2 state "the following preconditions must be met" / "must be met to fulfil" but state postconditions in the indicative ("the following postconditions are achieved", "would be achieved"). Chapter 5 gives no rule for whether a postcondition is a guarantee or an expectation. This page records postconditions as `must`; a reader who requires strict modal fidelity should treat `CEEDS-IMP-74` to `CEEDS-IMP-76`, `CEEDS-IMP-78` and `CEEDS-IMP-79` as unmodalised.
- **Precondition phrasing is inconsistent across BUCs.** BUC#1 Scenario 1, BUC#3 Scenario 1, BUC#5 Scenario 1 and BUC#5 Scenario 3 use "must"; BUC#1 Scenario 2 and BUC#3 Scenario 5 use "requires"; BUC#3 Scenario 3 and BUC#5 Scenario 4 use only "begins with the availability of" / "the preconditions for execution include the availability of". It is not stated whether these are intended to differ in force.
- **Building block naming is not stable within the chapter.** The same building block appears as *Contract Framework* (Table 9, BUC#1 Scenarios 2–3), *Contracting Framework* (§5.2 narratives, BUC#2, BUC#4) and *Contract Framework* / *Contracting Framework* interchangeably; *Access & Usage Policy* (Table 9, BUC#2, BUC#3) versus *Access & Usage Policies* (§5.2 narratives, BUC#5); *Connector* / *Data Space Connector* / *Dataspace connector*; *Vocabulary* (BUC#3 Scenario 4, BUC#5 Scenario 1) versus *Vocabulary Hub* elsewhere.
- **Project naming is not stable.** Table 9 uses "Synergies", "DataCellar", "Omega-X", "Enershare"; the narratives use "SYNERGIES", "Data Cellar" / "DATA CELLAR", "OMEGA-X", "Enershare" / "ENERSHARE". "sovity" is lower case in the narrative and "Sovity" in Table 9. "eMSP" and "EMSP" are both used within BUC#4.
- **Section 5.1 is titled "Energy Dataspace Cluster Projects"** while the abbreviation EDSCP is expanded elsewhere in the document as "Energy Data Space Cluster Projects" (`Blueprint_CEEDS_v3.0.txt:224-225`, `Blueprint_CEEDS_v3.0.txt:3393`). The heading spelling has been preserved.
- **The chapter's stated purpose is only partly delivered.** The introduction promises "a concise overview of the ongoing projects associated with BUCs" (`Blueprint_CEEDS_v3.0.txt:1686-1687`), but §5.1 does not associate any project with any BUC; the project-to-BUC mapping is not given anywhere in chapter 5.
- **BUC#3 Scenario 5 is truncated relative to its siblings.** It ends at "Logging tracks the sequence of data access and analyses" with no postcondition and no Provenance & Traceability step, unlike Scenarios 1–4 (`Blueprint_CEEDS_v3.0.txt:2231-2244`).
- **BUC#2 presents a single unnamed scenario**, whereas the other BUCs present numbered and (mostly) titled scenarios. BUC#3 Scenarios 2 and 3 also carry no titles in §5.3.
- **Source typography and grammar defects preserved verbatim above:** "Identity Management)" with an unmatched closing parenthesis (`Blueprint_CEEDS_v3.0.txt:2118`); "Publication & Discoveryto" with a missing space (`Blueprint_CEEDS_v3.0.txt:2294`); "For operational events identification in the short and mid-term is triggered by…" (`Blueprint_CEEDS_v3.0.txt:2232`); "to be exchange for another data set" (`Blueprint_CEEDS_v3.0.txt:2446-2447`); "non-reputability" where "non-repudiation"/"non-repudiability" appears to be meant (`Blueprint_CEEDS_v3.0.txt:1878-1879`); "OpenID Connector for Verifiable Credentials (OID4VC)" where the specification family is normally "OpenID for Verifiable Credentials" (`Blueprint_CEEDS_v3.0.txt:1965-1966`) — the source spelling has been kept.
- **"Data Space Protocol", "Dataspace Protocol" and "IDS Dataspace Protocol" are used for what appears to be the same specification** across the Data Cellar, OMEGA-X and Enershare narratives, with no version given anywhere in chapter 5. No version is given for IDS RAM in the SYNERGIES narrative either, while ENERSHARE cites "IDSA RAM v4" and "IDS-RAM v4".
- **TRL claims are unsourced and use several formats** — "TRL7+", "TRL 8-9", "TRL5", "at TRL6 … expected to reach TRL7", "N/A". Chapter 5 does not state the assessment method or the assessment date, and Enershare's "full DSP integration planned for 2025" is a forward-looking statement in a document dated September 2025.
- **§5.4 states compensation design in the future tense** ("transaction schemes that will be regulated by formalized data contract templates", `Blueprint_CEEDS_v3.0.txt:2434-2436`) without a modal, so it cannot be read as either an existing property or an obligation. Recorded as `informative`.
- **Chapter 5 gives no mapping between the eight "CEEDS Building Blocks" of Table 9 and the CEEDS architecture presented earlier in the document.** The chapter introduces the eight names without cross-reference.
- **§5.3 refers the reader to "the corresponding sequence diagrams (in section 3)"** (`Blueprint_CEEDS_v3.0.txt:2062-2063`) but does not identify which figure corresponds to which scenario.
