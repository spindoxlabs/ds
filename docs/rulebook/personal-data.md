# Personal data

The rules that apply when a data product concerns a natural person.

Covers `DSSC-XCT-01`–`29`, and the parts of `DSSC-AUP` and `DSSC-PTO` that personal data
constrains.

This is the area where the platform is most developed and where the rules are most
consequential, so they are stated at more length than elsewhere.

## 1. Scope

**Decision: four declarations gate a dataset, and any one of them alone is enough.**

`classification: pii` is one of them and it is the one with a second consequence, which is
why this page used to name it as *the* switch. It is not, and the page said so for months
while the connector implemented something else. `connector.services.consent_vocabulary.requires_consent`
resolves the gate as the **disjunction** of four declarations
(`ds.governance.consent.consent_gate`):

| Declaration | Also does |
|---|---|
| `dataspace.consent_required: true` | nothing else — it is the explicit statement |
| `classification: pii` | drives the automatic ODRL prohibitions in [Policies](policies.md) §3 |
| `row_filters[]` | names the column rows are narrowed by |
| `user_filter_column` | the legacy spelling of the same, superseded by `row_filters` (`GOV-05`) |

Those are two different consequences of `classification: pii` — gating the dataset, and
emitting the prohibitions — and this page previously read as though they were one.

**Why the disjunction matters to a reader.** Auditing *"which datasets in this deployment
are consent-gated?"* by grepping for `classification: pii` gives the wrong answer. Measured
across `celine-eu/celine-pipelines` on 2026-09-02: **zero** datasets carried
`classification: pii`, `dataspace.consent_required` was unset everywhere, and fifteen
personal datasets were gated solely by `row_filters`. By the rule this page used to state,
none of them were personal; by the rule the connector implements, all fifteen were gated.

**And to a producer.** Adding `row_filters` to a dataset silently makes it consent-gated;
removing them silently un-gates it, and the file looks *cleaner* afterwards. That direction
is now an **error** in `check_consent_coherence` — filters present with neither
`consent_required` nor `pii` is a file asserting per-subject access control while declaring
the data impersonal — so the un-gating cannot happen quietly any more.

A dataset gated by any of the four is subject to everything on this page; one gated by none
of them, is not.

`DSSC-XCT-02` requires pseudonymised data and personal data without direct identifiers to
be treated as personal data. This platform goes further in one direction and must be
honest about a limit in another:

| # | Rule | Status |
|---|---|---|
| D-1 | Pseudonymised data is personal data. A dataset keyed by device id or subject DID rather than by name is still `pii` | **Declared** — classification is the producer's declaration; nothing detects a misclassification |
| D-2 | Provenance records carry **codes, pseudonymous DIDs and hashes only — never PII** | **Enforced** by construction across all sixteen event types |
| D-3 | A dataset may not be reclassified downward (from `pii`) without a documented assessment | **Declared** — no mechanism |
| D-3a | Any one of the four declarations above gates a dataset; they are ORed, never required together | **Enforced** — `ds.governance.consent.consent_gate`, one predicate for the ODRL offer, the PDP verdict and the compliance report |
| D-3b | A dataset declaring row-level filtering must also declare that it is personal | **Enforced** — an error in `check_consent_coherence`. Both directions of the coherence check are guarded now; until 2026-09-03 only the unenforceable one was, and a file could rest its whole protection on `row_filters` and pass |

### What a bare `ALLOW` means

`POST /internal/dataplane/authorize` answers `ALLOW` with no row filter when
`consent_gate` finds **none** of the four declarations. That verdict is reached by
*absence*, not by assertion: nothing in the file said "this data is impersonal" — nothing
said anything, and the gate found nothing to object with.

That is worth knowing when reading a decision, because it means the verdict cannot
distinguish *a producer who considered this and declared it impersonal* from *a producer who
never filled the fields in*. Making the open path positive — requiring an explicit
`consent_required: false` before the unfiltered path is taken — would turn silence into a
refusal instead of a permission, which is the rule `DataplaneRowFilter`'s `extra="forbid"`
already applies one layer down. It is **not** implemented: it is a fail-closed change that
refuses datasets which pass today and needs every deployment's governance updated first, so
it is a decision this page has to take before it is code
([#21](https://github.com/spindoxlabs/ds/issues/21), direction 3). Open.

Which declaration gated a dataset is recorded at the decision point — `consent_gate` names
its signals and the authorize path logs them — so a verdict can be traced back to the line
in `governance.yaml` that produced it. The verdict's own `reason` is a token a PEP matches
on and does not carry them.

**The limit worth stating plainly:** classification is asserted, not derived. If a producer
declares a personal dataset `green`, none of the protections on this page apply and nothing
in the platform will notice.

**One narrow exception, since 2026-09-03.** A dataset carrying a subject-keyed row filter is
evidence the platform *could* notice, and `check_consent_coherence` now does — not by
deriving the classification, which stays the producer's declaration, but by refusing the
combination as incoherent. Whether `classification` should be derivable at all is a separate
question and is deliberately still open
([#21](https://github.com/spindoxlabs/ds/issues/21), direction 4).

## 2. Legal bases

`DSSC-XCT-04` requires legitimate grounds; `DSSC-XCT-05` requires purpose limitation;
`DSSC-XCT-06` requires a cross-organisational consent management capability where consent
is the basis.

**Decision: the legal basis is declared per sharing offer, using DPV IRIs, and it
determines the user interface.**

| Legal basis | DPV IRI | Treatment |
|---|---|---|
| Consent | `https://w3id.org/dpv#Consent` | The subject gets a control. Grant and revoke are both real actions |
| Contract | `https://w3id.org/dpv#Contract` | **Disclosed, never asked.** Contract-based processing is not a choice, and offering a toggle that changes nothing is worse than not offering one |

| # | Rule | Status |
|---|---|---|
| D-4 | Only `dpv:Consent` offers get a UI control | **Enforced** |
| D-5 | A **covered processor** — same controller, same operation, acting under a data processing agreement (GDPR Art. 28) — is disclosed, never asked. `POST /consent/request` returns 409 and `/internal/consent/check` returns `should_ask: false`, so the pending guard does not park a negotiation on a question that has no answer | **Enforced** |
| D-6 | A legal basis other than consent or contract requires legal analysis and appropriate protection measures before it is added to the vocabulary (`DSSC-XCT-07`, `-08`) | **Declared** — the vocabulary is closed; adding a basis is a code change |

## 3. Purpose limitation

**The purpose vocabulary is the mechanism, and it is deliberately narrow.**

`dataspace.purpose[]` on a dataset is the **only** runtime declaration of what that dataset may
be used for. `tags` are DCAT-AP keywords: a topic is not a reason for processing. One meter
dataset serves incentive calculation, flexibility research and cost optimisation, so
mapping `meters → <a purpose>` is a category error, and `tag_to_purpose` exists only as an
authoring hint for scaffolding.

| # | Rule | Status |
|---|---|---|
| D-7 | An empty `purpose[]` is **never** a wildcard for personal data. The person was never told the use, so consent would fail GDPR Art. 4(11). Fail closed — and this applies to the *requested* purpose too, not only the declared one | **Enforced** |
| D-8 | Purpose matching follows the local `broader` chain only, never the DPV mapping | **Enforced** — see [Policies](policies.md) §2.1 |
| D-9 | Consent to a child purpose does not cover its parent | **Enforced** |
| D-10 | A purpose not in the active profile is a 422 at consent-write time, not a silently ignored value | **Enforced** — `consent_vocabulary.py` |

## 4. The consent key

**Decision: a consent record is keyed by (subject, purpose, controller-role).**

The third element is the one that is easy to get wrong. **A controller is not a legal
entity.** A distribution system operator's grid-operations function and its metering
function are distinct controllers of the same readings: metering holds them, operations
wants them for planning, and consent to one is not consent to the other. `controller_role`
is what makes that boundary checkable — a request arriving in the metering role is refused
against a row consented for operations, even though the controller matches.

**Decision, 2026-08-08: the controller-role vocabulary is declared by the producer, in
`controller_roles` beside the sharing offers.** It is not a participant attribute. A
participant's `roles` are DSP capacities — the identity-registry pins them to
`{provider, consumer}` — and an unbundled controller function is a data-protection fact about
one legal entity, not a capacity in the protocol. `D-11a` was checked against participant
roles until this date and was therefore **unsatisfiable**: no legal `controller_role` could be
in that set, so the check either compared against an empty set and passed on anything, or
failed every offer that named a role. It compared against an empty set everywhere, which is
why nothing noticed. Declaring it beside the offers also makes it checkable offline, by the
producer's own gate, which is where a producer's declaration belongs.

| # | Rule | Status |
|---|---|---|
| D-11 | The consent key is (subject, purpose, controller-role). Matching on controller alone is insufficient | **Enforced** |
| D-11a | An offer's `controller_role` must be one the file declares in `controller_roles`, and an offer naming a controller that *is* unbundled must say which function | **Enforced** — `offer-controller`, both directions errors (`libs/governance/src/ds/governance/compliance/consent_checks.py`). Checked offline, so it runs in `compliance.yml` on every change rather than only against a live registry |
| D-12 | A consent record carries a `legal_basis` evidence record: the DPV basis IRI, the consent-text version, the locale, a SHA-256 of the rendered text, the `user_visible_hash` and a submission reference. **Codes and hashes only, never PII** | **Enforced** — surfaced on `GET /consent/my`, `/consent/status` and `/internal/consent/check` |
| D-13 | The rendered-text hash is what proves *what the person was shown*. A translation may never widen a coverage window, change a resolution or invent a legal basis — the codes are authoritative and the frontend translates them | **Enforced** by construction: `GET /ns/sharing-offers` serves codes plus an English fallback, and dataset keys are not in the public projection. **A caller that needs the mapping is served by a route, never by the projection.** `POST /admin/disclosure` accepts an `offer_id` and resolves it through `consent_vocabulary.datasets_for_offer` server-side, so an offer-scoped export can be recorded without the keys ever being published — the alternative, adding them to the offer payload, would publish operator detail to the internet because that surface is unauthenticated by design |

### The scoped wildcard

The onboarding wizard records a subject's standing consent after approval via
`POST /consent/admin/shares`, naming an **offer**, not a dataset. The connector expands it
into `consumer_id = "*"` rows.

| # | Rule | Status |
|---|---|---|
| D-14 | The wildcard admits any party **inside the circle** for that controller and purpose. It never admits a new controller and never a new purpose | **Enforced**, and since 2026-08-28 the controller is also in the `L-2` consent fingerprint. It was not: the hash tuple carried `controller_role` alone, so a dimension the wildcard refuses to cross was invisible in the evidence proving which consent state authorised a handover. See `L-2` in [Provenance and logging](provenance-and-logging.md) |
| D-15 | A per-party row overrides the wildcard. An explicit grant and an explicit **opt-out** both win | **Enforced** |

## 5. Asking, granting and revoking

**A consumer asks by negotiating, not by calling an API.**

There is no cross-participant consent API, and its absence is a design decision worth
recording. A provider-side negotiation for a consent-gated dataset is parked by
`ConsentPendingGuard`; the connector records the ask from EDC's **DCP-verified**
`counterPartyId` and the offer's asset and purpose constraints. The subject decides through
`/consent/my/*`; a grant clears `pending` through a resume endpoint in this repository's EDC
extension and the negotiation continues.

The reason: DSP already carries the requester's identity, cryptographically. Re-deriving it
from a header proved it more weakly. `POST /consent/request` survives only as the
provider-local seeding route for an operator or the portal, authenticated as a service.

| # | Rule | Status |
|---|---|---|
| D-16 | The identity recorded against a consent ask is the DCP-verified counterparty, never a self-asserted header | **Enforced** |
| D-17 | Revocation terminates a **running** transfer, not merely future ones — **when it removes the last consent for that consumer and dataset**. While anyone else still consents, the transfer continues and the row filter drops the withdrawing subject's rows | **Enforced, and asserted live since 2026-08-09.** The qualifier is not a weakening: `AgreementConsentFunction.inFlight` asks `consent.check("", dataset, consumer, purposes)` — **no subject named** — so what a running transfer needs is that *somebody* still consents. One person withdrawing must not cut off everyone else's lawfully shared data, and it does not. Two enforcement points, on two clocks, both measured: the per-query row filter drops that subject within the same second, and the transfer process reaches `TERMINATED` **3s** after the last consent goes. `ds-e2e --flow consent-withdrawal` asserts both, reading the terminal state from the **provider EDC** rather than inferring it from a 403 — a 403 is also what an unrelated denial produces — and it establishes the last-consenter precondition explicitly, because inheriting it from whatever ran before is how the first version of that flow passed alone and failed in the suite. `FailClosedTest` covers the unit case. See [Policies](policies.md) A-12 |
| D-18 | A pending question that nobody can answer must not park a negotiation forever. A covered processor, and a purpose the offer does not carry, both resolve without asking | **Enforced** for the covered-processor case. The failure mode is real and has occurred: a policy published with no purpose constraint parked every negotiation on a question nobody could answer, with no error and no log |
| D-19 | A subject may see every consent they hold and every ask outstanding against them | **Enforced** — `/consent/my/*`, authenticated by VC-JWT rather than by service scope |

## 6. Natural-person identity

`DSSC-XCT-09` requires the identity management capability to deal with natural persons.

| Aspect | Decision |
|---|---|
| Identifier | A subject DID, `did:web:<participant>:users:<id>` — in the namespace of the organisation that holds their credentials (`D-22a`) — mapped from a Keycloak user |
| Credential | `DataSubjectCredential`, issued by the trust anchor |
| Authentication to subject surfaces | VC-JWT headers (`X-Subject-Id` + `X-User-VC`) verified against the trust-anchor key — **not** the scope-based service guard |
| Role composition | Additive. The same person may hold `DataSubject` and `ConsumerUser` |

| # | Rule | Status |
|---|---|---|
| D-20 | Subject-facing surfaces authenticate the subject's credential, never a service's scope. A service token must not be able to read one person's consents | **Enforced** — `/consent/my/*`, `/consent/status`, `/consumer/*` use the VC-JWT path |
| D-21 | Membership in an owner organisation is checked against the registry at consent-write time, not read from a JWT claim. The portal reads claims for UX; **data access decisions always go through the registry API** | **Enforced** |
| D-22 | A path-bearing subject DID must resolve, and its document asserts **no verification method** — the person holds no key | **Enforced.** The service itself serves the did:web path form (`/{path}/did.json`), so resolution no longer depends on an edge-proxy rewrite. The document carries `id` and nothing it cannot back: a subject presents nothing and signs nothing, so a key would be read by nobody. The DID must still resolve because it is what consent records, provenance events and `credentialSubject.id` point at |
| D-22a | A person's DID sits in the namespace of the organisation that holds their credentials — `did:web:<participant>:users:<id>` — and **that** organisation publishes it | **Enforced** (`DID-11` step 2). It was `did:web:users.<anchor-domain>:<id>`, which said every person in the dataspace belonged to the trust anchor; the party that onboarded them, vouches for them and answers for them is their REC. A custodian learns of a person by *receiving their credential*, which is what creates the row it then publishes |
| D-22b | **One human, one identifier**, however many organisations hold credentials about them | **Enforced.** Roles are additive and issuance is per role, so deriving the DID from each call's organisation would give a dual-role person two identifiers — splitting their consent records, memberships and provenance in half, silently. The first organisation to onboard them decides where they live; custody still follows each credential |

## 7. The intermediary question

`DSSC-XCT-17` requires acknowledging that some intermediation activities fall under the
Data Governance Act; `DSSC-XCT-26` requires an intermediary in a consumer-to-intermediary-to-business
flow to have means to manage consent on behalf of natural persons.

**Decision: this platform is an intermediary in the DGA sense when a deployment operates it
on behalf of data subjects, and it provides the consent-management means `XCT-26` requires.**
Whether a given deployment triggers DGA notification obligations is that deployment's legal
assessment, not a property of the software. What the software guarantees:

- consent is managed per subject, per purpose, per controller-role, with evidence
- the operator cannot fabricate a consent without producing a `legal_basis` record naming
  the text version and its hash
- every grant, revocation and disclosure is recorded as a PROV-O event

**`DSSC-XCT-27`** — an anonymisation capability that can prove effective anonymisation for
the non-personal / anonymised intermediation case — **does not exist**. A deployment
needing it must anonymise before ingest. Recorded in
[Scope and deviations](scope-and-deviations.md) §2.

## 8. Subject rights

| Right | How it is served | Status |
|---|---|---|
| Access — what is held about me | `GET /consent/my`, plus the subject-facing provenance view | **Enforced** |
| Withdrawal of consent | `/consent/my/*` revoke; terminates running transfers | **Enforced** in design (see D-17) |
| Erasure | Via the retention duty on the consumer's side (`odrl:delete` with `delayPeriod`), and the provider's own retention | **Declared** — the obligation is expressed in the policy; nothing verifies the consumer performed it |
| Transparency of recipients | The sharing offer names the controller and the processor category, and `GET /consent/my` shows what is granted to whom | **Enforced** |
| Objection / opt-out | An explicit opt-out row overriding the wildcard | **Enforced** |

`DSSC-XCT-08` requires "appropriate data protection measures, such as guaranteeing data
subjects' rights to delete personal data". **The honest statement is that erasure is
contractual, not technical**: once rows have been transferred under an agreement, this
platform expresses the deletion duty and records the disclosure, and cannot compel deletion
on a consumer's premises.

## Blueprint rows

**Closed by this page:** `DSSC-XCT-02`, `-04`, `-05`, `-06`, `-07`, `-08`, `-09`, `-17`,
`-26`.

**Open:** `DSSC-XCT-27` (anonymisation capability — out of scope, §7). **D-17 is now
enforced** — `P1-1` is closed, so revocation reaches a running transfer rather than only a
future one. **D-22 is enforced** — `P1-6` is closed: the service serves the did:web path form
itself rather than depending on an edge-proxy rewrite.

**Beyond the blueprint:** the controller-role dimension of the consent key (D-11), the
scoped wildcard with opt-out precedence (D-14, D-15), the disclosed-processor rule (D-5),
the rendered-text hash (D-12, D-13) and revocation reaching a running transfer (D-17) are
not asked for by DSSC. They are recorded here because they are rules participants must
follow, not because a row requires them.
