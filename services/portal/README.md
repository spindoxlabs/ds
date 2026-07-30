# ds-portal

The dataspace web frontend. Covers the full portal surface for all participant roles: dataset consumer, dataset provider, operator, and data subject.

Port: `30004`
URL: `http://portal.dataspaces.localhost:9010`

Built with SvelteKit, targeting the latest stable release. Mobile-first component design.

---

> **Concepts live in the docs site, not here.** This README is the local entry
> point: routes, components, configuration and how to run it. The reasoning is
> published at **<https://spindoxlabs.github.io/ds/>** — start with
> [Architecture](https://spindoxlabs.github.io/ds/architecture/) and
> [Consent & Sovereignty](https://spindoxlabs.github.io/ds/consent-and-sovereignty/).
> Working on the code? Read `AGENTS.md` in this directory first.

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

Two independent axes decide what a person sees: **Keycloak groups** grant service
permissions, **verifiable credentials** decide the person-facing roles. They are
additive — one human can hold several at once. See `AGENTS.md` for the model.

### Public

- `/` — landing page with dataspace overview and featured datasets
- `/catalog/[id]` — dataset detail, policy summary and access-request wizard
- `/join` — invite-gated application to join the dataspace (no account needed)

### Consumer (`ConsumerUser` credential)

- `/consumer` — requests, negotiations and active transfers, including
  `awaiting_consent` rendered as what it is: waiting on a person
- `/consumer/activity` — this participant's provenance events

### Producer (`connector.provider.read` / `.write` groups)

- `/provider` — dashboard
- `/provider/assets`, `/provider/assets/[id]` — registered EDC assets and detail
- `/provider/contracts` — contract agreements over this participant's datasets
- `/provider/governance` — governance and policy matrix
- `/provider/requests` — consent asks awaiting a decision
- `/provider/activity` — provenance events

### Data subject (`DataSubject` credential)

- `/my-data` — sharing offers, the decision on each, the Art. 7(1) evidence
  record, and a timeline read with the subject's own credential
- `/consent`, `/consent/[id]` — consent requests directed at this subject

### Operator (`identity-registry.*` and `provenance.read` groups)

- `/admin` — dashboard
- `/admin/participants` — participant registry
- `/admin/onboarding` — organisation admission: invites, verification, agreement,
  credential, promotion, connection bundle
- `/admin/agreements` — service agreements and acceptances
- `/admin/observability` — filterable, paged provenance log (`/admin/audit` 308s here)
- `/admin/health` — service health
- `/lineage/[iri]` — provenance lineage viewer

---

## Key components

`NegotiationWizard.svelte` — multi-step wizard handling the full consumer flow: select dataset, negotiate, poll until `FINALIZED`, initiate transfer, poll until `STARTED`, retrieve EDR. Uses `StatusPoller.svelte` for async state updates.

`PolicySummary.svelte` — renders an ODRL policy as human-readable text, showing permitted actions, prohibitions, and obligations.

`LineageGraph.svelte` — renders PROV-O lineage as an interactive graph (nodes + edges) using the `ds-provenance` lineage API.

`ConsentBadge.svelte` — displays consent status with visual indicators.

`session.ts` — session helpers over the access token oauth2-proxy forwards. Parses realm roles and Keycloak **groups** (each naming a role bundle) to gate route access.

---

## Authentication — the local facts

**The portal is not an OIDC client.** Auth.js, the `ds-portal` realm client and
`AUTH_SECRET` are gone: **oauth2-proxy** holds the browser session and forwards the
access token as `X-Auth-Request-Access-Token`, which `hooks.server.ts` turns into a
session. The header is transport, never authority — whatever fronts this app must
strip a client-supplied `X-Auth-Request-*`, and every ds service re-verifies the
token via JWKS regardless.

Authority arrives on **two axes**, and conflating them is the commonest mistake
here:

| Axis | Carries | Checked with |
|---|---|---|
| Keycloak **groups** — each naming a role bundle | operator and provider authority | `hasGrant` / `requireGrant` in `src/lib/server/auth.ts` |
| **Verifiable credentials** — `ConsumerUser`, `DataSubject` | the data-subject plane | `hasVcRole`, sent as `X-Subject-Id` + `X-User-VC` |

Roles are **additive, never exclusive** — the same person is legitimately both.
The bundle table is generated from `ds_auth`; run `task auth:bundles:generate`
after changing it, never hand-edit `src/lib/server/bundles.generated.ts`.

A missing grant renders an **explanation**, not a redirect: bouncing a user to `/`
makes a missing group look like a broken page.

Operator actions forward the **signed-in user's own token**. The `svc-ds-portal`
service account deliberately holds no onboarding grant — its single use is the
login-time `/users/resolve`, which is also where the subject's DID comes from
(there is no `dataspace_did` claim; see
[Subject identity](https://spindoxlabs.github.io/ds/consent-subject-id/)).

Login surface, bundles and the realm contract:
[Architecture](https://spindoxlabs.github.io/ds/architecture/) and
[Keycloak requirements](https://spindoxlabs.github.io/ds/deployment/keycloak/).

---

## Configuration

`.env.example` at the repo root is the reference for every variable — it is kept
complete on purpose, so start there rather than from this list. The ones the
portal reads:

| Variable | Purpose |
|---|---|
| `CONNECTOR_URL`, `PROVENANCE_URL`, `CATALOGUE_URL`, `FEDERATED_CATALOG_URL`, `IDENTITY_REGISTRY_URL` | server-side upstreams |
| `CONSUMER_CONNECTOR_URL`, `CONSUMER_PARTICIPANT_DID`, `CONSUMER_DEFAULT_ASSIGNER`, `CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS` | consumer-side wiring |
| `OAUTH2_PROXY_BASE_URL` | where a browser is sent to start or end a session |
| `PORTAL_SERVICE_CLIENT_ID`, `PORTAL_SERVICE_CLIENT_SECRET` | the service account used only for `/users/resolve` |

A DSP address is an **identity**, not a route: `CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS`
is resolved against the participant registry, so an in-cluster hostname that
happens to be reachable is still rejected.

---

## Development

```bash
cd services/portal
task setup          # npm ci
task run            # SvelteKit dev server on :30004
task debug          # same, with the Node inspector on :30904
task check          # svelte-check
task lint           # eslint
npm run build       # ALSO run this — see AGENTS.md
task test:ui:setup  # once per machine — installs the Playwright browser
task test:ui        # UI journeys against a running stack
```

`task check` alone is not the gate: importing a *value* from `$lib/server/…` into
a component typechecks cleanly and fails the production build. Run `npm run build`.

The UI journeys need a running stack (`task docker:start` or `task dev:start`);
they sign in through the real Keycloak form as dev-realm users.

---

## Known gaps

- ~34 unkeyed `{#each}` blocks (`svelte/require-each-key` warns): an unkeyed block
  re-uses DOM nodes by index, which reorders form state when a list changes
- Mobile viewport not systematically tested below 375 px
