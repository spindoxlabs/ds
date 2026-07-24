# ds-portal

The dataspace web frontend. Covers the full portal surface for all participant roles: dataset consumer, dataset provider, operator, and data subject.

Port: `30004`
URL: `http://portal.dataspaces.localhost:9010`

Built with SvelteKit, targeting the latest stable release. Mobile-first component design.

---

## Purpose

The portal makes the dataspace accessible without direct API interaction. It provides:

- A public-facing catalogue browser for discovering available datasets
- A guided negotiation wizard for consumers to obtain data access
- A provider governance dashboard for syncing datasets to EDC and monitoring transfers
- A consent portal where data subjects can review, approve, reject, and revoke consent requests for use of their data
- A provenance lineage viewer showing the data flow graph for any dataset

---

## Routes

### Public

- `/` — landing page with dataspace overview and featured datasets from the catalogue
- `/catalog/[id]` — dataset detail, policy summary and access request wizard

### Consumer (requires `dataspaces.query` scope)

- `/consumer` — user-scoped requests, negotiations and active transfers

### Provider (requires `dataset.admin` role)

- `/provider` — provider dashboard
- `/provider/assets` — list registered EDC assets
- `/provider/assets/[id]` — asset detail and policy view
- `/provider/contracts` — provider contract state
- `/provider/governance` — governance and policy matrix view

### Consent portal (data subjects)

- `/consent` — list all consent requests directed at the authenticated subject
- `/consent/[id]` — consent request detail with full ODRL offer rendered via `PolicySummary`
- `/my-data` — datasets owned by the authenticated data subject
- `POST /consent/[id]/reject` — reject consent
- `POST /consent/[id]/revoke` — revoke previously granted consent (terminates linked transfers)

### Operator

- `/admin` — operator dashboard
- `/admin/participants` — participant registry management
- `/lineage/[iri]` — provenance lineage viewer (fetches from `ds-provenance`)

---

## Key components

`NegotiationWizard.svelte` — multi-step wizard handling the full consumer flow: select dataset, negotiate, poll until `FINALIZED`, initiate transfer, poll until `STARTED`, retrieve EDR. Uses `StatusPoller.svelte` for async state updates.

`PolicySummary.svelte` — renders an ODRL policy as human-readable text, showing permitted actions, prohibitions, and obligations.

`LineageGraph.svelte` — renders PROV-O lineage as an interactive graph (nodes + edges) using the `ds-provenance` lineage API.

`ConsentBadge.svelte` — displays consent status with visual indicators.

`session.ts` — Keycloak-based session store. Parses access token claims for `resource_access.ds-portal.roles` and `realm_access.roles` to gate route access.

---

## Authentication

Keycloak OIDC. The portal client is `ds-portal`. Role-based access:

- `dataspaces.query` scope — consumer routes
- `dataset.admin` role — provider routes
- `admin` role — operator routes
- No role — consent portal (data subject routes available to any authenticated user)

Role-based guards are implemented in `src/lib/server/auth.ts`.

### Subject identity

The subject identity extraction uses the following priority chain:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 | `DEMO_SUBJECT_ID` env var | Dev/test override; bypasses JWT entirely |
| 2 | `dataspace_did` JWT claim | DID set by identity-registry Keycloak sync |
| 3 | `preferred_username` claim | Keycloak display name (legacy fallback) |
| 4 | `sub` claim | Keycloak user UUID (last resort) |

The resolved subject ID is sent to ds-connector via the `X-Subject-Id` header on consent endpoints. This is backward compatible: if the `dataspace_did` claim is absent (before identity-registry onboarding), the existing claims are used as fallback.

---

## Configuration

Environment variables (set in `.env` or Docker):

- `PUBLIC_KEYCLOAK_URL` — Keycloak base URL
- `PUBLIC_KEYCLOAK_REALM` — realm name
- `PUBLIC_KEYCLOAK_CLIENT_ID` — OIDC client ID
- `CONNECTOR_URL` — `ds-connector` base URL (server-side)
- `PROVENANCE_URL` — `ds-provenance` base URL (server-side)
- `CATALOGUE_URL` — `dataset-api` catalogue URL (server-side)

---

## Development

```bash
cd services/portal
task setup       # npm install
task run         # SvelteKit dev server on :30004
task debug       # same, with the Node inspector on :30904

# The npm scripts are not wrapped in tasks:
npm run build
npm run preview
npm run test
```

```bash
docker compose -f docker-compose.yml up
```

---

## Known gaps

- No E2E tests (Playwright)
- Mobile viewport not systematically tested below 375 px
