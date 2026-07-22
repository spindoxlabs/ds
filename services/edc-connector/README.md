# edc-connector

Gradle project that builds a self-contained EDC connector fat JAR with DCP (Dataspace Credential Protocol) support and the custom `edc-extensions` ODRL functions bundled together.

---

## Purpose

The MVP phases used the EDC samples connector JAR from the `edc-samples` repository. That connector lacks DCP identity verification — it accepts any participant ID without proof.

This project replaces that connector with one that:

- Includes `controlplane-dcp-bom` — activates `IdentityAndTrustExtension`, `VerifiablePresentationVerifier`, and the DCP protocol handler
- Adds `identity-did-web` for resolving `did:web:` DID documents during VP verification
- Bundles `edc-extensions` so the profile-namespaced ODRL constraint functions (`Membership`, `ConsentStatus`) are always present
- Packages everything as a single fat JAR via the Shadow plugin

---

## Build

Requires Java 21 and Gradle 8.x (or use the Gradle wrapper if added):

```bash
./gradlew :edc-connector:shadowJar
```

Output: `edc-connector/build/libs/connector.jar`

Both provider and consumer use the same JAR — the participant identity is determined entirely by the `.properties` file passed at startup via `-Dedc.fs.config`.

---

## Docker

The `Dockerfile` performs a multi-stage build:

1. Builder stage (`gradle:8.12-jdk21`) — runs `shadowJar` with access to both `edc-extensions/` and `edc-connector/` source
2. Runtime stage (`eclipse-temurin:21-jre-alpine`) — copies the single JAR; minimal image footprint

```bash
# Build the image (from repo root)
docker build -f edc-connector/Dockerfile -t ds-edc-connector:local .
```

The root `docker-compose.provider.yml` and `docker-compose.consumer.yml` build this image automatically for the `edc-provider` and `edc-consumer` services.

---

## Dependencies

EDC version: `0.10.1`

- `org.eclipse.edc:controlplane-dcp-bom` — DCP control plane including identity/trust and VP verification
- `org.eclipse.edc:dataplane-base-bom` — HTTP data plane for EDR-based transfers
- `org.eclipse.edc:filesystem-configuration-bom` — reads `.properties` files as EDC configuration
- `org.eclipse.edc:identity-did-web` — `did:web:` resolver used during counterparty VP verification
- `project(":edc-extensions")` — custom ODRL constraint functions for profile-namespaced vocabulary

---

## DCP identity flow

When connector A (consumer) initiates DSP negotiation with connector B (provider):

1. A's EDC calls `edc.iam.sts.oauth.token.url` (the `ds-sts` service) with a `client_credentials` grant to obtain a Self-Issued token
2. A presents the SI token in the DSP negotiation request
3. B's EDC resolves A's DID document via `did:web:` and verifies the SI token signature
4. B's EDC calls A's Credential Service (`edc.credential.service.url`) to retrieve A's Verifiable Presentation
5. B's EDC verifies the `MembershipCredential` in the VP against the trusted issuer DID (`edc.iam.trustedissuer.0.id`)
6. If all checks pass, the ODRL policy constraints are evaluated (including `AccessScopeFunction`)

---

## Related configuration

EDC properties files for this connector are at `services/connector/config/provider.properties` and `consumer.properties`. Key DCP properties:

- `edc.participant.id` — participant DID URI
- `edc.iam.issuer.id` — same DID URI (used in VP assertions)
- `edc.iam.sts.oauth.token.url` — STS token endpoint
- `edc.iam.trustedissuer.0.id` — trust anchor DID
- `edc.credential.service.url` — VC wallet endpoint
- `edc.vault.fs.file` — filesystem vault file containing secrets
- `edc.iam.did.web.use.https` — set to `false` for Docker-internal HTTP resolution

---

## Gradle project structure

The root `settings.gradle.kts` includes both `:edc-extensions` and `:edc-connector`. The `:edc-connector` build depends on `:edc-extensions` as a `runtimeOnly` dependency so the custom functions are included in the fat JAR.

```
dataspaces/
├── settings.gradle.kts          includes :edc-extensions, :edc-connector
├── build.gradle.kts             root — repositories only
├── edc-extensions/
│   └── build.gradle.kts         library JAR
└── edc-connector/
    └── build.gradle.kts         shadow fat JAR
```
