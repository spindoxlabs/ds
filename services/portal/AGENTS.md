# ds-portal — Agent Guide

## Service identity

- **Role**: Web frontend for all dataspace participant roles
- **Language**: TypeScript, SvelteKit 2.0, Svelte 5.0, Tailwind CSS 4.0
- **Port**: 30004 (debug: 30904)
- **URL**: `https://portal.dataspaces.localhost`
- **Auth**: Auth.js with Keycloak OIDC

## Source layout

```
src/
├── routes/
│   ├── +layout.svelte           Root layout — nav bar, auth state, role-based menu
│   ├── +layout.server.ts        Server-side session loading
│   ├── +page.svelte             Landing page — catalogue browser with search
│   ├── +page.server.ts          SSR data loading for catalogue
│   ├── consumer/
│   │   ├── catalog/             Consumer catalog view
│   │   ├── negotiate/           Negotiation wizard flow
│   │   ├── negotiations/        Active negotiations list
│   │   ├── transfers/           Transfer history
│   │   └── edr/[id]/            EDR viewer (endpoint + token)
│   ├── provider/
│   │   ├── +page.svelte         Provider dashboard
│   │   ├── governance/          Governance YAML viewer/editor
│   │   ├── assets/              EDC asset list
│   │   ├── contracts/           Contract definitions
│   │   └── transfers/           Provider-side transfers
│   ├── consent/
│   │   ├── +page.svelte         Data subject consent list
│   │   └── [id]/                Individual consent detail
│   └── admin/
│       ├── +page.svelte         Operator dashboard
│       ├── health/              Service health checks
│       ├── audit/               Provenance event audit log
│       ├── participants/        Participant registry viewer
│       └── lineage/             Provenance graph viewer (Cytoscape)
├── lib/
│   ├── components/
│   │   ├── NegotiationWizard.svelte   Multi-step negotiate → transfer → EDR flow
│   │   ├── StatusPoller.svelte        Generic async state polling component
│   │   ├── PolicySummary.svelte       ODRL policy → human-readable rendering
│   │   ├── LineageGraph.svelte        Cytoscape DAG visualization
│   │   ├── ConsentBadge.svelte        Consent status badge
│   │   ├── MedallionBadge.svelte      Data quality tier badge (bronze/silver/gold)
│   │   └── JsonLdViewer.svelte        JSON-LD document inspector
│   ├── stores/
│   │   └── session.ts           Client-side persona derivation from Keycloak JWT
│   └── server/
│       ├── auth.ts              Server-side route guards (requireAuth, requireAdmin, requireProvider)
│       ├── connector.ts         ds-connector API client (server-side fetch)
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
| `PUBLIC_KEYCLOAK_URL` | `https://keycloak.dataspaces.localhost` | Keycloak base URL |
| `CONNECTOR_URL` | `http://ds-connector:30001` | ds-connector internal URL |
| `PROVENANCE_URL` | `http://ds-provenance:30000` | ds-provenance internal URL |
| `CATALOGUE_URL` | `http://ds-federated-catalog:30003` | Federated catalog URL |
| `AUTH_SECRET` | — | Auth.js session secret |
| `AUTH_KEYCLOAK_SECRET` | — | Keycloak client secret |

## Testing

```bash
task setup          # npm ci
task run            # dev server on :30004
task check          # svelte-check
task lint           # eslint
npm run test        # vitest
```

## Integration points

- **Downstream**: calls ds-connector REST API (all data operations)
- **Downstream**: calls ds-provenance REST API (lineage, audit)
- **Auth**: Keycloak OIDC via Auth.js
- **No upstream callers** — this is the user-facing frontend
