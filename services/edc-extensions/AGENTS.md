# edc-extensions

Java library of EDC `ServiceExtension`s, shaded into `connector.jar`. No image, no port.
This is **where the policy decision actually happens**: the ODRL constraint functions, the
pending guard, the negotiation-resume controller and the event publisher.

## References

| | |
|---|---|
| Requirements | [DSSC · Access & Usage Policies Enforcement](../../docs/blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) |
| Rules | [Rulebook · Policies](../../docs/rulebook/policies.md) — the conflict-resolution rules and the enforcement points, including **CR-4 fail closed** |
| Code as committed | [docs/services/edc-extensions.md](../../docs/services/edc-extensions.md) |

## The one rule

**A constraint function denies on error.** Unreachable connector, missing attribute,
unreadable operand — all deny. Returning `true` is the defect class this unit has most of,
and it is a silent one: the negotiation succeeds and nothing is logged.

## Three scopes, three questions

| Scope | Question | Functions |
|---|---|---|
| `contract.negotiation` | may an agreement be **signed**? | `AccessScopeFunction`, `ConsentStatusFunction`, `PurposeFunction`, `ContractRequiredFunction`, + the `NegotiationConsentValidator` post-validator |
| `transfer.process` | may access **start**? | `AgreementConsentFunction` (pre-start), `PurposeFunction` |
| `policy.monitor` | may access **continue**? | `AgreementConsentFunction` (in-flight), `PurposeFunction` |

Consent is revocable (GDPR Art. 7(3)), so one check at negotiation is not enough. The two
agreement-backed stances differ only in how they answer *silence*: pre-start denies on the
first unanswerable check, because refusing to start costs a retry; in flight it tolerates
three consecutive passes before terminating, because failing closed on one blip destroys a
live agreement. A definite *no* denies immediately in both. Membership and
`ds:contractRequired` are deliberately bound to `contract.negotiation` only — both are
conditions on entering an agreement.

**Consent at negotiation is decided by `NegotiationConsentValidator`, not by
`ConsentStatusFunction`.** A constraint function is handed the `Permission` and `Rule` has no
target at 0.16.0, so it cannot see the dataset; a `PolicyValidatorRule` receives the whole
`Policy`, which EDC has targeted at the asset. The function stays registered anyway, because
the operand must stay bound.

**Binding is what includes an operand in a scope, and EDC's `ScopeFilter` *removes* unbound
operands rather than failing them — so an unbound operand silently disables its check.**
Three consequences:

- **Bind the rule's action too.** An unbound action strips the whole permission, taking its
  consent constraint with it. `ACTIONS` in `DataspacesExtension` lists every form the mapper
  can emit; the profile query action is derived from the configured namespace rather than
  listed there.
- **`odrl:purpose` is bound in every scope** even though a purpose cannot change
  mid-transfer: the consent functions read purposes off the permission they are handed, and
  a filtered-out purpose constraint leaves them asking an unscoped question.
- **A bound operand with *no* function is the opposite failure** — evaluation fails outright
  and denies everything. So an operand nothing emits should be unbound, not bound-and-ignored.

Register **and bind** every operand you add, in both compact and expanded form. Two tests
enforce the pair, and neither can see what the other does:
`PolicyRegistrationTest` (here) asserts binding-vs-function;
`libs/governance/tests/tests/test_odrl_binding_conformance.py` asserts
binding-vs-emission by driving the real mapper and parsing this unit's bindings.

**Register on the narrowest context, never on `ParticipantAgentPolicyContext`.** The engine
matches both functions and validators with `contextType().isAssignableFrom(context.getClass())`,
and the catalogue, negotiation and transfer contexts all implement that interface — so a
registration there runs during catalogue browsing and collides, by operand key, with the
transfer scope's own function. `PolicyEvaluator` keeps one function per key and the winner is
whichever was registered last.

## Reading a right operand

**Getting this wrong is silent.** A policy that has been through EDC's JSON-LD expansion
carries a multi-purpose operand as a list of `{"@value": …}` objects whose inner literal is a
`jakarta.json.JsonString` that Jackson round-trips into a plain `Map{chars=…, string=…,
valueType=STRING}` — the IRI sits two levels down. `toString()` yields an object dump, which
the connector rejects as an unknown purpose. **Use `Purposes`**, which unwraps
`@value`/`@id`/`string`/`chars` recursively and drops anything still looking like a dump.

## The pending guard

`ConsentPendingGuard` marks a `REQUESTED` provider negotiation for a consent-gated dataset
*pending* while a subject decides; the state machine stops picking it up. It **decides
nothing** — every question is answered by ds-connector and the guard contributes the boolean.
**Returning `false` is not an allow**: the `ds:consentStatus` constraint still evaluates and
still denies. It only means parking would not help.

Resume is `NegotiationResumeController` on the management context, because EDC 0.16.0 can
terminate a negotiation through the Management API but cannot clear `pending`. Idempotent and
a no-op on terminal states, so a late grant cannot resurrect a terminated negotiation.

## A forked EDC class lives here

`org/eclipse/edc/connector/controlplane/transform/odrl/from/JsonObjectFromPolicyTransformer.java`
is **EDC v0.16.0's class**, patched so a multi-valued right operand publishes as a JSON-LD
array instead of a `toString()` dump, placed under the upstream package so it replaces the
broken one in the shadow JAR. A registered transformer cannot do this — the registry is
memoised, lookup is `findAny()`, there is no removal API and our extension initialises after
core. Full rationale in the file header.

Two guards, because a silent revert republishes unreadable policies while everything looks
healthy: `:edc-connector:verifyForkedTransformer` (greps the packaged outer **and** inner
`$Visitor` class) and `JsonObjectFromPolicyTransformerForkTest` (fails if `edcVersion` moves).
**When the fix lands upstream, delete the fork, both guards and the `duplicatesStrategy` block.**

## Authenticating to ds-connector

One implementation: `Oauth2InternalAuth`, a Keycloak `client_credentials` token cached to
30 s before expiry. Configured by `ds.connector.internal.{token.url,client.id,client.secret}`.
**The extension refuses to start without them** — an EDC that boots and then silently denies
every negotiation is much harder to diagnose than one that says why. An unresolved
`${PLACEHOLDER}` counts as unset: properties files interpolate from the environment and leave
unset variables verbatim.

There is no `X-Api-Key` fallback. That header was `EDC_API_KEY`, which is also EDC's
Management API key — one leak yielded contract administration, the data-plane signing keys
and the subject pools together, with no audit trail separating this caller from the dataset-api.

## The vault seeder is the only thing that fills the vault

Neither `vault-filesystem` nor `vault-hashicorp` is packaged, so the only `Vault` on the
classpath is EDC's boot-default `InMemoryVault`. `FilesystemVaultSeederExtension` is therefore
not one backend among several — **an unseeded vault resolves no alias at all**, which takes out
the EDR signing key and the STS client secret together and reports itself as a missing secret
rather than a missing file. It warns when no seed file is configured, for that reason.

Its setting is `ds.vault.seed.file`. It was `edc.vault.fs.file` — **the key EDC's own
`vault-filesystem` module reads** — which collides with nothing today only because that module
is absent; add it to the BOM and two extensions claim the vault from one key, with load order
deciding silently which seed survives. The old key is still honoured, with a deprecation
warning, because dropping it would start an un-updated deployment with an empty vault.

## Build and test

`task edc:test` · `task -d services/edc-extensions test` · `task edc:build` · `task edc:docker`.
Use `Monitor`, not SLF4J. OkHttp for HTTP. No mocking framework: the EDC contexts and
`ContractAgreement` have public constructors and builders, and `ConnectorClient.getJson` is
overridable, so every function can be driven from canned JSON.

**`task -d <unit> test` does not reach the container path.** A change here needs
`task edc:build`, and a behaviour change needs `task edc:restart` + `task e2e:all`.

> **`task dev:start` runs a continuous build plus watch loops that restart the EDC JVMs.**
> They race: a JVM can start while the JAR is still being written and load a partial file.
> Symptom is an EDC logging `Runtime … ready` but never answering, with an old startup
> message — check the `Dataspaces ODRL extensions registered: …` line against the source.
> The gradle cache is held by the continuous build, so a parallel `task edc:build` fails on a
> journal-cache lock. Let the watch build do it.

**Check EDC signatures against the packaged jars, not the source checkout.**
`~/git/github.com/eclipse-edc/Connector` is ahead of the 0.16.0 we build against — it carries
`StateEntityStore.breakLease`, which 0.16.0 does not — so the source answers *why* and the
jars answer *what*. `javap` inside the Gradle image reads the jars; see
`.agents/facts/services/edc-extensions.md`.
