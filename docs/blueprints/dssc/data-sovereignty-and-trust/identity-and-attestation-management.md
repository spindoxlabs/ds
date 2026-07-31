# Identity & Attestation Management

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Sovereignty and Trust › Identity & Attestation Management
> **Category** · Data Sovereignty and Trust

The objective of this building block is to enable secure and interoperable identity and attestation management. It provides the foundation for onboarding data space participants and supporting trusted exchanges in data spaces, so that identities can be reliably established and verified, attestations can be presented as verifiable evidence of qualification, and credentials can be exchanged and managed under the control of data space participants.

## Scope and objectives

The building block provides the foundation for onboarding data space participants and supporting trusted exchanges in data spaces by ensuring that:

- Identities of organisations, individuals, and services can be reliably established and verified.
- Data space participants can present and use attestations, such as membership credentials, as verifiable evidence of their qualification in the data space.
- Credentials can be exchanged and managed under the control of data space participants through secure protocols and credential stores.

The source states that these objectives "ensure transparent participation in the data space and give confidence that identities and attestations are managed in a consistent and verifiable way."

### Co-creation questions

Upstream §3 poses the following co-creation questions, which "apply when implementing this building block in your data space". They are questions to be answered by the data space, not requirements in themselves:

- Which types of identities need to be supported in your data space? And what are the conditions for their issuing? This can relate to the identity of organisations, individuals, and services or other digital assets.
- Which other types of attestations are needed? And what are the conditions for their issuance?

On the second question the source adds normative content: "As a minimum, this includes a data space membership credential. What is needed for obtaining such a credential? This is linked to the participation management building block. The data space membership credential provides proof that the entity adheres to the data space Rulebook. In addition to the data space membership credential, other types of attestations may be needed, for example, to prove compliance with policies related to data rights, consent, and security."

## Capabilities

"To achieve these objectives, every data space requires that the following capabilities are implemented and usable by data space participants":

- Issuance and validation of verifiable credentials covering identity, membership, and other relevant attestations.
- Data space participant-controlled credential stores for storing, exchanging, and presenting credentials securely.
- Secure credential exchange across participants and services.

"These capabilities allow data space participants to issue, store, and share credentials in a secure and controlled way."

### Functional dimensions

Upstream §4.1 sets out the functional dimensions covered by identity and attestation management in a data space:

- **Identity** — Identity attestations establish who or what an entity is within the data space. They apply to organisations, natural persons, and machines or services, and are issued by accredited trust service providers. They are attestations that include unique identifiers that identify the entity, such as company registration numbers, eIDAS-compliant digital credentials, or device identifiers. Proof of control is needed to ensure that only the legitimate holder can use the credential. Assurance levels need to be aligned with recognised KYC (Know Your Customer) and KYB (Know Your Business) practices.
  - **Organisations (legal identity)** — Legal entities are identified through recognised attributes such as company registration numbers, VAT IDs, or certificates of incorporation. This provides the foundation for accountability and traceability.
- **Natural persons** — Individuals interact within data spaces in roles such as legal representatives, data rights holders or end-users. Their identities can be established through government-issued digital credentials, eIDAS-regulated electronic identification and trust services, or other high-assurance schemes.
- **Machines and services** — Devices, applications, and automated agents also rely on secure identifiers and credentials to enable trusted interaction in the same way as organisations and individuals.
- **Data space membership** — Beyond identity, data spaces use credentials that confirm onboarding and demonstrate compliance with governance or sectoral requirements. These attestations make it possible to enforce the Data Space Rulebook and support trust in ongoing exchanges. Membership attestations are issued once compliance with the rules set by the data space has been verified as proof of a successful onboarding. They confirm that the entity is recognised as a data space participant under the Rulebook and entitled to interact in the data space. Membership attestations can also support federation, allowing recognition of data space participants across multiple data spaces.
- **Compliance with (other) policies** — Credentials can be needed to prove compliance with other policies, beyond data space membership. Compliance attestations demonstrate that a data space participant meets governance obligations or sector-specific regulations, such as energy market rules. They may be self-declared or certified by third parties, depending on the required level of assurance. These attestations are essential for maintaining trust over time and are subject to renewal, suspension, or revocation when conditions change.

> **Ambiguous:** In the source, "Organisations (legal identity)" is rendered as unbulleted prose immediately following the "Identity" bullet, while "Natural persons", "Machines and services", "Data space membership" and "Compliance with (other) policies" are peers at the top level. It is unclear whether the source intends "Organisations", "Natural persons" and "Machines and services" to be sub-dimensions of "Identity" (the "Identity" text names exactly those three categories) or peers of it. Rendered above as the source lays it out.

### Implementation

"To implement this building block, every data space requires a set of services."

As part of the **Federation services**, the data space needs:

- Trust services, responsible for issuing and verifying Verifiable Credentials, and supporting delegation of trust/rights, while interacting with lifecycle management mechanisms.

As part of the **Participant Agent services**, every data space participant also requires a **Credential Store**, which allows issuing, storing, managing, and presenting Verifiable Credentials under their own control, ensuring secure and private credential exchange. A common protocol for credential exchange — or compatible credential store implementations — must be used to ensure technical interoperability.

## Standards and protocols

Upstream §4.2 recommends the following. Names, spellings and versions below are reproduced exactly as the source writes them.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| W3C Verifiable Credentials | VC v2.0 (`https://www.w3.org/TR/vc-data-model-2.0/`) | Implement the attestations in a machine-readable format; "provides an interoperable model for expressing digital credentials" | recommended |
| W3C Decentralized Identifiers (DIDs) | `https://www.w3.org/TR/did-core/` — no version stated by the source | Implement globally unique and verifiable identifiers; "allow organisations, natural persons, and machines to be securely identified across domains" | recommended |
| OpenID for Verifiable Credentials (OIDC4VC) | `https://openid.net/sg/openid4vc/` — no version stated by the source | Credential exchange in data spaces; "extends OpenID Connect and OAuth2 flows, enabling secure and interoperable credential issuance and presentation in line with existing identity and access management practices" | recommended |
| Eclipse Dataspace Decentralized Claims Protocol | `https://projects.eclipse.org/projects/technology.dataspace-dcp/governance`; the best-practice sub-page links specification `v1.0.1` (`https://eclipse-dataspace-dcp.github.io/decentralized-claims-protocol/v1.0.1/`) | Credential exchange in data spaces; "developed under the Eclipse Dataspace Foundation, providing a governance-aware protocol overlay for exchanging and verifying claims without relying on centralised intermediaries" | recommended |

The two credential-exchange protocols are described by the source as "two complementary protocols".

The best-practice sub-page names the following further protocol components and specifications (see "Best practices on protocols for credential exchange" below):

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| OAuth 2.0 | 2.0 | OID4VC is "based on" OAuth 2.0; DCP is listed as `n/a` for this feature | referenced |
| SIOPv2 | not stated | OID4VC self-issuance protocol | referenced |
| Base Identity Protocol (BIP) | not stated | DCP self-issuance protocol | referenced |
| OID4VCi | not stated | OID4VC VC issuance protocol | referenced |
| Credential Issuance Protocol (CIP) | not stated | DCP VC issuance protocol | referenced |
| OID4VP | not stated | OID4VC VC presentation protocol | referenced |
| Verifiable Presentation Protocol (VPP) | not stated | DCP VC presentation protocol | referenced |
| Dataspace Protocol (DSP) | not stated | DCP is "targeted for use in conjunction with data transactions using the Dataspace Protocol (DSP)" | referenced |
| OpenID4VCI | not stated | Named in the interoperability statement: "Verifiable Credentials issued by DCP or OpenID4VCI are interoperable because they conform to W3C standards" | referenced |
| eIDAS Regulation / eIDAS 2 Regulation | not stated | eIDAS-compliant digital credentials and eIDAS-regulated electronic identification and trust services are named as means of establishing identity; both regulations are defined in the upstream glossary | referenced |
| ISO/IEC 17000:2020(en), *Conformity assessment — Vocabulary and general principles* | 2020(en) | Source of the conformity-assessment vocabulary in the upstream glossary | referenced |

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-IAM-01` | Identities of organisations, individuals, and services can be reliably established and verified. | informative | `identity-attestation-management.md` §1 |
| `DSSC-IAM-02` | Data space participants can present and use attestations, such as membership credentials, as verifiable evidence of their qualification in the data space. | informative | `identity-attestation-management.md` §1 |
| `DSSC-IAM-03` | Credentials can be exchanged and managed under the control of data space participants through secure protocols and credential stores. | informative | `identity-attestation-management.md` §1 |
| `DSSC-IAM-04` | Every data space requires that issuance of verifiable credentials covering identity, membership, and other relevant attestations is implemented and usable by data space participants. | must | `identity-attestation-management.md` §2 |
| `DSSC-IAM-05` | Every data space requires that validation of verifiable credentials covering identity, membership, and other relevant attestations is implemented and usable by data space participants. | must | `identity-attestation-management.md` §2 |
| `DSSC-IAM-06` | Every data space requires that data space participant-controlled credential stores for storing, exchanging, and presenting credentials securely are implemented and usable by data space participants. | must | `identity-attestation-management.md` §2 |
| `DSSC-IAM-07` | Every data space requires that secure credential exchange across participants and services is implemented and usable by data space participants. | must | `identity-attestation-management.md` §2 |
| `DSSC-IAM-08` | The attestations supported by a data space include, as a minimum, a data space membership credential. | must | `identity-attestation-management.md` §3 |
| `DSSC-IAM-09` | The data space membership credential provides proof that the entity adheres to the data space Rulebook. | informative | `identity-attestation-management.md` §3 |
| `DSSC-IAM-10` | Other types of attestations may be needed in addition to the data space membership credential, for example to prove compliance with policies related to data rights, consent, and security. | may | `identity-attestation-management.md` §3 |
| `DSSC-IAM-11` | Identity attestations include unique identifiers that identify the entity, such as company registration numbers, eIDAS-compliant digital credentials, or device identifiers. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-12` | Identity attestations are issued by accredited trust service providers. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-13` | Proof of control is needed to ensure that only the legitimate holder can use the credential. | must | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-14` | Assurance levels need to be aligned with recognised KYC (Know Your Customer) and KYB (Know Your Business) practices. | must | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-15` | Legal entities are identified through recognised attributes such as company registration numbers, VAT IDs, or certificates of incorporation. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-16` | The identities of natural persons can be established through government-issued digital credentials, eIDAS-regulated electronic identification and trust services, or other high-assurance schemes. | may | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-17` | Devices, applications, and automated agents rely on secure identifiers and credentials to enable trusted interaction in the same way as organisations and individuals. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-18` | Membership attestations are issued once compliance with the rules set by the data space has been verified, as proof of a successful onboarding. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-19` | Membership attestations can also support federation, allowing recognition of data space participants across multiple data spaces. | may | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-20` | Compliance attestations may be self-declared or certified by third parties, depending on the required level of assurance. | may | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-21` | Compliance attestations are subject to renewal, suspension, or revocation when conditions change. | informative | `identity-attestation-management.md` §4.1 |
| `DSSC-IAM-22` | To implement the attestations in a machine-readable format, the DSSC recommends using the W3C Verifiable Credentials (VC v2.0) standard. | recommended | `identity-attestation-management.md` §4.2 |
| `DSSC-IAM-23` | To implement globally unique and verifiable identifiers, the DSSC recommends using W3C Decentralized Identifiers (DIDs). | recommended | `identity-attestation-management.md` §4.2 |
| `DSSC-IAM-24` | To implement credential exchange in data spaces, the DSSC recommends OpenID for Verifiable Credentials (OIDC4VC). | recommended | `identity-attestation-management.md` §4.2 |
| `DSSC-IAM-25` | To implement credential exchange in data spaces, the DSSC recommends the Eclipse Dataspace Decentralized Claims Protocol. | recommended | `identity-attestation-management.md` §4.2 |
| `DSSC-IAM-26` | As part of the Federation services, the data space needs Trust services responsible for issuing and verifying Verifiable Credentials. | must | `identity-attestation-management.md` §5 |
| `DSSC-IAM-27` | Trust services support delegation of trust/rights. | must | `identity-attestation-management.md` §5 |
| `DSSC-IAM-28` | Trust services interact with lifecycle management mechanisms. | must | `identity-attestation-management.md` §5 |
| `DSSC-IAM-29` | As part of the Participant Agent services, every data space participant requires a Credential Store which allows issuing, storing, managing, and presenting Verifiable Credentials under their own control. | must | `identity-attestation-management.md` §5 |
| `DSSC-IAM-30` | A common protocol for credential exchange — or compatible credential store implementations — must be used to ensure technical interoperability. | must | `identity-attestation-management.md` §5 |
| `DSSC-IAM-31` | Participants manage their Verifiable Credentials through credential stores (digital wallets), which support secure storage and presentation. | informative | `best-practices-on-protocols-for-credential-exchange.md` §1 |
| `DSSC-IAM-32` | The choice of which protocols to use depends on the specific use case and the issuers involved, and is typically defined at the data space design or governance level. | informative | `best-practices-on-protocols-for-credential-exchange.md` §1 |
| `DSSC-IAM-33` | Verifiable Credentials issued by DCP or OpenID4VCI are interoperable because they conform to W3C standards. | informative | `best-practices-on-protocols-for-credential-exchange.md` §1 |

## Explainers and best practices

Upstream §6 "Further reading" lists one sub-page: *Best practices on protocols for credential exchange*.

### Best practices on protocols for credential exchange

> Upstream path · Technical Building Blocks › Data Sovereignty and Trust › Identity & Attestation Management › Best practices on protocols for credential exchange

#### 1. Protocols for credential exchange

Protocols for credential exchange define how verifiable credentials are issued, presented, and verified between parties. They are a key enabler for secure interactions where credentials need to be shared in a controlled and interoperable manner.

Participants manage their Verifiable Credentials through credential stores (digital wallets), which support secure storage and presentation. Protocols like OID4VC or the Decentralized Claim Protocol (DCP) facilitate credential exchange, ensuring participants retain control over their credentials and over what data they share and with whom. Currently, two such protocol standards being developed in the respective standardisation organisations are OID4VC and DCP.

The DCP protocol is currently in the standardisation process at the Eclipse Dataspace Working Group (EDWG) (`https://dataspace.eclipse.org/`) and targeted for use in conjunction with data transactions using the Dataspace Protocol (DSP). OID4VC is standardised by the OpenID Foundation and targeted for more general service interactions. The choice of which protocols to use depends on the specific use case and the issuers involved, and is typically defined at the data space design or governance level. It is also important to note that Verifiable Credentials issued by DCP or OpenID4VCI are interoperable because they conform to W3C standards.

#### 2. OpenID for VC (OID4VC) and Decentralized Claim Protocol (DCP)

"The following table highlights key differences between OID4VC and DCP relevant for data space implementations." Reproduced verbatim, including the asterisks the source places on the asynchronous-issuance row (the source gives no footnote for them):

| Feature | OID4VC | DCP |
|---|---|---|
| Based on | OAuth 2.0 | n/a |
| Self-Issuance protocol | SIOPv2 | Base Identity Protocol (BIP) |
| VC issuance protocol | OID4VCi | Credential Issuance Protocol (CIP) |
| VC Presentation protocol | OID4VP | Verifiable Presentation Protocol (VPP) |
| Has asynchronous issuance | via polling* | via callback* |
| allows Human-to-Machine communications | Yes | No |
| allows Machine-to-Machine (or Service-to-Service) communications | Yes | Yes |
| Supported VC formats | agnostic | agnostic |
| Target domain | General trusted transactions in data spaces and digital ecosystems | Data Space trusted data transactions on top of DSP Protocol |

#### 3. Useful links

**OpenID for VC**

- `https://openid.net/sg/openid4vc/`
- `https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html`
- `https://openid.github.io/OpenID4VC_SecTrust/draft-oid4vc-security-and-trust.html`

**Eclipse Dataspace Decentralized Claims Protocol**

- `https://eclipse-dataspace-dcp.github.io/decentralized-claims-protocol/v1.0.1/`

## Glossary (upstream §7)

The building block page carries its own glossary. Definitions are reproduced as upstream gives them, including its citation style; they carry no requirement IDs.

| Term | Description |
|---|---|
| Data Space Governance Authority | The body of a particular data space, consisting of participants that are committed to the governance framework for the data space, and is responsible for developing, maintaining, operating and enforcing the governance framework. |
| Data Space service offering credential | A service description that follows the schemas defined by the Data Space Governance Authority and whose claims are validated by the Data Space Compliance Service. |
| Conformity Assessment | demonstration that specified requirements are fulfilled (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Conformity Assessment Scheme | set of rules and procedures that describe the objects of conformity assessment, identifies the specified requirements and provides the methodology for performing conformity assessment. (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles). |
| Object of conformity assessment | entity to which specified requirements apply (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Attestation | issue of a statement, based on a decision, that fulfilment of specified requirements has been demonstrated (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| First-party conformity assessment activity | conformity assessment activity that is performed by the person or organization that provides or that is the object of conformity assessment (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Second-party conformity assessment activity | conformity assessment activity that is performed by a person or organization that has a user interest in the object of conformity assessment (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Third-party conformity assessment activity | conformity assessment activity that is performed by a person or organization that is independent of the provider of the object of conformity assessment and has no user interest in the object (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Claim | an assertion made about a subject. (ref. Verifiable Credentials Data Model v2.0 (w3.org) |
| Subject | thing about which claims are made (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Conformity Assessment Body | A body that performs conformity assessment activities, excluding accreditation (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Accreditation | third-party attestation related to a conformity assessment body, conveying formal demonstration of its competence, impartiality and consistent operation in performing specific conformity assessment activities (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Validation | confirmation of plausibility for a specific intended use or application through the provision of objective evidence that specified requirements have been fulfilled (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Verification | confirmation of truthfulness through the provision of objective evidence that specified requirements have been fulfilled (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Declaration | first-party attestation (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Certification | third-party attestation related to an object of conformity assessment, with the exception of accreditation (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles) |
| Scope of attestation | range or characteristics of objects of conformity assessment covered by attestation. |
| Verifiable Credential | A verifiable credential is a tamper-evident credential that has authorship that can be cryptographically verified. Verifiable credentials can be used to build verifiable presentations, which can also be cryptographically verified (ref. `https://www.w3.org/TR/vc-data-model-2.0/#dfn-verifiable-credential`) |
| Credential schema | In the W3C Verifiable Credentials Data Model v2.0. the value of the "credentialSchema" property must be one or more data schemas that provide verifiers with enough information to determine whether the provided data conforms to the provided schema(s). (ref: `https://www.w3.org/TR/vc-data-model-2.0/#data-schemas`) |
| Verifiable Presentation | A tamper-evident presentation of information encoded in such a way that authorship of the data can be trusted after a process of cryptographic verification. Certain types of verifiable presentations might contain data that is synthesized from, but does not contain, the original verifiable credentials (for example, zero-knowledge proofs). (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Issuer | A role an entity can perform by asserting claims about one or more subjects, creating a verifiable credential from these claims, and transmitting the verifiable credential to a holder. (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Holder | A role an entity might perform by possessing one or more verifiable credentials and generating verifiable presentations from them. A holder is often, but not always, a subject of the verifiable credentials they are holding. Holders store their credentials in credential repositories. (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Verifier | A role an entity performs by receiving one or more verifiable credentials, optionally inside a verifiable presentation for processing. Other specifications might refer to this concept as a relying party. (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Credential Store | A service used to issue, store, manage, and present Verifiable Credentials. |
| Compliance Service | Service taking as input the Verifiable Credentials provided by the participants, checking them against the SHACL Shapes available in the Data Space Registry and performing other consistency checks based on rules in the data space conformity assessment scheme. |
| eIDAS Regulation | The EU Regulation on electronic identification and trust services for electronic transactions in the internal market |
| eIDAS 2 Regulation | It is an updated version of the original eIDAS regulation, which aims to further enhance trust and security in cross-border digital transactions with the EU. |
| European Digital Identification (EUDI) Wallet | The European Digital Identity Regulation introduces the concepts of EU Digital Identity Wallets. They are personal digital wallets that allow citizens to digitally identify themselves, store and manage identity data and official documents in electronic format. These documents may include a driving licence, medical prescriptions or education qualifications. |
| Verifiable ID | It refers to a type of Verifiable Credential that a natural person or legal entity can use to demonstrate who they are. This verifiableID can be used for Identification and Authentication. (ref. Verifiable Attestation for ID - EBSI Specifications - (`http://europa.eu/`)) |
| Identity | an Identity is composed of a unique Identifier, associated with an attribute or set of attributes that uniquely describe an entity within a given context and policies determining the roles, permissions, prohibitions, and duties of the entity in the data space |
| Membership Credential | credential issued by the Data Space Governance Authority after having assessed compliance of an entity to its rules. This credential attest participation in a data space. |

## Tools implementing this building block

The source lists the following as tools implementing this building block, each with the service category upstream assigns it. These are illustrations, not requirements; the descriptions are the source's own.

- **Sovity Connector Plugin: Data Space Federation** — *Value-Creation Services*. "The Sovity Connector Plugin: Data Space Federation is a component that enables the Sovity Connector to operate across multiple identity management systems and participate in a federated dataspace environment. In the standard configuration, connectors typically trust a single identity issuer responsible for validating the X.509 certificates used during connector-to-connector communication. The plugin extends this model by allowing connectors to trust multiple certificate issuers resulting in connectors being able to authenticate and interact with Sovity connectors from different dataspaces with different identity providers. Conceptually, the plugin extends the identity management model from a simple user-based structure (e.g., user 1, user 2) to a more expressive user-and-group-based structure (e.g., user 1 belonging to dataspace A, user 1 belonging to dataspace B)."
- **NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V.** — *Trust Service*. "NoodleBar & Keyper are a complete, production-ready and modular dataspace trust service stack aligned with the DSSC Blueprint. NoodleBar provides three integrated layers: Identity (authentication for every machine and human in the dataspace), Participant Registry (participant lifecycle management, verification, onboarding, and catalogue), and Access & Authorization (real-time policy enforcement and audit logging). Keyper adds Personal Consent & Delegation Management, enabling data owners to actively control who accesses their data. The stack is compliance by design, supporting European data rules and requirements. Framework-agnostic by architecture, NoodleBar dataspace solution has been deployed in production across energy, logistics, and construction sectors."
- **Ocean Enterprise Provider** — *Participant Agent Services*. "The Ocean Enterprise Provider, alternatively named the 'Connector' or 'Access Controller' is a REST API specifically designed for the provisioning of data services. The access controller acts as an intermediary between the data source/data product provider and the user/data product consumer, thus preventing the need for the data product consumer to have direct access to the data product. Before granting access to a resource it performs a series of checks to verify the users permission to access a service, such as a data product contract opt-in, the identity of the data product consumer, successful payment, and access policies. The Ocean Enterprise Provider supports integrity checks, the transfer of data, the orchestration of Compute-to-Data, and the forwarding to service offerings to support 'Everything as a Service'."
- **Nautilus Participant Agent** — *Participant Agent Services*. "As a Data Space Participant Agent Nautilus for Ocean Enterprise provides Data Space Participants with the ability to publish, manage, discover, and consume data products and service offerings. It is a data economy toolkit and abstraction layer enabling programmatic interactions with the Ocean Enterprise Data Space Infrastructure and Components required by Participants."
- **Data Space Innovation Lab Connector** — *Participant Agent Services*. "IDSA complient certified IDS connector"
- **TNO Security Gateway (TSG)** — *Participant Agent Services*. "The TSG components allows you to participate in an IDS dataspace to exchange information with other organizations with data sovereignty in mind. You will be able to participate with the provided components as-is, but you're allowed to modify the components to create your own dataspace with specific use cases in mind."
- **FIWARE Data Space Framework (FDF)** — *Participant Agent Services*. "The FIWARE Data Space Framework FDF is an integrated suite of components implementing DSBA Technical Convergence recommendations, every organization participating in a data space should deploy to 'connect' to a data space."
- **Tekniker Dataspace Connector** — *Participant Agent Services*. "Modular solution that, deployed in any organization, allows to establish a single point of entry for multiple data sources either proprietary in the role of the Data Provider or available throughout the Data Space in the role of Data Consumer ensuring the interoperability of shared data, trust between the parties involved in data exchange and data sovereignty"
- **sovity EDC Community Edition (EDC CE)** — *Participant Agent Services*. "The sovity EDC Community Edition extends the Eclipse Dataspace Connector (EDC) with additional open-source enhancements, providing a ready-to-use solution for secure data exchange while ensuring data sovereignty."
- **Simpl-Open – Participant Agent** — *Participant Agent Services*. "Simpl is the open-source smart middleware that enables cloud-to-edge federations and all major data initiatives funded by the European Commission. Simpl-Open is a suite of integrated and modular components. This includes components for Participant Agent service. See the 'Purpose' section for a description of how Simpl-Open covers the service."

## Open questions

- **Protocol naming is inconsistent across the two source pages.** The building block page writes "OpenID for Verifiable Credentials (OIDC4VC)"; the best-practice sub-page writes "OpenID for VC (OID4VC)" throughout, and additionally "OpenID4VCI" in the interoperability statement while using "OID4VCi" in the comparison table. All four spellings are preserved above as the source uses them. It is not stated whether "OIDC4VC" and "OID4VC" are intended as the same name.
- **Protocol naming, DCP.** The building block page names the "Eclipse Dataspace Decentralized Claims Protocol"; the sub-page calls it the "Decentralized Claim Protocol (DCP)" (singular "Claim") and links a specification at `v1.0.1`. The building block page states no version for it.
- **No versions are given for most named standards.** Only W3C Verifiable Credentials carries a version (VC v2.0) in the source's recommendation text. W3C Decentralized Identifiers is cited by URL (`did-core`) without a version, and no **DID method** is named anywhere on either page. OIDC4VC/OID4VC is cited without a version or profile; the sub-page's "Useful links" points to `openid-4-verifiable-credential-issuance-1_0.html` and to a draft, `draft-oid4vc-security-and-trust.html`, but the source does not state that these are the recommended profiles.
- **Descriptive versus normative statements in §4.1.** Several statements in "Functional dimensions" are written in the declarative present ("Identity attestations … are issued by accredited trust service providers", "Membership attestations are issued once compliance … has been verified") without a modal verb. They have been recorded with force `informative` rather than promoted to `must`; the source does not make clear whether they are descriptions or obligations.
- **Structure of the "Functional dimensions" list** — see the ambiguity note under "Functional dimensions" above: "Organisations (legal identity)" is not formatted as a list item and its nesting relative to "Identity" is unclear.
- **Asterisks in the comparison table are unexplained.** "via polling\*" and "via callback\*" carry footnote markers with no corresponding footnote on the page.
- **Glossary terms not used on the page.** The §7 glossary defines "Data Space Registry", "SHACL Shapes" (inside the "Compliance Service" definition), "Data Space Compliance Service", "Data Space service offering credential", "European Digital Identification (EUDI) Wallet" and "Verifiable ID", none of which appear in §§1–6 of the building block page. The relationship between "Credential Store" (§5) and the "credential stores (digital wallets)" of the sub-page is also not stated explicitly.
- **The eIDAS references carry no article or instrument citation.** The source names the "eIDAS Regulation" and "eIDAS 2 Regulation" and speaks of "eIDAS-compliant digital credentials" and "eIDAS-regulated electronic identification and trust services" without citing a regulation number, date or article.
- **Cross-references given as site links.** §3 refers to "the participation management building block" and §5 links "Participant Agent services"; neither is given a document identifier beyond the site's own navigation.
- **Some upstream typographic artefacts were normalised.** §4.2 of the source contains stray asterisk runs (`****`) and uses `o` as a bullet marker for the two credential-exchange protocols; the sub-page is missing a space after "with whom." and "service interactions." Wording is unchanged; only these artefacts were regularised.
