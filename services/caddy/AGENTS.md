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

Four site blocks:

| Site block | Path | Upstream | Purpose |
|-----------|------|----------|---------|
| `*.dataspaces.localhost:80` | `/.well-known/did.json` | `identity-registry:30005` | DID document resolution (see below). All other paths `respond 404`. |
| `keycloak.dataspaces.localhost:9010` | `/*` | `172.17.0.1:9080` | Keycloak OIDC |
| `consumer.dataspaces.localhost:9000` | `/api/connector/*` | `172.17.0.1:31001` | Consumer connector API |
| | `/api/provenance/*` | `172.17.0.1:31000` | Consumer provenance API |
| `portal.dataspaces.localhost:9010` | `/api/connector/*` | `172.17.0.1:30001` | Provider connector API |
| | `/api/provenance/*` | `172.17.0.1:30000` | Provider provenance API |
| | `/api/catalog/*` | `172.17.0.1:30003` | Federated catalog API |
| | `/api/datasets/*` | `172.17.0.1:30002` | Dataset API |
| | `/*` (catch-all) | `172.17.0.1:30004` | Portal SvelteKit app |

Gateway upstreams use `172.17.0.1` (Docker host-gateway); the DID block uses Docker DNS (`identity-registry:30005`) because it serves container-to-container traffic. `handle_path` strips the matched prefix before proxying.

Note the consumer gateway has **no catch-all** — only `/api/connector/*` and `/api/provenance/*` are routed.

## DID document hosting

**Caddy is the DID router.** `did:web:` resolution works like this:

1. EDC resolves `did:web:provider.dataspaces.localhost` by fetching `http://provider.dataspaces.localhost/.well-known/did.json`.
2. `*.dataspaces.localhost` resolves to the Caddy container via **Docker network aliases** declared on the caddy service in `docker-compose.yml` — not via `/etc/hosts`.
3. Caddy rewrites `/.well-known/did.json` → `/dids/did:web:{http.request.host}/did.json` and proxies to the identity-registry.
4. The identity-registry builds the DID document from its database.

Aliases defined today: `provider.`, `consumer.`, `trust-anchor.`, `users.dataspaces.localhost`.

**Port 80 is not published to the host** (`docker-compose.yml` publishes only 9000 and 9010), so this block is reachable only from inside the `dataspaces` network. When running EDC on the host (`task edc-provider:run`), either add `/etc/hosts` entries and publish port 80, or rely on the demo identity fallback (`DS_DEMO_IDENTITY_ENABLED=true`, dev only).

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new service route | `Caddyfile` |
| Add a new participant gateway | `Caddyfile` (new site block) |

## Notes

- Inside Docker, `*.dataspaces.localhost` resolves via network aliases — no `/etc/hosts` needed. Only host-run processes (browser, host-run EDC) need `/etc/hosts` entries.
- Caddy runs as part of root `docker-compose.yml`, not per-service
- Dev setup uses plain HTTP (no TLS) — ports 9000 and 9010. Production terminates TLS here; see `helm/AGENTS.md`.
- Gateway upstreams use `172.17.0.1`, never `localhost` or `host.docker.internal`
- There is no reload task — recreate the container after editing the Caddyfile
- No `healthcheck` is defined for caddy, and it is the sole ingress
- The Caddyfile sets no security headers, rate limits, or request-body limits — production must add them

## Security notes

- `/api/connector/*`, `/api/catalog/*` and `/api/datasets/*` proxy to services whose `/metrics` endpoint is **unauthenticated**, so `GET /api/connector/metrics` is publicly reachable through this gateway.
- The DID rewrite interpolates the request `Host` into the upstream path. The site matcher constrains it to `*.dataspaces.localhost` and Caddy normalizes the path, so traversal is not currently reachable — but loosening the matcher would make it so. Validate the label explicitly if a new domain is added.
