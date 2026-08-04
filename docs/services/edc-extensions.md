# edc-extensions

A Java library of Eclipse EDC `ServiceExtension` implementations, shaded into
`connector.jar`. It has no image and no port of its own.

This is **where the policy question is asked**. The EDC evaluates ODRL constraints while it
negotiates a contract and for as long as a transfer runs; every constraint this platform
defines is answered here — by calling back into [`ds-connector`](connector.md). The Java side
carries the question across and enforces the answer; the decision itself is taken in Python,
in one place.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Access & Usage Policies Enforcement](../blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) |
| Rules it enforces | [Rulebook · Policies](../rulebook/policies.md) — the conflict-resolution rules and the enforcement points |

## The one rule

**A constraint function denies on error.** An unreachable connector, a missing attribute, an
unreadable operand — all deny.

Returning `true` when you cannot tell is the defect class this unit is most exposed to, and
it is a silent one: the negotiation succeeds, the data flows, and nothing is logged as wrong.

## What it does

Five things, in one JVM.

**Registers the ODRL constraint functions** that answer membership, purpose and consent
questions.

**Supplies a negotiation pending guard** that parks a provider-side negotiation while a data
subject decides, instead of refusing it.

**Registers a Management API route** that clears the parked flag again, so the connector can
resume a negotiation once a decision arrives.

**Forwards EDC's contract-negotiation and transfer-process events** to the connector's
webhooks, asynchronously, so delivery never blocks the state machine. DSP carries no signal
either side could use to learn a negotiation terminated or a transfer completed; EDC's
internal event router does. The transfer publisher is what makes a *provider* emit
`DataTransferCompleted` at all — before it, that half of the lifecycle reached the connector
from nowhere.

**Carries a fork of one upstream EDC class**, `JsonObjectFromPolicyTransformer`, placed under
the upstream package so it wins on the shaded classpath. The fork fixes multi-valued right
operands — without it an `isAnyOf` purpose list does not survive JSON-LD rendering. A build
task fails the build if the fork is not the copy that got packaged.

Two smaller extensions ride along: a **filesystem vault seeder** that loads a `.properties`
file into the EDC vault at boot, and an **HttpData endpoint generator** that rewrites the
public base URL advertised in an EDR.

## How it works

### Three scopes, three questions

EDC evaluates policy in named scopes. This unit binds to three, and the split is the point.

| Scope | Question | Evaluated by | Functions |
|---|---|---|---|
| `contract.negotiation` | may an agreement be **signed**? | `ContractValidationServiceImpl.validateInitialOffer` | `AccessScopeFunction`, `ConsentStatusFunction`, `PurposeFunction`, `ContractRequiredFunction`, plus the `NegotiationConsentValidator` post-validator |
| `transfer.process` | may access **start**? | `ContractValidationServiceImpl.validateAgreement`, from the provider's handling of a `TransferRequestMessage` | `AgreementConsentFunction` (pre-start stance), `PurposeFunction` |
| `policy.monitor` | may access **continue**? | EDC's policy monitor, per pass, per started provider transfer | `AgreementConsentFunction` (in-flight stance), `PurposeFunction` |

Consent is revocable under GDPR Art. 7(3), so one check at negotiation is not enough. The
policy monitor re-evaluates a *signed agreement's* frozen policy for every running provider
transfer, and a subject who withdraws consent terminates a transfer that is already flowing.
The transfer scope covers the window in between: an agreement is signed, the consumer asks
for the transfer, and until this was bound nothing looked at consent again until the first
monitor pass — which only runs once the transfer has already started.

**The two agreement-backed stances differ only in how they answer silence.** Pre-start, one
unanswerable check denies: refusing to start costs the consumer a retry. In flight, three
consecutive unanswerable passes are tolerated before terminating, because failing closed on
one blip would destroy a live agreement and buys nothing while it lasts — the dataset-api PEP
asks the same question on every query and fails closed itself. A definite *no* denies
immediately in both.

Membership and `ds:contractRequired` are bound to the negotiation scope only: whether you
belong to the dataspace is settled when the contract is made, not re-litigated per row.

### The constraint functions

| Left operand | Scope | Answered by |
|---|---|---|
| `{ns}Membership` | negotiation | `GET /internal/participants/check` — is this participant admitted with this scope? Cached per `identity\|scope`; an unanswerable check caches as **false** |
| `ds:consentStatus` / `{ns}ConsentStatus` | negotiation | `GET /internal/consent/check` — but see below: the deciding check is the post-validator, not this function |
| `ds:consentStatus` / `{ns}ConsentStatus` | transfer, monitor | `GET /internal/consent/check` against the **agreement's** consumer and asset — an empty subject pool refuses the start, or terminates the transfer |
| `odrl:purpose` | all three | accepts `IS_A`, `IS_ANY_OF` and `EQ`; the taxonomy check itself happens in the connector |
| `ds:contractRequired` | negotiation | requires `EQ`/`NEQ` and a boolean operand; denies anything else |

**At negotiation, consent is decided by a post-validator, not by the constraint function.**
`ConsentStatusFunction` is handed the `Permission`, and `Rule` carries no target at EDC
0.16.0, so it cannot learn which dataset is being negotiated. `NegotiationConsentValidator` is
a `PolicyValidatorRule`, which receives the whole `Policy` — and EDC targets that policy at
the asset before evaluating it. The function stays registered because the operand must stay
*bound*, and a bound operand with no function fails evaluation outright.

`{ns}` is the ODRL profile namespace, `https://w3id.org/dsp/policy/` by default. The operands
are produced by [`libs/governance`](libs/governance.md)'s mapper, and **the two vocabularies
must agree or the constraint is silently dropped by EDC's scope filter** — it removes an
unbound operand rather than failing it, and a permission stripped of its only constraint
becomes unconditional. `libs/governance`'s `test_odrl_binding_conformance.py` asserts that
every operand and action the mapper can emit is bound here, and that nothing bound is dead.

### Parking a negotiation

The most distinctive behaviour in the unit. When a consumer asks for a consent-gated dataset
that nobody has consented to yet:

1. The pending guard runs only for **provider-side** negotiations in `REQUESTED`.
2. It looks for a permission whose policy carries a consent-status constraint. None → not our
   problem, proceed.
3. It reads the purposes off that permission. Purposes arrive in a lot of shapes — plain
   strings, JSON-LD `@value` objects, Jackson round-trips, nested multiplicity constraints —
   so this unwrapping is deliberately thorough and deliberately drops anything it cannot
   read cleanly.
4. It asks the connector whether consent already exists. Three ways *not* to park: the
   connector could not answer, somebody already consents, or the requester is covered as a
   processor rather than someone to ask.
5. Otherwise it posts an ask and, only if the connector confirms, parks the negotiation.

A parked negotiation is excluded from every later state-machine batch, so the guard is not
re-invoked while it waits. When the subject decides, the connector calls
`POST {management}/dataspaces/negotiations/{id}/resume`, which clears the flag under the
entity's lease and reports one of `leased`, `terminal`, `not_pending` or `resumed`.

### Authentication outbound

Every call to the connector carries a Keycloak `client_credentials` bearer obtained as
`svc-edc`, cached until 30 s before expiry. That client holds `connector.internal` and
`connector.webhook` — two different scopes on one token, because the internal API and the
webhook are separate trust decisions.

## Configuration

EDC merges the process environment into its config, upper-casing and turning `.` into `_`, so
`ds.connector.internal.url` is set as `DS_CONNECTOR_INTERNAL_URL`.

**Credentials must come from the environment, never from a `.properties` file.** EDC's file
loader does a plain `Properties.load()` with no interpolation, so a `${VAR}` written there is
stored as that literal string. This unit defends against that: any value containing `${` is
treated as *absent*, which turns the mistake into a startup failure instead of a client id
literally named `${SVC_EDC_ID}`.

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| `ds.connector.internal.url` | `DS_CONNECTOR_INTERNAL_URL` | `http://ds-connector:30001` | the connector this EDC asks |
| `ds.connector.internal.token.url` | `DS_CONNECTOR_INTERNAL_TOKEN_URL` | — | Keycloak token endpoint. **Empty is fatal at boot** |
| `ds.connector.internal.client.id` | `DS_CONNECTOR_INTERNAL_CLIENT_ID` | — | this EDC's Keycloak client. **Empty is fatal** |
| `ds.connector.internal.client.secret` | `DS_CONNECTOR_INTERNAL_CLIENT_SECRET` | — | **secret**. Empty is fatal |
| `ds.access.scope.cache.ttl.seconds` | `DS_ACCESS_SCOPE_CACHE_TTL_SECONDS` | `60` | lifetime of both decision caches — the membership check and the pending guard. A value that is not a positive number of seconds is logged and ignored, not fatal |
| `dataspaces.odrl.namespace` | `DATASPACES_ODRL_NAMESPACE` | `https://w3id.org/dsp/policy/` | prefix for the `Membership` / `ConsentStatus` / `Query` operands |
| `ds.edr.endpoint.public.baseurl` | `DS_EDR_ENDPOINT_PUBLIC_BASEURL` | `""` | public base URL advertised in an EDR; empty means "do not rewrite" |
| `ds.vault.seed.file` | `DS_VAULT_SEED_FILE` | — | properties file the vault seeder loads. Neither `vault-filesystem` nor `vault-hashicorp` is packaged, so the only `Vault` on the classpath is EDC's in-memory default and **this seeder is the only thing that puts anything in it** — an unseeded vault resolves no alias, including the EDR signing key and the STS client secret. It reads `edc.vault.fs.file` as a deprecated fallback, with a warning: that is the key EDC's own `vault-filesystem` module reads, so the collision is latent rather than absent, and would be decided silently by extension load order |

!!! warning "`dataspaces.odrl.namespace` must match the connector's ODRL profile"
    The namespace is configured twice and independently: here, and as `namespace` in the ODRL
    profile `ds-connector` maps with. A mismatch is silent in the worst way — the connector
    publishes `{new}ConsentStatus`, this extension binds `{old}ConsentStatus`, EDC's scope
    filter *removes* the unbound operand, and every negotiation succeeds with no policy
    enforced and nothing logged. `libs/governance`'s
    `test_odrl_binding_conformance.py::test_the_extension_namespace_matches_the_profile` is
    what catches the drift.

There is **no** `ds.demo.identity.enabled`. The demo identity fallback — which accepted a
self-issued JWT without checking its signature and synthesised a `MembershipCredential` for
the signer — was deleted, not disabled; `task secrets:check` fails if a deployment reintroduces
`DS_DEMO_IDENTITY_ENABLED`. See [Rulebook · Participation](../rulebook/participation.md) `P-11`.

Hard-coded values that behave like configuration: a 5 s connect and read timeout to the
connector, four attempts with `{100, 500, 2000}` ms backoff on transport errors only (a
non-2xx is never retried), a 30 s token-refresh margin, a bound of 1024 entries on each
decision cache, and three tolerated unanswerable consent checks before the policy monitor
terminates a transfer. Each is a constant rather than a setting on purpose: they exist to
remove a failure mode, and a knob that lets a deployment turn one back to infinity restores
it.

## Build and packaging

A plain `java-library` — no `application` plugin, no shadow plugin of its own. It reaches a
running system only through `:edc-connector`, which declares it **first** in its dependency
block so that with `DuplicatesStrategy.EXCLUDE` the forked transformer wins over upstream's.

```
task edc:build      # gradle :edc-connector:shadowJar in a container → connector.jar
task edc:restart    # rebuild the JAR, rebuild the image, recreate both EDC containers
task edc:watch-build   # continuous rebuild, used by dev mode
```

Java 21, EDC SPI `0.16.0`. Third-party runtime dependencies shaded in: OkHttp and
Jackson-databind; everything else compiles against SPIs the runtime provides.
