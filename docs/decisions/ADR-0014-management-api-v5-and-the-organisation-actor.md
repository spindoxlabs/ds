# ADR-0014 — The management API is v5beta behind OAuth2, and an organisation can act as itself

**Date:** 2026-09-17
**Status:** accepted
**Rules affected:** `D-20` (amended), `D-16`, `D-21`; blueprint `DSSC-XCT-09` (declared, not a
deviation)

## Context

ds drove EDC 0.18.0 through the **v3** management API, which that release deprecates and EDC
main has removed. It authenticated with **one deployment-wide `x-api-key`**. Anyone holding
that key could administer any participant's contracts on the runtime they could reach, and
nothing said who had called.

A deployment also needs two organisations to exchange data with no person at the keyboard: a
batch job at one organisation pulls a dataset from another. ds could not do that. Every
`/consumer/*` route required a person's `ConsumerUser` credential. The first design proposed a
ds-specific `connector.consumer.write` permission. That would have reinvented what EDC 0.18.0
already ships:

- the v5 management API under `/v5beta/participants/{participantContextId}/…`;
- `management-api-oauth2-authentication`, which takes the participant context from the
  token's `sub`;
- `management-api-authorization`, which enforces `@RequiredScope` and confines a token to its
  own context.

Measured against the v0.18.0 tag and a running runtime:

- The OAuth2 filter checks the signature, `iss`, `nbf` and `exp`, and **never `aud`**.
- v5 is `v5beta` in 0.18.0. EDC main renamed it to `v5` with the same schemas for everything ds
  calls.
- v5 has **no EDR endpoint**.
- v5 validates raw request bodies against JSON schemas before any JSON-LD processing.
- Keycloak's `sub` is the service account's UUID unless a mapper replaces it.

## Decision

1. **Adopt EDC's model, and invent no permission.** ds calls the v5 management API
   (`EDC_MANAGEMENT_API_VERSION`, `v5beta` until 0.19) with an OAuth2 bearer token. EDC's
   scope grammar is `management-api[:resource]:read|write|admin`. ds grants seven
   per-resource scopes and never `admin`. The classic runtime keeps its single participant
   context, `edc.participant.context.id`, which is set to the participant DID.
2. **One client per organisation**, `svc-ds-connector-<alias>`, shared by its connector and
   its batch jobs:
   - `ir-cli keycloak org-sync` and the provisioning bundle create it, because the realm sync
     cannot add the mapper;
   - a hardcoded-claim mapper sets `sub` to the organisation's participant context;
   - it holds the management scopes plus the connector's service grants.

   **One credential per connector:** the connector presents this client to its EDC and to
   every ds service. `svc-ds-connector` remains only as the audience.
3. **Port isolation is the control for the missing audience check.** Any holder of the
   organisation's token can administer that organisation's contracts wherever the management
   port is reachable. Compose therefore publishes no EDC management port. The chart keeps the
   port ClusterIP-only behind the NetworkPolicy, and batch jobs call the connector, never the
   EDC. `services/connector/tests/test_management_port_isolation.py` asserts it statically,
   and `ds-e2e --flow organisation-token` asserts it live.
4. **The organisation is an actor on `/consumer/*`**, with no bypass:
   - its token must name **this** connector's participant context;
   - it must hold the EDC scope of the call ds makes on its behalf. For example,
     `/consumer/negotiate` requires `management-api:negotiations:write`, and EDC's own matcher
     decides;
   - it does not get the owner perimeter's blanket service pass;
   - its requests sit in the ledger under `org:<context>`, apart from any person's;
   - provenance records the client and the organisation it acted for (`acted_by`,
     `actedOnBehalfOf` the participant DID).

   Registry checks, purposes and consent gating apply exactly as they do for a person.
5. **An organisation token never reads a person's consents** (`D-20`, amended). `/consent/my/*`
   accepts only the subject's credential.
6. **The EDR comes from the transfer's own callback.** A consumer transfer names
   `CONNECTOR_EDC_CALLBACK_URL` for `transfer.process.started`, with a header whose value EDC
   reads from its vault (`ds-connector-callback-key`). The connector stores the EDR it receives
   (`edr_entries`). ds does not revive the deprecated EDR cache.
7. **`CONNECTOR_ROLE` accepts `provider`, `consumer` or `both`.** A participant has one EDC
   runtime, so one process may mount both routers against one management client.
8. **Multi-tenancy stays open.** The virtual control plane is not adopted in this cut, and the
   client is the same either way.

## Consequences

- The shared management key is gone from every surface: EDC properties, compose, Helm, the
  `.env` files and the Taskfile.
- The readiness probes target a v5 route through `docker exec`, because the port is no longer
  on the host.
- **Accepted deviation from the plan's order:** the classic v3 and v4 controllers were excluded
  from the runtime in the EDC phase, not after the client moved. Behind the OAuth2 filters
  they carry no scope and no ownership check, so they would have admitted any token naming a
  context. `RuntimeContractTest` holds the exclusion.
- Every request body now carries the v2 context as an array. Policies are sent in the DSP 2025
  compact form (`ds_edc.odrl.to_dsp_compact`), and the permissions EDC stores are unchanged.
  Callback auth keys are sent as `edc:authKey` and `edc:authCodeId`, because the v2 context
  does not map the bare names (an upstream gap).
- **`celine-policies keycloak sync --prune` deletes the organisation clients**, which it sees as
  orphans. ds never passes `--prune`. A deployment that does must re-run `org-sync` and
  redistribute the secrets.
- A deployment moving to this version needs, per participant:
  - an organisation client and its secret (`SVC_DS_CONNECTOR_<ALIAS>_SECRET`, and
    `organisationClientSecret` in Helm);
  - a callback key (`edcCallbackKey`);
  - for a consumer, a reachable callback URL.

  The ds-connector chart's Secret keys changed accordingly (`CONNECTOR_CLIENT_SECRET` and
  `EDC_CALLBACK_KEY` replace `EDC_API_KEY`), and an ExternalSecret mapping must follow.
- `GET /consumer/negotiations/{id}` answers `404` for a negotiation whose ledger row belongs to
  another actor.
- EDC 0.19 changes one setting (`v5beta` → `v5`), and nothing else ds calls.
- A data plane under the Data Plane Signaling protocol is a follow-on. It starts in
  `services/dataset-api-mock`.

An ADR is not a rule (ADR-0004). What an organisation token may and may not reach is rulebook
material, and lives in `D-20`. How the platform gets there is recorded here.
