# ADR-0007 — Backend URLs use the Docker host gateway

**Date:** 2026-08-12
**Status:** accepted
**Extracted from:** the root agent guide. This ADR states both the rule and the reason.

## Context

Roughly twelve services can each run either as a container in a compose stack or as a
hot-reloading process on the host (`task dev:restart`). A URL that one of them uses to
reach another therefore has to be correct in four combinations: host→host, host→container,
container→host, container→container.

`localhost:<port>` is correct in exactly one of them. Inside a container it means the
container, so a service moved into Docker starts talking to itself, and the failure is a
connection refused at a plausible-looking address rather than anything that names the real
cause.

Browser-facing URLs have a second constraint that has nothing to do with the first: an
OIDC issuer, an `ORIGIN` and a callback must be the *same string* for the browser and for
the service validating it, and must survive a port changing.

## Decision

| Direction | Address |
|---|---|
| Browser-facing, OIDC issuer, `ORIGIN`, callbacks | `*.dataspaces.localhost` through Caddy on `:80` — portless, split by Host header |
| Any backend call, host↔container in either direction | `172.17.0.1:<port>` |
| Container-to-container inside one compose stack | Docker DNS service name |

**Never `localhost:<port>` for a service URL.** `172.17.0.1` is the Docker host gateway and
resolves identically from the host and from inside a container.

## Consequences

- A service can be stopped in Docker and restarted on the host, or the reverse, without
  any other configuration changing. That interchangeability is the entire purpose, and it
  is what makes the local-stack and Docker test layers comparable.
- `ds-e2e` and the Playwright journeys address `172.17.0.1` and the Caddy domains, so they
  neither know nor care whether a given service is a container or a host process. One
  suite covers both layers.
- The rule is checkable by grep, which is why it is an item on the per-change security
  checklist rather than a convention.
- It is Linux-specific: `172.17.0.1` is the default `docker0` bridge gateway. A machine
  with a non-default bridge, or Docker Desktop's `host.docker.internal`, needs the address
  overridden in `.env` rather than the rule relaxed.
- Portless browser-facing hosts mean the edge is always in the path in dev, including for
  the auth wall. That is deliberate: a flow that only works when the edge is bypassed is a
  flow nobody deploys.
