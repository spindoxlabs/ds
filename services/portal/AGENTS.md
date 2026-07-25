# ds-portal — Agent Guide

## Service identity

- **Role**: Web frontend for all dataspace participant roles
- **Language**: TypeScript, SvelteKit 2.0, Svelte 5.0, Tailwind CSS 4.0
- **Port**: 30004 (debug: 30904)
- **URL**: `http://portal.dataspaces.localhost:9010` (via Caddy), direct `http://172.17.0.1:30004`
- **Auth**: Auth.js with Keycloak OIDC

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
│   │   └── transfers/           Transfer history + [id] detail
│   ├── provider/
│   │   ├── assets/              EDC asset list + [id] detail
│   │   ├── contracts/           Contract definitions
│   │   └── governance/          Governance YAML viewer
│   ├── consent/
│   │   ├── +page.svelte         Data subject consent list
│   │   └── [id]/                Individual consent detail
│   ├── my-data/                 Data subject — owned datasets and sharing
│   ├── lineage/[iri]/           Provenance graph viewer (Cytoscape)
│   ├── metrics/                 Usage metrics
│   └── admin/                   Operator panel
│       ├── audit/               Provenance event audit log
│       ├── health/              Service health checks
│       └── participants/        Participant registry viewer
├── lib/
│   ├── components/
│   │   ├── NegotiationWizard.svelte   Multi-step negotiate → transfer → EDR flow
│   │   ├── StatusPoller.svelte        Generic async state polling component
│   │   ├── PolicySummary.svelte       ODRL policy → human-readable rendering
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
├── hooks.server.ts              SvelteKit request lifecycle (Auth.js handle)
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
- **`ds` serves codes; the portal renders sentences.** ISO 8601 durations
  (`PT15M`, `P2Y`) and slugs are translated in the component via a lookup that falls
  back to the code itself. `fallback_text_en` is the server-supplied English safety
  net, so an unmapped code degrades to readable text rather than disappearing.

## Coding conventions

- **Mobile-first**: all layouts start with mobile viewport, scale up with Tailwind breakpoints
- **SSR by default**: data loading in `+page.server.ts`, not client-side fetch
- **Role-based visibility**: use `session.isProvider`, `session.isConsumer`, `session.isAdmin` from stores
- **Server-side API calls**: never call ds-connector or ds-provenance from client components — use SvelteKit server load functions
- **ODRL rendering**: use `summarisePolicy()` from `odrl.ts` to convert JSON-LD policies to readable text
- **Graph visualization**: use Cytoscape.js with dagre layout for lineage DAGs
- **Svelte 5**: use `$state`, `$derived`, `$effect` runes — not Svelte 4 stores syntax

## Auth model

Keycloak issues JWTs with roles in `resource_access` and scopes. The portal derives a `UserPersona`:

| Role / Scope | Persona flag | Access |
|-------------|-------------|--------|
| `admin` | `isAdmin` | Admin routes, health, audit, lineage |
| `dataset.admin` | `isProvider` | Provider routes, governance sync |
| `dataspaces.query` | `isConsumer` | Consumer routes, negotiate, transfer |
| (authenticated) | `isSubject` | Consent routes |

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
| `AUTH_KEYCLOAK_ISSUER` | `http://keycloak:9080/realms/dataspaces` | OIDC issuer (use `http://keycloak.dataspaces.localhost:9010/realms/dataspaces` for dev) |
| `AUTH_KEYCLOAK_ID` | `ds-portal` | Keycloak login client ID (public redirect client, **not** a service client) |
| `AUTH_KEYCLOAK_SECRET` | — | Login client secret (`change-me-local-client-secret` for dev) |
| `AUTH_KEYCLOAK_SCOPE` | `openid profile email` | OIDC scopes requested at login |
| `AUTH_SECRET` | `dev-secret-change-in-prod` | Auth.js session encryption secret. A known value means forgeable sessions |
| `ORIGIN` | — | SvelteKit ORIGIN for CSRF (`http://portal.dataspaces.localhost:9010` for dev) |
| `PORTAL_SERVICE_CLIENT_ID` | `svc-ds-portal` | Service account. Used for **one** call — `GET /users/resolve` at login; everything else forwards the user's own token |
| `PORTAL_SERVICE_CLIENT_SECRET` | `svc-ds-portal` | Service account secret |
| `CONSUMER_CONNECTOR_URL` | `http://172.17.0.1:31001` | Connector driven by the `/consumer/*` routes. In dev one portal fronts both stacks, so it differs from `CONNECTOR_URL`; per participant they are the same |
| `CONSUMER_PARTICIPANT_DID` | `did:web:consumer.dataspaces.localhost` | DID reported as the consumer when querying data through an EDR. Wrong value → the provider's PEP rejects the query |
| `CONSUMER_DEFAULT_ASSIGNER` | `did:web:provider.dataspaces.localhost` | ODRL assigner used only when the catalogue entry carries none |
| `CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS` | `http://edc-provider:19194/protocol/2025-1` | DSP protocol address used only when the catalogue entry carries none |

## Testing

```bash
task setup          # npm ci
task run            # dev server on :30004
task check          # svelte-check — the only working gate today
```

**There is no test runner yet, and `lint` does not run.** `package.json` declares
`lint: eslint src` but `eslint` is not in `devDependencies`, and there is no test
script at all — no vitest, no Playwright. So `task check` is the whole gate, and
"the UI exercises the API" is currently unenforced. Adding Playwright (and making
`lint` real) is P10 of `.agents/plans/portal-review/plan.md`. Until then, changes
here are verified by `task check` plus driving the affected page by hand.

## Integration points

- **Downstream**: calls ds-connector REST API (all data operations, JWT-authenticated via `svc-ds-portal`)
- **Downstream**: calls ds-provenance REST API (lineage, audit)
- **Downstream**: calls identity-registry `/users/resolve` (user DID/VC lookup on login, via `svc-ds-portal` service account)
- **Auth**: Keycloak OIDC via Auth.js (`@auth/sveltekit`)
- **No upstream callers** — this is the user-facing frontend
