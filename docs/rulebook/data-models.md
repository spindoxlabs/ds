# Data models

Which semantic models this data space uses, how vocabularies are published, and how both are
maintained.

Covers `DSSC-DMO-01`–`39` and the CEEDS specialisations `CEEDS-STD-11`, `-12`, `-23`,
`CEEDS-INT-27`, `-34`, `-36`.

**This is the building block where CEEDS asks the most**, and it was the weakest until the
semantic layer got an extension point (§3). What remains open is now a *deployment's* decision —
which payload models to adopt — rather than a missing mechanism. The page states what is
decided, and is explicit about what is not.

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
| **Payload semantics** — what a column *means* | **the deployment's choice** | **Mechanism enforced, model not mandated.** A dataset declares one with `dcat.conforms_to`; the platform still ships none. See §3 |

| # | Rule | Status |
|---|---|---|
| M-1 | Every offering declares its data format and content type | **Enforced** |
| M-2 | Every offering declares its refinement stage | **Enforced** |
| M-3 | Every offering declares the vocabulary its *policy* is written in (`odrl:profile`) | **Enforced** |
| M-4 | Every offering declares the semantic model its *payload* conforms to | **Partly enforced.** The mechanism exists end to end — `dcat.conforms_to` is read from the canonical governance block, emitted as `dct:conformsTo` on the EDC asset (so it reaches the DSP catalogue) and on the DCAT evidence dataset, and checked at validation. What is *not* enforced is the word **every**: declaring nothing is legal, because `M-6` leaves the payload model to the deployment and requiring one here would take that decision back. A deployment that has chosen its models makes this mandatory in its own copy of this page |

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
| M-7 | An offering's declared model must be resolvable — a bare name is not a model reference | **Enforced** — the `semantic-model` check refuses a `dcat.conforms_to` that is not an absolute http(s) URI. `saref4ener` names nothing a consumer can dereference, and publishing it into `dct:conformsTo` would put a string that merely looks like a standard reference into the catalogue. An absolute IRI this participant holds no local copy of is a **warning**, not an error: an external standard is a legitimate reference whether or not it is mirrored here |

## 3. The extension point

*(This section used to read "The open gap, and where it would attach", and said there was no
extension point. There is one now, and it is not the one that section predicted.)*

**A dataset declares its payload semantic model as `dcat.conforms_to`** — a URI, in the
canonical `dcat:` block of `governance.yaml`. The seam was not the ODRL profile mechanism, as
§3 previously guessed: it was a field **`celine-utils` had already defined and ds was not
reading**. The whole `dcat:` block — publisher, themes, languages, spatial and temporal
coverage, `conforms_to` — reached the resolver and stopped there, so a producer authoring
against the published schema got a valid file and no effect.

The chain, end to end:

| Step | Where |
|---|---|
| A dataset declares a model | `governance.yaml` → `dcat.conforms_to` |
| ds reads it | `DcatSpec` in `libs/governance/models.py` |
| It is checked | the `semantic-model` validation check — `M-7` above |
| It reaches the DSP catalogue | `dct:conformsTo` in the EDC asset properties |
| It reaches the audit evidence | `dct:conformsTo` on the DCAT dataset node |
| A local copy is published | the vocabulary registry → `GET /ns/{slug}`, §4 |

**Two `dct:conformsTo` claims exist and they are different questions.** The one on a
*distribution* names the **protocol** (DSP — how you fetch it). The one on a *dataset* names
the **semantic model** (what the columns mean). They are on separate nodes deliberately, and a
test pins that they stay there.

**ds does not map, transform or validate payloads.** A dataset declaring SAREF4ENER is a
statement by its producer; making the served rows conform to it is the data plane's job. The
data plane now offers it: the celine `dataset-api` exposes
`POST /catalogue/{id}/conformance`, which maps a bounded sample of a dataset's rows through
its declared mapping and validates the resulting graph against the SHACL shapes of the
ontology version that mapping pins (`M-15`). This is a boundary, not a gap: the function
exists, it is owned, and it is owned by the party that holds the rows.

**Still to do for a CEEDS-aligned deployment:** choose the models (§2), register them, and bind
at least one dataset. The platform ships an empty registry and mandates nothing (`M-6`).

## 4. The vocabulary surface

`DSSC-DMO-19` requires a tool for publishing, editing, browsing and maintaining
vocabularies and related documentation. CEEDS assigns a **Vocabulary Hub** component
(`CEEDS-STD-11`, `-12`).

**What exists:**

| Surface | What it serves | Access |
|---|---|---|
| `GET /ns` | the index — every vocabulary this participant publishes, and which have a local copy | public, unauthenticated |
| `GET /ns/policy` | the ODRL profile as SKOS concepts — purposes, labels, definitions, `broader`, DPV alignment | public, unauthenticated |
| `GET /ns/sharing-offers` | the sharing offers as codes plus an English fallback | public, unauthenticated |
| `GET /ns/vocabularies` | the semantic vocabulary registry — slug, title, version, canonical IRI, cached or not | public, unauthenticated |
| `GET /ns/{slug}` | a **semantic** vocabulary's cached JSON-LD definition — SAREF, CIM, COSEM | public, unauthenticated |
| `schemas/` | JSON Schema for every YAML shape that crosses a repository boundary, generated from the Pydantic models | in-repo |
| [`docs/taxonomies/dpv-2.3.md`](../taxonomies/dpv-2.3.md) | the DPV alignment of every purpose, with the reasoning per choice | published |

**Two layers are served here and the distinction matters.** `/ns/policy` and
`/ns/sharing-offers` publish the *policy* vocabulary — the purposes, operands and offer codes
this dataspace enforces against. `/ns/{slug}` publishes *semantic* vocabularies, which describe
what a dataset's columns mean and which this dataspace does not own. A dataset points at one
through `dcat.conforms_to` (§3).

Every `/ns/*` surface is deliberately public: an onboarding wizard has to render purposes and
offers before anyone has an identity, the offer projection omits dataset keys so publication
discloses nothing, and a semantic vocabulary is a public standard to begin with.

**Serving is from a local cache and never a live fetch.** A public unauthenticated route that
retrieved an operator-configured URL on demand would proxy for any caller and would fail
whenever the upstream did. The cache is filled by `task vocab:fetch` or at connector startup —
and **a registered vocabulary with no local copy is a startup failure**, because booting while
`/ns/{slug}` 404s publishes a reference the catalogue names and this participant cannot serve.

**What still does not exist:** editing through the surface. Changing a vocabulary remains a
commit and a sync — which is not a shortfall but §5.1 applied consistently: the registry is a
file in this repository like every other vocabulary here, so `M-12` (a change states the
consents it would widen) keeps working unchanged. Also absent: **documenting non-standardised
data at ingestion**, and **version history** — the registry carries one `version` per entry,
not a record of how a vocabulary changed.

*(This paragraph used to list **validating data against a vocabulary** here too, as a third
absent "Vocabulary Hub function". Both halves of that were wrong. It is not a hub function —
`DSSC-DMO-19` asks for a tool for **publishing, editing, browsing and maintaining**
vocabularies, and validation appears in DSSC only as an example Value-Creation Service, the
SEMIC SHACL Validator. And it is no longer absent: it belongs to the data plane and the data
plane implements it, `M-15`. Measuring this platform against a requirement no blueprint makes
is the failure mode a citable requirements source exists to prevent, so it is corrected here
rather than quietly dropped.)*

| # | Rule | Status |
|---|---|---|
| M-8 | Vocabularies are published in a machine-readable form, resolvable and unauthenticated | **Enforced** |
| M-9 | `schemas/` publishes every shape that crosses a repository boundary, generated from the models and never hand-edited, with a no-diff test | **Enforced** |
| M-10 | `schemas/purpose-vocabulary.json` is regenerated whenever the ODRL profile changes — it carries the slug `enum` the *active profile* accepts, which no static schema can | **Enforced, untested** at the drift level; the regeneration is a task, not a hook |
| M-11 | A vocabulary hub supporting editing and browsing exists (`DMO-19`) | **Partly enforced.** Browsing exists: `GET /ns` indexes every published vocabulary, `/ns/vocabularies` lists the semantic registry, `/ns/{slug}` serves a cached definition as JSON-LD. Editing is a code change, deliberately — see §5.1, and the note above on why that is consistency rather than a shortfall. The two functions listed above as absent are the remainder of `DMO-19` |
| M-15 | Checking that served rows satisfy the model a dataset declares is the **data plane's** function, offered on demand rather than run on every exchange | **Declared** — and implemented outside this repository. The celine `dataset-api` exposes `POST /catalogue/{id}/conformance`; ds neither implements nor calls it. Three properties make it the right shape, and each is a decision rather than a detail: it is **on demand**, so nothing on the exchange path pays for it and no query result depends on it; it is **authorised exactly as `/query`** — same parser, same governance checks, same `/internal/dataplane/authorize` call, same row filters — because it reads real rows and quotes their values back, so a laxer gate would be a row-level leak wearing a metadata endpoint's clothes; and it validates against the ontology version the **mapping pins**, so an ontology release cannot decide overnight that a dataset stopped conforming. What a green result asserts is **structural only**: that the graph the mapping produces satisfies the shapes. It does not say the columns mean what the mapping claims — a spec naming the wrong observed property yields a conformant graph of wrong statements — so this closes the checkable half of `dct:conformsTo` and the semantic half stays the producer's assertion (`M-4`) |

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

**Partly closed:** `DSSC-DMO-19` (vocabulary hub — publishing, browsing and maintaining, §4;
editing stays a code change, and two hub functions are absent). `DSSC-DMO-23` (an API through
which data models can be retrieved — `GET /ns/{slug}`).

**Open:** `DSSC-DMO-17` (standards-body collaboration — none). `DSSC-DMO-27` (semantic
definition of offerings — the mechanism exists, §3, but which model to use stays the
deployment's decision per §2, so the platform cannot close this). `DSSC-DMO-08` (standardised
discovery of data models across data spaces) — not applicable while federation is out of scope.

**CEEDS:** `CEEDS-STD-11`, `-12`, `CEEDS-INT-27`, `-34` are **closable by a deployment** —
registering SAREF/SAREF4ENER or CIM and binding a dataset is now configuration, not
development. `CEEDS-STD-23` / `INT-36` (*"approaches based on data ontology are a requirement
in order to avoid silos"*, **must**) are substantially addressed: a dataset can name its
ontology, the reference travels in the catalogue, the definition is served, and — since
`M-15` — the claim can be checked against the rows rather than only asserted. That last step
is what moves these from *"a producer says so"* to *"a consumer can find out"*, which is the
difference an anti-silo requirement is actually about.

`CEEDS-STD-22` (CGMES conformity assessment, **informative**) is the nearest blueprint anchor
for `M-15`, and it is worth being precise that it is only an anchor: **no blueprint requirement
mandates validating data against a vocabulary.** `DMO-19` asks for publishing, editing,
browsing and maintaining; `DMO-32` says data schemas *should* be used during exchange; DSSC
lists the SEMIC SHACL Validator as an example Value-Creation Service. So `M-15` is this
deployment going beyond what it is required to do, and is recorded as **Declared** rather than
as closing a row.

**None of them is closed by the platform**, and that is `M-6` working as intended rather than a
gap: ds ships no payload model and imposes none. §3 says what a deployment does next.
