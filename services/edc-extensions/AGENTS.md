# edc-extensions — Agent Guide

## Service identity

- **Role**: Custom ODRL constraint functions for the EDC policy engine
- **Language**: Java 21, Gradle
- **Type**: Library JAR (compiled into edc-connector fat JAR)
- **EDC version**: 0.16.0

## Source layout

```
src/main/java/dataspaces/edc/
├── DataspacesExtension.java              EDC ServiceExtension — bindings, functions, guard, event publisher
├── AccessScopeFunction.java              Membership constraint — participant scope check via HTTP
├── ConsentStatusFunction.java            ConsentStatus at negotiation — may access start?
├── AgreementConsentFunction.java         ConsentStatus in policy.monitor — may access continue?
├── ConsentPendingGuard.java              Parks a negotiation while a data subject decides
├── NegotiationResumeController.java      Clears `pending` — the one thing the Management API cannot do
├── NegotiationEventPublisher.java        Forwards negotiation lifecycle events to ds-connector
├── PurposeFunction.java                  odrl:purpose constraint — admits the shape the mapper emits
├── Purposes.java                         Reads odrl:purpose off a permission (shared by both consent functions)
├── ConnectorClient.java                  HTTP transport to ds-connector /internal/* — retry, fail-closed
├── ConsentApi.java                       GET /internal/consent/check → one decision, several projections
├── ConsentAskApi.java                    POST /internal/consent/asks → record the ask behind a parked negotiation
├── InternalAuth.java                     The credential seam (one implementation)
├── Oauth2InternalAuth.java               Keycloak client_credentials token, cached to 30s before expiry
├── DemoIdentityFallbackExtension.java    Dev-only: accepts unsigned DCP tokens (DS_DEMO_IDENTITY_ENABLED)
├── FilesystemVaultSeederExtension.java   Loads vault properties into EDC vault at boot
└── HttpDataEndpointExtension.java        HTTP data plane endpoint
```

## Two scopes, two questions

| Scope | Question | Functions |
|---|---|---|
| `contract.negotiation` | may access **start**? | `AccessScopeFunction`, `ConsentStatusFunction`, `PurposeFunction`, `ds:contractRequired` |
| `policy.monitor` | may access **continue**? | `AgreementConsentFunction`, `PurposeFunction` |

EDC's policy monitor re-evaluates a signed agreement's policy for every started
provider transfer and terminates the transfer the moment evaluation fails.
Consent is revocable (GDPR Art. 7(3)), so it has to be answered there too.

**Binding is what includes an operand in a scope**, and EDC's `ScopeFilter`
*removes* unbound operands rather than failing them — so an unbound operand
silently disables its check. Two consequences that are easy to get wrong:

- **Bind the rule's action too.** If the permission's action is unbound in a
  scope, the whole permission is stripped, taking its consent constraint with
  it. `ACTIONS` in `DataspacesExtension` lists every form the mapper can emit.
- **`odrl:purpose` is bound in `policy.monitor`** even though the purpose cannot
  change mid-transfer: the consent functions read the purposes off the
  permission they are handed, and a filtered-out purpose constraint would leave
  them asking an unscoped question, which the connector fails closed.

Membership and `ds:contractRequired` are deliberately *not* bound to
`policy.monitor` — both are conditions on entering an agreement.

## The pending guard

`ConsentPendingGuard` implements EDC's `ContractNegotiationPendingGuard`: a
provider negotiation in `REQUESTED` for a consent-gated dataset is marked
*pending* while a data subject decides, and the state machine stops picking it
up. This is upstream's recommended shape for "wait for an external decision"
(Connector discussion #4460).

It decides nothing. Every question — consent-gated? covered processor? ask
already outstanding? anybody to ask? — is answered by ds-connector; the guard
contributes the boolean. **Returning `false` is not an allow**: the
`ds:consentStatus` constraint still evaluates and still denies. It only means
parking would not help.

Cost is bounded: the state-machine query filters `isNotPending()` and the guard
runs on that already-filtered batch, so a parked negotiation is never re-tested.
The short-TTL cache is for bursts of *new* negotiations for the same dataset.

Resume is `NegotiationResumeController`, on the **management** context —
`POST {management}/dataspaces/negotiations/{id}/resume`. It exists because EDC
0.16.0 can terminate a negotiation through the Management API but has no way to
clear `pending`; refusal and TTL expiry therefore need no custom code. It is
idempotent and a no-op on terminal states, so a grant arriving after the TTL
cannot resurrect a terminated negotiation.

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new ODRL constraint | Create new `*Function.java`, register **and bind** in `DataspacesExtension.java` |
| Change access scope logic | `AccessScopeFunction.java` |
| Change consent check logic | `ConsentStatusFunction.java` (negotiation), `AgreementConsentFunction.java` (running transfer) |
| Change when a negotiation parks | `ConsentPendingGuard.java` + `/internal/consent/asks` in the connector |
| Change how the EDC authenticates to ds-connector | `Oauth2InternalAuth.java`, `DataspacesExtension.internalAuth` |
| Update EDC dependency version | `build.gradle.kts` |

## Constraint functions

The constraint functions use profile-namespaced operand names (e.g. `dsp-policy:Membership`, `dsp-policy:ConsentStatus`). The namespace prefix is configurable via the ODRL profile.

### AccessScopeFunction (Membership)

Evaluates whether the requesting participant has the required scope. Makes an HTTP POST to `ds-connector /internal/participants/check`, which forwards the check to the identity-registry service. The connector URL is configured via `ds.connector.internal.url` EDC property. Results are cached with a configurable TTL. Retries up to 3 times on failure.

### ConsentStatusFunction (ConsentStatus)

Makes an HTTP GET to `ds-connector /internal/consent/check` to verify active consent for the requesting participant. The connector URL is configured via `ds.connector.internal.url` EDC property.

**It also carries the purpose.** `Purposes.of(Permission)` reads the `odrl:purpose`
constraint off the *same permission being evaluated* — that is what the provider offers
this dataset for — and appends `&purpose=a,b,c`. A negotiation for a dataset whose
purposes no subject has consented to therefore finds an empty subject pool and is denied.

Reading the purpose off the permission avoids threading state between two independent
constraint functions: EDC evaluates each atomic constraint separately, but hands each
one the whole rule.

Both `odrl:purpose` and its expanded form `http://www.w3.org/ns/odrl/2/purpose` are
handled, since whether the ODRL context was applied depends on how the policy reached
the store.

**The value needs unwrapping, and getting that wrong is silent.** A policy that has
been through EDC's JSON-LD expansion carries a multi-purpose operand as a *list of
`{"@value": …}` objects*, and the inner literal is a `jakarta.json.JsonString` that
Jackson round-trips into a plain `Map{chars=…, string=…, valueType=STRING}` — so the
IRI sits two levels down. Calling `toString()` on it yields an object dump, which the
connector rejects as an unknown purpose (422). `Purposes` unwraps `@value`/`@id`/
`string`/`chars` recursively and drops anything that still looks like an object dump.

That bug survived a long time because the only caller was `ConsentStatusFunction`,
which short-circuits before reading purposes whenever `ds.dataset_id` is absent from
the participant attributes — which is always. Both consent functions now log the raw
type and value when a consent-gated permission yields no readable purpose; without
that the symptom is a refused or parked negotiation with nothing explaining it.

### PurposeFunction (odrl:purpose)

Admits the constraint shapes the governance mapper emits — `isA` (a single purpose),
`isAnyOf` (a multi-purpose dataset) and `eq` — and denies a constraint with no right
operand.

It is not, on its own, the access decision: a purpose the *provider* permits still
yields no rows for a subject who did not consent to it. Registering it is what stops
the purpose being decorative — **an unbound left operand evaluates to false in EDC, so
without this every negotiation for a purpose-scoped dataset would be denied.**

## Coding conventions

- Each function implements `AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext>` from EDC SPI
- Functions are registered in `DataspacesExtension.initialize()` for the `NEGOTIATION` scope
- **Bind every left operand you register** (`ruleBindingRegistry.bind(operand, "contract.negotiation")`), in both compact and expanded form when the ODRL context could apply
- Use `Monitor` (EDC's logging abstraction) for logging, not SLF4J directly
- HTTP calls use OkHttp (EDC's standard HTTP client)

## Build

```bash
# From repo root:
task edc:build                    # or: gradle :edc-extensions:build
task edc:docker                   # build fat JAR + Docker image
```

> **`task dev:start` runs a continuous build (`edc:watch-build`) plus watch loops that
> restart the EDC JVMs when the fat JAR changes.** The two race: a JVM can start while
> the JAR is still being written and then load a stale or partial file. The symptom is
> an EDC that logs `Runtime … ready` but never answers on any HTTP port, with an old
> startup message. Check the `Dataspaces ODRL extensions registered: …` line against
> the source, and restart the `edc-provider` / `edc-consumer` panes if it is stale.
>
> The gradle cache is held by the continuous build, so a parallel `task edc:build`
> fails with a journal-cache lock. Let the watch build do it.

## Authenticating to ds-connector

All `/internal/*` and `/webhooks/*` calls go through `ConnectorClient`, which
gets its credential from `InternalAuth`. There is exactly one implementation:
`Oauth2InternalAuth`, a Keycloak `client_credentials` token obtained with EDC's
own `Oauth2Client` and cached until 30 s before expiry.

Configured by `ds.connector.internal.{token.url,client.id,client.secret}` (env
`DS_KEYCLOAK_TOKEN_URL`, `DS_CONNECTOR_CLIENT_ID`, `DS_CONNECTOR_CLIENT_SECRET`).
**The extension refuses to start without them** — an EDC that boots and then
silently denies every negotiation because policy evaluation cannot reach the
connector is much harder to diagnose than one that says why.

There is no `X-Api-Key` fallback. That header was `EDC_API_KEY`, which is *also*
EDC's Management API key: one leak yielded contract administration, the
data-plane signing keys and the subject pools together, with no audit trail
distinguishing this caller from the dataset-api.

An unresolved `${PLACEHOLDER}` counts as unset (`DataspacesExtension.setting`) —
the properties files interpolate from the environment and leave unset variables
verbatim, which would otherwise authenticate as a client literally named
`${DS_CONNECTOR_CLIENT_ID}`.

## Integration points

- **Compiled into**: edc-connector fat JAR
- **Calls at runtime**: ds-connector `GET /internal/consent/check`, `POST /internal/consent/asks`
- **Calls at runtime**: ds-connector `POST /internal/participants/check` (which forwards to identity-registry)
- **Calls at runtime**: ds-connector `POST /webhooks/contract-negotiation` (negotiation lifecycle events)
- **Serves**: `POST {management}/dataspaces/negotiations/{id}/resume`, called by ds-connector when a subject grants
- **Registered by**: EDC ServiceExtension SPI
