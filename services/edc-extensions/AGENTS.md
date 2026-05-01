# edc-extensions — Agent Guide

## Service identity

- **Role**: Custom ODRL constraint functions for the EDC policy engine
- **Language**: Java 21, Gradle
- **Type**: Library JAR (compiled into edc-connector fat JAR)
- **EDC version**: 0.16.0

## Source layout

```
src/main/java/it/spindox/dataspaces/extensions/
├── DataspacesExtension.java      EDC ServiceExtension — registers all constraint functions
├── AccessScopeFunction.java      ds:accessScope — participant allowlist check
├── ConsentStatusFunction.java    ds:consentStatus — HTTP call to ds-connector consent check
└── ContractRequiredFunction.java ds:contractRequired — bilateral contract gate (currently pass-through)
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new ODRL constraint | Create new `*Function.java`, register in `DataspacesExtension.java` |
| Change access scope logic | `AccessScopeFunction.java` |
| Change consent check logic | `ConsentStatusFunction.java` |
| Update EDC dependency version | `build.gradle.kts` |

## Constraint functions

### AccessScopeFunction (`ds:accessScope`)

Evaluates whether the requesting participant has the required scope. Loads `participants.yaml` from a path configured via `ds.participants.yaml.path` EDC property. Checks if the participant's `allowed_scopes` list contains the required scope value.

**Known limitation**: re-parses `participants.yaml` on every call (no TTL cache).

### ConsentStatusFunction (`ds:consentStatus`)

Makes an HTTP GET to `ds-connector /internal/consent/check` to verify active consent for the requesting participant. The connector URL is configured via `ds.connector.internal.url` EDC property.

**Known limitation**: no retry or circuit-breaker on the HTTP call.

### ContractRequiredFunction (`ds:contractRequired`)

Placeholder for bilateral contract gate. Currently always returns `true` (pass-through).

## Coding conventions

- Each function implements `AtomicConstraintFunction<Permission>` from EDC SPI
- Functions are registered in `DataspacesExtension.initialize()` for the `NEGOTIATION` scope
- Use `Monitor` (EDC's logging abstraction) for logging, not SLF4J directly
- HTTP calls use OkHttp (EDC's standard HTTP client)
- The `ds:` namespace prefix corresponds to the dataspace's custom ODRL vocabulary

## Build

```bash
# From repo root:
gradle :edc-extensions:build      # compile + test
gradle :edc-connector:shadowJar   # build fat JAR including extensions
```

## Integration points

- **Compiled into**: edc-connector fat JAR
- **Calls at runtime**: ds-connector `/internal/consent/check` endpoint
- **Reads at runtime**: `governance/participants.yaml` file
- **Registered by**: EDC ServiceExtension SPI
