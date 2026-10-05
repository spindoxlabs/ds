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
(`X-Subject-Id` + `X-User-VC`) **and their own Keycloak login token** (`Authorization:
Bearer`). The identity registry binds that token to the subject the credential names
(`GET /users/me`), and outside `DS_ENV=dev` the credential alone, or the credential with a
service token, is refused ([ADR-0024](../decisions/ADR-0024-a-person-route-takes-the-persons-login.md)).
No operator sits in between. Organisations and the onboarding service have their own routes
under the same prefix, guarded by ordinary permissions: `POST /consent/admin/shares` records a
subject's standing decision (`connector.consent.provision`), and `GET /consent/admin/shares`
reads back **who currently consents to one sharing offer**, for one named consumer
(`connector.consent.audience`). The read is a separate permission on purpose — a write grant
must not carry bulk subject enumeration with it, which is why `.audience` is in no bundle and
is reached by a person only through `connector.admin`. What a writer can read back is only its
own members' decisions: one subject at a time with `GET /consent/admin/subject-shares`, or
listed per offer, every state, with `GET /consent/admin/decisions`. Both read-backs require
their own scope, `connector.consent.collector.read`, and the write grant no longer opens them
([ADR-0026](../decisions/ADR-0026-an-organisation-acts-through-its-collector-client-one-audience-per-scope.md)).

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
8. **Name the release.** An allow carries `decision_ref` — the release link
   ([ADR-0027](../decisions/ADR-0027-the-collector-asserts-whose-keys-it-registers.md)):

   ```
   decision_ref = sha256_hex(agreement_id + "\n" + "\n".join(sorted(set(key_index))))
   ```

   over every key the allowed row filters serve, where `key_index` is the keyed blind index
   (`HMAC-SHA256(CONNECTOR_KEY_INDEX_SECRET, key)`) the key ledger stores. An allow that serves
   no key hashes `agreement_id + "\n"`; a deny carries `null`. The data plane treats it as
   opaque and echoes it, with `agreement_id`, in its own audit record and in
   `POST /internal/audit/query`, which forwards both to `QueryExecuted` (a value that is not a
   SHA-256 hex digest is a `422`). An auditor with the ledger recomputes it for a candidate key
   set without opening a key. **Upgrade the data plane first**: it parses the decision with
   `extra="forbid"`. A provenance event the connector cannot deliver — this one or any other —
   is logged at `ERROR` with its type and id.

The verdict carries a cache TTL (`CONNECTOR_DATAPLANE_DECISION_TTL`, 30 s). That window is a
security parameter: it is how long a revoked consent can still yield rows.

### The consent wildcard

A subject can grant to a **specific consumer** or to `"*"` — a standing decision covering
every consumer. An explicit per-party opt-out overrides the wildcard, so "share with
everyone except them" is expressible.

A decision that names an **offer** is wildcard-scoped, on both routes that record one:
`POST /consent/admin/shares`, where a service records it, and `POST /consent/my/shares`,
where the subject does. Naming a `consumer_id` is what makes either a per-party decision.

**Both expand the offer the same way, and both refuse the same offer.** The offers
catalogue is dataspace-wide while the datasets are one connector's, so a member can be shown
an offer this node holds nothing for; expanding it produces no row. **On either route that
is a `422`** — a decision recorded nowhere must not be answered as if it had been. The
member's route answered `200 []` until 2026-09-20.

**Who decided is recorded, and it decides who may change it.** Every consent row carries
`decided_by` — `subject`, `operator`, `collector`, or `service` for a row the retired
plain-service path wrote — and a withdrawal may only be lifted by the authority that made it,
or by the subject (`D-15c`). So a service re-running onboarding over a member who
has since withdrawn is refused with a `409` naming the withdrawal, rather than appending a
grant that would win the cell on recency; a withdrawal that same service made earlier it
lifts as before. An operator with the person's instruction sends
`override_subject_withdrawal` on `POST /consent/admin/shares`, which records who authorised
it inside the row's evidence and stamps the row `operator`.

**Each withdrawal is its own record** ([ADR-0020](../decisions/ADR-0020-each-withdrawal-is-its-own-record.md)).
When an authority withdraws over a withdrawal another authority made, in either order (the
subject over a collector's, a collector over the subject's, one collector over another), the
new withdrawal is a row of its own with its own time and reason. The standing row keeps its
authority, time and reason as written. A repeat by the same authority records nothing. The
data is refused from the first withdrawal on.

**The member's withdrawal is the one presented.** Whenever the subject's own withdrawal
stands, every current-decision read returns it, even under a newer withdrawal by somebody
else: `/consent/my/shares`, `/consent/admin/subject-shares`, `/consent/status`, the consent
checks and the row filter. Lifting the cell needs authority over every withdrawal standing in
it, so only the subject (or the operator's evidenced override) lifts a cell the subject
withdrew. The writer's own answer is the row it recorded.

### A collector registers consent

Plan `a-collector-registers-consent-at-the-holder`. `POST /consent/admin/shares` classifies its
caller from the verified token, never from the body:

| Caller | Token | Speaks for | `decided_by` |
|---|---|---|---|
| an **accepted collector** | another organisation's client, `sub` ≠ this participant: its collector client `svc-ds-collector-<alias>` (ADR-0026) or its `svc-ds-connector-<alias>`, with a token asked for `connector.consent.provision` | its own organisation | stated: `subject` (relayed) or `collector` |
| this participant's **own organisation** | its own organisation's client, collector or connector — this is where an onboarding service belongs | this participant | stated, as above |
| the **deployment operator** | a **person** holding `connector.admin` | this participant | `operator` |

**A plain service token is refused** (`403`), and so is a participant operator's seat.
`connector.consent.provision` left the `ds-participant-admin` bundle and every plain service
client: the bundle was then held through a realm group, and a shared service client is bound
to no connector, so either could write at any connector for anyone's members. (Realm groups
now grant nothing at all, ADR-0023.) A service that registered consent moves to its
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
  collector acting on its own can lift it. Relayed over the collector's own withdrawal, it is
  a second row and the collector's is left as written (ADR-0020).
- **why the organisation withdrew**, when it withdraws on its own (`decided_by="collector"`,
  e.g. a membership ending) and sends `reason`: one line, at most 200 characters, no `@`. It
  is stored as the row's `revocation_reason` and carried by the `ConsentRevoked` event, and
  no read returns it (`D-12a`). `reason` anywhere else — a grant, a relayed withdrawal, the
  operator — is a `422`, and so is `message`, which is not a spelling of it.

`missing_prerequisites` on each returned row names the offers this one is admitted only
together with (`requires_offers`) that the subject has not granted here. An offer that resolves
to no dataset at this connector is a `422`, here and on the member's own route alike — see
"The consent wildcard" above.

**The organisation asks for each act, and the token names this connector**
([ADR-0026](../decisions/ADR-0026-an-organisation-acts-through-its-collector-client-one-audience-per-scope.md)).
`connector.consent.provision`, `connector.consent.collector.read` and `connector.provider.write`
are optional on the organisation client. The default token, which the connector sends to
every counterparty, carries none of them. Each of these scopes, and also
`connector.consent.audience` and `connector.disclosure.record`, adds the audience
`svc-ds-connector`. The guards require it in a service token's `aud`, and they refuse a
collector token that also names another ds service. A collector client is never the
connector: it is refused on `/provider/*` writes, on the holder key list and on `/consumer/*`.

The offer-audience read (`GET /consent/admin/shares`) and disclosure records
(`POST /admin/disclosure`) moved from the plain `svc-ds-onboarding` client to the collector
client. Neither request names an organisation, so the token's `sub` supplies it. It must be
this connector's own organisation, or a collector accepted here, which is the write's
admission. A plain service token on these two routes is accepted **only under
`DS_ENV=dev`**, with a warning in the log. An accepted collector reads the offer's whole
audience here, including subjects another collector registered; this is a stated residual.

`GET /consent/admin/subject-shares?subject_id=…` is the read-back: one subject's decisions and
outstanding asks here, for the organisation that speaks for them, under the same two checks. It
is the narrow exception to `D-20`. It lists only the cells the calling organisation **collected**
(the predicate `GET /consent/admin/decisions` uses), plus the asks: membership is checked now,
and a DID can carry history from an organisation the person left, which the next one does not
read ([ADR-0028](../decisions/ADR-0028-a-member-who-moves-gets-a-new-did-and-takes-the-login.md)).
The deployment operator reads every cell.

`GET /consent/admin/decisions?offer_id=…` is the same read-back as a list, for one offer
([ADR-0021](../decisions/ADR-0021-an-organisation-lists-its-own-members-decisions.md)). It
answers *who withdrew*, which the audience cannot: the audience lists grants only, so a
withdrawn subject is absent from it. The bound is exactly the per-subject one:

- the acceptance check runs once. A caller not accepted gets `403` (`503` when the registry
  cannot say), never an empty list;
- the membership check runs per subject on the page. A subject who is no longer a member is
  left out. A subject the registry cannot answer for makes the call a `503`;
- only the cells the caller's organisation collected are listed. The organisation collected
  a cell if a row there carries its `collector`, or if it registered the grant's evidence
  (`legal_basis.collector`). A member's withdrawal relayed by another organisation over this
  organisation's grant is still listed to it.

Each cell shows its presented decision, which is the row `subject-shares` returns for it (the
member's own withdrawal whenever one stands). A subject who never decided is absent.

```json
{
  "offer_id": "…", "datasets": ["…"], "limit": 50, "next_cursor": "…",
  "subjects": [{"subject_id": "did:…", "decisions": [{
    "dataset_id": "…", "consent_id": "…", "state": "granted | withdrawn",
    "decided_by": "subject | collector | service | operator", "collector": "did:… | null",
    "decided_at": "…", "revoked_at": "…", "keys": ["pod:…"]}]}]
}
```

`limit` runs from 1 to 100 subjects per page (default 50), and `cursor` takes the previous
page's `next_cursor`. A page can be short, or even empty, and still not be the last. Only
`next_cursor: null` ends the list. `keys` go back only to the organisation that registered them,
and the withdrawal `reason` to nobody (`D-12a`). An unknown offer or one resolving to no
dataset here is a `422`, a contract-based offer a `409`, and a cursor the route did not issue a
`422`. It is a holder route: a collector that registers at several holders asks each one.

### The holder reads the keys it serves

The routes above are the collector's. The holder — the organisation this connector serves —
reads its own enforcement state with two routes of its own
([ADR-0022](../decisions/ADR-0022-a-holder-reads-the-keys-it-serves.md)). They answer the
holder's operational question: *which of my keys may I release under this offer, and since
when?*

| Route | Answers |
|---|---|
| `GET /consent/admin/holder/keys?offer_id=…` | the typed keys the data plane serves the offer's recipient **now**, per dataset |
| `GET /consent/admin/holder/key-events?offer_id=…` | every key a decision here started or stopped carrying, oldest first |

**Who may call them.** This connector's own organisation client (the caller for a scheduled
export), the deployment operator (`connector.admin`), or a person granted
`connector.consent.holder.read` for an organisation that resolves to this participant. A
collector is refused (`403`, naming `GET /consent/admin/decisions`), and so is a plain service
token. The permission is held by every organisation client and is in no bundle: a key list is a
roster of authorised households, so no operator seat carries it by default.

**Keys only.** Neither route names a subject, counts subjects or returns a withdrawal reason.

**The current list is the row filter's answer.** It is computed with `get_granted_subjects`
and the same `D-14` admission `GET /internal/consent/check` applies, for the offer's
`recipients.recipient` resolved to a DID through the owner registry. So it cannot disagree with
what the data plane serves: a use offer whose prerequisite is missing lists nothing for that
subject. An unresolvable recipient is a `503`.

```json
{
  "offer_id": "…", "recipient": "example-dso", "recipient_did": "did:…",
  "purpose": ["…"], "recipient_role": "metering",
  "datasets": [{"dataset_id": "…", "key_count": 2, "grants_without_keys": false}],
  "limit": 100, "next_cursor": null,
  "keys": [{"dataset_id": "…", "key": "pod:…", "key_type": "pod", "value": "…",
            "authorised_since": "…"}]
}
```

`grants_without_keys` says that some standing grant carries no key, so nothing is served for it:
an empty key list must not read as "nobody consents" when the truth is "no key was sent".

**The history is a key ledger.** `consent_key_events` is appended by a flush listener
(`db/key_ledger.py`) in the same transaction as the decision row, for every path that moves a
row's keys: a grant, a withdrawal (the subject's own revoke by id included), and a new
registration with other keys. Entries hold no subject id; they reference the decision row,
and since migration `0016` they **outlive it**: erasing the row nulls the reference, and the
entry is kept for the key-record retention period (see below). Each entry names the collector's
key assertion it was written under (`assertion_ref`). The ledger records **decisions**, not the served set: a key two decisions
carry stays served after one withdraws, so the current list is the one to act on. Migration
`0014` seeds one `backfill` entry per key of each grant standing when it runs; withdrawals
before then cannot be recovered, and every history page says so in `note`.

```json
{
  "offer_id": "…", "datasets": ["…"], "limit": 100, "note": "…", "next_cursor": null,
  "events": [{"dataset_id": "…", "consumer_id": "*", "key": "pod:…",
              "event": "added | removed",
              "cause": "grant | withdrawal | key_change | backfill | holder_suspension | suspension_lifted",
              "at": "…", "decided_by": "subject", "collector": "did:…"}]
}
```

`decided_by` and `collector` name who took the decision behind the entry. For a `key_change`
that is whoever re-sent the keys, while the decision row keeps naming who granted.

Both routes page with an opaque `cursor`, `limit` 1–500 (default 100); the history also takes
`since`. An unknown offer or one resolving to no dataset here is a `422`, a contract-based offer
a `409`. The portal shows both at **Provider → Authorised keys**.

### The collector asserts whose keys it registers

A holder releases a key's data on the collector's word that the key is the member's — for a
`pod:` key, that the supply point is theirs. The platform cannot check that; it records the
word so that it can be audited and the collector answers for it
([ADR-0027](../decisions/ADR-0027-the-collector-asserts-whose-keys-it-registers.md), `D-12b`).

**The assertion.** A registration carrying keys may carry `legal_basis.key_assertion`, codes
and hashes only (`extra="forbid"`):

```json
{
  "terms": "rec-pod-assertion/1",
  "terms_sha256": "<sha256 of the exact responsibility statement accepted>",
  "method": "uploaded-document | offline-with-evidence",
  "verification_ref": "<the collector's verification record, a UUID>",
  "verified_by": "<HMAC-SHA256 of the verifying operator, under the collector's own key>",
  "verified_at": "<ISO-8601 with timezone, not in the future>",
  "evidence": [{"kind": "utility_bill | id_document | other", "sha256": "<of the file bytes>"}]
}
```

At least one evidence digest is required; a plain offline check is not a method. No fiscal
code, no supply point and no hash of either. Without keys, an assertion is a `422`.

**What the holder requires.** The offer's governance declares it:

```yaml
key_assertion:
  required: true
  methods: [uploaded-document, offline-with-evidence]
# or the shorthand:  key_assertion: required
```

Missing when required, or a method not listed, is a `422`. An offer that declares nothing
requires it for a `pod:` key outside `DS_ENV=dev`; in dev and for other key types it does not
(one that is sent is still validated). `governance-grid-operator/sharing-offers.yaml` declares
it on both of the grid operator's offers.

**One subject per `pod:` key.** A second subject registering a key another holds here is a
`409` that names neither; the same subject re-registering is fine. The owner
(`consent_key_owners`, by blind index) is released when the last grant carrying the key ends,
and kept for the retention period.

**On the record.** The assertion is stored in the row's `legal_basis` and once more, by its
`assertion_ref`, in `consent_key_assertions`. `ConsentGranted` carries it, `assertion_ref` and
`keys_digest = sha256_hex("\n".join(sorted(set(key_index))))`; a registration that changes the
keys or the assertion is a new event, an identical re-run is a duplicate. A newer assertion on
a standing grant replaces only `legal_basis.key_assertion`.

**The collector's read-back** (`GET /consent/admin/subject-shares`) lists, beside `keys`, the
`suspended_keys` the holder has suspended.

#### What a community asserts, in plain words

When your community registers a member's decision at a grid operator together with the
member's supply point, it tells the grid operator: *this supply point is this member's; we
checked, and we can show how.* The grid operator releases the readings on your word and does
not check again. So the platform keeps, beside the decision, which statement of responsibility
you agreed to, how you checked (a document the member uploaded, or an offline check of which
you kept a copy), when, a code for the operator who checked that only your community can turn
back into a name, and a fingerprint of each document you relied on — never the document
itself. Your community answers for the statement being true when it was made. Keep the
documents as long as the platform keeps the record (ten years by default) so the fingerprints
can be matched to them. If a supply point changes hands, withdraw the registration; if the
grid operator learns it first, it suspends the supply point until your community checks again.

### The holder suspends a key

`POST /consent/admin/holder/keys/suspend` `{"key": "pod:…", "reason": "holder_change"}` —
for this connector's own organisation client or the deployment operator; a person who holds
only `connector.consent.holder.read` reads and does not suspend, and a collector or a plain
service token is refused (`403`).

It takes the key out of the served set for every decision carrying it (the row filter, the
holder's key list and the audience agree, because `get_granted_subjects` drops it), writes a
`holder_suspension` ledger entry per such decision and a `KeySuspension` provenance event
(the key's digest, never the key), and changes no decision. The answer is
`{key, suspended_at, reason, grants_affected, already_suspended}`; repeating it is a no-op.

**Only a newer verification lifts it**: a registration of the key whose
`key_assertion.verified_at` is later than `suspended_at` — for the same member or, once the
old registration is withdrawn, a new one. Anything older is a `409`. Lifting writes
`suspension_lifted` entries and a `KeySuspension` event with `action: lifted`. The suspension
acts on keys: a dataset filtered by usernames is not narrowed by it.

### The key records are retained, then purged by an operator

The key ledger, the key owners, the key assertions and the lifted suspensions are the
holder's evidence of what it released and on whose word. They are **not** deleted with a
consent row and nothing deletes them on a schedule. After
`CONNECTOR_KEY_RECORD_RETENTION_DAYS` (default 3650 — the Italian ordinary limitation period,
art. 2946 c.c., **pending legal counsel**) from when a key stopped being carried, an operator
runs:

```
python -m connector.db.retention purge          # counts only
python -m connector.db.retention purge --apply  # deletes
```

It removes a key's ledger entries once no grant carries the key and its newest entry is older
than the period, owners released and suspensions lifted before it, and assertions nothing
remaining references. A key still carried, an active owner and a suspension in force are never
touched. The basis for keeping them after a subject's erasure is GDPR Art. 17(3)(e).

### Parking a negotiation

When a consumer negotiates for a consent-gated dataset and nobody has consented yet, the
provider EDC does not refuse — it *parks* the negotiation and the connector records an ask.
Asks expire on a TTL sweep (`CONNECTOR_CONSENT_PENDING_TTL`, 30 days), which terminates the
negotiation. When a subject decides in time, the connector resumes it.

### Who may drive the consumer side

Every `/consumer/*` route accepts one of two callers, and no other:

| Caller | Presents | Bound by |
|---|---|---|
| a **person** acting for this participant | `X-Subject-Id` + `X-User-VC`, a `ConsumerUser` credential linked to `CONNECTOR_CONSUMER_PARTICIPANT_DID`, **plus the person's own login token** bound to it (ADR-0024) | the credential |
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

The stored EDR is **sealed at rest**, as below: EDC's own cache keeps an EDR in its vault
(`VaultEndpointDataReferenceCache`), and the bearer it carries is as live here as there.

### Data keys and EDRs are sealed at rest

Two kinds of value in this database are worth something to whoever reads a backup or a
replica: a subject's data keys (`pod:…`, which the data plane filters on) and an EDR (a
live bearer for a counterparty's data plane). Both are stored as ciphertext
(`connector.db.sealed`), and nothing that reads them changes:

| Column | Stored as |
|---|---|
| `consent_requests.subject_keys` | Fernet ciphertext of the JSON list |
| `consent_key_events.key` | Fernet ciphertext, plus `key_index` |
| `edr_entries.authorization`, `edr_entries.data_address` | Fernet ciphertext |

**`key_index` keeps equality lookups.** A ciphertext is randomised, so two seals of one key
never compare equal. `key_index` is `HMAC-SHA256(CONNECTOR_KEY_INDEX_SECRET, key)`:
deterministic, so a lookup or a unique constraint on a key goes on that column, and keyed,
so nobody without the secret can compute the index of a known POD. It is set from the key on
every write; no write path has to remember it.

**A value no configured key opens is an error**, never the stored text: a data plane handed
ciphertext as a key would match nothing and report it as a match.

**Rotation.** `CONNECTOR_AT_REST_KEYS` is a list, newest first: the first seals, every one
opens. Prepend a new key, restart, run `python -m connector.db.sealed reseal`, then drop the
old key. To change `CONNECTOR_KEY_INDEX_SECRET`, run the same `reseal` before serving traffic:
until it has run, a lookup by index misses rows indexed with the old secret. Migration `0015`
sealed the rows already stored, with the keys configured when it ran. It refuses to run
outside `DS_ENV=dev` while the keys are the committed dev values.

### Reconciling a withdrawal across connectors

An offer can be bound at more than one connector: the collecting organisation's own, and a
holder of the same subjects' data that it registers at as a collector. A member's
withdrawal is written to each, one call per connector, and a call can fail. A withdrawal
that reached one connector leaves the other still serving.

`python -m connector.reconcile` closes that gap. It runs as the collecting organisation
(`CONNECTOR_CLIENT_ID` / `CONNECTOR_CLIENT_SECRET`), reads `GET /consent/admin/decisions` for
each `--offer` at every `--connector` given, and compares each subject's decisions:

- **a withdrawal newer than a grant at another connector is propagated there**
  (`POST /consent/admin/shares`, `enabled: false`). It is relayed as the subject's when the
  subject withdrew, and as the collector's otherwise, with a fixed cause;
- **a grant is never propagated.** A grant that reached only one connector, or a subject one
  connector has no decision about, is flagged and left for the onboarding retry: that side
  serves less than it may, not more;
- `--dry-run` writes nothing and flags what it would write.

```bash
python -m connector.reconcile --offer example-research \
  --connector https://connector.rec.example.org \
  --connector https://connector.dso.example.org
```

Run it periodically. It is idempotent: a reconciled state writes nothing. It logs counts,
connector hosts and consent ids, never a subject id. It exits `0` when the connectors agree
or were brought to agree, `1` when something is flagged, a write failed or a connector could
not be read, and `2` on a configuration error.

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
is held inside an organisation, and an organisation is bound to no connector, which is why the
person case is checked against the owners registry rather than taken on trust. A person with
no organisation holds no provider permission at all unless they are the platform administrator
([ADR-0023](../decisions/ADR-0023-a-persons-authority-has-two-levels.md)), so the
no-organisations exemption no longer decides anything for a person.

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
| `CONNECTOR_CREDENTIAL_STATUS_PATH` / `_URL` | — | StatusList2021 / Bitstring registers. **`_URL` is required outside dev** (guard, and a 503 at the point of use). It pins the **origin**; the credential names the register and the bit, so one value covers revocation and suspension. The register is read as the anchor's **signed** VC-JWT and verified against the key its DID document publishes; an unsigned register and an unknown entry type are refused. `_PATH` is one local, unsigned register for dev and tests, and answers only for the `statusPurpose` it publishes |
| `CONNECTOR_CREDENTIAL_STATUS_CACHE_SECONDS` | `900` | how long a verified register is reused, which is the revocation latency (EDC's default) |
| `CONNECTOR_PERSON_TOKEN_REQUIRED` | unset = required unless `DS_ENV=dev` | the person's login token on person routes (ADR-0024). `false` is a logged transition switch for a caller that does not forward it yet |
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
| `CONNECTOR_AT_REST_KEYS` | committed dev key | **secret** — Fernet keys, comma-separated, newest first; seals data keys and EDRs |
| `CONNECTOR_KEY_INDEX_SECRET` | committed dev value | **secret** — HMAC key of the data keys' blind index |
| `CONNECTOR_KEY_RECORD_RETENTION_DAYS` | `3650` | days the key ledger, owners, assertions and lifted suspensions are kept after a key stopped being carried; read by the purge only (pending legal counsel) |

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
- either at-rest key is still the committed dev value (a key list that is not valid Fernet
  refuses to boot in every environment);
- the process is a consumer and has no callback URL.

## Persistence

Its own database (`connector_rec` / `connector_third_party`), Alembic-managed; the service
refuses to boot against a schema that is not at head.

| Table | Holds |
|---|---|
| `contract_agreements` | one row per agreement, with the **frozen ODRL policy snapshot** — the source of truth for purpose checks |
| `consent_requests` | the consent registry: subject, consumer (or `*`), dataset, purposes, controller, status, who decided, the registering organisation and the subject's data keys |
| `consumer_access_requests` | consumer-side: what was asked for, its negotiation, agreement and transfer |
| `consumer_transfers` | consumer-side transfer records, so a subject sees only their own |
| `edr_entries` | consumer-side: the EDR each started transfer's callback delivered, by transfer id, sealed |
| `consent_key_events` | the holder's key ledger (ADR-0022), with `assertion_ref`; outlives its decision row |
| `consent_key_assertions` | collectors' key assertions, by `assertion_ref` (ADR-0027) |
| `consent_key_owners` | the subject holding each `pod:` key here, by blind index; one active per key |
| `consent_key_suspensions` | the holder's suspensions of a key; one active per key |

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
