# Co-Creation Method

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method
> **Category** · Co-creation pane

The Co-Creation Method is the DSSC Blueprint's process companion to its building blocks: it is meant to help navigate the blueprint once the decision has been taken to start and/or set up a data space. It comprises a preparatory chapter, **A - Before developing a data space**, and five **Development Processes** (B.1–B.5), each structured around a fundamental question, a flowchart of steps, and per-step tables that map questions to the building blocks that answer them and to the outcomes expected. This page renders all seven documents of the pane.

> **On requirement IDs** — Requirement IDs are a local index for benchmarking. The source does not number its requirements. Numbering on this page continues the single `BIZ` sequence begun on *Business and Organisational Building Blocks*.

> **Ambiguous:** the pane root is named **Introduction Co-Creation Method** in the source's breadcrumb trails and **Co-Creation Method** in the page navigation. The latter is used as this page's title.

---

## A - Before developing a data space

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › A - Before developing a data space

A decision has to be made to actually set up a data space, and this decision needs to be prepared. The preparation entails finding the answer to a number of questions, which are a means to answer the main question: **why do you want to set up a data space?**

The questions to answer at first:

- What is the (high-level) problem you would like to resolve?
- What is the specific reason or reasons why you need a data space to resolve the problem?
- Do you have an idea of which parties need to be involved?
- Can you make a high-level business case to show parties what the data space delivers and what it could yield?

### Why is it important to thoroughly consider the reasons why a data space should be developed?

Very few data spaces are (financially) self-sustaining at the time of writing; most data space initiatives are started by European or national subsidies and/or grants, which are finite in number, amount and time. The source cites the **JADS report – Sustainable Revenue Models for Data Sharing Initiatives** (Jheronimus Academy of Data Science, April 2025), which identifies as a key obstacle that "participants often fail to see the immediate benefits of sharing their data. The value is frequently indirect, delayed, or diffused, making it hard for organisations to justify investment." The same researchers state that "an analysis of 155 European data spaces reveals that only 15% have a clear revenue model". To avoid this issue, or at a minimum decrease the chance of it occurring, a proper analysis of why a data space is a good solution to the issues to be resolved is needed.

### What is the (high-level) problem you would like to resolve?

The high-level problem does not have to be extremely concrete yet, but it does require direction. The source's worked examples: "we would like to create a data space to support SME's in the manufacturing sector with the implementation of digital product passports to adhere to legislation, and increase digital collaboration to ensure competitiveness"; and "we want to create a data space to help hotels better manage their energy bills, to become more sustainable and decrease costs." Such statements provide an idea of the industry, the potential clients, and the problem to be resolved.

### What is the specific reason or reasons why you need a data space to resolve them?

This is the competition analysis: why should a data space be built, why should scarce time and resources be put into developing this piece of infrastructure, and what makes a data space better than other options in the market. Arguments may include (but are not limited to):

- **Data sovereignty** — the participant of the data space keeps control of the data, by allowing the data to be shared from its source and directly to their counterpart, or by allowing a more granular way to share this data (e.g. only reading rights, or sharing parts of the data rather than all of it);
- **Scalability of infrastructure** — the data space infrastructure is relatively easy to scale compared to other technologies, so this is particularly helpful if the problem has a non-linear (i.e. exponential) growth path;
- **Decentralized governance** — power can be distributed equally across the parties, and there is no extremely powerful man-in-the-middle;
- **Flexibility** — once the infrastructure is present, all different types of data and use cases can be created and distributed through the infrastructure.

Having more than one argument makes the case for a data space stronger.

### Do you have an idea of which parties need to be involved?

Going into the process completely without any idea of who should be in the data space is not recommended. Having an initial idea of the following roles is useful:

- **Data holders** — which parties have the systems that hold the data, are they industry parties or IT providers (for example ERP suppliers);
- **Data Space Governance Authority** — which party/parties would be interested or suited to step into the role of DSGA;
- **Data Space Operator** — which party/parties could actually build and maintain the data space, or is this a vendor selection to be done during the process;
- **Customers** — who would be willing to pay for the services of the data space; this group is important to have conversations with to validate the ideas.

Multiple roles could be fulfilled by a single organisation.

### Create a high-level business case

The business case should have initial ideas of the costs to set up the data space: software; personnel/FTE; R&D budget; marketing; legal support; miscellaneous; and third party/consultancy that help orchestrate the process (if necessary). These costs should be split into **CAPEX and OPEX**, so that there is also an idea of what it would cost to continue operating the data space once it is built.

Then look at the revenue side — figuring out what the revenue models are for the participants, which requires thinking about who should pay for the data space. Data spaces are likely to be two-sided models, so the customers could be both a data intermediary and the parties/customers to which they provide services. Revenue models to consider include: subscription model; percentage of service provider earnings; connection to the data space fee (for service providers, for data holders, for data providers, for data consumers, for end-users); and a credit system (buy credits pre-paid, per data transaction pay with credits).

The business case gives an idea of whether the data space is viable or not, and if it is not, what the gap would approximately be (**the valley of death**). One can then decide whether to reconsider the business case by finding a way to cut costs or increase the revenues.

### Final thoughts

Setting up a data space is much like setting up a new division or department within an existing organisation, or setting up a new organisation entirely, depending on the form chosen. It is much more than 'just' an IT infrastructure. Only setting up an IT system without thinking about governance or business logic is insufficient, just as much as only having a governance body without a business model or an IT infrastructure to send data across is not enough. To achieve a successful data space all of these aspects are needed — both the Business and Organisational and the Technical building blocks.

Creating a business plan could be an additional step, working out further: what the data space would do; where the data space stands in 3 to 5 years; the competition analysis; the team with which the data space is set up; and the way in which the market is served.

### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-270` | The decision to set up a data space needs to be prepared by answering why the data space is wanted. | must | `a-before-developing-a-data-space.md` §1 |
| `DSSC-BIZ-271` | The preparation must answer what the (high-level) problem to be resolved is. | must | `a-before-developing-a-data-space.md` §1, §3 |
| `DSSC-BIZ-272` | The preparation must answer the specific reason or reasons why a data space is needed to resolve the problem. | must | `a-before-developing-a-data-space.md` §1, §4 |
| `DSSC-BIZ-273` | The preparation must establish an idea of which parties need to be involved. | must | `a-before-developing-a-data-space.md` §1, §5 |
| `DSSC-BIZ-274` | The preparation must produce a high-level business case showing what the data space delivers and what it could yield. | must | `a-before-developing-a-data-space.md` §1, §6 |
| `DSSC-BIZ-275` | A proper analysis of why a data space is a good solution to the issues to be resolved is needed. | must | `a-before-developing-a-data-space.md` §2 |
| `DSSC-BIZ-276` | Having an initial idea of the data holder role is useful before entering the process. | recommended | `a-before-developing-a-data-space.md` §5 |
| `DSSC-BIZ-277` | Having an initial idea of which party or parties could take the Data Space Governance Authority role is useful before entering the process. | recommended | `a-before-developing-a-data-space.md` §5 |
| `DSSC-BIZ-278` | Having an initial idea of which party or parties could take the Data Space Operator role — or whether this is a vendor selection to be made during the process — is useful before entering the process. | recommended | `a-before-developing-a-data-space.md` §5 |
| `DSSC-BIZ-279` | Having an initial idea of who the customers are, and validating the ideas with them, is useful before entering the process. | recommended | `a-before-developing-a-data-space.md` §5 |
| `DSSC-BIZ-280` | The initial cost estimate should be split into CAPEX and OPEX. | should | `a-before-developing-a-data-space.md` §6 |
| `DSSC-BIZ-281` | Setting up an IT system without also addressing governance and business logic is insufficient. | informative | `a-before-developing-a-data-space.md` §7 |
| `DSSC-BIZ-282` | A successful data space requires both the Business and Organisational and the Technical building blocks. | must | `a-before-developing-a-data-space.md` §7 |

---

## B - Development Processes

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes

There are five development processes, all of which are complementary to one another:

- **Align Stakeholders on the Data Space Scope** — To create a 'coalition of the willing' out of stakeholders who want to investigate the extent to which they share data through a data space.
- **Develop Use Cases and Identify Functional Requirements** — Identify and describe individual use cases in detail to clarify the benefits for the data space participants and identify the data space's functional requirements.
- **Establish Organisational Form** — Create the organisational form of the data space and the governance framework.
- **Functional Analysis and Data Space Design** — Translate the functional requirements into a useful data space design.
- **Establish Data Space Agreements and Policies** — Document decisions on the functioning of the data space and create the governance framework.

> **Ambiguous:** the fifth process is named **"Establish Data Space Agreements and Policies"** in this list, but the page that documents it is titled **"B.5 - Document Data Space Policies and Agreements"** in the pane navigation. The source uses both names.

Each development process relates to building blocks from the Blueprint. As there are multiple approaches to setting up a data space, development processes can be used in a modular fashion: the data space or data space initiative can pick and choose which development processes or parts of specific processes are relevant depending on the situation. The different components of the data space are designed during the development processes; one of these components is the **rulebook**, which consists for instance of a governance structure and governance documents such as agreements and policies.

**Structure of the Development Processes.** Each development process focuses on "fundamental questions" that are crucial to its progress. These questions are detailed into steps, guiding the development and showing where answers lie within specific building blocks. Fundamental questions are often complex and their answers may evolve; therefore, they must be revisited regularly throughout the data space's lifespan. Each process lays out steps to address these questions in a structured sequence and flowchart, and each step poses specific questions that draw on insights from distinct parts of various building blocks.

**Workshops per Development Process.** Several workshops per development process have been developed to help resolve the questions asked. These workshops contain a fixed structure covering preparation work, an agenda, tools used, and follow-up actions. They are published in a separate document on the DSSC website.

### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-283` | The five development processes may be used in a modular fashion — a data space or data space initiative can pick and choose which processes or parts of processes are relevant. | may | `b-development-processes.md` |
| `DSSC-BIZ-284` | The fundamental questions of each development process must be revisited regularly throughout the data space's lifespan. | must | `b-development-processes.md` (Structure of the Development Processes) |

### B.1 - Align Stakeholders on the Data Space Scope

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes › B.1 - Align Stakeholders on the Data Space Scope

**Purpose.** To create a 'coalition of the willing' among different stakeholders who want to analyse the extent to which they are prepared to share data within or across data spaces. Successful data spaces require strong stakeholder alignment from the start; this process ensures all involved parties share a common understanding of the data space's purpose, scope, and governance principles.

**Result of the process:** the involved stakeholders have a basic idea of the purpose of the data space, why they might want to engage with it, and the principles with which they want to start; the stakeholders will have to decide on the scope of the data space on a general level; they will also decide on the context in which they will collaborate and the type of use case scenario's that will be covered; and they will determine whether the data space should be for-profit or non-profit.

**Who should take action:** one or more parties should be appointed to orchestrate the process of setting up the data space (not just this development process but all five); and all parties that have an initial interest in setting up the data space.

**What the actors can do with the result:** decide whether to continue engaging with the data space initiative. **This is the first go/no-go decision.**

**Fundamental question:** *What value is this data space meant to provide?* It is important for a "coalition of the willing" to exist prior to entering the process. Connected workshop: *Workshop 1 - Scope and Vision Data Space Ecosystem.*

**Step 1 - Theme and scope of the data space.** *Objective:* understand the general theme and scope of the data space, including industry, supply chain, or societal problems it aims to address.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What is the data space's thematic scope? | The Business Model building block explains the importance of understanding the type of problem (industrial, supply chain, or societal) that the data space intends to resolve. | A thematic scope is a general idea (preferably a consensus) among the participants as to what the data space will address. |
| 2 | What are the objectives of the data space? | The Business Model building block explains how data spaces create value by supporting one or more use case scenario's. Identifying the primary goals and objectives aids in guiding which types of use case scenario's are relevant and the impact those should have. | High-level objectives that allow for steering in use case selection. There is no immediate need to explain how these objectives will be achieved. There may be multiple objectives for each data space. |
| 3 | What are the data space's growth ambitions? | The Business Model building block distinguishes diverse ways the data space could expand. Ensure clarity on which party is responsible for monitoring and reviewing these ambitions and adapt strategies and/or policies as necessary. | An ambition on whether the data space wants to expand through: the number of participants; the number of service providers; the number of use case scenario's; the number of data products; growing into other countries; servicing different industries; cross-data space interoperability considerations. |
| 4 | What are the data space's profit ambitions? | The Business Model building block specifies elements of the business model, such as profit ambitions, which affect the financial model and stakeholder engagement. An important practical consideration is determining whether the data space will operate on a for-profit or non-profit basis. | Which parties should make a profit? The data space authority or the parties in it? The participants? The service providers? Other involved parties? Answers could vary from nobody to everybody to something more specific. |

**Step 2 - Identify high-level use case scenario's.** *Objective:* identify and define the high-level use case scenario's the data space will support.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What high-level use case scenario's should the data space support? | The Use Case Development building block offers guidance on identifying and describing high-level use case scenario's that demonstrate the data space's practical value and applications. | Outcomes could be that the governance authority has full control over which use case scenario's are developed, delivered, and monetised, or that the data space is a fully open platform where anyone can create and add use case scenario's. Hybrid models are also possible. |
| 2 | How do these use case scenario's contribute to the overarching goals and scope of the data space initiative? | The Business Model building block provides an understanding of the overarching goals and strategic decisions of the data space. | The mechanism by which the use case supports the objectives of the data space. |
| 3 | How will the data space attract and scale its user base, data providers, and service offerings to achieve critical mass, where it reaches a sufficient scale to sustain itself and generate significant value? | The Business Model building block offers guidance on aligning the value propositions of multiple organisations. | Depending on the ambitions outlined, the scaling strategy needs to be determined as they are closely linked. |

**Step 3 - Stakeholder engagement.** *Objective:* identify and engage with relevant stakeholders who will contribute to and benefit from the data space; assess their willingness to participate, their roles, and their identities within the data space.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Who are the stakeholders that are directly and indirectly affected by the data space? | The Participation Management building block provides guidance on identifying all relevant stakeholders and their relationship to the data space. | A list of stakeholders categorised according to the roles identified in Participation Management: data providers, data consumers, data rights holders, intermediaries, operators, etc. |
| 2 | Who of these stakeholders will actually participate in the data space? | The Participation Management building block provides guidance on identifying which stakeholders are willing to engage and clarifying their roles. | Identify the interested parties that might want to join the data space authority, participants that would want to become (paying) members, and participants that are interested but indirectly connected. |
| 3 | What are the objectives of participation? | The Participation Management building block provides guidance on defining goals and expectations for stakeholder participation. It is important to define these for every stakeholder that participates. | Determine per type of participant why they would want to join and what their interest is — a profit motive, data consumption, data sales, or use case scenario's that provide value. |

**Step 4 - Cooperation readiness.** *Objective:* determine whether to proceed with creating the data space based on organisational readiness and strategic alignment.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Do the organizations involved want to establish a data space? | The Organisational Form and Governance Authority building block assists data space initiative members in understanding their legal formalisation options. Initially, the data space must assess stakeholder commitment and readiness for formalisation. If stakeholders are committed, cooperation agreements are established; if not, the process halts for re-evaluation of the data space's suitability. | Clarifies the level of commitment from the stakeholders. This could range from a simple "yes" or "no" in an email to more extensive documentation in which each stakeholder indicates the conditions under which they would like to continue. The most formal way to confirm is by creating and signing cooperation agreements. |

> **Ambiguous:** Step 3 has three numbered questions, but Step 1 of B.2 cross-references "Align Stakeholders on the Data Space Scope - Step 3 - Question 4: relevant identities". No question 4 exists in Step 3 as rendered in the source.

#### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-285` | A "coalition of the willing" must exist prior to entering the Align Stakeholders development process. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` §2 |
| `DSSC-BIZ-286` | The stakeholders must decide on the scope of the data space on a general level. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` §1 |
| `DSSC-BIZ-287` | The stakeholders must decide on the context in which they will collaborate and the type of use case scenario's that will be covered. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` §1 |
| `DSSC-BIZ-288` | The stakeholders must determine whether the data space should be for-profit or non-profit. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` §1 |
| `DSSC-BIZ-289` | One or more parties should be appointed to orchestrate the process of setting up the data space, across all five development processes. | should | `b-1-align-stakeholders-on-the-data-space-scope.md` §1 |
| `DSSC-BIZ-290` | Completion of this process constitutes the first go/no-go decision on whether to continue engaging with the data space initiative. | informative | `b-1-align-stakeholders-on-the-data-space-scope.md` §1 |
| `DSSC-BIZ-291` | Clarity is required on which party is responsible for monitoring and reviewing the data space's growth ambitions, and for adapting strategies and/or policies as necessary. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` Step 1 Q3 |
| `DSSC-BIZ-292` | The data space must assess stakeholder commitment and readiness for formalisation; if stakeholders are committed, cooperation agreements are established, and if not, the process halts for re-evaluation of the data space's suitability. | must | `b-1-align-stakeholders-on-the-data-space-scope.md` Step 4 Q1 |

### B.2 - Develop Use Cases and Identify Functional Requirements

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes › B.2 - Develop Use Cases and Identify Functional Requirements

**Result of the process:** a defined set of use case scenario's described in detail, based on the high-level use case scenario's from B.1 Step 2 and aligned with the data space's purpose; and all relevant participants identified, as this is a prerequisite for establishing the organisational form. These use case scenario's will create the first value-generating activities of the data space.

**Who should take action:** the results are relevant for the data space participants, who will receive a clear definition for each use case of the individual business model, the collaborative business model, a business case for each participant, and a business case for the data space as a whole. A list of functional requirements derived from the use case scenario's will also be provided.

**What the actors can do with the result:** each actor can decide whether to continue their involvement; each actor has clarity regarding how they wish to be involved; and the process orchestrator is able to make technical, legal, and business agreements to meet the functional requirements set for each use case. It is an absolute necessity for the participants to generate enough value with the use case scenario's for the data space to be viable.

**Fundamental question**, divided into two sub-questions: *To what extent are the use case scenario's able to create a viable data space?* — (a) What value will the use case scenario's create for each of the stakeholders involved, and how? (b) What needs to be arranged (technically, legally, and otherwise) to enable value creation for the use case scenario's? Possible conditions for a *viable data space* might include: the data space can function without the need for public funding; there is a positive business case for all participants; and the data space is able to reach critical mass. Connected workshops: *Workshop 2 - Use Case Value Network*; *Workshop 3 - Use Case Business Model.*

**Step 1 - Use case selection and strategic alignment.** *Objective:* define the initial use case(s) and associated stakeholders that will allow the data space to start.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Which use case scenario's should the data space focus on first, and which are to be developed in the future? | The Business Model and Use Case Development building blocks explain that a data space generates value by enabling the creation of value in use case scenario's. | The list of high-level use case scenario's drafted in B.1 Step 2 needs to be refined and ranked according to: value created (considering the cost of development and margins); ease of development; stakeholder interests; and other parameters agreed upon by the stakeholders. Then select the top use case(s) to further develop. |
| 2 | What is the purpose or problem to be solved by the use case (business, societal, and/or environmental value)? | The Use Case Development building block explains how the purpose and value of a use case are integral to its core design and how these aspects are validated during the refinement step. | For each use case, define the problem it addresses and its intended purpose. The purpose should align with the purpose and scope of the data space and should be written in a way that brings together the relevant stakeholders. |
| 3 | Which participants or actors are directly involved in which use case scenario's, and what roles do they play? | The Contractual Framework building block enables interoperable, automated, and scalable agreements; the Organizational Form and Governance Authority building block outlines the roles, responsibilities, and relationships of participants; the Use Case Development building block describes a process for agreeing on the participants of a specific use case and their roles. | A comprehensive description of the use case and preferably a value network analysis. The offerings of data products and services between the participants should be detailed, including, if applicable, the physical flows of goods and services and monetary transactions. |
| 4 | What benefits do these use case scenario's offer to these participants? | The Business Model building block outlines how the value propositions of participants influence the business model of the data space. The Use Case Development building block describes how the value propositions for use case participants are part of the core design of a use case. | For each participant, a clear value proposition per use case, including: the value the participant adds; the actions each participant undertakes to deliver that value; the cost model of delivery; the revenue model of delivery; and the recipients of the participant's offerings. The business model radar serves as a useful tool. |

**Step 2 - Legal and compliance framework.** *Objective:* ensure adherence to legal and regulatory requirements for secure and compliant data sharing.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What legal agreements are necessary for governing data sharing, usage rights, and liabilities across different use case scenario's? | The Contractual Framework building block discusses factors that may trigger the application of various legal requirements, provides pointers on relevant rules and regulations, and offers insights into which agreements might be necessary. | A list of legal and compliance-related items that have been triggered (see the flow charts provided) — for instance personal data, data intermediaries — and whether specific legal norms apply because the data space is in the defence or health sectors. Next, a list of the documents required to address the triggers activated. Be very clear about the level at which these agreements should be made: for a data space in general, for individual users, or for users interacting with one another. Which Service Level Agreements pertain to the data space, and which are for a service operator? |

**Step 3 - Service design.** *Objective:* define how the use case scenario's and their data products will be offered in the data space, and support the identified use case scenario's by establishing the necessary federation, participant agent, and value creation services, as well as the parties responsible for delivering these services.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What are the core services required within the data space, and how do they relate to the business models of the use case scenario's and data space itself? | The core services are the minimum services necessary to facilitate the functioning of the data space and its (initial) use case(s). These may include federation, participant agent, value creation services, or any combination thereof. | Define a list of services that the data space and its participants need to offer to one another in order to ensure the data space can exist. Each data space possesses its own core service. |
| 2 | What value creation services are considered in the data space? | The Value Creation Services building block provides an approach for managing services that extend the core functionality required by the use case scenario's to create additional value. | Define a list of services that the data space and its participants need to offer one another. Aspects to answer include: how value creation services relate to the business model and use case(s); how they are governed (who provides them and under what conditions); and whether they will be visible and available to all participants or restricted to a subset. |
| 3 | Which parties will offer what services? | The Business Model building block shows how this question leads to a make-or-buy decision. The Intermediaries and Operators building block helps identify to whom these services would be provided: only to companies and organisations, or also to individuals? | Understanding the technical requirements and determining whether these should be bought or made. Defining how critical these services are informs the strategic decision for the data space orchestrator. Identifying the essential parties for the business model and the power dynamics between the participants, the service providers, and the data space authority is crucial. |
| 4 | How is data used by each use case within the data space and/or across data spaces, and what types of data are essential for its operation? | The Data Space Offering building block provides guidance for participants in creating resources and data product offerings, helping determine data sources, formats, and quality requirements. The Use Case Development building block explains how data products can either be developed within the data space or obtained from another data space for a cross-data space joint use case. | A complete picture of how data services and data products move around in the data space — a clear description of the data products that move throughout the data space, from whom to whom. |

#### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-293` | All relevant participants must be identified in this process, as this is a prerequisite for establishing the organisational form. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` §1 |
| `DSSC-BIZ-294` | The process must produce a list of functional requirements derived from the use case scenario's. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` §1 |
| `DSSC-BIZ-295` | Each use case must receive a clear definition of the individual business model, the collaborative business model, a business case for each participant, and a business case for the data space as a whole. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` §1 |
| `DSSC-BIZ-296` | It is advisable to establish how the term 'viable data space' is defined within the data space initiative. | recommended | `b-2-develop-use-cases-and-identify-functional-requirements.md` §2 |
| `DSSC-BIZ-297` | The list of high-level use case scenario's must be refined and ranked by value created, ease of development, stakeholder interests, and other parameters agreed upon by the stakeholders. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 1 Q1 |
| `DSSC-BIZ-298` | For each use case, the problem it addresses and its intended purpose must be defined, and the purpose must align with the purpose and scope of the data space. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 1 Q2 |
| `DSSC-BIZ-299` | For each participant there should be a clear value proposition per use case, covering the value added, the actions undertaken to deliver it, the cost model, the revenue model, and the recipients of the participant's offerings. | should | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 1 Q4 |
| `DSSC-BIZ-300` | The process must produce a list of the legal and compliance items triggered, and a list of the documents required to address them. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 2 Q1 |
| `DSSC-BIZ-301` | It must be clear at which level each agreement is made — for the data space in general, for individual users, or for users interacting with one another. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 2 Q1 |
| `DSSC-BIZ-302` | The core services — the minimum services necessary to facilitate the functioning of the data space and its initial use cases — must be defined. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 3 Q1 |
| `DSSC-BIZ-303` | It must be determined whether value creation services will be visible and available to all data space participants or restricted to specific subsets. | must | `b-2-develop-use-cases-and-identify-functional-requirements.md` Step 3 Q2 |

### B.3 - Establish Organisational Form

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes › B.3 - Establish Organisational Form

**Result of the process:** formalisation in collaboration, by defining the organisational form; and clarity on the main parameters of the governance framework, along with the roles and responsibilities within the data space. **Who should take action:** the (self-)determined establishing parties (founders) of the data space. **What the actors can do with the result:** participants can start joining the data space, and the establishing parties have an organisational form through which further agreements can be made.

**Fundamental question:** *how do we — the founders of the data space — wish to collaborate?* Within the steps of this development process, the **second go/no-go decision** is made. The first step concerns the investment decision of the founders: are they prepared to provide the funds to initiate the data space? If insufficient value is generated for parts of the data space, some assumptions or models may need to be revisited, or the members could consider a redistribution of value; if the value remains inadequate, there is no real reason for the data space to continue. Value here could be monetary but could also be something else, such as an improvement in air quality. Connected workshop: *Workshop 4 - Data Space Organisational Form.*

**Step 1 - Formalising Commitment and Investment Decision.** The parties that ultimately sign the constitutional agreement (i.e. founders) will become the governance authority (e.g. assembly of members) and elect, select or appoint the executive body (e.g. director, board of directors). *Objective:* divide roles and responsibilities among the founders of the data space.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What are the roles and responsibilities of the data space founders? | As explained in the Organisational Form and Governance Authority building block, the establishment of the data space requires the parties involved to agree to commit funds, capital, or in-kind contributions (e.g. intellectual property, IT capabilities). | The partners commit resources to one another. The manner in which these resources are brought in informs the decision regarding the organisational form made in step 2. It should be clear what each partner contributes to the foundation and maintenance of the data space. |
| 2 | What is the business model for the data space governed by the governance authority? | The Business Model building block provides guidelines for new business models, outlining financial and sustainability strategies for the data space. | The divisions of profits and losses are agreed upon. It is important to agree on how money is spent (e.g. paid out as dividends to shareholders, reinvested in the data space) and who will contribute which amounts of resources in case the data space requires additional funding. |

**Step 2 - Determine and Establish the Organisational Form.** *Objective:* create the data space and formalise its existence, including the establishment of its governance authority.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What organisational form is chosen for the data space? | The Organisational Form and Governance Authority building block offers an overview in the form of a decision tree to help members understand their options for legal structures. | The decision regarding the organisational form is made here. A letter of intent or a memorandum of understanding may be signed by the founders to confirm their intention to formalise their commitment in the future. |
| 2 | What are the data space agreements necessary for the establishment of the data space? | The Contractual Framework and Organisational Form and Governance Authority building blocks describe the different data space agreements that must be signed by the founders and what additional steps might be necessary (e.g. entry into a company registry, notary's verification). | The necessary foundational agreement (e.g. articles of association, statute) is signed between the founders. The data space as a company is entered into a company registry (depending on the country of establishment). The data space can start its activities. |
| 3 | What governance structure of the data space should be established? | The Organisational Form and Governance Authority building block offers an overview of the governance authority's structure based on the legal organisational form. | The legally required governance bodies of the data space organisation are created and effectuated. Additionally, if necessary or desired, additional bodies (e.g. task forces, working groups, committees) can be determined and created. |

**Step 3 - Determine and record key organisational documents and processes.** *Objective:* determine and record the essential documents by which the data space is governed and develop the main processes of governance.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Which activities will the governance authority overall and its bodies perform to run the data space? | The Business Model building block offers an overview of the roles of the governance authority concerning the business model. The Organisational Form and Governance Authority building block provides, from a legal perspective, a short description of the roles of different governance bodies and procedures of their functioning. | The data space members need to decide on the division of powers between the general assembly and the executive body — which issues refer to day-to-day operation and can be decided by the executive alone (e.g. acceptance of participants, conclusion of agreements with service providers), and which are the most important decisions that must be taken by the assembly of all members (e.g. appointment/election of a new director, admission of a new member, adoption of data space policies, creation of other governance bodies and determination of their mandate). |
| 2 | What are the processes through which the governance authority should perform their duties, and how should they be monitored and reviewed? | The Organizational Form and Governance Authority building block indicates some of the decision-making processes (e.g. some decisions must be taken unanimously by the assembly of members). Many rules on decision-making come directly from the legislation applicable to the founding agreement; however, members can decide additionally on their own rules. | The processes for executing the previously defined responsibilities are designed — for example, how a membership application should be made, when the assembly should convene and whether it decides unanimously or by majority; who should prepare the business strategy and how it should be adopted. |

**Step 4 - Strategy for the Data Space.** *Objective:* define the way in which the governance authority aims to keep the data space up-to-date and relevant.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | How does the data space identify the need to change its business model, redesign it, and effectuate these desired changes? | The Business Model building block offers insights into the regular monitoring, reviewing, and adaptation of the business model. | A process detailing how the business model is reviewed, who is responsible for this, and the metrics and KPIs that determine when and how the business model should be adjusted. |
| 2 | How will growth ambitions be realised? | This step refers back to Step 1 (questions 3 and 4) of the Align Stakeholders on the Data Space Scope development process. The Business Model building block explains how multi-sidedness is an important characteristic of a data space and discusses how a business model may evolve over time. | A clear decision on the direction in which the data space should grow (i.e. more use cases, service providers, primarily participants) and a process for achieving that growth, including who is responsible. |
| 3 | How does the data space foster a collaborative culture and manage transparency and efficient communication? | The Participation Management building block suggests mechanisms for improving participation management through feedback channels, dispute resolution, and fostering a collaborative culture. | Define what a collaborative culture is for the data space by establishing core values and fully integrating them into the design principles. Translate this into a communication strategy tailored for each type of participant. |

#### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-304` | Completion of this process constitutes the second go/no-go decision. | informative | `b-3-establish-organisational-form.md` §2 |
| `DSSC-BIZ-305` | Establishing the data space requires the parties involved to agree to commit funds, capital, or in-kind contributions (e.g. intellectual property, IT capabilities). | must | `b-3-establish-organisational-form.md` Step 1 Q1 |
| `DSSC-BIZ-306` | It must be clear what each partner contributes to the foundation and maintenance of the data space. | must | `b-3-establish-organisational-form.md` Step 1 Q1 |
| `DSSC-BIZ-307` | The divisions of profits and losses must be agreed upon, including how money is spent and who contributes what if additional funding is required. | must | `b-3-establish-organisational-form.md` Step 1 Q2 |
| `DSSC-BIZ-308` | The founders may sign a letter of intent or memorandum of understanding to confirm their intention to formalise their commitment in the future. | may | `b-3-establish-organisational-form.md` Step 2 Q1 |
| `DSSC-BIZ-309` | The necessary foundational agreement (e.g. articles of association, statute) must be signed between the founders. | must | `b-3-establish-organisational-form.md` Step 2 Q2 |
| `DSSC-BIZ-310` | Depending on the country of establishment, the data space as a company is entered into a company registry. | must | `b-3-establish-organisational-form.md` Step 2 Q2 |
| `DSSC-BIZ-311` | The legally required governance bodies of the data space organisation must be created and effectuated. | must | `b-3-establish-organisational-form.md` Step 2 Q3 |
| `DSSC-BIZ-312` | Additional governance bodies (e.g. task forces, working groups, committees) may be determined and created if necessary or desired. | may | `b-3-establish-organisational-form.md` Step 2 Q3 |
| `DSSC-BIZ-313` | The data space members must decide on the division of powers between the general assembly and the executive body. | must | `b-3-establish-organisational-form.md` Step 3 Q1 |
| `DSSC-BIZ-314` | The processes through which the governance authority performs its duties must be designed, and how they are monitored and reviewed must be defined. | must | `b-3-establish-organisational-form.md` Step 3 Q2 |
| `DSSC-BIZ-315` | A process must be defined detailing how the business model is reviewed, who is responsible, and the metrics and KPIs that determine when and how it should be adjusted. | must | `b-3-establish-organisational-form.md` Step 4 Q1 |
| `DSSC-BIZ-316` | A clear decision on the growth direction of the data space and a process for achieving that growth, including who is responsible, must be established. | must | `b-3-establish-organisational-form.md` Step 4 Q2 |
| `DSSC-BIZ-317` | The data space should define what a collaborative culture means for it by establishing core values and integrating them into its design principles, and translate this into a communication strategy tailored for each type of participant. | should | `b-3-establish-organisational-form.md` Step 4 Q3 |

### B.4 - Functional Analysis and Data Space Design

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes › B.4 - Functional Analysis and Data Space Design

**Result of the process:** translates the functional requirements into a design for the data space, detailing the necessary building blocks, standards, and services; the design should include technical and organizational components, as well as agreements about governance and policies. **Who should take action:** the data space authority is responsible for documenting the decisions made — such as those regarding standards, roles, responsibilities, and other specifications — in the rulebook. **What the actors can do with the result:** service providers can start building and connecting their services according to the specifications of the data space, and participants can start preparing their offerings and their connection to the data space.

**Fundamental question:** *Which data space design best meets the objectives and needs of participants while ensuring secure, compliant, and efficient data sharing?* Connected workshops: *Workshop 5 - Data Interoperability*; *Workshop 6 - Integrate and Connect*; *Workshop 7 - Data Value Creation Enablers.*

**Step 1 - Secure Participant Onboarding and Offboarding.**

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Which types of identities need to be supported in your data space? And what are the conditions for their issuing? | The Identity and Attestation Management building block provides an approach for managing identities and attestations while ensuring interoperability, security, and trust based on widely recognised technical standards and regulatory frameworks. | A list of identities for the data space. This can relate to the identity of organisations, individuals and/or services or other digital assets. The division can be created using the technical roles within a data space (data provider, data holder, data consumer, etc.) or the business roles (for example manufacturer and OEM). With each identity a list of conditions for issuing should be made. |
| 2 | Which other types of attestations are needed? And what are the conditions for their issuing? | The Identity and Attestation Management building block provides a division into three types of functional dimensions for identity and attestations, plus best practices and references to technical standards for data spaces. | As a minimum, this includes a **data space membership credential**, which provides proof that the entity adheres to the data space rulebook. In addition, other types of attestations may be needed, for example to prove compliance with policies related to data rights, consent, and security. |
| 3 | Which processes need to be in place to verify and enforce compliance with the Rulebook? | The Trust Framework building block provides general elements of the trust framework and a defining format of claims to make it machine readable, including a conformity assessment workflow. | For each of the credentials identified, processes need to be in place for their issuing — for instance membership credentials and other conformity credentials. Processes can include the signing of legal documents or automated verifications (e.g. credit score). |
| 4 | For each of the processes: how will the roles of Trust Anchors and Trust Services be implemented? | The Trust Framework building block provides the types of roles needed to ensure this trust, and explains their breadth of scope. | Which trust anchors exist as core trusted entities in the data space — this can stem from legislation, contractual conditions or the generally accepted position of a certain entity. And which trust services are available to implement their role in the digital world and issue credentials on their behalf. For a single trust anchor, multiple trust services can be operated, and a single trust service can operate for multiple trust anchors. |

**Step 2 - Trust among participants.**

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | How can data space participants verify compliance with access and usage policies using the trust framework? | The Access Control and Usage Policies Enforcement building block identifies the available trust anchors and trust services. | An overview of the different trust policies needed in the data space to allow for trustworthy exchange. Trust services can be used for the (automated) verification of claims of compliance, which can be used to evaluate access and usage policies. |
| 2 | Which common access and usage policies need to be included in the data space rulebook? | The Access Control and Usage Policies Enforcement building block provides several best practices and explainers on how to select and identify special policies. | A list of drafted policies which will later be part of the rulebook. Depending on the use cases supported, some common access and usage policies might exist for specific (types of) data products. These might stem from regulatory requirements (e.g. consent for the sharing of personal data, based on the GDPR) or from the legal framework of the data space. In other scenarios they can also serve as optional templates or best practices. |

**Step 3 - Agreements on Data Models and Protocols to Exchange Data.** *Objective:* the data models and communication protocols are defined. This step is highly specialized and heavily relies on the Data Models building block.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | For which (categories of) data products does the data space need to manage semantics? | The Data Models building block offers guidance on designing, reusing, and governing data models to enable common data sharing. | Inventory of necessary standards and guidelines for consistent data interpretation and integration. |
| 2 | Which data models are already available and can be re-used? Which new (shared) data models need to be created? | The Data Models building block provides an explainer on the abstraction levels of data models for semantically annotating the data being shared. | Determine whether to reuse current data models or develop new ones, and clearly define the levels of abstraction required to semantically describe the data products. |
| 3 | What kind of meta-standard will be used to express the data models in the data space? | The Data Models building block offers a list of best practices for metamodels to establish and/or annotate a domain-specific data model. | Align with one or more meta-standards to describe the data models, depending on the necessary levels of abstraction. For instance, **RDF** or **JSON Schema**. |
| 4 | What are the data space specific requirements for standardized data exchange protocols? | The Data Exchange building block offers guidance on ensuring that data is exchanged according to the specified semantics within the data model. | A list of functional requirements for protocols and interfaces to ensure compatibility and integration with the data models. |
| 5 | Which protocols meet these requirements? | The Data Exchange building block elaborates on the process of how to choose the exchange protocols and provides best practices. | A list of exchange protocols for the exchange of data that can be implemented in the data space. Identify whether existing protocols can be used or whether new ones are necessary. |
| 6 | How will data models be managed within the data space? | The Data Models building block describes how different abstraction levels of data models can be used in actual protocols for data exchange. | Data exchanged via the data exchange protocol are semantically compliant with the data models. For instance, a data schema (e.g. JSON Schema) can be used in the data exchange protocols during data transfer to provide technical validation. |
| 7 | How will the data space manage the agreed data exchange protocols? | The Data Exchange building block offers specifications and capabilities which can be used to design policies to manage the data exchange protocols. | Technical agreements need to be governed. This starts by publishing the data exchange protocol (such as an **OpenAPI specification**) in a vocabulary service. Furthermore, a strategy for maintenance and updates of the protocol needs to be defined (version management). |

**Step 4 - Accountability and Control of Data Usage.**

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | For which data products is provenance, traceability and observability required? And what needs to be recorded? | The Provenance, Traceability & Observability building block provides a process and best practices for implementing provenance, transaction traceability and transaction observability. | Determine why and what needs to be logged within the data space. For each offering, define what type of observability, provenance and traceability is possible and/or required. |
| 2 | Which data model will be used for recording and storing provenance, traceability and observability data? | The Provenance, Traceability & Observability building block offers specific information on the metadata models used in data spaces. | A chosen open standard data model for structuring the logs of the data transactions in the data space, to be amended if the standard is insufficient for the data space. |
| 3 | How will the logs be stored securely, and who can access them? | The Provenance, Traceability & Observability building block provides a path for how to decide this with some standard architectures in the best practices. | A storage architecture determining where and how logs will be stored, as well as the rules of when and how parties can access them. |
| 4 | How will the agreements on provenance, traceability and observability be governed? | The Provenance, Traceability & Observability building block | *(no outcome given in the source)* |

**Step 5 - Categorisation and Implementation of Services.**

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | Which discovery services are needed? And who is providing them? | The Publication and Discovery building block addresses how the Dataspace Protocol for managing the exchange of catalogue entries is set up. | A clear overview of the discovery services needed and a specific party responsible for providing them. These services can be centralised in a single party, or decentralised by providing them through multiple parties. |
| 2 | How will catalogue services be implemented in the data space? | The Publication and Discovery building block provides an explainer of catalogues in the Dataspace Protocol. | Provide a specification of the **Dataspace Protocol**, defining the schemas and protocols necessary for the participants to negotiate agreements, access data, and publish and discover metadata. |
| 3 | What is the minimum set of metadata which needs to be provided for the (types of) data products provided in a data space? | The Data, Services, and Offerings Descriptions building block provides an overview of how the metadata could be implemented. | The **Data Act, through article 33**, provides a minimum set of metadata to be provided for each data product by data providers in a data space. Determine this minimum set for the data products offered. The rulebook can provide further (domain specific) attributes. The outcomes need to be documented in the rulebook of the data space. |
| 4 | Which functionalities of the data space could or should be provided by dedicated intermediary service providers? | The Intermediaries and Operators building block outlines the existence of intermediary service providers that allow participants without their own participant agent to join a data space. | Design the functionalities for each specific service provider and the data space authority. Consider the business models defined in *Develop Use Cases and Identify Functional Requirements*, as well as the agreements made in *Establish Organisational Form*, to ensure the technical design aligns with the business and legal requirements. |

> **Ambiguous:** the header cell of the Step 4 table reads `4` where the other step tables read `#`, and the last row of that table has an empty "Potential Outcomes" cell. Both are as in the source.

#### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-318` | The data space authority is responsible for documenting the decisions made — standards, roles, responsibilities, and other specifications — in the rulebook. | must | `b-4-functional-analysis-and-data-space-design.md` §1 |
| `DSSC-BIZ-319` | The data space design should include technical and organizational components as well as agreements about governance and policies. | should | `b-4-functional-analysis-and-data-space-design.md` §1 |
| `DSSC-BIZ-320` | A list of the identity types the data space supports must be produced, covering organisations, individuals and/or services or other digital assets as applicable. | must | `b-4-functional-analysis-and-data-space-design.md` Step 1 Q1 |
| `DSSC-BIZ-321` | For each identity, a list of conditions for issuing should be made. | should | `b-4-functional-analysis-and-data-space-design.md` Step 1 Q1 |
| `DSSC-BIZ-322` | As a minimum, the attestations supported must include a data space membership credential, providing proof that the entity adheres to the data space rulebook. | must | `b-4-functional-analysis-and-data-space-design.md` Step 1 Q2 |
| `DSSC-BIZ-323` | For each identified credential, processes need to be in place for its issuing. | must | `b-4-functional-analysis-and-data-space-design.md` Step 1 Q3 |
| `DSSC-BIZ-324` | The trust anchors of the data space must be identified, together with the trust services available to implement their role and issue credentials on their behalf. | must | `b-4-functional-analysis-and-data-space-design.md` Step 1 Q4 |
| `DSSC-BIZ-325` | An overview of the trust policies needed in the data space must be created to allow trustworthy exchange. | must | `b-4-functional-analysis-and-data-space-design.md` Step 2 Q1 |
| `DSSC-BIZ-326` | The common access and usage policies to be included in the data space rulebook must be drafted. | must | `b-4-functional-analysis-and-data-space-design.md` Step 2 Q2 |
| `DSSC-BIZ-327` | An inventory of the standards and guidelines necessary for consistent data interpretation and integration must be produced. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q1 |
| `DSSC-BIZ-328` | It must be determined whether to reuse existing data models or develop new ones, and the levels of abstraction required to semantically describe the data products must be clearly defined. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q2 |
| `DSSC-BIZ-329` | The data space must align with one or more meta-standards to describe its data models — for instance RDF or JSON Schema. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q3 |
| `DSSC-BIZ-330` | A list of functional requirements for protocols and interfaces must be produced, to ensure compatibility and integration with the data models. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q4 |
| `DSSC-BIZ-331` | A list of exchange protocols to be implemented in the data space must be produced, identifying whether existing protocols can be used or new ones are necessary. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q5 |
| `DSSC-BIZ-332` | Data exchanged via the data exchange protocol must be semantically compliant with the data models. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q6 |
| `DSSC-BIZ-333` | The data exchange protocol (such as an OpenAPI specification) must be published in a vocabulary service. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q7 |
| `DSSC-BIZ-334` | A strategy for maintenance and updates of the data exchange protocol (version management) needs to be defined. | must | `b-4-functional-analysis-and-data-space-design.md` Step 3 Q7 |
| `DSSC-BIZ-335` | It must be determined why and what needs to be logged within the data space, and for each offering what type of observability, provenance and traceability is possible and/or required. | must | `b-4-functional-analysis-and-data-space-design.md` Step 4 Q1 |
| `DSSC-BIZ-336` | An open standard data model must be chosen for structuring the logs of data transactions in the data space, to be amended if the standard is insufficient. | must | `b-4-functional-analysis-and-data-space-design.md` Step 4 Q2 |
| `DSSC-BIZ-337` | A storage architecture must be defined determining where and how logs are stored, and the rules for when and how parties can access them. | must | `b-4-functional-analysis-and-data-space-design.md` Step 4 Q3 |
| `DSSC-BIZ-338` | The discovery services needed must be identified together with the specific party responsible for providing them; these services can be centralised in a single party or decentralised across multiple parties. | must | `b-4-functional-analysis-and-data-space-design.md` Step 5 Q1 |
| `DSSC-BIZ-339` | A specification of the Dataspace Protocol must be provided, defining the schemas and protocols necessary for participants to negotiate agreements, access data, and publish and discover metadata. | must | `b-4-functional-analysis-and-data-space-design.md` Step 5 Q2 |
| `DSSC-BIZ-340` | The minimum set of metadata for the data products offered in the data space must be determined, taking the Data Act article 33 minimum as the baseline. | must | `b-4-functional-analysis-and-data-space-design.md` Step 5 Q3 (Data Act Art. 33) |
| `DSSC-BIZ-341` | The rulebook may provide further domain-specific metadata attributes for the (types of) data products shared in the data space. | may | `b-4-functional-analysis-and-data-space-design.md` Step 5 Q3 |
| `DSSC-BIZ-342` | The metadata outcomes need to be documented in the rulebook of the data space. | must | `b-4-functional-analysis-and-data-space-design.md` Step 5 Q3 |

### B.5 - Document Data Space Policies and Agreements

> **Source** · DSSC Blueprint v3.0 › Introduction Co-Creation Method › B - Development Processes › B.5 - Document Data Space Policies and Agreements

> **Ambiguous:** this page has no breadcrumb trail in the source's index and its own heading is a slug (`b-5-document-data-space-policies-and-agreements`); in the source tree it sits at the co-creation pane root rather than beneath *B - Development Processes*, where B.1–B.4 sit. The pane navigation, however, lists it in sequence with B.1–B.4 under **Co-Creation Method**, and the *B - Development Processes* page counts it as the fifth of five development processes. It is rendered here under *B - Development Processes* on that basis. Its name is taken from the pane navigation; the *B - Development Processes* page calls the same process **"Establish Data Space Agreements and Policies"**.

**Result of the process:** the completion of the development processes (at least of their first iteration) by identifying and putting on record all policies, guidelines, procedures and agreements needed to run the data space; missing policies, guidelines and procedures are developed and also recorded; and agreements are prepared to be concluded with third parties, such as other data spaces, enabling or value-added service providers, or utilities like internet service, water and electricity providers — including the preparation of general terms and conditions for the use of the data space. Agreements between data space participants (i.e. bilateral agreements between a data provider and a data user) are **outside of the scope** of this development process.

**Who should take action:** the data space governance authority (executive body) identifies the necessary policies and keeps record of them; the governance authority (executive body, potentially a special working group/committee) drafts and adopts missing policies, guidelines and procedures — adoption is likely to be done by the representative assembly of all data space members; and the governance authority (executive body) has its contractual framework in place.

**What the actors can do with the results:** the governance authority will act according to the set policies; it can impose the policies onto the data space participants and service providers via concluded contracts (which include terms and conditions of use); and the first iteration of the data space definition is finished once this process is done. Formally ending a cycle allows a new iteration to start with fresh goals for improvement.

**Fundamental question:** *What policies and agreements need to be documented for the data space to operate within the appropriate laws and regulations, and how should they be recorded?* The process has three steps: identify all items that constitute the governance framework of the data space; if some of the identified items are not yet drafted, draft and adopt them and keep the documentation; and identify all agreements that the data space needs to function and draft them, keeping the documentation. All the items under points 1)–3) should be documented in one place (which can be a rulebook or have any other name) in human-readable and, if possible, machine-readable formats. Connected workshop: *Workshop 8 - Data Space Rulebook.*

**Step 1 - Identify necessary policies, guidelines and procedures.** *Objective:* to record all the policies necessary to allow the data space to run as intended.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What are the basic organisational policies that need to be drafted by the governance authority? | The internal policies that a data space needs are defined by the regulatory requirements as well as internal ambitions. The Regulatory Compliance building block offers an overview of triggers that result in obligations that may also require a special policy. Every organisation needs a policy on personal data protection. Cybersecurity policy is crucial for any data-driven organisation. Intellectual property rights, sustainability and competition policies may be desirable for some organisations. | Examine the trigger flowcharts in the building block and identify the necessary policies/documents to adhere to the relevant legislation. |
| 2 | Which design choices from the Functional Analysis and Data Space Design development process need policies to be included in the governance framework? | In many building blocks numerous decisions are made, particularly regarding policies, the use of standards and software. | For each of the building blocks, the addressed elements are identified. To properly realise a functionality in the data space you need: a technical implementation to execute the functionality; a party responsible for managing this technical implementation; and some sort of governance document (like a policy) to determine what the responsible party is allowed to do and, for example, what models need to be used with the technical implementation. The final two points need to be recorded in the rulebook if not done so already for each functionality. |

The non-exclusive list of per-building-block elements that could be considered for inclusion in the governance framework, as given in the source:

- **Identity and Attestation Management** — The Blueprint recommends using **W3C Verifiable Credentials** and **Decentralized Identifiers (DIDs)** to manage digital identities and verify their information.
- **Trust Framework** — The data space must specify the standards and methods for ensuring compliance with regulations, identifying **Trusted Service Providers (TSPs)**, and managing them in accordance with the **Electronic Identification and Trust Services (eIDAS) regulation**. This includes validating and verifying identities using software that adheres to these standards, with providers available in the DSSC Toolbox.
- **Access & Usage Policy Enforcement** — The Blueprint prescribes using **Open Digital Rights Language (ODRL)** to create and enforce usage policies. Tools like the Policy Information Point Service can support these functionalities.
- **Data Models** — The data space must define which data models are used and who manages them. These models are typically published and maintained centrally, facilitated by a vocabulary service. Agreements with service providers should be established.
- **Data Exchange** — Data exchange protocols are data space agnostic, so the data space must determine which protocols will be used for data transfer in relation to the participant agent service.
- **Provenance, Traceability & Observability** — Record all of the decisions made in step 4 of *Functional Analysis and Data Space Design*: the mandatory events, the chosen data models, the storage architecture, and the access policies, in the data space's rulebook.
- **Data, Services, and Offerings Descriptions** — The data space should specify the standards and rules for describing data and services, with **Data Catalog Vocabulary (DCAT)** recommended in the Blueprint for this purpose.
- **Publication and Discovery** — This involves the control plane of the participant agent service, where the data space must determine whether to adopt local or centralised cataloguing for publishing and discovering data, services, and offerings.
- **Value Creation Services** — There are various services designed to create value from the data shared within the data space, some of which are listed in the DSSC Toolbox.
- **Data Space Offerings** — This building block can provide information on when or how much the data space governance framework should enforce common standards and/or policies for data products.

**Step 2 - Draft and document missing policies.** *Objective:* create a comprehensive governance framework that prescribes the internal rules by which the data space is governed.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 2 | Which legislative frameworks/triggers must be considered for the internal rules? | The Regulatory Compliance building block offers guidelines to ensure compliance with relevant legislation and regulations throughout the data space's lifecycle. | Related to step 2 in *Develop Use Cases and Identify Functional Requirements*, this step elaborates on where the methods for adhering to these regulations are documented. It should provide a list of internal policies that support compliance with GDPR and other relevant rules and legislation. |
| 3 | Which legislative frameworks are relevant when drafting contractual clauses? | The Contractual Framework building block identifies elements of the contractual framework that address data protection, intellectual property, cybersecurity, risk management policies, and the technical standards required by law. | This step elaborates on the methods for adhering to these regulations. It should include a list of external agreements that support adherence to IP legislation, for example. |

> **Ambiguous:** the two questions in Step 2 are numbered `2` and `3` in the source; there is no question `1`.

**Step 3 - Draft and document necessary agreements.** *Objective:* identify various agreements that the data space needs to function and draft them (or at least their purpose, principles and main elements). The formalisation of all the collaborations of the data space happens under the operational processes.

| # | Question | Building Block Provides | Potential Outcomes |
|---|---|---|---|
| 1 | What are the agreements with third parties and/or other data spaces? | The Contractual Framework building block provides an overview of what a contractual framework looks like and enables the legal implementation of other building blocks. The Regulatory Compliance building block contains guidance on legislative requirements that may need to be considered in the data space contracts. | Draft any agreements related to enabling services, such as service agreements, and the terms and conditions of use of the data space. Ensure that the agreements in which the data space is involved are clear and comply with the legal requirements of the applicable law. |
| 2 | Are there any special third parties (e.g. data intermediation service providers, gatekeepers) involved in contracts with this data space? | The Regulatory Compliance building block contains a table listing different special types of third parties and providing explanations on the points of attention. | Consult the table and check whether any special types of third parties are involved with the data space. If yes, review the agreements prepared for conclusion with them and ensure that they comply with the legal requirements. |

#### Requirements

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-BIZ-343` | All policies, guidelines, procedures and agreements needed to run the data space must be identified and put on record. | must | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-344` | Missing policies, guidelines and procedures must be developed and recorded. | must | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-345` | Agreements to be concluded with third parties must be prepared, including general terms and conditions for the use of the data space. | must | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-346` | Bilateral agreements between data space participants (a data provider and a data user) are outside the scope of this development process. | informative | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-347` | The data space governance authority (executive body) identifies the necessary policies and keeps record of them. | must | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-348` | Adoption of missing policies, guidelines and procedures is likely to be done by the representative assembly of all data space members. | informative | `b-5-document-data-space-policies-and-agreements.md` §1 |
| `DSSC-BIZ-349` | All items constituting the governance framework and the necessary agreements should be documented in one place — which can be a rulebook or have any other name. | should | `b-5-document-data-space-policies-and-agreements.md` §2 |
| `DSSC-BIZ-350` | That documentation should be in human-readable and, if possible, machine-readable formats. | should | `b-5-document-data-space-policies-and-agreements.md` §2 |
| `DSSC-BIZ-351` | Every organisation needs a policy on personal data protection. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q1 |
| `DSSC-BIZ-352` | A cybersecurity policy is crucial for any data-driven organisation. | should | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q1 |
| `DSSC-BIZ-353` | Intellectual property rights, sustainability and competition policies may be desirable for some organisations. | may | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q1 |
| `DSSC-BIZ-354` | To realise a functionality in the data space, a technical implementation to execute the functionality is needed. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-355` | To realise a functionality in the data space, a party responsible for managing that technical implementation is needed. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-356` | To realise a functionality in the data space, a governance document (such as a policy) determining what the responsible party is allowed to do and which models must be used is needed. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-357` | The responsible party and the governance document for each functionality need to be recorded in the rulebook. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-358` | The Blueprint recommends using W3C Verifiable Credentials and Decentralized Identifiers (DIDs) to manage digital identities and verify their information. | recommended | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-359` | The data space must specify the standards and methods for ensuring compliance with regulations, identifying Trusted Service Providers (TSPs), and managing them in accordance with the eIDAS regulation. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-360` | The Blueprint prescribes using Open Digital Rights Language (ODRL) to create and enforce usage policies. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-361` | The data space must define which data models are used and who manages them. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-362` | Agreements with service providers for the publication and maintenance of data models should be established. | should | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-363` | The data space must determine which data exchange protocols will be used for data transfer in relation to the participant agent service. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-364` | The mandatory events, chosen data models, storage architecture, and access policies decided for provenance, traceability and observability must be recorded in the data space's rulebook. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-365` | The data space should specify the standards and rules for describing data and services; Data Catalog Vocabulary (DCAT) is recommended in the Blueprint for this purpose. | should | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-366` | The data space must determine whether to adopt local or centralised cataloguing for publishing and discovering data, services, and offerings. | must | `b-5-document-data-space-policies-and-agreements.md` Step 1 Q2 |
| `DSSC-BIZ-367` | A list of internal policies that support compliance with GDPR and other relevant rules and legislation should be produced. | should | `b-5-document-data-space-policies-and-agreements.md` Step 2 Q2 |
| `DSSC-BIZ-368` | A list of external agreements that support adherence to the relevant legislation (for example IP legislation) should be produced. | should | `b-5-document-data-space-policies-and-agreements.md` Step 2 Q3 |
| `DSSC-BIZ-369` | Agreements related to enabling services, such as service agreements, and the terms and conditions of use of the data space must be drafted. | must | `b-5-document-data-space-policies-and-agreements.md` Step 3 Q1 |
| `DSSC-BIZ-370` | The agreements in which the data space is involved must be clear and comply with the legal requirements of the applicable law. | must | `b-5-document-data-space-policies-and-agreements.md` Step 3 Q1 |
| `DSSC-BIZ-371` | It must be checked whether any special types of third parties (e.g. data intermediation service providers, gatekeepers) are involved with the data space; if so, the agreements prepared for conclusion with them must be reviewed for compliance with the legal requirements. | must | `b-5-document-data-space-policies-and-agreements.md` Step 3 Q2 |

---

## Open questions

Ambiguities, gaps and contradictions found in the source for this pane:

- **The fifth development process has two names.** *B - Development Processes* calls it "Establish Data Space Agreements and Policies"; the page navigation and the page itself call it "B.5 - Document Data Space Policies and Agreements".
- **B.5 has no breadcrumb trail and sits outside `B - Development Processes` in the source tree**, even though the *B - Development Processes* page counts it as the fifth of five and the pane navigation lists it in sequence after B.4. Its own page heading is a slug.
- **The pane root has two names.** "Introduction Co-Creation Method" in the breadcrumb trails, "Co-Creation Method" in the page navigation.
- **Dangling cross-reference in B.2.** Step 1 Question 3 refers to "Align Stakeholders on the Data Space Scope - Step 3 - Question 4: relevant identities", but B.1 Step 3 has only three questions and none concerns relevant identities.
- **Broken question numbering in B.5 Step 2.** The two questions are numbered `2` and `3`; there is no question `1`.
- **Malformed table in B.4 Step 4.** The header cell reads `4` instead of `#`, and the final row ("How will the agreements on provenance, traceability and observability be governed?") has an empty "Potential Outcomes" cell — the question is posed but not answered.
- **Flowcharts and figures are not available in text.** Every development process refers to a "Figure 1" flowchart of its steps; those figures are images in the source, so only the step sequence described in prose and the per-step tables are rendered here.
- **Normative force of the design-choice list in B.5 Step 1 Q2 is uneven.** Within one list the source uses "recommends" (Verifiable Credentials/DIDs, DCAT), "prescribes" (ODRL) and "must" (Trust Framework, Data Models, Data Exchange, Publication and Discovery) without explaining the distinction. The forces recorded above follow the source's wording verbatim.
- **Workshop content is out of scope of the rendered pages.** The eight workshops referenced by the development processes are published as a separate document, not as part of the blueprint pages.
