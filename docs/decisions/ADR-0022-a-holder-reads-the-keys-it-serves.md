# ADR-0022 — A holder reads the data keys it serves, and their history

**Date:** 2026-10-01
**Status:** accepted, implemented 2026-10-01
**Refines:** ADR-0015 (the collector registers at the holder) and ADR-0021 (the collector's list)
**Rules affected:** `D-20` (amended: the holder's own organisation may read the data keys on
its own connector's rows, as keys only)

## Context

A collector registers its members' decisions at the connector that holds their data
(ADR-0015), and sends each member's typed data keys with the decision: for example
`pod:<supply point>`, when a community (`example-rec`) collects consent to release meter
readings that a grid operator (`example-dso`) holds. The holder's data plane filters on those
keys (`subject_key_match`). Enforcement works.

What the holder cannot do is **read** the state it enforces. The grid operator's question is
operational: *which of my supply points may I release under this offer, as of now, and
since when?* Every existing read refuses it:

| route | answers | why it fails the holder |
|---|---|---|
| `GET /consent/admin/shares` | the audience, as subject DIDs | subject DIDs are opaque by construction; the holder cannot turn them into its own keys |
| `GET /consent/admin/subject-shares` | one subject, for the collector | the holder collected nothing |
| `GET /consent/admin/decisions` | a list, for the collector (ADR-0021) | only cells the caller collected; the holder collected none |

All three return keys only to the organisation that registered them (`_keys_for`). For the
collector's routes that is the right rule. It is the wrong rule for the holder reading its own
enforcement state.

**Why the holder may read them.** The holder is the controller of the release: it is the party
that discloses, so it is the one that has to demonstrate it disclosed only on consent (GDPR
Art. 5(2) and 7(1)). It cannot do that from a record it cannot read. And it learns very little
that is new. The keys identify the holder's **own** data (it already knows every supply
point it operates); the only new fact is *which of them are authorised, for whom, and since
when*, which is exactly what it is being asked to act on. The subject is told the holder
receives the key: a collector that sends keys says so in its consent text.

**Why the history needs a record of its own.** The consent rows cannot answer *when was this
key authorised, and when did that stop*:

- a withdrawal sets `subject_keys` to null on the row ("nothing it held stays behind");
- a re-registration with different keys updates `subject_keys` in place, with no new row;
- provenance carries no PII (`L-3`), and a supply-point key identifies a household, so it
  cannot go there either.

EDC and DSP have no consent concept (ADR-0015). There is nothing to reuse.

## Decision

1. **Two holder routes, beside the collector's.** Neither changes an existing route.
   - **The current keys**, per offer: the typed keys the data plane serves *now*.
   - **The key history**, per offer: every authorisation and deauthorisation of a key, with
     its time and cause.

   They are `GET /consent/admin/holder/keys?offer_id=…` and
   `GET /consent/admin/holder/key-events?offer_id=…`. The names are public API.
2. **Callers.** Exactly the holder, nobody acting for someone else:
   - this connector's **own organisation client** (`sub` = this participant). This is the
     caller for a scheduled export;
   - a **person** holding a new permission, `connector.consent.holder.read`, bound to this
     participant the way `_own_participant_only` binds a provider write;
   - the **deployment operator** (`connector.admin`), as everywhere else.

   **A collector is refused**: another organisation's client reads through ADR-0021's route
   and gets the decisions it collected, never the holder's whole key set. **A plain service
   token is refused**: it names no organisation (the same reason it cannot write consent).
   The permission is its own and is **not** bundled into `ds-participant-admin`, for the
   reason `connector.consent.audience` is not: a key list is a roster of authorised
   households, and nobody should get one as a side effect of a write grant.
3. **The current keys are the row filter's answer, not a second computation.** For each
   dataset the offer resolves to here, and for the consumer the offer names, the route takes
   the keys of `get_granted_subjects`, the same function the data plane's filter uses, so the
   list and enforcement cannot disagree. Per key: the key (type and value), the offer, the
   dataset, the recipient DID, and `authorised_since` (the earliest decision among the
   granting rows that carry it). Deduplicated per dataset.
4. **Keys only.** No subject DID, no username, no count of subjects, no other offer, no
   withdrawal reason (`D-12a`). The holder learns which of its own keys are authorised, and
   nothing about who stands behind them. That is why no membership check applies (`D-21`):
   the holder speaks for its own data, not for anyone's members.
5. **The history is an append-only key ledger at the holder.** It is written in the same
   transaction as the decision that changes a row's keys, one entry per key that row gains or
   loses: offer, dataset, consumer, key, `added` or `removed`, the cause (`grant`,
   `withdrawal`, `key_change`), the time, who decided, and the collector. It holds no subject
   id. It references the decision row (`consent_id`), which is never returned.
   - It is written by a **flush listener**, not by a call in each write path: four paths move
     a row's keys today (the standing grant, its key update and its withdrawal, and the
     subject's own approve and revoke by id), and a fifth would have to remember a call it
     cannot see.
   - It records **decisions**, not the served set. A key two decisions carry is still served
     after one of them withdraws, so the history can show a `deauthorised` for a key the
     current list still has. The current list is authoritative, and the history says so.
   - It is retained as long as the consent records it mirrors, and erased with them
     (`ON DELETE CASCADE` on `consent_id`).
   - **It starts when it ships.** At migration (`0014`), each granted row with keys seeds one
     `added` entry per key at its `decided_at`, with cause `backfill`. Withdrawals made before
     then cannot be recovered, because the rows no longer hold their keys. The route says
     where the ledger starts.
6. **An unknown offer is a `422`, a contract-based offer a `409`, and an offer that resolves
   to no dataset here a `422`**, as on ADR-0021's route. A recipient the owner registry cannot
   resolve is a `503`. Both routes are paged with an opaque cursor (`limit` 1–500), and
   `next_cursor: null` ends the list. The history also takes a `since`.
7. **A holder route.** It answers for this connector's rows. Nothing aggregates across
   connectors.
8. **The portal shows it.** A page in the provider section lists the current keys for a
   chosen offer, with a second tab for the history. It is shown to whoever holds the
   permission or `connector.admin`, and calls the routes with that person's token.

## Consequences

- A holder can see which of its keys it is authorised to release, from its own connector,
  without a file or an email from the collector. The collector's own export stays the
  collector's evidence; it is no longer the only place the list can be read.
- `D-20` gains a third, narrow exception. It already let a collector read its own members'
  decisions; it now also lets the holder's own organisation read the keys on its
  own rows, as keys only, never subjects. Anyone else's cross-subject read is still the
  audience permission.
- A deployment that wants the list in a table runs a scheduled job with the holder's
  organisation client. The connector stays authoritative; the table is a copy and needs its
  own retention.
- The ledger is a second write in every decision that touches keys. It has to share the
  transaction, so the history cannot drift from the rows.
- A deployment whose collectors send no keys gets an empty list, and the route says that no
  decision carries keys rather than answering as if nobody consented.
