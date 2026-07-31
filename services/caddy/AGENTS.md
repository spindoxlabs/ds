# caddy

One `Caddyfile`, bind-mounted into `caddy:2-alpine`. The **dev** edge, and dev only — there
is no Helm counterpart; in-cluster its jobs are done by Ingress rules and the oauth2-proxy
chart.

Four site blocks: `*.dataspaces.localhost:80` (DID resolution), `keycloak.…:9010`,
`sso.…:9010`, `consumer.…:9000` and `portal.…:9010`.

## References

| | |
|---|---|
| Requirements | [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) — `did:web` resolution is the part with a requirement behind it |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/caddy.md](../../docs/services/caddy.md) · [docs/development/compose-topology.md](../../docs/development/compose-topology.md) |

## Caddy is the DID router

1. EDC resolves `did:web:provider.dataspaces.localhost` by fetching
   `http://provider.dataspaces.localhost/.well-known/did.json`.
2. `*.dataspaces.localhost` resolves to the Caddy container through **Docker network
   aliases** declared on the caddy service — not `/etc/hosts`.
3. Caddy rewrites to `/dids/did:web:{host}/did.json` and proxies to the identity-registry.

Port 80 is not published, so this block is reachable only from inside the `dataspaces`
network. A host-run EDC needs `/etc/hosts` entries and a published port 80, or the demo
identity fallback (dev only).

## The `(auth)` snippet — three things that bite

Do not simplify any of these without reproducing the failure first:

1. **`/oauth2/sign_out` is intercepted before the generic `/oauth2/*`.** Inside a `route` the
   first matching `handle` wins, so the generic one shadows it and only the *proxy* cookie is
   cleared — Keycloak's SSO session survives and re-authenticates silently, so sign-out
   appears to do nothing.
2. **`/oauth2/*` is excluded from the pre-flight.** sign_in and callback must reach the proxy
   directly; running `forward_auth` on the callback checks for a session that does not exist yet.
3. **Every URL carries the gateway port.** ds does not own `:80` on a developer machine, so
   `redirect_url`, `post_logout_redirect_uri` and oauth2-proxy's `whitelist_domains` all need
   `:9010`. A bare domain in the whitelist matches the default port only, and the symptom is a
   blank page after a *successful* login rather than an error.

Client-supplied `X-Auth-Request-*` headers are stripped on the portal host. A client must
never be able to assert its own identity, even though every service re-verifies the JWT.

## Rules

- Gateway upstreams use `172.17.0.1`. The DID block uses Docker DNS because it serves
  container-to-container traffic — which means it breaks under `task dev:start`, where that
  container is stopped.
- `handle_path` strips the matched prefix before proxying. Check what the upstream's routes
  are actually mounted under before adding one.
- A page whose visitor legitimately has **no account** must be carved out of the auth wall
  (today `/join`). Behind the wall an applicant is bounced to a login form for an account
  that does not exist.
- `/api/*` is deliberately outside the wall: an unauthenticated API call must be a 401 the
  caller can act on, not a 302 to a login form it cannot complete.
- No reload task — recreate the container after editing.

Production concerns Caddy does not currently address (security headers, rate limits, body
limits, TLS) are the Ingress's job. See `helm/AGENTS.md`.
