# Publication and Discovery

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Value Creation Enablers › Publication and Discovery
> **Category** · Data Value Creation Enablers

This building block addresses the provisioning and discovery of offerings within a data space. These offerings are published and stored in a catalogue: an inventory of metadata of data and services published by one or more data- and service providers, which can be searched by data users.

## Scope and objectives

The objectives of this building block are:

- To expose offerings of data and services by publishing them in a catalogue, where potential data users can discover them through a discovery service.
- To manage offerings in the catalogue in accordance with their lifecycle.

The definition of the required metadata of a data product is **not** in scope here: it is within the scope of the **Data, Services and Offerings** building block.

### Co-creation questions

The source poses two co-creation questions that the data space must answer when implementing this building block. They are questions, not requirements, except where they state an obligation (captured in the Requirements table).

- **How will catalogue services be implemented in the data space?** The rulebook determines which data products can be contained in a data space; this is addressed in the Data, Services and Offerings building block. Every participant needs to implement or use a catalogue service as part of the control plane of the participant agent. However, different architectural options exist for which the data space governance authority needs to make a decision. For example: the publishing of catalogue entries in the catalogue of another participant; the federation of multiple catalogue services; or the setting-up of a single shared catalogue. It is important to determine the required set-up for a specific data space.
- **Which discovery services are needed? And who is providing them?** In addition to catalogues, more advanced discovery services can be needed which act as a directory to catalogues. There can be a single discovery service in a particular data space, or multiple. For some use cases an additional discovery service is not necessary.

### Glossary (upstream §7)

Definitions, not requirements — no requirement IDs are assigned to them.

| Term | Definition |
|---|---|
| Catalogue | A functional component to provision and discover offerings of data and services in a data space. |
| Data Consumer | A consumer of data or service. |
| Data Provider | A provider of data or service. |
| Offering | Data product(s), service(s), or a combination of these, and the offering description. Offerings can be put into a catalogue. |

## Capabilities

The source states that participants in data spaces *need to implement* the following capabilities:

- Exposure of offerings of a participant agent via a catalogue interface, so that they are discoverable by data consumers.
- Management of offerings in accordance with their lifecycle: publish, update, remove.
- Visibility- and access management of offerings, where offerings may be visible and/or accessible to all, or a subset of data space participants.

Data spaces **can** include a discovery service capability next to any catalogues. Discovery services allow for the wider querying of catalogues.

On implementation, the source states only that the required capabilities *can* be implemented using the catalogue service, *can* be accompanied by a discovery service, and that implementation also requires the Participant Agent to publish entries.

## Standards and protocols

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| Dataspace Protocol (DSP) | most recent version 2025-1 (linked build `2025-1-err1`) | Managing the exchange of catalogue entries for a catalogue service. | recommended |
| Catalogue Protocol | a specification of the Dataspace Protocol | Defines the specific protocols and schemas for publishing and discovering offerings, and how they are exchanged among dataspace participant agents. | required (within DSP) |
| DCAT-AP | not stated | Within DSP, the DCAT-AP based specification is used as syntax to exchange the metadata of individual data products; DCAT needs to be extended using DCAT-AP for use in a specific data space. | required (within DSP) |
| DCAT | DCAT version 3 (`https://www.w3.org/TR/vocab-dcat-3/`) | Offerings are represented using the `DCAT:Catalog` class and its properties; catalogues are collections of DCAT datasets and DCAT data services; `dcat:record` points to catalogue record identifiers. | required (within the Catalogue Protocol) |
| ODRL | not stated | Policies can be expressed using ODRL; within the Catalogue Protocol, access and usage control of offerings are expressed as ODRL policies. | may |
| IDS-RAM 4 | 4 | Named as the source of the metadata broker as an example of a centralized publication and discovery component, and as the partial origin of the centralized-publication process figure. | referenced |

The source does not state a version or profile for DCAT-AP or ODRL.

### Tools listed upstream (illustrative, not requirements)

The upstream page carries a vendor listing under "Tools implementing this building block". It is a directory of third-party offerings, not a specification: NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. (Trust Service); Ocean Enterprise Provider, Nautilus Participant Agent, Data Space Innovation Lab Connector, TNO Security Gateway (TSG), FIWARE Data Space Framework (FDF), Tekniker Dataspace Connector, sovity EDC Community Edition (EDC CE), Simpl-Open – Participant Agent (Participant Agent Services); Ocean Enterprise Catalogue and Aquarius Catalogue Cache, sovity Data Space Portal (DSPortal), Simpl-Open - Catalogue (Catalogue); Data Space Builder (Value-Creation Services).

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-PUB-01` | A participant must expose the offerings of a participant agent via a catalogue interface, so that they are discoverable by data consumers. | must | `publication-and-discovery.md` §2 |
| `DSSC-PUB-02` | A participant must manage offerings in accordance with their lifecycle: publish, update, remove. | must | `publication-and-discovery.md` §2 |
| `DSSC-PUB-03` | A participant must provide visibility- and access management of offerings, where offerings may be visible and/or accessible to all, or a subset of data space participants. | must | `publication-and-discovery.md` §2 |
| `DSSC-PUB-04` | A data space may include a discovery service capability next to any catalogues, allowing for the wider querying of catalogues. | may | `publication-and-discovery.md` §2 |
| `DSSC-PUB-05` | Every participant needs to implement or use a catalogue service as part of the control plane of the participant agent. | must | `publication-and-discovery.md` §3 |
| `DSSC-PUB-06` | The data space governance authority needs to make a decision on the architectural option for catalogue services in the data space. | must | `publication-and-discovery.md` §3 |
| `DSSC-PUB-07` | For implementing a catalogue service it is recommended to use the Dataspace Protocol (DSP) for managing the exchange of catalogue entries. | recommended | `publication-and-discovery.md` §4 |
| `DSSC-PUB-08` | Within DSP the DCAT-AP based specification is used as syntax to exchange the metadata of individual data products. | must | `publication-and-discovery.md` §4 |
| `DSSC-PUB-09` | Policies can be expressed using ODRL. | may | `publication-and-discovery.md` §4 |
| `DSSC-PUB-10` | The required capabilities can be implemented using the catalogue service. | may | `publication-and-discovery.md` §5 |
| `DSSC-PUB-11` | The catalogue service can be accompanied by a discovery service. | may | `publication-and-discovery.md` §5 |
| `DSSC-PUB-12` | Implementation requires the Participant Agent to publish entries. | must | `publication-and-discovery.md` §5 |
| `DSSC-PUB-13` | A data provider publishing an offering must be a registered data space participant and must be able to be authenticated as such. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Pre-conditions |
| `DSSC-PUB-14` | A data provider must be authorized to publish the offering in the catalogue. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Pre-conditions |
| `DSSC-PUB-15` | The catalogue must process the publication of the offering(s) and inform the data provider of the publication. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Main Success Scenario |
| `DSSC-PUB-16` | After publication, potential data consumers must be able to discover the offering. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Post-conditions |
| `DSSC-PUB-17` | An offering could, if necessary, be made accessible only to a subset of data space participants. | may | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Post-conditions |
| `DSSC-PUB-18` | The offering should be assigned a global unique resolvable persistent identifier (PID) to facilitate potential discovery from other data spaces. | should | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Post-conditions |
| `DSSC-PUB-19` | Where the data provider is not authenticated and/or authorized, the catalogue must deny publication of the offering(s). | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §I Extensions |
| `DSSC-PUB-20` | A data provider updating an offering must be authorized to modify the offering in the catalogue. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §II Pre-conditions |
| `DSSC-PUB-21` | An offering may only be updated if it has previously been published in the catalogue. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §II Pre-conditions |
| `DSSC-PUB-22` | The catalogue must process the update of the offering(s) and inform the data provider of the update. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §II Main Success Scenario |
| `DSSC-PUB-23` | Where the data provider is not authenticated and/or authorized, the catalogue must deny the update of the offering. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §II Extensions |
| `DSSC-PUB-24` | The catalogue must process the removal of the offering(s) and inform the data provider of the removal. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §III Main Success Scenario |
| `DSSC-PUB-25` | A removed offering must no longer be discoverable by data consumers. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §III Post-conditions |
| `DSSC-PUB-26` | Where the data provider is not authenticated and/or authorized, the catalogue must deny the removal of the offering. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §III Extensions |
| `DSSC-PUB-27` | A data consumer discovering offerings must be a registered data space participant. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Pre-conditions |
| `DSSC-PUB-28` | The catalogue must accept a request from a data consumer that includes the parameters to search the offerings in the catalogue. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Main Success Scenario |
| `DSSC-PUB-29` | The catalogue must compose a collection of relevant offerings based on the request. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Main Success Scenario |
| `DSSC-PUB-30` | The catalogue must send the resulting collection of offerings to the data consumer. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Main Success Scenario |
| `DSSC-PUB-31` | Where the data consumer is not authenticated and/or authorized, the catalogue must deny access to the offering(s). | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Extensions |
| `DSSC-PUB-32` | Where the data consumer is not authenticated and/or authorized, the catalogue must not collect relevant offerings based on the request. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Extensions |
| `DSSC-PUB-33` | An external party that is not a participant in the data space where an offering was initially published, but holds a global unique resolvable PID for that offering, may use a service to resolve this identifier to a metadata record. | may | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Extensions |
| `DSSC-PUB-34` | Access to the data or service itself would require subsequent onboarding of the external party into the data space. | must | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §IV Extensions |
| `DSSC-PUB-35` | All four use cases (publication, update, removal, discovery of an offering) depend on the Data, Services and Offerings Descriptions building block. | informative | `explainer-use-cases-of-a-catalogue-and-discovery-service.md` §§I–IV Dependencies |
| `DSSC-PUB-36` | Offerings are deployed inside catalogues and represented using the `DCAT:Catalog` class and its properties. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-37` | DCAT needs to be extended using DCAT-AP for the use in a specific data space. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-38` | Access and usage control of offerings are expressed as ODRL policies. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-39` | In the context of the Dataspace Protocol, a catalogue is a collection of offerings published by a provider in the form of DCAT datasets and DCAT data services. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-40` | Each dataset may include information on the data service that enables access to it. | may | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-41` | A catalogue must include at least one data service that references the service providing these datasets. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-42` | A catalogue request returns the catalogue's content with references to all its entries. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-43` | A catalogue request may provide a filter option. | may | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-44` | A dataset request returns a specific entry of the catalogue. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-45` | A catalogue request returns an instance of `dcat:Catalog`, which points to the identifiers of its catalogue records via its `dcat:record` property rather than containing all the metadata of its entries. | must | `explainer-catalogues-in-the-dataspace-protocol.md` |
| `DSSC-PUB-46` | The decision for either a centralized or a decentralized catalogue should be made within the data space governance framework. | should | `explainer-centralized-vs-decentralized-catalogue-publication.md` §1 |

## Explainers and best practices

### Explainer: Use cases of a catalogue and discovery service

The Publication and Discovery building block has the following key functionalities:

- Publication of an offering
- Update of an offering
- Removal of an offering
- Discovery of an offering

Each of these functionalities is outlined as a use case in the tables below. Each use case specifies the trigger, its pre- and post-conditions, the main success scenario, and dependencies on other building blocks.

#### I. Publication of an Offering

| | |
|---|---|
| Primary Actor(s) | Data provider, catalogue |
| Trigger | A data provider wishes to publish an offering. |
| Pre-conditions | The data provider is a registered data space participant, can be authenticated as such, and is authorized to publish the offering in the catalogue. The data provider has one or more offering(s) available to publish. |
| Post-conditions | The data provider has added and published a new offering in the catalogue. Potential data consumers can discover the offering. If necessary, it could be made accessible only to a subset of data space participants (e.g., those participating in the use case that includes this specific dataset or service). The offering should be assigned a global unique resolvable persistent identifier (PID) to facilitate potential discovery from other data spaces. |
| Main Success Scenario | The data provider selects the offering(s) it wants to publish. The data provider publishes the offering(s) and access rules in the catalogue. The catalogue processes the publication of offering(s) and informs the data provider of the publication. |
| Extensions | 2a. The data provider is not authenticated and/or authorized. The catalogue denies publication of the offering(s). |
| Dependencies | Data, Services and Offerings Descriptions |

#### II. Update of an Offering

| | |
|---|---|
| Primary Actor(s) | Data provider, catalogue |
| Trigger | A data provider wishes to update an existing offering. |
| Pre-conditions | The data provider is a registered data space participant, can be authenticated as such and is authorized to modify the offering in the catalogue. The specific offering has previously been published in the catalogue. |
| Post-conditions | The data provider has updated the specific offering in the catalogue. |
| Main Success Scenario | The data provider selects the offering(s) that it wants to update. The data provider updates the offering(s) and access rules in the catalogue. The catalogue processes the updates of the offering(s) and informs the data provider of the update. |
| Extensions | 2a. The data provider is not authenticated and/or authorized. The catalogue denies the update of the offering. |
| Dependencies | Data, Services and Offerings Descriptions |

#### III. Removal of an Offering

| | |
|---|---|
| Primary Actor(s) | Data provider, catalogue |
| Trigger | A data provider wishes to remove an existing offering from the catalogue. |
| Pre-conditions | The data provider is a registered data space participant, can be authenticated as such and is authorized to modify the offering in the catalogue. The specific offering has previously been published in the catalogue. |
| Post-conditions | The data provider has removed an existing offering from the catalogue. The removed offering is no longer discoverable by data consumers. |
| Main Success Scenario | The data provider selects the offering(s) it wants to remove. The data provider removes the offering(s) and access rules in the catalogue. The catalogue processes the removal of the offering(s) and informs the data provider of the removal. |
| Extensions | 2a. The data provider is not authenticated and/or authorized. The catalogue denies the removal of the offering. |
| Dependencies | Data, Services and Offerings Descriptions |

#### IV. Discovery of an Offering

| | |
|---|---|
| Primary Actor(s) | Data consumer, catalogue |
| Trigger | A data consumer wishes to find offering(s) in the catalogue. |
| Pre-conditions | The data consumer is a registered data space participant. |
| Post-conditions | The catalogue provides the data consumer with a collection of relevant offerings. |
| Main Success Scenario | The data consumer sends a request to the catalogue that includes the parameters to search the offerings in the catalogue. The catalogue composes a collection of relevant offerings based on the request. The catalogue sends the resulting collection of offerings to the data consumer. |
| Extensions | 2a. The data consumer is not authenticated and/or authorized. The catalogue denies access to the offering(s) and does not collect relevant offerings based on the request. When an external party that is not a participant in the data space where this offering was initially published holds a global unique resolvable PID for the offering, that party may use a service to resolve this identifier to a metadata record. This may be the offering itself, if it was intended to be open, or a record directing to the catalogue entry of the offering that explains, in a machine-actionable manner, any further prerequisites that must be met. Access to the data or service itself would require subsequent onboarding of the external party into the data space. |
| Dependencies | Data, Services and Offerings Descriptions |

### Explainer: Catalogues in the Dataspace Protocol

The **Dataspace Protocol** (most recent **version 2025-1**) is a set of specifications for data sharing between entities within a data space. These specifications define the schemas and protocols that are required for these entities to negotiate agreements, access data, and publish and discover metadata.

The **Catalogue Protocol** is a specification of the Dataspace Protocol. It defines the specific protocols and schemas for publishing and discovering offerings, as well as how they are exchanged among dataspace participant agents. The Catalogue Protocol describes how:

- Offerings are deployed inside catalogues and represented using the `DCAT:Catalog` class and its properties, as described in Data, Services, and Offerings Descriptions. Note that DCAT needs to be extended using DCAT-AP for the use in a specific data space.
- Access and usage control of offerings are expressed as ODRL policies.

In the context of the Dataspace Protocol, a catalogue is a collection of offerings published by a provider in the form of DCAT **datasets** and DCAT **data services**. Each dataset may include information on the data service that enables access to it. Additionally, a catalogue **must** include at least one data service that references the service providing these datasets.

Figure 1 (upstream, not reproduced here) shows a schematic representation of two **Participant Agents** based on the Dataspace Protocol. The protocol covers each Participant Agent's control plane; the parts that relate to the Catalogue Protocol are highlighted. As shown in Figure 1, each Participant Agent has its own catalogue containing its offerings. It is important to note that the **Vocabulary Hub** is also highlighted, as it contains a catalogue of vocabularies (see Data Models) that can be accessed through the Catalogue Protocol.

The Catalogue Protocol enables the querying of a Participant Agent's catalogue. More specifically, it provides the protocols and messages necessary to read a catalogue. It also facilitates two types of requests, namely:

- **A catalogue request**, which returns the catalogue's content with references to all its entries and may provide a filter option.
- **A dataset request**, which returns a specific entry of the catalogue.

The Catalogue Protocol states that a catalogue request returns an instance of `dcat:Catalog`. However, this is not technically a deep data structure containing all the metadata of the catalogue's entries (see **DCAT version 3**); rather, it points to the identifiers of its catalogue records (i.e., what we refer to as "entries" here) via its `dcat:record` property.

**References cited by this explainer, verbatim:**

- Dataspace Protocol: `https://eclipse-dataspace-protocol-base.github.io/DataspaceProtocol/2025-1-err1/`
- Catalogue Protocol: `https://eclipse-dataspace-protocol-base.github.io/DataspaceProtocol/2025-1-err1/#catalog-protocol`
- DCAT dataset property: `https://www.w3.org/TR/vocab-dcat-3/#Property:catalog_dataset`
- DCAT Data Service class: `https://www.w3.org/TR/vocab-dcat-3/#Class:Data_Service`
- DCAT Catalog class (DCAT version 3): `https://www.w3.org/TR/vocab-dcat-3/#Class:Catalog`

### Explainer: Centralized vs. Decentralized catalogue publication

This explainer weighs trade-offs; apart from the statement that the decision should be made within the data space governance framework (`DSSC-PUB-46`), it is **non-normative**. It does not mandate either deployment model.

#### 1. Introduction

A catalogue may contain a centralized component or may be fully distributed, i.e., decentralized. In a decentralized catalogue, each **participant agent** contains its own catalogue, and a data consumer must query each catalogue individually. On the other hand, a data space may also incorporate a centralized publication and discovery component, such as the **metadata broker**, outlined in the **IDS-RAM 4**. The decision for either should be made within the data space governance framework. Some of the following considerations are relevant:

- A central catalogue may or could include all publicly available offerings (products that all data space participants can view). Depending on the use case, it could, for instance, be made accessible to external actors under certain conditions (not only to data space participants), thereby attracting more attention and new candidates for joining the data space.
- A distributed catalogue could be accessible only to participants. To access a provider's catalogue, a consumer must be aware of the data provider's existence and the access endpoint of its respective catalogue. This could be facilitated by a **data space registry**, which serves as a catalogue of data space participants and their participant agents.
- In a local catalogue, the data provider may restrict the visibility of offerings (or the whole catalogue) to a specific group of data participants and, consequently, prevent their agents from scraping the specific offerings (or whole catalogue).

Additionally, there are synchronization mechanisms to consider in case of a centralized catalogue implementation:

- **Pull**: a central catalogue component actively gathers metadata from each of the individual catalogues at each participant agent, using scraper/crawler mechanisms.
- **Push**: a data provider pushes its offerings to the central catalogue component.
- **Point-to-point dissemination**: the metadata is spread throughout the network and to each participant agent, e.g. by using a gossip protocol.

#### 2. Process Model

**2.1 Decentralized Catalogue Publication** — Figure 1 (upstream) illustrates how a data provider prepares an offering, adds it to a bundle, and then publishes it in its local catalogue. As a result, data consumers must consult several distinct catalogues in a data space, each of which is maintained by a data provider.

**2.2 Centralized Catalogue Publication** — A centralized catalogue incorporates a central component for the publication and discovery of offerings. Figure 2 (upstream) shows the swimlane diagram for publishing offerings to a central component or broker; that figure was partially adopted from the data offering section in the IDS-RAM 4. It is assumed here that the provider has already published one or more offerings in its local catalogue. The provider selects a broker to publish its offerings. Then, the broker receives the offerings and goes through the steps of validation, storage, and publication.

**2.3 Discovery of Offerings** — Figure 3 (upstream) illustrates the discovery of offerings. A potential consumer selects a catalogue and subsequently sends a query to it. The catalogue processes the query and returns the result. In the context of the dataspace protocol, and more specifically the catalogue protocol, the query sent to the catalogue is either a **catalogue request** (returning the contents of the catalogue with all its entries) or a **dataset request** (returning a specific entry).

#### 3. Considerations

Choosing between a centralized and decentralized catalogue in a data space is a governance decision that depends on, among others, visibility needs, participant trust, operational complexity, and interoperability goals. Centralized catalogues simplify discovery as they offer "a single point of access", while decentralized catalogues might offer tighter control for data providers, and distribution of responsibility. In addition, each model requires different synchronization and publication strategies. These trade-offs need to be weighted when designing a data space to select the approach that best supports the required use cases and ecosystem dynamics.

## Open questions

- **Descriptive mood vs. normative force.** The main page's §4 Specifications and the Catalogue Protocol explainer state protocol behaviour in the present indicative ("is used", "are expressed", "returns"), not with RFC 2119 modals. The single explicit modal is "a catalogue **must** include at least one data service" (`DSSC-PUB-41`). Rows `DSSC-PUB-08`, `DSSC-PUB-36`, `DSSC-PUB-38`, `DSSC-PUB-39`, `DSSC-PUB-42`, `DSSC-PUB-44` and `DSSC-PUB-45` are recorded as `must` because they describe unconditional behaviour of the protocol, but the source does not label them as such.
- **"Need to implement" in §2 Capabilities.** The source writes "Participants in data spaces need to implement the following capabilities", not "must". Rows `DSSC-PUB-01`–`DSSC-PUB-03` render this as `must`.
- **No endpoints or message type names.** The Catalogue Protocol explainer names only two request kinds in prose — "catalogue request" and "dataset request" — and does not give HTTP endpoint paths or protocol message type identifiers. Nothing further can be recorded without going outside the blueprint.
- **Inconsistent building-block name.** The main page links the building block as "Data, Services and Offerings" (§1) and "Data, Services and Offerings building block" (§3); the Catalogue Protocol explainer writes "Data, Services, and Offerings Descriptions" (Oxford comma); the use-case tables' Dependencies rows write "Data, Services and Offerings Descriptions". All three spellings occur upstream and are reproduced here as they appear in each context.
- **Typographical defects in the source.** §4: "the DCAT-AP based specification is used to as syntax to exchange" (stray "to"). §5: "This required capabilities can be implemented" (should read "These"). Both are rendered here in corrected form in prose and in the requirements table; the defect is recorded rather than silently smoothed.
- **Discovery pre-condition weaker than the extension.** Use case IV's pre-condition requires only that the data consumer be "a registered data space participant", while its extension 2a is triggered when the consumer "is not authenticated and/or authorized" — authentication and authorization are never stated as pre-conditions for discovery, unlike use cases I–III.
- **PID resolution service unspecified.** The use-case explainer says an external party holding a global unique resolvable PID "may use a service to resolve this identifier to a metadata record" but does not name, specify or assign ownership of that service, nor state a PID scheme.
- **Figures not reproduced.** The Catalogue Protocol explainer refers to Figure 1, and the centralized-vs-decentralized explainer to Figures 1–3 (swimlane diagrams). Their content beyond the accompanying prose is not available in the source text used here.
- **Vocabulary Hub link is to an archived page.** The Catalogue Protocol explainer's "Data Models" reference points at a page whose title is marked `_archived` upstream.
- **Missing DCAT-AP and ODRL versions.** Neither the main page nor the explainers state which DCAT-AP profile or which ODRL version applies, though both are named as required syntax within DSP.
