# Data Exchange

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Data Exchange
> **Category** · Data Interoperability

The objective of this building block is to enable the actual sharing of data between a data provider and data user. Just as with data models, a data space can make strategic choices about how protocols for data exchange are implemented and managed — the outcome of which needs to be documented in the rulebook. This enables participants to select and reuse a pre-defined set of protocols for data exchange with clear interaction patterns and reliability measures.

## Scope and objectives

The scope is the actual sharing of data between a data provider and a data user.

A data space can make strategic choices about how protocols for data exchange are implemented and managed. The outcome of those choices needs to be documented in the rulebook, which enables participants to select and reuse a pre-defined set of protocols for data exchange with clear interaction patterns and reliability measures.

The source states that this building block supports compliance with [article 33, point c, of the EU Data Act](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202302854), which requires data providers to describe the technical means to access the data, such as application programming interfaces, their terms of use and quality of service.

The source draws two structural distinctions that scope the building block:

- **Control plane vs. data plane.** When implementing the capability, a difference shall be made between a control plane and a data plane. Whereas the data plane is often domain-specific (implementing a domain specific Data exchange protocol), the control plane is generic. The data plane and control plane shall work together, to ensure any access and usage policies are enforced. Exchanges between control planes of different parties shall use the Dataspace protocol as a standard.
- **Protocol layering** (from the best practice below). The data space protocol manages contract negotiation and the coordination of data sharing; the data exchange protocol defines the rules and structure for the actual data transfer on the data plane; the transmission protocol is the transport mechanism that the data exchange protocol uses to send and receive data.

On implementation, the source states that the Data exchange protocol is implemented on the data plane level of the Participant agent, and that the data plane needs to work closely together with the control plane of the Participant agent for facilitating generic data space interactions such as the exchange of catalogue data.

## Capabilities

The source is explicit that this building block does **not** impose a common protocol:

> It is not mandatory to define a common (domain) data exchange protocol in a dataspace, as part of the rulebook. Every participant can specify their own technical means to access their data, as far as this is not limited by the dataspace rulebook to (a) certain data exchange protocol(s).

The capability list below is introduced by the source as capabilities that *"can contribute to achieving technical interoperability"* — it is not framed as a mandatory set. Statements *within* individual capabilities do carry normative force, and are preserved as such.

- **Protocol selection** — the ability to select which data exchange protocols the data space adopts. This involves specifying all necessary technical details, including:
    - *Interaction Patterns*: defining whether data is actively sent by the provider (push) or retrieved by the consumer (pull), and whether it concerns a one-time dataset (finite) or a continuous flow of data (non-finite, such as streaming).
    - *Transmission protocols*: a choice for the associated transmission method needs to be made (e.g. HTTP, Event Streams (like MQTT), Apache AVRO, Thrift, Protocol Buffers, etc). These transmission methods are generic and usually based on industry standards. Depending on the nature transmission, a suitable method can be selected.
    - *Data payloads*: specify how the data schema (from the Data Models building block) is structured within the protocol to ensure the data is correctly interpreted upon arrival.
- **Protocol governance** — the ability to manage the lifecycle of the supported data exchange protocols. This involves processes for versioning, introducing new protocols, and phasing out outdated ones.
- **Protocol publication and discovery** — the ability to make the specifications of protocols easily discoverable for all data space participants. Each data product in the catalogue should clearly indicate which exchange protocol(s) can be used to access it, including links to the relevant technical documentation (e.g., an OpenAPI specification) and endpoints.
- **Reliable data transfer** — the ability to facilitate the actual data transfer in a secure manner. This includes the transfer process in a participant agent, which go from initiation and monitoring to completion or termination.
- **Cross data space exchange** — the ability to align on data exchange with participants from other data spaces. This requires mechanisms to discover each other protocols and align on common protocols or to translate between the protocols used in different data spaces.

## Co-creation questions

The source frames these as guidance, not requirements: *"There is no 'one-size-fits-all' solution. A data space must base its choice of data exchange protocols on the use cases of its participants, and it is very likely that a data space will need to support multiple protocols to facilitate different needs. These questions are created to guide a data space in establishing the necessary agreements for using a data exchange protocol."*

**What are the data space specific requirements for standardized data exchange protocols?** — This question focuses on the specific needs of the data space before considering any technology.

- *Evaluate the scope of the data exchange*: evaluate which data products will be exchanged by considering the nature of the data (e.g., small, frequent messages, large files, or continuous streams) and the purpose of the exchange, such as one-time reporting, real-time monitoring, or ad-hoc querying.
- *Define the required interaction patterns*: define the required interaction patterns by determining whether participants should retrieve data on demand (a pull-based model) or if data should be proactively sent as it becomes available (a push-based model).
- *Is a common data exchange protocol needed*: decide whether it is needed to define a single (set of) data exchange protocol(s) to be used in the dataspace or whether this is to be defined by each individual participant.

**Which protocols meet these requirements?** — If it is decided to limit the data exchange protocols, or when selecting a data exchange protocol as a participant in a dataspace several choices are available:

- *Reuse of existing protocols*: given the requirements, are there implementations of the protocols above that can be reused? This is always the preferred approach to maximize interoperability.
- *Specification of a new protocol*: If an existing protocols does not fully meet the needs, a custom specification (e.g., API) must be created. Note that a new protocol can be an extension of an existing (common) protocol.

**How will the data space manage the agreed data exchange protocols?** — Technical agreements need to be governed. This starts by publishing the data exchange protocol (such as an OpenAPI specification) in a vocabulary service. Furthermore, a strategy for maintenance and updates of the protocol needs to be defined (version management).

## Standards and protocols

Names, versions and identifiers below are reproduced exactly as the source writes them. "referenced" means the source names it as an example, not as an obligation.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| Dataspace Protocol (<https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol>) | no version stated by the source | Common set of rules used by participant agents to communicate about discovering data, negotiating contracts, and initiating the transfer itself; the source elsewhere writes it as "Dataspace protocol" and requires it for exchanges between control planes of different parties | recommended |
| EU Data Act, article 33, point c | Regulation as published at <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202302854> | Requires data providers to describe the technical means to access the data, such as application programming interfaces, their terms of use and quality of service; the building block supports compliance with it | required (legal instrument cited by the source) |
| HTTP | no version stated | Transmission protocol; example of an associated transmission method; carries the requests and responses for a RESTful API | referenced |
| Event Streams (like MQTT) | no version stated | Transmission method example; MQTT is separately listed as "designed for the (IoT), sensor networks, and situations with low bandwidth" | referenced |
| Apache AVRO | no version stated | Transmission method example | referenced |
| Thrift | no version stated | Transmission method example | referenced |
| Protocol Buffers | no version stated | Transmission method example | referenced |
| OpenAPI specification / Open API Specifications (OAS) | no version stated | Example of a clear machine-readable description of a protocol's capabilities and endpoints; example of what is published in a vocabulary service; OAS is listed for Representational State Transfer (RESTful), Hypertext Transfer Protocol (HTTP) APIs | referenced |
| RESTful API's | no version stated | "the de-facto standard for web APIs. Suitable for requesting, creating, and modifying structured data"; example of a protocol style | referenced |
| Webhooks | no version stated | "event-driven (push) mechanism for simple and real-time notifications, often used to extend a REST API with push capabilities" | referenced |
| GraphQL | no version stated | "for complex data needs and mobile applications" | referenced |
| WebSockets | no version stated | "for real-time communication, such as in live dashboards, chat applications, or online gaming" | referenced |
| SOAP | no version stated | "used in enterprise environments with high transactional requirements" | referenced |
| NGSI-LD API standard | published under the European Telecommunications Standards Institute Context Information Management Industry Specifications Group, ETSI CIM ISG ("The latest specifications"); an evolution of Next Generation Service Interfaces version 2 (NGSI-v2) | "provides a simple yet powerful RESTful API for accessing context/digital twin data"; also cited as a protocol style and as an example query language ("NGSI-LD querying"); "https REST is used in an API like NGSI-LD" | referenced |
| NGSI-v2 (Next Generation Service Interfaces version 2) | version 2 | Predecessor of NGSI-LD | referenced |
| NGSI | no version stated | Example of a Consensus Protocol — a 'de facto' standard data exchange protocol in a domain (smart cities) | referenced |
| Linked Data Event Streams (LDES) | no version stated; "by Semantic Interoperability Community Europe, SEMIC" | "enables the publication and consumption of evolving datasets as streams while maintaining Linked Data principles"; example for real-time and continuous data flows | referenced |
| FAIR principles (Findable, Accessible, Interoperable, Reusable) — <https://www.go-fair.org/fair-principles/> | no version stated | Must be applied not just to data, but to the operational specifications of the data spaces themselves, to create synergies between data spaces | required |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Sources cite the upstream document and its section number: `data-exchange.md` is the Data Exchange building block page; `best-practice-defining-data-exchange-protocols.md` is the best practice sub-page rendered below.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-DEX-01` | The outcome of a data space's strategic choices about how protocols for data exchange are implemented and managed needs to be documented in the rulebook. | must | `data-exchange.md` §1 |
| `DSSC-DEX-02` | A data provider must describe the technical means to access the data, such as application programming interfaces, their terms of use and quality of service. | must | `data-exchange.md` §1 (EU Data Act, article 33, point c) |
| `DSSC-DEX-03` | Defining a common (domain) data exchange protocol in a dataspace, as part of the rulebook, is not mandatory. | may | `data-exchange.md` §2 |
| `DSSC-DEX-04` | Every participant can specify their own technical means to access their data, as far as this is not limited by the dataspace rulebook to (a) certain data exchange protocol(s). | may | `data-exchange.md` §2 |
| `DSSC-DEX-05` | A data space can provide the ability to select which data exchange protocols it adopts (Protocol selection). | may | `data-exchange.md` §2 |
| `DSSC-DEX-06` | When selecting data exchange protocols, the interaction pattern must define whether data is actively sent by the provider (push) or retrieved by the consumer (pull). | must | `data-exchange.md` §2 |
| `DSSC-DEX-07` | When selecting data exchange protocols, the interaction pattern must define whether the exchange concerns a one-time dataset (finite) or a continuous flow of data (non-finite, such as streaming). | must | `data-exchange.md` §2 |
| `DSSC-DEX-08` | A choice for the associated transmission method needs to be made (e.g. HTTP, Event Streams (like MQTT), Apache AVRO, Thrift, Protocol Buffers, etc). | must | `data-exchange.md` §2 |
| `DSSC-DEX-09` | The data payload specification must state how the data schema (from the Data Models building block) is structured within the protocol, to ensure the data is correctly interpreted upon arrival. | must | `data-exchange.md` §2 |
| `DSSC-DEX-10` | A data space can provide the ability to manage the lifecycle of the supported data exchange protocols, with processes for versioning, introducing new protocols, and phasing out outdated ones (Protocol governance). | may | `data-exchange.md` §2 |
| `DSSC-DEX-11` | A data space can provide the ability to make the specifications of protocols easily discoverable for all data space participants (Protocol publication and discovery). | may | `data-exchange.md` §2 |
| `DSSC-DEX-12` | Each data product in the catalogue should clearly indicate which exchange protocol(s) can be used to access it. | should | `data-exchange.md` §2 |
| `DSSC-DEX-13` | Each data product in the catalogue should include links to the relevant technical documentation (e.g., an OpenAPI specification) and endpoints. | should | `data-exchange.md` §2 |
| `DSSC-DEX-14` | A data space can provide the ability to facilitate the actual data transfer in a secure manner, including the transfer process in a participant agent from initiation and monitoring to completion or termination (Reliable data transfer). | may | `data-exchange.md` §2 |
| `DSSC-DEX-15` | A data space can provide the ability to align on data exchange with participants from other data spaces, with mechanisms to discover each other protocols and align on common protocols or to translate between the protocols used in different data spaces (Cross data space exchange). | may | `data-exchange.md` §2 |
| `DSSC-DEX-16` | A dataspace can freely choose which Data exchange protocol(s) is/are to be used. | may | `data-exchange.md` §4 |
| `DSSC-DEX-17` | Through the rulebook, a dataspace governance authority can limit the allowed Data exchange protocol(s) in a particular dataspace. | may | `data-exchange.md` §4 |
| `DSSC-DEX-18` | When implementing the capability, a difference shall be made between a control plane and a data plane. | must | `data-exchange.md` §4 |
| `DSSC-DEX-19` | The data plane and control plane shall work together, to ensure any access and usage policies are enforced. | must | `data-exchange.md` §4 |
| `DSSC-DEX-20` | Exchanges between control planes of different parties shall use the Dataspace protocol as a standard. | must | `data-exchange.md` §4 |
| `DSSC-DEX-21` | The Data exchange protocol is implemented on the data plane level of the Participant agent. | informative | `data-exchange.md` §5 |
| `DSSC-DEX-22` | The data plane needs to work closely together with the control plane of the Participant agent for facilitating generic data space interactions such as the exchange of catalogue data. | must | `data-exchange.md` §5 |
| `DSSC-DEX-23` | The DSSC recommends the usage of the Dataspace Protocol for communicating about discovering data, negotiating contracts, and initiating the transfer itself. | recommended | `best-practice-defining-data-exchange-protocols.md` §1 |
| `DSSC-DEX-24` | The Dataspace Protocol only initiates and coordinates the data transaction; it does not prescribe how the actual transfer of the data is done, so a separate data exchange protocol is required. | informative | `best-practice-defining-data-exchange-protocols.md` §1 |
| `DSSC-DEX-25` | A data space must establish clear agreements on which data exchange protocols are used. | must | `best-practice-defining-data-exchange-protocols.md` §1, §2 |
| `DSSC-DEX-26` | The agreements about the data exchange protocols to be used must be documented in the data space rulebook. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-27` | A data space is to prioritise the reuse of existing and open standards ("a key principle"). | should | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-28` | A data space should first evaluate if a mature and standardized protocol (e.g., an API specification) already exists for its domain. | should | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-29` | If no suitable specification can be reused, the data space must define its own. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-30` | The protocol should suit the purpose of data sharing or the purpose of allowing data access. | should | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-31` | The protocol must be capable of carrying the payload as defined by the data schema from the data models building block. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-32` | The protocol must operate within the rules established on the control plane, such as those for identification, authentication, and access policies. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-33` | The data space governance authority is responsible for maintaining a precise inventory of the technical specifications for the different protocols used, including their versions. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-34` | The inventory of protocol specifications must be made available to all participants via the vocabulary or catalogue services. | must | `best-practice-defining-data-exchange-protocols.md` §2 |
| `DSSC-DEX-35` | The protocol's capabilities should be divided into what is mandatory for all participants and what is recommended. | should | `best-practice-defining-data-exchange-protocols.md` §3 |
| `DSSC-DEX-36` | The exchange must only start after the Control Plane has handled the necessary identification and authorization. | must | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-37` | The protocol must be able to maintain a consistent quality of service, for example, by managing what happens when a connection is lost. | must | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-38` | The protocol must provide a clear machine-readable description of its capabilities and endpoints (e.g., via an OpenAPI specification), so that participants can easily understand how to interact with the data. | must | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-39` | Once approved, the protocol description for the data exchange has to be published [in] the Dataspace rulebook. | must | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-40` | The specification itself should be published with the data itself in the services of the publication and discovery building block. | should | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-41` | The specification should be kept up to date. | should | `best-practice-defining-data-exchange-protocols.md` §3.1 |
| `DSSC-DEX-42` | For complex datasets, the protocol should allow consumers to request specific subsets of data. | should | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-43` | Querying may involve a specific query language (i.e. NGSI-LD querying) capable of handling complex requests independent of the data structure. | may | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-44` | The querying mechanism might also need to integrate with the Control Plane to provide different results based on the user's access rights. | may | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-45` | Additional capabilities like geoquerying and querying for time periods are also recommended. | recommended | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-46` | The selection of data exchange protocols should be based on the specific usage scenario. | should | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-47` | For scenarios involving the retrieval of extensive datasets, such as historical data or historical archives, dedicated data retrieval endpoints should be available. | should | `best-practice-defining-data-exchange-protocols.md` §3.2 (stated twice: "Data streaming endpoints" and "Bulk data retrieval") |
| `DSSC-DEX-48` | The transmission of large volumes of data may necessitate specialized mechanisms for data integrity verification, error handling, and efficient transport to ensure reliability and consistency. | may | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-49` | For event-driven scenarios, the protocol should support mechanisms for enabling alerts or notifications when data sources are updated or modified, so that consumers receive proactive updates without the need for continuous polling. | should | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-50` | In case of federation scenarios, the data spaces' specific protocols for data exchange needs to be available. | must | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-51` | The governance of the data spaces will define what are the accepted protocols for the data exchange between the federated data spaces and how to make it available to the different participants. | must | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-52` | A list of accepted data exchange protocols and their versions will be available at the start of the technical federation of data space, independently if this is created by a direct connection or by means of an intermediary entity. | must | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-53` | Eventually a specific data model for the data exchange protocols could be created to speed up the negotiation of the data transmission between data spaces. | may | `best-practice-defining-data-exchange-protocols.md` §3.2 |
| `DSSC-DEX-54` | Where a data space defines its own data exchange protocol, the resulting protocol must be documented in the rulebook. | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-55` | The protocol must specify how requests are handled, functional and technical (synchronous versus asynchronous handling). | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-56` | The specification must define a consistent use of status codes (when using HTTP) to communicate the outcome of a request, including clear definitions for success codes (2xx), client errors (4xx), and server errors (5xx). | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-57` | The protocol must specify how participants are authenticated, linking back to the identity mechanisms managed by the Control Plane. | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-58` | The protocol must specify what participants are authorized to do, linking back to the policies managed by the Control Plane. | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-59` | A strategy for versioning the protocol for future updates without breaking the implementations of existing participants is a key aspect to define. | may | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-60` | A data exchange protocol requires a governance process to ensure its up to date. | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-61` | The governance process for a data exchange protocol must be documented in the rulebook. | must | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-62` | The governance process should describe the approval process for changes. | should | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-63` | The governance process should describe how the specifications are published so that all participants can find and use them. | should | `best-practice-defining-data-exchange-protocols.md` §4 |
| `DSSC-DEX-64` | To create synergies and enable a network of interconnected ecosystems, data spaces must agree on the data exchange protocols they will use. | must | `best-practice-defining-data-exchange-protocols.md` §5 |
| `DSSC-DEX-65` | The FAIR (Findable, Accessible, Interoperable, Reusable) principles must be applied not just to data, but to the operational specifications of the data spaces themselves. | must | `best-practice-defining-data-exchange-protocols.md` §5 |
| `DSSC-DEX-66` | The first step towards cross-data space collaboration is for data spaces to publish their supported protocols in a standardized and findable manner. | informative | `best-practice-defining-data-exchange-protocols.md` §5 |

## Explainers and best practices

The source attaches one sub-page to this building block, rendered in full below. The building block page also points to a separate explainer, *how a data plane and control plane work together*, which lives outside this building block.

## Best practice: Defining Data exchange protocols

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Data Exchange › Best practice: Defining Data exchange protocols

The building block page introduces this sub-page as follows: *"A dataspace can freely choose which Data exchange protocol(s) is/are to be used. As a separate explainer, we provide a best practice for choosing and defining data exchange protocols."*

### 1. Data Exchange and the Data Spaces Protocol

In a data space, the transfer of data occurs between two software services, named the participant agents. To communicate about discovering data, negotiating contracts, and initiating the transfer itself, these agents use a common set of rules. The DSSC recommends the usage of the [Dataspace Protocol](https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol), which is a set of specifications designed to facilitate interoperable data sharing.

However, the Dataspace Protocol only initiates and coordinates the data transaction; it does not prescribe how the actual transfer of the data is done. For that, a separate protocol is required. This is the **data exchange protocol**, which operates on the data plane. It defines the specific "language" that applications use to send or receive data. In practice, a data exchange protocol is built on top of a **transmission protocol**. For example, a data space might specify a RESTful API, which defines the rules and structure of the exchange, while HTTP is used as the transmission protocol for the actual transport of the messages.

It is important to distinguish between these protocol layers:

- The data space protocol manages contract negotiation and the coordination of data sharing.
- The data exchange protocol defines the rules and structure for the actual data transfer on the data plane. For example, a RESTful API specification that allows a booking website to query real-time flight availability.
- The transmission protocol is the transport mechanism that the data exchange protocol uses to send and receive data. For example, HTTP is the transmission protocol that carries the requests and responses for the RESTful API.

While the data space protocol provides a generic framework for interaction between two participants agents, the choice of data exchange protocol can be domain-specific and tailored to a use case. Therefore, a data space must establish clear agreements on which data exchange protocols are used.

### 2. Choosing a protocol

To ensure that all participants can communicate technically, a data space must establish clear agreements about the data exchange protocols to be used. These agreements must be documented in the data space rulebook.

A key principle is to **prioritise the reuse of existing and open standards.** A data space should first evaluate if a mature and standardized protocol (e.g., an API specification) already exists for its domain. If one does, adopting it is the most efficient path to interoperability.

If no suitable specification can be reused, the data space must define its own. This does not mean inventing a new web technology, but it means creating, for example, a specific API specification that is built upon a transmission protocol like HTTP. Examples of transmission protocols can be found in the further reading section (i.e. https REST is used in an API like NGSI-LD).

A suitable protocol must meet the following criteria:

- The protocol should suit the purpose of data sharing or the purpose of allowing data access.
- It must be linked to the relevant data models. The protocol must be capable of carrying the payload as defined by the data schema from the data models building block.
- It must be linked to the control plane. The protocol must operate within the rules established on the control plane, such as those for identification, authentication, and access policies.

The data space governance authority is responsible for maintaining a precise inventory of the technical specifications for the different protocols used, including their versions. This inventory must be made available to all participants via the vocabulary or catalogue services.

Examples of common protocols:

- **RESTful API's**: the de-facto standard for web APIs. Suitable for requesting, creating, and modifying structured data.
- **Webhooks**: event-driven (push) mechanism for simple and real-time notifications, often used to extend a REST API with push capabilities.
- **GraphQL**: for complex data needs and mobile applications.
- **MQTT**: designed for the (IoT), sensor networks, and situations with low bandwidth.
- **WebSockets**: for real-time communication, such as in live dashboards, chat applications, or online gaming.
- **SOAP**: used in enterprise environments with high transactional requirements.

### 3. Functional Specifications

The decision of which data exchange protocol to adopt or develop depends on the specific requirements needed to implement the data space's use cases. Such exchanges may occur in any of the following scenarios:

- A gets access to data owned by B.
- B gets access to data owned by A.
- Both participants get mutual access to their data.

To support these scenarios, the protocol's capabilities should be divided into what is mandatory for all participants and what is recommended.

#### 3.1. Mandatory functionalities

Any protocol selected by the data space must support the following:

- **Efficient transmission of data**: data exchange starts after an event has taken place or upon a user's request. The exchange must only start after the Control Plane has handled the necessary identification and authorization. Furthermore, the protocol must be able to maintain a consistent quality of service, for example, by managing what happens when a connection is lost.
- **Published list of capabilities**: The protocol must provide a clear machine-readable description of its capabilities and endpoints (e.g., via an OpenAPI specification) so that participants can easily understand how to interact with the data. Once approved, the protocol description for the data exchange has to be published the Dataspace rulebook [*sic* — the source omits a preposition]. The specification itself should be published with the data itself in the services of the publication and discovery building block and kept up to date.

#### 3.2. Recommended functionalities

Depending on the needs, support for the following functionalities should be considered. The following list is not exhaustive but a general approach, and specific needs could be necessary in some domains.

- **Querying capabilities** — For complex datasets, the protocol should allow consumers to request specific subsets of data. This may involve a specific query language (i.e. NGSI-LD querying) capable of handling complex requests independent of the data structure. The querying mechanism might also need to integrate with the Control Plane to provide different results based on the user's access rights. Additional capabilities like geoquerying and querying for time periods are also recommended.
- **Data streaming endpoints** — The selection of data exchange protocols should be based on the specific usage scenario. For instance, streaming data requires different protocols compared to querying structured records in a database or retrieving large datasets. For real-time and continuous data flows, an example is the Linked Data Event Streams (LDES) protocol, which enables the publication and consumption of evolving datasets as streams while maintaining Linked Data principles. For scenarios involving the retrieval of extensive datasets, such as historical data, dedicated data retrieval endpoints should be available. The transmission of large volumes of data may necessitate specialized mechanisms for data integrity verification, error handling, and efficient transport to ensure reliability and consistency.
- **Bulk data retrieval** — For scenarios involving the retrieval of extensive datasets, such as historical archives, the protocol should offer dedicated data retrieval endpoints. The transmission of such large volumes may require specialized mechanisms for data integrity verification and error handling to ensure reliability.
- **Triggered exchange mechanisms** — For event-driven scenarios, the protocol should support mechanisms for enabling alerts or notifications when data sources are updated or modified. This allows consumers to receive proactive updates without the need for continuous polling.
- **Information retrieval in federation scenarios** — In case of federation scenarios, the data spaces' specific protocols for data exchange needs to be available. The governance of the data spaces will define what are the accepted protocols for the data exchange between the federated data spaces and how to make it available to the different participants. There will be a list of accepted data exchange protocols and their versions available at the start of the technical federation of data space independently if this is created by a direct connection or by means of an intermediary entity. Eventually a specific data model for the data exchange protocols could be created to speed up the negotiation of the data transmission between data spaces.

### 4. Defining your own data exchange protocol

While data spaces should prioritise the reuse of existing data exchange protocols, there are situations where no suitable protocol exists for a specific use case. In such cases, the data space must define its own. This process involves several design decisions, where the resulting protocol must be documented in the rulebook.

The process begins with most important choices about the architecture of the protocol. This includes selecting a protocol style, such as REST or NGSI-LD, and defining the interaction pattern:

- **Pull method**: a data consumer actively requests data from a provider. This is the most common pattern, ideal for querying specific, finite datasets.
- **Push method**: a data provider proactively sends data to subscribers as it becomes available. This pattern is essential for continuous, real-time data streams.

Once the overall pattern is chosen, the specification must detail the technical rules of the interaction to ensure clarity and predictability for all developers. Key aspects to define can include:

- **Synchronous vs. asynchronous Handling**: the protocol must specify how requests are handled, functional and technical. For quick queries, a synchronous response where the client waits for the data is sufficient. For long-running processes, an asynchronous approach is necessary, where the server immediately confirms receipt and notifies the client later when the data is ready.
- **Error handling**: the same goes for error handling. The specification must define a consistent use of status codes (when using HTTP) to communicate the outcome of a request. This includes clear definitions for success codes (2xx), client errors (4xx), and server errors (5xx).
- **Authentication and authorization**: the protocol must specify how participants are authenticated and what they are authorized to do, linking back to the policies and identity mechanisms managed by the Control Plane.
- **Versioning**: a strategy for versioning the protocol for future updates without breaking the implementations of existing participants.
- More..

Defining the technical specification is only the first step. Just as with data models, a data exchange protocol requires a **governance process** to ensure its up to date. This governance process must be documented in the rulebook, and should describe the approval process for changes and how the specifications are published so that all participants can find and use them.

### 5. Synergies of data spaces

To create synergies and enable a network of interconnected ecosystems, data spaces must agree on the data exchange protocols they will use. This could involve adopting a common, shared protocol or one data space aligning with the protocol of another. To facilitate this, the [FAIR](https://www.go-fair.org/fair-principles/) principles (Findable, Accessible, Interoperable, Reusable) must be applied not just to data, but to the operational specifications of the data spaces themselves. Therefore, the first step is for data spaces to publish their supported protocols in a standardized and findable manner. This is the first in negotiation which protocols to use in cross-data space collaboration.

### 6. Examples

- Open API Specifications (OAS) for Representational State Transfer (RESTful), Hypertext Transfer Protocol (HTTP) APIs.
- The NGSI-LD API standard provides a simple yet powerful RESTful API for accessing context/digital twin data. NGSI-LD is an evolution of Next Generation Service Interfaces version 2 (NGSI-v2) that incorporates support for linked data and other powerful features. The latest specifications are published under the European Telecommunications Standards Institute Context Information Management Industry Specifications Group, ETSI CIM ISG.
- Linked Data Event Streams (LDES) by Semantic Interoperability Community Europe, SEMIC.
- A proposal for the data model in a data interchanges of assets in data spaces federation.

## Glossary

Reproduced from the building block page. Definitions are not requirements and carry no requirement IDs. Where the source runs an explanatory note into the definition cell, it is preserved and marked.

| Term | Definition |
|---|---|
| Consensus Protocol | The data exchange protocol that is globally accepted in a domain. *Explanatory Text*: In some domains the data exchange protocols are 'de facto' standards (e.g. NGSI for smart cities). |
| Federated data spaces | A data space that enables seamless data transactions between the participants of multiple data spaces based on agreed common rules, typically set in a governance framework. *Explanatory Text*: The definition of a federation of data spaces is evolving in the data space community. A federation of data spaces is a data space with its own governance framework, enabled by a set of shared services (federation and value creation) of the federated systems, and participant agent services that enable participants to join multiple data spaces with a single onboarding step. |
| Geoquerying | Query involving geographical boundaries. *Explanatory Text*: Data querying frequently needs to be restricted to a geographical area. |
| Transfer Process (TP) | A process that manages the lifecycle of data exchange between a provider and a consumer, involving, in example, states, as a minimum, REQUESTED, STARTED, COMPLETED, SUSPENDED, and TERMINATED. |
| Pull Transfer | A data transfer initiated by the consumer, where data is retrieved from the provider. |
| Push Transfer | A data transfer initiated by the provider, where data is sent to the consumer. |
| Non-Finite Data | Data that is defined by an infinite set or has no specified end, such as continuous streams. |
| Finite Data | Data that is defined by a finite set, such as a fixed dataset. |

## Tools implementing this building block

The source lists the following tools against this building block. They are illustrations of available implementations, not requirements; the "Service" column reproduces the service category the source assigns to each entry.

| Tool | Service |
|---|---|
| Fair Data Publisher | Data Plane |
| SEMIC SHACL Validator (Unified Validator) | Value-Creation Services |
| SEMIC XML Validator | Value-Creation Services |
| Interoperability Test Bed | Value-Creation Services |
| Ocean Enterprise Provider | Participant Agent Services |
| Nautilus Participant Agent | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| FIWARE Data Space Framework (FDF) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |
| Simpl-Open – Participant Agent | Participant Agent Services |
| Ocean Enterprise Catalogue and Aquarius Catalogue Cache | Catalogue |
| sovity Data Space Portal (DSPortal) | Catalogue |
| Simpl-Open - Catalogue | Catalogue |
| Data Space Builder | Value-Creation Services |

## Open questions

> **Ambiguous:** The normative force of the Dataspace Protocol is stated two different ways. The best practice sub-page (§1) says *"The DSSC recommends the usage of the Dataspace Protocol"*, while the building block page (§4) says *"Exchanges between control planes of different parties **shall** use the Dataspace protocol as a standard."* The source does not reconcile a recommendation with a "shall". Both are recorded (`DSSC-DEX-20`, `DSSC-DEX-23`).

> **Ambiguous:** The Dataspace Protocol is named without a version. The only anchor the source gives is a link to <https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol>. A conformance claim cannot be pinned to a specific specification version from this source alone.

> **Ambiguous:** The source spells the protocol three ways — "Dataspace Protocol" (best practice §1), "Dataspace protocol" (building block §4), "the data space protocol" and "the Data Spaces Protocol" (best practice §1 heading and body). It is not stated whether these denote the same specification; they are treated as the same throughout the source's prose but the naming is not normalised.

> **Ambiguous:** Best practice §4 introduces its bullet list with *"Key aspects to define **can** include"*, yet three of the four bullets are written with "must" (synchronous vs. asynchronous handling, error handling, authentication and authorization) and one with no modal at all (versioning). Whether these are mandatory or illustrative is unresolved; the per-bullet force has been recorded (`DSSC-DEX-55` to `DSSC-DEX-59`).

> **Ambiguous:** The list of key aspects in best practice §4 ends with the literal bullet "More..", so the source states the list is incomplete without saying what else belongs in it.

> **Contradiction / duplication:** Best practice §3.2 states the same requirement twice with different wording. Under "Data streaming endpoints": *"For scenarios involving the retrieval of extensive datasets, such as historical data, dedicated data retrieval endpoints **should be available**. The transmission of large volumes of data **may necessitate** specialized mechanisms for data integrity verification, error handling, and efficient transport."* Under "Bulk data retrieval": *"For scenarios involving the retrieval of extensive datasets, such as historical archives, the protocol **should offer** dedicated data retrieval endpoints. The transmission of such large volumes **may require** specialized mechanisms for data integrity verification and error handling."* The second omits "efficient transport". Recorded once each (`DSSC-DEX-47`, `DSSC-DEX-48`).

> **Gap:** Best practice §3.2, "Information retrieval in federation scenarios", is written in the future indicative ("The governance of the data spaces **will** define…", "There **will be** a list…") rather than with a modal. Whether these are obligations on a federation or a description of expected practice is not stated.

> **Gap:** Best practice §3.1 requires the protocol description to be published "the Dataspace rulebook" — a preposition is missing in the source, so it is not literally stated whether the description is published *in* or *with* the rulebook. `DSSC-DEX-39` marks the insertion.

> **Gap:** The building block page (§2) says the transmission method choice depends on "the nature transmission" (a word appears to be missing) and gives no criteria for choosing between the named transmission methods.

> **Gap:** The building block page's capability list is introduced as capabilities that *"can contribute to achieving technical interoperability"*, with no statement of which, if any, are required of a conformant data space. Individual sentences inside those capabilities do carry force ("needs to be made", "should clearly indicate") and have been captured at that force, but the capabilities themselves are recorded as `may`.

> **Gap:** The building block page (§5) states where the Data exchange protocol is implemented ("on the data plane level of the Participant agent") in the plain indicative with no modal verb, so it is unclear whether this is an architectural obligation or a description. Recorded as `informative` (`DSSC-DEX-21`).

> **Gap:** The building block glossary defines Transfer Process (TP) with the states REQUESTED, STARTED, COMPLETED, SUSPENDED, and TERMINATED "as a minimum", but no section of either document specifies the transitions between those states, nor which component owns them.

> **Gap:** Best practice §1 links the phrase "the data plane" to a page in the *business* pane (business and organisational services), whereas the building block page links the control-plane/data-plane distinction to the technical explainer on how a data plane and control plane work together. The two references do not point at the same material.

> **Note:** Best practice §2 says *"Examples of transmission protocols can be found in the further reading section"*, but the sub-page has no section named "further reading"; the closest is §6 "Examples", which lists API specifications rather than transmission protocols.

> **Note:** The building block page (§3) says "are there implementations of the protocols **above** that can be reused?", but no list of protocols precedes that sentence on the page — the protocol examples are on the best practice sub-page.
