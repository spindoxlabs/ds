# Policies

The policy language, the profile, how conflicts resolve, and where enforcement happens.

Covers `DSSC-AUP-01`–`91`.

## 1. Language

**Decision: ODRL 2.2, JSON-LD serialisation, with the profile in §2. No other policy
language is accepted.**

`DSSC-AUP-01` requires business rules to be convertible into machine-readable policies;
`DSSC-AUP-09` requires machine-readable formats. The authoring surface is
`services/connector/governance-rec/governance.yaml` — a declarative YAML that the governance
mapper turns into an `odrl:Offer` plus the EDC asset, policy definition and contract
definition. Participants do not author ODRL by hand.

`DSSC-AUP-10`–`-13` require each policy to carry metadata describing its language,
serialization, profile and version:

| Metadatum | How it is carried | Status |
|---|---|---|
| Language | `@type: odrl:Offer` and the ODRL `@context` | **Enforced** |
| Serialization | JSON-LD, implicit in the payload | **Enforced** |
| Profile | `odrl:profile` in the `@context`, set from the profile's `profile_iri` | **Enforced** when the profile declares one |
| Version | — | **Not enforced.** No policy carries a version. **Open gap** |

## 2. The profile

`DSSC-AUP-44`, `-45`, `-46` state what an ODRL profile must define: a standard vocabulary
for the domain, conflict-resolution rules, and validation rules distinguishing required from
optional fields.

**The profile is a file, not prose**:
`libs/governance/src/ds/governance/profiles/energy.yaml`, selected by
`CONNECTOR_ODRL_PROFILE_PATH`. It is served at `GET /ns/policy` as SKOS concepts, publicly
and unauthenticated — an onboarding wizard has to render purposes before anyone has an
identity.

`POST /provider/sync` re-reads the profile and drops the cached vocabulary, so a change is
published without a restart, and the taxonomy served is always the one the catalogue was
mapped against — one profile, not two.

### 2.1 Vocabulary (`AUP-44`)

Namespace `https://w3id.org/dsp/policy/`, prefix `dsp-policy`.

| Term | Kind | Meaning |
|---|---|---|
| `Membership` | left operand | The requester's standing relative to a named owner: `owner:<alias>:member` or `owner:<alias>:partner` |
| `ConsentStatus` | left operand | Whether a consent covering (subject, purpose, controller-role) is active |
| `Query` | action | Read rows from a dataset through the data plane |
| `purpose/<Slug>` | concept | A reason for processing, from the purpose taxonomy |
| `odrl:purpose` | left operand (core ODRL) | The requester's declared reason for processing |

The purpose taxonomy is nine SKOS concepts with a local `broader` hierarchy and a
`dpv_mapping` to W3C DPV 2.3. Two rules govern it and both are anti-widening:

| # | Rule | Status |
|---|---|---|
| A-1 | `odrl:isA` matching follows **only** the local `broader` chain, never `dpv_mapping`. A `broadMatch` to a generic DPV term would let an unrelated use satisfy a specific consent | **Enforced** |
| A-2 | Consent to a child purpose does **not** cover its parent | **Enforced** |

Adding a purpose means editing the profile *and* recording the DPV alignment in
[`docs/taxonomies/dpv-2.3.md`](../taxonomies/dpv-2.3.md), *and* regenerating
`schemas/purpose-vocabulary.json`, whose `enum` is the active profile's slug list.

### 2.2 Validation rules (`AUP-46`)

`DSSC-AUP-02` and `-03` require syntax and semantic validation **before deployment**. The
gate is `task compliance:validate`, which runs before `POST /provider/sync` and refuses on:

- EDC asset / policy / contract id collisions between dataset keys (an import would
  silently clobber)
- referential integrity of `ownership[].name` against the owners registry, and owner DIDs
  against the participant registry
- a purpose not in the active profile
- a sharing offer that does not resolve, or whose purpose the dataset does not declare
- incoherence between consent declarations, row filters, retention and the validity window
- `--deny-key <glob>` for dataset keys that must not reach a given environment

**Required vs optional fields** are the Pydantic models in `libs/governance`, published as
JSON Schema under `schemas/` and generated from the models rather than hand-written — see
[Catalogue and metadata](catalogue-and-metadata.md) §3 for the field-level list.

| # | Rule | Status |
|---|---|---|
| A-3 | No governance file reaches an EDC without passing the gate | **Declared** — the CLI exists and CI runs it, but `POST /provider/sync` does not itself require that it passed |
| A-4 | CI runs the gate on every change | **Not enforced** — CI passes `--participants` pointing at a file that does not exist, so the `owner-participant` and `controller_role` checks are silently skipped. Defect **P1-8** |
| A-5 | The policy-id collision sweep detects collisions between policy ids and contract ids | **Not enforced** — the two id spaces are compared in separate buckets and the check is registered under the wrong name, so the collision the mapper can actually produce is undetectable. Defect **P3-3** |

## 3. What a policy says

The mapper derives the ODRL from two declared fields, so a producer states intent and the
policy follows.

**Permitted actions, by `access_level`:**

| `access_level` | Actions |
|---|---|
| `open` | `Query`, `odrl:aggregate`, `odrl:transfer` |
| `internal` | `Query`, `odrl:aggregate` |
| `restricted` | `Query` |
| `secret` | none — the dataset is not published at all |

**Automatic prohibitions, by `classification`:**

| `classification` | Prohibited |
|---|---|
| `pii` | `odrl:transfer`, `odrl:derive`, `odrl:distribute`, `odrl:sublicense` |
| `red` | `odrl:transfer`, `odrl:sublicense` |
| `yellow` | `odrl:sublicense` |
| `green` | none |

**Constraints attached to a permission**, in emission order: membership (for `internal`
and `restricted`, or an explicit `access_requirements`), contract acknowledgement (for
`restricted`), purpose, and consent status.

Constraints within a permission are **ANDed**. Multiple purposes are therefore emitted as
one `odrl:isAnyOf` constraint listing every permitted purpose, not one constraint per
purpose — the latter would demand a consumer's use serve all of them at once.

**Obligations:** a delete obligation refined by `odrl:delayPeriod ≤ P<retention_days>D`, and
an attribution obligation when the dataset declares one.

| # | Rule | Status |
|---|---|---|
| A-6 | `access_level: secret` means the dataset is never mapped or published | **Enforced** |
| A-7 | A `pii` dataset may never be transferred onward, derived from, distributed or sublicensed | **Enforced** as an ODRL prohibition. Note that a prohibition is a *statement to the consumer*; nothing in this platform technically prevents a consumer from doing it after receipt |
| A-8 | Retention is expressed as a machine-readable duty on every dataset that declares one | **Enforced** in emission. Its `rdf:` prefix is not declared in the emitted `@context` (defect P3-3) |
| A-9 | A policy's validity window (`valid_from` / `valid_until`) is enforced | **Not enforced** — the fields are order-checked and never emitted into the policy. Defect **P3-3** |

## 4. Conflict resolution

`DSSC-AUP-39` requires the data space to define its policy interpretation rules;
`DSSC-AUP-50`–`-53` state the three rules a data space must specify. **This data space
adopts all three as written**, plus two of its own that the blueprint does not state and
this platform's design requires.

### The five rules, in precedence order

| # | Rule | Source |
|---|---|---|
| **CR-1** | **Prohibition precedence.** If one policy permits an action and another prohibits it, the prohibition wins | `DSSC-AUP-51` |
| **CR-2** | **Data space rules precedence.** A mandatory data space policy overrides a participant policy | `DSSC-AUP-53` |
| **CR-3** | **Specificity precedence.** A more specific policy overrides a more general one | `DSSC-AUP-52` |
| **CR-4** | **Fail closed.** An undecidable constraint — an unreachable evaluation endpoint, a missing attribute, an unbound operand — is a **denial**, never a permission | this data space |
| **CR-5** | **Consent precedence.** Where personal data is involved, absence or withdrawal of a valid consent overrides every permission, including one already agreed | this data space |

### What each means concretely here

- **CR-1** is why a `pii` dataset published at `access_level: open` still cannot be
  transferred: `open` permits `odrl:transfer`, `pii` prohibits it, the prohibition wins.
  The mapper emits both and the conflict is real, not hypothetical.
- **CR-2** is why the classification-driven prohibitions and the consent gate are derived
  by the platform from `classification` and `consent_required`, not written by the producer.
  A producer cannot opt out of them in `governance.yaml`.
- **CR-3** applies within the consent registry: a per-party consent row overrides the
  scoped wildcard, and **an explicit opt-out and an explicit grant both win** over the
  wildcard. It also applies to the governance overlay: `governance.<name>.yaml` merges on
  top of the base file.
- **CR-4** was the rule this platform most needed and least kept — defect **P0-2**, now
  closed. Every path that returned *permit* on an unreachable or missing input now denies:
  `Oauth2InternalAuth.authorize` returns `false` rather than sending an unauthenticated
  request, `ContractRequiredFunction` denies on an operator it cannot apply and on a right
  operand it cannot parse, and `AgreementConsentFunction` denies once an outage stops being
  transient (see `Stance` and `tolerate`, and the note on bounded tolerance below).
  `ConsentStatusFunction`'s missing-`ds.dataset_id` branch defers to
  `NegotiationConsentValidator`, a post-validator that reads the dataset off the policy
  target — post-validators run only after constraint functions pass, so deferring is not a
  permit. `services/edc-extensions/src/test/java/dataspaces/edc/FailClosedTest.java`.
- **CR-5** is why `AgreementConsentFunction` is bound to EDC's `policy.monitor` scope
  rather than only to `contract.negotiation` — an agreement is not a standing permission
  over personal data.

| # | Rule | Status |
|---|---|---|
| A-10 | CR-1, CR-2, CR-3 are implemented by the mapper's emission order and the consent registry's row precedence | **Enforced** |
| A-11 | CR-4 holds at every evaluation point | **Enforced** — defect **P0-2** is closed. `FailClosedTest` covers each path: a definite *no* denies immediately, sustained silence denies, and the PRE_START gate denies on the first unanswerable check. **One deliberate exception:** a *single* unanswerable check in `policy.monitor` does not terminate a running transfer, because the dataset-api PEP fails closed per query and a transient blip is not a revocation. The tolerance is bounded and the streak resets on any definite answer |
| A-12 | CR-5 holds during a running transfer, not only at negotiation | **Enforced** — defect **P1-1** is closed. The consent constraint now reaches EDC: the mapper emits `ds:contractRequired` (not the unbound `odrl:industry`) and the profile's `ConsentStatus` operand, and both are registered in `policy.monitor` |

## 5. Enforcement points

`DSSC-AUP-04`–`-08` require enforcement at publication, discovery, negotiation and during
the sharing itself, and require every participant to have the capability.

| Stage | Point | Mechanism | Status |
|---|---|---|---|
| **Publication** | `POST /provider/sync` | validation gate; `secret` never published; unresolvable consent gate refused | **Enforced** |
| **Discovery** | DSP catalogue over a DCP-verified counterparty | the offer carries the policy; a consumer sees the terms before negotiating | **Enforced** over DSP, and on `POST /consumer/catalog` since defect **P0-1** closed — `require_consumer_catalog_caller` accepts a service scope **or** a `ConsumerUser` VC-JWT, never neither. `services/connector/tests/test_consumer_catalog_auth.py` |
| **Negotiation** | EDC constraint functions in `contract.negotiation` scope, calling `ds-connector /internal/*` | membership, purpose, consent, contract acknowledgement | **Enforced** — defect **P1-1** is closed. No emitted operand is stripped: `ds:accessScope` is no longer bound with nothing behind it, `ds:contractRequired` replaced the unbound `odrl:industry`, and consent is registered in both scopes and in both spellings. `PolicyRegistrationTest`, `NegotiationScopeFunctionsTest`, `NegotiationConsentValidatorTest` |
| **Negotiation** | `ConsentPendingGuard` | parks a negotiation while a subject decides, rather than refusing | **Enforced** |
| **During transfer** | `AgreementConsentFunction` in `policy.monitor` scope | revocation terminates a live transfer through EDC's state machine | **Enforced.** `FailClosedTest` covers this function in both scopes — withdrawal after signing terminates, an agreement with no asset terminates, sustained silence terminates, and a definite answer clears the streak |
| **Data plane** | `POST /internal/dataplane/authorize` | per-request decision plus the row filter | **Enforced.** The decision shape is `ds.governance.dataplane`, parsed by both ends — a PEP that cannot read it, or cannot apply the filter it names, serves nothing (defect **P1-2**, closed) |

**PAP / PIP / PDP / PEP mapping**, for readers coming from `DSSC-AUP-38`–`-91`:

| Role | Component |
|---|---|
| PAP — administration | `governance.yaml` + `libs/governance` mapper + `POST /provider/sync` |
| PIP — information | identity-registry (participants, owners, memberships, credentials); ds-connector consent registry |
| PDP — decision | ds-connector `/internal/*` |
| PEP — enforcement | `services/edc-extensions` at negotiation and monitor scope; the participant-operated dataset API at the data plane |

| # | Rule | Status |
|---|---|---|
| A-13 | Every participant runs the policy enforcement capability; there is no unenforced participation tier (`AUP-08`) | **Declared** — the participant agent bundles it |
| A-14 | An operand emitted by the mapper has a function registered for it in every scope it is bound to, and no operand is bound without a producer | **Enforced** — the conformance test this row asked for exists: `PolicyRegistrationTest.everyBoundOperandHasAFunctionSomewhere`, plus `accessScopeIsNotBound`, `consentStaysBoundInEveryScope`, `consentHasAFunctionForBothOperandFormsInEveryScope` and `negotiationOnlyOperandsAreNotBoundElsewhere`. It governs the **policy engine**; the compliance matrix is a separate consumer and §6 below is where it still falls short |

## 6. The compliance matrix

`task compliance:evidence` produces a DCAT-AP catalogue and an ODRL offer report under
`reports/compliance`, plus a policy matrix intended to show, per dataset, which constraints
are enforced where.

**Do not currently trust the matrix**, and note that its cause is *not* the one this page
used to give. `P1-1` is closed at the policy engine — the operands are emitted, bound and
registered — but the matrix still misses two of them, because **it filters on CURIEs while
the mapper emits full IRIs**. `matrix.py` buckets on `ds:consentStatus` and `ds:accessScope`;
the mapper emits `{profile.namespace}ConsentStatus` and `{profile.namespace}Membership`
(verified in `reports/compliance/core-odrl-offers.jsonld`:
`https://w3id.org/dsp/policy/ConsentStatus`, `.../Membership`), and `_constraint_summary`
does no CURIE/IRI normalisation. So **membership appears in neither bucket and consent in
none**, and every matrix entry understates what EDC actually evaluates.

Two parts of the old claim no longer hold: `ds:contractRequired` *is* matched, and the
`pii` over-report is fixed — `requires_consent` no longer includes `classification == "pii"`.

The fix is to normalise both sides to one spelling before comparing, and to assert it, so
the matrix cannot silently diverge from the mapper again. **Open gap**, with no owning
defect row since `P1-1` closed.

## Blueprint rows

**Closed by this page:** `DSSC-AUP-01`, `-02`, `-03`, `-04`, `-05`, `-06`, `-07`, `-08`,
`-09`, `-10`, `-11`, `-12`, `-16`, `-17`, `-39`, `-44`, `-45`, `-46`, `-50`, `-51`, `-52`,
`-53`; `DSSC-PUB-38`; `DSSC-SVD-38`.

**Open:** `DSSC-AUP-13` (policy version metadata). `AUP-06` and `AUP-07` were previously
listed here as blocked by defects **P0-2** and **P1-1**; both are closed, so both rows are
now claimed — see A-11, A-12 and §5. What remains open on this page is the policy version
(§1), the validity window (A-9), the `rdf:` prefix (A-8), the CI gate (A-4) and the
compliance matrix's operand spelling (§6).
