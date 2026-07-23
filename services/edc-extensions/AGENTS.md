# edc-extensions — Agent Guide

## Service identity

- **Role**: Custom ODRL constraint functions for the EDC policy engine
- **Language**: Java 21, Gradle
- **Type**: Library JAR (compiled into edc-connector fat JAR)
- **EDC version**: 0.16.0

## Source layout

```
src/main/java/dataspaces/edc/
├── DataspacesExtension.java              EDC ServiceExtension — registers constraint functions + vault seeder
├── AccessScopeFunction.java              Membership constraint — participant scope check via HTTP
├── ConsentStatusFunction.java            ConsentStatus constraint — HTTP call to ds-connector consent check
├── PurposeFunction.java                  odrl:purpose constraint — admits the shape the mapper emits
├── DemoIdentityFallbackExtension.java    Dev-only: accepts unsigned DCP tokens (DS_DEMO_IDENTITY_ENABLED)
├── FilesystemVaultSeederExtension.java   Loads vault properties into EDC vault at boot
└── HttpDataEndpointExtension.java        HTTP data plane endpoint
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new ODRL constraint | Create new `*Function.java`, register in `DataspacesExtension.java` |
| Change access scope logic | `AccessScopeFunction.java` |
| Change consent check logic | `ConsentStatusFunction.java` |
| Update EDC dependency version | `build.gradle.kts` |

## Constraint functions

The constraint functions use profile-namespaced operand names (e.g. `dsp-policy:Membership`, `dsp-policy:ConsentStatus`). The namespace prefix is configurable via the ODRL profile.

### AccessScopeFunction (Membership)

Evaluates whether the requesting participant has the required scope. Makes an HTTP POST to `ds-connector /internal/participants/check`, which forwards the check to the identity-registry service. The connector URL is configured via `ds.connector.internal.url` EDC property. Results are cached with a configurable TTL. Retries up to 3 times on failure.

### ConsentStatusFunction (ConsentStatus)

Makes an HTTP GET to `ds-connector /internal/consent/check` to verify active consent for the requesting participant. The connector URL is configured via `ds.connector.internal.url` EDC property.

**It also carries the purpose.** `extractPurposes(Permission)` reads the `odrl:purpose`
constraint off the *same permission being evaluated* — that is what the provider offers
this dataset for — and appends `&purpose=a,b,c`. A negotiation for a dataset whose
purposes no subject has consented to therefore finds an empty subject pool and is denied.

Reading the purpose off the permission avoids threading state between two independent
constraint functions: EDC evaluates each atomic constraint separately, but hands each
one the whole rule.

Both `odrl:purpose` and its expanded form `http://www.w3.org/ns/odrl/2/purpose` are
handled, since whether the ODRL context was applied depends on how the policy reached
the store.

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

> **`task dev` runs a continuous build (`edc:watch-build`) plus watch loops that
> restart the EDC JVMs when the fat JAR changes.** The two race: a JVM can start while
> the JAR is still being written and then load a stale or partial file. The symptom is
> an EDC that logs `Runtime … ready` but never answers on any HTTP port, with an old
> startup message. Check the `Dataspaces ODRL extensions registered: …` line against
> the source, and restart the `edc-provider` / `edc-consumer` panes if it is stale.
>
> The gradle cache is held by the continuous build, so a parallel `task edc:build`
> fails with a journal-cache lock. Let the watch build do it.

## Integration points

- **Compiled into**: edc-connector fat JAR
- **Calls at runtime**: ds-connector `/internal/consent/check` endpoint
- **Calls at runtime**: ds-connector `POST /internal/participants/check` (which forwards to identity-registry)
- **Registered by**: EDC ServiceExtension SPI
