# oauth2-proxy

One config file for the upstream `quay.io/oauth2-proxy/oauth2-proxy:v7.11.0` image. It is
the deployment's **single human login surface**: it runs the OIDC authorization-code flow
against the `dataspaces` realm as the confidential client `oauth2_proxy`, holds the browser
session in a cookie, and answers a reverse proxy's sub-request with `202` plus
`X-Auth-Request-*` headers, or `401`.

It proxies no traffic (`upstreams = [ "static://200" ]`). The reverse proxy in front does
the routing — Caddy `forward_auth` in compose, ingress-nginx `auth-url` in Kubernetes.
**No published host port**; it is reachable only as `oauth2-proxy:4180` on the compose network.

## References

| | |
|---|---|
| Requirements | [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/oauth2-proxy.md](../../docs/services/oauth2-proxy.md) — renders the configuration in full |

## What this component is load-bearing for

The portal is **not** an OIDC client. It builds its whole session from the access token this
proxy forwards. That design is only safe if the thing in front does two jobs: authenticate,
**and** make a client-supplied `X-Auth-Request-*` unable to reach the portal.

- In compose, the strip is in the Caddyfile. In Kubernetes it is
  `nginx.ingress.kubernetes.io/auth-response-headers` — each listed name becomes a
  `proxy_set_header` from the auth response, overwriting the client's.
- **A header the portal reads that is not in that list is forwarded from the client
  verbatim.** Keep the list in step with `bearerFrom` and `buildSession`. `Authorization`
  is in it for exactly that reason.
- Disabling the proxy does **not** fall back to a portal login — there is none. It leaves
  the portal open with client-controlled identity headers, and the portal mints
  `X-Subject-Id` + `X-User-VC` server-side from that session, so a forged header reaches the
  consent plane.

## When editing the config

- Every URL is portless: the gateway owns `:80` — see the traps in `services/caddy/AGENTS.md`.
- **`cookie_secret` and `client_secret` are not in the config file, in either mode.** Both
  arrive as `OAUTH2_PROXY_<OPTION>` environment variables — from `docker-compose.yml` (dev
  defaults in `.env.local`) and from a Secret in the chart (`secrets.cookieSecret` on
  `ds-oauth2-proxy`). A known cookie secret means forgeable sessions for every human in the
  deployment, and while they were literals here no deployment could override either without
  editing a tracked file. Do not re-add them: `libs/ds-e2e/tests/test_oauth2_proxy_secrets.py`
  checks both files and both modes.
- The compose and Kubernetes forms of this config differ in more than one place. If you
  change one, check the other — `helm/charts/ds-oauth2-proxy/templates/configmap.yaml`.
