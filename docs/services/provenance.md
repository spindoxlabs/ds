# ds-provenance

`ds-provenance` is one participant's memory of what happened to its data.

It accepts typed domain events — a catalogue was published, a contract was negotiated, a
query ran, a consent was revoked — and materialises each into a **W3C PROV-O graph**:
entities (datasets, agreements), activities (negotiations, transfers, queries) and agents
(participants, people), joined by PROV-O relations. It serves that graph as JSON-LD, walks it
as a lineage traversal, and keeps the original event payload verbatim so a question nobody
anticipated can still be answered.

One instance per participant, over its own database. A participant's provenance is not
readable by another participant — there is no federation here, deliberately.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Provenance, Traceability & Observability](../blueprints/dssc/data-interoperability/provenance-traceability-observability.md) |
| Rules it enforces | [Rulebook · Provenance and logging](../rulebook/provenance-and-logging.md) |

## What it does

**Ingests seventeen event types** on `POST /prov/events`, each validated against its own model.
The connector emits all of them; the dataset API's query audit reaches here indirectly,
forwarded by the connector.

| Group | Events |
|---|---|
| Discovery | `CataloguePublished`, `CatalogueWithdrawn`, `CatalogViewed` |
| Contracting | `AccessRequested`, `NegotiationStarted`, `NegotiationFinalized`, `NegotiationTerminated`, `ContractAgreementSigned` |
| Exchange | `TransferStarted`, `DataTransferCompleted`, `QueryExecuted`, `AccessRevoked` |
| Personal data | `ConsentGranted`, `ConsentRevoked`, `KeySuspension`, `DataIngested`, `DataDisclosed` |

**Materialises each into a graph.** One handler per event type creates or updates the nodes
and edges the event implies, in a single transaction with the stored payload. Seven PROV-O
relations are produced across all seventeen: `wasGeneratedBy`, `wasAttributedTo`,
`wasDerivedFrom`, `wasAssociatedWith`, `used`, `invalidated`, `actedOnBehalfOf`.
`services/provenance/tests/test_relation_vocabulary.py` sweeps the materialisers and fails on any term the
relations schema or the JSON-LD context does not also carry.

**Carries the references that tie a release to an assertion** ([ADR-0027](../decisions/ADR-0027-the-collector-asserts-whose-keys-it-registers.md)),
as SHA-256 hex digests the schema refuses in any other shape:

| Event | Field | Is |
|---|---|---|
| `ConsentGranted` | `keys_digest` | `sha256_hex("\n".join(sorted(set(key_index))))` over the keyed blind indexes of the keys the grant carries — never the keys |
| `ConsentGranted` | `assertion_ref` | `sha256_hex(canonical(legal_basis.key_assertion))`, canonical = sorted-keys compact JSON; the assertion itself is inside `legal_basis` |
| `QueryExecuted` | `decision_ref` | the data-plane allow's release link, echoed by the data plane beside `agreement_id` |
| `KeySuspension` | `keys_digest`, `action`, `reason` / `assertion_ref` | a holder suspending one key (`holder_change`), or a newer assertion lifting it |

All of them are inside the chained payload (`L-17`), so the connector's row or ledger edited
after the fact no longer matches the record. **Deploy this service before a connector that
sends them**: an older provenance ignores a field it does not know, and refuses an event type
it does not know.

**Answers three kinds of question.**

| Surface | For |
|---|---|
| `GET /prov/events` | operators — a filtered, paged event query with `hydra:*` counters |
| `GET /prov/my/events` | **a data subject, authenticated by their own credential** — their own history and nobody else's |
| `GET /prov/lineage/{iri}` | anyone with read access — a bounded breadth-first walk upstream, downstream or both |
| `GET /prov/chain/verify` | operators (`provenance.read`) — whether the event record is intact, and its head hash |

**Keeps a compliance access log** (`/audit/log`) with a per-dataset summary, separate from the
event graph.

**Keeps the event record append-only and tamper-evident** (`L-17`). Every stored event is
hash-chained onto the one before it, and `GET /prov/chain/verify` recomputes the chain. No
route changes or deletes anything: nodes are created and read, and a `POST` naming an IRI that
already exists answers `409` with the node as recorded.

**Lets person ids age out** (`L-18`). After `PROVENANCE_PERSON_ID_RETENTION_DAYS`, the
retention job replaces the person ids in a record with their keyed pseudonyms. The record
stays, the chain still verifies, and the subject still reads it.

## How it works

### The subject's own view

`GET /prov/my/events` is the one route that does not take a scope. It authenticates with
`X-Subject-Id` + `X-User-VC` — an ES256 credential issued by the trust anchor — together with
the person's own login token, which the identity registry binds to the credential's subject
(`GET /users/me` with that token, [ADR-0024](../decisions/ADR-0024-a-person-route-takes-the-persons-login.md)).
It filters on
the subject id **taken from the verified credential**, never from a query parameter. A person
can read their own history without an operator, and cannot read anyone else's by asking
nicely.

### Ingestion, traced

1. **Authorise.** `provenance.write` for a write, `provenance.read` for a read. A write
   is **audience-bound**: a service token must name `svc-ds-provenance` in `aud`, and a
   collector token (`svc-ds-collector-<alias>`) that also names another ds service is
   refused. A plain service token, meaning one that is not an organisation's client, may
   write only under `DS_ENV=dev`, with a warning in the log. `provenance.write` moved from
   the plain onboarding client to the organisation's collector client
   ([ADR-0026](../decisions/ADR-0026-an-organisation-acts-through-its-collector-client-one-audience-per-scope.md)).
   A connector writes with its organisation client's default token, which names this audience.
2. **Validate.** The request resolves against a discriminated union on `event_type`; an
   unknown type or a missing required field is a `422` before any handler runs.
3. **One transaction** wraps the whole ingest.
4. **Idempotency.** If the event id is already stored, the response is `200 duplicate` and
   nothing is written. A caller that supplies no `event_id` gets one derived from the event's
   own content — `sha256:<hex>` over the canonical payload, `occurred_at` included — so a
   retry is a no-op rather than a second copy. Supplying your own id is still the better
   choice: it is what lets you decide what "the same event" means.
5. **Materialise.** Nodes are upserted by IRI, edges are inserted only if that exact
   `(relation, subject, object)` triple does not already exist.
6. **Store the payload verbatim**, alongside five normalised columns (`agreement_id`,
   `data_product_id`, `provider_did`, `consumer_did`, `subject_id`) that reconcile the
   different names the same concept carries across event types.
7. **Chain** the row onto the head of the record (below), under a lock, in the same
   transaction.
8. **Respond** `201 created` with the event id and the activity node it produced.

### The hash chain

Each `domain_events` row carries `seq`, `prev_hash` and `record_hash`:

```text
record_hash = sha256(prev_hash + "\n" + canonical(row))
```

`canonical` is sorted-key JSON over every column except the row's own id and the server
receive time: `seq`, `event_id`, `event_type`, `occurred_at`, the payload, the activity node and
the five normalised columns. The first row's `prev_hash` is 64 zeros. There is one chain per
store, and appends are serialised by a Postgres advisory lock.

**Person ids enter the hash as pseudonyms.** Before hashing, `subject_id`, `user_did` and
`authorized_subject_ids` are replaced with `pseud:<HMAC-SHA256(key, id)>` under
`PROVENANCE_SUBJECT_PSEUDONYM_KEY`. Retention later writes the same pseudonym into the row,
so a pseudonymised row hashes as it did when it was written. A row given another person's
pseudonym does not.

`GET /prov/chain/verify` (and `provenance-admin verify`, exit 1 on failure) returns `ok`,
`records`, `pseudonymised`, `unchained`, `firstFailure` and `head`. A changed, removed or
reordered row fails at its sequence number. Removing the **newest** rows is visible only
against a head recorded somewhere else, so an operator records `head` outside the store.

The chain covers the event record. The graph and `access_log` are projections of it and are
not chained, though the API cannot change them either. `access_log` has no write route: every
row comes from a chained `QueryExecuted` event.

### Retention of person ids

`provenance-admin retention` (for a scheduled job) takes every record older than
`PROVENANCE_PERSON_ID_RETENTION_DAYS`, by `occurred_at`. It replaces the person ids in the
payload, the `subject_id` column, the activity node's `external_meta` and the matching
`access_log` rows with their pseudonyms, and sets `pseudonymised_at`. An agent node named by
a person id is renamed to the pseudonym once no newer record names that id in clear. If the
person comes back later, the new node is merged into the pseudonymous one. Nothing is deleted,
and the run logs counts and the cutoff, never an id. `GET /prov/my/events` matches the
subject's id and its pseudonym, so a subject's history does not shrink.

`acted_by.subject` is not a person id for this purpose. It names the operator or client that
decided something (`L-5`) and stays attributable.

### No PII, by construction

Payloads carry codes, pseudonymous DIDs and hashes — never names, addresses or readings. This
is load-bearing rather than aspirational: the event-query projection publishes an event's
*own* fields straight out of the stored payload, so **whatever an event declares is
published**. A new event type that carries personal data leaks it the moment somebody queries.

### Everything is JSON-LD

Every `/prov/*` response is `application/ld+json` with an `@context` pointing at
`GET /prov/context` — a self-hosted context document declaring the `prov`, `dcat`, `odrl` and
`ds` vocabularies plus the energy-domain terms. Lineage responses add `root`, `direction` and
`depth` alongside the `@graph`.

An **edge** in that graph publishes two separate facts. `ds:source` and `ds:target` carry
direction and are on every edge, which is what a consumer splits nodes from edges on.
`prov:entity` / `prov:activity` / `prov:agent` say what each end *is*, read off the node's own
type — so a `wasAssociatedWith` edge carries `prov:activity` and `prov:agent` and no
`prov:entity` at all. Where both ends share a type (`wasDerivedFrom`, `actedOnBehalfOf`) the
typed key holds both IRIs as a list and direction is read from `ds:source` / `ds:target`.

### Lineage direction

Every edge points backwards in time, so `direction` selects which way the walk follows them:

| `direction` | Follows | Answers |
|---|---|---|
| `upstream` | subject → object | how this came to be |
| `downstream` | object → subject | what was made from it |
| `both` | either | the union |

## Configuration

`pydantic-settings`, prefix `PROVENANCE_`.

| Variable | Default | Meaning |
|---|---|---|
| `PROVENANCE_DATABASE_URL` | Postgres on `172.17.0.1:35432/provenance` | **secret** |
| `PROVENANCE_CONTEXT_URL` | `https://provenance.dataspaces.localhost/prov/context` | the `@context` value in every response — set it to a URL that actually resolves |
| `PROVENANCE_MAX_LINEAGE_DEPTH` | `20` | hard cap on traversal depth, above whatever a request asks for |
| `PROVENANCE_OIDC_ISSUER_URL` | — | Keycloak realm issuer. Set ⇒ JWTs fully verified |
| `PROVENANCE_OIDC_INSECURE_DEV` | `true` | accept unverified JWTs when no issuer. **Refused in production** |
| `PROVENANCE_SERVICE_CLIENT_ID` | `svc-ds-provenance` | the expected JWT audience |
| `PROVENANCE_OIDC_GROUP_ALIASES` | `""` | JSON map: foreign group → ds role bundle |
| `PROVENANCE_TRUST_ANCHOR_DID` | `did:web:trust-anchor.dataspaces.localhost` | expected issuer; **its key is resolved from this DID's document**, not mounted |
| `PROVENANCE_TRUST_LIST_URL` | — | the dataspace trust list. An issuer not listed **active** is refused (`DSSC-TRF-05`) |
| `PROVENANCE_DID_WEB_USE_HTTPS` | `true` | resolve did:web over TLS |
| `PROVENANCE_VC_INSECURE_DEV` | `true` | skip signature verification entirely. **Refused in production** |
| `PROVENANCE_CREDENTIAL_STATUS_PATH` / `_URL` | — | as the connector's: **`_URL` is required outside dev**, and the register is read signed and verified. `_PATH` is one local, unsigned register for dev and tests |
| `PROVENANCE_CREDENTIAL_STATUS_CACHE_SECONDS` | `900` | the revocation latency |
| `PROVENANCE_IDENTITY_REGISTRY_URL` | — | the registry holding the Keycloak mappings (the anchor's). Required while the login binding is. It is asked with the person's token, so no client secret is needed |
| `PROVENANCE_PERSON_TOKEN_REQUIRED` | unset = required unless `DS_ENV=dev` | as the connector's |
| `PROVENANCE_SUBJECT_PSEUDONYM_KEY` | a dev constant | **secret**. The key person ids are pseudonymised under, in the chain and at retention. Set once per store and **never rotated**: a new key fails the verification of every existing record. The dev value is refused in production |
| `PROVENANCE_PERSON_ID_RETENTION_DAYS` | unset | days after which a record's person ids are pseudonymised. Unset keeps them in clear, and the service warns at startup outside dev |

Under `DS_ENV=production` the service refuses to start if the Keycloak issuer, the trust-anchor
DID or the trust list is unset, if the pseudonym key is the dev value, or if either
`*_INSECURE_DEV` flag is true — what keeps
`GET /prov/my/events` from trusting an unsigned credential, or one from an issuer this
dataspace no longer accredits.

## Persistence

Four tables, Alembic-managed.

| Table | Holds |
|---|---|
| `prov_nodes` | Entity / Activity / Agent, keyed by IRI, with an `external_meta` blob |
| `prov_relations` | the edges, unique on `(relation_type, subject, object)` |
| `domain_events` | the verbatim event payload plus the five normalised dimensions and an indexed `subject_id`; `seq`, `prev_hash`, `record_hash` (the chain) and `pseudonymised_at` |
| `access_log` | the compliance audit log: consumer, dataset, agreement, rows returned, duration |

Two properties worth knowing, both of which used to be the opposite: a node's **type follows
the latest statement about it**, so an IRI first seen in one position is reclassified when a
later event names it as what it is; and `external_meta` is **merged**, so
`NegotiationFinalized` adds the agreement id without dropping the offer id
`NegotiationStarted` recorded on the same node. A `None` on the incoming side means *this
event does not know* and never overwrites a value.

`access_log` is written only from `QueryExecuted`, with no direct write route: the query
audit already reaches the connector's PEP route and is forwarded here, so the compliance log
needs no second caller.

## Integration

| Direction | Counterpart |
|---|---|
| in | [`ds-connector`](connector.md) — the only writer, fire-and-forget, so a provenance outage never fails an exchange |
| in | [`ds-portal`](portal.md) — operator event tables, subject timelines, the lineage graph view |
| out | Keycloak JWKS only. It calls nothing else |

## Running it

| Task | Effect |
|---|---|
| `task provider:provenance:run` | uvicorn on `:30000` against the provider database |
| `task consumer:provenance:run` | uvicorn on `:31000` against the consumer database |
| `task db:migrate:provenance` | `alembic upgrade head` against both. Migration `0004` chains the existing rows, so it runs with the store's pseudonym key |
| `provenance-admin verify` / `backfill` / `retention` | in the image: check the chain, chain rows the migration missed, apply retention |
| `task e2e:lineage` | the live lineage flow |

Ports: **30000** provider, **31000** consumer.
