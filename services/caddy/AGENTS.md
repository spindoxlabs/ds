# caddy

One `Caddyfile`, bind-mounted into `caddy:2-alpine`. The **dev** edge, and dev only — there
is no Helm counterpart; in-cluster its jobs are done by Ingress rules and the oauth2-proxy
chart.

Five site blocks, **all on `:80`**, separated by Host header alone:
`*.dataspaces.localhost` (DID resolution), `keycloak.…`, `sso.…`, `consumer.…` and
`portal.…`.

## References

| | |
|---|---|
| Requirements | [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) — `did:web` resolution is the part with a requirement behind it |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/caddy.md](../../docs/services/caddy.md) · [docs/development/compose-topology.md](../../docs/development/compose-topology.md) |

## Caddy is the DID router

1. EDC resolves `did:web:rec.dataspaces.localhost` by fetching
   `http://rec.dataspaces.localhost/.well-known/did.json`.
2. `*.dataspaces.localhost` resolves to the Caddy container through **Docker network
   aliases** declared on the caddy service; from the host, the `.localhost` TLD resolves to
   loopback and compose publishes `80:80`.
3. Caddy rewrites to `/dids/did:web:{host}/did.json` and proxies to the identity-registry.

**This is why the gateway owns `:80` and nothing else.** A portless DID — and every DID here
is portless — resolves on port 80; no resolver tries another. When the gateway lived on
`:9010`/`:9000`, host-side `did:web` resolution could not work at all and every host-run EDC
silently took the demo identity fallback. Moving a gateway port back would reintroduce
exactly that.

Under `task dev:start` the identity-registry runs on the host, so the `identity-registry`
service name in this block does not resolve and the DID handlers 502 — the documented dev
tradeoff, guarded out of production by `task secrets:check`.

If another stack on the machine wants `:80`, front both with a host-level proxy that routes
by hostname. Do not move this listener.

## The `(auth)` snippet — three things that bite

Do not simplify any of these without reproducing the failure first:

1. **`/oauth2/sign_out` is intercepted before the generic `/oauth2/*`.** Inside a `route` the
   first matching `handle` wins, so the generic one shadows it and only the *proxy* cookie is
   cleared — Keycloak's SSO session survives and re-authenticates silently, so sign-out
   appears to do nothing.
2. **`/oauth2/*` is excluded from the pre-flight.** sign_in and callback must reach the proxy
   directly; running `forward_auth` on the callback checks for a session that does not exist yet.
3. **Every URL is portless, and must stay that way.** `redirect_url`,
   `post_logout_redirect_uri` and oauth2-proxy's `whitelist_domains` all match on `:80`
   because a bare domain in the whitelist matches the default port only. Reintroduce a
   gateway port in one URL and not the others and the symptom is a blank page after a
   *successful* login rather than an error.

Client-supplied `X-Auth-Request-*` headers are stripped on the portal host. A client must
never be able to assert its own identity, even though every service re-verifies the JWT.

## Rules

- Gateway upstreams use `172.17.0.1`. The DID handlers use Docker DNS because they serve
  container-to-container traffic — which means they break under `task dev:start`, where that
  container is stopped.
- **A host with its own site block does not fall through to the `*` wildcard.** Caddy picks
  the most specific host, full stop. `third-party.dataspaces.localhost` is both a gateway host
  and a participant DID, so its block repeats the `/.well-known/did.json` handler. Add a
  block for any other DID-bearing host and it must repeat it too.
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
