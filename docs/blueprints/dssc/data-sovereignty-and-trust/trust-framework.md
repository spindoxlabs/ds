# Trust Framework

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Sovereignty and Trust › Trust Framework
> **Category** · Data Sovereignty and Trust

The objective of this building block is to enable trust to be established and maintained within a data space, accelerating trust decisions and supporting secure and trustworthy data exchange. It defines the core components of a trust framework, allowing the Data Space Governance Authority to translate governance rules into a practical trust framework that data space participants can rely on as a foundation for collaboration within and across data spaces.

## Scope and objectives

The building block defines the core components of a trust framework by ensuring that:

- Governance rules and conformity assessment processes are in place to operationalise trust according to the data space Rulebook.
- Trust anchors and trust services are recognised to validate, issue and verify credentials. Trust anchors are authoritative entities for which trust is assumed, while trust services are services acting on their behalf.

### General elements of a trust framework

A trust framework provides the methodology and technical specifications for collecting, organising, and verifying information to support trust decisions — that is, decisions about whether an entity, piece of information, or transaction can be trusted.

Every data space **should** have a **trust framework**, comprised of:

- **Compliance criteria**: criteria linked to regulatory, business, or technical requirements are detailed in the data space rulebook. The source's examples: UNECE vehicle regulations and ISO/SAE 21434 (mobility); GDPR and EHDS guidelines (health); AML/KYC obligations (finance); ISO 27001 or BSI C5 (industry).
- **Processes and technical means for validation**: this requires defining the format of claims, establishing mechanisms to collect them, and making the criteria machine-readable. It also involves semantic models and ontologies, and standards to validate, verify, exchange, and, if necessary, revoke or suspend attestations, including rights and trust delegation.
- **Accredited sources of trust**: the trust framework should contain a list of accredited entities (trust anchors and trust service providers). Different levels of trustworthiness can be defined by applying distinct sets of criteria or referencing different sources of trust.

### Roles ensuring trust

The following roles apply:

- **Trust anchors**: authoritative entities (e.g., governments) for which trust is assumed and not derived. They are accepted in relation to a specific scope of attestation and ensure the authenticity, integrity, security, and reliability of identities, data services and transactions within the data space.
- **Providers of trust services**: designated issuers deriving authority from trust anchors, providing certificates or attestations. Data spaces may accept as trust service providers Conformity Assessment Bodies (CABs), accredited to attest to conformity with established standards, codes of conduct, and regulations. It is also possible to include others, such as notaries: accredited when a trust service cannot directly sign a claim, they validate claims using objective evidence from trusted sources and convert non-machine-readable proofs (e.g. a signed contract) into machine-readable formats.

Note that for a single trust anchor, multiple trust services can be operated, while a single trust service can operate for multiple trust anchors.

### Conformity assessment workflow

The conformity assessment process ensures that participation in the data space is based on verifiable credentials aligned with the Rulebook. The source presents it in four main phases:

1. **Definition of the Rulebook and schemas**: the Data Space Governance Authority defines conformity schemas, including possible mandatory and optional requirements and assurance levels.
2. **Evidence gathering**: data space participants prepare the required declarations or certifications. Evidence may be self-declared, issued by accredited Conformity Assessment Bodies, or notarised when external proofs are converted into machine-readable credentials.
3. **Conformity assessment**: the data space participant aggregates evidence into a verifiable presentation. The Compliance Service, relying on the information maintained in the Registry Service, validates the claims against the Rulebook.
4. **Attestation issuance**: based on the conformity assessment result, the Data Space Governance Authority issues a signed attestation of compliance. The credential is then stored in the data space participant's credential store for onboarding or future transactions.

> **Gap:** the source states that "The ArchiMate diagram below provides an overview of the process, showing the main components across business, application, and technology layers", but the diagram itself is not part of the textual source and its content is therefore not reproduced here.

### Co-creation questions

The source poses two co-creation questions, whose answers "form the trust framework for a data space":

- Which processes need to be in place to verify and enforce compliance with the Rulebook? For each of the credentials identified in the Identity and Attestation management building block, processes need to be in place for their issuance — for instance, membership credentials and other conformity credentials that data space participants can use in their bilateral exchange. Processes can include, for instance, the signing of legal documents or automated verifications.
- For each process, how will the roles of trust anchors and trust services be implemented? Which trust anchors are recognised as core trusted entities in a data space? This can stem from legislation, contractual conditions or the generally accepted position of a certain entity in the data space. Furthermore, which trust services are available to implement their role in the digital world and issue credentials on their behalf?

## Capabilities

To achieve this objective, every data space requires the following capabilities:

- A Rulebook that defines governance requirements and supports automated conformity assessment.
- Compliance verification processes and services that operationalise conformity assessment and validate data space participants and services against the Rulebook.
- A listing of trust anchors and trust service providers (including revoked ones).

Ideally, the Rulebook and listing of trust anchors and trust service providers are made available in a machine-readable form, enabling a high degree of automation.

### Implementation services

To implement the trust framework, every data space requires the following services:

- **Trust services**: these services validate attestations and declarations submitted by data space participants against the conformity assessment criteria defined in the Rulebook. They can also perform conformity assessments by validating data space participant declarations and certifications against the conformity schema. These services combine organisational checks and automated verification processes, issuing results under the authority of the Data Space Governance Authority.
- **Credential stores** as part of the participant agent. This is used during the issuing, storage, sharing and verification of credentials.

## Standards and protocols

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| ISO/IEC 17000:2020 (Conformity assessment — Vocabulary and general principles) | 2020 | Common vocabulary and principles to define assurance levels and ensure consistency across data spaces; used to implement conformity assessment processes | recommended |
| ETSI TS 119 612 (Trusted Lists) | v2.1.1 (version given on the *Examples of trust services in European trust frameworks* sub-page) | Harmonised format for expressing and publishing trusted lists of qualified trust service providers and services, facilitating transparent and interoperable discovery of trust information based on eIDAS Trusted Lists; supports recognition of accredited trust entities | recommended |
| W3C SHACL (Shapes Constraint Language) | — | Expresses rules and constraints in a machine-readable format and supports automated validation of Verifiable Credentials and other claims against the Data Space Rulebook; enables automated compliance verification | recommended |
| Verifiable Credentials Data Model v2.0 (W3C) | 2.0 | Source of the glossary definitions for Claim, Evidence, Issuer and Verifiable Credential used by this building block | referenced |
| eIDAS 1.0 | first version of the regulation | Defines five core categories of qualified trust services (QES, QESeal, QWAC, QET, QERDS) | referenced |
| eIDAS 2.0 (European Digital Identity Framework) | [celex 32024R1183](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1183) | Introduces Electronic Attestations of Attributes, Electronic Ledgers, Electronic Archiving Services, ESCD requirements and the EUDI Wallet | referenced |
| Regulation (EU) No 910/2014 | — | Obliges each Member State to create and maintain a Trusted List; basis of the List of Trusted Lists (LOTL) | referenced |
| ISO 3166-2 | — | Code used in the illustrative compliance criteria to express the physical location of a Participant's headquarters and of its legal registration | referenced |
| ODRL | — | Format for the data license expressed in a Data Product Description in the illustrative compliance criteria | referenced |
| UNECE vehicle regulations | — | Example of compliance criteria (mobility) | referenced |
| ISO/SAE 21434 | — | Example of compliance criteria (mobility) | referenced |
| GDPR | — | Example of compliance criteria (health) | referenced |
| EHDS guidelines | — | Example of compliance criteria (health) | referenced |
| AML/KYC obligations | — | Example of compliance criteria (finance) | referenced |
| ISO 27001 | — | Example of compliance criteria (industry) | referenced |
| BSI C5 | — | Example of compliance criteria (industry); also named as a certification scheme with Assessment and Monitoring Bodies | referenced |
| CISPE | — | Named as a certification scheme with Assessment and Monitoring Bodies in the illustrative compliance criteria | referenced |
| EU Codes of Conducts | — | Named as a certification scheme with Assessment and Monitoring Bodies in the illustrative compliance criteria | referenced |
| CSA CCM | — | Named as a certification scheme with Assessment and Monitoring Bodies in the illustrative compliance criteria | referenced |
| SecNumCloud | — | Named as a certification scheme with Assessment and Monitoring Bodies in the illustrative compliance criteria | referenced |

Trusted data sources and APIs named by the source (all `referenced`, as examples): EU Trusted Lists (via the LOTL), European Commission APIs, EORI (European Commission API), LEI Code (Global Legal Entity Identifier (GLEIF) API), OpenCorporate API, VAT Information Exchange System (VIES) API, national registries providing legal entity numbers.

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Sources below are given as the upstream filename plus the section of the DSSC Blueprint v3.0 page. `trust-framework.md` sections are numbered as upstream numbers them; sub-page sections are named as upstream names them.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-TRF-01` | A data space requires a Rulebook that defines governance requirements. | must | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-02` | The Rulebook supports automated conformity assessment. | must | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-03` | A data space requires compliance verification processes and services that operationalise conformity assessment. | must | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-04` | Compliance verification processes and services validate data space participants and services against the Rulebook. | must | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-05` | A data space requires a listing of trust anchors and trust service providers, including revoked ones. | must | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-06` | The Rulebook is ideally made available in a machine-readable form, enabling a high degree of automation. | recommended | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-07` | The listing of trust anchors and trust service providers is ideally made available in a machine-readable form, enabling a high degree of automation. | recommended | `trust-framework.md` §2 Capabilities |
| `DSSC-TRF-08` | For each of the credentials identified in the Identity and Attestation management building block, processes need to be in place for their issuance. | must | `trust-framework.md` §3 Co-creation questions |
| `DSSC-TRF-09` | Every data space should have a trust framework. | should | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-10` | The trust framework comprises compliance criteria linked to regulatory, business, or technical requirements, detailed in the data space rulebook. | should | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-11` | The trust framework comprises processes and technical means for validation. | should | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-12` | Processes and technical means for validation require defining the format of claims. | must | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-13` | Processes and technical means for validation require establishing mechanisms to collect claims. | must | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-14` | Processes and technical means for validation require making the criteria machine-readable. | must | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-15` | Validation also involves semantic models and ontologies. | informative | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-16` | Validation also involves standards to validate, verify, exchange, and, if necessary, revoke or suspend attestations, including rights and trust delegation. | informative | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-17` | The trust framework should contain a list of accredited entities (trust anchors and trust service providers). | should | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-18` | Different levels of trustworthiness can be defined by applying distinct sets of criteria or referencing different sources of trust. | may | `trust-framework.md` §4.1 General elements of a trust framework |
| `DSSC-TRF-19` | Trust anchors are accepted in relation to a specific scope of attestation. | informative | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-20` | Trust anchors ensure the authenticity, integrity, security, and reliability of identities, data services and transactions within the data space. | informative | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-21` | Providers of trust services are designated issuers deriving authority from trust anchors, providing certificates or attestations. | informative | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-22` | Data spaces may accept as trust service providers Conformity Assessment Bodies (CABs), accredited to attest to conformity with established standards, codes of conduct, and regulations. | may | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-23` | Data spaces may include other providers of trust services, such as notaries, accredited when a trust service cannot directly sign a claim. | may | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-24` | Notaries validate claims using objective evidence from trusted sources and convert non-machine-readable proofs (e.g. a signed contract) into machine-readable formats. | informative | `trust-framework.md` §4.2 Roles ensuring trust |
| `DSSC-TRF-25` | For a single trust anchor, multiple trust services can be operated. | may | `trust-framework.md` §3 Co-creation questions |
| `DSSC-TRF-26` | A single trust service can operate for multiple trust anchors. | may | `trust-framework.md` §3 Co-creation questions |
| `DSSC-TRF-27` | The conformity assessment process ensures that participation in the data space is based on verifiable credentials aligned with the Rulebook. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-28` | The Data Space Governance Authority defines conformity schemas, including possible mandatory and optional requirements and assurance levels. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-29` | Data space participants prepare the required declarations or certifications as evidence. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-30` | Evidence may be self-declared, issued by accredited Conformity Assessment Bodies, or notarised when external proofs are converted into machine-readable credentials. | may | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-31` | The data space participant aggregates evidence into a verifiable presentation. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-32` | The Compliance Service validates the claims against the Rulebook, relying on the information maintained in the Registry Service. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-33` | Based on the conformity assessment result, the Data Space Governance Authority issues a signed attestation of compliance. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-34` | The credential is stored in the data space participant's credential store for onboarding or future transactions. | informative | `trust-framework.md` §4.3 Conformity assessment workflow |
| `DSSC-TRF-35` | To implement conformity assessment processes, the DSSC recommends using ISO/IEC 17000:2020 (Conformity assessment — Vocabulary and general principles). | recommended | `trust-framework.md` §4.4 Recommended technical standards |
| `DSSC-TRF-36` | To support recognition of accredited trust entities, the DSSC recommends using ETSI TS 119 612 (Trusted Lists). | recommended | `trust-framework.md` §4.4 Recommended technical standards |
| `DSSC-TRF-37` | To enable automated compliance verification, the DSSC recommends using W3C SHACL (Shapes Constraint Language). | recommended | `trust-framework.md` §4.4 Recommended technical standards |
| `DSSC-TRF-38` | Every data space requires trust services that validate attestations and declarations submitted by data space participants against the conformity assessment criteria defined in the Rulebook. | must | `trust-framework.md` §5 Implementation |
| `DSSC-TRF-39` | Trust services can also perform conformity assessments by validating data space participant declarations and certifications against the conformity schema. | may | `trust-framework.md` §5 Implementation |
| `DSSC-TRF-40` | Trust services combine organisational checks and automated verification processes, issuing results under the authority of the Data Space Governance Authority. | informative | `trust-framework.md` §5 Implementation |
| `DSSC-TRF-41` | Every data space requires credential stores as part of the participant agent, used during the issuing, storage, sharing and verification of credentials. | must | `trust-framework.md` §5 Implementation |
| `DSSC-TRF-42` | A data space can leverage — and, if necessary, modify — existing trust frameworks to define both governance and the associated technical and procedural components. | may | `use-and-extension-of-existing-trust-frameworks.md` (introduction) |
| `DSSC-TRF-43` | Existing frameworks can be extended by introducing more stringent requirements for the acceptance of trust anchors and trust service providers, thereby selecting a subset of those accepted in the trust framework which is extended. | may | `use-and-extension-of-existing-trust-frameworks.md` (introduction) |
| `DSSC-TRF-44` | Existing frameworks can be extended by adding additional rules into the rulebook, introducing more criteria for a specific credential type. | may | `use-and-extension-of-existing-trust-frameworks.md` (introduction) |
| `DSSC-TRF-45` | Existing frameworks can be extended by designating new, data-space-specific trust anchors and trust service providers for the new criteria. | may | `use-and-extension-of-existing-trust-frameworks.md` (introduction) |
| `DSSC-TRF-46` | Embracing common rules that can be further specialised with domain-specific requirements is essential for enhancing cross-data space interoperability. | informative | `use-and-extension-of-existing-trust-frameworks.md` § Cross-sectorial sets of rules: example from Gaia-X |
| `DSSC-TRF-47` | Data spaces can use cross-sectoral conformity schemes as a basis, extending them with additional requirements and corresponding assessment methods tailored to their specific needs. | may | `use-and-extension-of-existing-trust-frameworks.md` § Cross-sectorial sets of rules: example from Gaia-X |

No requirement rows are derived from *Examples of compliance criteria in trust frameworks* or *Examples of trust services in European trust frameworks*: the source labels both as examples/overviews, and the parent page attaches no normative obligation to them. Their content is rendered below as context.

## Explainers and best practices

### Examples of compliance criteria in trust frameworks

> The source states: "The following examples are illustrative and aim to show how compliance criteria, attributes, and trust sources can be combined and used in practice within a trust framework."

In this context, the term "Entity" in the first column refers to the organisation, participant, service, or data product for which a specific attribute or claim (third column) must be attested. The last column lists possible trust sources, a generic term encompassing Trusted Data Sources, Trust Anchors, Qualified Trust Service Providers, and Notaries that can validate the claim or issue the required evidence.

These examples illustrate how different types of entities can rely on recognised trust sources, including registry APIs, eIDAS trust services, certification bodies, or notary services, to prove compliance with governance and policy requirements within a data space.

| Entity | Criterion | Attribute/Claim | Possible Trust Sources |
|---|---|---|---|
| Participant (Legal Person - all roles) | The participant shall be uniquely identified. | Registration number of the legal person (typically issued by national bodies), which identifies one specific legal entity. | Trusted data sources: EORI (European Commission API) LEI Code (Global Legal Entity Identifier (GLEIF) API OpenCorporate API VAT Information Exchange System (VIES) API Notary services: Alternatively, notary services can be used. By providing more services and service level agreements, these services eventually also consult the trusted data sources quoted above. |
| Participant (Legal Person - all roles) | Proof of Data Space Membership is required | Data Space Membership Credential | Data Space Governance Authority |
| Participant (Legal Person - Provider) | The physical location of the Participant's headquarters shall be provided. | ISO 3166-2 code | eIDAS TSP (declaration) |
| Participant (Legal Person - Provider) | The physical location of the Participant's legal registration shall be provided | ISO 3166-2 code | eIDAS TSP (declaration) |
| Service | The Provider shall ensure there are provisions governing the rights of the parties to use the service and any Customer Data therein. | This criterion is attested through the following three attributes: LegallyBindingAct, CustomerDataProcessingTerms and CustomerDataAccessTerms | eIDAS TSP (declaration) Assessment and Monitoring Bodies for BSI C5, CISPE and EU Codes of Conducts, CSA CCM (certification) |
| Participant (Provider) | The Provider shall clearly define if and to what extent sub-processors will be involved, and the measures that are in place regarding sub-processors management. | If the attribute possiblePersonalDataTransfers is declared, then the DataTransfer attribute is also provided in the credential. | eIDAS TSP (declaration) Assessment and Monitoring Bodies for SecNumCloud, CISPE and EU Codes of Conducts (certification) |
| Participant (Data Provider) | The Data Provider shall have the legal authorization from the Data Producer to include the data in the Data Product | links to authorization documents which are signed through a data space-accredited Trust Service Provider. | Data Space Governance Authority |
| Data Product | For each Data Product, the Data Provider shall provide in the Data Product Description a Data License defining the usage policy in ODRL for all data in this Data Product. | The Data Product Description shall include a data license expressed as a valid ODRL document containing at least indication whether or not the data product contains licensed data. | eIDAS TSP (declaration) |

> **Note on normative force:** the criteria in the second and third columns are phrased with *shall*. That *shall* is internal to the illustrative criterion — it states how a data space might word its own Rulebook criterion — and the source does not impose these criteria on data spaces. They are reproduced verbatim and generate no requirement rows.

### Examples of trust services in European trust frameworks

The source provides "an overview of trust services commonly used in trust frameworks, with a particular focus on the European context."

#### Introduction to eIDAS trust services

The eIDAS regulatory framework is a key enabler of secure cross-border digital transactions. It establishes common rules for electronic identification, authentication and trust services, ensuring interoperability and legal certainty across the EU.

The first version of the regulation (**eIDAS 1.0**) defines five core categories of qualified trust services:

- **Qualified Electronic Seals (QESes)**: Similar to traditional business stamps, used to guarantee the origin and integrity of electronic documents.
- **Qualified Electronic Signatures (QESs)**: The electronic equivalent of handwritten signatures, with the same legal effect.
- **Qualified Website Authentication Certificates (QWACs)**: Certificates proving that a website is secure, authentic and trustworthy.
- **Qualified Electronic Time Stamps (QETs)**: Provide evidence that a document existed at a specific point in time.
- **Qualified Electronic Registered Delivery Services (QERDS)**: Provide proof of sending and receiving electronic data.

#### New Trust Services Introduced by eIDAS 2.0

The updated regulation ([eIDAS 2.0](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1183)), commonly referred to as the European Digital Identity Framework, expands the trust service landscape by introducing new categories:

- **Electronic Attestations of Attributes (EAA)**: Verifiable credentials representing attributes such as professional qualifications, legal capacities or educational degrees. They have the same legal effect as paper documents across the EU.
- **Electronic Ledgers**: Services enabling the storage of data in a tamper-evident manner, including technologies such as distributed ledgers and blockchain.
- **Electronic Archiving Services**: Ensure long-term preservation, integrity and legal admissibility of electronic documents.

In addition, eIDAS 2.0 further specifies requirements for **Electronic Signature/Seal Creation Devices (ESCDs).** These devices, hardware or software, are not trust services in themselves but qualified devices used to create qualified signatures and seals, including for remote signing.

#### The European Digital Identity Wallet (EUDI Wallet)

eIDAS 2.0 introduces [European Digital Identity Wallets](https://ec.europa.eu/digital-building-blocks/sites/display/EUDIGITALIDENTITYWALLET/Technical+Specifications) **(EUDI Wallets)**, secure mobile-based tools enabling individuals and organisations to:

- authenticate at a high level of assurance using a nationally issued identifier;
- store and present attestations of attributes, including qualified EAAs (QEAA);
- control when, how and to whom personal attributes are shared.

EUDI Wallets must be notified by Member States and must be accepted in specified use cases across the EU when a user voluntarily chooses to use them.

##### Privacy-preserving mechanisms

EUDI Wallets rely on technologies such as:

- Zero-Knowledge Proof (ZKP) methods, enabling users to prove a statement (e.g., "I am over 18") without disclosing the underlying data.

#### Qualified Electronic Attestations of Attributes (QEAA)

Qualified EAAs (QEAAs) are issued by **Qualified Trust Service Providers (QTSPs)**. QTSPs must provide:

- an interface for requesting and delivering QEAAs;
- mutual authentication with EUDI Wallets;
- where applicable, an interface to Authentic Sources for verifying attribute accuracy;
- a mechanism allowing third parties to check the validity status of a QEAA without accessing usage information.

#### EU Trusted Lists and the List of Trusted Lists (LOTL)

Under Regulation (EU) No 910/2014, each Member State must create and maintain a **Trusted List**, containing:

- the Trust Service Providers recognised by the national supervisory scheme;
- the qualified trust services they offer;
- the current status of each service;
- the status history of each service.

To support interoperability, the European Commission publishes the **List of Trusted Lists (LOTL)**, available in:

- a human-readable format, and
- XML for automatic processing.

Trusted Lists must be electronically signed or sealed.

#### Examples of Trusted Data Sources and APIs

Trusted sources that can be used to verify legal and natural persons include:

- EU Trusted Lists (via the LOTL)
- European Commission APIs
- VAT information exchange system (VIES) API
- Global Legal Entity Identifier (GLEIF) API
- National registries providing legal entity numbers (e.g., EORI)

Technical specifications for trusted lists are defined in [ETSI TS 119 612 v2.1.1](http://www.etsi.org/deliver/etsi_ts/119600_119699/119612/02.01.01_60/ts_119612v020101p.pdf).

#### Further Information

Additional information on the European Digital Identity Framework Regulation and its implementation can be found through official European Commission channels, including:

- Trusted Lists Browser
- eIDAS Trusted Lists Viewer

> **Note on normative force:** the *must* statements in this sub-page (EUDI Wallet notification and acceptance, QTSP obligations, Member State Trusted Lists, signing or sealing of Trusted Lists) are obligations placed by eIDAS on Member States, wallet providers and QTSPs. The source presents them as an overview of the European regulatory landscape, not as obligations on a data space, and they therefore generate no requirement rows for this building block.

### Use and extension of existing trust frameworks

A data space can leverage — and, if necessary, modify — existing trust frameworks to define both governance and the associated technical and procedural components. Generic trust frameworks, such as those provided by [Gaia-X](https://docs.gaia-x.eu/), iSHARE or [Ayra](https://ayra.forum/about/), can serve as foundational models. Additionally, frameworks developed for specific projects or initiatives, like [Catena-X](https://catena-x.net/en/1), [DOME](https://dome-project.eu/) or [Simpl-Open](https://simpl-programme.ec.europa.eu/book-page/simpl-open-architecture) of the European Commission, may also be (re-)used.

From a governance standpoint, these existing frameworks establish requirements and criteria for identities, authorisation, and other key elements governing interactions among data space participants, including data usage, processing, and the roles of intermediaries.

Moreover, established trust frameworks define processes and methods that integrate widely adopted technical standards to operationalise the validation and verification of compliance with the data space rulebook.

Existing frameworks can be extended by:

- Introducing more stringent requirements for the acceptance of trust anchors and trust service providers, thereby selecting a subset of those accepted in the trust framework which is extended;
- Adding additional rules into the rulebook by: Introducing more criteria for a specific credential type — for instance, imposing additional transparency requirements for participant onboarding.
- Designating new, data-space-specific trust anchors and trust service providers for the new criteria.

#### Cross-sectorial sets of rules: example from Gaia-X

Embracing common rules that can be further specialised with domain-specific requirements is essential for enhancing cross-data space interoperability. Gaia-X provides one mandatory conformity scheme (Gaia-X Standard Compliance) and three optional schemes (Gaia-X Labels, from Label 1 to Label 3). These cross-sectoral schemes reflect European values such as transparency, security, interoperability, portability, sustainability, and data protection, with additional requirements addressing European control in Gaia-X Label 2 and Label 3. Data spaces can use these schemes as a basis, extending them with additional requirements and corresponding assessment methods tailored to their specific needs.

#### References to existing Trust Frameworks

- "Gaia-X Trust Framework: Your Pathway to Trusted Digital Ecosystems"
- "An Introduction to the Gaia-X Trust Framework"
- Gaia-X Compliance Document 25.10
- iSHARE Trust Framework
- iSHARE Trust Framework - Framework and Roles
- TRAIN - Trust Management Infrastructure (fraunhofer.de)
- <https://eidas.ec.europa.eu/>
- Ayra Governance Framework

## Glossary

The source page carries its own glossary. It is reproduced verbatim; definitions are not requirements and carry no IDs.

| Term | Description |
|---|---|
| Data Space Governance Authority | The body of a particular data space, consisting of participants that are committed to the governance framework for the data space, and is responsible for developing, maintaining, operating and enforcing the governance framework. |
| Accreditation | Third-party attestation related to a conformity assessment body, conveying formal demonstration of its competence, impartiality and consistent operation in performing specific conformity assessment activities (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles ) |
| Accreditation body | Authoritative body that performs accreditation (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles ) |
| Attestation | Issue of a statement, based on a decision, that fulfilment of specified requirements has been demonstrated (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles ) |
| Claim | An assertion made about a subject. (ref. Verifiable Credentials Data Model v2.0 (w3.org) |
| Evidence | Evidence can be included by an issuer to provide the verifier with additional supporting information in a verifiable credential (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Issuer | A role an entity can perform by asserting claims about one or more subjects, creating a verifiable credential from these claims, and transmitting the verifiable credential to a holder. (ref. Verifiable Credentials Data Model v2.0 (w3.org) ) |
| Conformity Assessment Body | A body that performs conformity assessment activities, excluding accreditation (ref. ISO/IEC 17000:2020(en), Conformity assessment — Vocabulary and general principles ) |
| Trust Framework | A trust framework is comprised of: (business-related) policies, rules, and standards collected and documented in the rulebook. procedures for automation and implementation of the business-related components. |
| Trust Anchor | An entity for which trust is assumed and not derived. Each Trust Anchor is accepted by the data space governance authority in relation to a specific scope of attestation. |
| Trust Service Provider | Trust Service Providers (also referred to as Trusted Issuers) are legal or natural persons deriving their trust from one or more Trust Anchors and designated by the data space governance authority as parties eligible to issue attestations about specific objects. |
| Trusted Data Source | Source of the information used by the issuer to validate attestations. The data space defines the list of Trusted Data Sources for the Data Space Conformity Assessment Scheme/s. |
| Notary | Notaries are entities accredited by the Data Space, which perform validation based on objective evidence from a data space Trusted Data source, digitalising an assessment previously made. |
| LOTL (List of Trusted Lists) | List of qualified trust service providers in accordance with the eIDAS Regulation published by the Member States of the European Union and the European Economic Area (EU/EEA) |
| Verifiable Credential | A verifiable credential is a tamper-evident credential that has authorship that can be cryptographically verified. Verifiable credentials can be used to build verifiable presentations, which can also be cryptographically verified (ref. https://www.w3.org/TR/vc-data-model-2.0/#dfn-verifiable-credential ) |

## Open questions

> **Contradiction:** the page gives two different compositions of a trust framework. §4.1 says a trust framework is comprised of *compliance criteria*, *processes and technical means for validation*, and *accredited sources of trust*. The page glossary says a Trust Framework "is comprised of: (business-related) policies, rules, and standards collected and documented in the rulebook. procedures for automation and implementation of the business-related components." Neither is reconciled with the other, and the glossary entry's second sentence is also grammatically truncated in the source.

> **Ambiguous:** the source uses *trust service* and *provider of trust services* / *Trust Service Provider* interchangeably in places. §1 says "trust services are services acting on their behalf [of trust anchors]"; §4.2 titles the role "Providers of trust services"; §5 says "Trust services: These services validate attestations…"; the capability in §2 asks for "a listing of trust anchors and trust service providers". Whether the listing registers services, providers, or both is not stated.

> **Ambiguous:** §2 requires "A listing of trust anchors and trust service providers (including revoked ones)". It is not stated whether revoked entries must be held in the same listing, nor what "revoked" means for a trust anchor as opposed to a credential.

> **Ambiguous:** §4.1 requires "making the criteria machine-readable" while §2 says the Rulebook is "ideally" machine-readable. The relationship between the two — whether a machine-readable criteria set satisfies the machine-readable Rulebook capability, and whether the §4.1 statement is a hard requirement inside a `should` clause — is not resolved by the source.

> **Gap:** §4.3 introduces two named components, the **Compliance Service** and the **Registry Service**, which appear nowhere else on the page and are not defined in the page glossary. Their interfaces, ownership and relationship to the Trust services of §5 are not specified.

> **Gap:** the ArchiMate diagram referenced in §4.3 ("showing the main components across business, application, and technology layers") is not available in the textual source; the business/application/technology layer decomposition it is said to convey is therefore not captured here.

> **Gap:** §4.4 recommends ETSI TS 119 612 without a version; the *Examples of trust services in European trust frameworks* sub-page cites v2.1.1. W3C SHACL is recommended with no version or profile at all. ISO/IEC 17000:2020 is the only fully pinned recommendation.

> **Ambiguous:** the source names *trust source* as "a generic term encompassing Trusted Data Sources, Trust Anchors, Qualified Trust Service Providers, and Notaries", but only in the *Examples of compliance criteria in trust frameworks* sub-page. The main page uses "sources of trust" (§4.1, "Accredited sources of trust") without defining it, and neither term appears in the page glossary.

> **Ambiguous:** §3 refers to "the Identity and Attestation management building block", which is not the spelling upstream uses for that building block elsewhere. The reference is reproduced verbatim above.

> **Source formatting defect:** in *Use and extension of existing trust frameworks*, the second extension mechanism ("Adding additional rules into the rulebook by:") is followed in the source by an unindented, unbulleted sentence ("Introducing more criteria for a specific credential type…") and then by a third top-level bullet ("Designating new, data-space-specific trust anchors…"). Whether "Designating new…" is a sub-item of "Adding additional rules into the rulebook" or a third independent mechanism cannot be determined from the source. It is rendered here as a third independent mechanism (`DSSC-TRF-45`), which is the reading the source's own list nesting supports.

> **Source defect:** in *Use and extension of existing trust frameworks*, the reference to iSHARE is hyperlinked to the Trust Framework page itself (`?pane=technical&technical=trust-framework`) rather than to an iSHARE resource. The link has been dropped here rather than reproduced as a self-reference.

> **Source defect:** the "Privacy-preserving mechanisms" subsection of *Examples of trust services in European trust frameworks* introduces "technologies such as" and then lists a single technology (Zero-Knowledge Proof methods). The list appears truncated in the source.
