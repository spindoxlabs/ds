# edc-connector

**No source code.** A Gradle Shadow build that assembles an Eclipse EDC 0.16.0 runtime
(DCP-enabled) from upstream BOMs plus `:edc-extensions`, and a two-stage Dockerfile. One
image, deployed once per participant with its own config, database and DID.

## References

| | |
|---|---|
| Requirements | [DSSC · Data Exchange](../../docs/blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Control and Data Plane](../../docs/blueprints/dssc/control-and-data-plane.md) |
| Rules | [Rulebook · Data exchange](../../docs/rulebook/data-exchange.md) — the accepted protocols, the version pin, and the specification inventory |
| Code as committed | [docs/services/edc-connector.md](../../docs/services/edc-connector.md) |

## Where to work

| Task | File |
|---|---|
| Add or remove an EDC module | `build.gradle.kts` |
| Change the EDC version | `build.gradle.kts` `edcVersion` — **and** the four places the tag is duplicated (`Dockerfile`, `Dockerfile.base`, two Taskfile entries) |
| Change connector runtime settings | `services/connector/config/{provider,consumer}.properties` |

## Configuration: environment, never `${}` in a properties file

`services/connector/config/*.properties` is loaded by EDC's `FsConfigurationExtension`, a
plain `Properties.load()` — **no interpolation**. A `${EDC_API_KEY}` written there is stored
as that literal string, and the failure is silent wherever the value is not actually checked.

EDC *does* read the environment: `ConfigurationLoader` merges `ConfigFactory.fromEnvironment`,
converting `ENVIRONMENT_NOTATION` to `dot.notation`. So a secret-bearing or
deployment-specific setting is an env var whose name **is** the setting:

| Env var | Setting |
|---|---|
| `WEB_HTTP_MANAGEMENT_AUTH_KEY` | `web.http.management.auth.key` |
| `DS_CONNECTOR_INTERNAL_CLIENT_ID` | `ds.connector.internal.client.id` |
| `EDC_DATASOURCE_DEFAULT_PASSWORD` | `edc.datasource.default.password` |

Set those in the compose `environment:` block or from a Kubernetes Secret, and leave the
setting out of the properties file entirely.

## Ports

| Suffix | Provider / consumer | Context |
|---|---|---|
| x9191 | 19191 / 29191 | default — `/api/check/health` |
| x9193 | 19193 / 29193 | Management API |
| x9194 | 19194 / 29194 | DSP protocol (`/protocol/2025-1`) |

`x9195` (version) and `x9291` (public) are configured and published but **no packaged module
registers them** — those ports refuse connections. Tracked in `.agents/defect-per-service.md`.

**`web.http.management.auth.type=tokenbased` is required, not just `auth.key`.** EDC installs
an authentication filter only for contexts that declare a type, so the key alone protects
nothing. The same applies to the control context, which is currently unauthenticated.

## Persistence

PostgreSQL SQL stores. `SqlSchemaBootstrapperExtension` creates the tables from the JAR's
`*-schema.sql` resources at first start — **not Flyway**, which is credited in five comments
and is not on the classpath. Init containers create the databases only.

## Build

```bash
task edc:base       # dependency-cache base image, once per version bump
task edc:build      # fat JAR, via Docker, cached in data/gradle
task edc:docker     # image (requires ds-edc-base:0.16.0)
task edc:restart    # rebuild + force-recreate both containers
```

No Gradle wrapper is committed. The unit has no test sources.
