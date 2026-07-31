# Building on Top of Foundational Standards

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Building on Top of Foundational Standards
> **Framing section of the Technical Building Blocks pane — not a building block.**

Upstream places "Building on Top of Foundational Standards" in the Technical Building Blocks pane alongside the nine building blocks, but presents it as framing *for* those building blocks rather than as one of them: it opens with "Throughout the technical building blocks we refer to a number of common technical standards, which play a role in implementing several different technical capabilities. In this section we highlight those technical standards." It is a cross-reference layer — it collects the standards, specifications and protocols the building blocks rely on, and points back to the building blocks where each is used. It is therefore not a tenth building block, has no capabilities of its own, and carries no explainer or best-practice sub-pages.

## Scope and objectives

The section distinguishes three categories of standard:

- Harmonised standards for compliance with the Data Act.
- Key technical standards: "these are underlying technical standards which apply in any context."
- Protocols: "technical protocols which enable the key technical standards to work together."

**Data Act standards (§2).** It is foreseen through the Data Act (article 33) that standards will be provided to comply with the requirements of the Data Act; the blueprint states it already refers to these requirements. A standardisation process has started at CEN-CENELEC and ETSI to work on these standards, followed at CEN-CENELEC JTC 25 and ETSI TC DATA. Publication of the standards is expected in 2026. The DSSC has a liaison with the standardisation process and has contributed to it, to ensure close alignment with the DSSC Blueprint.

**Key technical standards (§3).** Underlying technical standards are needed to implement these formal specifications. §3 lists the "**minimum set** of technical standards and specifications data spaces need to adhere to" in order (a) to make them interoperable with other data spaces and (b) to allow them to capitalize on existing software implementations which, in many cases, also exist in the form of open-source software (OSS). The source gives four selection criteria for this set — these are rationale, not requirements:

- there exists overwhelming consensus to include them;
- many operational data spaces use these standards in a production environment (i.e., for exchanging live business or transaction data);
- in most cases the standards are used in the wider context of data sharing, even beyond data spaces;
- they can be used to cover requirements stemming from the formal standards and specifications for Data Act compliancy.

**Protocols (§4).** "There are many options when implementing the aforementioned technical standards. Various initiatives and technology developers are now working together to drive the work on establishing protocols that explain how these standards can be used in conjunction with each other." §4.3 notes that the projects listed there are still in the specification phase.

**Cross-references upstream declares.** Verifiable Credentials → the *Data sovereignty & trust* pillar; DCAT → the *Data, Services and Offerings Descriptions* and *Publication and Discovery* building blocks; ODRL → the *access and usage policies and enforcement* building block.

## Standards and protocols

Names, versions, profiles and organisations below are verbatim from the source, including its own spellings ("Open ID Foundation", "Eclipse Dataspace Working group"). Where the "Version / profile" cell cites a URL, the source's prose states no version and the version appears only in the specification the source links to — flagged as such rather than asserted as the source's own claim.

| Standard | Organisation | Version / profile | Role | Normative force |
|---|---|---|---|---|
| Data Act (article 33) | not stated (source links `https://eur-lex.europa.eu/eli/reg/2023/2854`) | article 33 | Foresees that standards will be provided to comply with the requirements of the Data Act | referenced |
| Trusted Data Transaction part 1: Terms and definitions | CEN-CENELEC / ETSI standardisation process | part 1 | Terms and definitions; the DSSC has contributed elements of the glossary, and the blueprint glossary is aligned with this work where possible | referenced |
| Trusted Data Transaction part 2: Trustworthiness requirements | CEN-CENELEC / ETSI standardisation process | part 2 | "will cover elements covered in the building blocks on sovereignty & trust" | referenced |
| Trusted Data Transaction part 3: Interoperability requirements | CEN-CENELEC / ETSI standardisation process | part 3 | "will cover elements relating to interoperability, primarily covered in the pillars on Data interoperabilty and Data Value Creation" | referenced |
| A data catalogue implementation framework, DCAT-AP | CEN-CENELEC / ETSI standardisation process | not stated | Data catalogue implementation framework, listed as a key deliverable of the Data Act standardisation process | referenced |
| Technical specifications for internal data governance, the management of semantic assets and the maturity framework for data spaces | CEN-CENELEC / ETSI standardisation process | not stated | Key deliverable; uses the DSSC Maturity Model as input | referenced |
| W3C Verifiable Credentials | World Wide Web Consortium (W3C) | not stated (source links `https://www.w3.org/TR/vc-overview/`) | Creation, sharing and verification of digital credentials; within a data space, issued for identification and for claims/attestations | required — one of the "minimum set … data spaces need to adhere to" (§3) |
| DCAT (Data Catalog Vocabulary) | World Wide Web Consortium (W3C) | version 3 (source links `https://www.w3.org/TR/vocab-dcat-3/`) | "provides the baseline metamodel for catalogues"; supports discoverability of datasets within a data space | required — one of the "minimum set … data spaces need to adhere to" (§3) |
| DCAT-AP | standardised through ETSI | not stated | "provides an implementation framework for DCAT. This needs to be used for data spaces" | required |
| ODRL (Open Digital Rights Language) / ODRL Information Model | World Wide Web Consortium (W3C) | not stated (source links `https://www.w3.org/TR/odrl-model/`) | Policy expression language; used within a data space to express access and usage policies to a dataset | required — one of the "minimum set … data spaces need to adhere to" (§3) |
| Dataspace Protocol (DSP) | Eclipse Dataspace Working group | 2025-1 (source links `https://eclipse-dataspace-protocol-base.github.io/DataspaceProtocol/2025-1/`) | Specifies availability of data products via DCAT Catalogs, usage control as ODRL Policies, syntax and electronic negotiation of Agreements, and dataset access via Transfer Process Protocols; specifies generic elements only | referenced |
| Technology Compatibility Kit (TCK) | Eclipse Dataspace Working Group (EDWG) | not stated | To be combined with the DSP specification document, under the Eclipse Specification Process, to test compliance of specific implementations of the Dataspace Protocol with the specification | referenced |
| ISO/IEC Joint Technical Committee 1 — Publicly Available Specification (PAS) | ISO/IEC | not stated | Route to which the Dataspace Protocol "will be submitted" | referenced |
| X.509 certificates, in combination with a DAPS-service | not stated (source links the International Data Spaces Association IDS-G repository) | not stated | "more traditional approaches for issuing credentials" on which some operational data spaces still rely | referenced |
| Open ID for Verifiable Credentials (OID4VC) | Open ID Foundation | "currently being standardized"; comprises OID4VCI, OID4VP and SIOPv2 | One of the two protocols "commonplace for the issuing and sharing of" verifiable credentials | referenced |
| OpenID for Verifiable Credential Issuance (OID4VCI) | Open ID Foundation | not stated | "defines an API and corresponding OAuth-based authorization mechanisms for issuance of Verifiable Credentials" | referenced |
| OpenID for Verifiable Presentations (OID4VP) | Open ID Foundation | not stated | "defines a mechanism on top of OAuth 2.0 to allow the presentation of claims in the form of Verifiable Credentials as part of the protocol flow" | referenced |
| Self-Issued OpenID Provider v2 (SIOPv2) | Open ID Foundation | v2 | "enables end users to use OpenID Providers that they control" | referenced |
| OAuth 2.0 | not stated | 2.0 | Underlies OID4VP; OAuth-based authorization mechanisms underlie OID4VCI | referenced |
| EUDI Wallet Architecture and Reference Framework | not stated (source links `https://eu-digital-identity-wallet.github.io/eudi-doc-architecture-and-reference-framework/1.1.0/arf/`) | 1.1.0 (from the linked URL) | Framework of which OID4VC is part | referenced |
| eIDAS2 | not stated | not stated | "With eIDAS2, every natural and legal person within the EU will be able to receive a digital identity stored in a suitable wallet (EUDI Wallet) by 2026." | referenced |
| Decentralized Claims Protocol (DCP) — Eclipse Dataspace Decentralized Claims Protocol | Eclipse | v1.0.1 (source links `https://eclipse-dataspace-dcp.github.io/decentralized-claims-protocol/v1.0.1/`) | "conveying organizational identities and establishing trust in a way that preserves privacy and limits the possibility of network disruption"; one of the two commonplace credential protocols | referenced |
| Eclipse Conformity Assessment Policy and Credential Profile | Eclipse; "mainly driven by contributors from Gaia-X" | in the specification phase | "aims to specify how compliance can be assessed and verified using verifiable credentials"; takes an ODRL policy specification and allows users to specify how compliance to that policy can be achieved using verifiable credentials | referenced |
| Eclipse Data Rights Policies Profile (DRP) | Eclipse; "initiated by iSHARE" | in the specification phase | "to provide a set of specifications designed to facilitate interoperable trust between entities that comply with requirements for trust frameworks and data spaces" | referenced |

Standardisation bodies and fora named in the section, for reference: CEN-CENELEC, ETSI, CEN-CENELEC JTC 25, ETSI TC DATA, World Wide Web Consortium (W3C), Eclipse Dataspace Working Group (EDWG), Open ID Foundation, ISO/IEC Joint Technical Committee 1, Gaia-X, iSHARE, International Data Spaces Association.

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

Much of this section is descriptive framing rather than obligation; rows marked `informative` record what the source states about a standard, not something a data space is required to do. Section numbers in the Source column are the source document's own headings.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-FND-01` | Standards provided under Data Act article 33 shall relate to the description of the dataset content, use restrictions, licences, data collection methodology, data quality and uncertainty (…) to allow the recipient to find, access and use the data. | must | `building-on-top-of-foundational-standards.md` §2 |
| `DSSC-FND-02` | Standards provided under Data Act article 33 shall relate to the description of the data structures, data formats, vocabularies, classification schemes, taxonomies and code lists. | must | `building-on-top-of-foundational-standards.md` §2 |
| `DSSC-FND-03` | Standards provided under Data Act article 33 shall relate to the description of the technical means to access the data, such as application programming interfaces, and their terms of use and quality of service (…) to enable automatic access and transmission of data between parties (…). | must | `building-on-top-of-foundational-standards.md` §2 |
| `DSSC-FND-04` | Where applicable, the means to enable the interoperability of tools for automating the execution of data sharing agreements, such as smart contracts, shall be provided. | must | `building-on-top-of-foundational-standards.md` §2 |
| `DSSC-FND-05` | Where possible, the glossary of this version of the blueprint is aligned with Trusted Data Transaction part 1: Terms and definitions. | informative | `building-on-top-of-foundational-standards.md` §2 |
| `DSSC-FND-06` | Data spaces need to adhere to the minimum set of technical standards and specifications listed in §3 (W3C Verifiable Credentials, DCAT/DCAT-AP, ODRL) in order to be interoperable with other data spaces. | must | `building-on-top-of-foundational-standards.md` §3 |
| `DSSC-FND-07` | Data spaces need to adhere to that same minimum set in order to capitalize on existing software implementations which, in many cases, also exist in the form of open-source software (OSS). | must | `building-on-top-of-foundational-standards.md` §3 |
| `DSSC-FND-08` | Within a data space, a Verifiable Credential can be issued for identification and to indicate that a participant or some element is compliant with something (a claim or attestation). | may | `building-on-top-of-foundational-standards.md` §3.1 |
| `DSSC-FND-09` | The W3C Verifiable Credentials data model allows for selective disclosure, so that the credential holder can choose to share only specific information from a credential or only certain credentials. | informative | `building-on-top-of-foundational-standards.md` §3.1 |
| `DSSC-FND-10` | The issuing, sharing and validation of claims is an essential element for establishing trust in a dataspace. | informative | `building-on-top-of-foundational-standards.md` §3.1 |
| `DSSC-FND-11` | DCAT version 3 by W3C provides the baseline metamodel for catalogues. | informative | `building-on-top-of-foundational-standards.md` §3.2 |
| `DSSC-FND-12` | DCAT-AP, which provides an implementation framework for DCAT, needs to be used for data spaces. | must | `building-on-top-of-foundational-standards.md` §3.2 |
| `DSSC-FND-13` | Further extensions of DCAT-AP are possible for specific data spaces, e.g. taking into account domain specific needs. | may | `building-on-top-of-foundational-standards.md` §3.2 |
| `DSSC-FND-14` | ODRL can be used within a data space to express access and usage policies to a dataset. | may | `building-on-top-of-foundational-standards.md` §3.3 |
| `DSSC-FND-15` | The Dataspace Protocol specifies how data products can be made available to other using DCAT Catalogs. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-16` | The Dataspace Protocol specifies how usage control is expressed as ODRL Policies. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-17` | The Dataspace Protocol specifies how Agreements that govern data usage are syntactically expressed and electronically negotiated between data providers and data users. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-18` | The Dataspace Protocol specifies how Datasets are accessed using Transfer Process Protocols. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-19` | The Dataspace Protocol only specifies the generic elements. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-20` | The APIs/technical interfaces for the actual data exchange are data space-specific. | informative | `building-on-top-of-foundational-standards.md` §4.1 |
| `DSSC-FND-21` | For future dataspaces, the DSSC recommends to use verifiable credentials as a technology to assist in establishing trust between participants. | recommended | `building-on-top-of-foundational-standards.md` §4.2 |
| `DSSC-FND-22` | Some operational data spaces still rely on more traditional approaches for issuing credentials, such as X.509 certificates in combination with a DAPS-service. | informative | `building-on-top-of-foundational-standards.md` §4.2 |
| `DSSC-FND-23` | Two protocols are commonplace for the issuing and sharing of verifiable credentials: OpenID4VC and DCP. | informative | `building-on-top-of-foundational-standards.md` §4.2 |
| `DSSC-FND-24` | OpenID for Verifiable Credential Issuance (OID4VCI) defines an API and corresponding OAuth-based authorization mechanisms for issuance of Verifiable Credentials. | informative | `building-on-top-of-foundational-standards.md` §4.2.1 |
| `DSSC-FND-25` | OpenID for Verifiable Presentations (OID4VP) defines a mechanism on top of OAuth 2.0 to allow the presentation of claims in the form of Verifiable Credentials as part of the protocol flow. | informative | `building-on-top-of-foundational-standards.md` §4.2.1 |
| `DSSC-FND-26` | Self-Issued OpenID Provider v2 (SIOPv2) enables end users to use OpenID Providers that they control. | informative | `building-on-top-of-foundational-standards.md` §4.2.1 |
| `DSSC-FND-27` | OID4VC is part of the EUDI Wallet Architecture and Reference Framework. | informative | `building-on-top-of-foundational-standards.md` §4.2.1 |
| `DSSC-FND-28` | The scope of the Eclipse DCP specification includes specifying a format for self-issued identity tokens. | informative | `building-on-top-of-foundational-standards.md` §4.2.2 |
| `DSSC-FND-29` | The scope of the Eclipse DCP specification includes defining a protocol for storing and presenting Verifiable Credentials and other identity-related resources. | informative | `building-on-top-of-foundational-standards.md` §4.2.2 |
| `DSSC-FND-30` | The scope of the Eclipse DCP specification includes defining a protocol for parties to request credentials from a credential issuer. | informative | `building-on-top-of-foundational-standards.md` §4.2.2 |
| `DSSC-FND-31` | The specification projects listed under "Other protocols" still need to provide their initial results, and these will be evaluated for future inclusion in the DSSC blueprint. | informative | `building-on-top-of-foundational-standards.md` §4.3 |

## Open questions

> **Ambiguous:** No specification versions are given in the prose for W3C Verifiable Credentials, DCAT-AP, ODRL or OAuth 2.0 (beyond "2.0" in the protocol's own name). Versions for the Dataspace Protocol (`2025-1`), the Decentralized Claims Protocol (`v1.0.1`), the EUDI Wallet Architecture and Reference Framework (`1.1.0`) and DCAT (`vocab-dcat-3`) appear only in the URLs the source links to, not in its text. A conformance claim against the "minimum set" therefore cannot be pinned to a specific specification version from this section alone. The W3C Verifiable Credentials link points to the *VC Overview* note rather than to a versioned data model specification.

> **Ambiguous:** Normative force of verifiable credentials is stated two ways. §3 places W3C Verifiable Credentials in the "minimum set of technical standards and specifications data spaces need to adhere to", while §4.2 says "For future dataspaces, the DSSC recommends to use verifiable credentials as a technology to assist in establishing trust between participants" — and notes that some operational data spaces still use X.509 with a DAPS-service. Whether VCs are required or recommended is not resolved.

> **Ambiguous:** §3 phrases the obligation as "need to adhere to" rather than *must*, *shall* or *required*, and no conformance criteria, profile or test procedure is given for adherence to the minimum set. The only compliance-testing mechanism named anywhere in the section is the TCK, and that applies to the Dataspace Protocol, which is not part of the minimum set.

> **Ambiguous:** DCAT-AP is simultaneously presented as a forthcoming Data Act standardisation deliverable ("A data catalogue implementation framework, DCAT-AP", §2, publication expected in 2026) and as something that "needs to be used for data spaces and is standardised through ETSI" (§3.2). No DCAT-AP version or profile is named, so the mandated artefact is not identifiable.

> **Ambiguous:** Naming variance for the OpenID family. §4.2 writes "OpenID4VC"; §4.2.1 titles it "OpenID for Verifiable Credentials" with link text "Open ID for Verifiable Credentials" and acronym "OID4VC", and names the "Open ID Foundation" with a space. Which string is canonical is not stated. Similarly, §4.1 writes "Eclipse Dataspace Working group" and §4.1 later "Eclipse Dataspace Working Group (EDWG)".

> **Ambiguous:** §4.2 states "Both have some overlap in functionality, but there are also differences" before either protocol has been named — the preceding sentence refers to "several protocols being developed". The two protocols (OpenID4VC and DCP) are only named in the following paragraph, so "Both" resolves forward rather than back.

> **Gap:** §1 announces "Harmonised standards for compliance with the Data Act" as one of the three categories, but the term "harmonised standards" does not recur; §2 is titled "Standards and specifications to comply with Data Act requirements". Whether the CEN-CENELEC/ETSI deliverables listed in §2 are the harmonised standards intended is not stated.

> **Gap:** §3 is titled "Three Key Technical Standards", but §3.2 covers two distinct artefacts with different roles and different normative treatment — DCAT version 3 (baseline metamodel) and DCAT-AP (implementation framework that "needs to be used") — plus optional data space-specific extensions.

> **Gap:** The Data Act article 33 bullets in §2 are quoted with the source's own elisions "(…)", so the requirement text captured in `DSSC-FND-01`–`DSSC-FND-04` is partial by construction. The full text must be read from the instrument itself.

> **Gap:** No organisation is stated for eIDAS2, X.509/DAPS or OAuth 2.0, and none is stated for the EUDI Wallet Architecture and Reference Framework. The DAPS reference is to an International Data Spaces Association IDS-G repository page rather than to a specification with a version.
