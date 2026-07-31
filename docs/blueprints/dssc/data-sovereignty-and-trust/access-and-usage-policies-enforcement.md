# Access & Usage Policies Enforcement

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Sovereignty and Trust › Access & Usage Policies Enforcement
> **Category** · Data Sovereignty and Trust

This building block addresses the negotiation and enforcement of access and usage policies for data sharing in Data Spaces. Machine-readable policies enable automated contract negotiation for standard terms and automated enforcement during data access; this allows data spaces to scale without requiring manual review for every transaction.

## Scope and objectives

The building block addresses the negotiation and enforcement of access and usage policies for data sharing in Data Spaces.

Participants can:

- Define and negotiate data access and usage policies in a transparent and interoperable way.
- Enforce policies during the actual sharing of data.

Machine-readable policies enable automated contract negotiation for standard terms and automated enforcement during data access. This allows data spaces to scale without requiring manual review for every transaction.

## Capabilities

To achieve these objectives, every data space requires the following capabilities:

- **Policy Creation and Validation**: Convert business rules into machine-readable policies and validate their syntax and semantics before deployment. This can be needed by dataspace governance authorities when defining common rules as part of the data space rulebook. In addition it is be needed by data space participants to define their own rules for their data products.

  > **Note:** "it is be needed" is the source's own wording, reproduced verbatim.

- **Enforcement of policies during the various stages of a data transaction**: During the publication of data products in a catalogue service, discovery, the contract negotiation and the actual sharing of the data, all policies need to be enforced. Every participant needs to have this capability.

These capabilities make it possible to automate policy enforcement and support trusted data transactions across the data space.

## Standards and protocols

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| ODRL (Open Digital Rights Language), W3C | The building block page links `https://www.w3.org/TR/odrl-model/` without naming a version; the ODRL explainer names **ODRL Information Model 2.2** (`https://www.w3.org/TR/odrl-model/`) | Basis for expressing access and usage policies. W3C standard for expressing permissions, prohibitions, and obligations on data products. | recommended |
| ODRL Vocabulary | `https://www.w3.org/TR/odrl-vocab/` | Listed under "Further Resources" of the ODRL explainer as an ODRL specification. | referenced |
| Dataspace Protocol | No version or profile stated | For the actual exchange of policies and the negotiation there-of; "which is using ODRL as a policy language". The source links it to the building block page *Building on top of foundational standards*. | recommended |
| IDS Information Model | Named as an ODRL profile; the explainer's Further Resources entry is the unresolved placeholder `[IDS profile for usage control]` (no URI in the source) | Cited as an existing ODRL profile that a data space may adopt; the "IDS Profile" example is said to define data usage control vocabulary, specify how to combine multiple policies, and provide a reference implementation. | referenced |
| W3C ODRL Best Practices | `https://w3c.github.io/odrl/bp/` | Listed under "Implementation Examples". | referenced |
| JSON-LD | No version stated | Named only inside the tool description "ODRL parser (JSON-LD to executable rules)". | referenced |
| GDPR | Instrument named, no article cited | Named as an example of a regulatory requirement from which a common access and usage policy might stem (consent for the sharing of personal data). | referenced |

## Co-creation questions

The source lists the following co-creation questions, which "apply when implementing this buildingblock in your Data Space". They are questions for implementers, not requirements, and therefore carry no requirement ID.

- **Which common access and usage policies need to be included in the data space rulebook?** Depending on the use cases supported in the data space, some common access and usage policies might exist for specific (types of) data products. As an example: some (domain specific) roles in the network might need to adopt a specific access and usage policy for the mandatory sharing or control of data. These might stem from regulatory requirements (e.g. consent for the sharing of personal data, based on the GDPR) or legal requirements stemming from the legal framework of the data space. In other scenarios they can also serve as optional templates or best practices for dataspace participants.

- **How can data space participants verify compliance with access and usage policies using the trust framework?** The trust framework identifies the available trust anchors and trust services. Trust services can be used for the (automated) verification of claims of compliance, which can be used to evaluate access and usage policies ('does the other participant meet the requirements').

## Specifications

Policies need to be expressed in machine-readable formats to ensure semantic clarity and interoperability. Each policy needs to include clear metadata describing its language, serialization format, profile, and version. This enables a consistent interpretation and evolution over time and between partners.

The DSSC recommends to use [ODRL](https://www.w3.org/TR/odrl-model/) (Open Digital Rights Language) as a basis for expressing access and usage policies. ODRL is the W3C standard for expressing permissions, prohibitions, and obligations on data products.

For the actual exchange of policies and the negation there-of, the DSSC recommends to use the Dataspace Protocol, which is using ODRL as a policy language.

> **Note:** "the negation there-of" is the source's own wording (apparently for "negotiation thereof"), reproduced verbatim.

## Implementation

To implement access and usage policies in a dataspace two key services are needed:

- **Participant agents**: which contain a control plane, where the policy negotiation and execution takes place.
- **Trust services**: which can be used to validate/verify claims, which can be used to automate policy evaluation and execution.

## Requirements

Requirement IDs are a local index for benchmarking. The source does not number its requirements.

Notes on the **Force** column for this building block:

- `must` is used where the source says *needs to* / *requires* / *must*.
- `should` is used where the source says *should*.
- `may` is used where the source says *may* / *can*.
- `recommended` is used where the source recommends, or issues a bare best-practice imperative ("Action: …", "Provide …", "Document …") inside an explainer or best-practice page.
- `informative` is used for descriptive statements that attach no normative force (architecture component descriptions, process narrative).

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-AUP-01` | A data space must be able to convert business rules into machine-readable policies. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-02` | A data space must be able to validate the syntax of policies before deployment. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-03` | A data space must be able to validate the semantics of policies before deployment. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-04` | All policies must be enforced during the publication of data products in a catalogue service. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-05` | All policies must be enforced during discovery. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-06` | All policies must be enforced during the contract negotiation. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-07` | All policies must be enforced during the actual sharing of the data. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-08` | Every participant must have the policy enforcement capability. | must | `access-usage-policies-enforcement.md` §2 Capabilities |
| `DSSC-AUP-09` | Policies must be expressed in machine-readable formats. | must | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-10` | Each policy must include metadata describing its language. | must | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-11` | Each policy must include metadata describing its serialization format. | must | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-12` | Each policy must include metadata describing its profile. | must | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-13` | Each policy must include metadata describing its version. | must | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-14` | ODRL is recommended as the basis for expressing access and usage policies. | recommended | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-15` | The Dataspace Protocol is recommended for the actual exchange of policies and the negotiation thereof. | recommended | `access-usage-policies-enforcement.md` §4 Specifications |
| `DSSC-AUP-16` | Participant agents containing a control plane, in which policy negotiation and execution takes place, are needed to implement access and usage policies. | must | `access-usage-policies-enforcement.md` §5 Implementation |
| `DSSC-AUP-17` | Trust services able to validate/verify claims, so that policy evaluation and execution can be automated, are needed to implement access and usage policies. | must | `access-usage-policies-enforcement.md` §5 Implementation |
| `DSSC-AUP-18` | Agreements between participants should be expressed in a standard, machine-readable format. | should | `best-practice-policy-administration-information-decision-e14456.md` (introduction) |
| `DSSC-AUP-19` | Policy decisions should generate verifiable records. | should | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Documentation |
| `DSSC-AUP-20` | Systems should track policy lifecycle states (negotiation, agreement finalization, execution, monitoring, termination) conceptually. | should | `best-practice-policy-administration-information-decision-e14456.md` § Policy Lifecycle Awareness |
| `DSSC-AUP-21` | Systems should track the well-defined states under which data transfers occur, conceptually. | should | `best-practice-policy-administration-information-decision-e14456.md` § Policy Lifecycle Awareness |
| `DSSC-AUP-22` | A Policy Enforcement Point (PEP) intercepts requests and enforces policy decisions. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-23` | A Policy Decision Point (PDP) evaluates requests against policy agreements and contextual information. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-24` | A Policy Administration Point (PAP) manages policy agreements and provides them to the PDP when required. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-25` | A Policy Information Point (PIP) supplies additional contextual information, such as consent or identity-related data. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-26` | A Context Handler coordinates contextual information from PIP and other sources to support PDP evaluations. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-27` | A Data Sink/Source handles actual data storage and retrieval based on approved requests. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Architecture |
| `DSSC-AUP-28` | Negotiation continues until all policies are mutually accepted or the negotiation is terminated. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Negotiation phase |
| `DSSC-AUP-29` | Once all policies are agreed upon, a contract agreement is formally generated. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Negotiation phase |
| `DSSC-AUP-30` | The contract agreement is machine-readable and serves as the official basis for subsequent data transactions. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Negotiation phase |
| `DSSC-AUP-31` | Automatically enforceable policies and legal-only policies should be clearly separated. | should | `best-practice-policy-administration-information-decision-e14456.md` § Negotiation phase |
| `DSSC-AUP-32` | Access provisions are evaluated primarily by the provider before any data is exchanged. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-33` | Consumers may also verify access terms upon receiving data. | may | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-34` | Usage provisions are evaluated by the consumer during data usage. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-35` | Depending on the contract, usage evaluations may occur continuously throughout the data lifecycle. | may | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-36` | Third-party consent status is checked to ensure revoked or modified consents are respected. | informative | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-37` | Consumers may provide proof of policy enforcement that providers verify (bilateral verification). | may | `best-practice-policy-administration-information-decision-e14456.md` § Enforcement Phase |
| `DSSC-AUP-38` | ODRL defines policy vocabulary, not how to interpret or enforce policies. | informative | `explainer-open-digital-rights-language-odrl.md` §1 |
| `DSSC-AUP-39` | The data space must decide on / define its policy interpretation rules. | must | `explainer-open-digital-rights-language-odrl.md` §1, §1.2 |
| `DSSC-AUP-40` | Two systems can read the same ODRL policy but enforce it differently. | informative | `explainer-open-digital-rights-language-odrl.md` §1.2 |
| `DSSC-AUP-41` | Interpretation decisions are documented in the data space rulebook. | recommended | `explainer-open-digital-rights-language-odrl.md` §1.2 |
| `DSSC-AUP-42` | An existing ODRL profile is adopted (e.g. IDS Information Model), or an own profile is created with clear interpretation guidelines. | recommended | `explainer-open-digital-rights-language-odrl.md` §1.2 |
| `DSSC-AUP-43` | "Pure" ODRL is not used; a profile is defined. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.1 |
| `DSSC-AUP-44` | The profile defines standard vocabulary for the domain (source: "Required elements"). | must | `explainer-open-digital-rights-language-odrl.md` §2.1 |
| `DSSC-AUP-45` | The profile defines conflict resolution rules (source: "Required elements"). | must | `explainer-open-digital-rights-language-odrl.md` §2.1 |
| `DSSC-AUP-46` | The profile defines validation rules distinguishing required from optional fields (source: "Required elements"). | must | `explainer-open-digital-rights-language-odrl.md` §2.1 |
| `DSSC-AUP-47` | The profile is documented in the data space rulebook. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.1 ("Action:") |
| `DSSC-AUP-48` | Validation tools are provided for the profile. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.1 ("Action:") |
| `DSSC-AUP-49` | Standard policy templates are provided for common scenarios. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.2 |
| `DSSC-AUP-50` | The data space must specify conflict resolution rules. | must | `explainer-open-digital-rights-language-odrl.md` §2.3 |
| `DSSC-AUP-51` | Rule 1 — Prohibition precedence: if one policy permits and another prohibits, prohibition wins. | must | `explainer-open-digital-rights-language-odrl.md` §2.3 |
| `DSSC-AUP-52` | Rule 2 — Specificity precedence: a more specific policy overrides a general policy. | must | `explainer-open-digital-rights-language-odrl.md` §2.3 |
| `DSSC-AUP-53` | Rule 3 — Data space rules precedence: mandatory data space policies override participant policies. | must | `explainer-open-digital-rights-language-odrl.md` §2.3 |
| `DSSC-AUP-54` | The conflict resolution rules are documented in the rulebook. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.3 ("Action:") |
| `DSSC-AUP-55` | The conflict resolution rules are implemented in the PDP. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.3 ("Action:") |
| `DSSC-AUP-56` | Level 1 (syntax validation): the ODRL structure is valid. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-57` | Level 1 (syntax validation): required fields are present. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-58` | Level 1 (syntax validation): data types are correct. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-59` | Level 2 (semantic validation): terms are defined in the data space's profile. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-60` | Level 2 (semantic validation): constraints use allowed values. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-61` | Level 2 (semantic validation): references point to valid credentials. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-62` | Level 3 (consistency validation): there are no internal contradictions. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-63` | Level 3 (consistency validation): the policy is compatible with mandatory data space policies. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-64` | Level 3 (consistency validation): there are no undefined dependencies. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-65` | Level 4 (compatibility validation, during negotiation): provider and consumer policies can be reconciled. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 |
| `DSSC-AUP-66` | A validation service that checks all four levels is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.4 ("Tool:") |
| `DSSC-AUP-67` | Complex policies are broken into reusable modules. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.5 ("Recommendation:") |
| `DSSC-AUP-68` | Obligations requiring organizational compliance are clearly marked as distinct from those under automated enforcement. | recommended | `explainer-open-digital-rights-language-odrl.md` §2.6 ("Action:") |
| `DSSC-AUP-69` | Policy creation: a created policy is validated against the data space profile. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-70` | Policy publication: the policy is attached to the data product in the catalog. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-71` | Policy publication: the policy is made searchable by policy attributes. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-72` | Policy negotiation: on a consumer access request, the system checks policy compatibility. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-73` | Policy negotiation: compatible policies are agreed automatically, otherwise the request is flagged for manual review. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-74` | Policy enforcement: ODRL is converted into executable rules in the PDP. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-75` | Policy enforcement: policies are enforced during data access. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-76` | Policy enforcement: enforcement decisions are logged. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-77` | Policy monitoring: obligation compliance is tracked. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-78` | Policy monitoring: audit reports are generated. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-79` | Policy monitoring: violations raise alerts. | informative | `explainer-open-digital-rights-language-odrl.md` §3.1 |
| `DSSC-AUP-80` | For policy authors: a policy editor with templates is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-81` | For policy authors: real-time validation is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-82` | For policy authors: a compatibility checker is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-83` | For policy enforcers: an ODRL parser (JSON-LD to executable rules) is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-84` | For policy enforcers: a PDP integration library is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-85` | For policy enforcers: an audit logging system is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-86` | For administrators: a policy registry/catalog is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-87` | For administrators: a conflict detection tool is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-88` | For administrators: a compliance dashboard is provided. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.2 |
| `DSSC-AUP-89` | Limitations — what cannot be enforced technically — are documented before deploying ODRL in the data space. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.4 |
| `DSSC-AUP-90` | Participants are trained on policy creation best practices. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.4 |
| `DSSC-AUP-91` | Monitoring for policy compliance is set up. | recommended | `explainer-open-digital-rights-language-odrl.md` §3.4 |

## Explainers and best practices

The source lists two further-reading items under this building block. Note that the names used in the building block's "Further reading" list differ from the sub-pages' own titles (see [Open questions](#open-questions)); the sections below use the sub-pages' own titles.

### Explainer: Open Digital Rights Language (ODRL)

#### 1. What is ODRL?

ODRL is the W3C standard for expressing machine-readable policies about data access and usage. It provides a standardized vocabulary for defining:

- **Permissions** — What actions are allowed
- **Prohibitions** — What actions are forbidden
- **Obligations** — What actions must be performed

> **Key Point:** ODRL defines policy vocabulary, not how to interpret or enforce policies. Your data space must decide on interpretation rules (see Section 4 below).

> **Note:** the "see Section 4 below" cross-reference does not resolve — Section 4 of the explainer is "Further Resources"; interpretation rules are treated in Sections 1.2 and 2.3.

##### 1.1 Why Use ODRL in Data Spaces?

- **Interoperability:** Participants can understand each other's policies using a common vocabulary.
- **Extensibility:** Create domain-specific extensions (profiles) for your sector's needs.
- **Machine-Readability:** Enables automated policy negotiation and enforcement.
- **Standardization:** W3C standard with broad tool support and active community.
- **Profile Extension:** Custom domain-specific profiles can extend ODRL to address unique needs.

##### 1.2 Understanding ODRL's Limitations

> **Important:** ODRL specifies WHAT policies mean, not HOW to evaluate them.

**What this means in practice:**

- Two systems can read the same ODRL policy but enforce it differently.
- Your data space must define interpretation rules (e.g., "prohibition always overrides permission").
- Document your interpretation decisions in your data space rulebook.

**Solution:** Adopt an existing ODRL profile (e.g., IDS Information Model) or create your own with clear interpretation guidelines.

#### 2. Best Practices for Data Spaces

##### 2.1 Adopt or Create an ODRL Profile

**Don't use "pure" ODRL** — Define your profile with:

```
Required elements:
- Standard vocabulary for your domain (e.g., "certified researcher" in health data)
- Conflict resolution rules (e.g., "stricter policy wins")
- Validation rules (required vs. optional fields)

Example: IDS Profile
- Defines data usage control vocabulary
- Specifies how to combine multiple policies
- Provides reference implementation
```

**Action:** Document your profile in the data space rulebook and provide validation tools.

##### 2.2 Use Policy Templates

**Provide standard templates** for common scenarios:

```
Template: Research Access
  Permission: Use data
  Assignee: Organizations with [researcher credential]
  Constraint: Purpose = research
  Prohibition: Commercial use
  Obligation: Attribute data source

Template: Commercial License
  Permission: Use data
  Assignee: Any organization
  Duty: Pay [fee]
  Constraint: Usage period = [dates]
```

**Benefit:** Reduces errors, increases consistency, speeds negotiation.

##### 2.3 Define Clear Conflict Resolution Rules

**Your data space must specify:**

```
Rule 1: Prohibition precedence
  If one policy permits and another prohibits → prohibition wins

Rule 2: Specificity precedence
  More specific policy overrides general policy
  Example: "No access from Germany" beats "Access from EU"

Rule 3: Data space rules precedence
  Mandatory data space policies override participant policies
```

**Action:** Document these rules in your rulebook and implement in your PDP.

##### 2.4 Validate Policies Before Deployment

**Implement validation at multiple levels:**

```
Level 1: Syntax validation
  Valid ODRL structure
  Required fields present
  Correct data types

Level 2: Semantic validation
  Terms defined in your profile
  Constraints use allowed values
  References to valid credentials

Level 3: Consistency validation
  No internal contradictions
  Compatible with mandatory data space policies
  No undefined dependencies

Level 4: Compatibility validation (during negotiation)
  Provider and consumer policies can be reconciled
```

**Tool:** Provide a validation service that checks all levels.

##### 2.5 Keep Policies Simple and Modular

**Good practice:**

```
Base policy: Authentication required
+ Purpose constraint: Research only
+ Time constraint: Valid until 2025-12-31
= Combined policy (easy to understand and modify)
```

**Bad practice:**

```
One large policy with 20+ nested conditions
→ Hard to validate, hard to modify, error-prone
```

**Recommendation:** Break complex policies into reusable modules.

##### 2.6 Separate Technical vs. Legal-Only Policies

**Not all policy rules can be technically enforced:**

```
Technically Enforceable:
  Access control (check credentials before access)
  Purpose restrictions (tag data usage in system)
  Geographic restrictions (check IP/location)

Legal-Only (organizational compliance):
  "Delete data after use"
  "Do not combine with other datasets"
  "Use only for specified project"
```

**Action:** Clearly mark which obligations require organizational compliance vs. automated enforcement.

#### 3. Implementation Guidance

##### 3.1 Policy Lifecycle in Your Data Space

```
1. Policy Creation
   → Provider creates policy using templates or custom rules
   → Validate against data space profile

2. Policy Publication
   → Attach to data product in catalog
   → Make searchable by policy attributes

3. Policy Negotiation
   → Consumer requests access
   → System checks policy compatibility
   → Automatically agree (if compatible) or flag for manual review

4. Policy Enforcement
   → Convert ODRL → executable rules in PDP
   → Enforce during data access
   → Log enforcement decisions

5. Policy Monitoring
   → Track obligation compliance
   → Generate audit reports
   → Alert on violations
```

##### 3.2 Essential Tools to Provide

**For Policy Authors:**

- Policy editor with templates
- Real-time validation
- Compatibility checker

**For Policy Enforcers:**

- ODRL parser (JSON-LD to executable rules)
- PDP integration library
- Audit logging system

**For Administrators:**

- Policy registry/catalog
- Conflict detection tool
- Compliance dashboard

##### 3.3 Common Pitfalls to Avoid

| Pitfall | Remedy given by the source |
|---|---|
| Over-complex policies | Use templates and modular design |
| Undefined terms | Maintain shared vocabulary in profile |
| No conflict resolution rules | Document precedence rules upfront |
| Assuming all policies are enforceable | Distinguish technical vs. legal-only obligations |
| No validation before deployment | Implement multi-level validation |

##### 3.4 Getting Started Checklist

**Before deploying ODRL in your data space:**

- Choose or create an ODRL profile for your domain
- Define conflict resolution rules in your rulebook
- Create policy templates for common scenarios
- Implement validation service (syntax, semantics, consistency)
- Provide policy authoring tools (editor, validator)
- Integrate with PDP for automated enforcement
- Document limitations (what can't be enforced technically)
- Train participants on policy creation best practices
- Set up monitoring for policy compliance

#### 4. Further Resources

**ODRL Specifications:**

- ODRL Information Model 2.2: <https://www.w3.org/TR/odrl-model/>
- ODRL Vocabulary: <https://www.w3.org/TR/odrl-vocab/>

**Implementation Examples:**

- W3C ODRL Best Practices: <https://w3c.github.io/odrl/bp/>
- IDS Information Model: [IDS profile for usage control]

> **Note:** the IDS Information Model entry appears in the source exactly as shown — a bracketed placeholder with no URI.

### Best practice: Policy Administration, Information, Decision and Enforcement

Agreements between participants should be expressed in a **standard, machine-readable format** to enable transparent, automated interpretation and shared understanding. This ensures that the **intended business terms are consistently represented across all parties**, supporting interoperability and trust.

#### Enforcement Documentation

Policy decisions should generate **verifiable records** that support transparency, accountability, and trust. These records help participants monitor compliance and demonstrate that policies are applied correctly, while allowing flexibility in how the information is captured or represented.

#### Policy Lifecycle Awareness

Policies have a **lifecycle**, from negotiation and agreement finalization to execution, monitoring, and termination. Similarly, data transfers occur under well-defined states that ensure compliance, accountability, and traceability. Systems should track these states conceptually to maintain **alignment between agreements, policy enforcement, and audit requirements**.

#### Architecture

Figure 1 illustrates the core architectural components for access and usage policy enforcement and their interactions. These components work together to ensure that requests for data are evaluated, authorized, and executed according to defined policies.

> **Note:** Figure 1 and Figure 2 are referenced by the source but are diagrams; only their textual description is reproduced here.

Key Components:

- **Data Plane** on the left (outside the main boundary) represents the requester's infrastructure, while the Data Plane inside the main system boundary represents the provider's infrastructure.
- **Policy Enforcement Point (PEP)**: Intercepts requests and enforces policy decisions.
- **Policy Decision Point (PDP)**: Evaluates requests against policy agreements and contextual information.
- **Policy Administration Point (PAP)**: Manages policy agreements and provides them to the PDP when required.
- **Policy Information Point (PIP)**: Supplies additional contextual information, such as consent or identity-related data.
- **Context Handler**: Coordinates contextual information from PIP and other sources to support PDP evaluations.
- **Data Sink/Source**: Handles actual data storage and retrieval based on approved requests.

These components support the complete policy enforcement process (Figure 2), following a data transaction from the initial request, through verification and policy evaluation, to eventual data access. The process is organized into two distinct phases negotiation and enforcement phase.

#### Negotiation phase

The negotiation phase begins when a **consumer** discovers a relevant data offering. Each offering contains **license terms**, which include policies defined by the provider as conditions for data sharing.

During negotiation, the consumer and provider interact to accept, reject, or propose modifications to these policies. This process continues until all policies are mutually accepted or the negotiation is terminated.

Once all policies are agreed upon, a **contract agreement** is formally generated. This contract is machine-readable and serves as the **official basis for subsequent data transactions**, ensuring both automated enforcement of applicable policies and a legal reference for non-automated policies.

It is important to note that some policies can be enforced automatically during data transactions, while others are legal-only and cannot be technically enforced. Both types are essential, but they should be clearly separated to maintain clarity in enforcement and compliance.

The **contract agreement** is central to the negotiation process and explicitly defines the rights, obligations, and enforcement conditions agreed upon by both parties. This makes it the authoritative document that governs the enforcement phase.

#### Enforcement Phase

The enforcement phase begins once a Contract Agreement has been established during negotiation and continues throughout the data transaction lifecycle. Its purpose is to monitor and enforce ongoing obligations throughout the data transaction lifecycle, ensuring that all data transactions adhere to the terms agreed upon in the contract. Figure 2 illustrates the enforcement workflow between consumer and provider.

**Key Activities:**

- **Access provisions**: Evaluated primarily by the provider before any data is exchanged. Consumers may also verify access terms upon receiving data.
- **Usage provisions**: Evaluated by the consumer during data usage. Depending on the contract, evaluations may occur continuously throughout the data lifecycle.
- **Consent requirements**: Third-party consent status is checked to ensure revoked or modified consents are respected. Both provider and consumer monitor compliance as needed.

During enforcement, the **Policy Enforcement Point (PEP)** intercepts requests. The **Policy Decision Point (PDP)** evaluates them against the contract agreement retrieved from the **Policy Administration Point (PAP)**. The **Policy Information Point (PIP)** supplies any additional contextual information needed for decision-making.

The workflow also includes **bilateral verification**, where consumers can provide proof of policy enforcement that providers verify to ensure compliance.

All enforcement activities rely directly on the **Contract Agreement**. This ensures that automated policy enforcement aligns with negotiated terms while maintaining clarity between technically enforceable policies and legal-only policies that cannot be automatically enforced.

## Glossary

The source gives the following glossary under the heading "Terms specific to Access and Usage Policy Negotiation and Enforcement". Definitions are not requirements and carry no requirement ID. The table is reproduced as given, including the three terms that appear twice with different definitions (see [Open questions](#open-questions)).

| Terms | Definition |
|---|---|
| Policy | A machine-readable rule that expresses permissions, prohibitions, or obligations regarding data access and usage. Policies are encoded in ODRL and implement the terms and conditions defined in data product contracts. See 3.4.2.1 Data product contract in Contractual Framework building block. |
| Policy Negotiation | The process through which a data provider and consumer agree on machine-readable policies for data sharing. The provider offers policies, the consumer may propose alternatives, resulting in a mutually acceptable data product contract. |
| Policy Validation | The process of verifying that policies are syntactically correct (valid ODRL), semantically meaningful, internally consistent, and compliant with data space mandatory rules. |
| Machine-Readable Policy | A policy expressed in a standard format (ODRL) that computers can automatically process, evaluate, and enforce. |
| Access Control | Technical mechanisms that enforce who can access data resources based on permissions in policies. Evaluated before data transfer. |
| Usage Control | Technical mechanisms that enforce how data can be used after access, based on obligations and prohibitions in policies. |
| Policy Validation | The process of verifying that policies are correctly structured, consistent, and free from conflicts. |
| Access Control | Systems and policies that regulate who can access specific data resources and under what conditions. |
| Usage Control | Mechanisms that specify and enforce how data can be used after access has been granted. |
| Trust Service | A service that verifies claims used in policy evaluation (e.g., participant credentials, certifications). Examples include identity providers and credential verification services. |

## Tools implementing this building block

The source lists the following tools under "Tools implementing this building block". These are illustrations — naming a tool is not a requirement. Descriptions are the source's own.

- **Sitra Rulebook model for a fair data economy** — *Business and Organisational Services*. The Sitra Rulebook model provides a manual for establishing a data space and to set out general terms and conditions for data sharing agreements. Rulebook Part 2 includes editable frameworks and templates including: Data Space Canvas; Checklists: Business, Governance, Legal, and Technical; Ethical maturity model; Rolebook; Servicebook; General Terms and Conditions (to be used as-is); template for the Constitutive Agreement; template for the Accession Agreement; template for the Governance Model; and template for the Dataset Terms of Use.
- **PETSpaces (Privacy-Enhancing Data App for Secure Computations in Data Spaces)** — *Value-Creation Services*. This data app focuses on enabling privacy-preserving computations in data spaces. It leverages advanced Privacy-Enhancing Technologies (PETs), currently featuring Fully Homomorphic Encryption (FHE) and planned support for approaches like anonymization techniques and Zero-Knowledge Proofs (ZKPs). It is offered in the data space and delivered as a ready-to-deploy app to be instantiated in EDC connectors. It allows participants to process and compute encrypted data, preserving data privacy and enhancing data owners' sovereignty over their data.
- **NoodleBar & Keyper - Dataspace Infrastructure by Poort8 B.V.** — *Trust Service*. NoodleBar & Keyper are a complete, production-ready and modular dataspace trust service stack aligned with the DSSC Blueprint. NoodleBar provides three integrated layers: Identity (authentication for every machine and human in the dataspace), Participant Registry (participant lifecycle management, verification, onboarding, and catalogue), and Access & Authorization (real-time policy enforcement and audit logging). Keyper adds Personal Consent & Delegation Management, enabling data owners to actively control who accesses their data. The stack is compliance by design, supporting European data rules and requirements. Framework-agnostic by architecture, NoodleBar dataspace solution has been deployed in production across energy, logistics, and construction sectors.
- **Ocean Enterprise Provider** — *Participant Agent Services*. The Ocean Enterprise Provider, alternatively named the "Connector" or "Access Controller" is a REST API specifically designed for the provisioning of data services. The access controller acts as an intermediary between the data source/data product provider and the user/data product consumer, thus preventing the need for the data product consumer to have direct access to the data product. Before granting access to a resource it performs a series of checks to verify the users permission to access a service, such as a data product contract opt-in, the identity of the data product consumer, successful payment, and access policies. The Ocean Enterprise Provider supports integrity checks, the transfer of data, the orchestration of Compute-to-Data, and the forwarding to service offerings to support "Everything as a Service".
- **Nautilus Participant Agent** — *Participant Agent Services*. As a Data Space Participant Agent Nautilus for Ocean Enterprise provides Data Space Participants with the ability to publish, manage, discover, and consume data products and service offerings. It is a data economy toolkit and abstraction layer enabling programmatic interactions with the Ocean Enterprise Data Space Infrastructure and Components required by Participants.
- **Data Space Innovation Lab Connector** — *Participant Agent Services*. IDSA complient certified IDS connector.
- **TNO Security Gateway (TSG)** — *Participant Agent Services*. The TSG components allows you to participate in an IDS dataspace to exchange information with other organizations with data sovereignty in mind. You will be able to participate with the provided components as-is, but you're allowed to modify the components to create your own dataspace with specific use cases in mind.
- **FIWARE Data Space Framework (FDF)** — *Participant Agent Services*. The FIWARE Data Space Framework FDF is an integrated suite of components implementing DSBA Technical Convergence recommendations, every organization participating in a data space should deploy to "connect" to a data space.
- **Tekniker Dataspace Connector** — *Participant Agent Services*. Modular solution that, deployed in any organization, allows to establish a single point of entry for multiple data sources either proprietary in the role of the Data Provider or available throughout the Data Space in the role of Data Consumer ensuring the interoperability of shared data, trust between the parties involved in data exchange and data sovereignty.
- **sovity EDC Community Edition (EDC CE)** — *Participant Agent Services*. The sovity EDC Community Edition extends the Eclipse Dataspace Connector (EDC) with additional open-source enhancements, providing a ready-to-use solution for secure data exchange while ensuring data sovereignty.
- **Simpl-Open – Participant Agent** — *Participant Agent Services*. Simpl is the open-source smart middleware that enables cloud-to-edge federations and all major data initiatives funded by the European Commission. Simpl-Open is a suite of integrated and modular components. This includes components for Participant Agent service. See the "Purpose" section for a description of how Simpl-Open covers the service.
- **Ocean Enterprise Catalogue and Aquarius Catalogue Cache** — *Catalogue*. The Ocean Enterprise Catalogue allows the distributed, tamper-proof, self-sovereign storage of Data, Services, and Offerings Descriptions. Metadata records are stored as signed Verifiable Credentials utilizing Ocean Enterprise smart contracts. The metadata is openly extensible to support domain-specific descriptions and standards, such as DCAT, Gaia-X, and others. As API and for performant queries against the distributed catalogue of any Ocean Dataspace the Aquarius Catalogue Cache Component, based on Elasticsearch, is utilized. Aquarius continuously monitors metadata being created or updated and caches the catalogue state for local processing supporting participant agents, markets and applications using the Data Space Infrastructure.
- **sovity Data Space Portal (DSPortal)** — *Catalogue*. The Data Space Portal is a comprehensive platform that enables seamless interactions within data spaces, providing tools for data discovery and governance, while ensuring interoperability and adherence to data sovereignty principles for the data space members. The Crawler module of the Data Space Portal is designed to automatically discover, index, and update data resources across members Connectors. This component enhances the usability of data spaces by providing seamless and real-time insights into available data offers, supporting interoperability and data-sharing standards.
- **Simpl-Open - Catalogue** — *Catalogue*. Simpl is the open-source smart middleware that enables cloud-to-edge federations and all major data initiatives funded by the European Commission. Simpl-Open is a suite of integrated and modular components. This includes components for Catalogue service. See the "Purpose" section for a description of how Simpl-Open covers the service.
- **Data Space Builder** — *Value-Creation Services*. The Data Space Builder is a suite composed by the different data spaces components and technical building blocks such as catalogs, vocabulary services, trust framework & usage, policies and identity management, and data exchange including connectors and agents, also focused on semantic data management, data models management and NLP (Natural Language Process) intelligence.

## Open questions

> **Ambiguous:** The building block's "Further reading" list names the two sub-pages differently from their own titles. It lists *"Explainer: Open Digital Rights Language for data spaces"* (sub-page title: *"Explainer: Open Digital Rights Language (ODRL)"*) and *"Best practice: Implementing Policy Administration, Information, Decision and Execution"* (sub-page title: *"Best practice: Policy Administration, Information, Decision and Enforcement"* — **Execution** vs **Enforcement**). It is not stated which name is authoritative.

> **Ambiguous:** The building block page is titled *"Access & Usage Policies Enforcement"*, but its glossary section is headed *"Terms specific to Access and Usage Policy Negotiation and Enforcement"*. Two different names for the same building block appear on the same page.

> **Contradiction:** The glossary is internally duplicated. **Policy Validation**, **Access Control** and **Usage Control** each appear twice with different definitions. For *Policy Validation* the two definitions differ in substance: the first requires compliance with data space mandatory rules, the second requires freedom from conflicts. Which definition governs is not stated.

> **Contradiction:** The glossary states that "Policies are encoded in ODRL" (unconditional), while §4 Specifications only *recommends* ODRL ("The DSSC recommends to use ODRL … as a basis"). The normative force of ODRL is therefore stated two different ways on the same page.

> **Ambiguous (version):** §4 Specifications links ODRL as `https://www.w3.org/TR/odrl-model/` without naming a version, whereas the ODRL explainer's Further Resources names *ODRL Information Model 2.2* at the same URI. No statement fixes which version a data space must conform to.

> **Gap:** The Dataspace Protocol is recommended for the exchange and negotiation of policies, but no version, release or profile of it is given on this page; the page links onward to the *Building on top of foundational standards* page.

> **Ambiguous:** The ODRL explainer §1.2 presents prohibition precedence as an *example* of an interpretation rule ("e.g., 'prohibition always overrides permission'"), while §2.3 lists the same rule as "Rule 1" under the heading "**Your data space must specify:**". It is unclear whether the three named rules (prohibition precedence, specificity precedence, data space rules precedence) are mandated content or illustrations of the kind of rules a data space must specify. `DSSC-AUP-51`–`DSSC-AUP-53` follow the §2.3 framing.

> **Ambiguous:** The ODRL explainer §2.1 labels the profile's contents "Required elements", but the section itself is a best practice ("Adopt or Create an ODRL Profile"). Whether "required" carries the same force as the explicit "must" statements elsewhere in the explainer is not stated.

> **Ambiguous:** §2.4 is titled "Validate Policies Before Deployment", yet its Level 4 (compatibility validation) is explicitly scoped "during negotiation" — i.e. after deployment. The four levels therefore do not all belong to the stated pre-deployment scope.

> **Gap:** The ODRL explainer §1 refers the reader to "Section 4 below" for interpretation rules, but Section 4 of that page is "Further Resources". Interpretation rules are actually covered in §1.2 and §2.3.

> **Gap:** The ODRL explainer's Further Resources entry for the IDS Information Model is the unresolved placeholder `[IDS profile for usage control]` — no URI or version is given, although the IDS Information Model is the only concrete ODRL profile the source names.

> **Gap:** The best practice page describes Figures 1 (architecture) and 2 (enforcement process) but the figures themselves are diagrams; the component interactions and the message flow between consumer and provider are available only as prose. Detail present only in the diagrams cannot be rendered here.

> **Gap (normative force):** The best practice attaches no normative verb to the architectural components. It says Figure 1 "illustrates the core architectural components" and describes what each does, but never states that a participant must or should deploy a PEP, PDP, PAP, PIP, Context Handler or Data Sink/Source. `DSSC-AUP-22`–`DSSC-AUP-27` are therefore recorded as `informative`.

> **Gap:** The glossary's "Policy" definition cross-references "3.4.2.1 Data product contract in Contractual Framework building block". That numbering is not resolvable from this building block's pages, and DSSC does not number its building blocks.

> **Note (source text quality):** §2 Capabilities contains the ungrammatical "In addition it is be needed by data space participants", and §4 Specifications contains "the negation there-of" where "negotiation thereof" appears to be intended. Both are reproduced verbatim above rather than corrected.
