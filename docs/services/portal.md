# ds-portal

The web front end. Every human-facing surface in the platform is here: the dataset catalogue,
a data subject's consent and "my data" screens, the provider console, the consumer
access-request console, the operator onboarding console, and a public organisation-application
form.

It is a **rendering and gating layer**, nothing more. It has no database, issues no
credentials, and makes every upstream call from the Node server — the browser never talks to
the connector, provenance or the catalogue directly.

It is also **not an OIDC client.** [oauth2-proxy](oauth2-proxy.md), behind
[Caddy](caddy.md), owns the browser session and forwards the access token as
`X-Auth-Request-Access-Token`. The portal decodes that token per request to build a session.
The header is transport, never authority: the reverse proxy strips client-supplied copies,
and every service the portal calls re-verifies the token itself.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Cross-cutting (personal data, natural persons)](../blueprints/dssc/cross-cutting.md) · [DSSC · Publication and Discovery](../blueprints/dssc/data-value-creation-enablers/publication-and-discovery.md) |
| Rules it enforces | [Rulebook · Personal data](../rulebook/personal-data.md) · [Rulebook · Participation and trust](../rulebook/participation.md) |

## What it does

| Area | Routes | Who reaches it |
|---|---|---|
| Catalogue | `/`, `/catalog/[id]` | anyone signed in; the detail page drives negotiation |
| My data | `/my-data` | a **data subject** — sharing offers, per-dataset toggles, their own timeline |
| Consent decisions | `/consent`, `/consent/[id]` | a data subject — approve, reject, revoke a specific ask |
| Consumer console | `/consumer`, `/consumer/activity` | a **consumer user** — access requests, transfers, revocation |
| Provider console | `/provider/*` | a participant admin — assets, contracts, incoming requests, sync |
| Operator console | `/admin/*` | a platform admin — participants, onboarding, agreements, observability |
| Lineage | `/lineage/[iri]` | a provenance graph view |
| Join | `/join` | **public** — an organisation applies with an invite code |

## How it works

### Two axes of authority

Every guard reads one of two independent sources, and the distinction is the thing to
understand about this service.

| Axis | Comes from | Answers | Guards |
|---|---|---|---|
| **Keycloak groups and roles** | the access token: realm `groups` and `organization.<alias>.groups` | *may this operator act?* | `requireAdmin`, `requireProvider`, `requireGrant` |
| **Verifiable credentials** | the identity registry, resolved per session by email | *is this person a data subject / a consumer?* | `requireDataSubject`, `requireConsumer` |

They do not substitute for one another. A platform admin is **not** a data subject and cannot
reach `/my-data`; a data subject with no Keycloak group cannot reach `/provider`. That is
deliberate: consent belongs to the person, not to an administrator.

Groups are expanded into capabilities through `services/portal/src/lib/server/bundles.generated.ts`, which is
generated from [`libs/ds-auth`](libs/ds-auth.md)'s role-bundle table by
`task auth:bundles:generate`. Do not hand-edit it — a test asserts it matches a fresh render.

**All of this is UI gating.** Every backend re-verifies and re-authorises. A guard here
decides what to render, never what is permitted.

### Building a session

Per request, `hooks.server.ts`:

1. reads the bearer from `x-auth-request-access-token`, falling back to `Authorization`;
2. base64-decodes the JWT payload and rejects an expired `exp`;
3. takes the `email` claim and resolves the person against the identity registry
   (`GET /users/resolve?email=`), cached 60 s per email including negative results;
4. exposes `{ user, accessToken, userDid, userVcRoles, userVcJwsByRole, userSubjectId }`.

The registry call is the **only** one made with the portal's own service account. Everything
else forwards the signed-in user's token, or the subject's credential headers.

### Two credential styles travel outward

- **Bearer** — the user's own access token, forwarded verbatim, for operator and provider
  calls.
- **Subject credential** — `X-Subject-Id` + `X-User-VC`, selected per VC role, for
  `/consent/my*`, `/consumer/*` and `/prov/my/events`. The connector and provenance verify the
  credential themselves; no bearer is sent on these.

### Server-side rendering, with one exception

Page loads and form actions run on the server. The negotiation wizard is the exception: it
runs in the browser and drives four `+server.ts` endpoints, polling the negotiation and then
the transfer. Note that SvelteKit does **not** run `+layout.server.ts` for standalone
endpoints — a `+server.ts` route must carry its own guard or rely on the connector's.

## Configuration

Plain process environment through `$env/dynamic/private`. There is no settings class and no
prefix; each call site supplies its own fallback.

| Variable | Default | Meaning |
|---|---|---|
| `ORIGIN` | — | consumed by `adapter-node` for CSRF. Must equal the public URL |
| `OAUTH2_PROXY_BASE_URL` | `http://sso.dataspaces.localhost` | sign-in / sign-out redirect base. In the cluster this is the **portal** origin — the chart serves `/oauth2/*` there and there is no separate SSO host |
| `OAUTH2_PROXY_CLIENT_ID` | `oauth2_proxy` | the **proxy's** realm client, not `PORTAL_SERVICE_CLIENT_ID`. Named when the portal asks Keycloak to end the session; Keycloak validates the post-logout redirect URI against it (`REV-04`) |
| `CONNECTOR_URL` | `http://ds-connector:30001` | provider connector |
| `CONSUMER_CONNECTOR_URL` | `http://172.17.0.1:31001` | consumer connector, for `/consumer/*` |
| `PROVENANCE_URL` | `http://ds-provenance:30000` | events, lineage |
| `IDENTITY_REGISTRY_URL` | `http://172.17.0.1:30005` | identity resolution, onboarding console |
| `FEDERATED_CATALOG_URL` | *(none)* | unset ⇒ the federated catalogue is skipped entirely |
| `CATALOGUE_URL` | `http://172.17.0.1:30002` | the dataset API — catalogue and subject datasets |
| `CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS` | provider EDC `…/protocol/2025-1` | DSP address used when negotiating |
| `CONSUMER_DEFAULT_ASSIGNER` | `did:web:rec.dataspaces.localhost` | assigner DID on an offer |
| `KEYCLOAK_ISSUER_URL` | `http://keycloak:9080/realms/dataspaces` | realm issuer, for the portal's own client-credentials grant |
| `PORTAL_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-portal` | that service account |
| `PORT` | `30004` | set in the image |

## Stack

SvelteKit 2 on `@sveltejs/adapter-node`, Svelte 5 runes, Tailwind 4, Vite 6. The only runtime
dependencies in the image are `cytoscape` and `cytoscape-dagre`, for the lineage graph.

Conventions worth keeping:

- upstream calls live in `+page.server.ts` and `src/lib/server/*`, never in a component;
- route guards live in `services/portal/src/lib/server/auth.ts`;
- a `+server.ts` endpoint guards itself;
- any new user-facing flow gets a Playwright journey.

## Running it

| Task | Effect |
|---|---|
| `task rec:portal:run` | `vite dev` on `:30004` |
| `task -d services/portal setup` | `npm ci` — required before the first run |
| `task -d services/portal check` / `lint` | type check and lint |
| `task -d services/portal test:ui` | Playwright journeys **against an already-running stack** |
| `task auth:bundles:generate` | regenerate the role-bundle table after changing `ds-auth` |

Reach it at `http://portal.dataspaces.localhost`, not `localhost:30004` — the direct port
bypasses the auth wall and the `/api/*` proxy prefixes the footer links use.

The UI journeys log in as real dev-realm users and are chosen to separate the two authority
axes: `operator` and `provider` carry Keycloak groups, `consumer` and `subject` carry
credentials, and `dual` carries both credential roles at once.
