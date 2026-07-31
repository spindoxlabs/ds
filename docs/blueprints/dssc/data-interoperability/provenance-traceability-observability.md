# Provenance, Traceability & Observability

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Provenance, Traceability & Observability
> **Category** · Data Interoperability

Data spaces are meant to provide a trusted environment that enables data sharing under a joint governance framework. This building block covers the recording and storage of metadata about the completion of processes within the data space, which can support trustworthiness by providing verifiable evidence that processes have been executed according to agreed rules and regulations, by increasing transparency and trust among participants, by enabling dispute resolution, and by facilitating operational and business purposes such as billing, charging or monitoring the use of highly valuable datasets.

## Scope and objectives

The recording and storage of metadata about the completion of processes within the data space can support trustworthiness:

- by providing verifiable evidence that processes have been executed according to agreed rules and regulations.
- by increasing transparency and trust among participants by allowing activities related to data usage to be traced and verified
- to enable dispute resolution, as recorded metadata can serve as objective proof in case of conflicts between participants,
- to facilitate operational and business purposes such as billing, charging, or monitoring the use of highly valuable datasets.

The source offers the use of data in artificial intelligence as "a prime example that highlights the importance of provenance, traceability, and observability within data spaces". Training an AI model relies on diverse data sources and complex data processing chains, often involving multiple participants across organizational boundaries. In such a distributed environment, it becomes crucial to know where data originates, how it has been transformed, and under which terms it can be used. Data spaces provide the governance and technical means to enable this transparency. Ensuring traceable and verifiable data usage not only supports regulatory compliance but also builds trust among participants, facilitates responsible data reuse, and enhances the overall reliability of AI-driven services within the ecosystem.

## Capabilities

The source states that "Three capabilities are required for dataspaces":

- **Data provenance** relates to backward looking in the data value chain: where did the data come from? Its purpose is to ensure trust and transparency in data lineage.
- **Transaction traceability** relates to the ability to follow the entire path of the data value chain: how was the data handled and by whom? Its purpose is to enable accountability and quality control.
- **Transaction observability** relates to "the ability to which certain decisions or outcomes can be understood" for the purposes of monitoring and troubleshooting.

The source adds a qualifier: "Note that the level to which these capabilities need to be implemented and how they are implemented depends on the specific circumstances of the dataspace."

> **Ambiguous:** the phrase "the ability to which certain decisions or outcomes can be understood" is grammatically incomplete in the source. It is rendered verbatim above rather than corrected.

## Co-creation questions

The source states: "To effectively implement this building block, the following questions must be answered." Each question is followed by explanatory text and by the steps needed to answer it.

**1. For which data products is provenance, traceability and observability required? And what needs to be recorded?**

This is the fundamental first step to determine why and what needs to be logged.

- Evaluate legal and contractual obligations: Identify all relevant legislation (such as GDPR or the AI Act) and typical contractual requirements (e.g., for billing or auditing) that mandate specific logging.
- Define the events to be recorded: Based on the identified requirements, determine which specific events on the Control Plane (observability) and everything else regarding the data transformation (provenance & traceability) must be logged by participants.

**2. Which datamodel will be used for recording and storing provenance, traceability and observability data?**

This question addresses the semantic layer of the logs, preventing each participant from using their own, incompatible log format.

- Select a standard data model: Evaluate and choose an existing, open standard data model for structuring the logs.
- Create an application profile (if necessary): If the standard is insufficient, define a domain-specific profile that extends the standard with concepts relevant to the data space, and document it.

**3. How will the logs be stored securely, and who can access them?**

This question deals with the technical implementation of storage and access control.

- Choose a storage architecture: Decide whether logs will be stored locally by either or both the participants, or independent trusted third party (Observability Service) will be used.
- Define access and usage policies: Define clear rules on who can access the logs, under what conditions, and for what purpose. Ensure these policies are technically enforceable. Additionally, access and usage policies could be negotiated in the data space between participants.

**4. How will the agreements on provenance, traceability and observability be governed?**

This final question ensures that all choices made are formally documented and managed.

- Document the rules in the rulebook: Record all of the above decisions—the mandatory events, the chosen data models, the storage architecture, and the access policies—in the data space's rulebook.
- Also define a process for maintaining and updating these rules as part of the framework.

## Specifications

"There are no mandatory specifications a dataspace shall follow for implementing this capability."

The source instead offers a separate explainer — *Best practice: implementing provenance, traceability & observability* — for setting up provenance, traceability and observability in a dataspace. It is rendered below.

## Implementation

To implement provenance, traceability and observability two services are relevant:

- **The participant agent** of the data provider, the data user or both. As part of the control plane data is generated and provided. This includes metadata on the data product which can include provenance data of the data product, and traceability and observability of decisions regarding the execution of access and usage policies.
- **A dedicated observability service**, which is a third party system operating on behalf of the dataspace governance authority, a data provider, data user or other actor in the ecosystem. In such a service the relevant data is collected and stored. Having an observability service is not mandatory for every dataspace, this depends on choices made in the dataspace-specific rulebook.

## Standards and protocols

The source names no mandatory specification for this building block (see "Specifications" above). The entries below are the standards, specifications and instruments it names, with the normative force it attaches to each.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| Dataspace Protocol (Eclipse data space Protocol) | No version stated; "The current specification can be found at: https://eclipse-dataspace-protocol-base.github.io/DataspaceProtocol" | Defines the three state machines (Catalog, Contract Negotiation, Transfer Process) whose states are the subject of observability on the Control Plane | referenced |
| W3C PROV-O | https://www.w3.org/TR/prov-o/ — no version stated | "Set of classes, properties, and restrictions to represent and interchange provenance information generated in different systems and under different contexts"; data model for provenance and traceability data | recommended |
| PAV — Provenance, Authoring and Versioning Ontology | https://pav-ontology.github.io/pav/ | "Specialises PROV-O to describe authorship, curation and digital creation of online resources"; recommended alongside PROV-O | recommended |
| CloudEvents | https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md | "a specification for describing event data in common formats to provide interoperability across services, platforms and systems"; an approach that "can be considered" for modeling specific events in the data space | may |
| W3C DCAT | `vocab-dcat-3` — https://www.w3.org/TR/vocab-dcat-3/#examples-dataset-provenance | The DCAT vocabulary specification examples include the use of PROV-O | referenced |
| ODRL | No version stated | Named as a semantic standard for which data-plane-level extensions "might be developed"; additional ODRL policies governing the permitted use of observed activities "could be created by data space initiatives" | may |
| Open Provenance Model | https://openprovenance.org/opm/ | "a predecessor of the Prov model, also brings specific aspects of provenance and may still have good resources" | referenced |
| Kantara Consent Receipts | https://kantarainitiative.org/download/7902/ | "for data sharing consent. Requirements for the creation of a consent record and the provision of a human-readable receipt" | referenced |
| IDSA Position Paper — Observability in Data Spaces | https://internationaldataspaces.org/wp-content/uploads/dlm_uploads/IDSA-Position-Paper-Observability-in-Data-Spaces.pdf | "provides further guidance on observability in data spaces and differentiates it provenance, traceability and regular IT-telemetry"; the blueprint content is "mainly based on this whitepaper" | referenced |
| CamFlow | https://camflow.org/ | "a Linux Security Module (LSM) designed to capture data provenance for the purpose of system audit" | referenced |
| How to Provenance | https://github.com/provenance-io/how-to-provenance | Repository of examples of provenance blockchain usage, smart contract development, application development and related topics | referenced |
| GDPR | Not cited by article | Named as legislation that may mandate specific logging; deletion logging cited as proof of GDPR compliance | referenced |
| AI Act | Not cited by article | Named as legislation that may mandate specific logging; data lineage described as "Mandatory ... especially under the AI Act" | referenced |

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-PTO-01` | A data space provides the capability of data provenance: backward looking in the data value chain — where did the data come from — to ensure trust and transparency in data lineage. | must | `provenance-traceability-observability.md` §2 |
| `DSSC-PTO-02` | A data space provides the capability of transaction traceability: the ability to follow the entire path of the data value chain — how was the data handled and by whom — to enable accountability and quality control. | must | `provenance-traceability-observability.md` §2 |
| `DSSC-PTO-03` | A data space provides the capability of transaction observability, for the purposes of monitoring and troubleshooting. | must | `provenance-traceability-observability.md` §2 |
| `DSSC-PTO-04` | The level to which these capabilities need to be implemented, and how they are implemented, depends on the specific circumstances of the dataspace. | informative | `provenance-traceability-observability.md` §2 |
| `DSSC-PTO-05` | The data space must answer for which data products provenance, traceability and observability are required, and what needs to be recorded. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-06` | The data space must identify all relevant legislation (such as GDPR or the AI Act) that mandates specific logging. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-07` | The data space must identify typical contractual requirements (e.g. for billing or auditing) that mandate specific logging. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-08` | The data space must determine which specific events on the Control Plane (observability) must be logged by participants. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-09` | The data space must determine which events regarding the data transformation (provenance & traceability) must be logged by participants. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-10` | The data space must answer which data model will be used for recording and storing provenance, traceability and observability data. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-11` | The data space must evaluate and choose an existing, open standard data model for structuring the logs. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-12` | If the chosen standard is insufficient, the data space must define a domain-specific profile that extends the standard with concepts relevant to the data space. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-13` | Such a domain-specific profile must be documented. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-14` | The data space must answer how the logs will be stored securely and who can access them. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-15` | The data space must decide whether logs will be stored locally by either or both of the participants, or whether an independent trusted third party (Observability Service) will be used. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-16` | The data space must define clear rules on who can access the logs, under what conditions, and for what purpose. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-17` | These access and usage policies must be technically enforceable. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-18` | Access and usage policies for logs could additionally be negotiated in the data space between participants. | may | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-19` | The data space must answer how the agreements on provenance, traceability and observability will be governed. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-20` | The data space must record the mandatory events, the chosen data models, the storage architecture and the access policies in the data space's rulebook. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-21` | The data space must define a process for maintaining and updating these rules as part of the framework. | must | `provenance-traceability-observability.md` §3 |
| `DSSC-PTO-22` | There are no mandatory specifications a dataspace shall follow for implementing this capability. | informative | `provenance-traceability-observability.md` §4 |
| `DSSC-PTO-23` | The participant agent of the data provider, the data user or both generates and provides, as part of the control plane, metadata on the data product which can include provenance data of the data product. | informative | `provenance-traceability-observability.md` §5 |
| `DSSC-PTO-24` | The participant agent provides traceability and observability of decisions regarding the execution of access and usage policies. | informative | `provenance-traceability-observability.md` §5 |
| `DSSC-PTO-25` | A dedicated observability service — a third party system operating on behalf of the dataspace governance authority, a data provider, data user or other actor in the ecosystem — may collect and store the relevant data. | may | `provenance-traceability-observability.md` §5 |
| `DSSC-PTO-26` | Having an observability service is not mandatory for every dataspace; this depends on choices made in the dataspace-specific rulebook. | informative | `provenance-traceability-observability.md` §5 |
| `DSSC-PTO-27` | Since the requirements for provenance and traceability can arise from various sources, the necessary capabilities depend on the specific use case. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-28` | Event logging and data generation: the ability to generate and capture (immutable) logs of key events occurring, such as the observability of contract negotiations and the traceability of data access. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-29` | The event logging capability should ensure compliance with legislation and contractual agreements by covering the proper requirements for provenance and traceability. | should | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-30` | Use of provenance data models: the ability to define and apply structured data models for describing provenance information in a consistent and interoperable manner, so that process and data lineage information can be clearly understood and exchanged across different participants and systems within the data space. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-31` | Secure storage and controlled access: the ability to facilitate the secure storage of logs and to manage access to them according to clear/enforceable authorization and usage policies, including an appropriate design for storage and processing solutions. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-32` | Governance of provenance and traceability: the capability of the data space (e.g. governance authority) to establish and manage governance processes as part of the participant management building block. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-33` | These governance processes ensure that the rules for logging, retention, and access are clearly defined in the rulebook. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-34` | These governance processes ensure that the rules for logging, retention, and access are updated in response to changing legal or contractual requirements. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-35` | Observability data can be as sensitive as the data shared under a contract, as it may reveal important information about business relationships. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-36` | It is "of high importance" to establish trust not just between the two parties sharing data but also with a possible third party receiving observability data. | should | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-37` | Observability services should not be centrally provided by a single entity, but offered in a decentralized manner defined within the data space governance. | should | `best-practice-implementing-provenance-traceability-observability.md` §1 |
| `DSSC-PTO-38` | Observability is considered to be on DSP data space level and thus placed on control plane level, while data provenance and traceability are seen at data plane level, where the actual data transfer takes place. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-39` | Both aspects may be subject to regulatory or contractual compliance. | may | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-40` | Ensuring observability and provenance tracking is the responsibility of each participant. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-41` | Ensuring observability and provenance tracking requires the implementation of robust data governance processes by all Data Space participants. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-42` | Concepts for observability need to satisfy horizontal (cross-sector) requirements. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-43` | Concepts for observability need to satisfy vertical (industry-specific) requirements. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-44` | Concepts for observability must maintain appropriate security controls. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-45` | Concepts for observability must maintain appropriate audit trails. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-46` | Concepts for observability must maintain appropriate compliance documentation. | must | `best-practice-implementing-provenance-traceability-observability.md` §1.1.1 |
| `DSSC-PTO-47` | Observability concerns the logging of DSP activities on the Control Plane; provenance and traceability concern the logging of events related to the data itself on the Data Plane. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2 |
| `DSSC-PTO-48` | The extent to which DSP events must be logged depends on the specific use case, legal or contractual obligations, and the general governance agreements within the data space. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.1 |
| `DSSC-PTO-49` | At the Catalog state, a participant's interactions with the catalog — such as requesting the list of data products or viewing the details of a specific dataset — can be observed. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.1, Table 1 |
| `DSSC-PTO-50` | At the Contract Negotiation state, the complete state cycle of the negotiation process — from the initial offer and counter-offers to the final acceptance and verification of the agreement — can be observed. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.1, Table 1 |
| `DSSC-PTO-51` | At the Transfer Process state, the state changes of the transfer process on the Control Plane — such as 'requested', 'started', 'completed', or 'terminated' — can be observed. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.1, Table 1 |
| `DSSC-PTO-52` | Telemetry data — such as system uptime, performance metrics, and other operational information — is implementation-specific and falls outside the scope of this building block. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.1 |
| `DSSC-PTO-53` | Observations for provenance and traceability begin with the transfer on the Data Plane but extend to the full lifecycle of the data before and after it has been received. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.2 |
| `DSSC-PTO-54` | There is (yet) no single or standardized data plane protocol for logging provenance and traceability events. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.2 |
| `DSSC-PTO-55` | Provenance and traceability events divide into three categories: pre transfer events, events during data transfer, and post transfer (lifecycle) events. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.2 |
| `DSSC-PTO-56` | Logging post transfer events often requires active cooperation from the consumer (e.g. via self-reporting) or the use of specialized, trusted applications. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.2 |
| `DSSC-PTO-57` | The event table in §1.2.2 lists **possible** events a data space can require participants to log or provide; it is not exhaustive and serves as a starting point. | informative | `best-practice-implementing-provenance-traceability-observability.md` §1.2.2 |
| `DSSC-PTO-58` | Information collected about observability, provenance, and traceability must be captured in a structured and standardized data model. | must | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-59` | All principles from the Data Models building block apply to observability, provenance and traceability data. | must | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-60` | The reuse of existing standards is to be prioritized for this data. | should | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-61` | Extending an existing model or creating a new one should only be considered if reuse is not viable. | should | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-62` | There is no one-size-fits-all semantic standard for this data, as it is highly dependent on the use case and the type of data to be logged and stored. | informative | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-63` | For many scenarios it is recommended to align with existing, open standards such as W3C PROV-O and PAV — Provenance, Authoring and Versioning — primarily for provenance and traceability data. | recommended | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-64` | For domain-specific requirements, these standards can be extended. | may | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-65` | An approach like CloudEvents can be considered for modeling specific events in the data space. | may | `best-practice-implementing-provenance-traceability-observability.md` §2 |
| `DSSC-PTO-66` | Because P&T data is metadata, similar governance structures as for the original data can be applied and existing trust mechanisms can be reused. | may | `best-practice-implementing-provenance-traceability-observability.md` §3 |
| `DSSC-PTO-67` | The role of an observer for P&T data can be considered a business process role and not a technical function, as it does not require any special implementations on a technical level. | informative | `best-practice-implementing-provenance-traceability-observability.md` §3 |
| `DSSC-PTO-68` | No changes on a technical level are mandatory for the collection of P&T data. | informative | `best-practice-implementing-provenance-traceability-observability.md` §3 |
| `DSSC-PTO-69` | Changes might be developed to facilitate data collection and exchange, including extensions for semantic standards like ODRL on a data plane level. | may | `best-practice-implementing-provenance-traceability-observability.md` §3 |
| `DSSC-PTO-70` | Either or both of the parties involved in the data sharing can store the P&T data. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-71` | Each participant in a data space could use a participant agent service to retrieve data and store it in a separate database. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-72` | A neutral third party can be involved to store the P&T data. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-73` | Involving a trusted third party is always recommendable to provide a neutral instance for conflict resolution. | recommended | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-74` | If no trusted third party is involved, it is advisable to store the P&T data at both provider and consumer, so both have evidence in case of disputes or audits. | recommended | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-75` | It needs to be defined which entity stores which part of the P&T data, which might also include redundancies. | must | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-76` | For non-mandatory P&T data, the allocation of storage could be agreed on in a peer-to-peer fashion. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-77` | For mandatory P&T data, the allocation of storage should be clearly defined in the data space rulebook. | should | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-78` | For non-mandatory data, participants can store the data in any way they like, potentially for internal processes. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-79` | For mandatory P&T data it needs to be guaranteed that the data can be accessed and presented on demand. | must | `best-practice-implementing-provenance-traceability-observability.md` §3.1 |
| `DSSC-PTO-80` | P&T data is very sensitive data: it can reveal information about business processes and connections between participants, which might be considered confidential. | informative | `best-practice-implementing-provenance-traceability-observability.md` §3.2 |
| `DSSC-PTO-81` | The trust between a third party observer and all other parties must always be ensured for the collection of P&T data. | must | `best-practice-implementing-provenance-traceability-observability.md` §3.2 |
| `DSSC-PTO-82` | Additional ODRL policies governing the permitted use of the observed activities could be created by data space initiatives. | may | `best-practice-implementing-provenance-traceability-observability.md` §3.2 |
| `DSSC-PTO-83` | The implementation needs to be performant and must not slow down the overall performance of the data space. | must | `best-practice-implementing-provenance-traceability-observability.md` §3.3 |
| `DSSC-PTO-84` | An appropriate data model for each type of P&T data storage must be chosen that is capable of tracking all the necessary information. | must | `best-practice-implementing-provenance-traceability-observability.md` §3.3 |
| `DSSC-PTO-85` | P&T data collection on each control plane and data plane process can cause significant transaction overhead, and the data volume can grow quickly and reach storage limitations, which in the worst case could prevent the data space from scaling. | informative | `best-practice-implementing-provenance-traceability-observability.md` §3.3 |
| `DSSC-PTO-86` | Data from various sources needs to be integrated properly, which can be a challenging task. | informative | `best-practice-implementing-provenance-traceability-observability.md` §3.3 |

## Explainers and best practices

The building block has one upstream sub-page, rendered in full below.

## Best practice: implementing provenance, traceability & observability

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability › Provenance, Traceability & Observability › Best practice: implementing provenance, traceability & observability

### 1. Detailed capabilities

Since the requirements for provenance and traceability can arise from various sources, the necessary capabilities will depend on the specific use case. These capabilities are:

- **Event logging and data generation** is the ability to generate and capture (immutable) logs of key events occurring like the observability of contract negotiations and the traceability of data access. This capability should ensure compliance with legislation and contractual agreements by covering the proper requirements for provenance and traceability.
- **Use of provenance data models** is the ability to define and apply structured data models for describing provenance information in a consistent and interoperable manner. This enables process and data lineage information to be clearly understood and exchanged across different participants and systems within the data space.
- **Secure storage and controlled access** enables to facilitate the secure storage of these logs and to manage access to them according to clear/enforceable authorization and usage policies. This includes implementing an appropriate design for storage and processing solutions, and authorization and usage policies.
- **Governance of provenance and traceability** is capability of the data space (e.g., governance authority) to establish and manage governance processes as part of the participant management building block. These processes ensure that the rules for logging, retention, and access are clearly defined in the rulebook and updated in response to changing legal or contractual requirements.

Implementing these capabilities requires careful consideration of trust and security. Observability data can be as sensitive as the data shared under a contract, as it may reveal important information about business relationships. For this reason, it is of high importance to establish trust not just between the two parties sharing data but also between a possible the 3rd party receiving observability data. To mitigate risks, such services should not be centrally provided by a single entity, but are offered as a decentralized manner defined within the data space governance.

#### 1.1 Implementing these capabilities in detail

##### 1.1.1 Observability, Traceability and Provenance of transactions

Figure 1 (not reproduced here) illustrates an integration concept for these terms in data spaces at the control and data plane levels of the participant agent, highlighting the differences in terminology. Hereby, the observability is considered to be on DSP data space level and thus placed on control plane level, while data provenance and traceability is rather the be seen at data plane level, where the actual data transfer takes place.

Both aspects fall may be subject to regulatory or contractual compliance. Regardless, ensuring observability and provenance tracking is the responsibility of each participant and requires the implementation of robust data governance processes by all Data Space participants. These concepts for observability need to satisfy both, horizontal (cross-sector) and vertical (industry-specific) requirements while maintaining appropriate security controls, audit trails, and compliance documentation.

#### 1.2 Different observation types

This subsection provides an overview of the different observation types and which processes can be observed in data spaces. Again, we distinguish between **observability**, which concerns the logging of DSP activities on the Control Plane, and **provenance and traceability**, which is about logging events related to the data itself on the Data Plane.

##### 1.2.1 Observability - Dataspace Protocol States

The table below provides an overview of the different DSP states and what type of data can be observed at each moment. The extent to which these events must be logged depends on the specific **use case, legal or contractual obligations, and the general governance agreements** within the data space. This table highlights in general the three state machines in the DSP; for more details on the specific states and what can be observed, the source refers to the [IDSA Paper on Observability](https://internationaldataspaces.org/wp-content/uploads/dlm_uploads/IDSA-Position-Paper-Observability-in-Data-Spaces.pdf).

| Dataspace Protocol States | What can be observed? | Why? |
|---|---|---|
| Catalog | A participant's interactions with the catalog, such as requesting the list of data products or viewing the details of a specific dataset. | For market analysis and business intelligence to, for example, track the popularity of data offerings. Example: A data provider analyses which organizations are viewing its data products to identify potential new customers. |
| Contract Negotiation | The complete state cycle of the negotiation process, from the initial offer and counter-offers to the final acceptance and verification of the agreement. | Essential for legal evidence, audits, and dispute resolution. Example: In a conflict over usage rights, the log serves as irrefutable proof of the agreed-upon terms. |
| Transfer Process | The state changes of the transfer process on the Control Plane, such as 'requested', 'started', 'completed', or 'terminated'. | Links the contract to the technical execution; crucial for operational monitoring and billing. Example: A pay-per-use model uses the 'completed' state as the trigger for a billing cycle. |

*Table 1. Steps of the DSP and respective observability data.*

While end-to-end implementations may also incorporate telemetry data—such as system uptime, performance metrics, and other operational information—these aspects are implementation-specific and fall outside the scope of this building block.

##### 1.2.2 Provenance and Traceability - Data Lifecycle Events

Whereas **observability** is strictly coupled to the Control Plane, **provenance and traceability** concern the data itself. Observations for provenance and traceability begin with the transfer on the Data Plane but extend to the full lifecycle of the data before and after it has been received.

Given the diversity of transfer methods and the private nature of participants' systems, there is (yet) no single or standardized data plane protocol for logging these events. The specific logging requirements are highly dependent on the use case and the agreements made.

For provenance and traceability, we can divide the events into three categories:

- **Pre transfer events**: This is provenance metadata about the history of the data before it is transferred.
- **Events during data transfer**: These are events that are directly observable on or around the Data Plane during the transaction.
- **Post transfer events (lifecycle)**: These are events that occur within the consumer's systems after the data has been received. Logging these often requires active cooperation from the consumer (e.g., via self-reporting) or the use of specialized, trusted applications.

The table below provides an overview of **possible** events and information that a data space can require participants to log or provide. This list is not exhaustive and serves as a starting point.

| Events (suggestions!) | Type of data | What can be observed? | Why? |
|---|---|---|---|
| **Pre transfer** | | | |
| Data Creation | Provenance | Information about the data origin, creation date, ownership, and data usage rights. | Essential for assessing the reliability and legal validity of the data. Example: An AI company must be able to demonstrate the origin of training data to comply with the AI Act. |
| **During transfer** | | | |
| Data Access | Provenance & Traceability | Logs that a consumer connects to the provider's endpoint and starts the data transfer. | Proves that the data was actually requested; starting point of the 'chain of custody'. Example: In logistics, logging access to freight documents is crucial for tracking goods. |
| Data Transfer | Provenance & Traceability | Logs the successful completion or failure of the transfer, including metadata such as size and timestamp. | Serves as proof of (non-)delivery. Example: A financial institution must prove that some reports has been successfully delivered. |
| **Post transfer** | | | |
| Data Lineage | Traceability | Logs (by the consumer) that the data has been processed or combined. This is mainly traceability for the original data and for provenance related to new data. The transformation of data can be performed by value added services, as explained in that building block. | Mandatory for data lineage, especially under the AI Act. Example: An AI company logs that Dataset_A was used to train Model_B, making the model's origin verifiable. |
| Data Deletion | Traceability | Logs (by the consumer) the deletion of the data, which can be essential for GDPR compliance. | To comply with privacy legislation and contractual agreements on data retention. Example: an organization logs the deletion of personal data as proof for GDPR compliance. |

### 2. A data model for observability, provenance, and traceability data

Information collected about observability, provenance, and traceability is also data itself. Therefore, like any other data product, it must be captured in a structured and standardized data model. All principles from the Data Models building block apply here. This means prioritizing the reuse of existing standards, and extending an existing model or creating a new one should only be considered if reuse is not viable.

However, there is no one-size-fits-all semantic standard, and there probably never will be, as it is highly dependent on the use case and the type of data you want to log and store. As shown in Figure 2 (a conceptual model for observability, provenance, and traceability data; not reproduced here), this building block provides insight into the data models needed to simplify logging across a multitude of data spaces. These models are required for three key data types:

- **Provenance**: the origin and history of data (data lineage).
- **Traceability**: the usage of data after it has been shared.
- **Observability**: logs of interactions in the control plane (e.g., contract negotiations).

**Recommendation for the data model**

As mentioned, there is no 'one-size-fits-all' solution as it depends on the data space implementation and the information to be logged, but the following approach is recommended:

- **Generic**: For many scenarios, it is recommended to align with existing, open standards such as W3C PROV-O and PAV - Provenance, Authoring and Versioning. This is primarily for provenance and traceability data.
- **Specific**: For domain-specific requirements, these standards can be extended. An approach like CloudEvents can be considered for modeling specific events in the data space.

Standardizing this data simplifies the implementation of auditing and compliance, lowers the barrier for the development of analysis and reporting tools, and builds trust within the ecosystem.

### 3. Where to store provenance, traceability & observability data?

Data for provenance, traceability and observability (shortened P&T data) is just metadata, thus data about data. Hence, similar governance structures as for the original data can be applied and existing trust mechanisms can be reused, which enable the data sharing in the first place. Hence, the role of an observer for P&T data can be considered a business process role and not a technical function, as it does not require any special implementations on a technical level.

Although no changes on a technical level are mandatory for the collection of P&T data, some changes might be developed to facilitate data collection and exchange. This might include the development extensions for semantic standards like ODRL on a data plane level.

#### 3.1 Storage and Collection P&T Data

P&T data can be stored at different places, distributing it across multiple stakeholders. Any or both of the parties involved in the data sharing can store the P&T data (see Figure 2). Each participant in a data space could use a participant agent service to retrieve data and store it in a separate database. Depending on the data to be collected and keeping in mind which data each party can access any of the three constellations shown in Figure 2 might be suitable.

Additionally, a neutral third party can be involved to store the P&T data (see Figure 3). Worth mentioning here is that similar roles apply as in the original data sharing, as P&T data is also just data to be exchanged. Thus, an observer can also be see to be just another participant in the data space. As the observer is consider to be a business role instead of a technical role, no technical changes to the data space will be required.

In general, involving a trusted third party is always recommendable to provide a neutral instance for conflict resolution. If not, it would be advisable to store the P&T at provider and consumer, so both have evidence in case of disputes or audits.

It can be assumed that not all P&T that one entity stores also needs to be stored by all other entities. Hence it needs to be defined, which entity stores which part of the P&T data, which might also include redundancies, especially for the case of conflict resolution and no thrid party is included that could provide neutral evidence. For non-mandatory P&T data, this could either be agreed on in a peer-to-peer fashion and for mandatory data it should be clearly defined in the data space rulebook. For the non-mandatory data the participants can store the data in any way they like, potentially for internal processes. Additionally, for the mandatory P&T it needs to be guaranteed that the data can be accessed and present it on demand.

#### 3.2 Access and Usage Control for P&T Data

P&T data is very sensitive data. It can reveal information about business processes and connections between participants, which might be considered confidential. Especially accessing P&T data for the entire data space, for example if the data stored at a central 3rd party provider, might have a high potential for data sensitive data aggregation. Also the trust between a 3rd party observer and all other parties must also always be ensured for the collection of P&T data. To this end, additional ODRL policies governing the permitted used of the observed activities could be created by data space initiatives.

#### 3.3 Technical Challenges for the Implementation

While the collection of P&T is necessary and beneficial in most places, it might also impose some technical challenges. Most important is that the implementation needs to be performant and thus does not slow down the overall performance of the data space. As the P&T data needs to be collected on each process on the control plane and the data plane, its collection can cause signification transaction overhead. Also the data volume of P&T data can grow quite fast, reaching storage limitations. In the worst case this could prevent the data space from scaling.

Also the storage and collection of P&T data need to be considered. An appropriate data model for each type of P&T data storage must be chosen that is capable to track all the necessary information. All this data from various sources needs to be integrated properly, which can be a challenging task.

### 4. Further reading

The sub-page closes with a reading list, reproduced verbatim in substance below.

**Observability**

- IDSA Paper on Observability provides further guidance on observability in data spaces and differentiates it provenance, traceability and regular IT-telemetry. It provides many more details of the content in this blueprint which is mainly based on this whitepaper.

**Provenance**

- W3C PROV-O / https://www.w3.org/TR/prov-o/. Set of classes, properties, and restrictions to represent and interchange provenance information generated in different systems and under different contexts. Additionally, DCAT vocabulary specification examples include the use of PROV-O https://www.w3.org/TR/vocab-dcat-3/#examples-dataset-provenance
- PAV (Provenance, Authoring and Versioning) Ontology https://pav-ontology.github.io/pav/. Specialises PROV-O to describe authorship, curation and digital creation of online resources

**Traceability**

- Cloudevents https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md is a specification for describing event data in common formats to provide interoperability across services, platforms and systems.
- Open Provenance Model https://openprovenance.org/opm/ is a predecessor of the Prov model, also brings specific aspects of provenance and may still have good resources.
- Kantara Consent Receipts (https://kantarainitiative.org/download/7902/) is for data sharing consent. Requirements for the creation of a consent record and the provision of a human-readable receipt.

**Further resources**

- Data Spaces from a GDPR perspective examines how Data Spaces can be designed in compliance with the GDPR, focusing on proactive accountability and data protection by design. It relates to provenance, traceability, and observability by ensuring that Data Spaces aligning data governance with GDPR principles which needs to be considered when processing personal data.
- CamFlow https://camflow.org/ is a Linux Security Module (LSM) designed to capture data provenance for the purpose of system audit.
- How to Provenance https://github.com/provenance-io/how-to-provenance is a repository where you can find examples of provenance blockchain usage, smart contract development, application development and related topics.

## Glossary

The building block page carries its own glossary, reproduced verbatim.

| Term | Definition |
|---|---|
| Provenance | The place of origin or earliest known history of something. Usually it is the backwards-looking direction of a data value chain which is also referred to as provenance tracking |
| Traceability | The quality of having an origin or course of development that may be found or followed |
| Observability | The ability to monitor, measure and understand the internal states of processes through its outputs such as logs, metrics and traces. |
| Dataspace Protocol | The Eclipse data space Protocol is a set of specifications that enable secure, interoperable data sharing between independent entities by defining standardized models, contracts, and processes for publishing, negotiating, and transferring data within data space s. The current specification can be found at: https://eclipse-dataspace-protocol-base.github.io/DataspaceProtocol |
| Data Space Governance Authority | A governance authority refers to bodies of a data space that are composed of and by data space participants responsible for developing and maintaining as well as operating and enforcing the internal rules. |

## Tools implementing this building block

The building block page lists tools from the blueprint's tool catalogue. These are illustrations, not requirements: the source names them without endorsing or mandating any of them. Descriptions are the source's own.

| Tool | Listed service category | Description (source's own) |
|---|---|---|
| Ocean Enterprise Provider | Participant Agent Services | The Ocean Enterprise Provider, alternatively named the "Connector" or "Access Controller" is a REST API specifically designed for the provisioning of data services. The access controller acts as an intermediary between the data source/data product provider and the user/data product consumer, thus preventing the need for the data product consumer to have direct access to the data product. Before granting access to a resource it performs a series of checks to verify the users permission to access a service, such as a data product contract opt-in, the identity of the data product consumer, successful payment, and access policies. The Ocean Enterprise Provider supports integrity checks, the transfer of data, the orchestration of Compute-to-Data, and the forwarding to service offerings to support "Everything as a Service". |
| Nautilus Participant Agent | Participant Agent Services | As a Data Space Participant Agent Nautilus for Ocean Enterprise provides Data Space Participants with the ability to publish, manage, discover, and consume data products and service offerings. It is a data economy toolkit and abstraction layer enabling programmatic interactions with the Ocean Enterprise Data Space Infrastructure and Components required by Participants. |
| Data Space Innovation Lab Connector | Participant Agent Services | IDSA complient certified IDS connector |
| TNO Security Gateway (TSG) | Participant Agent Services | The TSG components allows you to participate in an IDS dataspace to exchange information with other organizations with data sovereignty in mind. You will be able to participate with the provided components as-is, but you're allowed to modify the components to create your own dataspace with specific use cases in mind. |
| FIWARE Data Space Framework (FDF) | Participant Agent Services | The FIWARE Data Space Framework FDF is an integrated suite of components implementing DSBA Technical Convergence recommendations, every organization participating in a data space should deploy to "connect" to a data space. |
| Tekniker Dataspace Connector | Participant Agent Services | Modular solution that, deployed in any organization, allows to establish a single point of entry for multiple data sources either proprietary in the role of the Data Provider or available throughout the Data Space in the role of Data Consumer ensuring the interoperability of shared data, trust between the parties involved in data exchange and data sovereignty |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services | The sovity EDC Community Edition extends the Eclipse Dataspace Connector (EDC) with additional open-source enhancements, providing a ready-to-use solution for secure data exchange while ensuring data sovereignty. |
| Simpl-Open – Participant Agent | Participant Agent Services | Simpl is the open-source smart middleware that enables cloud-to-edge federations and all major data initiatives funded by the European Commission. Simpl-Open is a suite of integrated and modular components. This includes components for Participant Agent service. See the "Purpose" section for a description of how Simpl-Open covers the service. |
| Ocean Enterprise Catalogue and Aquarius Catalogue Cache | Catalogue | The Ocean Enterprise Catalogue allows the distributed, tamper-proof, self-sovereign storage of Data, Services, and Offerings Descriptions. Metadata records are stored as signed Verifiable Credentials utilizing Ocean Enterprise smart contracts. The metadata is openly extensible to support domain-specific descriptions and standards, such as DCAT, Gaia-X, and others. As API and for performant queries against the distributed catalogue of any Ocean Dataspace the Aquarius Catalogue Cache Component, based on Elasticsearch, is utilized. Aquarius continuously monitors metadata being created or updated and caches the catalogue state for local processing supporting participant agents, markets and applications using the Data Space Infrastructure. |
| sovity Data Space Portal (DSPortal) | Catalogue | The Data Space Portal is a comprehensive platform that enables seamless interactions within data spaces, providing tools for data discovery and governance, while ensuring interoperability and adherence to data sovereignty principles for the data space members. The Crawler module of the Data Space Portal is designed to automatically discover, index, and update data resources across members Connectors. This component enhances the usability of data spaces by providing seamless and real-time insights into available data offers, supporting interoperability and data-sharing standards |
| Simpl-Open - Catalogue | Catalogue | Simpl is the open-source smart middleware that enables cloud-to-edge federations and all major data initiatives funded by the European Commission. Simpl-Open is a suite of integrated and modular components. This includes components for Catalogue service. See the "Purpose" section for a description of how Simpl-Open covers the service. |
| Data Space Builder | Value-Creation Services | The Data Space Builder is a suite composed by the different data spaces components and technical building blocks such as catalogs, vocabulary services, trust framework & usage, policies and identity management, and data exchange including connectors and agents, also focused on semantic data management, data models management and NLP (Natural Language Process) intelligence. |

## Open questions

The following are ambiguities, gaps and internal inconsistencies observed in the source. They are recorded, not resolved.

- **"Required" capabilities versus circumstance-dependent implementation.** §2 of the building block page states that "Three capabilities are required for dataspaces", then immediately qualifies that "the level to which these capabilities need to be implemented and how they are implemented depends on the specific circumstances of the dataspace". §4 then states that "There are no mandatory specifications a dataspace shall follow for implementing this capability". It is not stated what, if anything, remains mandatory. `DSSC-PTO-01` to `DSSC-PTO-03` are recorded with force `must` on the strength of the word "required", but the qualifier makes the obligation untestable as written.

- **Definition of transaction observability is grammatically incomplete.** "Transaction observability relates to the ability to which certain decisions or outcomes can be understood" (§2). "The ability to which" is not a complete construction; the intended reading is not determinable from the text.

- **Predominantly non-normative source.** Outside §3 (co-creation questions, introduced with "must be answered") and a small number of sentences in the best practice sub-page, the material is descriptive. A majority of the requirement rows above therefore carry force `informative`. Promoting them would misstate the source.

- **List nesting in §3 is flattened.** In the source, the four co-creation questions and the two-to-three sub-steps that answer each appear at the same bullet level, separated only by interleaved explanatory sentences. The grouping used in "Co-creation questions" above follows those explanatory sentences; the source does not mark the hierarchy structurally.

- **Table 1 has a stray column.** The header row of the DSP-states table declares four columns ("Dataspace Protocol States", an empty cell, "What can be observed?", "Why?") while each data row populates three, leaving the last cell empty. The table is rendered here with three columns. The caption in the source reads "Table 1. Steps of the DSP and respective observability data[]." with a trailing empty bracket.

- **Figure numbering is reused.** The best practice sub-page introduces "Figure 2" in §2 as the "conceptual model for observability, provenance, and traceability data", then in §3.1 refers to "Figure 2" again for the storage constellations between the two sharing parties ("see Figure 2", "any of the three constellations shown in Figure 2") and to "Figure 3" for the neutral third party case. Two distinct figures carry the number 2. The figures themselves (Figures 1, 2 and 3) are images and are not reproduced in this rendering; their content is only knowable from the surrounding prose.

- **The Data Models cross-reference points at an archived page.** §2 of the best practice sub-page links the Data Models building block to a page whose identifier ends in `_archived`, while Data Models is a live building block in the same category as this one. Which version of the Data Models principles is intended is not stated.

- **"Participant management building block" is named but not linked.** §1 of the best practice sub-page places governance of provenance and traceability "as part of the participant management building block". No such link or exact upstream name is given on this page.

- **Third-party observability: recommended and discouraged in the same document.** §1 states that observability services "should not be centrally provided by a single entity, but are offered as a decentralized manner defined within the data space governance", while §3.1 states that "involving a trusted third party is always recommendable to provide a neutral instance for conflict resolution". Whether a single trusted third party observer satisfies the decentralisation expectation is not addressed.

- **Retention is governed but never specified.** "Rules for logging, retention, and access" are to be defined in the rulebook (§1 of the sub-page), but retention is not otherwise mentioned — no periods, no criteria, and no relationship to the GDPR deletion logging described in §1.2.2.

- **Immutability is parenthetical.** The event logging capability is described as generating "(immutable) logs". The parentheses are the source's; it does not say whether immutability is required, and no mechanism for it is discussed.

- **Uncited legal instruments.** GDPR and the AI Act are named as sources of logging obligations, and data lineage logging is called "Mandatory ... especially under the AI Act", without an article or provision citation for either instrument.

- **Source text quality.** The sub-page contains several evident transcription or drafting errors, preserved verbatim in the rendering above where they occur inside quoted material: "Both aspects fall may be subject to", "between a possible the 3rd party", "are offered as a decentralized manner", "is rather the be seen at", "an observer can also be see to be", "the observer is consider to be", "signification transaction overhead", "the permitted used of", "no thrid party is included", "some reports has been successfully delivered".
