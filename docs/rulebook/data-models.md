# Data models

Which semantic models this data space uses, how vocabularies are published, and how both are
maintained.

Covers `DSSC-DMO-01`–`39` and the CEEDS specialisations `CEEDS-STD-11`, `-12`, `-23`,
`CEEDS-INT-27`, `-34`, `-36`.

**This is the weakest building block in the platform, and the one where CEEDS asks the
most.** The page states what is decided, and is explicit about what is not.

## 1. What is decided

`DSSC-DMO-01` requires data providers to describe their data structures, formats,
vocabularies, classification schemes, taxonomies and code lists.

**Decision: structural description is mandatory and enforced; semantic description is not
yet required.**

| Layer | Model | Status |
|---|---|---|
| Catalogue metadata | DCAT-AP + Dublin Core | **Enforced** — every offering, see [Catalogue and metadata](catalogue-and-metadata.md) §3 |
| Policy | ODRL 2.2 + this data space's profile | **Enforced** |
| Purpose taxonomy | SKOS, aligned to W3C DPV 2.3 | **Enforced** |
| Provenance | W3C PROV-O | **Enforced** |
| Legal bases | DPV 2.3 IRIs | **Enforced** |
| Refinement stage | a four-value medallion vocabulary (`bronze`, `silver`, `gold`) | **Enforced** |
| **Payload semantics** — what a column *means* | **none** | **Not decided.** See §3 |

| # | Rule | Status |
|---|---|---|
| M-1 | Every offering declares its data format and content type | **Enforced** |
| M-2 | Every offering declares its refinement stage | **Enforced** |
| M-3 | Every offering declares the vocabulary its *policy* is written in (`odrl:profile`) | **Enforced** |
| M-4 | Every offering declares the semantic model its *payload* conforms to | **Not enforced.** `dct:conformsTo` exists in the emission vocabulary but no rule requires or populates it |

## 2. Agreements on model use

`DSSC-DMO-35` requires agreements on the use of existing models to be documented in the
governance framework; `DSSC-DMO-27` requires participants to semantically define their
offerings using a standardised model agreed within the data space.

**Decision, and it is a deliberate one: this platform is domain-agnostic and mandates no
payload data model. A deployment must choose one and record it.**

The reasoning is in `AGENTS.md`: the approach should generalise across use cases, and
domain specialisation belongs in modules and extensions rather than in the platform. The
cost of that choice is that `DSSC-DMO-27` and every CEEDS semantic row are unmet **by the
platform** and can only be met **by a deployment**.

A deployment adopting this platform for an energy data space must, before it is
CEEDS-aligned:

1. Choose its payload models. CEEDS names CIM / IEC 61970 for grid data, IEC 62325 ESMP for
   market data, COSEM for metering, SAREF and SAREF4ENER for behind-the-meter equipment —
   all in a single sentence introduced by "such as", with no version, edition or profile,
   so the choice is genuinely the deployment's.
2. Record that choice here, in its own copy of this page.
3. Declare it per offering, so a consumer can discover it rather than being told out of
   band.

| # | Rule | Status |
|---|---|---|
| M-5 | A deployment records its payload models in its rulebook | **Declared** — this page is the slot |
| M-6 | The platform ships no payload model and imposes none | **Enforced** by absence |
| M-7 | An offering's declared model must be resolvable — a bare name is not a model reference | **Declared**, unimplementable until M-4 exists |

## 3. The open gap, and where it would attach

**Nothing in `libs/governance`, the ODRL profile, the DCAT emission or `governance.yaml`
references CIM, IEC 61970, IEC 62325, IEC 61850, COSEM, SAREF or SAREF4ENER.** Datasets are
described structurally — title, format, medallion stage, access level, purposes — and never
semantically.

The gap is not merely that the binding is unimplemented. **There is no extension point where
it would attach.** The obvious seam is the ODRL profile mechanism
(`libs/governance/src/ds/governance/profiles/*.yaml`, selected by
`CONNECTOR_ODRL_PROFILE_PATH`), which already carries a namespace, a prefix, custom
operands and a SKOS taxonomy — but today it carries *purposes* only.

**A concrete first step, recommended before any larger commitment:** bind one dataset to
SAREF4ENER, emit the reference into DCAT via `dct:conformsTo`, and declare it in
`governance.yaml`. That closes `CEEDS-INT-27` for one dataset and — more usefully —
establishes whether the profile mechanism can carry vocabularies at all. If it cannot, that
is an architecture finding worth having before the domain layer is scheduled.

## 4. The vocabulary surface

`DSSC-DMO-19` requires a tool for publishing, editing, browsing and maintaining
vocabularies and related documentation. CEEDS assigns a **Vocabulary Hub** component
(`CEEDS-STD-11`, `-12`).

**What exists:**

| Surface | What it serves | Access |
|---|---|---|
| `GET /ns/policy` | the ODRL profile as SKOS concepts — purposes, labels, definitions, `broader`, DPV alignment | public, unauthenticated |
| `GET /ns/sharing-offers` | the sharing offers as codes plus an English fallback | public, unauthenticated |
| `schemas/` | JSON Schema for every YAML shape that crosses a repository boundary, generated from the Pydantic models | in-repo |
| [`docs/taxonomies/dpv-2.3.md`](../taxonomies/dpv-2.3.md) | the DPV alignment of every purpose, with the reasoning per choice | published |

Both `/ns/*` surfaces are deliberately public: an onboarding wizard has to render purposes
and offers before anyone has an identity, and the offer projection omits dataset keys so
publication discloses nothing.

**What does not exist:** editing, browsing and maintenance. Publication is a static
projection of files in this repository. Changing a vocabulary is a commit, a rebuild and a
sync — not an operation an authorised participant can perform.

| # | Rule | Status |
|---|---|---|
| M-8 | Vocabularies are published in a machine-readable form, resolvable and unauthenticated | **Enforced** |
| M-9 | `schemas/` publishes every shape that crosses a repository boundary, generated from the models and never hand-edited, with a no-diff test | **Enforced** |
| M-10 | `schemas/purpose-vocabulary.json` is regenerated whenever the ODRL profile changes — it carries the slug `enum` the *active profile* accepts, which no static schema can | **Enforced, untested** at the drift level; the regeneration is a task, not a hook |
| M-11 | A vocabulary hub supporting editing and browsing exists (`DMO-19`) | **Not enforced** — publication only. **Open gap** |

## 5. The management process

`DSSC-DMO-16` requires a data-model management process; `-17` requires key stakeholders,
including standards bodies, to collaborate in it; `-37`, `-38`, `-39` require a data space
creating its own model to set up guidelines and a conflict-resolution process.

**Decision: the platform's own vocabularies follow the process below. Payload models are
the deployment's, and their process is the deployment's.**

For the vocabularies this platform owns — the purpose taxonomy, the sharing-offer shape, the
medallion values, the PROV-O domain profile:

1. **Change is a code change.** The vocabulary lives in a file in this repository and moves
   through review like any other change.
2. **A purpose addition requires three things in one commit:** the profile entry, the DPV
   alignment written up in `docs/taxonomies/dpv-2.3.md`, and a regenerated
   `schemas/purpose-vocabulary.json`. The validation only asserts that the IRI is absolute
   and the relation is a SKOS match property, so **a wrong-but-well-formed IRI passes every
   test in this repository** — the write-up is the actual review gate.
3. **Widening is the failure mode to guard against.** Re-parenting a concept, or changing a
   `broader` link, can silently make an existing consent cover a use the subject was never
   shown. Any change to the hierarchy must state, in the commit, which existing consents it
   would widen.
4. **Conflict resolution** (`DMO-39`): where two vocabularies disagree, the local
   `broader` hierarchy is authoritative for enforcement and the external alignment
   (DPV, and any future domain ontology) is documentation only. This is the same rule as
   [Policies](policies.md) A-1, stated once more because it is the rule that keeps the two
   layers from bleeding into each other.
5. **Standards-body collaboration** (`DMO-17`): none today. The DPV alignment tracks an
   external vocabulary and is revised when it moves — the 2.2 → 2.3 re-parenting prompted
   two corrections — but no upstream contribution is made.

| # | Rule | Status |
|---|---|---|
| M-12 | A vocabulary change states the consents it would widen, or states that it widens none | **Declared** |
| M-13 | The local hierarchy is authoritative for enforcement; external alignments are documentation | **Enforced** |
| M-14 | Deployment-owned payload models have their own documented management process | **Declared** — deployment's responsibility |

## Blueprint rows

**Closed by this page:** `DSSC-DMO-01`, `-16`, `-35`, `-37`, `-38`, `-39`.

**Open:** `DSSC-DMO-19` (vocabulary hub — publication only, §4). `DSSC-DMO-17`
(standards-body collaboration — none). `DSSC-DMO-27` (semantic definition of offerings —
deferred to the deployment, §2, and unimplementable until M-4 exists). `DSSC-DMO-08`
(standardised discovery of data models across data spaces) — not applicable while
federation is out of scope.

**CEEDS:** `CEEDS-STD-11`, `-12`, `-23`, `CEEDS-INT-27`, `-34`, `-36` are all **unmet**.
They are the single largest CEEDS gap and §3 states the first step.
