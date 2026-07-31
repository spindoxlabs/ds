# Cross-cutting concerns

> **Source** · DSSC Blueprint v3.0 › Key Concepts of Data Spaces
> **Documents** ·
> *Personal data and natural persons in data space design and operation*
> (`personal-data-and-natural-persons-in-data-space-design-an-aea68a.md`) ·
> *Cross-data space interoperability considerations in data space design and operation*
> (`cross-data-space-interoperability-considerations-in-data-081093.md`)

These are the two substantive documents of the "Key Concepts of Data Spaces" pane of the
DSSC Blueprint v3.0. They are grouped here because neither belongs to a single building
block: the first states what a data space has to take into account, across all of its
building blocks, in order to engage in trusted data exchange with natural persons and/or
with personal data in a compliant manner; the second states what a data space has to take
into account, across all of its building blocks, in order to interoperate with other data
spaces. Both are written as guidance to the data space designer and to the governance
authority, and both point into the technical, business and co-creation panes rather than
defining a capability of their own.

Upstream names neither document as a building block. Where a document refers to a building
block it is named here exactly as upstream names it.

---

## Personal data and natural persons in data space design and operation

> **Source** · DSSC Blueprint v3.0 › Key Concepts of Data Spaces › Personal data and natural persons in data space design and operation

### Scope and objectives

The document opens from the observation that data spaces technologies and practices have
emerged from the industrial domain and that, because of this history, most use cases focus
on trusted data sharing of business data between organisations (legal persons). In
practice, however, the use of Common European Data Spaces takes many forms and
configurations, and there are many use cases with natural persons involved in data
sharing, either as participants or data rights holders.

The document distinguishes two situations that it treats together:

- cases where the data shared falls directly under the GDPR's definition of personal data
  (which, the document states, includes pseudonymised data);
- data spaces that deal with anonymised personal data.

It states that explicitly addressing the needs of natural persons and the specifics of
personal data in data spaces leads to new use cases, but that it also imposes new
requirements to any data space that does so.

Its stated purpose is to elaborate on data space configurations and use case scenarios
that involve natural persons and/or personal data, to provide general guidance for use
cases that depend on natural persons as stakeholders and for use cases that involve
personal data, and to say how to manage the related requirements — described upstream as
*legal, governance, business, or technical*. The sections that follow it are introduced as
identifying "what considerations should be taken into account from and in further
implementation of the data space building blocks".

> **Note on force** · The document frames its own content as *considerations* for the data
> space designer. Individual statements inside it are nonetheless modal ("must be able to
> deal with", "needs to accommodate", "requires that"), and are recorded below with the
> force the source gives them.

### How natural persons can be involved

The document notes first that natural persons can act in the role of a data provider or a
data user, or both. It then foresees four different ways in which natural persons can be
involved in use cases in a data space, reproduced here in the source's own structure:

- Natural person as a representative of a legal person participant of the data space
- Natural person as a stakeholder, such as a data subject or a data rights holder for data
  managed by a legal person participant
- Natural person as a participant
  - Participation directly or via a device or software agent, as data user
  - Participant directly as data provider
  - Participant directly as data subject
  - Participation indirectly via an intermediary
- Natural persons are not involved directly, but the use case involves anonymised data
  about natural persons, and the data subjects may be involved to respect data subject
  rights (e.g. the right to be informed)

Two determinations follow:

- **Whether personal data is involved is not a binary question.** In most data space use
  cases a natural person is involved in the data sharing in one way or another. Data space
  initiatives should therefore acknowledge that the answer is "not a simple yes or no, but
  may involve indirect dependencies and complex relationships that require more analysis
  and preparation". Personal data is defined in accordance with the GDPR. The document
  states explicitly that personal data does not require the inclusion of PII (personally
  identifiable information), i.e. pseudonymised data or personal data without PII needs to
  be considered as personal data.
- **Anonymised data is called out separately.** Because of the inherent risk of
  de-anonymisation or re-identification as a result of combining anonymised data from
  different sources, the document holds it helpful to distinguish whether the use case
  involves sharing anonymised data, and states that "there is a need to prove that data is
  adequately anonymised, especially when combined from different sources".

### Personal data and natural person related data sharing scenarios

The document describes four scenarios.

#### B2B data sharing personal data considerations

Business-to-Business (B2B) data sharing usually involves either non-personal data or
anonymised data. B2B data sharing that includes personal data requires that there are
legitimate grounds for data processing and that purpose limitation is applied — described
upstream as the *principles of data protection by design and default*. In the case of
consent as the legal basis, the data space needs to accommodate a cross-organisational
consent management capability (the source links this to **Access & Usage Policies
Enforcement**). There may be other legitimate grounds for sharing personal data, but these
cases require careful legal analysis and appropriate data protection measures such as
guaranteeing data subjects' rights to delete personal data.

In such scenarios the identity management capability (linked to **Identity & Attestation
Management**) must be able to deal with natural person identity. In some cases, an
intermediary (linked to **Intermediaries and Operators**) may be used to facilitate the
consent collection and subsequent data subject rights management — B2I2B, "where the
'I=intermediary' manages the interaction with the data subjects". Such services are called
**personal data intermediaries (PDI)**.

#### B2C data sharing

The example given of Business-to-Consumer (B2C) data sharing is a case where a group of
businesses shares their product data with their consumers. Consumers would act as data
space participants, namely data recipients or users. This case might require that there is
a unique enabling service provider that allows consumers to participate in the data space
directly or through an intermediary (B2I2C). B2C data sharing use cases do not necessarily
involve personal data sharing. The core challenges for the data space to address are with
consumer **participation management**.

#### C2B data sharing

As a Consumer-to-Business example, in some health, agriculture or mobility cases consumers
(or small business that effectively act as individuals) can act as data providers in a
data space; they can have a connected device with a system that produces data that
businesses can use for providing benchmarks, analytics or other services.

Depending on the use case, there might be need for consent management, unique natural
person participation management and registration, an appropriate organisational form and
governance, and/or separate anonymisation or aggregation services. The document states
that the inclusion of personal data provides significantly different use cases and
requirements, e.g. on how to describe the **data space offering**. It adds that often
these cases might be most practical to realise with an intermediary who acts on behalf of
the consumers as the data space participant (C2I2B), treated as a separate scenario.

#### C2I2B data sharing

The Consumer-to-Intermediary-to-Business scenario. An intermediary can aggregate natural
persons' data in order to share it either as anonymised data or to act as a consent
management service to collect and process data across consumers and businesses. Designing
such intermediary roles for the data space **must acknowledge that certain types of
intermediation activities fall under the scope of the Data Governance Act**.

#### Summary table of data sharing scenarios and core challenges

Reproduced as upstream gives it. The upstream caption states that the table "summarises
the different scenarios for trusted data sharing that involves natural persons and/or
personal data, and the associated challenges for the data space initiative to address".

| Transaction object: Sharing roles: | Personal data | Non-personal data or anonymised data |
|---|---|---|
| B2B | Address the legal basis for personal data sharing, by consent or other legal bases. | For anonymised data: prepare to demonstrate how data is and stays anonymised across use cases. Expect natural persons as representatives to exercise data subject rights. |
| B2C | [Practically not relevant scenario.] | Manage consumer participation in the data space. Is a special enabling service provider needed for connecting to the consumer? |
| C2B | Manage direct participation of natural persons and address the legal basis for personal data processing. | A legal basis to anonymise and a proper anonymisation capability or service is needed. |
| C2I2B | Intermediary must have means to manage consent or other legal grounds for handling the exchange of personal data on behalf of natural persons. | Intermediary must have an anonymisation capability that can proof effective anonymisation in cross-organisational data processing. |

### Legal instruments, defined terms and roles

The document names the following instruments and terms. Instrument names are kept
verbatim; the document cites no article numbers.

| Instrument / term | As the source uses it | Normative force |
|---|---|---|
| GDPR | Source of the definition of personal data ("where personal data is defined in accordance with the GDPR"); the definition "includes pseudonymised data". | referenced |
| Data Governance Act | "certain types of intermediation activities fall under the scope of the Data Governance Act" — to be acknowledged when designing intermediary roles. | required (must acknowledge) |
| PII (personally identifiable information) | Personal data does not require the inclusion of PII; pseudonymised data or personal data without PII needs to be considered as personal data. | referenced |
| data subject | Natural person as a stakeholder; also as a participant directly ("Participant directly as data subject"); data subject rights are to be respected, e.g. the right to be informed, and the right to delete personal data is named as an example of an appropriate data protection measure. | role |
| data rights holder | Natural person as a stakeholder for data managed by a legal person participant. | role |
| data provider / data user | "natural persons can act in the role of a data provider or a data user, or both". | role |
| data recipient / data user (B2C) | In B2C, "consumers would act as data space participants, namely data recipients or users". | role |
| personal data intermediary (PDI) | Intermediary service that facilitates consent collection and subsequent data subject rights management (B2I2B). | role |
| principles of data protection by design and default | Named as the principles behind requiring legitimate grounds and purpose limitation in B2B personal data sharing. | referenced |

> **Ambiguous:** The document does not use the GDPR roles *controller* or *processor*, and
> cites no GDPR article numbers. It refers to "legitimate grounds for data processing",
> "the legal basis", "consent as the legal basis" and "other legal bases" without mapping
> them to GDPR provisions.

### Conclusions for the data space designer

The use case scenarios involving natural persons or personal data are described as quite
diverse, with capability and governance requirements that vary significantly. The data
space designer should prepare for and learn about these scenarios if the scope of the data
space use cases involve anything beyond the pure B2B transactions with business data. The
document warns that building new capabilities, involving intermediaries, or changing the
participation management or governance frameworks later in the lifecycle of a data space
may be hard or impossible, and concludes that for these reasons the scenarios should be
identified and prepared in the early phase of the data space design, as presented in the
**co-creation method**.

---

## Cross-data space interoperability considerations in data space design and operation

> **Source** · DSSC Blueprint v3.0 › Key Concepts of Data Spaces › Cross-data space interoperability considerations in data space design and operation

### Scope and objectives

The document argues that seamless data exchange across domains is crucial for unlocking
innovation, optimizing infrastructure, and fostering economic growth, and that
interoperability between the data spaces "is a cornerstone of the digital single market".
It gives examples of value across data spaces — combining energy and mobility data;
combining agriculture, energy and climate data for environmental challenges; combining
solar energy production data with weather data (a use case named as under work in the
TRUSTEE project); combining traffic data with CO2 emissions measurement data to optimize
air quality in a city (named as under work in the DS2 project). It points to the position
paper *Synergies of Data Spaces* for more on synergies. These are illustrations, not
requirements.

Two definitions are set out in the document as highlighted statements:

- **Cross-data space interoperability** "refers to the ability of participants to
  seamlessly access and/or exchange data across two or more data spaces."
- **Cross-data space use cases** "refer to settings in which participants of multiple data
  spaces aim to create value from data sharing across these multiple data spaces."
- **A "federation of data spaces"** "is a data space that enables seamless data
  transactions between the participants of multiple data spaces based on agreed common
  rules, typically set in a governance framework." (Given under *Future work*; see below.)

The document states that when you build your data space you can assume that some of your
data space participants join also other data spaces, and that in this scenario **it is the
participant's responsibility** to comply with the rules of different data spaces, and set
up participant agent services to join multiple data spaces. A data space may require its
participants to comply with its specific technological, business and contractual
requirements, but it can also help them by considering interoperability with other data
spaces as a leading principle in its design and architectural decisions.

Interoperability is presented as non-binary: "instead of a binary choice whether a data
space is interoperable or not with other data spaces, we talk of a variety of design and
architectural choices that fosters cross-data space interoperability". ISO/IEC 19941 is
cited as providing a comprehensive overview of the various facets of interoperability.

The stated benefits of prioritizing interoperability — reduced participant cost of joining
and using the data space, attractiveness to potential participants, economies of scale,
consistent and familiar user experience, consistency in functionalities, vocabulary and
processes, reduced participant confusion, uncertainty and errors, faster learning, better
decision-making, transparency, control, increased trust — are given as motivation, not as
obligations.

### Interoperability-by-design

Interoperability-by-design "refers to a principle that considers interoperability as a key
requirement of the data space design and operation throughout all stages of its
lifecycle". The document states that following this principle is the key enabler of
collaboration between data spaces, and later that it "is the most important enabler of
collaboration between data spaces".

The document lists elements that foster interoperability, "while acknowledging that the
list is not exhaustive":

- **Common terminology, models and practices** — aimed at building a common language and
  understanding of data spaces and related concepts. Examples given: the DSSC assets (such
  as the DSSC blueprint, the glossary, and the design principles); industry-specific
  frameworks, blueprints and practices.
- **Recommended standards, protocols, common quality, security and other requirements,
  legal, governance and business templates and guidelines** — these enable developing an
  interoperable data space, "a data space capable of collaborating with other data spaces
  by design". Choosing the recommended standards and other elements makes it easier to
  achieve interoperability across data spaces.
- **Contribution to the data space community** — the community is said to consist of
  various data space initiatives, Standard Development Organisations, open source
  communities, national governments, the European Union, the DSSC community and its
  stakeholders, among others.

The section closes: "We highlight the importance of following the recommended standards,
and the creation of standards when relying upon the same interoperability measures."

### The importance of interoperability governance

Interoperability and synergy-enabling design are said to require strategic decisions in
all lifecycle stages of the data spaces, with the *Data Spaces' Synergies* position paper
cited for per-stage considerations.

The document states there is a need for **interoperability governance**: "developing and
maintaining a strategy, mechanisms, and processes that ensure interoperability within the
data space and across data spaces". Interoperability governance affects decisions related
to most aspects of data space design and operation. Developing and maintaining a strategy
that enables adding, modifying and deleting elements of interoperability governance
ensures prioritizing interoperability not only in design, but also in the operation stage.

Two explicit recommendations follow: to develop and maintain a strategy, mechanisms, and
processes that consider interoperability within the data space and across data spaces in
the decision making related to many aspects of data space design and operation; and to
include this in the rulebook of the data space initiative and work with the data space
governance authorities maintaining the rulebooks the data space seeks to be interoperable
with.

### Investing in interoperability is a strategic decision

Given the nascent nature of a data spaces market, the document identifies a business
decision about how to invest upfront to ensure flexibility for future interoperability
needs, requiring a balance between the benefits of cross-data space collaboration and the
risks, costs and sacrifices required from the governance authority to develop this
capability. It notes an asymmetry: "While the benefits of prioritizing interoperability
can occur only later in a data space lifecycle, the potential investment might be made
much earlier." It recommends, when designing a data space, to consider that participants
might operate in multiple contexts and might want to combine data across data spaces.

### Cross-data space use cases

A cross-data space use case is "a specific setting in which participants of multiple data
spaces aim to create value from data sharing"; cross-data space interoperability is an
enabler of developing and operating them. Developing a joint use case between data spaces
requires similar steps as developing a data space use case, with the elements of the **Use
Case Development building block** cited for details. The European Tourism Data Space and
the European Mobility Data Space are given as an example of two data spaces with a
specified joint use case.

When organisations need to exchange data products and services across two or more data
spaces, the document gives "two main options":

- **A joint use case built by the participating organisations.** The organisations join the
  data spaces as participants, which allows them to exchange data products and services
  across all the data spaces whose governance framework they comply with. Data spaces that
  follow the interoperability-by-design principle help their participants to develop these
  cross-data space use cases easier.
- **A joint use case built by the governance authorities.** The governance authorities can
  build shared functionalities between their data spaces that enables their participants to
  exchange data and services across data spaces without them being participants also of the
  other data spaces. In this case the data space governance authorities will negotiate and
  agree on the rules for collaboration. Typically this requires developing or outsourcing
  additional technical and governance components and processes (e.g., contracts between the
  data spaces, participation management processes).

"In its simplest form, the additional rules to address joint use cases can be restricted to
the joint use case participants", in which case the scope of the rules does not necessarily
impact participants not participating in the joint use case.

### Business considerations of collaborating data spaces

**Collaboration between data spaces** is defined as the situation where two or more data
spaces enable their participants to carry out data transactions across multiple data
spaces, while being participants of only one of the data spaces. It requires establishing
a shared understanding and common rules for technical, business, legal and governance
aspects. Ways to achieve this listed by the source:

- Following the interoperability-by-design principle — "choosing recommended standards,
  protocols, mechanisms and processes, the regulations, the DSSC guidelines and
  recommendations, and being active in the data space community".
- The governance authorities of the data spaces can negotiate and set common rules for
  collaboration; for example, they can agree on some of the common supported standards.
- The governance authorities of the data spaces can identify non-interoperable components,
  services and processes and provide a solution for harmonisation.

The governance authorities can decide to develop the needed functionalities themselves or
buy services from intermediaries that operate in multiple data spaces; the two options can
be used in combination.

On scope: where participants spot a business opportunity or use case requiring data
available in a different data space, the document gives two main options — to expand the
scope of the data space and create room for new participants that have the data required
(in which case the data space would either insist that new participants follow the rules
as elaborated in the rulebook, or make adjustments to the rulebook as per the governance
structure of the data space, "as addressed in the business model building block"), or to
create an agreement with another data space, which in some cases might require alignment
of the rulebooks for each data space. The second option is noted as potentially
challenging depending on the monetization strategy of each data space and other governance
issues around data protection, and as complicated by the "multisided" nature of data space
organisations.

### Technical considerations of collaborating data spaces

The section states that interoperability-by-design can be achieved if rules and standards
introduced in **Building on Top of Foundational Standards** and in the **Technical Building
Blocks** are followed, and applied when implementing the capabilities exposed clustered in
the technical services introduced in **Services for Implementing Technical Building
Blocks**. Per building block, the source says:

- **Data Models_archived** specifies that the first step in (re)using data models from
  other data space is to find and access them. "Therefore, data spaces should be able to
  exchange their data models in a standardized manner to establish agreements on their
  usage, with vocabulary services federated between them."
- **Data Exchange_old** states that specific protocols for data exchange needs to be
  available when connecting data spaces. The governance of the data spaces will define what
  are the accepted protocols for the data exchange between the federated data spaces and how
  to make it available to the different participants. "There should be a list of accepted
  data exchange protocols and its versions available at the start of the technical
  federation of data space independently if this is created by a direct connection or by
  means of an intermediary entity." Eventually a specific data model for the data exchange
  protocols could be created to speed up the negotiation of the data transmission between
  data spaces.
- **Provenance & Traceability** — "It is also important to enable the interchange of
  provenance information generated in different systems and under different contexts. The
  use of W3C PROV-O vocabulary introduced in Provenance & Traceability supports this
  aspect."
- **Data, Services, and Offerings Descriptions** — "The use of a general standard as W3C
  DCAT to generate metadata descriptions of data, services and offerings entails a common
  understanding of such descriptions from participants coming from different data spaces".
- **Publication and Discovery** presents different scenarios to publish centralized or
  decentralized catalogues. "In both cases, the federation of catalogues could be
  considered, but this aspect will be covered in the next version of this building block".
- **Value creation services** depend very much on the specificities of each data space, its
  own objectives and uses. Following the guidelines included in this building block,
  regarding the proposed taxonomy to classify services and DCAT (or future extensions) to
  describe them, "can facilitate their use in cross-data space use cases".

On top of the standards included in the specific building blocks, the document says it is
worth considering the ISO/IEC 19941:2017 series on "Information technology — Cloud
computing — Interoperability and portability", given their relevance for addressing
interoperability and portability, and that they can provide good guidance to the governance
authorities to enable interoperable data spaces. The section closes with an explicit
recommendation to follow the standards, rules and guidelines introduced in **Building on
Top of Foundational Standards** and in the **Technical Building Blocks**.

> **Ambiguous:** the two building block names *Data Models_archived* and *Data Exchange_old*
> appear with those suffixes in the source text of this section. They are reproduced
> verbatim here. See "Open questions".

### Legal aspects of collaborating data spaces

#### Legal interoperability by design: enablers of cross-data space interoperability

Similar rules within data spaces, or measures to address specific legal requirements, can
have a positive impact on interoperability between different data spaces. For this reason,
smooth collaboration between data spaces "requires not only a careful investigation of the
applicability of the laws, but also implementation of similar measures to facilitate the
compliance". The **Data Privacy Vocabulary** is given as an example of something that "can
help to identify relevant regulatory requirements and related requirements". Despite
having discretion on how to address some of the compliance requirements, this approach
enables more seamless collaboration between data spaces on various levels.

#### Legal requirements for cross-data space interoperability

The document states that in order to achieve a digital single market, regulations may
impose a number of technical or organisational **requirements** to ensure interoperability
— both 'within' and 'between' data spaces — and that at the moment there are **two EU legal
frameworks explicitly addressing these issues**: the **Data Act** and the recently adopted
**European Health Data Space Regulation (EHDS)**.

- **Article 33 of the Data Act** "lays down essential requirements regarding
  interoperability of data, of data sharing mechanisms and services, as well as of Common
  European Data Spaces". The requirements apply to participants of Common European Data
  Spaces, offering data or data services to other participants, and so "might be of
  relevance for facilitating smooth cooperation between different data spaces". The
  document adds that these requirements "can have a generic nature or concern specific
  sectors, and shall take fully into account the interrelation with requirements arising
  from other Union or national law".
- **Chapter IV of the EHDS** "establishes legal, technical, and organisational frameworks
  for the secondary use of health-related data". While primarily focused on regulating data
  sharing to enhance healthcare within the Union, the EHDS Regulation extends its influence
  beyond the health sector and "is poised to significantly shape other Common European Data
  Spaces across multiple dimensions, both directly and indirectly". In the EHDS regulation,
  the "direct" interoperability requirements concern the planned implementing acts to be
  adopted by the European Commission; these implementing acts lay down the common
  specifications for the interoperability and architecture concerning not only
  **HealthData@EU** but also other Common European Data Spaces relevant for health (such as
  environmental or agricultural data spaces).

The **Regulatory Compliance building block** is cited for more information about navigating
relevant legal provisions and requirements for data spaces.

#### Agreements between data spaces

Collaborating data spaces might achieve interoperability by agreeing to common taxonomies
(e.g., by providing harmonised definitions in the various Agreements constituting the
**Contractual Framework**), procedures (e.g., dispute resolution mechanisms, onboarding,
offboarding), or internal rules (e.g., using common General Terms & Conditions to the
extent that similarities across data spaces exist). Using common resources when designing
the contractual framework is also said to be conducive to interoperability; the examples
given are the **SITRA Rulebook for a Fair Data Economy** and the **DSSC Blueprint**.

Collaboration can be achieved both by agreeing to common standards and by more formal —
contractually binding — agreements. Common standards "could be represented by Code of
Practices, to which parties may decide to agree and commit to comply, whether sectorial or
not, or to refer to common external resources for the interpretation of the legal terms of
the various contracts of the Contractual Framework"; the example given is the **ALI-ELI
Principles for a Data Economy - Data Transactions and Data Rights**. These are described as
informal mechanisms to produce legal interoperability, which "would normally need to find
at least indirect expression in the Contractual Framework".

A different approach — "although coming with a higher level of transaction costs and
reduced flexibility" — is to develop explicit agreements between data space initiatives.
This "would require to create a higher level of governance — rules regulating the conduct
of the parties — not only within an individual data space but also between different data
spaces, and translate these rules in legally enforceable agreements". The goal should be to
create common elements — "or better, common obligations and rights" — across different data
spaces, potentially covering any aspect currently part of the **Contractual Framework**,
from data sharing agreements to general terms & conditions. The example given is to use or
establish a limited set of modular terms and conditions across different data spaces, i.e.
to standardise the data licences used to share data.

An effective alternative to drafting one's own agreements is to agree — which can be in the
form of a legal agreement — on the common elements, such as standards and licences, relying
directly on existing standardised and commonly used licences (the **Data License Picker**
is given as an example). When doing this, "it is nonetheless recommended that an assessment
is carried out on the legal status of the data being shared". The illustration given:
Creative Commons licences assume that the data are protected by copyright; if the data
contains personal data, then a different licence may be necessary. A higher level of
contractual integration is noted to be more difficult to achieve the more different the
contexts in which the data spaces operate (e.g., different sectors or countries), and so
"interventions should thus be proportionate to the needs of the data spaces". Standardised
licences are nonetheless called "one of the most effective way to achieve
interoperability", especially where they benefit from a high level of adoption across
different data spaces.

"The first step towards legal interoperability is screening the laws and regulations to
identify the barriers to legal interoperability", with the **Regulatory Compliance**
building block given as a good starting point.

### Future work (informative)

The document marks this material explicitly as future work; none of it is stated as a
requirement.

**Federation of data spaces: a multi-faceted term.** The data space community sometimes
uses the term 'federations of data spaces'; the document states this is a topic it aims to
explore further in upcoming versions of the blueprint, and that the term can have several
meanings. Non-exhaustive technical examples given: a single data space can be considered as
a federation of its participants' systems; federation can refer to a federation of
different use cases' participants' systems; federation can refer to a federation of various
domains, countries or segments' participants' systems. Two summary statements are marked
out in the source:

- "From a technical perspective, a federation is enabled by joint services (federation and
  value creation) of the federated systems, and participant agent services that enable the
  federated systems to join a federation."
- "From a governance perspective, a federation is governed based on rules that are jointly
  agreed by the federated entities" — from a governance perspective, the document speaks of
  sovereign parties that agree on common rules for collaboration, typically set in a
  governance framework.

The key question posed is "federation of what?". The definition given is that a "federation
of data spaces" is a data space that enables seamless data transactions between the
participants of multiple data spaces based on agreed common rules, typically set in a
governance framework. Its explanatory notes state that the definition is evolving in the
data space community, and that a federation of data spaces is a data space with its own
governance framework, enabled by a set of shared services (federation and value creation)
of the federated systems, and participant agent services that enable participants to join
multiple data spaces with a single onboarding step.

**The role of service providers.** Service providers typically aim to serve multiple data
spaces, by providing participant agents, federation services and value creation services.
Through the standards recommended in the blueprint there is increasingly an economy of
scale for such providers. The **Data Governance Act** provides an 'EU Trusted Data
Intermediation Service Provider' label, allowing providers to showcase that they meet the
requirements stated in this act. Illustrations given: allowing organisations with a single
'connector' (i.e. a participant agent service) to connect to multiple data spaces; or
connecting participants from different business contexts to a single federation service.
The document states it aims to continue to explore this role.

**Possible governance aspects.** The key question raised is whether there is a need to set
up a governance authority of the federation of data spaces that develops, maintains and
enforces the common rules for collaboration. While developing a governance framework of the
federation of data spaces, there is a need to decide what decisions to make at the
federation of data spaces level, and which ones are left for the federated data spaces to
decide on. One option given: the federation of data spaces gives sovereignty to specific
participants to set up their own governance framework, where they can specify their "local"
rules that are compliant with the common rules set in the common governance framework of
the federation; the common governance framework can set general rules that are
contextualized or extended by the federated data spaces — for example, a minimum set of
supported standards to be supported by all federated data spaces, which some federated data
spaces can extend with standards specific to their own needs. In this example, the
association between the governance framework of the federated data spaces and the
Federation of Data Spaces is **inheritance** (the source refers to a Figure 3 for the
visualisation).

The four key questions the document suggests thinking through:

- Who develops, maintains and enforces the common rules between the data spaces?
- What rules have to be decided at the federation of data spaces level, and which ones
  require flexibility and decision-making at the federated data spaces level?
- What services will be provided at the federation of data spaces level, and which ones
  should be provided at the federated data spaces level?
- What are the processes and mechanisms for modifying the rules for collaboration between
  the data spaces?

### Conclusions

The document concludes that there is no single way to achieve interoperability within and
across data spaces; the options it lists each have their own advantages and disadvantages,
are not exclusive, and can be used in combination, tailored to the specific needs and
objectives of the data spaces. It repeats that following the interoperability-by-design
principle, and the guidelines and recommendations in the DSSC assets, is a key enabler of
interoperability.

### Standards, protocols and legal instruments

| Standard / instrument | Version / profile | Role in the source | Normative force |
|---|---|---|---|
| ISO/IEC 19941 | — | "provides a comprehensive overview of the various facets of interoperability" | referenced |
| ISO/IEC 19941:2017 series | 2017, "Information technology — Cloud computing — Interoperability and portability" | "it is worth considering" on top of the standards included in the specific building blocks; "can provide good guidance to the governance authorities to enable interoperable data spaces" | referenced |
| W3C PROV-O | vocabulary | Introduced in Provenance & Traceability; supports interchange of provenance information generated in different systems and under different contexts | referenced |
| W3C DCAT | "(or future extensions)" | Generating metadata descriptions of data, services and offerings; entails a common understanding of such descriptions across data spaces; also named for describing value creation services | referenced |
| Data Privacy Vocabulary | — | "can help to identify relevant regulatory requirements and related requirements" | referenced |
| Data Act | Article 33 | Lays down essential requirements regarding interoperability of data, of data sharing mechanisms and services, as well as of Common European Data Spaces; applies to participants of Common European Data Spaces offering data or data services to other participants | required |
| European Health Data Space Regulation (EHDS) | Chapter IV; planned implementing acts to be adopted by the European Commission | Establishes legal, technical, and organisational frameworks for the secondary use of health-related data; implementing acts lay down common specifications for interoperability and architecture concerning HealthData@EU and other Common European Data Spaces relevant for health | required (as law); implementing acts planned |
| Data Governance Act | — | Provides an 'EU Trusted Data Intermediation Service Provider' label | referenced |
| SITRA Rulebook for a Fair Data Economy | — | Common resource for designing the contractual framework | referenced |
| DSSC Blueprint | — | Common resource for designing the contractual framework; DSSC assets named as common terminology, models and practices (blueprint, glossary, design principles) | referenced |
| ALI-ELI Principles for a Data Economy - Data Transactions and Data Rights | Final Council Draft | Common external resource for the interpretation of the legal terms of the various contracts of the Contractual Framework | referenced |
| Code of Practices | — | Standards to which parties may decide to agree and commit to comply, whether sectorial or not | referenced |
| Data License Picker | — | Example of existing standardised and commonly used licences to rely on directly | referenced |
| Creative Commons licences | — | Illustration: they assume the data are protected by copyright; if the data contains personal data, a different licence may be necessary | referenced |

---

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its
requirements.* IDs in this page use the code `XCT` (cross-cutting) and are allocated
`DSSC-XCT-01` … `DSSC-XCT-62`.

Source references name the upstream document and the section number as the document itself
numbers it: `personal-data…aea68a.md` abbreviates *Personal data and natural persons in
data space design and operation*, `cross-data-space…081093.md` abbreviates *Cross-data
space interoperability considerations in data space design and operation*.

### Personal data and natural persons in data space design and operation

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-XCT-01` | A data space initiative should acknowledge that whether personal data is involved is not a simple yes or no, but may involve indirect dependencies and complex relationships that require more analysis and preparation. | should | `personal-data…aea68a.md` §2 |
| `DSSC-XCT-02` | Pseudonymised data, and personal data without PII, must be considered as personal data. | must | `personal-data…aea68a.md` §2 |
| `DSSC-XCT-03` | Where anonymised data is shared, there is a need to prove that data is adequately anonymised, especially when combined from different sources. | should | `personal-data…aea68a.md` §2 |
| `DSSC-XCT-04` | B2B data sharing that includes personal data requires that there are legitimate grounds for data processing. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-05` | B2B data sharing that includes personal data requires that purpose limitation is applied. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-06` | Where consent is the legal basis, the data space needs to accommodate a cross-organisational consent management capability. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-07` | Sharing personal data on legitimate grounds other than consent requires careful legal analysis. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-08` | Sharing personal data on legitimate grounds other than consent requires appropriate data protection measures, such as guaranteeing data subjects' rights to delete personal data. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-09` | In scenarios where personal data is shared, the identity management capability must be able to deal with natural person identity. | must | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-10` | An intermediary may be used to facilitate consent collection and subsequent data subject rights management (B2I2B); such services are called personal data intermediaries (PDI). | may | `personal-data…aea68a.md` §3.1 |
| `DSSC-XCT-11` | B2C data sharing might require a unique enabling service provider that allows consumers to participate in the data space directly or through an intermediary (B2I2C). | may | `personal-data…aea68a.md` §3.2 |
| `DSSC-XCT-12` | In B2C data sharing, the core challenges for the data space to address are with consumer participation management. | informative | `personal-data…aea68a.md` §3.2 |
| `DSSC-XCT-13` | In C2B data sharing there might be need for consent management. | may | `personal-data…aea68a.md` §3.3 |
| `DSSC-XCT-14` | In C2B data sharing there might be need for unique natural person participation management and registration. | may | `personal-data…aea68a.md` §3.3 |
| `DSSC-XCT-15` | In C2B data sharing there might be need for an appropriate organisational form and governance. | may | `personal-data…aea68a.md` §3.3 |
| `DSSC-XCT-16` | In C2B data sharing there might be need for separate anonymisation or aggregation services. | may | `personal-data…aea68a.md` §3.3 |
| `DSSC-XCT-17` | Designing intermediary roles for the data space must acknowledge that certain types of intermediation activities fall under the scope of the Data Governance Act. | must | `personal-data…aea68a.md` §3.4 |
| `DSSC-XCT-18` | B2B sharing of personal data: address the legal basis for personal data sharing, by consent or other legal bases. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-19` | B2B sharing of anonymised data: prepare to demonstrate how data is and stays anonymised across use cases. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-20` | B2B sharing of non-personal or anonymised data: expect natural persons as representatives to exercise data subject rights. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-21` | B2C sharing of non-personal or anonymised data: manage consumer participation in the data space. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-22` | C2B sharing of personal data: manage direct participation of natural persons. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-23` | C2B sharing of personal data: address the legal basis for personal data processing. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-24` | C2B sharing of non-personal or anonymised data: a legal basis to anonymise is needed. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-25` | C2B sharing of non-personal or anonymised data: a proper anonymisation capability or service is needed. | should | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-26` | C2I2B sharing of personal data: the intermediary must have means to manage consent or other legal grounds for handling the exchange of personal data on behalf of natural persons. | must | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-27` | C2I2B sharing of non-personal or anonymised data: the intermediary must have an anonymisation capability that can proof effective anonymisation in cross-organisational data processing. | must | `personal-data…aea68a.md` §3.4, summary table |
| `DSSC-XCT-28` | The data space designer should prepare for and learn about the natural-person and personal-data scenarios if the scope of the data space use cases involves anything beyond pure B2B transactions with business data. | should | `personal-data…aea68a.md` §4 |
| `DSSC-XCT-29` | The natural-person and personal-data scenarios should be identified and prepared in the early phase of the data space design. | should | `personal-data…aea68a.md` §4 |

### Cross-data space interoperability considerations in data space design and operation

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-XCT-30` | A participant joining multiple data spaces is responsible for complying with the rules of the different data spaces. | must | `cross-data-space…081093.md` §2.1 |
| `DSSC-XCT-31` | A participant joining multiple data spaces is responsible for setting up participant agent services to join multiple data spaces. | must | `cross-data-space…081093.md` §2.1 |
| `DSSC-XCT-32` | Interoperability-by-design — considering interoperability as a key requirement of the data space design and operation throughout all stages of its lifecycle — is the most important enabler of collaboration between data spaces. | informative | `cross-data-space…081093.md` §2.2 |
| `DSSC-XCT-33` | Follow the recommended standards, and create standards when relying upon the same interoperability measures. | recommended | `cross-data-space…081093.md` §2.2 |
| `DSSC-XCT-34` | There is a need for interoperability governance: developing and maintaining a strategy, mechanisms, and processes that ensure interoperability within the data space and across data spaces. | should | `cross-data-space…081093.md` §2.3 |
| `DSSC-XCT-35` | Develop and maintain a strategy, mechanisms, and processes that consider interoperability within the data space and across data spaces in the decision making related to many aspects of data space design and operation. | recommended | `cross-data-space…081093.md` §2.3 |
| `DSSC-XCT-36` | Include the interoperability strategy, mechanisms and processes in the rulebook of the data space initiative. | recommended | `cross-data-space…081093.md` §2.3 |
| `DSSC-XCT-37` | Work with the data space governance authorities maintaining the rulebooks the data space seeks to be interoperable with. | recommended | `cross-data-space…081093.md` §2.3 |
| `DSSC-XCT-38` | When designing a data space, consider that participants might operate in multiple contexts and might want to combine data across data spaces. | recommended | `cross-data-space…081093.md` §2.4 |
| `DSSC-XCT-39` | Where governance authorities build a joint use case, the governance authorities negotiate and agree on the rules for collaboration. | informative | `cross-data-space…081093.md` §3 |
| `DSSC-XCT-40` | The additional rules addressing a joint use case can be restricted to the joint use case participants, in which case they do not necessarily impact participants outside the joint use case. | may | `cross-data-space…081093.md` §3 |
| `DSSC-XCT-41` | Collaboration between data spaces requires establishing a shared understanding and common rules for technical, business, legal and governance aspects. | must | `cross-data-space…081093.md` §4.1 |
| `DSSC-XCT-42` | Data spaces should be able to exchange their data models in a standardized manner to establish agreements on their usage, with vocabulary services federated between them. | should | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-43` | Specific protocols for data exchange need to be available when connecting data spaces. | must | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-44` | The governance of the data spaces defines what the accepted protocols for data exchange between the federated data spaces are, and how to make them available to the different participants. | informative | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-45` | There should be a list of accepted data exchange protocols and their versions available at the start of the technical federation of data spaces, independently of whether the federation is created by a direct connection or by means of an intermediary entity. | should | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-46` | A specific data model for the data exchange protocols could be created to speed up the negotiation of the data transmission between data spaces. | may | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-47` | Enable the interchange of provenance information generated in different systems and under different contexts; the use of W3C PROV-O vocabulary supports this aspect. | should | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-48` | The use of a general standard as W3C DCAT to generate metadata descriptions of data, services and offerings entails a common understanding of such descriptions from participants coming from different data spaces. | informative | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-49` | The federation of catalogues could be considered for both centralized and decentralized catalogue publication scenarios. | may | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-50` | On top of the standards included in the specific building blocks, it is worth considering the ISO/IEC 19941:2017 series on "Information technology — Cloud computing — Interoperability and portability". | informative | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-51` | Follow the standards, rules and guidelines introduced in Building on Top of Foundational Standards and in the Technical Building Blocks. | recommended | `cross-data-space…081093.md` §5 |
| `DSSC-XCT-52` | Smooth collaboration between data spaces requires a careful investigation of the applicability of the laws. | must | `cross-data-space…081093.md` §6.1.1 |
| `DSSC-XCT-53` | Smooth collaboration between data spaces requires implementation of similar measures to facilitate the compliance. | must | `cross-data-space…081093.md` §6.1.1 |
| `DSSC-XCT-54` | Participants of Common European Data Spaces offering data or data services to other participants are subject to the essential requirements regarding interoperability of data, of data sharing mechanisms and services, as well as of Common European Data Spaces laid down in Article 33 of the Data Act. | must | `cross-data-space…081093.md` §6.1.2 |
| `DSSC-XCT-55` | The Article 33 Data Act requirements shall take fully into account the interrelation with requirements arising from other Union or national law. | must | `cross-data-space…081093.md` §6.1.2 |
| `DSSC-XCT-56` | Chapter IV of the EHDS establishes legal, technical, and organisational frameworks for the secondary use of health-related data; its planned implementing acts, to be adopted by the European Commission, lay down the common specifications for the interoperability and architecture concerning HealthData@EU and other Common European Data Spaces relevant for health. | informative | `cross-data-space…081093.md` §6.1.2 |
| `DSSC-XCT-57` | Collaborating data spaces might achieve interoperability by agreeing to common taxonomies, procedures, or internal rules. | may | `cross-data-space…081093.md` §6.2 |
| `DSSC-XCT-58` | Informal mechanisms for legal interoperability (common standards, Codes of Practice, common external interpretation resources) would normally need to find at least indirect expression in the Contractual Framework. | should | `cross-data-space…081093.md` §6.2 |
| `DSSC-XCT-59` | Developing explicit agreements between data space initiatives requires creating a higher level of governance — rules regulating the conduct of the parties both within an individual data space and between different data spaces — and translating these rules into legally enforceable agreements. | must | `cross-data-space…081093.md` §6.2 |
| `DSSC-XCT-60` | When relying directly on existing standardised and commonly used licences, an assessment should be carried out on the legal status of the data being shared. | recommended | `cross-data-space…081093.md` §6.2 |
| `DSSC-XCT-61` | Interventions towards contractual integration should be proportionate to the needs of the data spaces. | should | `cross-data-space…081093.md` §6.2 |
| `DSSC-XCT-62` | The first step towards legal interoperability is screening the laws and regulations to identify the barriers to legal interoperability. | should | `cross-data-space…081093.md` §6.2 |

---

## Open questions

Ambiguities, gaps and inconsistencies found in the two source documents. They are recorded,
not resolved.

**Personal data and natural persons in data space design and operation**

1. **No article-level legal citations.** The document names the GDPR and the Data Governance
   Act, but cites no article numbers of either, and does not name the GDPR roles
   *controller* or *processor*. It speaks of "legitimate grounds for data processing", "the
   legal basis", "consent as the legal basis" and "other legal bases" without mapping them
   to GDPR provisions. Article-level citations in this unit appear only in the cross-data
   space document (Article 33 of the Data Act; Chapter IV of the EHDS).
2. **Statements of "need" without a modal verb.** Several obligations are phrased as "there
   is a need to prove…", "there might be need for…", "a legal basis … is needed". They are
   recorded above as `should` / `may` according to whether the source qualifies them with
   "might"/"depending on the use case". A stricter reading of "there is a need to prove that
   data is adequately anonymised" as a `must` is defensible.
3. **The summary table cells are phrased as challenges, not obligations.** Its caption calls
   them "the associated challenges for the data space initiative to address", yet the cells
   are written as bare imperatives ("Address the legal basis…", "Manage consumer
   participation…"). Only the two C2I2B cells use "must". Rows `DSSC-XCT-18` … `-25` are
   therefore recorded as `should` and `-26`/`-27` as `must`.
4. **The B2C / personal data cell is empty of guidance**: "[Practically not relevant
   scenario.]", brackets in the original. No requirement is derived from it.
5. **Terminology drift on the consumer side.** §3.2 describes consumers as "data space
   participants, namely data recipients or users", while §2 enumerates the roles as "data
   provider or a data user". *Data recipient* is not otherwise defined in the document.
6. **The nesting of §2's bullet list is irregular in the source.** The three sub-bullets of
   "Natural person as a participant" ("Participant directly as data provider", "Participant
   directly as data subject", "Participation indirectly via an intermediary") are rendered
   at the same level as their parent, while "Participation directly or via a device or
   software agent, as data user" appears as unbulleted text under it. The list is reproduced
   above in the reading that "Natural person as a participant" has four sub-cases; this is
   an interpretation of the source's layout.
7. **No anonymisation criterion is given.** The document requires proof that data is
   "adequately anonymised" and an anonymisation capability that "can proof effective
   anonymisation", but defines neither adequacy nor effectiveness, and names no standard or
   technique.

**Cross-data space interoperability considerations in data space design and operation**

8. **Two building blocks are referenced under names carrying editorial suffixes** —
   *Data Models_archived* and *Data Exchange_old* (§5). These appear to be stale references
   to the Data Models and Data Exchange building blocks, but the source states the names as
   given and they are reproduced verbatim above. Which version of those building blocks the
   statements were derived from is not stated.
9. **An internal cross-reference is wrong.** §5 opens "As mentioned in Section 2.1,
   interoperability-by-design can be achieved if…", but interoperability-by-design is
   introduced in §2.2, not §2.1.
10. **A named gap.** For Publication and Discovery, the source states that "the federation
    of catalogues could be considered, but this aspect will be covered in the next version
    of this building block" — i.e. cross-data space catalogue federation is explicitly not
    specified in v3.0.
11. **"Federation of data spaces" is explicitly unsettled.** §7.1 gives a definition while
    simultaneously stating that "the definition of a federation of data spaces is evolving
    in the data space community" and that the topic is future work. The section also lists
    three mutually different technical senses of "federation" (a data space as a federation
    of its participants' systems; of use cases' participants' systems; of domains,
    countries or segments' participants' systems). No requirement is derived from §7.
12. **A figure is referenced that the text does not reproduce.** §7.3 refers to "Figure 3"
    for the inheritance association between the governance framework of the federated data
    spaces and the Federation of Data Spaces.
13. **Force is unclear for the ISO/IEC 19941 references.** §2.1 cites ISO/IEC 19941 without a
    year; §5 cites the "ISO/IEC 19941:2017 series". Neither is stated as required — the
    strongest phrasing is "it is worth considering" — so both are recorded as referenced /
    `informative`.
14. **Descriptive future tense vs. obligation.** "The governance of the data spaces will
    define what are the accepted protocols…" (§5) reads as a description of what happens
    rather than an obligation on anyone; it is recorded as `informative`
    (`DSSC-XCT-44`). Read as an allocation of responsibility to the governance authority it
    would be a `must`.
15. **Interoperability-by-design is never stated as an obligation.** It is called "a
    principle", "the key enabler" and "the most important enabler", and appears in a list of
    ways collaboration "can" be achieved (§4.1). It is recorded as `informative`
    (`DSSC-XCT-32`), with the concrete recommendations it implies recorded separately.
16. **Formatting damage in the source text.** Three highlighted definitional sentences carry
    stray inline markup where a word boundary should be — "the ability of****participants",
    "participants of multiple data spaces****aim to create value" (twice) — and §7.1 ends
    with the placeholder line "Explanatory text." before its explanatory bullets. The
    sentences are rendered above without the stray markup; no wording was otherwise changed.
17. **One recommendation link is unresolved.** §2.2 states "The recommended DSSC standards
    are available here" with no target given in the source text.
