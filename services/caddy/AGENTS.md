# caddy — Agent Guide

## Service identity

- **Role**: Reverse proxy, local HTTPS termination, DID document hosting
- **Type**: Configuration-only (no application code)
- **Ports**: 80, 443
- **Image**: `caddy:2-alpine`

## File layout

```
caddy/
├── Caddyfile              Routing config for all services
└── did/
    ├── provider/did.json  DID document for did:web:provider.dataspaces.localhost
    ├── consumer/did.json  DID document for did:web:consumer.dataspaces.localhost
    └── trust-anchor/did.json  DID document for did:web:trust-anchor.dataspaces.localhost
```

## Caddyfile routing

| Domain | Target | Purpose |
|--------|--------|---------|
| `provenance.dataspaces.localhost` | `host.docker.internal:30000` | ds-provenance |
| `connector.dataspaces.localhost` | `host.docker.internal:30001` | ds-connector |
| `dataset-api.dataspaces.localhost` | `host.docker.internal:30002` | Dataset API adapter |
| `federated-catalog.dataspaces.localhost` | `host.docker.internal:30003` | ds-federated-catalog |
| `portal.dataspaces.localhost` | `host.docker.internal:30004` | ds-portal |
| `provider.dataspaces.localhost` | varies by path | EDC provider + DID doc |
| `consumer.dataspaces.localhost` | varies by path | EDC consumer + DID doc |
| `trust-anchor.dataspaces.localhost` | — | DID doc only |
| `sts-provider.dataspaces.localhost` | `host.docker.internal:38080` | STS provider |
| `sts-consumer.dataspaces.localhost` | `host.docker.internal:38081` | STS consumer |
| `vc-wallet-provider.dataspaces.localhost` | `host.docker.internal:38082` | VC wallet provider |
| `vc-wallet-consumer.dataspaces.localhost` | `host.docker.internal:38083` | VC wallet consumer |
| `keycloak.dataspaces.localhost` | `host.docker.internal:8080` | Keycloak auth |

## DID document hosting

Each participant domain serves `/.well-known/did.json` by rewriting the path to the static DID document file. The DID documents contain EC P-256 `JsonWebKey2020` verification methods.

Public keys in DID documents are updated by `scripts/gen-keys.sh`.

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new service route | `Caddyfile` |
| Add a new participant identity | `Caddyfile` (domain + DID rewrite), `did/<name>/did.json` |
| Change TLS settings | `Caddyfile` (tls directive per domain) |

## Notes

- All `*.dataspaces.localhost` domains use Caddy's local CA for TLS
- Trust the CA with `task proxy:trust-ca` to avoid browser warnings
- Add hostnames with `task proxy:hosts` (writes to `/etc/hosts`)
- Caddy runs as part of root `docker-compose.yml`, not per-service
