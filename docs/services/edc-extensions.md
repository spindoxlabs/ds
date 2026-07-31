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

### Two scopes, two questions

EDC evaluates policy in named scopes. This unit binds to two, and the split is the point.

| Scope | Question | Functions |
|---|---|---|
| `contract.negotiation` | may access **start**? | `AccessScopeFunction`, `ConsentStatusFunction`, `PurposeFunction`, `ds:contractRequired` |
| `policy.monitor` | may access **continue**? | `AgreementConsentFunction`, `PurposeFunction` |

The policy monitor re-evaluates a *signed agreement's* frozen policy for every running
provider transfer. Consent is revocable under GDPR Art. 7(3), so it must be answered there
too — a subject who withdraws consent terminates a transfer that is already flowing.

Membership and `ds:contractRequired` are bound to the negotiation scope only: whether you
belong to the dataspace is settled when the contract is made, not re-litigated per row.

### The constraint functions

| Left operand | Scope | Answered by |
|---|---|---|
| `{ns}Membership` | negotiation | `GET /internal/participants/check` — is this participant admitted with this scope? Cached per `identity\|scope`; an unanswerable check caches as **false** |
| `{ns}ConsentStatus` | negotiation | `GET /internal/consent/check` |
| `ds:consentStatus` / `{ns}ConsentStatus` | monitor | `GET /internal/consent/check` against the **agreement's** consumer and asset — an empty subject pool terminates the transfer |
| `odrl:purpose` | both | accepts `IS_A`, `IS_ANY_OF` and `EQ`; the taxonomy check itself happens in the connector |
| `ds:contractRequired` | negotiation | a marker constraint |

`{ns}` is the ODRL profile namespace, `https://w3id.org/dsp/policy/` by default. The operands
are produced by [`libs/governance`](libs/governance.md)'s mapper — the two vocabularies must
agree or the constraint is silently dropped by EDC's scope filter.

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
| `ds.access.scope.cache.ttl.seconds` | `DS_ACCESS_SCOPE_CACHE_TTL_SECONDS` | `60` | membership-decision cache lifetime |
| `dataspaces.odrl.namespace` | `DATASPACES_ODRL_NAMESPACE` | `https://w3id.org/dsp/policy/` | prefix for the `Membership` / `ConsentStatus` / `Query` operands |
| `ds.edr.endpoint.public.baseurl` | `DS_EDR_ENDPOINT_PUBLIC_BASEURL` | `""` | public base URL advertised in an EDR; empty means "do not rewrite" |
| `edc.vault.fs.file` | `EDC_VAULT_FS_FILE` | — | properties file the vault seeder loads |
| `ds.demo.identity.enabled` | `DS_DEMO_IDENTITY_ENABLED` | `false` | **dev only** — see below |

!!! danger "`DS_DEMO_IDENTITY_ENABLED` accepts unverified tokens"
    When the real DCP verifier rejects a token, this fallback base64-decodes the JWT payload
    **without checking any signature** and, if `iss` equals `sub`, synthesises a membership
    credential for that subject. It exists so a host-run EDC can work when `did:web`
    resolution is unavailable in the dev topology. It is a complete DSP authentication
    bypass, it defaults to **true** in dev compose, and it appears nowhere in the Helm charts
    — an absent key cannot be set.

Hard-coded values that behave like configuration: a 5 s connect and read timeout to the
connector, four attempts with `{100, 500, 2000}` ms backoff on transport errors only (a
non-2xx is never retried), and a 30 s token-refresh margin.

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
