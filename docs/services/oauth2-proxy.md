# oauth2-proxy

One configuration file for the upstream `quay.io/oauth2-proxy/oauth2-proxy` image. No code, no
Dockerfile, no published port.

It is the deployment's **single human login surface**. It runs the OIDC authorization-code flow
against the `dataspaces` realm as the confidential client `oauth2_proxy`, holds the browser
session in a cookie, and answers a reverse proxy's authentication sub-request with either
`202` plus a set of `X-Auth-Request-*` headers, or `401`.

It proxies no traffic itself. The reverse proxy in front does the routing —
[Caddy](caddy.md) `forward_auth` in compose, ingress-nginx `auth-url` in Kubernetes — and calls
`/oauth2/auth` as a side-band check.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Identity & Attestation Management](../blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules it supports | [Rulebook · Participation and trust](../rulebook/participation.md) |

## Why it exists

The [portal](portal.md) is deliberately **not** an OIDC client: no client secret, no callback
registration, no session of its own. That means one login surface for the whole deployment and
one fewer client registration to negotiate with whoever owns the realm.

The cost is that the portal builds its entire session from a header, which is only safe if the
thing in front does two jobs — authenticate, **and** make a client-supplied `X-Auth-Request-*`
unable to reach the portal.

- In compose, the strip is in the Caddyfile.
- In Kubernetes it is `nginx.ingress.kubernetes.io/auth-response-headers`, where each listed
  name becomes a `proxy_set_header` from the auth response, overwriting whatever the client
  sent.

**A header the portal reads that is not in that list is forwarded from the client.** That is
the property to preserve when touching either side.

## The endpoints in play

All under `proxy_prefix = /oauth2`.

| Path | Called by |
|---|---|
| `/oauth2/auth` | the reverse proxy's sub-request — `202` or `401` |
| `/oauth2/sign_in` | Caddy's 401 handler, and the portal's own sign-in redirect |
| `/oauth2/start` | the nginx `auth-signin` annotation |
| `/oauth2/callback` | the browser, after Keycloak. Registered as the realm client's redirect URI |
| `/oauth2/sign_out` | Keycloak as `post_logout_redirect_uri`, and the portal's sign-out redirect |
| `/ping` | Kubernetes liveness and readiness probes |

## What it puts on the request

Five flags govern emission — `set_xauthrequest`, `pass_user_headers`,
`pass_authorization_header`, `set_authorization_header`, `pass_access_token` — all on.

What actually reaches the portal is decided by the reverse proxy, and only three of the headers
are read:

| Header | Read by the portal |
|---|---|
| `X-Auth-Request-Access-Token` | **yes** — the session is built from this |
| `X-Auth-Request-Email` | **yes** — fallback when the token carries no `email` claim |
| `Authorization` | **yes** — fallback when the access-token header is absent |
| `X-Auth-Request-User`, `-Groups`, `-Preferred-Username` | no |

The portal does **not** verify the token's signature: it decodes the payload and checks `exp`.
Every ds *service* the portal then calls re-verifies independently — that is a property of
those services, not of this one.

## Configuration

Two independent configurations exist for the same image and are not generated from one another:
the dev file `services/oauth2-proxy/oauth2-proxy.cfg` and the Helm ConfigMap.

| Setting | Dev | Cluster |
|---|---|---|
| `provider` | `keycloak-oidc` | same |
| `oidc_issuer_url` | `http://keycloak.dataspaces.localhost/realms/dataspaces` | `global.keycloak.issuerUrl` |
| `scope` | `openid email profile organization:*` | same — **the `organization:*` scope is required**, or no per-owner group claim is emitted |
| `client_id` | `oauth2_proxy` | `auth.clientId` |
| `client_secret` | **not in the file** — `OAUTH2_PROXY_CLIENT_SECRET`, passed by compose, defaulting to `.env.local` | env, from a Secret |
| `redirect_url` | `http://sso.dataspaces.localhost/oauth2/callback` | `https://portal.<baseDomain>/oauth2/callback` — the portal host, there is no separate SSO host |
| `cookie_secret` | **not in the file** — `OAUTH2_PROXY_COOKIE_SECRET`, same route | env, from a Secret. Must be 16, 24 or 32 bytes |
| `cookie_name` | `_oauth2_proxy_ds` | same |
| `cookie_domains` | `.dataspaces.localhost` | `.<baseDomain>` |
| `cookie_secure` | `false` | **`true`** |
| `cookie_expire` / `cookie_refresh` | `30m` / `25m` | same |
| `whitelist_domains` | the dev hosts | `.<baseDomain>` |
| `session_store_type` | `cookie` | same — so replicas need no shared store |
| `code_challenge_method` | `S256` | same |
| `skip_provider_button` | `true` | same — no interstitial, the redirect *is* the sign-in |
| `skip_jwt_bearer_tokens` | `true` | same — a request already carrying a bearer is validated against JWKS instead of being redirected |
| `upstreams` | `static://200` | same — required by the binary, unused under `forward_auth` |
| `insecure_oidc_allow_unverified_email` | `true` | **not emitted at all** |

The compose service declares no `environment:` and no `env_file:` — every value the container
sees comes from the mounted file. In Kubernetes the two secrets arrive as environment variables
and are absent from the ConfigMap.

`skip_jwt_bearer_tokens` is what lets machine callers and the e2e harness traverse the same
sites a browser does.

## The realm client

| Property | Dev | Production example |
|---|---|---|
| `publicClient` | `false` | `false` |
| `secret` | literal `oauth2_proxy` | supplied out of band |
| `standardFlowEnabled` | `true` | `true` |
| `directAccessGrantsEnabled` | **`true`** — the e2e harness gets a user token by password grant | `false` |
| `serviceAccountsEnabled` | `false` | `false` |
| `redirectUris` | the dev callback | the public callback |

The client is declared in the **realm import**, not created by the syncer. Naming it as
`oauth2_proxy_client:` in [`clients.yaml`](keycloak.md) is what makes the syncer attach an
audience mapper per service client, so a user token carries an `aud` each ds service accepts.

## The auth wall, and its carve-outs

Compose carves eight paths out of the wall on the portal host: `/oauth2/sign_out`, `/oauth2/*`,
`/join*`, `/metrics*` and the four `/api/*` prefixes. `/join` in particular **must** be public
— its visitor has no account by definition.

The Kubernetes Ingress puts `auth-url` on a single `path: /` rule, so it has no equivalent
carve-outs; reproducing them needs additional Ingress objects with narrower path rules and no
auth annotations.

## Running it

Started with the shared infrastructure. It depends on Keycloak being healthy **and** on Caddy
having started — its OIDC discovery goes through Caddy at the browser-facing issuer, so without
Caddy listening the process exits on failed discovery.

No published host port: it is reachable only as `oauth2-proxy:4180` on the compose network, and
as a ClusterIP Service in Kubernetes.
