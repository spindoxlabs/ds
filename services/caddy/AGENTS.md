# caddy — Agent Guide

## Service identity

- **Role**: HTTP reverse proxy — gateway routing for provider (:9010) and consumer (:9000) stacks, Keycloak proxy
- **Type**: Configuration-only (no application code)
- **Ports**: 9000 (consumer gateway), 9010 (provider gateway)
- **Image**: `caddy:2-alpine`

## File layout

```
caddy/
└── Caddyfile              Routing config for all services
```

## Caddyfile routing

Three site blocks:

| Site block | Path | Upstream | Purpose |
|-----------|------|----------|---------|
| `keycloak.dataspaces.localhost:9010` | `/*` | `172.17.0.1:8080` | Keycloak OIDC |
| `consumer.dataspaces.localhost:9000` | `/api/connector/*` | `172.17.0.1:31001` | Consumer connector API |
| | `/api/provenance/*` | `172.17.0.1:31000` | Consumer provenance API |
| `portal.dataspaces.localhost:9010` | `/api/connector/*` | `172.17.0.1:30001` | Provider connector API |
| | `/api/provenance/*` | `172.17.0.1:30000` | Provider provenance API |
| | `/api/catalog/*` | `172.17.0.1:30003` | Federated catalog API |
| | `/api/datasets/*` | `172.17.0.1:30002` | Dataset API |
| | `/*` (catch-all) | `172.17.0.1:30004` | Portal SvelteKit app |

All upstreams use `172.17.0.1` (Docker host-gateway). `handle_path` strips the matched prefix before proxying.

## DID document hosting

DID documents (`/.well-known/did.json`) are served dynamically by the identity-registry service, not from static files. Caddy is not involved in DID routing — EDC resolves `did:web:` DIDs by fetching directly from the identity-registry via the `*.dataspaces.localhost` hostname which resolves to `127.0.0.1` via `/etc/hosts`.

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new service route | `Caddyfile` |
| Add a new participant gateway | `Caddyfile` (new site block) |

## Notes

- All `*.dataspaces.localhost` domains must be in `/etc/hosts` — run `task proxy:hosts`
- Caddy runs as part of root `docker-compose.yml`, not per-service
- Dev setup uses plain HTTP (no TLS) — ports 9000 and 9010
- Upstream targets use `172.17.0.1`, never `localhost` or `host.docker.internal`
