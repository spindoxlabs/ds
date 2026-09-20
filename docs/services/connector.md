# ds-connector

`ds-connector` is the control plane that sits beside an Eclipse Dataspace Components (EDC)
runtime and decides what that runtime is allowed to do.

The EDC speaks the Dataspace Protocol: it exchanges catalogues, negotiates contracts and
moves data. It does not know what a dataset is, who owns it, or whether a person consented
to it being shared. `ds-connector` knows all three, and answers the EDC every time a
decision is needed.

One codebase, one process per participant. `CONNECTOR_ROLE` is `provider`, `consumer` or
`both`, and decides which routers are mounted: `/provider/*` for a provider, `/consumer/*` for
a consumer, and everything else in every role. Whatever the role, a participant has **one**
EDC runtime, and the connector drives it through one management client. The dev stack runs a
provider (`rec`, `grid-operator`) and a consumer (`third-party`) as separate processes.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Access & Usage Policies Enforcement](../blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) · [DSSC · Data Exchange](../blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Cross-cutting (personal data)](../blueprints/dssc/cross-cutting.md) |
| Rules it enforces | [Rulebook · Policies](../rulebook/policies.md) · [Rulebook · Personal data](../rulebook/personal-data.md) |

In DSSC terms this is the **policy decision point** and the participant-side control plane.
The EDC is the protocol engine; this is the thing with an opinion.

## What it does

**Publishes governance into the EDC, and withdraws what it no longer declares.**
`POST /provider/sync` reads `governance.yaml`, compiles each exposed dataset into an EDC
asset, an ODRL policy definition and a contract definition, and pushes all three. The
compilation lives in [`libs/governance`](libs/governance.md); this service owns the sync,
the ordering and the refusal to publish a dataset whose purposes cannot be resolved. It is
a **reconcile**, not an append — see [What the sync removes](#what-the-sync-removes).

**Holds the consent registry.** `/consent/*` is where a data subject grants, rejects or
revokes sharing of their own rows. Subjects authenticate with a Verifiable Credential
(`X-Subject-Id` + `X-User-VC`), not a bearer token — the credential *is* the identity, and
no operator sits in between. Organisations and the onboarding service have their own routes
under the same prefix, guarded by ordinary permissions: `POST /consent/admin/shares` records a
subject's standing decision (`connector.consent.provision`), and `GET /consent/admin/shares`
reads back **who currently consents to one sharing offer**, for one named consumer
(`connector.consent.audience`). The read is a separate permission on purpose — a write grant
must not carry bulk subject enumeration with it, which is why `.audience` is in no bundle and
is reached by a person only through `connector.admin`.

**Registers consent another organisation collected.** A person consents where they are a
member; the organisation holding their data runs this connector. An **accepted collector** —
an organisation the identity registry lists for this participant — registers its members'
decisions here with its own client token, together with the typed keys their data is stored
under (`keys: ["pod:…"]`). The data plane then matches rows on those keys and never calls the
collector back. See [A collector registers consent](#a-collector-registers-consent) below.

**Answers every policy question.** `/internal/*` is the decision point:

| Endpoint | Asked by | Question |
|---|---|---|
| `GET /internal/consent/check` | EDC constraint functions, pending guard | does anyone consent to this dataset for this consumer and purpose? |
| `POST /internal/consent/asks` | EDC pending guard | park this negotiation and ask the subjects |
| `POST /internal/dataplane/authorize` | the dataset API | may these rows leave, and which ones? |
| `GET /internal/edr-jwks` | the dataset API | the public key that verifies an EDR token |
| `POST /internal/audit/query` | the dataset API | record that a query happened |

**Drives the consumer side of an exchange.** `/consumer/*` walks the whole flow — request a
catalogue over DSP, negotiate, poll to agreement, start a transfer, receive the EDR — and
records each access request so its requester can see and revoke their own. The requester is a
person holding a `ConsumerUser` credential, or **the organisation itself**, through its own
client token (see [Who may drive the consumer side](#who-may-drive-the-consumer-side)).

**Receives the EDR.** `POST /webhooks/edc-callback` is where this participant's EDC posts
`TransferProcessStarted` for a transfer the connector started. The event carries the EDR, and
the connector keeps it (see [The EDR arrives on a callback](#the-edr-arrives-on-a-callback)).

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
   collect the subjects whose latest decision authorises this consumer — an offer that
   `requires_offers` another admits them only while that one does too — translate their DIDs
   to the usernames the data plane joins on (`principals`), gather the typed keys registered
   with their consents (`keys`), and return a row filter. It is refused only when both lists
   are empty; the handler reads the list it knows.
7. **Combine.** The strictest verdict wins, and every refusal shares one response shape so a
   probe cannot distinguish causes.

The verdict carries a cache TTL (`CONNECTOR_DATAPLANE_DECISION_TTL`, 30 s). That window is a
security parameter: it is how long a revoked consent can still yield rows.

### The consent wildcard

A subject can grant to a **specific consumer** or to `"*"` — a standing decision covering
every consumer. An explicit per-party opt-out overrides the wildcard, so "share with
everyone except them" is expressible.

A decision that names an **offer** is wildcard-scoped, on both routes that record one:
`POST /consent/admin/shares`, where a service records it, and `POST /consent/my/shares`,
where the subject does. Naming a `consumer_id` is what makes either a per-party decision.

**Who decided is recorded, and it decides who may change it.** Every consent row carries
`decided_by` — `subject`, `operator`, `collector`, or `service` for a row the retired
plain-service path wrote — and a withdrawal may only be lifted by the authority that made it,
or by the subject (`D-15c`). So a service re-running onboarding over a member who
has since withdrawn is refused with a `409` naming the withdrawal, rather than appending a
grant that would win the cell on recency; a withdrawal that same service made earlier it
lifts as before. An operator with the person's instruction sends
`override_subject_withdrawal` on `POST /consent/admin/shares`, which records who authorised
it inside the row's evidence and stamps the row `operator`.

### A collector registers consent

Plan `a-collector-registers-consent-at-the-holder`. `POST /consent/admin/shares` classifies its
caller from the verified token, never from the body:

| Caller | Token | Speaks for | `decided_by` |
|---|---|---|---|
| an **accepted collector** | another organisation's client (`svc-ds-connector-<alias>`, `sub` ≠ this participant) holding `connector.consent.provision` | its own organisation | stated: `subject` (relayed) or `collector` |
| this participant's **own organisation** | its own organisation client — this is where an onboarding service belongs | this participant | stated, as above |
| the **deployment operator** | a **person** holding `connector.admin` | this participant | `operator` |

**A plain service token is refused** (`403`), and so is a participant operator's seat.
`connector.consent.provision` left the `ds-participant-admin` bundle and every plain service
client: a realm group and a shared service client are bound to no connector, so either could
write at any connector for anyone's members. A service that registered consent moves to its
organisation's client — see
[Operations · upgrading past connector schema 0012](../deployment/operations.md#upgrading-past-connector-schema-0012-consent-is-registered-by-an-organisation-client).
The operator is kept for one act no organisation token may perform: the evidenced
`override_subject_withdrawal` a person asks for (`D-15c`). Rows the retired service path wrote
keep `decided_by = "service"`, and the holder's own organisation or its operator may lift them.

For every caller the route then asks two questions, in order:

1. **May this organisation write here?** `GET /consent-collectors/check` on the identity
   registry, cached per pair for `CONNECTOR_COLLECTOR_CACHE_TTL` and dropped by the registry's
   invalidation hint (`POST /internal/registry/invalidate`). An outage serves the last answer
   for at most five TTLs, then refuses (`503`). A holder always collects for itself. Not
   accepted is a `403`.
2. **Is the subject its member?** The registry's answer names the organisation's owner id,
   and `GET /memberships/check` is asked against **that** organisation — never the offer's
   recipient (`D-21`). Not a member is a `403`, an unanswerable check a `503`.

What is recorded:

- the collector's DID on the row (`collector`), in the evidence record
  (`legal_basis.collector`) and in provenance, with the client that acted (`acted_by`);
- the keys on the row (`subject_keys`). A later registration replaces them, a withdrawal drops
  them; sending keys with a withdrawal is a `422`. Provenance records only `keys_supplied`, and
  only the registering organisation gets the keys back;
- a relayed withdrawal as the member's (`decided_by="subject"`), so neither a service nor the
  collector acting on its own can lift it.
- **why the organisation withdrew**, when it withdraws on its own (`decided_by="collector"`,
  e.g. a membership ending) and sends `reason`: one line, at most 200 characters, no `@`. It
  is stored as the row's `revocation_reason` and carried by the `ConsentRevoked` event, and
  no read returns it (`D-12a`). `reason` anywhere else — a grant, a relayed withdrawal, the
  operator — is a `422`, and so is `message`, which is not a spelling of it.

`missing_prerequisites` on each returned row names the offers this one is admitted only
together with (`requires_offers`) that the subject has not granted here. An offer that resolves
to no dataset at this connector is a `422`.

`GET /consent/admin/subject-shares?subject_id=…` is the read-back: one subject's decisions and
outstanding asks here, for the organisation that speaks for them, under the same two checks. It
is the narrow exception to `D-20`, and it is not a roster.

### Parking a negotiation

When a consumer negotiates for a consent-gated dataset and nobody has consented yet, the
provider EDC does not refuse — it *parks* the negotiation and the connector records an ask.
Asks expire on a TTL sweep (`CONNECTOR_CONSENT_PENDING_TTL`, 30 days), which terminates the
negotiation. When a subject decides in time, the connector resumes it.

### Who may drive the consumer side

Every `/consumer/*` route accepts one of two callers, and no other:

| Caller | Presents | Bound by |
|---|---|---|
| a **person** acting for this participant | `X-Subject-Id` + `X-User-VC`, a `ConsumerUser` credential linked to `CONNECTOR_CONSUMER_PARTICIPANT_DID` | the credential |
| **the organisation itself** — a batch job, the connector's operator tooling | a bearer from the organisation client `svc-ds-connector-<alias>` | its `sub` must be **this** connector's participant context, and its `scope` must hold EDC's scope for the call ds makes on its behalf |

The scope an organisation token must hold is EDC's scope for the management call ds makes,
not a permission ds invents:

| Route | Scope |
|---|---|
| `POST /consumer/catalog` | `management-api:catalog:read` (the route also takes `connector.consumer.read`, as before) |
| `POST /consumer/negotiate` | `management-api:negotiations:write` |
| `GET /consumer/requests`, `GET /consumer/negotiations/{id}` | `management-api:negotiations:read` |
| `POST /consumer/transfer`, `POST /consumer/requests/{id}/revoke` | `management-api:transfers:write` |
| `GET /consumer/transfers`, `GET /consumer/transfers/{id}`, `GET /consumer/edr/{id}` | `management-api:transfers:read` |
| `POST /consumer/flow` | `negotiations:write` **and** `transfers:write` |

Before any consumer route dials a counterparty, the connector checks that the counterparty is
a registered, active participant. It asks identity-registry's `GET /participants/resolve`, by
DSP address or DID, which answers with the DID, the address and the roles, and is cached for
`CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL`. It no longer reads the `/admin/participants`
listing for this. If identity-registry cannot be reached and nothing is cached, the check
fails closed.

EDC's own matcher decides, so `management-api:write` also satisfies
`management-api:negotiations:write`. A token naming another participant's context gets `403`,
whatever scopes it holds.

The organisation's requests are recorded under the actor `org:<context>`, apart from any
person's. Provenance records the client that acted (`acted_by.client_id`) and the organisation
it acted for (`actedOnBehalfOf`, the participant DID), as `DSSC-XCT-09` requires (rulebook
`D-20`). An organisation token **never** reads a person's consents: `/consent/my/*` accepts
only the subject's credential and answers `401` to the token.

`GET /consumer/negotiations/{id}` answers `404` when the ledger row for that negotiation
belongs to another actor. A person does not see the organisation's negotiations, and the
organisation does not see a person's.

### The EDR arrives on a callback

EDC 0.18.0's v5 management API has no EDR endpoint. When the connector starts a transfer, it
names a callback address:

- the URI is `CONNECTOR_EDC_CALLBACK_URL`;
- the event is `transfer.process.started`;
- the header is `X-Ds-Edc-Callback-Key`. EDC reads that header's value from **its own vault**
  under `CONNECTOR_EDC_CALLBACK_AUTH_CODE_ID` (default `ds-connector-callback-key`).

EDC posts `TransferProcessStarted` there, and `POST /webhooks/edc-callback` handles it:

- it compares the header with `CONNECTOR_EDC_CALLBACK_SECRET` (`401` otherwise);
- it refuses an event for another participant context (`403`) and an event that carries no
  EDR (`422`);
- it stores the EDR in `edr_entries`, keyed by transfer id. A later event for the same
  transfer refreshes it.

Consumer routes wait up to `CONNECTOR_EDR_WAIT_TIMEOUT` for the EDR to arrive and then answer
`504`. With no callback URL configured, they refuse to start a transfer (`503`): v5 cannot be
asked for the EDR afterwards, so such a transfer would be useless. A consumer process under
`DS_ENV=production` refuses to boot without the URL.

The callback carries no bearer token, because EDC's callback client sends only the
configured header. That header is the route's whole authentication.

### What the sync removes

`POST /provider/sync` makes EDC match the governance it was given. Everything it publishes
it also owns the withdrawal of: a dataset removed from `governance.yaml`, or one whose
`dataspace.expose` is turned off, has its **contract definition, then its policies, then
its asset** deleted — the only order EDC accepts, because a policy a definition still
references cannot be deleted. The asset ids removed come back in `withdrawn`.

Before this, the sync created and updated and never removed, so a withdrawn dataset kept
its asset, both policies and its contract definition and went on being offered over DSP —
while the run reported a *higher* published count than the one before it, because the count
is of what published rather than of what is on offer.

Three bounds:

- **Only assets this platform published.** Each carries the governance key it came from
  (`{profile-prefix}:datasetKey`); anything else in the runtime is left alone. An asset
  published by a version of ds that predates that property is also left alone — one sync
  under this version labels it, and only then can it be withdrawn.
- **Only datasets governance no longer declares.** A declared dataset that was *refused*
  (an unresolvable purpose, a dangling offer, an exposure conflict) keeps whatever it had:
  the refusal deliberately leaves a previously published version standing rather than
  tearing it down over a bad edit.
- **Plus an asset a still-declared dataset has just moved away from**, when its
  `dataspace.asset.id` changed in this run — otherwise renaming an id leaves the old asset
  on offer for ever.

An asset EDC refuses to delete because it has contract agreements (409) is reported in
`errors`, never swallowed.

**An asset under agreement is updated in place rather than replaced.** EDC refuses to delete
an asset a counterparty has negotiated for, and the sync used to keep the old one and move
on — so a governance edit to it published *nothing*, silently, for as long as the agreement
stood. It is now written with `PUT …/assets`, which is the call EDC provides for exactly
this. EDC's own documentation calls updating an asset a danger zone for offers already sent
out; the alternative is publishing a change that does not apply.

**`governance_yaml_path` in the request body reconciles too.** Pointing the sync at another
governance file withdraws everything that file does not declare — it is one rule ("make EDC
match this file"), not two. Do not use it as an ad-hoc publish.

### What the sync answers

The route's status code agrees with its body, and the body is the same `SyncResult` in
every case:

| Code | Meaning |
|---|---|
| `200` | nothing failed |
| `207 Multi-Status` | some datasets published or were withdrawn, and some failed |
| `502 Bad Gateway` | nothing published or was withdrawn, and something failed |

It answered `200` unconditionally before. In a live deployment every dataset failed at
`delete_asset` and the route still said `200`, so the deployment's publishing step — which
checked the status code — reported success against two empty catalogues. **Check `errors`,
not only the code**; the code is a summary of it.

### Who may publish

`POST /provider/sync` acts on the participant as a whole, so it is bounded by
**participant**, not by owner:

| Caller | Bound by |
|---|---|
| an organisation client (`svc-ds-connector-<alias>`) | its `sub` must name this connector's participant context |
| a person | an organisation claim resolving, in the owners registry, to this connector's participant DID — unless the deployment models no organisations and `CONNECTOR_OWNER_SCOPING_STRICT` is off |
| `connector.admin` | nothing — the deployment operator's grant crosses participants by design |
| any other service token | nothing — it names no participant; see below |

A participant's own organisation client may publish its own catalogue. `ds-participant-admin`
is a realm group and a realm group is bound to no connector, which is why the person case is
checked against the owners registry rather than taken on trust.

A plain service token names no participant, so there is nothing to bind it to. The control
is that the identity which publishes holds nothing else: `svc-ds-publisher` carries
`connector.provider.read` and `connector.provider.write`, and no `management-api:*` and no
`connector.admin`. See [operations](../deployment/operations.md#who-publishes).

### The owner perimeter

A participant admin acting for one organisation must not be able to delete another's asset.
Provider writes go through a perimeter check that resolves the target's owner and requires
the caller to hold `connector.provider.write` *within* that organisation. Platform admins and
service principals are exempt; a caller carrying no organisation claims at all is allowed
unless `CONNECTOR_OWNER_SCOPING_STRICT` is set.

An **organisation token** gets no such exemption. It may write only for its own participant
context. It may write to an unowned target, or to one whose owner resolves, in the owners
registry, to that context's DID. An owner that cannot be resolved is refused.

## Configuration

`pydantic-settings`, prefix `CONNECTOR_`. Three `EDC_*` fields are read under their literal
name, without the prefix — all Management API, none of them DSP: the connector never dials
a protocol endpoint, and a counter-party's is resolved by DSP address through the identity
registry.

One variable is read by the container rather than by the settings model: `CONNECTOR_PORT`
(default `30001`) is the port the image binds *and* health-checks, so the provider and the
consumer run the same image on 30001 and 31001 without the probe drifting from the server.

### Identity and role

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_ROLE` | **required** | `provider`, `consumer` or `both`. Selects the mounted routers |
| `CONNECTOR_PARTICIPANT_ID` | `provider` | short id, used in event attribution |
| `CONNECTOR_PARTICIPANT_BASE_URL` | `https://rec.dataspaces.localhost` | own base URL; asset ids derive from it |
| `CONNECTOR_PARTICIPANT_DID` | `did:web:rec.dataspaces.localhost` | own DID |
| `CONNECTOR_CONSUMER_PARTICIPANT_DID` | `did:web:third-party.dataspaces.localhost` | the counterparty's DID, checked on consumer credentials |

### EDC

| Variable | Default | Meaning |
|---|---|---|
| `EDC_MANAGEMENT_URL` | `http://localhost:19193/management` | this participant's Management API. **Never published on a host**: EDC does not check a token's audience, so network isolation is the control (ADR-0014) |
| `EDC_MANAGEMENT_API_VERSION` | `v5beta` | the version path segment; `v5` from EDC 0.19 |
| `EDC_PARTICIPANT_CONTEXT_ID` | *(`CONNECTOR_PARTICIPANT_DID`)* | this participant's context in its EDC — the organisation client's `sub` |
| `CONNECTOR_EDC_CALLBACK_URL` | — | this connector's `/webhooks/edc-callback` as the EDC reaches it. **Required for a consumer in production** |
| `CONNECTOR_EDC_CALLBACK_AUTH_CODE_ID` | `ds-connector-callback-key` | the EDC vault alias holding the callback header value |
| `CONNECTOR_EDC_CALLBACK_SECRET` | `insecure-dev-callback-key` | **secret** — the same value, compared here. `_FILE` reads it from a file |
| `CONNECTOR_EDR_WAIT_TIMEOUT` | `30.0` | seconds a consumer route waits for the EDR |
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
| `CONNECTOR_SERVICE_CLIENT_ID` | `svc-ds-connector` | the audience this service verifies on incoming tokens. Not a credential: nothing authenticates as it |
| `CONNECTOR_CLIENT_ID` / `_SECRET` | `svc-ds-connector-example-org` | **secret** — the organisation client this connector authenticates as, to its EDC and to every ds service. One credential per connector |
| `CONNECTOR_KEYCLOAK_TOKEN_URL` | Keycloak on `172.17.0.1:9080` | token endpoint for outbound calls |
| `CONNECTOR_TRUST_ANCHOR_DID` | `did:web:trust-anchor.dataspaces.localhost` | issuer of user VCs; **its key is resolved from this DID's document**, not mounted |
| `CONNECTOR_TRUST_LIST_URL` | — | the dataspace trust list. An issuer not listed **active** is refused (`DSSC-TRF-05`) |
| `CONNECTOR_DID_WEB_USE_HTTPS` | `true` | resolve did:web over TLS. False only in dev, where Caddy serves :80 |
| `CONNECTOR_VC_INSECURE_DEV` | `true` | skip signature verification entirely. **Refused in production** |
| `CONNECTOR_CREDENTIAL_STATUS_PATH` / `_URL` | — | StatusList2021 registers. `_URL` pins the **origin**; the credential names the register and the bit, so one value covers revocation and suspension. `_PATH` is one local register and answers only for the `statusPurpose` it publishes |
| `CONNECTOR_OWNER_SCOPING_STRICT` | `false` | refuse a provider write from a caller with no org claims |
| `CONNECTOR_ALLOW_UNKNOWN_PARTICIPANTS` | `false` | accept a DSP peer absent from the registry |
| `CONNECTOR_OWNER_ALIASES` | — | JSON map: foreign org alias → ds owner id |
| `CONNECTOR_OIDC_GROUP_ALIASES` | — | JSON map: foreign group → ds role bundle |

### Dependencies and storage

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_IDENTITY_REGISTRY_URL` | `http://identity-registry:30005` | participants, owners, memberships |
| `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL` | `60.0` | seconds; invalidated on registry change |
| `CONNECTOR_COLLECTOR_CACHE_TTL` | `60.0` | seconds an accepted-collector answer is reused; invalidated by the same hint; an outage serves it for at most five TTLs |
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

Under `DS_ENV=production` a startup guard refuses to boot in any of these cases:

- the issuer is unset or not `https`;
- either `*_INSECURE_DEV` flag is true;
- the trust anchor or the trust list is unset;
- the organisation client's secret still equals its id;
- the callback secret is still at its dev default;
- the process is a consumer and has no callback URL.

## Persistence

Five tables in its own database (`connector_rec` / `connector_third_party`), Alembic-managed;
the service refuses to boot against a schema that is not at head.

| Table | Holds |
|---|---|
| `contract_agreements` | one row per agreement, with the **frozen ODRL policy snapshot** — the source of truth for purpose checks |
| `consent_requests` | the consent registry: subject, consumer (or `*`), dataset, purposes, controller, status, who decided, the registering organisation and the subject's data keys |
| `consumer_access_requests` | consumer-side: what was asked for, its negotiation, agreement and transfer |
| `consumer_transfers` | consumer-side transfer records, so a subject sees only their own |
| `edr_entries` | consumer-side: the EDR each started transfer's callback delivered, by transfer id |

## Running it

| Task | Effect |
|---|---|
| `task provider:connector:run` | uvicorn on `:30001`, `CONNECTOR_ROLE=provider`. Pairs with the host-JVM EDCs of `dev:*`: a compose EDC does not publish its management port |
| `task consumer:connector:run` | uvicorn on `:31001`, `CONNECTOR_ROLE=consumer` |
| `task provider:connector:debug` | same plus debugpy on `:30901` (`:31901` for consumer) |
| `task db:migrate:connector` | `alembic upgrade head` against both databases |
| `task -d services/connector test` | unit tests |

Ports: **30001** provider, **31001** consumer. The image serves 30001; the consumer moves it
with a command override.
