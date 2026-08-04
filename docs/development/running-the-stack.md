# Running the stack

Everything is driven from the root `Taskfile.yml`. `task --list-all` is the complete list; this
page covers the lifecycle.

## The two modes

There are two ways to run the platform, and the difference is not cosmetic.

| | `task docker:*` | `task dev:*` |
|---|---|---|
| Where the services run | all in containers | containers come up first, then ten of them are **stopped and replaced by host processes** in a tmux session named `ds` |
| Hot reload | no | yes — uvicorn `--reload`, Vite dev server, a JVM watch loop for each EDC |
| Exercises Dockerfiles, compose env, dependency sets | **yes** | **no**, for the replaced services |
| Speed | slow | fast |

```bash
task docker:restart        # everything in containers
task dev:restart           # containers, then hot-reload services in tmux
task status                # what is running
```

Both restart families take `BUILD=false` to reuse existing images.

!!! warning "Ask which mode before restarting somebody else's stack"
    `dev:*` replaces ~12 services with host processes that read `.env.local` through the
    Taskfile and **never see the compose `environment:` block**. A change to a `Dockerfile`, a
    compose environment block, a `pyproject.toml` dependency or a `build.gradle.kts` is **not
    verified** by `dev:*`.

    The usual sequence for a substantial change: `dev:restart` to find logic bugs cheaply, then
    `docker:restart` to prove the container path.

### What `dev:*` leaves in containers

Four long-running containers survive: **caddy, postgres, keycloak, oauth2-proxy**. Everything
else — identity-registry, both connectors, both provenance instances, the dataset API mock, the
federated catalogue, the portal and both EDCs — becomes a host process in its own tmux window.

The one-shot containers (database creation, migrations, the Keycloak syncs, the identity
bootstrap) still run during the container phase and exit.

### What `dev:*` breaks, on purpose

The Caddyfile resolves `did:web` documents through the **compose service name**
`identity-registry:30005`. With that container stopped, the name does not resolve, so
in-network DID resolution does not work in `dev` mode. A host-run EDC falls back to the demo
identity extension, which is exactly what `DS_DEMO_IDENTITY_ENABLED` is for and exactly why it
is dev-only.

## Startup order

Both families run the same sequence:

```
infra:start          shared infrastructure: caddy, postgres, keycloak, oauth2-proxy,
                     the identity registry, and the Keycloak syncs
identity:bootstrap   the trust anchor, the owners, the agreements, and one
                     single-use enrolment code per participant
rec:start       the REC's stack — its registry generates its own key and
                     enrols — then wait for its connector, then POST /provider/sync
grid-operator:start  the DSO's stack, the same way. **A second provider**, and one
                     with no members: `D-54`, `DID-15`
third-party:start       the third party's stack, which buys from both
identity:users       the dev users' credentials, delivered to the participants
                     that hold them
```

**`identity:users` is last and has to be.** A person's credential is delivered to the
organisation that holds it (`DID-11`), and that organisation's DID document — with the
`CredentialService` entry the anchor delivers to — does not exist until it has enrolled. Running
it early is not corrupting: the credentials are issued and the delivery is reported as failed,
which is the state a re-run repairs.

`POST /provider/sync` is part of *starting*, not of building — it is what pushes the
governance-derived assets and policies into the provider EDC. Without it the catalogue is
empty.

The provider and consumer compose files declare the `dataspaces` network as **external**, so
`infra:start` must run first and the root `down` is what removes it.

## Destructive operations

!!! danger "`docker:stop`, `dev:stop` and both `restart` tasks delete all database state"
    They end with `docker compose down -v` on the root file, and the root file owns the only
    named volume — `postgres_data`. That volume holds **every** service database:
    `identity_registry`, both connector databases, both provenance databases, both EDC
    databases, and anything else created in that instance.

    The next start re-creates and re-migrates them and re-runs the identity bootstrap, so the
    dev stack recovers. Anything else living in that Postgres does not.

**Use `task stop` when you want to keep the data.** It is three `down` commands with no `-v`,
no port sweeping and no tmux handling.

| Task | Destroys | Confirms? |
|---|---|---|
| `task stop` | nothing | — |
| `task infra:stop` / `rec:stop` / `third-party:stop` | nothing | — |
| `task docker:stop` · `dev:stop` · `docker:restart` · `dev:restart` | **every service database** | no |
| `task db:reset` | drops and re-creates the seven service databases, then migrates | **yes** |
| `task reset-demo-state` | truncates the connector, provenance and EDC state, then re-syncs | no |
| `task e2e:clean` | drops and re-creates both EDC databases | no |
| `task keycloak:reload` | discards the Keycloak container, and with it the realm state | no |

`docker:stop` is a failsafe sweep: it kills the EDC watch loops by name, sends `C-c` to every
tmux window and kills the session, kills whatever holds the dev ports, brings all three compose
stacks down, and waits for the ports to free. It exits `0` whatever happened.

## Single-service modes

Each of these stops the corresponding container first, then runs the service on the host
against the same ports — so the rest of the stack keeps working.

| Task | Port | Debug port |
|---|---|---|
| `task identity-registry:run` / `:debug` | 30005 | 30905 |
| `task provider:connector:run` / `:debug` | 30001 | 30901 |
| `task consumer:connector:run` / `:debug` | 31001 | 31901 |
| `task provider:provenance:run` | 30000 | — |
| `task consumer:provenance:run` | 31000 | — |
| `task provider:dataset-api:run` | 30002 | — |
| `task provider:federated-catalog:run` | 30003 | — |
| `task rec:portal:run` | 30004 | — |

The portal needs `task -d services/portal setup` (an `npm ci`) once before its first run.

### The EDCs

| Task | Effect |
|---|---|
| `task edc:build` | build `connector.jar` in a Gradle container |
| `task edc:docker` | build the EDC image |
| `task edc:restart` | build, rebuild the image, recreate both EDC containers, wait for health |
| `task edc-rec:run` / `edc-third-party:run` | run the JAR on the host |
| `task edc-rec:watch` / `edc-third-party:watch` | the same JVM under a supervision loop that restarts on JAR change |
| `task edc:watch-build` | continuous Gradle build — pairs with the two watch tasks |

`task edc:restart` is the only mode that uses `--force-recreate --no-deps`, so it recreates the
two EDC containers without touching their dependency chain.

### Keycloak

```bash
task keycloak:reload    # discard the container, re-import the dev realm, re-run both syncs
```

Under `start-dev` Keycloak keeps its realm state in the container filesystem, so removing the
container is what resets it.

## The real dataset API

`docker-compose.dataset-api.yml` builds the real dataset-api and REC registry from sibling
checkouts outside this repository. **No task starts it** — run it by hand:

```bash
docker compose -f docker-compose.dataset-api.yml up -d
```

It declares its own compose project, so `task docker:stop` does not touch it.

It binds host **30002**, which is also the mock's default. The committed `.env.local` resolves
the collision by setting `DATASET_API_MOCK_PORT=30022`, moving the mock out of the way — so in
the default configuration 30002 belongs to the real service, and starting the mock alone
requires unsetting that variable.

`./services/dataset-api-mock/fixtures/seed.sh` brings that stack up and seeds it with the
fixtures the end-to-end flows expect.

## Testing

Four layers. Each proves something the others cannot.

| Layer | Command | Proves |
|---|---|---|
| **Unit** | `task -d <unit> test` | logic, in isolation |
| **Local stack** | `task dev:restart` | the code works against real dependencies, with hot reload |
| **Docker end-to-end** | `task docker:restart` then `task e2e:all` | the images, the compose environment and the startup order work |
| **Portal UI** | `task -d services/portal test:ui` | Playwright journeys against the running stack |

The third layer must pass before the results of the second mean much: `ds-e2e` and Playwright
address `172.17.0.1` and the Caddy domains, so they neither know nor care whether a given
service is a container or a host process.

**Read the database directly when a result is ambiguous.** One Postgres, one database per
service:

```bash
psql -h 172.17.0.1 -p 35432 -U postgres -l                    # list the service databases
psql -h 172.17.0.1 -p 35432 -U postgres -d connector_rec -c '…'
```

An assertion about consent, agreement or provenance state is worth more checked against the row
than against an API response.

## Two things that bite

**`docker compose up -d` returns success even when an init container exited non-zero.** After a
restart, check `docker ps -a` for non-zero `Exited` one-shot containers before trusting a
result. The database-creation and migration containers are the ones to look at.

**A first build on a clean machine needs the EDC base image.** `task edc:ensure-base` builds
it; the provider and consumer start tasks depend on it, but a bare `task build` does not, so
run `task edc:base` once if a build fails on a missing `ds-edc-base` tag.
