# ds-connector

`ds-connector` is the control plane that sits beside an Eclipse Dataspace Components (EDC)
runtime and decides what that runtime is allowed to do.

The EDC speaks the Dataspace Protocol: it exchanges catalogues, negotiates contracts and
moves data. It does not know what a dataset is, who owns it, or whether a person consented
to it being shared. `ds-connector` knows all three, and answers the EDC every time a
decision is needed.

One codebase runs as **two instances** — a provider and a consumer — selected by
`CONNECTOR_ROLE`. The role decides which EDC the connector drives and which routers it
mounts: `/provider/*` on a provider, `/consumer/*` on a consumer, everything else on both.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Access & Usage Policies Enforcement](../blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) · [DSSC · Data Exchange](../blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Cross-cutting (personal data)](../blueprints/dssc/cross-cutting.md) |
| Rules it enforces | [Rulebook · Policies](../rulebook/policies.md) · [Rulebook · Personal data](../rulebook/personal-data.md) |

In DSSC terms this is the **policy decision point** and the participant-side control plane.
The EDC is the protocol engine; this is the thing with an opinion.

## What it does

**Publishes governance into the EDC.** `POST /provider/sync` reads `governance.yaml`,
compiles each exposed dataset into an EDC asset, an ODRL policy definition and a contract
definition, and pushes all three. The compilation lives in [`libs/governance`](libs/governance.md);
this service owns the sync, the ordering and the refusal to publish a dataset whose purposes
cannot be resolved.

**Holds the consent registry.** `/consent/*` is where a data subject grants, rejects or
revokes sharing of their own rows. Subjects authenticate with a Verifiable Credential
(`X-Subject-Id` + `X-User-VC`), not a bearer token — the credential *is* the identity, and
no operator sits in between. Operators and the onboarding service have their own routes under
the same prefix, guarded by ordinary permissions: `POST /consent/admin/shares` records a
subject's standing decision (`connector.consent.provision`), and `GET /consent/admin/shares`
reads back **who currently consents to one sharing offer**, for one named consumer
(`connector.consent.audience`). The read is a separate permission on purpose — a write grant
must not carry bulk subject enumeration with it, which is why `.audience` is in no bundle and
is reached by a person only through `connector.admin`.

**Answers every policy question.** `/internal/*` is the decision point:

| Endpoint | Asked by | Question |
|---|---|---|
| `GET /internal/participants/check` | EDC constraint function | is this participant in the dataspace, with this scope? |
| `GET /internal/consent/check` | EDC constraint functions, pending guard | does anyone consent to this dataset for this consumer and purpose? |
| `POST /internal/consent/asks` | EDC pending guard | park this negotiation and ask the subjects |
| `POST /internal/dataplane/authorize` | the dataset API | may these rows leave, and which ones? |
| `GET /internal/edr-jwks` | the dataset API | the public key that verifies an EDR token |
| `POST /internal/audit/query` | the dataset API | record that a query happened |

**Drives the consumer side of an exchange.** `/consumer/*` walks the whole flow — request a
catalogue over DSP, negotiate, poll to agreement, start a transfer, fetch the EDR — and
records each access request so a consumer can see and revoke their own.

**Records the EDC's lifecycle.** `/webhooks/*` receives contract-negotiation and
transfer-process events from the EDC extensions and writes agreements and their frozen
policy snapshots into its own tables. That snapshot is what later purpose checks read: the
agreed policy, not the current one. The transfer webhook emits `TransferStarted` and
`DataTransferCompleted` — **the only place a provider emits the second** — and attributes
both to the counterparties named in its own agreement record, never to anything the event
claims about them.

**Publishes the vocabularies.** `/ns/*` is public and unauthenticated — an onboarding wizard
renders purposes and offers before anyone has an identity. Two layers, and confusing them is
the easy mistake:

| Endpoint | Layer | Serves |
|---|---|---|
| `GET /ns` | — | the index of everything below |
| `GET /ns/policy` | **policy** | the ODRL profile as SKOS — purposes, operands, actions, DPV alignment |
| `GET /ns/sharing-offers` | **policy** | offer codes plus an English fallback, no dataset keys |
| `GET /ns/vocabularies` | **semantic** | the registry — slug, title, version, canonical IRI, cached or not |
| `GET /ns/{slug}` | **semantic** | a cached JSON-LD vocabulary — SAREF, CIM, COSEM |

The policy vocabulary is this dataspace's own and is compiled from the ODRL profile. The
semantic ones are external standards this participant serves a **local copy** of; a dataset
points at one through `dcat.conforms_to`, which travels into the catalogue as `dct:conformsTo`
on the EDC asset. Serving is from disk only — never a live fetch, because a public
unauthenticated route that retrieved an operator-configured URL would proxy for any caller.
The cache is filled by `task vocab:fetch` or at startup, and **a registered vocabulary with no
local copy stops the connector booting**.

**Emits provenance.** Every act above produces a PROV-O domain event posted to
[`ds-provenance`](provenance.md), fire-and-forget, so a provenance outage never fails an
exchange.

## How it works

### The data-plane decision, end to end

The representative path. A consumer holds an EDR token and issues a SQL query; the dataset
API asks the connector whether rows may flow.

1. **Authenticate.** The caller must present `connector.internal` *by name* —
   `connector.admin` deliberately does not satisfy it. Only the dataset API, the EDC and the
   e2e harness hold it.
2. **Resolve the agreement** from the connector's own tables, by either the local id or the
   shared DSP id, and check it is not terminated.
3. **Bind it to the caller.** The agreement's consumer must equal the DID in the verified
   EDR token. This is what makes the caller-supplied agreement id safe to trust.
4. **Check transfer liveness**, when a transfer id is named.
5. **Check purpose.** The agreed purposes come from the agreement's policy snapshot;
   the requested purpose must be covered by one of them under the profile's `broader`
   hierarchy — consent to a parent purpose covers a narrower request, never the reverse.
6. **Per dataset:** if governance says no consent is needed, allow with no filter. Otherwise
   collect the subjects whose latest decision authorises this consumer, translate their DIDs
   to the usernames the data plane joins on, and return a row filter.
7. **Combine.** The strictest verdict wins, and every refusal shares one response shape so a
   probe cannot distinguish causes.

The verdict carries a cache TTL (`CONNECTOR_DATAPLANE_DECISION_TTL`, 30 s). That window is a
security parameter: it is how long a revoked consent can still yield rows.

### The consent wildcard

A subject can grant to a **specific consumer** or to `"*"` — a standing decision covering
every consumer. An explicit per-party opt-out overrides the wildcard, so "share with
everyone except them" is expressible.

### Parking a negotiation

When a consumer negotiates for a consent-gated dataset and nobody has consented yet, the
provider EDC does not refuse — it *parks* the negotiation and the connector records an ask.
Asks expire on a TTL sweep (`CONNECTOR_CONSENT_PENDING_TTL`, 30 days), which terminates the
negotiation. When a subject decides in time, the connector resumes it.

### The owner perimeter

A participant admin acting for one organisation must not be able to delete another's asset.
Provider writes go through a perimeter check that resolves the target's owner and requires
the caller to hold `connector.provider.write` *within* that organisation. Platform admins and
service principals are exempt; a caller carrying no organisation claims at all is allowed
unless `CONNECTOR_OWNER_SCOPING_STRICT` is set.

## Configuration

`pydantic-settings`, prefix `CONNECTOR_`. Four `EDC_*` fields are read under their literal
name, without the prefix — all Management API, none of them DSP: the connector never dials
a protocol endpoint, and a counter-party's is resolved by DSP address through the identity
registry.

One variable is read by the container rather than by the settings model: `CONNECTOR_PORT`
(default `30001`) is the port the image binds *and* health-checks, so the provider and the
consumer run the same image on 30001 and 31001 without the probe drifting from the server.

### Identity and role

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_ROLE` | **required** | `provider` or `consumer`. Selects the EDC client and the mounted routers |
| `CONNECTOR_PARTICIPANT_ID` | `provider` | short id, used in event attribution |
| `CONNECTOR_PARTICIPANT_BASE_URL` | `https://rec.dataspaces.localhost` | own base URL; asset ids derive from it |
| `CONNECTOR_PARTICIPANT_DID` | `did:web:rec.dataspaces.localhost` | own DID |
| `CONNECTOR_CONSUMER_PARTICIPANT_DID` | `did:web:third-party.dataspaces.localhost` | the counterparty's DID, checked on consumer credentials |

### EDC

| Variable | Default | Meaning |
|---|---|---|
| `EDC_PROVIDER_MANAGEMENT_URL` | `http://localhost:19193/management` | Management API, provider role |
| `EDC_CONSUMER_MANAGEMENT_URL` | `http://localhost:29193/management` | Management API, consumer role |
| `EDC_API_KEY` | `insecure-dev-key` | **secret** — Management API key |
| `EDC_API_KEY_FILE` | — | read the key from a file instead |
| `CONNECTOR_NEGOTIATION_POLL_INTERVAL` / `_TIMEOUT` | `2.0` / `120.0` | seconds |
| `CONNECTOR_TRANSFER_POLL_INTERVAL` / `_TIMEOUT` | `2.0` / `120.0` | seconds. Separate from the negotiation pair: a negotiation can park on a person, a transfer cannot |
| `CONNECTOR_EDC_VAULT_FILE` | — | EDC filesystem vault; unset ⇒ `/internal/edr-jwks` serves no key |
| `CONNECTOR_EDR_SIGNER_ALIAS` | `participant-private-key` | vault alias of the EDR signing key |

### Governance and policy

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_GOVERNANCE_YAML_PATH` | `<workdir>/governance/governance.yaml` | the dataset catalogue |
| `CONNECTOR_GOVERNANCE_OVERLAY_NAME` | — | merges `governance.<name>.yaml` on top |
| `CONNECTOR_SHARING_OFFERS_PATH` | *(beside the governance file)* | the sharing-offer catalogue |
| `CONNECTOR_SHARING_OFFERS_OVERLAY_NAME` | — | same, for offers |
| `CONNECTOR_ODRL_PROFILE_PATH` | *(bundled energy profile)* | the purpose taxonomy and operand names |
| `CONNECTOR_VOCABULARIES_PATH` | *(beside the governance file)* | the semantic vocabulary registry. **A registered vocabulary with no cached copy stops startup** — empty by default, so this costs a default install nothing |
| `CONNECTOR_VOCABULARIES_OVERLAY_NAME` | — | merges `vocabularies.<name>.yaml`, replace-by-slug |
| `CONNECTOR_VOCABULARY_CACHE_DIR` | `data/vocabularies` | where the JSON-LD copies live — fetched material, so under `data/` like every other cache. Must be writable if any entry has a `source:` |
| `CONNECTOR_DATAPLANE_DECISION_TTL` | `30` | seconds a data plane may reuse an `allow` |
| `CONNECTOR_CONSENT_PENDING_TTL` | `P30D` | ISO-8601: how long a negotiation may wait on a subject |
| `CONNECTOR_CONSENT_PENDING_SWEEP_INTERVAL` | `3600.0` | seconds between expiry sweeps |

### Trust and authorisation

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_OIDC_ISSUER_URL` | — | Keycloak realm issuer. Set ⇒ JWTs are fully verified |
| `CONNECTOR_OIDC_INSECURE_DEV` | `true` | with no issuer, accept unverified JWTs. **Refused in production** |
| `CONNECTOR_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-connector` | own client credentials; the id is also the expected JWT audience |
| `CONNECTOR_KEYCLOAK_TOKEN_URL` | Keycloak on `172.17.0.1:9080` | token endpoint for outbound calls |
| `CONNECTOR_TRUST_ANCHOR_DID` | `did:web:trust-anchor.dataspaces.localhost` | issuer of user VCs; **its key is resolved from this DID's document**, not mounted |
| `CONNECTOR_TRUST_LIST_URL` | — | the dataspace trust list. An issuer not listed **active** is refused (`DSSC-TRF-05`) |
| `CONNECTOR_DID_WEB_USE_HTTPS` | `true` | resolve did:web over TLS. False only in dev, where Caddy serves :80 |
| `CONNECTOR_VC_INSECURE_DEV` | `true` | skip signature verification entirely. **Refused in production** |
| `CONNECTOR_CREDENTIAL_STATUS_PATH` / `_URL` | — | StatusList2021 source for revocation checks |
| `CONNECTOR_OWNER_SCOPING_STRICT` | `false` | refuse a provider write from a caller with no org claims |
| `CONNECTOR_ALLOW_UNKNOWN_PARTICIPANTS` | `false` | accept a DSP peer absent from the registry |
| `CONNECTOR_OWNER_ALIASES` | — | JSON map: foreign org alias → ds owner id |
| `CONNECTOR_OIDC_GROUP_ALIASES` | — | JSON map: foreign group → ds role bundle |

### Dependencies and storage

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_IDENTITY_REGISTRY_URL` | `http://identity-registry:30005` | participants, owners, memberships |
| `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL` | `60.0` | seconds; invalidated on registry change |
| `CONNECTOR_OWNERS_REGISTRY_CACHE_TTL` | `60.0` | seconds |
| `CONNECTOR_PROVENANCE_URL` | `http://localhost:30000` | where events go |
| `CONNECTOR_PROVIDER_CONNECTOR_URL` | `""` | consumer side: poll the provider for a parked decision. Empty disables |
| `CONNECTOR_DATABASE_URL` | Postgres on `172.17.0.1:35432/connector` | **secret** — embeds credentials |

### Notifications

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_NOTIFY_BACKENDS` | `""` | comma-separated: `smtp`, `webhook` |
| `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` | `""` | SSRF allowlist. **Empty rejects every webhook URL** |
| `CONNECTOR_NOTIFY_PORTAL_BASE_URL` | `https://portal.dataspaces.localhost` | link base in notifications |
| `CONNECTOR_NOTIFY_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_FROM` / `_TLS` | — / `587` / — / — / — / `true` | required when `smtp` is enabled |

Under `DS_ENV=production` a startup guard refuses to boot if the issuer is unset, either
`*_INSECURE_DEV` flag is true, the trust-anchor key is missing, or the EDC key or service
secret is still at its dev default.

## Persistence

Four tables in its own database (`connector_rec` / `connector_third_party`), Alembic-managed;
the service refuses to boot against a schema that is not at head.

| Table | Holds |
|---|---|
| `contract_agreements` | one row per agreement, with the **frozen ODRL policy snapshot** — the source of truth for purpose checks |
| `consent_requests` | the consent registry: subject, consumer (or `*`), dataset, purposes, controller, status |
| `consumer_access_requests` | consumer-side: what was asked for, its negotiation, agreement and transfer |
| `consumer_transfers` | consumer-side transfer records, so a subject sees only their own |

## Running it

| Task | Effect |
|---|---|
| `task provider:connector:run` | uvicorn on `:30001`, `CONNECTOR_ROLE=provider` |
| `task consumer:connector:run` | uvicorn on `:31001`, `CONNECTOR_ROLE=consumer` |
| `task provider:connector:debug` | same plus debugpy on `:30901` (`:31901` for consumer) |
| `task db:migrate:connector` | `alembic upgrade head` against both databases |
| `task -d services/connector test` | unit tests |

Ports: **30001** provider, **31001** consumer. The image serves 30001; the consumer moves it
with a command override.
