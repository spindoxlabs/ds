# caddy

A single `Caddyfile`, bind-mounted into the stock `caddy:2-alpine` image. No code, no
Dockerfile, no port of its own beyond `:80`.

It is the **development edge**, and development only. There is no Helm counterpart: in
Kubernetes its jobs are done by Ingress rules and the oauth2-proxy chart.

## Role in the blueprint

| | |
|---|---|
| Relates to | [DSSC · Identity & Attestation Management](../blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) — `did:web` resolution is the part with a requirement behind it |
| Rules it supports | [Rulebook · Participation and trust](../rulebook/participation.md) |

## What it does

Four jobs, on one listener, separated by `Host` header alone.

**Resolves `did:web`.** Every `*.dataspaces.localhost` host serves `/.well-known/did.json`,
rewritten onto the identity registry's `/dids/did:web:{host}/did.json`. This is the single
most load-bearing thing in the file — a participant *is* its DID document.

**Fronts Keycloak and oauth2-proxy on stable hostnames**, so the browser-facing issuer URL and
the OIDC redirect URL are the same string from a browser, from a host process and from inside
the compose network.

**Fans a few `/api/*` prefixes out to per-service ports**, so a page served from the portal
host can reach the connector without CORS.

**Puts the portal behind an auth wall** — an oauth2-proxy `forward_auth` pre-flight, with the
client's own `X-Auth-Request-*` headers stripped first.

## Why port 80

Not a preference. A portless `did:web` DID — and every DID here is portless — resolves to
`http://<host>/.well-known/did.json`, and no resolver will try another port. A gateway on any
other port cannot serve the documents its participants are identified by.

`*.dataspaces.localhost` resolves to the Caddy container through **Docker network aliases**
declared on the compose service, so container-to-container requests for those names land here
too — which is what lets oauth2-proxy perform OIDC discovery against the browser-facing issuer.

## The sites

| Host | Routes |
|---|---|
| `*.dataspaces.localhost` | `/.well-known/did.json` → identity registry. Everything else 404 |
| `keycloak.dataspaces.localhost` | everything → Keycloak on `172.17.0.1:9080` |
| `sso.dataspaces.localhost` | `/oauth2/*` → oauth2-proxy; everything else redirects to the portal host |
| `consumer.dataspaces.localhost` | its own DID document, plus `/api/connector/*` → `:31001` and `/api/provenance/*` → `:31000` |
| `portal.dataspaces.localhost` | the browser surface — see below |

The wildcard is matched **last**, so a specific host always wins. That is why
`consumer.dataspaces.localhost` — which is both a gateway host and a participant DID — repeats
the DID handler inside its own block; without it the consumer's DID document would 404 while
every other participant resolved.

### The portal host

Five header deletions run on *every* request before any routing decision:

```
request_header -X-Auth-Request-User
request_header -X-Auth-Request-Email
request_header -X-Auth-Request-Groups
request_header -X-Auth-Request-Access-Token
request_header -X-Auth-Request-Preferred-Username
```

The portal builds its entire session from those headers, so this strip **is** the
authentication boundary, not a hardening extra. A client that could set them could be anyone.

Then, inside a `route` (so the order is the written order, first match wins):

| Path | Auth? | Goes to |
|---|---|---|
| `/oauth2/sign_out` | no | Keycloak's `end_session`, which redirects back to the proxy |
| `/oauth2/*` | no | oauth2-proxy — the callback carries a code, not a session |
| `/join*` | **no** | the portal — the applicant has no account by definition |
| `/metrics*` | **no** | the portal |
| `/api/connector/*` | no | `:30001`, prefix stripped |
| `/api/provenance/*` | no | `:30000`, prefix stripped |
| `/api/catalog/*` | no | `:30003`, prefix stripped |
| `/api/datasets/*` | no | `:30002`, prefix stripped |
| everything else | **yes** | the `(auth)` snippet, then the portal on `:30004` |

### The `(auth)` snippet

```
forward_auth oauth2-proxy:4180 {
    uri /oauth2/auth
    copy_headers X-Auth-Request-User X-Auth-Request-Email X-Auth-Request-Groups \
                 X-Auth-Request-Access-Token Authorization
    @unauthenticated status 401
    handle_response @unauthenticated {
        redir * http://sso.dataspaces.localhost/oauth2/sign_in?rd={scheme}://{hostport}{uri}
    }
}
```

`copy_headers` is the other half of the boundary: those names are re-added from the *auth
response*, after having been stripped from the client's request. A header the portal reads
that is not in this list can only have arrived from the client.

## A signed-out request, traced

1. `GET http://portal.dataspaces.localhost/catalog` arrives on `:80`.
2. The five `X-Auth-Request-*` deletions run.
3. `/catalog` matches none of the carve-outs — note it is *not* `/api/catalog/*` — so it
   reaches the final handler and `import auth` runs.
4. Caddy sub-requests `oauth2-proxy:4180/oauth2/auth`. No session cookie ⇒ `401`.
5. Caddy answers `302` to `sso.dataspaces.localhost/oauth2/sign_in?rd=…`.
6. The proxy redirects to Keycloak, which resolves back through Caddy.
7. After login, Keycloak redirects to `/oauth2/callback` on the `sso` host — outside the auth
   wall, which is why `/oauth2/*` must not be behind `forward_auth`.
8. The proxy sets its cookie and redirects to `rd`. The request replays, this time with a
   `200` from the sub-request, and `copy_headers` writes the identity onto the request before
   it reaches the portal.

## Configuration

None. Every value in the file is a literal — no environment variables, no external files, no
TLS block (each site address carries an explicit `http://`, so automatic HTTPS is skipped) and
no logging directives.

| Upstream | Reaches |
|---|---|
| `identity-registry:30005` | the identity registry, **by compose service name** |
| `oauth2-proxy:4180` | the session proxy, by service name (it publishes no host port) |
| `172.17.0.1:9080` | Keycloak |
| `172.17.0.1:30001` / `:31001` | connector, provider / consumer |
| `172.17.0.1:30000` / `:31000` | provenance, provider / consumer |
| `172.17.0.1:30003` | federated catalogue |
| `172.17.0.1:30002` | dataset API |
| `172.17.0.1:30004` | portal |

Everything except the DID routes dials `172.17.0.1`, the Docker host gateway. That is what
makes the same Caddyfile correct whether a service is a container publishing that port or a
host process holding it — which is exactly what `task dev:*` swaps between.

The two DID routes are the exception, and the tradeoff is deliberate: they use container DNS,
so under `task dev:*`, where the identity-registry container is stopped and replaced by a host
process, DID resolution through Caddy does not work.

## Running it

Started with the shared infrastructure — `task infra:start`, or any of the `docker:*` /
`dev:*` lifecycle tasks. It is one of the four containers `dev:*` leaves running.

To check a routing change without a restart:

```sh
docker run --rm -v "$PWD/services/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2-alpine caddy adapt --config /etc/caddy/Caddyfile
```
