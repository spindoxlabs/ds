# ds-portal — Agent Guide

## Service identity

- **Role**: Web frontend for all dataspace participant roles
- **Language**: TypeScript, SvelteKit 2.0, Svelte 5.0, Tailwind CSS 4.0
- **Port**: 30004 (debug: 30904)
- **URL**: `http://portal.dataspaces.localhost:9010` (via Caddy), direct `http://172.17.0.1:30004`
- **Auth**: **oauth2-proxy** in front, via Caddy `forward_auth`. The portal is *not* an
  OIDC client: it reads the access token oauth2-proxy forwards as
  `X-Auth-Request-Access-Token` and builds the session per request. The header is
  transport, never authority — Caddy strips client-supplied copies and every ds
  service re-verifies the JWT.

## Source layout

```
src/
├── routes/
│   ├── +layout.svelte           Root layout — nav bar, auth state, role-based menu
│   ├── +layout.server.ts        Server-side session loading
│   ├── +page.svelte             Landing page — catalogue browser with search
│   ├── +page.server.ts          SSR data loading for catalogue
│   ├── catalog/[id]/            Dataset detail view
│   ├── consumer/
│   │   ├── negotiate/           Negotiation wizard flow
│   │   ├── negotiations/        Active negotiations list + [id] detail
│   │   ├── transfer/            Transfer initiation
│   │   ├── transfers/           Transfer history + [id] detail
│   │   └── activity/            This participant's provenance
│   ├── provider/
│   │   ├── assets/              EDC asset list + [id] detail
│   │   ├── contracts/           Contract definitions
│   │   ├── governance/          Governance YAML viewer
│   │   └── activity/            This participant's provenance
│   ├── consent/
│   │   ├── +page.svelte         Data subject consent list
│   │   └── [id]/                Individual consent detail
│   ├── my-data/                 Data subject — owned datasets and sharing
│   ├── lineage/[iri]/           Provenance graph viewer (Cytoscape)
│   ├── metrics/                 Usage metrics
│   └── admin/                   Operator panel
│       ├── onboarding/          Organisation review queue (verify → credential → promote)
│       ├── agreements/          Agreement versions and acceptances
│       ├── observability/       Provenance events — filters, paging, CSV
│       ├── audit/               308 → observability (kept so links survive)
│       ├── health/              Service health checks
│       └── participants/        Participant registry viewer
├── lib/
│   ├── components/
│   │   ├── NegotiationWizard.svelte   Multi-step negotiate → transfer → EDR flow
│   │   ├── StatusPoller.svelte        Generic async state polling component
│   │   ├── PolicySummary.svelte       ODRL policy → human-readable rendering
│   │   ├── EventTable.svelte          Shared provenance table (detail expand, paging)
│   │   ├── LineageGraph.svelte        Cytoscape DAG visualization
│   │   ├── ConsentBadge.svelte        Consent status badge
│   │   └── JsonLdViewer.svelte        JSON-LD document inspector
│   ├── stores/
│   │   └── session.ts           Client-side persona derivation from Keycloak JWT
│   └── server/
│       ├── auth.ts              Server-side route guards (requireAuth, requireAdmin, requireProvider, requireConsumer, requireDataSubject)
│       ├── connector.ts         ds-connector API client (server-side fetch)
│       ├── identity-registry.ts Identity-registry client (user resolution via service account)
│       ├── provenance.ts        ds-provenance API client (server-side fetch)
│       └── odrl.ts              ODRL JSON-LD → human-readable sentence converter
├── hooks.server.ts              Session from the oauth2-proxy header + sign-in/out redirects
└── app.html                     HTML shell
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new page/route | `src/routes/<path>/+page.svelte` + `+page.server.ts` |
| Add a new reusable component | `src/lib/components/<Name>.svelte` |
| Change navigation items | `src/routes/+layout.svelte` (navItems array) |
| Modify auth/role logic | `src/lib/stores/session.ts` (client), `src/lib/server/auth.ts` (server) |
| Call ds-connector API | `src/lib/server/connector.ts` |
| Call ds-provenance API | `src/lib/server/provenance.ts` |
| Change ODRL rendering | `src/lib/server/odrl.ts` |
| Change what a data subject is asked | `src/routes/my-data/` + `getSharingOffers()` in `connector.ts` |

## `/my-data` — sharing offers, not dataset toggles

The page has two sections, and the distinction matters:

1. **Sharing** — the `GET /ns/sharing-offers` list. This is what a person is actually
   asked: a purpose-scoped bundle, from a named controller, for a described category
   of recipient. Toggling posts `{offer_id, enabled}`; the connector expands the offer
   into per-dataset rows and stamps the purpose and controller, so the portal never
   names a dataset and the decision cannot drift from the copy shown.
2. **Data held about you** — the dataset-derived detail view. Read-only. Raw dataset
   keys are not something anyone consents to.

Rules when touching this page:

- **Only `requires_consent` offers get a control.** Contract-based offers render as
  disclosure with no toggle — offering a choice that does not exist is what
  invalidates consent, and the connector returns 409 if you try anyway.
- **Never hardcode a purpose.** `ds` validates purposes against the ODRL taxonomy and
  returns 422 for anything unknown. Pass what the offer declares, or nothing.
  `NegotiationWizard.svelte` broke this rule for a long time: three hardcoded labels,
  two of them not in the taxonomy, sent under a field `NegotiateRequest` does not
  declare — so Pydantic dropped every declaration a person made while the UI implied
  it had been recorded. The options now come from `policySummary.purposes`, read from
  the offer's own `odrl:purpose` constraint (set-valued for a multi-purpose dataset),
  and go out as `declared_purpose[]`, which the connector validates against that same
  offer. **A choice the backend discards is worse than no choice: it manufactures
  consent to a purpose nobody recorded.**
- **`ds` serves codes; the portal renders sentences.** ISO 8601 durations
  (`PT15M`, `P2Y`) and slugs are translated in the component via a lookup that falls
  back to the code itself. `fallback_text_en` is the server-supplied English safety
  net, so an unmapped code degrades to readable text rather than disappearing.

## Observability

Three views read the same provenance API and share `EventTable.svelte`:

| Route | Shows | Reads |
|---|---|---|
| `/admin/observability` | everything this participant recorded, filterable, CSV | `GET /prov/events` |
| `/provider/activity`, `/consumer/activity` | the same store, framed per console | `GET /prov/events` |
| `/my-data` timeline | the person's own history, in plain language | `GET /prov/my/events` |

Three things to keep right when touching them:

- **Event types carry different fields**, so the table shows the shared dimensions
  and expands the rest per row. `queryEvents` keeps every unrecognised field in
  `detail` rather than discarding it — the old client kept four columns, which is
  why `DataDisclosed` used to arrive with its recipient, purposes and column names
  already thrown away.
- **CSV exports the union of what is on screen**, not a fixed header. A fixed
  header drops exactly the fields that make the Block C events meaningful.
- **The subject timeline renders sentences, not codes.** It is read by the person
  the data is about; event type names, DIDs and purpose IRIs are not their
  vocabulary. It is also the only one of the three authenticated by a verifiable
  credential rather than a scope — `subject_id` is taken from that credential
  server-side, so there is no parameter to point elsewhere.

`/admin/audit` is a 308 to `/admin/observability`, kept so older links resolve.

## Operator onboarding

`/admin/onboarding` drives organisation admission. Two rules:

- **Every action calls the same identity-registry endpoint as `ir-cli`.** The CLI
  is the reference implementation — the console must not become a second way to
  change trust state.
- **Show the gate, do not hide the button.** The registry enforces the gates
  (a credential needs a verified owner holding a current agreement; promotion
  needs a valid credential); the page states which one is unmet so the trust
  model stays legible. Actions are additionally gated on `hasGrant`.
- **A stated gate needs a way to satisfy it.** The credential also needs the owner
  to have a `did:web`, and an organisation that applied through `/join` has none —
  it is standing up a deployment, not migrating one. The page offers a *Set DID*
  control (`?/setDid` → `PATCH /admin/owners/{alias}`) next to that gate; without
  it the public join flow dead-ends at "has no DID".

These calls forward the **operator's own token**. `svc-ds-portal` holds no
onboarding grant on purpose, so a 403 means the signed-in user is missing a
Keycloak group — which `requireGrant` renders as an explanation.

## Coding conventions

- **Mobile-first**: all layouts start with mobile viewport, scale up with Tailwind breakpoints
- **SSR by default**: data loading in `+page.server.ts`, not client-side fetch
- **Role-based visibility**: use `session.isProvider`, `session.isConsumer`, `session.isAdmin` from stores
- **Server-side API calls**: never call ds-connector or ds-provenance from client components — use SvelteKit server load functions
- **ODRL rendering**: use `summarisePolicy()` from `odrl.ts` to convert JSON-LD policies to readable text
- **Graph visualization**: use Cytoscape.js with dagre layout for lineage DAGs
- **Svelte 5**: use `$state`, `$derived`, `$effect` runes — not Svelte 4 stores syntax

## Auth model — two independent axes

Authority arrives on **two axes that must not be conflated**. Getting this wrong
is what made roles mutually exclusive.

| Axis | Source | Carries | Checked with |
|---|---|---|---|
| **Keycloak** | realm roles, realm `groups` and `organization.<alias>.groups` — each group naming a **role bundle** expanded by `bundles.generated.ts` | operator and provider authority (`connector.provider.*`, `dataset.admin`, …) | `parseTokenRoles` / `derivePersona` |
| **Verifiable credential** | identity-registry `GET /users/resolve` | `ConsumerUser`, `DataSubject` — what the connector's `X-User-VC` calls present | `hasVcRole(session, role)` |

**Roles are additive, never exclusive.** One person legitimately holds several:
the same human is a data subject about their own consumption *and* a consumer user
acting for an organisation, and may hold provider groups on top. So:

- **Always `hasVcRole(session, …)`, never `session.userVcRole === …`.** The
  singular field is the newest credential, kept only for compatibility.
- **Present the credential the call requires** — `vcJwsForRole(session, role)`.
  `session.userVcJws` is whichever VC was issued last, so using it made a consumer
  call fail whenever the subject credential happened to be newer.
- **The nav shows every section the user qualifies for**, and the landing page
  redirects only when exactly one other path applies. Ranking roles by priority
  bounced a multi-role user away from a section they were entitled to.
- **There is no admin bypass on the VC axis, by design.** An admin has no
  identity-registry mapping, so an "admin may act as consumer" exception was dead
  code — and letting one through would only defer the failure to the connector,
  which requires a VC the portal cannot produce. An operator who must act as a
  consumer needs a credential issued.

`dual@example.test` / `dual` is the dev fixture that holds both VC roles.

### Gating an action on a permission

`hasGrant(session, 'connector.provider.write')` answers "may this user do it", and
`requireGrant(event, '…')` guards a whole route. Both mirror
`ds_auth.permissions.grant_satisfies`, including the `{service}.admin` superset —
a portal that gates on different rules than the API either hides things the user
may do or offers actions the API will refuse.

Use `hasGrant` to decide whether to *offer* an action (a read-only operator should
see a queue without buttons that would 403) and `requireGrant` to guard a route.

**A denied route fails with an explanation, not a redirect.** `requireAdmin`,
`requireProvider` and `requireGrant` throw a 403 naming the missing permission,
rendered by `routes/+error.svelte`. A silent bounce to `/` is indistinguishable
from a broken page: the operator missing one Keycloak group sees the app "not
work" with nothing to act on.

Persona flags (`isAdmin`, `isProvider`, `isConsumer`, `isSubject`) remain for UI
display. All gating is cosmetic — the backend re-verifies and re-authorizes every
request.

## Environment variables

All of these are **server-side only** — the portal is SSR, so every URL is dialled
from the portal process, never from the browser. Use backend addresses
(`172.17.0.1:<port>` on the host, Docker DNS in compose, in-cluster DNS in
Kubernetes); only `ORIGIN` and `AUTH_KEYCLOAK_ISSUER` are browser-facing.

`.env.local` sets all of them for dev and `docker-compose.provider.yml` passes
them to the container. **The in-code fallbacks are a last resort, not the dev
config** — several used to be, and a stale participant DID fails a negotiation
with no useful error.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONNECTOR_URL` | `http://ds-connector:30001` | This participant's ds-connector (used by `connector.ts` and the provider/admin pages) |
| `PROVENANCE_URL` | `http://ds-provenance:30000` | ds-provenance internal URL |
| `FEDERATED_CATALOG_URL` | — | Federated catalog. Preferred source for the catalogue list **and** dataset detail; falls back to `CATALOGUE_URL` |
| `CATALOGUE_URL` | `http://172.17.0.1:30002` | dataset-api. Backs catalogue fallback, `/my-data`'s "data held about you" list, and the health page's dataset-api probe. **External in production** — no chart ships it |
| `IDENTITY_REGISTRY_URL` | `http://172.17.0.1:30005` | Identity registry (user resolution at login) |
| `KEYCLOAK_ISSUER_URL` | `http://keycloak:9080/realms/dataspaces` | Realm issuer, used for **this app's own** client-credentials grant as `svc-ds-portal`. Not a login setting — the portal no longer logs anyone in (use `http://keycloak.dataspaces.localhost:9010/realms/dataspaces` for dev) |
| `OAUTH2_PROXY_BASE_URL` | `http://sso.dataspaces.localhost:9010` | Where a browser is sent to start or end a session. Caddy routes `/oauth2/*` there |
| `ORIGIN` | — | SvelteKit ORIGIN for CSRF (`http://portal.dataspaces.localhost:9010` for dev) |
| `PORTAL_SERVICE_CLIENT_ID` | `svc-ds-portal` | Service account. Used for **one** call — `GET /users/resolve` at login; everything else forwards the user's own token |
| `PORTAL_SERVICE_CLIENT_SECRET` | `svc-ds-portal` | Service account secret |
| `CONSUMER_CONNECTOR_URL` | `http://172.17.0.1:31001` | Connector driven by the `/consumer/*` routes. In dev one portal fronts both stacks, so it differs from `CONNECTOR_URL`; per participant they are the same |
| `CONSUMER_PARTICIPANT_DID` | `did:web:consumer.dataspaces.localhost` | DID reported as the consumer when querying data through an EDR. Wrong value → the provider's PEP rejects the query |
| `CONSUMER_DEFAULT_ASSIGNER` | `did:web:provider.dataspaces.localhost` | ODRL assigner used only when the catalogue entry carries none |
| `CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS` | `http://172.17.0.1:19194/protocol/2025-1` | DSP protocol address used only when the catalogue entry carries none. **Must equal the participant's registered `dsp_address`** — see below |

### A DSP address is an identity, not a route

`counter_party_address` is resolved against the identity registry, so it has to be
the value registered as that participant's `dsp_address`. Anything else gets
`400 Unknown dataspace participant` from the connector — **including an address
that is perfectly reachable**. The container-DNS form
(`http://edc-provider:19194/protocol/2025-1`) resolves, answers HTTP, and is still
rejected, which is why "I can curl it" is not evidence that this value is right.
Check it against `GET /admin/participants` on the identity registry.

For the same reason the catalogue detail loader prefers the DSP endpoint carried
*in the dataset record* (`accessService.endpointURL`) over this default: the
default is only correct for the one provider the deployment happens to name, and
a federated catalogue serves datasets from several.

## Testing

```bash
task setup          # npm ci
task run            # dev server on :30004
task check          # svelte-check
npm run build       # ALSO run this — see below
```

**`task check` is not sufficient on its own.** `svelte-check` does not enforce
SvelteKit's server/client boundary: importing a *value* (not just a type) from
`$lib/server/…` into a component typechecks cleanly and then fails the production
build with "Cannot import … into code that runs in the browser". Anything a
component needs at runtime belongs in a browser-safe module — see
`src/lib/consent.ts`. **Run `npm run build` before considering a change done.**

### UI journeys (`task test:ui`)

```bash
task test:ui:setup  # once per machine — npx playwright install chromium
task test:ui        # one journey per role, plus a dual-role journey
```

Playwright, in `tests/ui/`. Three rules they follow, and new ones should too:

- **Real auth.** Each journey signs in through the Keycloak form as a dev-realm
  user (`fixtures.ts`). Seeding a session or using a direct-grant token would
  make the journeys assert against the fixture — the portal's entire
  authorisation model is derived from the session and the user's credentials.
- **Assert on API effects, not DOM cosmetics.** A decision that survives a
  `reload()` is evidence the connector wrote it. `expectReachable()` checks the
  response *status*, because a 403 here renders as an explanation rather than a
  redirect, so "the page loaded" is not evidence of access.
- **A refusal probe needs an otherwise-valid page state.** If a route would also
  fail for an unrelated reason, the probe passes with the guard deleted.

There is **no `webServer`**: every journey needs the connector, the registry,
provenance and Keycloak, so `global-setup.ts` fails fast with "start the stack"
rather than letting the suite red out on timeouts. `workers: 1` — journeys mutate
shared backend state, and parallelism here trades a real signal for a flaky one.

These journeys found three defects that unit tests and `ds-e2e` both missed: two
sharing offers over one dataset collided in the connector, `/provider/contracts`
was wired to EDC transfer processes and 500'd on real data, and an organisation
that applied through `/join` could never be issued a credential because nothing
assigned it a DID.

### Lint

`npm run lint` is real now (it previously named a package that was not
installed). `svelte/require-each-key` is a **warning**: ~34 unkeyed `{#each}`
blocks predate the config, and an unkeyed block re-uses DOM nodes by index, which
reorders form state when a list changes underneath. Worth fixing; not a
lint-config decision. `svelte/no-navigation-without-resolve` is off — the portal
is served from the root of its own host and never sets `base`.

### The npm lock file is cross-platform

The image is `node:22-alpine` (musl) and `npm ci` fails if the lock lacks the
musl-only optional deps — a plain `npm install` on a glibc host prunes them and
the *Docker build* breaks while everything local still works. After changing
dependencies, regenerate the lock in the build image:

```bash
docker run --rm -v "$PWD":/w -w /w node:22-alpine \
  sh -c 'npm install --package-lock-only --include=optional'
```

## Integration points

- **Downstream**: calls ds-connector REST API (all data operations, JWT-authenticated via `svc-ds-portal`)
- **Downstream**: calls ds-provenance REST API (lineage, audit)
- **Downstream**: calls identity-registry `/users/resolve` (user DID/VC lookup on login, via `svc-ds-portal` service account)
- **Auth**: Keycloak OIDC via oauth2-proxy (no OIDC client in this app)
- **No upstream callers** — this is the user-facing frontend
