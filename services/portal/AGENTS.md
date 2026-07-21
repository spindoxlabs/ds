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
│   └── admin/
│       ├── audit/               Provenance event audit log
│       ├── compliance/          Compliance checks
│       ├── health/              Service health checks
│       ├── participants/        Participant registry viewer
│       └── rulebook/            Governance rulebook
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

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONNECTOR_URL` | `http://ds-connector:30001` | ds-connector internal URL |
| `PROVENANCE_URL` | `http://ds-provenance:30000` | ds-provenance internal URL |
| `FEDERATED_CATALOG_URL` | `http://ds-federated-catalog:30003` | Federated catalog URL |
| `IDENTITY_REGISTRY_URL` | `http://identity-registry:30005` | Identity registry URL (user resolution) |
| `AUTH_KEYCLOAK_ISSUER` | `http://keycloak:8080/realms/dataspaces` | OIDC issuer (use `http://keycloak.dataspaces.localhost:9010/realms/dataspaces` for dev) |
| `AUTH_KEYCLOAK_ID` | `ds-portal` | Keycloak client ID |
| `AUTH_KEYCLOAK_SECRET` | — | Keycloak client secret (`change-me-local-client-secret` for dev) |
| `AUTH_SECRET` | `dev-secret-change-in-prod` | Auth.js session encryption secret |
| `ORIGIN` | — | SvelteKit ORIGIN for CSRF (`http://portal.dataspaces.localhost:9010` for dev) |
| `PORTAL_SERVICE_CLIENT_ID` | `svc-ds-portal` | Service account for backend API calls |
| `PORTAL_SERVICE_CLIENT_SECRET` | `svc-ds-portal` | Service account secret |
| `PORTAL_DEMO_ADMIN_USERS` | `admin` | Comma-separated usernames treated as admin (dev fallback) |

## Testing

```bash
task setup          # npm ci
task run            # dev server on :30004
task check          # svelte-check
task lint           # eslint
npm run test        # vitest
```

## Integration points

- **Downstream**: calls ds-connector REST API (all data operations, JWT-authenticated via `svc-ds-portal`)
- **Downstream**: calls ds-provenance REST API (lineage, audit)
- **Downstream**: calls identity-registry `/users/resolve` (user DID/VC lookup on login, via `svc-ds-portal` service account)
- **Auth**: Keycloak OIDC via Auth.js (`@auth/sveltekit`)
- **No upstream callers** — this is the user-facing frontend
