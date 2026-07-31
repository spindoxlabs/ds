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

**Ingests sixteen event types** on `POST /prov/events`, each validated against its own model.
The connector emits all of them; the dataset API's query audit reaches here indirectly,
forwarded by the connector.

| Group | Events |
|---|---|
| Discovery | `CataloguePublished`, `CatalogViewed` |
| Contracting | `AccessRequested`, `NegotiationStarted`, `NegotiationFinalized`, `NegotiationTerminated`, `ContractAgreementSigned` |
| Exchange | `TransferStarted`, `DataTransferCompleted`, `QueryExecuted`, `AccessRevoked`, `UsageObligationFulfilled` |
| Personal data | `ConsentGranted`, `ConsentRevoked`, `DataIngested`, `DataDisclosed` |

**Materialises each into a graph.** One handler per event type creates or updates the nodes
and edges the event implies, in a single transaction with the stored payload. Six PROV-O
relations are produced across all sixteen: `wasGeneratedBy`, `wasAttributedTo`,
`wasDerivedFrom`, `wasAssociatedWith`, `used`, `invalidated`.

**Answers three kinds of question.**

| Surface | For |
|---|---|
| `GET /prov/events` | operators — a filtered, paged event query with `hydra:*` counters |
| `GET /prov/my/events` | **a data subject, authenticated by their own credential** — their own history and nobody else's |
| `GET /prov/lineage/{iri}` | anyone with read access — a bounded breadth-first walk upstream, downstream or both |

**Keeps a compliance access log** (`/audit/log`) with a per-dataset summary, separate from the
event graph.

## How it works

### The subject's own view

`GET /prov/my/events` is the one route that does not take a scope. It authenticates with
`X-Subject-Id` + `X-User-VC` — an ES256 credential issued by the trust anchor — and filters on
the subject id **taken from the verified credential**, never from a query parameter. A person
can read their own history without an operator, and cannot read anyone else's by asking
nicely.

### Ingestion, traced

1. **Authorise.** `provenance.write` for a write, `provenance.read` or `.write` for a read.
2. **Validate.** The request resolves against a discriminated union on `event_type`; an
   unknown type or a missing required field is a `422` before any handler runs.
3. **One transaction** wraps the whole ingest.
4. **Idempotency.** If the caller's `event_id` is already stored, the response is
   `200 duplicate` and nothing is written. Supply an `event_id` — an event posted twice
   without one is stored twice.
5. **Materialise.** Nodes are upserted by IRI, edges are inserted only if that exact
   `(relation, subject, object)` triple does not already exist.
6. **Store the payload verbatim**, alongside five normalised columns (`agreement_id`,
   `data_product_id`, `provider_did`, `consumer_did`, `subject_id`) that reconcile the
   different names the same concept carries across event types.
7. **Respond** `201 created` with the event id and the activity node it produced.

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
| `PROVENANCE_TRUST_ANCHOR_DID` | `did:web:trust-anchor.dataspaces.localhost` | expected issuer of subject credentials |
| `PROVENANCE_TRUST_ANCHOR_KEY_PATH` | — | public key that verifies them |
| `PROVENANCE_VC_INSECURE_DEV` | `true` | with no key, accept unsigned subject VCs. **Refused in production** |
| `PROVENANCE_CREDENTIAL_STATUS_PATH` / `_URL` | — | StatusList2021 source for revocation checks |

Under `DS_ENV=production` the service refuses to start if the issuer or the trust-anchor key
is unset, or either `*_INSECURE_DEV` flag is true — the second pair is what keeps
`GET /prov/my/events` from trusting an unsigned credential.

## Persistence

Four tables, Alembic-managed.

| Table | Holds |
|---|---|
| `prov_nodes` | Entity / Activity / Agent, keyed by IRI, with an `external_meta` blob |
| `prov_relations` | the edges, unique on `(relation_type, subject, object)` |
| `domain_events` | the verbatim event payload plus the five normalised dimensions and an indexed `subject_id` |
| `access_log` | the compliance audit log: consumer, dataset, agreement, rows returned, duration |

Two properties worth knowing: a node's **type is fixed by the first event that mentions its
IRI** — later events update its fields but never change Entity into Activity — and
`external_meta` is *replaced*, not merged, on each upsert.

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
| `task db:migrate:provenance` | `alembic upgrade head` against both |
| `task e2e:lineage` | the live lineage flow |

Ports: **30000** provider, **31000** consumer.
