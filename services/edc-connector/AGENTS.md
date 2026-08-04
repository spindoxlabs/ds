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
| Change the EDC version | `gradle.properties` `edcVersion` — **and** the copies `BuildConsistencyTest` names, which it will fail on until they agree |
| Change connector runtime settings | `services/connector/config/{rec,third-party,grid-operator}.properties` |
| Add a test | `src/test/java/dataspaces/edc/connector/` · `task -d services/edc-connector test` |

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

`rec` 19xxx · `third-party` 29xxx · `grid-operator` 39xxx.

| Suffix | Context | Published |
|---|---|---|
| x9191 | default — `/api/check/health` | no; the compose healthcheck runs inside the container |
| x9192 | control | **never** — see below |
| x9193 | Management API | yes in compose, ClusterIP-only under Helm |
| x9194 | DSP protocol (`/protocol/2025-1`) | yes — the only public one |

**Do not add a `public` or `version` context.** Both used to be configured, published by
compose, given container/Service/NetworkPolicy ports, and `/public` was an Ingress path — and
no packaged module registers a resource on either. A configured context binds a port and 404s,
so everything routing to it looks wired and is not; that is how the Helm EDR base URL came to
name a dead endpoint. `RuntimeContractTest` fails if one is configured again.

**`web.http.management.auth.type=tokenbased` is required, not just `auth.key`.** EDC installs
an authentication filter only for contexts that declare a type, so the key alone protects
nothing.

**`web.http.control.auth.type=tokenbased` is set, and it must stay set.** Until it was,
`GET /control/v1/dataplanes` answered 200 with the full data-plane registry to anything on the
Docker network. Its registrants (`ControlPlaneApiExtension`, `DataPlaneSignalingApiExtension`,
`DataplaneSelectorControlApiExtension`) are this runtime talking to itself, and because the
data-plane client is **embedded** the calls never cross the port — so the filter costs nothing.
Verified by running the full consumer-pull flow with it on.

This is safe *only while the data plane shares the runtime*. Split it out and the signalling
becomes real HTTP, and the only `ControlClientAuthenticationProvider` packaged here is the
**no-op default** from `CoreDefaultServicesExtension` — it sends no headers, so every signal
would 401. Package a real provider in the same change, or transfers stop.

## What this unit can get wrong, and how it is caught

It has no source, so its risk is the *assembly*: which modules are packaged, and whether the
properties files configure things the result reads. Both fail silently — EDC ignores an
unknown setting without a word. `src/test/java/.../RuntimeContractTest.java` reads the built
JAR's constant pools and fails when a configured context has no registrant or a setting has no
reader. Run it with `task -d services/edc-connector test`, or `task edc:test` for both Java
units.

## Persistence

PostgreSQL SQL stores. `SqlSchemaBootstrapperExtension` creates the tables from the JAR's
`*-schema.sql` resources at first start — **not Flyway**, which is credited in five comments
and is not on the classpath. Init containers create the databases only.

## Build

```bash
task edc:base       # dependency-cache base image, once per version bump
task edc:build      # fat JAR, via Docker, cached in data/gradle
task edc:docker     # image (requires the ds-edc-base image)
task edc:restart    # rebuild + force-recreate all three EDC containers
task edc:test       # the Java tests of both units
```

**No Gradle wrapper is committed, deliberately** — the build runs in a pinned
`gradle:8.12-jdk21` container so a checkout needs Docker and nothing else. `./gradlew` has
never worked here; anything documenting it is stale.

Both Dockerfiles copy the build descriptors individually, and `gradle.properties` is one of
them. Omit it and the image build fails several minutes in with *"Cannot get non-null property
'edcVersion'"* — while `task edc:build`, which mounts the whole repo, keeps working.
