# edc-connector — Agent Guide

## Service identity

- **Role**: Eclipse Dataspace Connector fat JAR build — DCP-enabled EDC v0.16.0
- **Language**: Java 21, Gradle (Shadow plugin)
- **Type**: Build project (produces a fat JAR, no application code)
- **Ports**: Provider 19191-19291, Consumer 29191-29291

## Source layout

```
edc-connector/
├── build.gradle.kts      Shadow JAR configuration + EDC BOM dependencies
├── Dockerfile            Multi-stage build (Gradle 8.12/JDK21 → Alpine JRE21)
└── Dockerfile.base       Dependency cache base image (ds-edc-base:0.16.0)
```

Configuration lives in `services/connector/config/`:

```
config/
├── provider.properties       EDC properties for provider connector
├── consumer.properties       EDC properties for consumer connector
├── provider-key.json         EC P-256 private key (JWK)
├── consumer-key.json         EC P-256 private key (JWK)
├── provider-vault.properties Vault secrets
└── consumer-vault.properties Vault secrets
```

## EDC modules included

| Module | Purpose |
|--------|---------|
| `controlplane-dcp-bom` | DCP identity/trust + VP verification |
| `dataplane-base-bom` | HTTP data plane for EDR-gated transfers |
| `configuration-filesystem` | Reads `.properties` config files |
| `identity-did-web` | `did:web:` DID resolver |
| `:edc-extensions` | Custom `ds:` ODRL constraint functions |

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add/remove EDC modules | `build.gradle.kts` (dependencies block) |
| Change EDC version | `build.gradle.kts` (edcVersion variable) |
| Change connector properties | `services/connector/config/*.properties` |
| Rebuild base image | `Dockerfile.base` |

## Build commands

```bash
# Build dependency cache base image (once per EDC version bump)
task edc:base

# Build fat JAR (requires Java 21 + Gradle on host)
task edc:build
# or: gradle :edc-connector:shadowJar --no-daemon

# Build Docker image (requires ds-edc-base:0.16.0)
task edc:docker
```

## EDC port scheme

| Port | Provider | Consumer | Purpose |
|------|----------|----------|---------|
| x9191 | 19191 | 29191 | Management API |
| x9193 | 19193 | 29193 | Management API (alt) |
| x9194 | 19194 | 29194 | DSP Protocol |
| x9195 | 19195 | 29195 | Version/health |
| x9291 | 19291 | 29291 | Public data plane |

## Integration points

- **Includes**: edc-extensions (compiled as project dependency)
- **Called by**: ds-connector via EDC Management API
- **Calls**: STS for token issuance, VC-wallet for credential queries, ds-connector for constraint evaluation
- **Network**: runs on `dataspaces` Docker network, launched by `services/connector/docker-compose.yml`
