# Energy standards, abbreviations and glossary

> **Source** · Blueprint of the Common European Energy Data Space, Version 3.0, September 2025 — Interoperability Network for the Energy Transition (int:net), DOI 10.5281/zenodo.17116750
> **Coverage** · whole document: standards named across body chapters 1–8, plus chapter 12 "List of Abbreviations" and chapter 13 "Glossary"

This page consolidates every standard, ontology, protocol, role model and reference architecture that the CEEDS Blueprint names anywhere in its body chapters, together with the blueprint's own List of Abbreviations and its own Glossary. It is a reference index, not a chapter rendering: the blueprint scatters these identifiers across its architecture chapter, its implementation chapter and its interoperability chapter, and a conformance claim rests on the exact strings, so they are gathered here in one place.

**The grouping is ours. Every identifier is the source's.** The section headings below ("Energy-domain data models…", "Identity, trust and security…") are our organising device — CEEDS does not classify its standards this way. The identifiers themselves are reproduced exactly as CEEDS writes them, including capitalisation, spacing and version suffixes, and each carries a line reference into the blueprint text so the original wording can be checked. Where CEEDS writes an identifier in a form that differs from the standard's usual spelling (`OpenADR3.0`, `IDSA RAM v4`, `IEC (CIM, 61850, COSEM, etc.)`), the source's form is what appears here.

Named EU legal instruments (Data Act, Data Governance Act, Electricity Directive 2019/944, Implementing Regulation (EU) 2023/1162, and so on) are regulatory instruments rather than standards and are not indexed on this page.

---

## The standards reference

Each entry gives the identifier exactly as CEEDS writes it, what CEEDS says it is for in its own framing, and where the document names it. Line references are into the blueprint text (`Blueprint_CEEDS_v3.0.txt`).

### Energy-domain data models, ontologies and protocols

- **CIM** / **Common Information Model** / **IEC CIM** — CEEDS's framing: "the overarching CIM data model and associated ontologies" (§7.1.2); the model through which "harmonised ontologies" are defined for end-to-end interoperability of demand side flexibility data (§3.6). Glossary: "A standardized data model used to facilitate the exchange of information among various systems and organizations in the power industry."
  *Where:* named as "the Common Information Model (CIM)" at lines 1315–1317; inside "IEC (CIM, 61850, COSEM, etc.)" as a standard the Vocabulary Hub module is "expected to be reliant on" at lines 1600–1612; as "the IEC CIM standard for the information model" (EDDIE) at line 1866; "translates national information models into IEC CIM" (EDDIE) at line 1881; "cross-sectoral Common Information Models (CIM)" (SYNERGIES CIM Network Manager) at lines 1928–1929; "the overarching CIM data model and associated ontologies" at line 2853. Abbreviation list line 3379; glossary lines 3463–3466.

- **IEC 61970** — CEEDS's framing: "IEC 61970 for grid modelling".
  *Where:* §7.1.2 Semantic Interoperability, line 2850, in the list of "prominent standards-based data models and ontologies" the CEEDS "relies on".

- **IEC 61850-7** — CEEDS's framing: "IEC 61850-7 for advanced DER controls".
  *Where:* §7.1.2, lines 2851–2852.
  > **Note:** the bare string `IEC 61850` never appears in the document. The family is named twice, once as the bare number inside a parenthetical list — "IEC (CIM, 61850, COSEM, etc.)", line 1600 — and once as the part-specific `IEC 61850-7`, lines 2851–2852.

- **IEC 62325** and **IEC 62325 ESMP** — CEEDS's framing: "IEC 62325 ESMP for flexibility market interfaces".
  *Where:* as `IEC 62325` among the standards the SYNERGIES CIM Network Manager supports, line 1930; as `IEC 62325 ESMP` in §7.1.2, line 2850. CEEDS does not expand the abbreviation "ESMP".

- **IEC 62746** — CEEDS's framing: "IEC 62746 for service provided to technical aggregator communication".
  *Where:* §7.1.2, line 2851.

- **COSEM** — expanded by CEEDS as "Companion Specification for Energy Metering". Glossary: "A set of standards for energy metering data exchange, facilitating interoperable and accurate energy consumption measurements."
  *Where:* inside "IEC (CIM, 61850, COSEM, etc.)", line 1600. Abbreviation list line 3381; glossary lines 3468–3469.
  > **Note:** CEEDS never writes `DLMS`, and never attaches an IEC number (such as the IEC 62056 series) to COSEM.

- **SAREF** — expanded by CEEDS as "Smart Appliances REFerence ontology". CEEDS's framing: "SAREF for behind-the-meter-equipments"; also cited as an ETSI standard the Vocabulary Hub module is expected to rely on.
  *Where:* "ETSI (SAREF, etc.) standards", line 1611; "well-known vocabularies like SAREF and ThinkHome" (DATA CELLAR), line 1971; "SAREF for behind-the-meter-equipments", line 2850. Abbreviation list line 3437; glossary lines 3606–3608.

- **SAREF4ENER** — named without expansion or explanation.
  *Where:* line 1930, among the standards the SYNERGIES CIM Network Manager supports. This is the only occurrence in the document.

- **OCPP** — expanded by CEEDS as "Open Charge Point Protocol". CEEDS's framing: "OCPP for Public Charging Point interfaces". Glossary: "An application protocol for communication between electric vehicle charging stations and a central management system, also known as a charge point operator."
  *Where:* line 1930 (SYNERGIES CIM Network Manager); line 2852 (§7.1.2). Abbreviation list line 3425; glossary lines 3590–3591.

- **OpenADR3.0** — named without expansion or explanation. Written closed-up, with no space before the version.
  *Where:* line 1930, among the standards the SYNERGIES CIM Network Manager supports. Only occurrence.

- **CGMES Conformity Assessment Scheme (CAS)** — CEEDS's framing: "developed by ENTSO-E, as an example of conformity assessment in the Energy domain".
  *Where:* §7.1.2, lines 2853–2855, with footnote 14 pointing to ENTSO-E CIM Conformity and Interoperability.
  > **Note:** `CGMES` appears only inside this compound name. The document never expands CGMES, and CGMES is absent from the List of Abbreviations.

- **Open Data Protocol (OData)** — named in the same §7.1.2 list, with no further framing than its inclusion among the data models, ontologies and protocols CEEDS relies on.
  *Where:* lines 2852–2853.

- **Green Button CMD** — CEEDS's framing: connectivity supported by the EDDIE Framework for "United States (US)/Canada (CAN)" in addition to seven Member States.
  *Where:* line 1700. "CMD" is not expanded.

- **ThinkHome** — named as one of the "well-known vocabularies" the DATA CELLAR bespoke ontology draws on.
  *Where:* line 1971.

- **European Master Data Model** — EDDIE's data model, used both as its Vocabulary Hub and as its Publication & Discovery mechanism to "connect multiple data spaces".
  *Where:* Table 9 lines 1835–1837 and 1843–1845; lines 1881–1882, 1890.

- **Common Semantic Data Model (CSDM)** — OMEGA-X's Vocabulary Hub, "available on GitHub", to be published in the Semantic Treehouse of the ENERSHARE project.
  *Where:* Table 9 lines 1835–1838; lines 2006–2008.

### Energy-domain reference architectures, role models and organisations

- **Smart Grid Architecture Model (SGAM)** / **SGAM** — CEEDS's framing (glossary): "Conceptual framework designed to support the visualization, design, and analysis of smart grid systems, ensuring interoperability and standardization. It organizes the smart grid into three dimensions: domains, zones and layers."
  *Where:* the Technology deployment dimension is identified "in the energy domain through the Smart Grid Architecture Model (SGAM)", lines 289–291; DERA 3.0 "has been defined in the Bridge Data Management WG based on SGAM", line 1349; distributed data exchange platforms are "in line with the key applications and functions defined in the SGAM", lines 1354–1355; "new streams for data exchange according to SGAM", lines 2516–2517; the DERA 3.1 governance components are mapped "to the five SGAM interoperability layers (vertically)" with "ten building blocks … defined along the SGAM layers", lines 2886–2891; the int:net whitebook proposal of "a 6th SGAM layer, named 'framework' layer", lines 2903–2907 and 2950–2953; "These three subgroups directly relate to the proposal for a 6th SGAM layer", line 3027; "In the energy sector, assisted by SGAM", line 3058; "consistent with reference architectures used in the energy domain such as SGAM and Bridge DERA", lines 3190–3191. Abbreviation list line 3441; glossary lines 3622–3624.

- **DERA 3.0 (Data Exchange Reference Architecture 3.0)** — CEEDS's framing: the proposed combination of distributed data exchange platforms with a federated data space orchestration layer "reflects the concept of DERA 3.0 … which has been defined in the Bridge Data Management WG based on SGAM".
  *Where:* lines 1345–1350, with footnote 7 to the EU Publications Office.

- **DERA 3.1 model** / **DERA** / **Bridge DERA** — CEEDS's framing: "developed in the Data Management working group of Bridge"; its governance components are mapped to local and federated parts and to the five SGAM layers. Glossary: "A framework for facilitating efficient and secure data exchange in distributed energy resource environments."
  *Where:* "in line with the latest implementation plans of DERA", line 2774; "With respect to the DERA 3.1 model (developed in the Data Management working group of Bridge, at [11])", lines 2886–2887; Figure 15 caption line 2901; "SGAM and Bridge DERA", lines 3190–3191. Abbreviation list line 3387; glossary lines 3495–3496.
  > **Ambiguous:** the document cites **DERA 3.0** in chapter 4 and **DERA 3.1** in §7.1.3, with different references ([11] is "European (energy) data exchange reference architecture 3.1"). It does not say whether 3.1 supersedes the 3.0 concept the architecture chapter is built on.

- **Harmonised Electricity Market Role Model (HEMRM)** / **HEMRM** — CEEDS's framing: the role model through which "the participation of single users … is defined in the CEEDS"; the set of energy stakeholders "typically include all actors defined through the HEMRM"; stakeholder interactions in governance are "detailed based on the HEMRM".
  *Where:* lines 313–315 with footnote 1 (`https://www.entsoe.eu/data/cim/role-models/`, line 335); lines 1374–1376; lines 2515–2517.
  > **Note:** HEMRM is **not** in the List of Abbreviations and has no glossary entry, although it is one of the few role models the blueprint treats as constitutive.

- **ENTSO-E** — expanded by CEEDS as "European Network of Transmission System Operators for Electricity"; named as a drafting body for the network code on demand response, as a discussant of "relevant data exchange standards", as the developer of the CGMES Conformity Assessment Scheme, and as an energy supplier association in the framework layer.
  *Where:* lines 1274, 1315, 2854, 2918, 2998. Abbreviation list line 3403; glossary lines 3532–3534.

- **IEC** — expanded as "International Electrotechnical Commission". Glossary: "An international standards organization that prepares and publishes international standards for all electrical, electronic, and related technologies."
  *Where:* abbreviation list line 3419; glossary lines 3559–3560; used as a standards-body prefix at lines 1600, 1866, 1881, 2850–2852.

- **ETSI** — named as a standards body whose standards (SAREF among them) the Vocabulary Hub module is expected to rely on, and as part of the "CEN-CENELEC-ETSI Smart Grid Coordination Group".
  *Where:* line 1611; line 2999.

- **CEN-CENELEC-ETSI Smart Grid Coordination Group** — named as one of the "standards organisations" involved in the institutional arrangements behind Commission Implementing Regulation (EU) 2023/1162.
  *Where:* lines 2998–2999.

- **EMINENT** — CEEDS's framing: "an interoperability maturity model developed in the int:net project", addressing interoperability "as a business capability".
  *Where:* §7.1.4, lines 3107–3119.

- **IntMAS** / **"Interoperability Management and Audit System"** — CEEDS's framing: allows institutions "to implement a continuous improvement process in their management practices and daily work"; "modelled alongside proven management systems such as ISO 9001, ISO 14001 or EMAS".
  *Where:* §7.1.4, lines 3124–3148. Related: **IntPPC, the Interoperability People and Project Connector platform** (line 3148).

- **CEI Sphere Hourglass© model** / **Hourglass Model** — CEEDS's framing: "a simple framework to help diverse stakeholders align using a market-driven, standards-enabled approach"; maps business stakeholders to technological roles, layers functions, and "will create a pathway to standardisation".
  *Where:* ch.8, lines 3214–3226 (Figure 18, "Hourglass Model (From CEI-Sphere [15])").

### Data space architectures, protocols and frameworks

- **dataspace protocol** / **Dataspace Protocol** / **Data Space Protocol (DSP)** / **IDS Dataspace Protocol** — CEEDS's framing: "specifications intended to facilitate interoperable data sharing among entities governed by usage control and utilizing web technologies"; it "ensures fundamental technical interoperability for participants, a prerequisite for joining any data space" and "aims to define the minimum standard of communication".
  *Where:* §7.1.1.4, lines 2813–2834, with footnote 13 to the IDS knowledge base; "a Dataspace Protocol-compliant connector" (DATA CELLAR), line 1757; "the International Data Spaces (IDS) Dataspace Protocol", lines 1960–1961; "the IDS Dataspace Protocol's Contract Negotiation Protocol", line 1973; "the Data Space Protocol (DSP) for contract negotiation and secure data transfers" (OMEGA-X), line 1997; "it does not yet support the Data Space Protocol (DSP)" (ENERSHARE), lines 2029–2030; "it has adopted the Dataspace Protocol for connector interoperability", lines 2606–2607.
  > **Ambiguous:** the document uses four spellings of the same protocol — `dataspace protocol` (lower case, §7.1.1.4), `Dataspace Protocol`, `Data Space Protocol (DSP)` and `IDS Dataspace Protocol`. It never states that these denote one specification, though the surrounding prose implies it.

- **IDS RAM** / **IDS-RAM v4** / **IDSA Reference Architecture Model v4** / **IDSA RAM v4** — CEEDS's framing: the reference architecture model the EDSCP implementations align with; the source of the Metadata Broker and App Store specifications.
  *Where:* "aligns with the Gaia-X architecture (22.10 Release) and IDS RAM", line 1915; "aligning with IDS RAM and Gaia-X", lines 1930–1931; "aligns with the IDS RAM and Gaia-X Clearing House", line 1934; "the specifications of the IDS RAM Metadata Broker and App Store", lines 1938–1939; "comply with IDS RAM and Gaia-X", line 1949; "in alignment with DSSC and IDS RAM", line 1953; "an IDSA-certified connector aligned with the IDSA Reference Architecture Model v4", lines 2026–2027; "with compliance to IDSA RAM v4", line 2037; "compliant with IDSA RAM v4", line 2043; "compliant with IDS-RAM v4", line 2050; "compliant with IDS RAM specifications", line 2383. Reference [3] is "IDS-RAM 4 - Roles in the International data spaces".
  > **Ambiguous:** five spellings of the same model appear (`IDS RAM`, `IDS-RAM v4`, `IDSA RAM v4`, `IDSA Reference Architecture Model v4`, `IDS-RAM 4`), sometimes on facing pages.

- **IDSA** — the International Data Spaces Association, named as the provider of Metadata Broker specifications, as the definer of the identity provider solution, and as a certification authority for connectors.
  *Where:* "the Metadata Broker specifications provided by IDSA", lines 1673–1675; "an IDSA-compatible DAPS", line 2000; "compatible with IDSA and GAIA-X trust frameworks", line 2597; "as defined by IDSA", line 2598.

- **Gaia-X** / **GAIA-X** — named throughout chapter 5 and §6.2.1 as the specification set and architecture the EDSCP align with; "GAIA-X deploys a decentralized approach based on self-sovereign identity" (line 1577); "The Gaia-X specifications constitute a valid reference for the implementation" of data cataloguing and marketplaces (line 2377).
  *Where:* lines 1577, 1758, 1824, 1915, 1921, 1931, 1935, 1965, 1978, 1980, 2001–2002, 2011, 2015, 2017, 2139, 2184, 2339, 2342, 2377, 2402, 2597, 2602, 2609. Both `Gaia-X` and `GAIA-X` capitalisations occur.
  Named Gaia-X sub-components: **Gaia-X Trust Framework** (1921, 1965, 1978, 2001–2002), **Gaia-X Digital Clearing House (GXDCH)** (1846, 1980, 2017–2020), **Gaia-X Federated Catalogue** (1758, 2015, 2184), **Gaia-X Verifiable Credentials** (1823–1824, 2139, 2339), **Gaia-X Clearing House** (1935), **GAIA-X schemas** (2402), **Marketplace Federator** (2608–2609).

- **DSSC** / **Dataspace Support Centre** — CEEDS's framing: "The objective in the future is that the CEEDS architecture is a specialization of the mandatory part of the Dataspace Support Centre (DSSC) and of future data space standards"; the DSSC Blueprint v1.0 is the source of the data space definition and of the control plane / data plane approach.
  *Where:* lines 227–239, 264–266, 1489–1495, 1872, 1887, 1953, 2747, 3032, 3228, 3262. References [1] and [5] are the DSSC Blueprint v1.0 and v2.0.

- **OPEN DEI** — named as the origin of the technical building blocks and of the "Trust" category grouping.
  *Where:* lines 1576, 2747, Figure 13 caption line 2754. Reference [4] "OPEN DEI - State of the Art".

- **DSBA** technical convergence paper — CEEDS's framing: "DSBA has recently published the technical convergence paper which has defined the main actors" of a data space.
  *Where:* lines 2773–2793, footnote 12. Reference [10] "Technical Convergence – Discussion Document", Data Spaces Bus. Alliance.

- **European Interoperability Framework (EIF) Toolbox** — CEEDS's framing: the interoperability requirements in the blueprint "refer to the European Interoperability Framework (EIF) Toolbox [9], addressing the applicable layers".
  *Where:* lines 2710–2714.

- **European Interoperability Reference Architecture** (**EIRA**, per reference [13]) — CEEDS's framing: "identifies target users (under its scope of application, from within public administrations) as portfolio managers, business analysts and architects".
  *Where:* lines 3050–3053; reference [13] at lines 3311–3313.

- **FAIR (Findable, Accessible, Interoperable, Reusable) principles** — CEEDS's framing: "the catalogue follows as much as possible the FAIR … principles".
  *Where:* lines 1658–1659.

- **Eclipse Dataspace Components (EDC)** — the connector framework used by DATA CELLAR, OMEGA-X (via the sovity connector) and ENERSHARE; also the ODRL-based policy engine.
  *Where:* Table 9 lines 1815–1819 and 1854–1856; lines 1959–1960, 1983, 2054, 2137, 2142, 2335.

- **XFSC Federated Catalogue** — DATA CELLAR's Publication & Discovery component, "a modified fork", "ensuring compliance with the Gaia-X Trust Framework".
  *Where:* Table 9 line 1843; lines 1977–1978.

- **TNO Security Gateway (TSG)** — ENERSHARE's connector, "an IDSA-certified connector".
  *Where:* Table 9 lines 1815–1816; lines 2026–2027, 2036–2037, 2050, 2053–2055, 2137, 2338.

- **OneNet Connector** — the basis of the "Energy Data Space Connector v1.1" used by ENERSHARE.
  *Where:* lines 2028–2030.

- **Semantic Treehouse** — ENERSHARE's Vocabulary Hub, "compliant with IDSA RAM v4"; also the intended publication venue for OMEGA-X's CSDM.
  *Where:* Table 9 line 1835; lines 2007–2008, 2043–2046, 2146, 2336.

- **DAPS** / **Dynamic Attribute Provisioning Service (DAPS)** — part of the IDSA identity provider solution, used by OMEGA-X and ENERSHARE.
  *Where:* Table 9 line 1820; line 2000; lines 2598–2599.

### Semantic web, metadata, serialisation and policy languages

- **DCAT (Data Catalog Vocabulary)** — CEEDS's framing: "recommended as a publisher to describe datasets and data services".
  *Where:* §4.1 Vocabulary Hub, lines 1599–1600, with footnote 11 (`https://w3.org/TR/vocab-dcat-3/#Class:Catalog`, line 1605). This is one of the very few explicit recommendations of a named standard in the whole blueprint.

- **RDF** — CEEDS's framing: "a framework for expressing linked data so it can be exchanged between applications without loss of meaning"; expresses "simple facts in the form of triples (subject, predicate and object)" and "uses URIs to name the relationship between things".
  *Where:* §7.1.2, lines 2858–2864; also "OWL, RDF, JSON-LD" in the DATA CELLAR bespoke ontology, line 1970.

- **Turtle [TURTLE]**, **TriG, [TRIG]**, **JSON-LD [JSON-LD]** — CEEDS's framing: "various concrete syntaxes for RDF". Written with the bracketed reference tags shown.
  *Where:* line 2864.
  > **Note:** the bracketed tags `[TURTLE]`, `[TRIG]`, `[JSON-LD]` are reference markers with no corresponding entries in the blueprint's chapter 9 reference list. The comma placement in "TriG, [TRIG]" is the source's.

- **JSON** — CEEDS's framing: "As the main reference, JSON constitutes a lightweight, language-independent data interchange format, easy to parse and generate."
  *Where:* §7.1.1.3 Data Formats, lines 2805–2807.

- **JSON-LD** — CEEDS's framing: "Particularly relevant, as specific proposed solution is the use of JSON-LD, which serializes linked data in JSON."
  *Where:* §7.1.1.3, lines 2807–2808; also lines 1970 (DATA CELLAR) and 2009 (OMEGA-X, "ontology-based REST API standards such as OPENAPI and JSON-LD").

- **OWL** and **RDFS/OWL** — the ontology languages used by DATA CELLAR's bespoke ontology and supported by Semantic Treehouse.
  *Where:* lines 1970, 2044.

- **SHACL** — used for "the syntactic and semantic verification of any submitted self-description against predefined schemas (aligned with the released GAIA-X schemas)"; also an open standard supported by Semantic Treehouse.
  *Where:* lines 2044, 2402.

- **JSON schema** — an open standard supported by Semantic Treehouse.
  *Where:* line 2044.

- **OPENAPI** — named as one of the "ontology-based REST API standards" OMEGA-X's CSDM follows. Written in all capitals.
  *Where:* lines 2008–2009.

- **ODRL** — the policy language used by DATA CELLAR (with the EDC policy engine), by ENERSHARE via EDC, and in the BUC realisation of Access & Usage Policies.
  *Where:* lines 1984, 2054, 2338.

- **XACML** — the policy language used by ENERSHARE's TSG-based policy enforcement, presented alongside ODRL as the alternative.
  *Where:* lines 2054, 2338 ("implemented using ODRL (EDC) or XACML (TSG), aligned with GDPR").

### Identity, trust and security standards

- **eIDAS** / **eID** / **eIDs** — CEEDS's framing: "Infrastructures regulated and deployed via electronic Identification and Authentication Services eIDAS [7] provide proven-in-use electronic IDs (eIDs), certification services, and with its 2024 amendments [8] adding the European Digital Identity Framework – even distributed identity wallets." EDDIE "is utilising as far as possible European electronic Identification and Authentication Services (eIDAS)".
  *Where:* Table 9 line 1820; lines 1870–1871, 1901, 2615–2628. Underlying instruments: Regulation 910/2014 [7] and Regulation (EU) 2024/1183 [8].

- **X.509** — CEEDS's framing: EDDIE establishes trust between federated components "using X.509-based signing and encryption. This implementation follows eIDAS and X.509 standards"; X.509 certificates are also named as the Provenance & Traceability mechanism in a BUC realisation.
  *Where:* Table 9 line 1846; lines 1900–1902, 2145.

- **OpenID Connect** / **OIDC** / **OpenID** — used by EDDIE, SYNERGIES and DATA CELLAR (all with Keycloak) for centralised authentication; also named among the "established standards" underlying DID and VC implementations.
  *Where:* Table 9 lines 1820–1828; lines 1870, 1920–1921, 1963, 2594, 2606.

- **OAuth 2.0** / **OAuth** — CEEDS's framing: SYNERGIES' identity management "complies with OAuth 2.0"; OAuth is also listed among "established standards (e.g., W3C, OpenID, SAML, OAuth)".
  *Where:* lines 1921, 2594, 2606.

- **SAML** — named among the established standards underlying DID/VC implementations and as a marketplace integration mechanism in ENERSHARE.
  *Where:* lines 2594, 2606.

- **JWT** — named among the standards DATA CELLAR's access and usage policy enforcement follows.
  *Where:* line 1984.

- **W3C Verifiable Credentials** / **Verifiable Credentials (VCs)** / **Verifiable Presentation** — the credential model used by DATA CELLAR, OMEGA-X and (as "Gaia-X Verifiable Credentials") in BUC realisations; DATA CELLAR and OMEGA-X base identity management on Self-Sovereign Identity principles "primarily utilizing W3C Verifiable Credentials and Decentralized Identifiers (DID)".
  *Where:* Table 9 lines 1823–1828; lines 1964, 1984–1990, 2000–2001, 2139, 2339, 2403, 2592–2593, 2603–2604.

- **Decentralized Identifiers (DIDs)** / **DID** — used with Verifiable Credentials for SSI-based identity management; DIDs are cryptographically verified in the catalogue security measures.
  *Where:* lines 1964–1965, 2403, 2592, 2604, 2608.

- **OID4VC** / **OID4VCI** / **OID4VP** — CEEDS expands OID4VC once as "OpenID Connector for Verifiable Credentials (OID4VC)". OID4VCI is used by OMEGA-X's VC issuer; ENERSHARE aims to implement a participant wallet using "DID, OID4VP, and OID4VCI".
  *Where:* Table 9 line 1828; lines 1965–1966, 2001, 2608.
  > **Note:** "OpenID Connector for Verifiable Credentials" (line 1965) is the source's expansion of OID4VC.

- **W3C** — named as a standards body, "established standards (e.g., W3C, OpenID, SAML, OAuth)".
  *Where:* line 2594.

- **PKI**, **Certificate Authority (CA)**, **Self-Sovereign Identity (SSI)** — named as the supporting security constructs in the EDSCP identity implementations.
  *Where:* lines 2000, 2599, 2603–2604.

### Messaging, API and transport protocols

- **OASIS AS4** / **AS4 standards** — CEEDS's framing: one of the "multiple communication protocols" the EDDIE Framework supports; EDDIE logging ensures "compliance with AS4 standards for features such as repeatability, non-reputability, and auditability".
  *Where:* lines 1866–1868, 1878–1879. (The source writes "non-reputability".)

- **REST** / **REST APIs** / **Pub-Sub APIs** — REST is named among EDDIE's supported protocols and as the only standard ENERSHARE's Clearing House follows ("It does not follow specific standards beyond REST APIs"); bilateral exchange of traded data among data exchange platforms is "based on REST or Pub-Sub APIs".
  *Where:* lines 1479–1481, 1867, 2040.

- **Kafka** — named as the connector mechanism EDDIE uses for cross-sectoral data integration and among its supported protocols.
  *Where:* lines 1865–1867.

- **AMQP** — among EDDIE's supported communication protocols.
  *Where:* line 1867.

- **MQTT5** — among EDDIE's supported communication protocols, "for edge deployments". Written closed-up, with no space or hyphen before the version.
  *Where:* line 1868.

### Distributed-ledger token standards

- **ERC20** — CEEDS's framing: ENERSHARE's contracting framework "uses blockchain and smart contracts based on the ERC20 standard for tokenized transactions"; DATA CELLAR uses ERC20 for fungible tokens.
  *Where:* lines 2047–2048, 2477–2480.

- **ERC721** — CEEDS's framing: used by DATA CELLAR, "associated with the creation of non-fungible … tokens", to digitise assets and licences.
  *Where:* lines 2477–2480.

- **Solidity** and **Ethereum** — the smart-contract language and distributed platform named in the DATA CELLAR and SYNERGIES contracting implementations.
  *Where:* lines 1933–1934, 2470–2477.

### Reference-architecture, management-system and standardisation-body references

- **ISO/IEC/IEEE 42042 - reference architecture** — CEEDS's framing: one of the "current standards on reference architectures" that recommend "a description of DSSC structured into a reference part and a pattern part". The descriptive suffix is the source's.
  *Where:* §1.1, line 231. Only occurrence.

- **ISO/IEC 40131 - guidance for reference architecture** — the second of the two reference-architecture standards named in the same parenthesis. The descriptive suffix is the source's.
  *Where:* §1.1, line 231. Only occurrence.

- **ISO 9001**, **ISO 14001**, **EMAS** — CEEDS's framing: the "proven management systems" alongside which IntMAS "has been modelled".
  *Where:* §7.1.4, line 3131.

- **ISO/IEC JTC 1/SC 41** (footnote spelling: **ISO/IEC JTC1/SC41**) — CEEDS's framing: the standardisation committee to which the Hourglass model will be submitted, alongside "the 2026 standardisation rolling plan"; the footnote points to "the preliminary work item on architecture considerations on IoT, Cloud, Edge".
  *Where:* ch.8, lines 3220–3221 (body) and line 3244 (footnote 24).
  > **Note:** the body text writes `ISO/IEC JTC 1/SC 41` with spaces; footnote 24 writes `ISO/IEC JTC1/SC41` without. Both are in the source.

### Named implementations that are not standards

For completeness, and to make clear they were considered and deliberately excluded from the standards index above, the blueprint also names these products and platforms: **Keycloak**, **walt.id**, **EJBCA**, **sovity** ("Connector-as-a-Service"), **Kubernetes** (with **Fluentd** and **Fluentbit**), **Docker**, **Python v3.12**, **NodeJS**, **NestJS**, **VueJS**, **TailwindCSS**, **GitHub**, **AIIDA** (Administrative Interface for In-house Data Access), **DATADIS**, **EDDIE Framework**, **EDDIE Data Marketplace**, **EDDIE Online**. They are implementation choices reported by the EDSCP, not standards the blueprint asks anyone to conform to.

---

## Normative force per standard

A conformance claim rests on knowing which identifiers CEEDS asks for and which it merely mentions. The classification below uses four values:

- **required** — the source uses a mandatory construction ("prerequisite", "are a requirement").
- **recommended** — the source uses "recommended", "should", "proposed solution", "as much as possible".
- **expected** — the source states an expectation of reliance without a normative verb ("is expected to be reliant on"). Recorded separately rather than promoted to "recommended", because the source's wording is weaker than a recommendation and stronger than a bare mention.
- **referenced** — the source names it, describes it, or reports that an EDSCP project uses it, without saying anything normative about it. **This is the honest answer for the large majority of the standards in this document**, including almost all of the energy-domain ones.

| Identifier (as CEEDS writes it) | Normative force | The source's own wording | Lines |
|---|---|---|---|
| `dataspace protocol` / `Data Space Protocol (DSP)` | required | "a prerequisite for joining any data space" | 2830–2832 |
| data-ontology-based approaches (framework: `RDF`) | required | "approaches based on data ontology … are a requirement in order to avoid silos" | 2856–2858 |
| `DCAT (Data Catalog Vocabulary)` | recommended | "is recommended as a publisher to describe datasets and data services" | 1599–1600 |
| `JSON-LD` | recommended | "Particularly relevant, as specific proposed solution is the use of JSON-LD" | 2807–2808 |
| `FAIR (Findable, Accessible, Interoperable, Reusable) principles` | recommended | "follows as much as possible" | 1658–1659 |
| `CEI Sphere Hourglass© model` | recommended | "Further improvements to the CEEDS blueprint should build on" | 3214–3216 |
| `ISO/IEC/IEEE 42042 - reference architecture` | referenced | cited as the source of a recommendation about DSSC structure | 231 |
| `ISO/IEC 40131 - guidance for reference architecture` | referenced | cited as the source of a recommendation about DSSC structure | 231 |
| `IEC (CIM, 61850, COSEM, etc.)` | informative | "standards are what this vocabulary module is expected to be reliant on" | 1600–1612 |
| `ETSI (SAREF, etc.)` | informative | "standards are what this vocabulary module is expected to be reliant on" | 1600–1612 |
| `SAREF` | referenced | named after "such as", in the list CEEDS "relies on"; "for behind-the-meter-equipments" | 2848–2850 |
| `IEC 61970` | referenced | named after "such as"; "for grid modelling" | 2850 |
| `IEC 62325 ESMP` | referenced | named after "such as"; "for flexibility market interfaces" | 2850 |
| `IEC 62746` | referenced | named after "such as"; "for service provided to technical aggregator communication" | 2851 |
| `IEC 61850-7` | referenced | named after "such as"; "for advanced DER controls" | 2851–2852 |
| `OCPP` | referenced | named after "such as"; "for Public Charging Point interfaces" | 2852 |
| `Open Data Protocol (OData)` | referenced | named after "such as", no stated purpose | 2852–2853 |
| `CIM` / `IEC CIM` | referenced | "the overarching CIM data model and associated ontologies"; "harmonised ontologies, as defined in the Common Information Model (CIM)" | 1315–1317, 2853 |
| `CGMES Conformity Assessment Scheme (CAS)` | referenced | "as an example of conformity assessment in the Energy domain" | 2853–2855 |
| `COSEM` | referenced | named only inside the IEC parenthetical and in the abbreviations/glossary | 1600, 3381, 3468 |
| `SAREF4ENER` | referenced | reported EDSCP implementation (SYNERGIES CIM Network Manager) | 1930 |
| `OpenADR3.0` | referenced | reported EDSCP implementation (SYNERGIES CIM Network Manager) | 1930 |
| `IEC 62325` | referenced | reported EDSCP implementation (SYNERGIES CIM Network Manager) | 1930 |
| `Green Button CMD` | referenced | reported EDSCP capability (EDDIE Framework) | 1700 |
| `ThinkHome` | referenced | reported EDSCP implementation (DATA CELLAR ontology) | 1971 |
| `Smart Grid Architecture Model (SGAM)` | referenced | the organising frame throughout: "as identified in the energy domain through", "in line with the key applications and functions defined in", "according to SGAM", "consistent with … such as SGAM" | 290, 1349, 1355, 2517, 2889, 3190 |
| `DERA 3.0 (Data Exchange Reference Architecture 3.0)` | referenced | "This approach reflects the concept of DERA 3.0" | 1348–1349 |
| `DERA 3.1 model` / `Bridge DERA` | referenced | "With respect to the DERA 3.1 model"; "consistent with … such as SGAM and Bridge DERA" | 2886, 3190–3191 |
| `Harmonised Electricity Market Role Model (HEMRM)` | referenced | "the participation of single users, defined in the CEEDS through the … (HEMRM), remains a foremost feature"; "typically include all actors defined through the HEMRM" | 313–315, 1375, 2516 |
| `EMINENT` | referenced | described as an int:net maturity model; no conformance obligation stated | 3107–3119 |
| `IntMAS` | referenced | described; "modelled alongside proven management systems" | 3124–3133 |
| `ISO 9001`, `ISO 14001`, `EMAS` | referenced | named after "such as", as models for IntMAS | 3131 |
| `ISO/IEC JTC 1/SC 41` | referenced | a submission target for the Hourglass model | 3221, 3244 |
| `IDS RAM` / `IDSA RAM v4` / `IDS-RAM v4` | referenced | reported EDSCP alignment; also the source of the Metadata Broker specification | 1915–2050, 2383 |
| `Metadata Broker specifications provided by IDSA` | referenced | "An example of such implementation could be…" | 1673–1675 |
| `Gaia-X` / `GAIA-X` (and Trust Framework, GXDCH, Federated Catalogue) | referenced | "The Gaia-X specifications constitute a valid reference for the implementation"; reported EDSCP alignment | 1758–2402, 2597–2609 |
| `Eclipse Dataspace Components (EDC)` | referenced | reported EDSCP implementation | 1815, 1959, 2054 |
| `XFSC Federated Catalogue` | referenced | reported EDSCP implementation (DATA CELLAR) | 1843, 1977 |
| `Semantic Treehouse` | referenced | reported EDSCP implementation (ENERSHARE, OMEGA-X) | 2007, 2043 |
| `DAPS` | referenced | reported EDSCP implementation; "as defined by IDSA" | 1820, 2000, 2599 |
| `JSON` | referenced | "As the main reference, JSON constitutes a lightweight … format" | 2805–2806 |
| `RDF` | referenced | described at length as the framework for expressing linked data | 2858–2864 |
| `Turtle [TURTLE]`, `TriG, [TRIG]`, `JSON-LD [JSON-LD]` | referenced | "There are various concrete syntaxes for RDF, such as…" | 2864 |
| `OWL` / `RDFS/OWL` | referenced | reported EDSCP implementation | 1970, 2044 |
| `SHACL` | referenced | "can be performed using SHACL checks"; reported EDSCP support | 2044, 2402 |
| `JSON schema` | referenced | reported EDSCP support (Semantic Treehouse) | 2044 |
| `OPENAPI` | referenced | reported EDSCP implementation (OMEGA-X CSDM) | 2009 |
| `ODRL` | referenced | reported EDSCP implementation; "implemented using ODRL (EDC) or XACML (TSG)" | 1984, 2054, 2338 |
| `XACML` | referenced | reported EDSCP implementation | 2054, 2338 |
| `eIDAS` / `eID` | referenced | "provide proven-in-use electronic IDs"; reported EDSCP use | 1871, 1901, 2615–2628 |
| `X.509` | referenced | reported EDSCP implementation (EDDIE); example mechanism in a BUC realisation | 1901, 2145 |
| `OpenID Connect` / `OpenID` / `OIDC` | referenced | reported EDSCP implementation; "established standards (e.g., W3C, OpenID, SAML, OAuth)" | 1870, 1921, 1963, 2594 |
| `OAuth 2.0` / `OAuth` | referenced | "complies with OAuth 2.0"; named among established standards | 1921, 2594, 2606 |
| `SAML` | referenced | named among established standards; reported EDSCP integration | 2594, 2606 |
| `JWT` | referenced | reported EDSCP implementation (DATA CELLAR) | 1984 |
| `W3C Verifiable Credentials` / `Decentralized Identifiers (DID)` | referenced | reported EDSCP implementation; "commonly used" | 1964, 2592, 2604 |
| `OID4VC` / `OID4VCI` / `OID4VP` | referenced | reported EDSCP implementation | 1828, 1966, 2001, 2608 |
| `OASIS AS4` / `AS4` | referenced | reported EDSCP implementation; "ensuring compliance with AS4 standards" | 1867, 1878 |
| `REST` / `Pub-Sub APIs` | referenced | "based on REST or Pub-Sub APIs"; "does not follow specific standards beyond REST APIs" | 1480, 1867, 2040 |
| `Kafka`, `AMQP`, `MQTT5` | referenced | reported EDSCP implementation (EDDIE) | 1865–1868 |
| `ERC20`, `ERC721` | referenced | reported EDSCP implementation (ENERSHARE, DATA CELLAR) | 2048, 2479 |
| `European Interoperability Framework (EIF) Toolbox` | referenced | "they refer to the European Interoperability Framework (EIF) Toolbox [9]" | 2713 |
| `European Interoperability Reference Architecture` | referenced | described as identifying target users | 3051 |
| `DSSC` | referenced | "the CEEDS architecture is a specialization of the mandatory part of the … (DSSC)" — stated as a future objective | 227–228 |
| `OPEN DEI` | referenced | source of the technical building blocks figure | 2747, 2754 |
| `DSBA` technical convergence paper | referenced | "has defined the main actors" | 2774–2775 |

---

## Identifiers CEEDS does **not** use

Recorded because their absence is itself a finding for anyone benchmarking against this blueprint:

- **`IEC 61850`** as a bare string — never appears. Only `61850` inside "IEC (CIM, 61850, COSEM, etc.)" (line 1600) and `IEC 61850-7` (lines 2851–2852).
- **`DLMS`** — never appears, in any form, despite COSEM appearing three times.
- **`IEC 61968`**, **`IEC 62056`**, **`IEC 63110`**, **`ISO 15118`**, **`OCPI`**, **`EEBUS`**, **`Matter`**, **`Modbus`**, **`BACnet`**, **`OpenADR`** without a version, **`USEF`**, **`EFET`**, **`MADES`**, **`ECP`**, **`UN/CEFACT`**, **`EDIFACT`**, **`NGSI-LD`**, **`FIWARE`**, **`SPARQL`**, **`SKOS`**, **`IEEE 2030.5`** — none of these strings appears anywhere in the document.
- **`CGMES`** on its own — appears only inside "CGMES Conformity Assessment Scheme (CAS)"; never expanded, and absent from the List of Abbreviations.
- **`HEMRM`** is used in the body four times but has **no** entry in the List of Abbreviations and **no** glossary entry.
- **`CIM`** is defined in the abbreviations and glossary as "Common Information Model" only; the blueprint never gives it an IEC number of its own (it names `IEC 61970` separately, for grid modelling).
- **`ESMP`** is used once, in `IEC 62325 ESMP`, and is never expanded.

---

## Abbreviations

Chapter 12, "List of Abbreviations", reproduced verbatim and in the source's own order (which is not strictly alphabetical — `EDSCP` precedes `EDIB`, and `IEC` falls between `LEC` and `OEM`). The dash character is the source's; CEEDS mixes hyphens and en dashes within the list.

| Abbreviation | Expansion (verbatim) |
|---|---|
| ADMS | Automation Distribution Management System |
| BRP | Balance Responsible Party |
| BSP | Balance Service Provider |
| CIM | Common Information Model |
| COSEM | Companion Specification for Energy Metering |
| CPO | Charge Point Operator |
| DER | Distributed Energy Resources |
| DERA | Data Exchange Reference Architecture |
| DGA | Data Governance Act |
| DSO | Distribution System Operator |
| EDSCP | Energy Data Space Cluster Projects |
| EDIB | European Data Innovation Board |
| EMRSP | Electro Mobility Roaming Service Provider |
| EMS | Energy Management System |
| EMSP | e-Mobility Service Provider |
| ENTSO-E | European Network of Transmission System Operators for Electricity |
| EV | Electric Vehicle |
| EVCI | Electric Vehicle Charging Infrastructure |
| EVU | Electric Vehicle User |
| FSP | Flexibility Service Provider |
| GDPR | General Data Protection Regulation |
| JASC | Jointly Acting Self-Consumers |
| LEC | Local Energy Community |
| IEC | International Electrotechnical Commission |
| OEM | Original Equipment Manufacturer |
| O&M | Operation and Maintenance |
| OCPP | Open Charge Point Protocol |
| PV | Photovoltaic |
| PaaS | Platform as a Service |
| RES | Renewable Energy Sources |
| SAREF | Smart Appliances REFerence ontology |
| SCADA | Supervisory Control and Data Acquisition |
| SGAM | Smart Grid Architecture Model |
| SGU | Significant Grid User |
| SPG | Service Providing Group |
| SPU | Service Providing Unit |
| TSO | Transmission System Operator |

*Source: chapter 12, lines 3372–3449. 37 entries.*

> **Note:** the source writes "LEC- Local Energy Community" and "PaaS- Platform as a Service" without a space before the expansion, and "DSO  –  Distribution System Operator" with doubled spaces. Only that incidental whitespace has been normalised for the table; the terms and expansions are verbatim.

---

## Glossary

Chapter 13 is **CEEDS's own glossary**, not ours. Every definition below is reproduced verbatim, in the source's order (which is broadly but not strictly alphabetical — "Contracting" follows "CPO", "Metering" follows "Microgrid", and "Smart Grid Architecture Model (SGAM)" is filed under S-m-a-r-t rather than under SGAM). Definitions are not requirements and carry no requirement IDs.

**Access & Usage Policies and Control**: Policies that define the rights and obligations for accessing services and using data within CEEDS, ensuring control over data usage.

**CEEDS (Common European Energy Data Space)**: A collaborative initiative aimed at enhancing data sharing and interoperability within the European energy sector to foster innovation, efficiency, and sustainability.

**CIM (Common Information Model)**: A standardized data model used to facilitate the exchange of information among various systems and organizations in the power industry. It ensures interoperability and seamless integration by providing a common framework for representing power system components, their attributes, and relationships.

**COSEM (Companion Specification for Energy Metering)**: A set of standards for energy metering data exchange, facilitating interoperable and accurate energy consumption measurements.

**CPO (Charge Point Operator)**: Entities responsible for installing, operating, and maintaining electric vehicle charging stations.

**Contracting**: Focuses on managing and executing specific data transactions through contract templates, model clauses, and possibly smart contracts to streamline and automate the contracting process within CEEDS.

**Control Plane and Data Plane**: Differentiates between management, routing, and processing of data (control plane) and the actual movement of data (data plane), pivotal for standardizing data exchange in CEEDS.

**Cybersecurity in Energy Systems**: The protection of energy infrastructure and data from cyber threats and attacks, ensuring the reliability, integrity, and availability of energy systems and data.

**Data Space Connector**: A software component that enables interconnection and data exchange between different IT systems/platforms and data-using applications, facilitating interoperable and trustworthy data exchanges in CEEDS.

**Data Spaces**: Conceptual frameworks that enable secure and sovereign data exchange across different domains and industries, promoting interoperability and collaboration.

**DER (Distributed Energy Resources)**: Small-scale units of local generation connected to the grid at distribution level, including solar panels, wind turbines, and energy storage systems.

**DERA (Data Exchange Reference Architecture)**: A framework for facilitating efficient and secure data exchange in distributed energy resource environments.

**Demand Response (DR)**: A change in the power consumption of an electric utility customer to better match the demand for power with the supply.

**Digital Twin Technology in Energy**: The creation of a digital replica of physical assets, processes, people, places, systems, and devices for various purposes in energy management and optimization.

**Distributed Data Ecosystems**: Collections of data platforms that capture and manage their own data, usually inputted to local services for tailored applications, fundamental to the CEEDS architecture.

**DSO (Distribution System Operator)**: Entities responsible for operating, maintaining, and developing the distribution network for electricity, ensuring secure and reliable energy supply.

**EMRSP (Electro Mobility Roaming Service Provider)**: Organizations that provide interoperability among different e-mobility service providers, facilitating seamless electric vehicle charging across networks.

**EMSP (e-Mobility Service Provider)**: Companies that offer services to electric vehicle users, including charging and billing.

**Energy Data Analytics**: The process of analysing large datasets to uncover patterns, correlations, market trends, customer preferences, and other useful information to make informed decisions in the energy sector.

**Energy Efficiency**: The goal to reduce the amount of energy required to provide products and services, enhancing energy conservation in processes, buildings, machines, and devices.

**Energy Storage Systems (ESS)**: Technologies used for storing energy for later use, including batteries, flywheels, pumped hydro storage, and thermal storage, playing a critical role in balancing supply and demand in the energy grid.

**ENTSO-E (European Network of Transmission System Operators for Electricity)**: An organization that represents European TSOs, promoting the development of an integrated national and cross-border transmission system to support the EU's energy goals.

**EV (Electric Vehicle)**: Vehicles that use one or more electric motors for propulsion, relying on battery storage for energy.

**EVCI (Electric Vehicle Charging Infrastructure)**: The set of hardware, software, and services that provide electric energy for the recharging of electric vehicles.

**EVU (Electric Vehicle User)**: Individuals or entities that own or operate electric vehicles.

**Federated Data Space**: An overarching layer that indexes data from multiple distributed data ecosystems, making it discoverable and facilitating a marketplace for trading both data and data services in CEEDS.

**Flexibility Service Provider (FSP)**: Entities that aggregate and manage flexibility services from DERs or demand response to provide valuable services to the grid, such as balancing and congestion management.

**GDPR (General Data Protection Regulation)**: European Union regulation that sets guidelines for the collection and processing of personal information from individuals who live in the European Union.

**IEC (International Electrotechnical Commission)**: An international standards organization that prepares and publishes international standards for all electrical, electronic, and related technologies.

**Identity Management**: Enables the identification of data space participants, connectors, and trusted data providers, crucial for authorization mechanisms in CEEDS.

**Interoperability**: The ability of different systems, devices, applications, and services to work together within and across organizational boundaries to meet the diverse needs of users.

**IoT (Internet of Things) in Energy**: The network of physical devices, vehicles, home appliances, and other items embedded with electronics, software, sensors, actuators, and connectivity which enables these objects to connect and exchange data, enhancing operational efficiency, and energy management.

**Log**: Used to log information or store data about data usage, incidents, and activities within the data space, associated with the "Provenance & Traceability" building block in CEEDS.

**Microgrid**: A localized group of electricity sources and loads that normally operates connected to and synchronous with the traditional centralized grid (macrogrid), but can also disconnect to "island mode" and function autonomously as physical or economic conditions dictate.

**Metering**: The process of measuring energy consumption or production, critical for enabling high-level, real-time monitoring requirements managed by service providers within CEEDS. It supports the digitalization and efficient operation of energy markets.

**OEM (Original Equipment Manufacturer)**: a company that produces parts and equipment that may be marketed by another manufacturer.

**O&M (Operation and Maintenance)**: Activities associated with operating and maintaining energy systems and infrastructure to ensure they function efficiently and effectively.

**OCPP (Open Charge Point Protocol)**: An application protocol for communication between electric vehicle charging stations and a central management system, also known as a charge point operator.

**PV (Photovoltaic)**: Technology that converts light into electricity using semiconducting materials that exhibit the photovoltaic effect, widely used in solar panels.

**Publication & Discovery**: Acts as a catalogue for the data products available within CEEDS, managing self-descriptions and facilitating the discovery of data products by potential users.

**RES (Renewable Energy Sources)**: Energy sources that are replenished at a faster rate than they are consumed, such as solar, wind, hydro, and biomass.

**SAREF (Smart Appliances REFerence ontology)**: A shared model of consensus that facilitates the interoperability of smart appliances, promoting the integration and communication between different devices and systems.

**SCADA (Supervisory Control and Data Acquisition)**: A control system architecture comprising computers, networked data communications, and graphical user interfaces for high-level process supervisory management, while also allowing other software applications to perform essential process control.

**SGU (Significant Grid User)**: the existing and new power generating facility and demand facility deemed by the TSO as significant because of their impact on the transmission system in terms of the security of supply, including provision of ancillary services.

**Smart Grids**: Electricity networks that use digital technology to monitor and manage the transport of electricity from all generation sources to meet the varying electricity demands of end users.

**Smart Grid Architecture Model (SGAM)**: Conceptual framework designed to support the visualization, design, and analysis of smart grid systems, ensuring interoperability and standardization. It organizes the smart grid into three dimensions: domains, zones and layers.

**Smart Meters**: Electronic devices that record consumption of electric energy in intervals of an hour or less and communicate that information back to the utility for monitoring and billing.

**SPG (Service Providing Group)**: Entities or consortia that offer a range of services, potentially across different sectors, leveraging collective capabilities to meet diverse customer needs.

**SPU (Service Providing Unit)**: The individual operational units within a service providing group, each responsible for delivering specific services or functions.

**Submetering**: The measurement of energy use beyond the primary utility meter, allowing for detailed tracking of energy consumption or production at a granular level within premises. Integrated into the European regulatory framework, it enables multiple Flexibility Service Providers (FSPs) and suppliers to operate behind a final customer's connection point.

**Sustainable Energy Transition**: The process of shifting from fossil fuel-based systems of energy production and consumption to renewable energy sources, improving energy efficiency and reducing greenhouse gas emissions.

**Trust Framework**: A set of building blocks, including "Access & Usage Policies and Control" and "Identity Management," ensuring a trusted data ecosystem within CEEDS.

**TSO (Transmission System Operator)**: Entities responsible for transporting electricity over long distances via high-voltage power lines, ensuring the stability and reliability of the electrical grid.

**Virtual Power Plants (VPPs)**: A cloud-based distributed power plant that aggregates the capacities of heterogeneous Distributed Energy Resources (DER) for the purposes of enhancing power generation, as well as trading or selling power on the electricity market.

**Vocabulary Hub**: Provides endpoints for seamless communication with data space connectors and infrastructure components, storing and documenting vocabularies, ensuring compliance within CEEDS.

*Source: chapter 13, lines 3455–3659. 55 entries.*

---

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `CEEDS-STD-01` | A description of DSSC structured into a reference part and a pattern part is recommended by current standards on reference architectures (ISO/IEC/IEEE 42042 - reference architecture, ISO/IEC 40131 - guidance for reference architecture). | recommended | ch.1 §1.1, `Blueprint_CEEDS_v3.0.txt:228-232` |
| `CEEDS-STD-02` | It is recommended that the European Commission start a transversal task force between the data space architects in various initiatives to enable this alignment. | recommended | ch.1 §1.1, `Blueprint_CEEDS_v3.0.txt:231-233` |
| `CEEDS-STD-03` | The Technology deployment dimension offers specifications on adopted standards or required software components, as identified in the energy domain through the Smart Grid Architecture Model (SGAM). | informative | ch.2, `Blueprint_CEEDS_v3.0.txt:289-291` |
| `CEEDS-STD-04` | The participation of single users is defined in the CEEDS through the Harmonised Electricity Market Role Model (HEMRM). | informative | ch.2 §2.1, `Blueprint_CEEDS_v3.0.txt:313-315` |
| `CEEDS-STD-05` | End-to-end interoperability of demand side flexibility data is to be ensured through harmonised ontologies, as defined in the Common Information Model (CIM). | informative | ch.3 §3.6, `Blueprint_CEEDS_v3.0.txt:1315-1317` |
| `CEEDS-STD-06` | The proposed model reflects the concept of DERA 3.0 (Data Exchange Reference Architecture 3.0), defined in the Bridge Data Management WG based on SGAM. | informative | ch.4, `Blueprint_CEEDS_v3.0.txt:1345-1350` |
| `CEEDS-STD-07` | The distributed data exchange platforms layer is in line with the key applications and functions defined in the SGAM. | informative | ch.4, `Blueprint_CEEDS_v3.0.txt:1352-1355` |
| `CEEDS-STD-08` | Data space connectors typically use standardized data exchange protocols to facilitate the transfer of data between different systems. | informative | ch.4, `Blueprint_CEEDS_v3.0.txt:1455-1457` |
| `CEEDS-STD-09` | Bilateral exchange of traded data among two data exchange platforms is based on REST or Pub-Sub APIs. | informative | ch.4, `Blueprint_CEEDS_v3.0.txt:1479-1481` |
| `CEEDS-STD-10` | DCAT (Data Catalog Vocabulary) is recommended as a publisher to describe datasets and data services. | recommended | ch.4 §4.1, `Blueprint_CEEDS_v3.0.txt:1599-1600` |
| `CEEDS-STD-11` | The vocabulary module is expected to be reliant on IEC (CIM, 61850, COSEM, etc.) standards. | informative | ch.4 §4.1, `Blueprint_CEEDS_v3.0.txt:1600-1612` |
| `CEEDS-STD-12` | The vocabulary module is expected to be reliant on ETSI (SAREF, etc.) standards. | informative | ch.4 §4.1, `Blueprint_CEEDS_v3.0.txt:1600-1612` |
| `CEEDS-STD-13` | The catalogue follows as much as possible the FAIR (Findable, Accessible, Interoperable, Reusable) principles. | should | ch.4 §4.1, `Blueprint_CEEDS_v3.0.txt:1658-1659` |
| `CEEDS-STD-14` | An example of a centralized or distributed catalogue implementation could be the Metadata Broker specifications provided by IDSA. | informative | ch.4 §4.1, `Blueprint_CEEDS_v3.0.txt:1670-1675` |
| `CEEDS-STD-15` | The control plane can be standardized at a high level, incorporating common standards for identification and authentication. | may | ch.7 §7.1.1.1, `Blueprint_CEEDS_v3.0.txt:2763-2764` |
| `CEEDS-STD-16` | The data plane may vary across different data spaces, adapting to diverse data exchange requirements. | may | ch.7 §7.1.1.1, `Blueprint_CEEDS_v3.0.txt:2764-2766` |
| `CEEDS-STD-17` | JSON is the main reference data interchange format. | informative | ch.7 §7.1.1.3, `Blueprint_CEEDS_v3.0.txt:2805-2807` |
| `CEEDS-STD-18` | The use of JSON-LD, which serializes linked data in JSON, is the specific proposed solution. | recommended | ch.7 §7.1.1.3, `Blueprint_CEEDS_v3.0.txt:2807-2808` |
| `CEEDS-STD-19` | The dataspace protocol ensures fundamental technical interoperability for participants, a prerequisite for joining any data space. | must | ch.7 §7.1.1.4, `Blueprint_CEEDS_v3.0.txt:2830-2832` |
| `CEEDS-STD-20` | The dataspace protocol aims to define the minimum standard of communication so that each actor manages to communicate with other connectors. | informative | ch.7 §7.1.1.4, `Blueprint_CEEDS_v3.0.txt:2832-2834` |
| `CEEDS-STD-21` | The CEEDS relies on the harmonization and usage of prominent standards-based data models and ontologies. | informative | ch.7 §7.1.2, `Blueprint_CEEDS_v3.0.txt:2848-2853` |
| `CEEDS-STD-22` | The CGMES Conformity Assessment Scheme (CAS), developed by ENTSO-E, is highlighted as an example of conformity assessment in the Energy domain. | informative | ch.7 §7.1.2, `Blueprint_CEEDS_v3.0.txt:2853-2855` |
| `CEEDS-STD-23` | In data spaces where there is data exchange, approaches based on data ontology are a requirement in order to avoid silos. | must | ch.7 §7.1.2, `Blueprint_CEEDS_v3.0.txt:2856-2858` |
| `CEEDS-STD-24` | By adhering to semantic and syntactic standards, open data sources can align their data structures and semantics. | informative | ch.7 §7.1.2, `Blueprint_CEEDS_v3.0.txt:2879-2881` |
| `CEEDS-STD-25` | Ten building blocks have been defined along the SGAM layers to address the governance of interoperability. | informative | ch.7 §7.1.3, `Blueprint_CEEDS_v3.0.txt:2886-2891` |
| `CEEDS-STD-26` | The inclusion of a 6th SGAM layer, named "framework" layer, is proposed. | informative | ch.7 §7.1.3, `Blueprint_CEEDS_v3.0.txt:2903-2907` |
| `CEEDS-STD-27` | IntMAS has been modelled alongside proven management systems such as ISO 9001, ISO 14001 or EMAS. | informative | ch.7 §7.1.4, `Blueprint_CEEDS_v3.0.txt:3129-3133` |
| `CEEDS-STD-28` | The proposed CEEDS architecture is consistent with reference architectures used in the energy domain such as SGAM and Bridge DERA. | informative | ch.8, `Blueprint_CEEDS_v3.0.txt:3189-3192` |
| `CEEDS-STD-29` | Further improvements to the CEEDS blueprint should build on the CEI Sphere Hourglass© model. | should | ch.8, `Blueprint_CEEDS_v3.0.txt:3214-3216` |
| `CEEDS-STD-30` | The Hourglass will create a pathway to standardisation through submission to the 2026 standardisation rolling plan and to ISO/IEC JTC 1/SC 41. | informative | ch.8, `Blueprint_CEEDS_v3.0.txt:3216-3221` |

---

## Open questions

Ambiguities, inconsistencies and gaps found in the source. These are recorded, not resolved.

1. **The energy standards are named once, in a single sentence, and never normatively.** `IEC 61970`, `IEC 62325 ESMP`, `IEC 62746`, `IEC 61850-7`, `OCPP` and `Open Data Protocol (OData)` occur in exactly one sentence of §7.1.2 (lines 2848–2853), introduced by "such as", inside the clause "the CEEDS relies on the harmonization and usage of prominent standards-based data models and ontologies". No version, edition, profile or conformance obligation is given for any of them. A conformance benchmark built from this document cannot say *which edition* of `IEC 61970` a CEEDS implementation must use, or what "relies on" obliges an implementation to do.

2. **`IEC 61850` is never written as a whole.** The document gives only the bare number `61850` inside a parenthetical (line 1600) and the part `IEC 61850-7` (lines 2851–2852). It is not stated whether the parenthetical reference means the full IEC 61850 series or the same part 7.

3. **`DERA 3.0` versus `DERA 3.1`.** The architecture chapter builds on `DERA 3.0` (line 1348) with a footnote to one EU publication; §7.1.3 works from the `DERA 3.1 model` (line 2886) with a different reference ([11]). The document never says whether the architecture of chapter 4 has been revisited against 3.1.

4. **Four spellings of one protocol.** `dataspace protocol`, `Dataspace Protocol`, `Data Space Protocol (DSP)` and `IDS Dataspace Protocol` all appear, none of them cross-referenced to the others. Since this is the one thing the blueprint calls "a prerequisite for joining any data space", the ambiguity matters.

5. **Five spellings of one reference architecture model.** `IDS RAM`, `IDS-RAM v4`, `IDSA RAM v4`, `IDSA Reference Architecture Model v4` and (in the reference list) `IDS-RAM 4`.

6. **`ISO/IEC JTC 1/SC 41` versus `ISO/IEC JTC1/SC41`** — body text and footnote 24 disagree on spacing.

7. **`Gaia-X` versus `GAIA-X`** — both capitalisations appear, sometimes in adjacent sentences (lines 2597 and 2609).

8. **`SAREF4ENER` and `OpenADR3.0` appear once each, only as reported project implementations.** Both occur exclusively in the SYNERGIES paragraph (line 1930), which describes what one EDSCP project's Vocabulary Hub supports. Neither is picked up by the semantic interoperability section, which names plain `SAREF` instead. It is not stated whether `SAREF4ENER` is intended as the CEEDS profile of SAREF.

9. **`CGMES` is never expanded**, appearing only inside "CGMES Conformity Assessment Scheme (CAS)". Likewise `ESMP` in `IEC 62325 ESMP`. Neither is in the List of Abbreviations.

10. **`HEMRM` is constitutive but undocumented internally.** The role model that "defines" the participation of single users in the CEEDS has no entry in either the List of Abbreviations or the Glossary; the only pointer is footnote 1 to an ENTSO-E web page.

11. **The Vocabulary Hub's standards commitment is stated as an expectation, not a rule.** "IEC (CIM, 61850, COSEM, etc.) and ETSI (SAREF, etc.) standards are what this vocabulary module is expected to be reliant on" (lines 1600–1612) is the strongest energy-standards statement in the architecture chapter, and it uses neither *must*, *should*, nor *recommended*. It is also the only place `COSEM` is named outside the abbreviations and glossary.

12. **The glossary and the abbreviations list disagree in coverage.** Ten entries in the List of Abbreviations have no glossary entry: `ADMS`, `BRP`, `BSP`, `DGA`, `EDSCP`, `EDIB`, `EMS`, `JASC`, `LEC`, `PaaS`. Conversely, twenty-eight glossary entries are not abbreviations at all: `Access & Usage Policies and Control`, `CEEDS`, `Contracting`, `Control Plane and Data Plane`, `Cybersecurity in Energy Systems`, `Data Space Connector`, `Data Spaces`, `Demand Response (DR)`, `Digital Twin Technology in Energy`, `Distributed Data Ecosystems`, `Energy Data Analytics`, `Energy Efficiency`, `Energy Storage Systems (ESS)`, `Federated Data Space`, `Identity Management`, `Interoperability`, `IoT (Internet of Things) in Energy`, `Log`, `Microgrid`, `Metering`, `Publication & Discovery`, `Smart Grids`, `Smart Meters`, `Submetering`, `Sustainable Energy Transition`, `Trust Framework`, `Virtual Power Plants (VPPs)`, `Vocabulary Hub`. The two chapters were evidently maintained independently.

13. **`[TURTLE]`, `[TRIG]` and `[JSON-LD]` are dangling reference markers.** They are bracketed in the style of the document's numbered reference list but have no entries in chapter 9 References, which is numbered `[1]`–`[16]`.

14. **"non-reputability"** (line 1878) appears where "non-repudiation" would be expected in a list of AS4 features ("repeatability, non-reputability, and auditability"). Recorded as written; not corrected.

15. **Semantic and syntactic conformance is asserted but not testable from this document.** The only conformity assessment scheme the blueprint names is the `CGMES Conformity Assessment Scheme (CAS)`, and it is named as "an example … in the Energy domain", not as a scheme CEEDS adopts.
