# Service Definitions

> **Source** · DSSC Blueprint v3.0 › Service Definitions
> **Category** · Service Definitions (pane)

The Service Definitions pane describes data space capability as a set of *services* rather than
as building blocks. Where the technical pane names the functions a data space needs, this pane
names the components that deliver them: what a participant deploys to join a data space, what the
data space itself operates on behalf of all participants, what innovators may add on top, and what
business and organisational services surround the technical ones. It is the deployable-component
view of the blueprint.

Upstream organises the pane into four top-level entries, three of which group further services
beneath them. This page preserves that organisation and renders every one of the eleven upstream
pages as its own section.

---

## Service inventory and naming

Upstream names several of these services inconsistently between its navigation, its page
headings and its section headings. The table below records the name used on this page and the
evidence for it. Where upstream itself uses two spellings, both are given.

| Service (as rendered here) | Group | Upstream page | Naming evidence | Other upstream spellings |
|---|---|---|---|---|
| Business and Organisational Services | *(top-level)* | `business-and-org-tools.md` | Pane navigation listing; the page's own "Tools implementing this service" category label | — |
| Participant Agent Services | *(top-level, groups the next three)* | `participant-agent.md` | Pane navigation listing; page URL slug `participant-agent`; the page's own opening sentence ("Participant agents allow participants…"); its tools category label "Participant Agent Services" | The page's `# Heading` and breadcrumb both read "Control Plane" — see [Open questions](#open-questions) |
| Control Plane | Participant Agent Services | `control-plane.md` | Page `# Heading` "Control Plane"; breadcrumb "Service Definitions › Participant Agent Services › Control Plane"; pane navigation | Body heading reads "Control Plane vs. Data Plane" |
| Data Plane | Participant Agent Services | `data-plane.md` | Page body heading "## Data Plane"; pane navigation "Data Plane" | — |
| Credential Store | Participant Agent Services | `credential-store.md` | Page body heading "## Credential Store"; pane navigation "Credential Store"; section heading "1.1 Credential Store" in `participant-agent.md` | — |
| Facilitating Services | *(top-level, groups the next four)* | `federation.md` | Page `# Heading` "Facilitating Services"; breadcrumb "Service Definitions › Facilitating Services"; pane navigation | The page states "also called: federation services"; the page URL slug is `federation` |
| Trust services | Facilitating Services | `trust-service.md` | Page body heading "## Trust services"; section heading "1.1 Trust services" in `federation.md` | Pane navigation reads "Trust Service" (singular) |
| Vocabulary services | Facilitating Services | `vocabulary.md` | Page body heading "## Vocabulary services"; section heading "1.3 Vocabulary services" in `federation.md` | Pane navigation reads "Vocabulary" |
| Observability services | Facilitating Services | `observability.md` | Section heading "1.4 Observability services" in `federation.md`; the page's own prose in that section ("Such services are called 'observability services'") | Pane navigation reads "Observability"; `observability.md` itself carries no heading and no descriptive prose |
| Catalogue services | Facilitating Services | `catalogue.md` | Page body heading "## Catalogue services"; section heading "1.2 Catalogue services" in `federation.md` | Pane navigation reads "Catalogue" |
| Value-Creation Services | *(top-level)* | `value-creation.md` | Pane navigation listing; the page's own tools category label "Value-Creation Services"; the page links to the "Value-Creation Services" building block | The page's prose writes "Value-creation services" and "value creation services" |

### Evidence for the top-level split

- **Participant Agent Services** — `participant-agent.md` and `control-plane.md` both carry the
  breadcrumb `Service Definitions › Participant Agent Services › Control Plane`, establishing
  *Participant Agent Services* as a group under *Service Definitions*. `participant-agent.md`
  enumerates its members as sections: *1.1 Credential Store*, *1.2 Local Catalogue Publication*,
  *1.3 Contract Negotiation*, *1.4 Data Plane*. The pane navigation lists *Control Plane*,
  *Data Plane* and *Credential Store* immediately after *Participant Agent Services*.
- **Facilitating Services** — `federation.md` carries the breadcrumb
  `Service Definitions › Facilitating Services` and enumerates its members as sections:
  *1.1 Trust services*, *1.2 Catalogue services*, *1.3 Vocabulary services*,
  *1.4 Observability services*. Those four sections are exactly the bodies of `trust-service.md`,
  `catalogue.md`, `vocabulary.md` and `observability.md`.
- **Value-Creation Services** — `value-creation.md` opens: *"In the two previous categories
  (federation services and participant agent services), we provided a finite list of services."*
  It is therefore a third category alongside the two, not a member of either.
- **Business and Organisational Services** — `business-and-org-tools.md` describes
  *"business and organisation services (as opposed to technical services)"*. The pane navigation
  lists it as a sibling of *Participant Agent Services* and *Facilitating Services*.

> **Ambiguous:** `business-and-org-tools.md`, `data-plane.md`, `credential-store.md`,
> `trust-service.md`, `vocabulary.md`, `observability.md`, `catalogue.md` and `value-creation.md`
> carry no breadcrumb of their own. Their group membership above is inferred from the section
> structure of `participant-agent.md` and `federation.md` and from the pane navigation listing —
> both upstream evidence, but weaker than an explicit breadcrumb.

---

## Business and Organisational Services

> **Group** · top-level · **Upstream page** · `business-and-org-tools.md`

This page describes the collection of business and organisation services — as opposed to technical
services — that are relevant for data spaces.

### 1. Categories of business and operational services

Upstream states there are "four broad and partially overlapping categories of business and
operational services that we consider specific to data spaces (as opposed to any business or other
organisation)", and then lists five:

- **Management services**, such as
  - Governance framework management
  - Data space strategy development and foresight
  - Service architecture and governance
  - Interoperability and security governance
- **Oversight services**, such as
  - Standards compliance monitoring
  - Governance compliance monitoring and enforcement
  - Technical observability services, data space monitoring and reporting
  - Conflict resolution and arbitration
- **Orchestration services**, such as
  - Use case matchmaking, participation brokering
  - Use case development and onboarding
- **Participation management services**
  - Participant lifecycle management; eligibility check, role transitions, on- and off-boarding
  - Roles management
- **Participant support services**, such as
  - Offering validation and onboarding for publication
  - Offering development: usage policy definition support, data (model) transformations
  - Technical integration support
  - Interoperability support
  - Legal and regulatory compliance support

Upstream adds: "Some of these services include or imply also technical services."

> **Ambiguous:** the count ("four broad and partially overlapping categories") does not match the
> five categories listed. The upstream list markup is also damaged — each category's leading
> example is run together with the category name (e.g. "Management services, such asGovernance
> framework management") and the sub-items are rendered at the same list level as the categories.
> The nesting above is a reconstruction of the intended structure; the items and their wording are
> verbatim.

### 2. Governing data space services and their providers

In most cases, the governance framework or rulebook of a data space will specify which services
can or should be used by its participants. A data space **may** and, in many cases, **should** have
a service provider registry (as part of the *data space registry*) which can be used to indicate
who are the service providers in the data space.

The data space governance framework should also address at least the following aspects of service
governance:

- Service level agreements and performance metrics
- Security and compliance requirements
- Data handling and privacy standards
- Incident response and business continuity plans
- Audit and monitoring requirements, including transparency requirements
- Exit strategies and data portability provisions, including fungibility requirements

Upstream refers the reader to *Intermediaries and Operators* §3.3.7 ("Service provider and DSGA
responsibilities") for more detail.

Different approaches exist to who provides, procures, and uses different data space services:

1. The Governance Authority can either provide a service itself or procure it from a separate
   service provider (which upstream notes "is becoming increasingly common").
2. Certain services might be certified, recommended, or approved by the Governance Authority, and
   individual participants can choose to procure the service from whichever provider they prefer.

"In most cases, some services will follow approach 1 and others approach 2." Upstream refers the
reader to *Intermediaries and Operators* §3.3.1 ("Data-space service model characteristics") for
more detail.

### 3. Regulating data space services and their providers

As legal entities in the EU, all service providers are also subject to EU and national regulations
and laws. Some EU regulations additionally govern specific types of services that may be used in
data spaces:

- **trust services** regulated by the **eIDAS regulation**
- **data intermediation services** regulated by the **DGA**
- **internet intermediary services** regulated by the **DSA**

Upstream refers the reader to *Regulatory Compliance* for details on regulatory compliance of data
spaces and their services.

### Tools implementing this service — illustration only

Upstream lists implementing tools with vendor-supplied descriptions. These are examples, not
requirements, and no requirement on this page derives from them.

| Tool | Upstream category label |
|---|---|
| Business Model Radar | Business and Organisational Services |
| Sitra Rulebook model for a fair data economy | Business and Organisational Services |
| iSHARE Trust Framework for Data Rights | Business and Organisational Services |

---

## Participant Agent Services

> **Group** · top-level (groups Control Plane, Data Plane and Credential Store) ·
> **Upstream page** · `participant-agent.md`

Participant agents allow participants, as the name suggests, to participate in a data space. It is
their 'digital representation' in the data space.

Such services play a vital role in ensuring trust in a data space as they differentiate between a
*data plane* and a *control plane*. The control plane is key here as it implements functionalities
for identification, publishing of data sets, etc.

Within the Participant Agent, several parts can be identified (upstream: "see Figure 1"). Upstream
advises reading the technical-pane section explaining the data and control plane first.

> **Ambiguous:** upstream references "Figure 1" for the parts of the Participant Agent. The figure
> is not reproducible from the source text, so the enumeration below comes from the page's own
> section headings.

### 1.1 Credential Store

The credential store is used to store credentials (identities and attestations) which have been
issued by the validation and verification federation service. This could include credentials
indicating that a participant is a member of a particular data space, for example.

The credential store is also used to present credentials to other participants in the data space
and to validate credentials from others. **The store shall use protocols for the issuing and
sharing of credentials.**

Relevant building blocks include **Identity & Attestation Management** and **Trust Framework**.

### 1.2 Local Catalogue Publication

This part allows for publishing metadata of data products, provided through the Participant Agent,
to the data space. On a data space level, this functionality can be enhanced by including offerings
of other participants, too. In the latter case, upstream calls this a **Catalogue**.

**The Participant agent shall use the Dataspace Protocol, in combination with DCAT-AP, for the
exchange of catalogue entries.** (Upstream links this statement to *Building on top of foundational
standards*.)

### 1.3 Contract Negotiation

This part allows data access and usage policies to be published within catalogue metadata based on
the **ODRL** standard. As explained in the *Access and Usage Policies and Enforcement* building
block, this implements a **Policy Administration Point (PAP)**.

After publishing, a contract negotiation process needs to occur, during which the policies of the
data consumer and data provider are matched. Ultimately, this leads to a decision on whether or not
to grant access to data. This is called a **Policy Decision Point (PDP)**.

During this process, it is possible to interact with a **Policy Information Point (PIP)** operating
as a *federation service* in the data space, e.g., to query whether someone has given personal
consent or to evaluate a specific policy.

**The Participant agents shall use the Dataspace Protocol for the contract negotiation process.**
(Upstream links this statement to *Building on top of foundational standards*.)

### 1.4 Data Plane

The data plane implements the data exchange with APIs and data models specific to a particular
domain. Consequently, the data plane is likely to be domain-specific. It can also contain runtime
components, such as cloud infrastructure, which is required to execute the required functionality.

The control plane and data plane **should** work together to manage the transfer process. After
contract negotiation, the transfer process can take place. This happens on the Data Plane. The
'Transfer Process' part of the Participant Agent also plays an important role, as it manages the
actual transfer process. It acts as a **Policy Decision Point (PDP)** and **Policy Execution Point
(PEP)**, enforcing the agreed data-sharing contract.

> **Ambiguous:** upstream introduces a "'Transfer Process' part of the Participant Agent" inside
> §1.4 but does not give it a section of its own, nor a page in the pane navigation. It is
> therefore unclear whether the Participant Agent has four parts (the four section headings) or
> five (those plus Transfer Process).

### What is a connector, then?

Upstream answers this explicitly:

> Some initiatives use the concept of a 'connector'. In fact, this is a combination of some or all
> elements mentioned above. It is software to implement Participant agents. Different set-ups exist,
> however. For example, the Credential Store can be implemented as part of a 'connector', but it
> could also be implemented as a separate software tool working together with the connector. Other
> service providers have even chosen to integrate participant agent services with other software or
> platforms.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Ocean Enterprise Provider | Participant Agent Services |
| Nautilus Participant Agent | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| FIWARE Data Space Framework (FDF) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |
| Simpl-Open – Participant Agent | Participant Agent Services |
| NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. | Trust Service |

---

## Control Plane

> **Group** · Participant Agent Services · **Upstream page** · `control-plane.md`

### Control Plane vs. Data Plane

It is important to distinguish between a **control plane** and a **data plane**:

- The control plane is responsible for deciding how data is managed, routed and processed.
- The data plane is responsible for the actual sharing of data.

For example, the control plane handles user identification, access, and usage policies, while the
data plane handles the actual exchange of data.

This implies that the control plane can be standardised to a high level, using common standards for
identification, authentication, etc.

The data plane can be different for each data space and use case depending on the types of data
exchange that take place. Some data spaces focus on sharing large datasets, others on message
exchange, and others take an event-based approach. There is no one-size-fits-all, although some
mechanisms (especially in the **data interoperability pillar**) can assist in making sure different
data planes work together.

### Local Catalogue Publication

This part allows for publishing metadata of data products, provided through the Participant Agent,
to the data space. On a data space level, this functionality can be enhanced by including offerings
of other participants, too. In the latter case, upstream calls this a **Catalogue**.

**The Participant agent shall use the Dataspace Protocol, in combination with DCAT-AP, for the
exchange of catalogue entries.**

### Contract Negotiation

This part allows data access and usage policies to be published within catalogue metadata based on
the **ODRL** standard. As explained in the *Access and Usage Policies and Enforcement* building
block, this implements a **Policy Administration Point (PAP)**.

After publishing, a contract negotiation process needs to occur, during which the policies of the
data consumer and data provider are matched. Ultimately, this leads to a decision on whether or not
to grant access to data. This is called a **Policy Decision Point (PDP)**.

During this process, it is possible to interact with a **Policy Information Point (PIP)** operating
as a *federation service* in the data space, e.g., to query whether someone has given personal
consent or to evaluate a specific policy.

**The Participant agents shall use the Dataspace Protocol for the contract negotiation process.**

### What is a connector, then?

`control-plane.md` repeats the "What is a connector, then?" passage verbatim from
`participant-agent.md`. It is rendered once, under *Participant Agent Services*.

> **Ambiguous:** `control-plane.md` presents *Local Catalogue Publication* and *Contract
> Negotiation* as its own parts, while `participant-agent.md` presents the same two — with
> identical wording — as parts of the Participant Agent alongside *Credential Store* and
> *Data Plane*. Upstream does not state whether the Control Plane comprises exactly these two
> parts, or whether the duplication is editorial. The requirements derived from the shared text
> are listed once, under Participant Agent Services, and are not restated for the Control Plane.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Ocean Enterprise Provider | Participant Agent Services |
| Nautilus Participant Agent | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| FIWARE Data Space Framework (FDF) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |

---

## Data Plane

> **Group** · Participant Agent Services · **Upstream page** · `data-plane.md`

The data plane implements the data exchange with APIs and data models specific to a particular
domain. Consequently, the data plane is likely to be domain-specific. It can also contain runtime
components, such as cloud infrastructure, which is required to execute the required functionality.

The control plane and data plane **should** work together to manage the transfer process. After
contract negotiation, the transfer process can take place. This happens on the Data Plane. The
'Transfer Process' part of the Participant Agent also plays an important role, as it manages the
actual transfer process. It acts as a **Policy Decision Point (PDP)** and **Policy Execution Point
(PEP)**, enforcing the agreed data-sharing contract.

> `data-plane.md` carries exactly the text of §1.4 of `participant-agent.md`. The requirements are
> listed once, under *Data Plane*, in the consolidated table.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Fair Data Publisher | Data Plane |
| Ocean Enterprise Provider | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| FIWARE Data Space Framework (FDF) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |

---

## Credential Store

> **Group** · Participant Agent Services · **Upstream page** · `credential-store.md`

The credential store is used to store credentials (identities and attestations) which have been
issued by the validation and verification federation service. This could include credentials
indicating that a participant is a member of a particular data space, for example.

The credential store is also used to present credentials to other participants in the data space
and to validate credentials from others. **The store shall use protocols for the issuing and
sharing of credentials.**

Relevant building blocks include **Identity & Attestation Management** and **Trust Framework**.

> `credential-store.md` carries exactly the text of §1.1 of `participant-agent.md`. The
> requirements are listed once, under *Credential Store*, in the consolidated table.

> **Gap:** upstream states the store "shall use protocols for the issuing and sharing of
> credentials" but names no protocol here. The named protocol family appears only under
> *Trust services*, as W3C Verifiable Credentials "and other related protocols".

`credential-store.md` lists no implementing tools.

---

## Facilitating Services

> **Group** · top-level (groups Trust services, Catalogue services, Vocabulary services and
> Observability services) · **Upstream page** · `federation.md`

Facilitating services, also called **federation services**, support the interplay of participants
in a data space. They operate according to the policies and rules specified in the Rulebook by the
data space authority.

It is important to note that data spaces are distributed in nature. There is not necessarily a
central platform where all data is kept. In most cases, participants in a data space manage their
own data and can decide for themselves whether or not to share it with other participants,
sometimes even in multiple data spaces.

That being said, there can still be the need for services which facilitate them in this interplay,
e.g., federation services. There are **four main categories** of federation services (upstream:
"see Figure 1. Federation services"):

1. Trust services
2. Catalogue services
3. Vocabulary services
4. Observability services

> **Ambiguous:** upstream references "Figure 1. Federation services" for the categories. The figure
> is not reproducible from the source text; the enumeration above comes from the page's own section
> headings, which do number exactly four.

> **Ambiguous:** the page's URL slug is `federation` and its own text says facilitating services
> are "also called: federation services", but its heading and breadcrumb use *Facilitating
> Services*. Elsewhere in the pane the same set is referred to as "Federation Services"
> (`value-creation.md`). The two names are used interchangeably upstream.

`federation.md` lists no implementing tools of its own; tools appear on the four member pages.

---

## Trust services

> **Group** · Facilitating Services · **Upstream page** · `trust-service.md`
> *(identical text at `federation.md` §1.1)*

The capabilities implemented by validation and verification services serve to:

- Issue or validate credentials
- Verify Credentials
- Optionally: allow for delegation of trust (which, technically, is also the issuance of a
  credential).

Credentials can relate to all kinds of attestations:

- **Identity**, which can be an eIDAS-compliant credential when available or another identity
  credential if needed.
- **Participation**, which describes whether someone is a participant in the data space (i.e., has
  signed the relevant contracts or is compliant with certain regulations). This service implements
  the data space's participants registry.
- **Other compliance**: the credential indicates compliance with other rules, policies or
  regulations. This can include aspects such as personal consent, the signing of legal contracts or
  any other conformity assessment.

Trust services can be fully automated (e.g. by checking against a database or registry) or can
contain manual compliance verifications such as audits or legal checks.

Whatever the setup is, these services rely on the usage of **W3C Verifiable Credentials and other
related protocols** for issuing and validating credentials.

The **trust framework** of a dataspace can identify which trust services can be used for the
issuing and validation of credentials.

> **Ambiguous:** upstream lists "Issue or validate credentials" and "Verify Credentials" as
> separate capabilities without distinguishing *validate* from *verify*.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Gaia-X Compliance Service | Trust Service |
| Gaia-X registry | Trust Service |
| iSHARE Satellite (Participant Registry) | Trust Service |
| sovity Dynamic Attribute Provisioning Service (DAPS) | Trust Service |
| Apache Syncope | Trust Service |
| iSHARE Authorisation Registry | Trust Service |
| Simpl-Open - Trust Service | Trust Service |
| NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. | Trust Service |
| Nautilus Participant Agent | Participant Agent Services |
| Data Space Innovation Lab Connector | Participant Agent Services |
| TNO Security Gateway (TSG) | Participant Agent Services |
| Tekniker Dataspace Connector | Participant Agent Services |
| sovity EDC Community Edition (EDC CE) | Participant Agent Services |

---

## Vocabulary services

> **Group** · Facilitating Services · **Upstream page** · `vocabulary.md`
> *(identical text at `federation.md` §1.3)*

Vocabulary services provide an overview of available **data models** in the data space. This allows
participants of the data space to choose common data models for a particular application. In the
rulebook, some data models can be made mandatory to ensure semantic interoperability between
participants.

Vocabulary Services can also link these data models to APIs/technical interfaces for **data
exchange**, providing semantics and syntax. This can also be done for other services where mappings
need to be made between semantic models and technical interfaces, such as **provenance, traceability
and observability**.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Semantic Treehouse | Vocabulary |
| Smart Data Models | Vocabulary |
| AgroPortal | Vocabulary |
| OntoPortal | Vocabulary |
| Simpl-Open - Vocabulary Service | Vocabulary |
| Data Space Builder | Value-Creation Services |

---

## Observability services

> **Group** · Facilitating Services · **Upstream page** · `observability.md`
> *(descriptive text exists only at `federation.md` §1.4)*

Depending on the use case and relevant legal/contractual obligations, it might be necessary to
audit data sharing within the data space. In this case, it might be required to record specific
data for the purposes of **provenance & traceability**.

Such services are called 'observability services'.

> **Gap:** `observability.md` contains no heading and no descriptive prose at all — only the
> "Tools implementing this service" listing. The definition above is taken from `federation.md`
> §1.4, the only place in the pane where observability services are described. Unlike the other
> three facilitating services, observability services get no statement of interfaces, standards or
> protocols anywhere in this pane.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. | Trust Service |

---

## Catalogue services

> **Group** · Facilitating Services · **Upstream page** · `catalogue.md`
> *(identical text at `federation.md` §1.2)*

These services provide an overview of registered data products in the data space and links to their
respective participant agents. This allows participants to search and find assets in the data
space. These services implement the **Publication and Discovery** building block.

Catalogue services use the **DCAT-AP** specification to express the metadata of Data Products and
the **Dataspace Protocol** for the exchange of these entries.

Technically, a catalogue uses the same interface as the catalogue of a Participant agent. The
difference is that in this particular case, a catalogue can include entries of multiple participants
or federate multiple catalogues.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Ocean Enterprise Catalogue and Aquarius Catalogue Cache | Catalogue |
| sovity Data Space Portal (DSPortal) | Catalogue |
| Simpl-Open - Catalogue | Catalogue |
| Data Space Builder | Value-Creation Services |
| NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V. | Trust Service |

---

## Value-Creation Services

> **Group** · top-level · **Upstream page** · `value-creation.md`

In the two previous categories (**federation services** and **participant agent services**),
upstream provided a finite list of services.

Value-creation services relate to additional services which reside in a data space. For
value-creation services, it is not possible to define a limited list. This is because it is up to
innovators in data spaces to determine which services are offered.

Upstream's definition, verbatim:

> Value-creation services are there to unlock, generate and maximize the value of data shared
> within a data space, providing additional functionalities on top of the core process of data
> sharing or data transaction. These services complement the Federation Services (which provide the
> basic capabilities to perform a data transaction) and Participant Agent Services (which enable an
> individual participant to join the data space and facilitate the providing, using or sharing of
> data) to compose the whole set of services available in a data space"

Examples of these services could be a data marketplace, a data analytics service or a cross-data
space AI service.

Participants of the dataspace can contract such services. They can be mandatory or optional,
depending on what is specified in the Rulebook.

From a technical perspective, **value creation services shall also adopt the foundational technical
standards as specified in the blueprint for their basic interactions with others.**

The **Value-Creation Services** building block provides more perspectives on deploying such
services.

> **Ambiguous:** the definition paragraph ends with an unmatched closing quotation mark in the
> source, suggesting it is a quotation whose opening mark and attribution are lost. It is
> reproduced verbatim above.

### Tools implementing this service — illustration only

| Tool | Upstream category label |
|---|---|
| Ocean Enterprise Market | Value-Creation Services |
| WISEPHERE | Value-Creation Services |
| Data Space Builder | Value-Creation Services |
| PETSpaces (Privacy-Enhancing Data App for Secure Computations in Data Spaces) | Value-Creation Services |
| IFLEX (Ikerlan Federated Learning EXtensible kit) | Value-Creation Services |
| PURIS - Predictive Unit Realtime Information Service | Value-Creation Services |
| SEMIC SHACL Validator (Unified Validator) | Value-Creation Services |
| SEMIC XML Validator | Value-Creation Services |
| Interoperability Test Bed | Value-Creation Services |
| Sovity Connector Plugin: Data Space Federation | Value-Creation Services |
| Fair Data Publisher | Data Plane |

---

## Standards and protocols named in this pane

Verbatim names as upstream writes them. "referenced" means the source names the standard as an
example or as context rather than requiring it.

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| Dataspace Protocol | not stated | Exchange of catalogue entries by the Participant agent | required ("shall") |
| DCAT-AP | not stated | Expressing metadata of Data Products, in combination with the Dataspace Protocol | required ("shall") |
| Dataspace Protocol | not stated | Contract negotiation process between Participant agents | required ("shall") |
| ODRL | not stated | Basis for data access and usage policies published within catalogue metadata | referenced |
| DCAT-AP | not stated | Used by Catalogue services to express the metadata of Data Products | referenced |
| Dataspace Protocol | not stated | Used by Catalogue services for the exchange of catalogue entries | referenced |
| W3C Verifiable Credentials and other related protocols | not stated | Issuing and validating credentials by trust services | referenced |
| eIDAS | not stated | Identity credentials ("an eIDAS-compliant credential when available"); regulation of trust services | referenced |
| DGA | not stated | Regulation of data intermediation services | referenced |
| DSA | not stated | Regulation of internet intermediary services | referenced |
| "the foundational technical standards as specified in the blueprint" | not enumerated on this page | Basic interactions of value creation services with others | required ("shall") |

> **Gap:** this pane never states a version or profile for any standard it names. Version
> information, where it exists, lives in the technical pane's foundational-standards material.

---

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its requirements.*

Force is the source's own. Most of this pane is descriptive prose that defines what a service *is*
rather than what an implementation *must do*; those rows are marked `informative`. Only six
statements in the entire pane carry an explicit obligation modal ("shall", "should", "needs to
occur"), and they are marked `must` or `should` accordingly.

Where two upstream pages carry identical text (`credential-store.md` and `participant-agent.md`
§1.1; `data-plane.md` and `participant-agent.md` §1.4; `trust-service.md` /
`catalogue.md` / `vocabulary.md` and `federation.md` §§1.1–1.3; `control-plane.md` and
`participant-agent.md` §§1.2–1.3), the requirement appears once and its Source column names both
locations.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-SVD-01` | A data space's business and operational services include Management services, such as governance framework management, data space strategy development and foresight, service architecture and governance, and interoperability and security governance. | informative | `business-and-org-tools.md` §1 |
| `DSSC-SVD-02` | A data space's business and operational services include Oversight services, such as standards compliance monitoring, governance compliance monitoring and enforcement, technical observability services / data space monitoring and reporting, and conflict resolution and arbitration. | informative | `business-and-org-tools.md` §1 |
| `DSSC-SVD-03` | A data space's business and operational services include Orchestration services, such as use case matchmaking and participation brokering, and use case development and onboarding. | informative | `business-and-org-tools.md` §1 |
| `DSSC-SVD-04` | A data space's business and operational services include Participation management services: participant lifecycle management (eligibility check, role transitions, on- and off-boarding) and roles management. | informative | `business-and-org-tools.md` §1 |
| `DSSC-SVD-05` | A data space's business and operational services include Participant support services, such as offering validation and onboarding for publication, offering development (usage policy definition support, data (model) transformations), technical integration support, interoperability support, and legal and regulatory compliance support. | informative | `business-and-org-tools.md` §1 |
| `DSSC-SVD-06` | In most cases, the governance framework or rulebook of a data space will specify which services can or should be used by its participants. | informative | `business-and-org-tools.md` §2 |
| `DSSC-SVD-07` | A data space "may and, in many cases, should" have a service provider registry, as part of the data space registry, which can be used to indicate who the service providers in the data space are. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-08` | The data space governance framework should address service level agreements and performance metrics. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-09` | The data space governance framework should address security and compliance requirements. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-10` | The data space governance framework should address data handling and privacy standards. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-11` | The data space governance framework should address incident response and business continuity plans. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-12` | The data space governance framework should address audit and monitoring requirements, including transparency requirements. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-13` | The data space governance framework should address exit strategies and data portability provisions, including fungibility requirements. | should | `business-and-org-tools.md` §2 |
| `DSSC-SVD-14` | The Governance Authority may either provide a service itself or procure it from a separate service provider. | may | `business-and-org-tools.md` §2 |
| `DSSC-SVD-15` | Certain services may be certified, recommended, or approved by the Governance Authority, with individual participants free to procure the service from whichever provider they prefer. | may | `business-and-org-tools.md` §2 |
| `DSSC-SVD-16` | As legal entities in the EU, all service providers are subject to EU and national regulations and laws. | informative | `business-and-org-tools.md` §3 |
| `DSSC-SVD-17` | Trust services used in data spaces are regulated by the eIDAS regulation. | informative | `business-and-org-tools.md` §3 |
| `DSSC-SVD-18` | Data intermediation services used in data spaces are regulated by the DGA. | informative | `business-and-org-tools.md` §3 |
| `DSSC-SVD-19` | Internet intermediary services used in data spaces are regulated by the DSA. | informative | `business-and-org-tools.md` §3 |
| `DSSC-SVD-20` | Participant agents allow participants to participate in a data space and are the participant's 'digital representation' in the data space. | informative | `participant-agent.md` §1 |
| `DSSC-SVD-21` | Participant agent services differentiate between a data plane and a control plane. | informative | `participant-agent.md` §1 |
| `DSSC-SVD-22` | The control plane implements functionalities for identification, publishing of data sets, etc. | informative | `participant-agent.md` §1 |
| `DSSC-SVD-23` | The Participant Agent comprises the parts Credential Store, Local Catalogue Publication, Contract Negotiation and Data Plane. | informative | `participant-agent.md` §§1.1–1.4 |
| `DSSC-SVD-24` | A 'connector' is a combination of some or all of the Participant Agent parts; it is software to implement Participant agents. | informative | `participant-agent.md` §1.4 ("What is a connector, then?") |
| `DSSC-SVD-25` | The Credential Store may be implemented as part of a 'connector' or as a separate software tool working together with the connector. | may | `participant-agent.md` §1.4 ("What is a connector, then?") |
| `DSSC-SVD-26` | Participant agent services may be integrated with other software or platforms. | may | `participant-agent.md` §1.4 ("What is a connector, then?") |
| `DSSC-SVD-27` | The credential store stores credentials (identities and attestations) which have been issued by the validation and verification federation service. | informative | `credential-store.md`; `participant-agent.md` §1.1 |
| `DSSC-SVD-28` | The credential store presents credentials to other participants in the data space. | informative | `credential-store.md`; `participant-agent.md` §1.1 |
| `DSSC-SVD-29` | The credential store validates credentials from other participants. | informative | `credential-store.md`; `participant-agent.md` §1.1 |
| `DSSC-SVD-30` | The credential store shall use protocols for the issuing and sharing of credentials. | must | `credential-store.md`; `participant-agent.md` §1.1 |
| `DSSC-SVD-31` | The building blocks relevant to the credential store include Identity & Attestation Management and Trust Framework. | informative | `credential-store.md`; `participant-agent.md` §1.1 |
| `DSSC-SVD-32` | Local Catalogue Publication allows metadata of data products provided through the Participant Agent to be published to the data space. | informative | `participant-agent.md` §1.2; `control-plane.md` |
| `DSSC-SVD-33` | At data space level, local catalogue publication may be enhanced by including offerings of other participants; in that case it is called a Catalogue. | may | `participant-agent.md` §1.2; `control-plane.md` |
| `DSSC-SVD-34` | The Participant agent shall use the Dataspace Protocol for the exchange of catalogue entries. | must | `participant-agent.md` §1.2; `control-plane.md` |
| `DSSC-SVD-35` | The Participant agent shall use DCAT-AP, in combination with the Dataspace Protocol, for the exchange of catalogue entries. | must | `participant-agent.md` §1.2; `control-plane.md` |
| `DSSC-SVD-36` | Contract Negotiation allows data access and usage policies to be published within catalogue metadata based on the ODRL standard. | informative | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-37` | Publishing access and usage policies within catalogue metadata implements a Policy Administration Point (PAP). | informative | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-38` | After publishing, a contract negotiation process needs to occur, during which the policies of the data consumer and data provider are matched. | must | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-39` | Contract negotiation leads to a decision on whether or not to grant access to data; this is called a Policy Decision Point (PDP). | informative | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-40` | During contract negotiation it is possible to interact with a Policy Information Point (PIP) operating as a federation service in the data space — e.g. to query whether someone has given personal consent, or to evaluate a specific policy. | may | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-41` | The Participant agents shall use the Dataspace Protocol for the contract negotiation process. | must | `participant-agent.md` §1.3; `control-plane.md` |
| `DSSC-SVD-42` | The control plane is responsible for deciding how data is managed, routed and processed. | informative | `control-plane.md` |
| `DSSC-SVD-43` | The data plane is responsible for the actual sharing of data. | informative | `control-plane.md` |
| `DSSC-SVD-44` | The control plane can be standardised to a high level, using common standards for identification, authentication, etc. | may | `control-plane.md` |
| `DSSC-SVD-45` | The data plane may be different for each data space and use case, depending on the types of data exchange that take place. | may | `control-plane.md` |
| `DSSC-SVD-46` | There is no one-size-fits-all data plane, although some mechanisms — especially in the data interoperability pillar — can assist in making sure different data planes work together. | informative | `control-plane.md` |
| `DSSC-SVD-47` | The data plane implements the data exchange with APIs and data models specific to a particular domain. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-48` | The data plane is likely to be domain-specific. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-49` | The data plane may contain runtime components, such as cloud infrastructure, required to execute the required functionality. | may | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-50` | The control plane and data plane should work together to manage the transfer process. | should | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-51` | After contract negotiation, the transfer process takes place on the Data Plane. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-52` | The 'Transfer Process' part of the Participant Agent manages the actual transfer process. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-53` | The 'Transfer Process' part of the Participant Agent acts as a Policy Decision Point (PDP), enforcing the agreed data-sharing contract. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-54` | The 'Transfer Process' part of the Participant Agent acts as a Policy Execution Point (PEP), enforcing the agreed data-sharing contract. | informative | `data-plane.md`; `participant-agent.md` §1.4 |
| `DSSC-SVD-55` | Facilitating services, also called federation services, support the interplay of participants in a data space. | informative | `federation.md` §1 |
| `DSSC-SVD-56` | Facilitating services operate according to the policies and rules specified in the Rulebook by the data space authority. | informative | `federation.md` §1 |
| `DSSC-SVD-57` | Data spaces are distributed in nature; there is not necessarily a central platform where all data is kept. | informative | `federation.md` §1 |
| `DSSC-SVD-58` | In most cases, participants in a data space manage their own data and decide for themselves whether or not to share it with other participants, sometimes in multiple data spaces. | informative | `federation.md` §1 |
| `DSSC-SVD-59` | There are four main categories of federation services: trust services, catalogue services, vocabulary services and observability services. | informative | `federation.md` §§1.1–1.4 |
| `DSSC-SVD-60` | Validation and verification services issue or validate credentials. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-61` | Validation and verification services verify Credentials. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-62` | Validation and verification services may optionally allow for delegation of trust, which technically is also the issuance of a credential. | may | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-63` | Credentials can relate to Identity, which can be an eIDAS-compliant credential when available or another identity credential if needed. | may | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-64` | Credentials can relate to Participation, describing whether someone is a participant in the data space — i.e. has signed the relevant contracts or is compliant with certain regulations. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-65` | The Participation attestation service implements the data space's participants registry. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-66` | Credentials can relate to Other compliance, indicating compliance with other rules, policies or regulations — including personal consent, the signing of legal contracts or any other conformity assessment. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-67` | Trust services may be fully automated, e.g. by checking against a database or registry. | may | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-68` | Trust services may contain manual compliance verifications such as audits or legal checks. | may | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-69` | Whatever the setup, trust services "rely on the usage of" W3C Verifiable Credentials and other related protocols for issuing and validating credentials. | informative | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-70` | The trust framework of a dataspace can identify which trust services can be used for the issuing and validation of credentials. | may | `trust-service.md`; `federation.md` §1.1 |
| `DSSC-SVD-71` | Vocabulary services provide an overview of available data models in the data space. | informative | `vocabulary.md`; `federation.md` §1.3 |
| `DSSC-SVD-72` | Vocabulary services allow participants of the data space to choose common data models for a particular application. | informative | `vocabulary.md`; `federation.md` §1.3 |
| `DSSC-SVD-73` | In the rulebook, some data models can be made mandatory to ensure semantic interoperability between participants. | may | `vocabulary.md`; `federation.md` §1.3 |
| `DSSC-SVD-74` | Vocabulary Services may also link data models to APIs/technical interfaces for data exchange, providing semantics and syntax. | may | `vocabulary.md`; `federation.md` §1.3 |
| `DSSC-SVD-75` | Vocabulary Services may also map semantic models to technical interfaces for other services, such as provenance, traceability and observability. | may | `vocabulary.md`; `federation.md` §1.3 |
| `DSSC-SVD-76` | Depending on the use case and relevant legal/contractual obligations, it might be necessary to audit data sharing within the data space. | may | `federation.md` §1.4 |
| `DSSC-SVD-77` | Where auditing is necessary, it might be required to record specific data for the purposes of provenance & traceability. | may | `federation.md` §1.4 |
| `DSSC-SVD-78` | Services that record data for provenance & traceability purposes are called 'observability services'. | informative | `federation.md` §1.4 |
| `DSSC-SVD-79` | Catalogue services provide an overview of registered data products in the data space and links to their respective participant agents. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-80` | Catalogue services allow participants to search and find assets in the data space. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-81` | Catalogue services implement the Publication and Discovery building block. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-82` | Catalogue services use the DCAT-AP specification to express the metadata of Data Products. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-83` | Catalogue services use the Dataspace Protocol for the exchange of catalogue entries. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-84` | Technically, a catalogue uses the same interface as the catalogue of a Participant agent. | informative | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-85` | A catalogue may include entries of multiple participants. | may | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-86` | A catalogue may federate multiple catalogues. | may | `catalogue.md`; `federation.md` §1.2 |
| `DSSC-SVD-87` | For value-creation services it is not possible to define a limited list; it is up to innovators in data spaces to determine which services are offered. | informative | `value-creation.md` |
| `DSSC-SVD-88` | Value-creation services unlock, generate and maximize the value of data shared within a data space, providing additional functionalities on top of the core process of data sharing or data transaction. | informative | `value-creation.md` |
| `DSSC-SVD-89` | Value-creation services complement the Federation Services and the Participant Agent Services to compose the whole set of services available in a data space. | informative | `value-creation.md` |
| `DSSC-SVD-90` | Participants of the dataspace may contract value-creation services. | may | `value-creation.md` |
| `DSSC-SVD-91` | Value-creation services may be mandatory or optional, depending on what is specified in the Rulebook. | may | `value-creation.md` |
| `DSSC-SVD-92` | Value creation services shall adopt the foundational technical standards as specified in the blueprint for their basic interactions with others. | must | `value-creation.md` |

---

## Open questions

1. **`participant-agent.md` is titled "Control Plane" in both its heading and its breadcrumb.**
   The page whose URL slug is `participant-agent` carries the heading `# Control Plane` and the
   breadcrumb `Service Definitions › Participant Agent Services › Control Plane` — identical to
   those of `control-plane.md`. Its content is unambiguously the Participant Agent Services
   overview (it opens "Participant agents allow participants… to participate in a data space" and
   enumerates the Participant Agent's parts), and the pane navigation lists *Participant Agent
   Services* as a distinct entry above *Control Plane*. This page names it **Participant Agent
   Services** on that evidence, but the upstream heading and breadcrumb contradict that name.

2. **Control Plane and Participant Agent Services overlap without a stated boundary.**
   `control-plane.md` and `participant-agent.md` share the *Local Catalogue Publication*,
   *Contract Negotiation* and "What is a connector, then?" text word for word.
   `participant-agent.md` presents those as parts of the Participant Agent, alongside *Credential
   Store* and *Data Plane*; `control-plane.md` presents them as its own content. Upstream never
   states which parts belong to the control plane. Notably, `control-plane.md` does **not** repeat
   the Credential Store section, even though `participant-agent.md` §1 calls the control plane
   "key… as it implements functionalities for identification".

3. **Four or five categories of business and operational services?**
   `business-and-org-tools.md` §1 says "four broad and partially overlapping categories" and then
   lists five (Management, Oversight, Orchestration, Participation management, Participant support).

4. **The business and operational services list markup is damaged upstream.**
   Category names are run together with their first example ("Management services, such
   asGovernance framework management") and sub-items appear at the same list level as categories.
   The nesting rendered above is a reconstruction; wording is verbatim.

5. **`observability.md` has no content.** The page carries no heading and no descriptive prose,
   only its tool listing. Observability services are described only in `federation.md` §1.4, and
   are the one facilitating service for which the pane names no standard, protocol or interface.

6. **`credential-store.md` names no protocol.** The store "shall use protocols for the issuing and
   sharing of credentials" without naming them. The only protocol family named for credentials in
   this pane is "W3C Verifiable Credentials and other related protocols", stated under *Trust
   services* — upstream does not explicitly bind the credential store to it.

7. **No version or profile is given for any standard.** Dataspace Protocol, DCAT-AP, ODRL and
   W3C Verifiable Credentials are all named without version or profile anywhere in this pane.

8. **Unmodalised statements that read as obligations.** Several statements state a fact about how
   services behave rather than imposing a duty — "Catalogue services use the DCAT-AP
   specification…", "these services rely on the usage of W3C Verifiable Credentials…",
   "Facilitating services… operate according to the policies and rules specified in the Rulebook".
   They are recorded as `informative` because the source uses no obligation modal, but they may be
   intended as requirements. Notably, the identical obligation ("use the Dataspace Protocol and
   DCAT-AP for catalogue entries") is expressed with "shall" for the Participant agent and without
   a modal for Catalogue services.

9. **"Facilitating services" vs "federation services".** Both names are used for the same set,
   including within a single sentence ("Facilitating services, also called: federation services"),
   and `value-creation.md` uses "Federation Services" in its definition. Upstream sets no preferred
   term.

10. **Two figures are referenced but not reproducible from the source text.** "Figure 1" in
    `participant-agent.md` (parts of the Participant Agent) and "Figure 1. Federation services" in
    `federation.md` (the four categories). Both enumerations on this page were reconstructed from
    the pages' own section headings, which may not match the figures.

11. **The pane's own top-level split has four entries, not two.** Beyond *Participant Agent
    Services* and *Facilitating Services*, the pane also carries *Value-Creation Services* and
    *Business and Organisational Services* as top-level entries. Only *Participant Agent Services*
    and *Facilitating Services* have breadcrumb evidence; the other two are placed at top level on
    the strength of the pane navigation listing and their own framing text.

12. **Tool listings do not match their page's service.** Several "Tools implementing this service"
    lists include tools whose upstream category label is a different service — for example
    `data-plane.md` lists six tools labelled *Participant Agent Services* and one labelled *Data
    Plane*; `observability.md`'s only entry is labelled *Trust Service*. Upstream does not explain
    the mismatch. These listings are illustration in any case, and no requirement derives from them.
