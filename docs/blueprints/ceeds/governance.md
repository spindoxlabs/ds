# CEEDS Governance

> **Source** · Blueprint of the Common European Energy Data Space (int:net), v3.0, September 2025 › 6. CEEDS Governance
> **Location** · pp. 66–70 (`Blueprint_CEEDS_v3.0.txt:2500-2708`)

The chapter, in its own words, "presents provides an overview of the governance frameworks and approaches employed by the EDSCP within their pilot projects for intra-dataspace governance. At the same time, identifying best practices and actionable insights that can be applied to the CEEDS initiative." (The doubled verb is in the source.) It is therefore predominantly a **survey of existing practice across the Energy Data Space Cluster Projects (EDSCP)**, not a normative specification: it establishes a vocabulary of governance building blocks taken from the DSSC Blueprint v2.0, then reports how five cluster projects have implemented access control and security, governance rules, and onboarding/offboarding agreements. Aspects of **inter**-data space governance, including interoperability governance, are explicitly deferred to Section 7.1.3 of the same blueprint.

## 6.1. Main Governance building blocks

Data space governance "aims to address fundamental questions about regulatory dynamics, decision-making authority, stakeholder participation, and accountability within a given data space." It is framed as a collective effort by relevant actors who share a common goal, focusing on determining how decisions are reached, who has the authority to make them, and how they are communicated and enforced. Governance of an *energy* data space involves establishing a comprehensive framework that dictates how data is managed, accessed, and utilized within the energy sector.

The chapter grounds the need for governance in the energy domain specifically: the new paradigms in the management of energy flows (e.g., associated with the active roles of **DER**, **e-mobility**, **flexibility solutions**) are favouring unprecedented interactions among stakeholders, "detailed based on the **HEMRM**", and consequently new streams for data exchange "according to **SGAM**". Foremost importance is assigned to identifying these necessary interactions (i.e., the stakeholders to be involved) while equipping the data spaces with systems that respect policies and regulations as well as fostering the development and adoption of new services for reliable energy systems.

### The four governance layers

The governance framework of data spaces is divided into four distinct layers (cited to the OPEN DEI State of the Art report, reference [4]):

- **Common European framework for data ecosystem**: private-public data governance (e.g., **Data Act** or **Data Innovation Board**);
- **Domain-specific building blocks governance**: inter-data spaces governance;
- **Data space governance**: intra-data space governance;
- **Governance of a soft infrastructure**: operational level of data space to provide essential services.

This framework "encompasses a range of policies, procedures, and technologies designed to ensure the data space operates securely, efficiently, and in compliance with regulatory standards." It **may** entail the identification of stakeholders and the definition of their roles, data management policies (classification, lifecycle etc.), access control and security aspects (authentication / authorization), data sharing agreements and governance bodies.

### Governance building blocks

Within the context of intra-data space governance, the chapter states that the **DSSC blueprint v2.0** deepens the organizational and business building blocks, reaching the definition of the following **governance building blocks** (reference [5]):

**Organisational Form and Governance Authority.** Governance in a data space is multi-faceted and encompasses various key decisions. Examples of these key decision points given by the source include the scope of the data space, the position the data space initiative wishes to take in the ecosystem, openness concerning entering participants, the support it wishes to arrange for its participants, or the principles it wishes to implement (e.g. democratic). "The specific choices made will differ between data spaces, but they **should** aim to promote collaborative, multi-stakeholder governance for effective data space operation."

Data Spaces can be categorized as either **unincorporated** (lacking legal personality) or **incorporated** (possessing legal personality). For the Common European Data Space, such as CEEDS, the DSSC Blueprint v2.0 offers several examples of the legal forms that a data space **may** adopt:

| Legal form | Characterisation given by the source |
|---|---|
| European Digital Infrastructure Consortium | a special legal form created for Common European Data Spaces and special multi-country projects |
| European Company | a for-profit legal entity, similar to the limited liability company |
| European Cooperative Society | a non-profit with characteristics of a cooperative and public limited company |
| European Economic Interest Grouping | a non-profit legal entity similar to a partnership |

> **Ambiguous:** the source presents these as *examples* offered by the DSSC Blueprint v2.0, not as a closed list, and gives no article-level citation for any of the four instruments that create these legal forms.

**Participation Management.** "The participation management building block outlines the operational processes that are implemented through the technical building blocks. It concerns how data transactions are facilitated within the data space." As a part of the data space governance framework, a **governance authority can mandate** rules and standards for the **security, performance, interoperability and observability** of data transactions. "Clear data-sharing rules are essential for building trust between data space participants and directly reflect the functionality of the data space."

## 6.2. EDSCP Implementations

The section introduction repeats the closing sentence of 6.1 verbatim: "In the following sections, the implementation of peculiar elements (i.e., access control and security, governance rules and data sharing agreements) in the EDSCP will be presented."

### 6.2.1. Access control and security

"Identity management is a critical component in the governance of an energy data space, which ensures that data access and usage are controlled, secure, and compliant with regulatory requirements."

As described in Section 5.2 of the blueprint, **five cluster projects — Data Cellar, SYNERGIES, OMEGA-X, ENERSHARE and EDDIE —** have implemented identity management systems using various approaches and technologies. Despite differences in their methods, all aim to ensure security, authentication, and interoperability of identities, whether for individual users or organizations. The primary focus is on managing digital identities to secure data and facilitate integration with other components and services.

Common ground reported across the projects:

- In the area of security and authentication, **all projects utilize certificates or similar mechanisms** to ensure secure communication between entities.
- **Decentralized Identifiers (DID)** and **Verifiable Credentials (VC)** are commonly used, and the implementing solutions are based on established standards (e.g., **W3C, OpenID, SAML, OAuth**).

Per-project implementations, as the source reports them:

| Project | Reported implementation |
|---|---|
| **Omega-X** and **ENERSHARE** | For managing dynamic, secure identities and ensuring the authenticity and integrity of interactions between connectors, both focus on creating an environment compatible with **IDSA** and **GAIA-X** trust frameworks. Both base the organizational identity management in the implementation of identity provider solution, **as defined by IDSA**, including a **Certificate Authority (CA)** and **Dynamic Attribute Provisioning Service (DAPS)**. "This combination contributes to the CEEDS System Use Case for onboarding and demonstrating decentralized identity solutions." |
| **Data Cellar** | A dedicated server is used to manage organizational identities and request **trust anchors** for credential signing "as per defined in GAIA-X framework". |
| **Data Cellar** and **OMEGA-X** | The identity management solution is based on **Self-Sovereign Identity (SSI)** principles, primarily utilizing **W3C Verifiable Credentials** and **Decentralized Identifiers (DID)**. |
| **ENERSHARE** | In its pilots, **"Keycloak"** is used for managing individual users' identities, integrating with marketplace services via **OpenID, SAML, and OAuth**. Additionally it has adopted the **Dataspace Protocol** for connector interoperability and **aims to** implement a participant wallet using **DID, OID4VP, and OID4VCI**. |
| **OMEGA-X** | The **Marketplace Federator** is in charge of managing user registrations and approvals, "inspired by Gaia-X specifications". |
| **SYNERGIES** | Utilizes a **"security, authentication & authorisation"** service responsible for identity and access management across the energy data space and related marketplaces. The service handles user and organizational lifecycle management, including registration, verification, and authentication. The solution includes **single sign-on** functionality which facilitates secure communication and authorization permissions across various SYNERGIES components. |
| **EDDIE** | Is utilising as far as possible European electronic Identification and Authentication Services (**eIDAS**), "not only for the authentication of data space participants, but also to close chains-of-trust with cloud-edge assets and distributed communication participants". Apart from the use of **eIDAS, eID and compliant certificate infrastructures**, it "highlights and promotes how the European way of identification and access management **should** be adopted throughout the whole value chain". Further information is in reference [6]. |

The section closes with a general argument for reuse of the existing European identity infrastructure:

> "Lastly, Identity management doesn't need to be created anew for data space environments, especially in a European context. Infrastructures regulated and deployed via electronic Identification and Authentication Services eIDAS [7] provide proven-in-use electronic IDs (eIDs), certification services, and with its 2024 amendments [8] adding the European Digital Identity Framework – even distributed identity wallets. The European federated authentication infrastructure is up and running for years in most Member States and is set to be a very important pillar in a Digital Single Market. With the possibility to share identification handles it serves as a linking pin between different within-sector data spaces as well as cross-sectorally."

### 6.2.2. Design and implementation of data space governance rules

Governance rules are presented as "another important aspect to guarantee interoperability across energy data space", covering the policies and rules designed to ensure the data space operates in compliance with regulatory standards on aspects such as **access control, risk mitigation and data sovereignty**. The source notes that different approaches can be distinguished within the different EDSCP.

All the cluster projects are designing a model focused on **fully preserving the rights of the data owner** and on the **facilitation of assurances for both the consumer and the producer of the data**. To this end, most projects include legal and ethical considerations in the design of their governance models:

- **Legal perspective**: the legislative frameworks include **data protection, cyber security and energy specific regulations**. (No instrument is named at this point in the chapter.)
- **Ethical perspective**: generally considered when utilizing an **ethics-by-design methodology**.

Two principles are stated as guiding the projects' actions:

1. "Creation of a governance model that enables data use and data access ensuring compliance with ethical, legal and financial requirements applicable to all stakeholders. This enables the effective exercise of available data rights, protect data autonomy, sovereignty, and human dignity as well as fundamental rights of individuals such as the right to privacy and freedom from discrimination."
2. "Implementation of legal agreements, which safeguard and ensure the respect of the governance model; additionally, compensation mechanisms and other adequate remedies are considered and activated in case of fundamental data rights violations."

On the rights of the **service providers**, these "are preserved by the contracts and compensations in the incentive schemes (financial and non-financial) that can be agreed beforehand with the tools provided by the data space."

**Governance body.** Regarding the implementation of the governance model, "the EDSCP foresees the creation of a body that exerts the powers both within the data space and with the affairs related to cross-data space issues." The source is explicit that this is unfinished work:

> "The role and functions of the governance authority are still under development, anyway a proposed approach corresponds to a general assembly of members supported by a management board. A federated model could also be adopted for the case of a cross-data space governance, where the positions and opinions of the different data spaces can be represented and considered."

### 6.2.3. Data sharing agreements

Despite its title, this section covers **governance rules for participant onboarding and offboarding**. "These are critical to the governance of data spaces to ensure the integrity, security, and compliance of the data ecosystem. Onboarding rules ensure that new participants meet data governance standards such as security, privacy, and regulatory compliance. Offboarding rules prevent ex-participants from accessing data and services post-exit." The practice from the different projects is then summarised.

**Onboarding agreements.** In most projects, the application and evaluation of the prospective participant is conducted by the **governance authority**. The sequence described is:

1. The applicant will express the data space's intended use.
2. The authority will check compliance with **legal and ethical standards** and its **technical capabilities** (capability to deploy software to provide/consume the data).
3. In the evaluation, the authority will clearly outline the **potential penalties and consequences for non-compliance** and **processes for addressing and rectifying compliance violations**.
4. Subsequently, "a secret and unique **API key** will be generated for the participant. This key allows communication with the data space services."

Some projects are working on a first draft version of the **terms and conditions** for getting involved in the data space. These will define:

- the **types of stakeholders** admissible for registration and the roles they can effectively undertake (e.g. data providers, data recipients);
- the **processes and technical means employed for licensing** applied over shared data;
- the **means employed for establishing data sharing agreements**, "stepping on formalized and legally binding data contracts".

**Offboarding agreements.** The offboarding process "represents the termination of the agreement". It includes **the notice of termination**, **data retrieval and deletion**, and **the revocation of access**.

- The notice of termination **can be either issued by the participant or the data space governance authority**.
- "Data retrieval **must** ensure that all participant data is securely deleted from the data space's systems to protect privacy and comply with data protection regulations."
- The revocation of access **includes a system audit** to ensure the revocation of the participant's access.

The chapter ends by pointing forward: "Section 7.1.3 will further discuss governance aspects in the energy domain and analysis of the interoperability requirements."

## Standards and protocols

The chapter names the following standards, protocols and trust frameworks. **No version or profile is given for any of them anywhere in the chapter.** All are named as what one or more cluster projects use or aim to use — i.e. reported practice, not a mandate on CEEDS.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| Decentralized Identifiers (DID) | not stated | "commonly used" across the projects; basis of SSI-based identity in Data Cellar and OMEGA-X; part of the planned ENERSHARE participant wallet | referenced |
| Verifiable Credentials (VC) | not stated | "commonly used" across the projects | referenced |
| W3C Verifiable Credentials | not stated | primary basis of the SSI identity solution in Data Cellar and OMEGA-X | referenced |
| W3C | not stated | named as one of the "established standards" the implementing solutions are based on | referenced |
| OpenID | not stated | named as an established standard; ENERSHARE Keycloak integration with marketplace services | referenced |
| SAML | not stated | named as an established standard; ENERSHARE Keycloak integration with marketplace services | referenced |
| OAuth | not stated | named as an established standard; ENERSHARE Keycloak integration with marketplace services | referenced |
| OID4VP | not stated | intended ENERSHARE participant wallet | referenced |
| OID4VCI | not stated | intended ENERSHARE participant wallet | referenced |
| Dataspace Protocol | not stated | adopted by ENERSHARE for connector interoperability | referenced |
| IDSA trust framework | not stated | Omega-X and ENERSHARE target compatibility; IDSA also "defines" the identity provider solution (CA + DAPS) both projects implement | referenced |
| GAIA-X trust framework | not stated | Omega-X and ENERSHARE target compatibility; Data Cellar requests trust anchors "as per defined in GAIA-X framework"; OMEGA-X Marketplace Federator "inspired by Gaia-X specifications" | referenced |
| Self-Sovereign Identity (SSI) principles | not stated | basis of the Data Cellar and OMEGA-X identity management solution | referenced |
| eIDAS / eID | 2014 regulation plus 2024 amendments | EDDIE authentication of data space participants and chains-of-trust; argued as the reusable European base for data space identity | referenced |
| HEMRM (Harmonised Electricity Market Role Model) | not stated | the basis on which the stakeholder interactions driving governance are "detailed" | referenced |
| SGAM (Smart Grid Architecture Model) | not stated | the model according to which the new data exchange streams arise | referenced |

**Named tool (illustration, not a standard):** "Keycloak" — used in ENERSHARE pilots for managing individual users' identities.

### Legal instruments and frameworks named

The chapter names the following instruments and bodies. Citations are given exactly as the blueprint's own reference list writes them (including its unbalanced quotation marks); the chapter body itself gives **no article numbers**.

| Instrument / body | As cited in the chapter | Full citation in the blueprint's reference list |
|---|---|---|
| Data Act | "e.g., Data Act or Data Innovation Board" (example of Common European framework for data ecosystem, private-public data governance) | not cited; no reference number, no article |
| Data Innovation Board | "e.g., Data Act or Data Innovation Board" | not cited; no reference number, no article |
| eIDAS | "electronic Identification and Authentication Services eIDAS [7]" | [7] "Regulation 910/2014 on 'electronic Identification and Authentication Services.'" 2014. `https://eur-lex.europa.eu/eli/reg/2014/910/oj/eng` |
| European Digital Identity Framework | "its 2024 amendments [8] adding the European Digital Identity Framework" | [8] "Regulation amending Regulation (EU) 910/2014 adding the 'European Digital Identity Framework.'" 1183 2024. `https://eur-lex.europa.eu/eli/reg/2024/1183/oj/eng` |
| DSSC Blueprint v2.0 | "the DSSC blueprint v2.0 deepens the organizational and business building blocks" [5] | [5] "Data Spaces Blueprint v2.0 - Home - Blueprint v2.0 - Data Spaces Support Centre." Accessed: Mar. 28, 2025. |
| OPEN DEI State of the Art | source of the four-layer governance framework, "cf. [4]" | [4] "OPEN DEI - State of the Art." Accessed: Sept. 14, 2025. |
| EDDIE, *Identification and Authentication in a Common Energy Data Space* | "Further information on the EDDIE approach can be found in [6]." | [6] EDDIE Project, *Identification and Authentication in a Common Energy Data Space"*. Project EDDIE, 2024. |

**Named governance bodies and roles in the chapter:** governance authority · general assembly of members · management board · Certificate Authority (CA) · Dynamic Attribute Provisioning Service (DAPS) · Marketplace Federator (OMEGA-X) · trust anchors (Data Cellar / GAIA-X).

> **Ambiguous:** the chapter names no regulator (NRA, ACER), no market operator role (TSO, DSO, BRP), and no network code. Governance in this chapter is data-space governance, not energy-market governance; the energy-domain governance analysis is deferred to Section 7.1.3.

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Most of this chapter is descriptive: it reports what the EDSCP have built or intend to build, and describes an intended future arrangement in the present or future tense. Those rows carry force `informative` and must not be read as mandates on a CEEDS implementation. The chapter contains exactly **one** explicit `must` (`CEEDS-GOV-39`) and **one** explicit `should` addressed to data spaces generally (`CEEDS-GOV-04`).

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-GOV-01` | The governance framework of data spaces is divided into four distinct layers: Common European framework for data ecosystem (private-public data governance); Domain-specific building blocks governance (inter-data spaces governance); Data space governance (intra-data space governance); Governance of a soft infrastructure (operational level of data space to provide essential services). | informative | `Blueprint_CEEDS_v3.0.txt:2521-2527` |
| `CEEDS-GOV-02` | Governance of an energy data space involves establishing a comprehensive framework that dictates how data is managed, accessed, and utilized within the energy sector. | informative | `Blueprint_CEEDS_v3.0.txt:2512-2513` |
| `CEEDS-GOV-03` | The governance framework may entail the identification of stakeholders and the definition of their roles, data management policies (classification, lifecycle etc.), access control and security aspects (authentication / authorization), data sharing agreements and governance bodies. | may | `Blueprint_CEEDS_v3.0.txt:2529-2533` |
| `CEEDS-GOV-04` | The specific governance choices made will differ between data spaces, but they should aim to promote collaborative, multi-stakeholder governance for effective data space operation. | should | `Blueprint_CEEDS_v3.0.txt:2545-2547` |
| `CEEDS-GOV-05` | Data Spaces can be categorized as either unincorporated (lacking legal personality) or incorporated (possessing legal personality). | may | `Blueprint_CEEDS_v3.0.txt:2547-2549` |
| `CEEDS-GOV-06` | A Common European Data Space such as CEEDS may adopt one of the legal forms exemplified by the DSSC Blueprint v2.0: European Digital Infrastructure Consortium, European Company, European Cooperative Society, or European Economic Interest Grouping. | may | `Blueprint_CEEDS_v3.0.txt:2549-2556` |
| `CEEDS-GOV-07` | The Participation Management building block outlines the operational processes that are implemented through the technical building blocks, and concerns how data transactions are facilitated within the data space. | informative | `Blueprint_CEEDS_v3.0.txt:2557-2559` |
| `CEEDS-GOV-08` | As part of the data space governance framework, a governance authority can mandate rules and standards for the security, performance, interoperability and observability of data transactions. | may | `Blueprint_CEEDS_v3.0.txt:2559-2561` |
| `CEEDS-GOV-09` | Clear data-sharing rules are essential for building trust between data space participants and directly reflect the functionality of the data space. | informative | `Blueprint_CEEDS_v3.0.txt:2561-2563` |
| `CEEDS-GOV-10` | Identity management is a critical component in the governance of an energy data space, ensuring that data access and usage are controlled, secure, and compliant with regulatory requirements. | informative | `Blueprint_CEEDS_v3.0.txt:2578-2579` |
| `CEEDS-GOV-11` | In the area of security and authentication, all cluster projects utilize certificates or similar mechanisms to ensure secure communication between entities. | informative | `Blueprint_CEEDS_v3.0.txt:2591-2592` |
| `CEEDS-GOV-12` | Decentralized Identifiers (DID) and Verifiable Credentials (VC) are commonly used, and the implementing solutions are based on established standards (e.g., W3C, OpenID, SAML, OAuth). | informative | `Blueprint_CEEDS_v3.0.txt:2592-2594` |
| `CEEDS-GOV-13` | Organizational identity management based on an identity provider solution as defined by IDSA, including a Certificate Authority (CA) and Dynamic Attribute Provisioning Service (DAPS), contributes to the CEEDS System Use Case for onboarding and demonstrating decentralized identity solutions. | informative | `Blueprint_CEEDS_v3.0.txt:2595-2601` |
| `CEEDS-GOV-14` | The European way of identification and access management should be adopted throughout the whole value chain. (Stated as what EDDIE "highlights and promotes", not as a CEEDS-level mandate.) | should | `Blueprint_CEEDS_v3.0.txt:2615-2620` |
| `CEEDS-GOV-15` | Identity management does not need to be created anew for data space environments, especially in a European context. | informative | `Blueprint_CEEDS_v3.0.txt:2621-2622` |
| `CEEDS-GOV-16` | Infrastructures regulated and deployed via eIDAS provide proven-in-use electronic IDs (eIDs), certification services, and — with the 2024 amendments adding the European Digital Identity Framework — distributed identity wallets. | informative | `Blueprint_CEEDS_v3.0.txt:2622-2625` |
| `CEEDS-GOV-17` | With the possibility to share identification handles, the European federated authentication infrastructure serves as a linking pin between different within-sector data spaces as well as cross-sectorally. | informative | `Blueprint_CEEDS_v3.0.txt:2626-2628` |
| `CEEDS-GOV-18` | All the cluster projects are designing a governance model focused on fully preserving the rights of the data owner and on the facilitation of assurances for both the consumer and the producer of the data. | informative | `Blueprint_CEEDS_v3.0.txt:2640-2642` |
| `CEEDS-GOV-19` | From a legal perspective, the legislative frameworks applied to governance model design include data protection, cyber security and energy specific regulations. | informative | `Blueprint_CEEDS_v3.0.txt:2643-2644` |
| `CEEDS-GOV-20` | The ethical aspects of governance are generally considered when utilizing an ethics-by-design methodology. | informative | `Blueprint_CEEDS_v3.0.txt:2644-2646` |
| `CEEDS-GOV-21` | Guiding principle: creation of a governance model that enables data use and data access ensuring compliance with ethical, legal and financial requirements applicable to all stakeholders, enabling the effective exercise of available data rights and protecting data autonomy, sovereignty, human dignity and fundamental rights such as the right to privacy and freedom from discrimination. | informative | `Blueprint_CEEDS_v3.0.txt:2647-2650` |
| `CEEDS-GOV-22` | Guiding principle: implementation of legal agreements which safeguard and ensure the respect of the governance model; compensation mechanisms and other adequate remedies are considered and activated in case of fundamental data rights violations. | informative | `Blueprint_CEEDS_v3.0.txt:2651-2653` |
| `CEEDS-GOV-23` | The rights of service providers are preserved by the contracts and compensations in the incentive schemes (financial and non-financial) that can be agreed beforehand with the tools provided by the data space. | informative | `Blueprint_CEEDS_v3.0.txt:2654-2656` |
| `CEEDS-GOV-24` | The EDSCP foresees the creation of a body that exerts the powers both within the data space and with the affairs related to cross-data space issues. | informative | `Blueprint_CEEDS_v3.0.txt:2657-2659` |
| `CEEDS-GOV-25` | The role and functions of the governance authority are still under development; the proposed approach corresponds to a general assembly of members supported by a management board. | informative | `Blueprint_CEEDS_v3.0.txt:2659-2661` |
| `CEEDS-GOV-26` | A federated model could also be adopted for cross-data space governance, where the positions and opinions of the different data spaces can be represented and considered. | may | `Blueprint_CEEDS_v3.0.txt:2661-2662` |
| `CEEDS-GOV-27` | Onboarding rules ensure that new participants meet data governance standards such as security, privacy, and regulatory compliance. | informative | `Blueprint_CEEDS_v3.0.txt:2668-2670` |
| `CEEDS-GOV-28` | Offboarding rules prevent ex-participants from accessing data and services post-exit. | informative | `Blueprint_CEEDS_v3.0.txt:2671-2672` |
| `CEEDS-GOV-29` | In most projects, the application and evaluation of the prospective participant is conducted by the governance authority. | informative | `Blueprint_CEEDS_v3.0.txt:2678-2679` |
| `CEEDS-GOV-30` | The applicant will express the data space's intended use. | informative | `Blueprint_CEEDS_v3.0.txt:2679-2680` |
| `CEEDS-GOV-31` | The authority will check the applicant's compliance with legal and ethical standards and its technical capabilities (capability to deploy software to provide/consume the data). | informative | `Blueprint_CEEDS_v3.0.txt:2680-2682` |
| `CEEDS-GOV-32` | In the evaluation, the authority will clearly outline the potential penalties and consequences for non-compliance and processes for addressing and rectifying compliance violations. | informative | `Blueprint_CEEDS_v3.0.txt:2682-2684` |
| `CEEDS-GOV-33` | A secret and unique API key will be generated for the participant, allowing communication with the data space services. | informative | `Blueprint_CEEDS_v3.0.txt:2684-2685` |
| `CEEDS-GOV-34` | The terms and conditions will define the types of stakeholders admissible for registration and the roles they can effectively undertake (e.g. data providers, data recipients). | informative | `Blueprint_CEEDS_v3.0.txt:2687-2689` |
| `CEEDS-GOV-35` | The terms and conditions will define the processes and technical means employed for licensing applied over shared data. | informative | `Blueprint_CEEDS_v3.0.txt:2689-2691` |
| `CEEDS-GOV-36` | The terms and conditions will define the means employed for establishing data sharing agreements, stepping on formalized and legally binding data contracts. | informative | `Blueprint_CEEDS_v3.0.txt:2691-2692` |
| `CEEDS-GOV-37` | Offboarding represents the termination of the agreement and includes the notice of termination, data retrieval and deletion, and the revocation of access. | informative | `Blueprint_CEEDS_v3.0.txt:2694-2696` |
| `CEEDS-GOV-38` | The notice of termination can be issued either by the participant or by the data space governance authority. | may | `Blueprint_CEEDS_v3.0.txt:2696-2697` |
| `CEEDS-GOV-39` | Data retrieval must ensure that all participant data is securely deleted from the data space's systems, to protect privacy and comply with data protection regulations. | must | `Blueprint_CEEDS_v3.0.txt:2697-2699` |
| `CEEDS-GOV-40` | The revocation of access includes a system audit to ensure the revocation of the participant's access. | informative | `Blueprint_CEEDS_v3.0.txt:2699-2700` |

## Open questions

- **Necessity is asserted with adjectives, not modals.** The chapter repeatedly says something "is essential" (`CEEDS-GOV-09`), "is a critical component" (`CEEDS-GOV-10`) or "are critical to" (onboarding/offboarding rules, `Blueprint_CEEDS_v3.0.txt:2668-2669`) without a modal verb. These are recorded here as `informative` because the source is characterising, not mandating. A reader wanting a normative reading of them has no textual basis for it in this chapter.

- **Section 6.2.3 is titled "Data sharing agreements" but covers onboarding and offboarding.** Its opening sentence is "Another relevant aspect to consider within the governance model of the CEEDS is the governance rules for participant onboarding and offboarding." Data sharing agreements appear only as one item that draft terms and conditions "will define". The title and the content do not match.

- **"Data retrieval must ensure that all participant data is securely deleted."** The single explicit `must` in the chapter (`CEEDS-GOV-39`) attaches the deletion obligation to *retrieval*. The sub-process was introduced two sentences earlier as "data retrieval and deletion", so the sentence appears to conflate the two; it is not clear whether retrieval-by-the-participant, deletion-by-the-data-space, or both are being mandated, nor what "securely deleted" requires.

- **Governance authority is described but not constituted.** The chapter states outright that "the role and functions of the governance authority are still under development", yet later sections assign it concrete operational duties (conducting applications and evaluations, outlining penalties, issuing notices of termination). Its powers, composition beyond "a general assembly of members supported by a management board", and appointment mechanism are all unspecified.

- **The legal-form list is not tied to its instruments.** European Digital Infrastructure Consortium, European Company, European Cooperative Society and European Economic Interest Grouping are named with one-line characterisations only. No regulation, directive or article number is given for any of them, and the list is presented as "several examples" rather than an exhaustive set.

- **Legislative frameworks are named only by category.** "Data protection, cyber security and energy specific regulations" (`CEEDS-GOV-19`) names no instrument. The GDPR, NIS2, the Data Governance Act and the energy network codes are all absent from this chapter, so nothing in it can be benchmarked against a specific legal obligation.

- **Data Act and Data Innovation Board appear only as parenthetical examples** of the outermost governance layer (`Blueprint_CEEDS_v3.0.txt:2522-2523`), with no statement of what either requires of, or does for, CEEDS.

- **The chapter's normative baseline is DSSC Blueprint v2.0, not v3.0.** The governance building blocks in 6.1 are taken from "the DSSC blueprint v2.0", accessed Mar. 28, 2025, while this CEEDS blueprint is v3.0 dated September 2025. Whether the v2.0 governance building-block definitions still hold in later DSSC versions is not addressed.

- **"API key" as the onboarding credential contradicts the identity approach of 6.2.1.** Onboarding concludes with "a secret and unique API key" (`CEEDS-GOV-33`), while 6.2.1 describes DID/VC, SSI, eIDAS and wallet-based credentials. The relationship between the two — whether the API key is an additional artefact, a project-specific practice, or a placeholder — is not explained.

- **Inconsistent naming within the chapter.** The same projects and frameworks are written differently in adjacent sentences: "Omega-X" and "OMEGA-X"; "GAIA-X framework" and "Gaia-X specifications". Names are reproduced above exactly as each occurrence writes them.

- **Editorial defects in the source text.** The chapter opener reads "This section presents provides an overview"; the sentence introducing the two guiding principles repeats its own tail — "two following principles are guiding the projects actions: following principles are guiding the projects actions:"; and the intro paragraph of 6.2 duplicates the closing paragraph of 6.1 word for word. These are reproduced or noted rather than silently corrected.

- **Forward references are load-bearing.** Inter-data space governance and interoperability governance — including anything resembling energy-market or regulator involvement — are deferred to Section 7.1.3 in both 6.1 and 6.2.3. This chapter alone does not describe CEEDS governance completely.
