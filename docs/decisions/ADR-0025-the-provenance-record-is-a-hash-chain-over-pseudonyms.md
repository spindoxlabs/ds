# ADR-0025 — The provenance record is a hash chain over pseudonyms

**Date:** 2026-10-05
**Status:** accepted, implemented 2026-10-05
**Rules affected:** `L-16` (provenance is retained), `L-17` (append-only and tamper-evident,
new), `L-18` (person ids age out, new), `D-2` (codes, pseudonymous DIDs and hashes only)

## Context

The provenance store is a participant's evidence of what happened to its data, and the record
could be changed by the principal that writes it. Any holder of `provenance.write` could
soft-delete an entity, activity or agent, which hid it from every listing. Re-posting a node
overwrote its label and description. Nothing showed whether a stored event had been changed
since it was written.

The record also kept every person id in clear for the life of the deployment (`L-16`). The ids
are pseudonymous DIDs, so they are still personal data (`D-1`), and a deployment had no way to
limit how long the store links them.

The two goals pull against each other. A tamper-evident record must not change, and retention
must change it.

EDC does not model this. At the pinned tag (0.18.0) no module keeps an audit trail. The
decision record on entity updates (`docs/developer/decision-records/2023-02-22-update-entities`)
puts audit tables explicitly out of scope, and `extensions/common/events` publishes events
without recording them. DSP and DCP define no record of past exchanges either.

## Decision

1. **No route changes or deletes a record.** The node `DELETE` routes are removed. A node
   `POST` naming an existing IRI answers `409` with the node as recorded. A node changes only
   through an ingested event. Who holds `provenance.write` is unchanged.
2. **The event record is one hash chain per store.** Each `domain_events` row carries `seq`,
   `prev_hash` and `record_hash = sha256(prev_hash ‖ canonical(row))`. Appends are serialised
   by a Postgres advisory lock. `GET /prov/chain/verify` and `provenance-admin verify` recompute
   the chain, and migration `0004` chains the existing rows.
3. **The chain hashes a keyed pseudonym of every person id, never the id itself:**
   `pseud:HMAC-SHA256(PROVENANCE_SUBJECT_PSEUDONYM_KEY, id)`. Retention writes that same
   pseudonym into the row, so the hash does not change and the whole chain still verifies.
4. **Retention is a scheduled job** (`provenance-admin retention`) with a deployment-set
   period. Unset, ids stay in clear and the service warns. Nothing is deleted.

## Alternatives rejected

- **Hash a commitment to the payload and blank the payload at retention.** This also
  verifies, but a blanked payload proves nothing about its other fields. The pseudonym keeps
  every non-person field verifiable after retention.
- **Hash the id unsalted.** A guessed DID or address could then be tested against any record,
  so retention would remove nothing.
- **Delete aged records.** That contradicts `L-16`, and it cannot be told apart from tampering.
- **A database trigger that refuses `UPDATE` and `DELETE`.** It must make an exception for the
  retention job. It stops nobody who can drop it, which the chain detects anyway. The chain
  is enough. A deployment can add the trigger on its own.
- **Chain the graph as well.** The graph is a projection of the events. Chaining it doubles
  the write path, and its tables change legitimately (`L-8` reclassification, merged
  `external_meta`).

## Consequences

- The pseudonym key is set once per store and never rotated. A new key fails the
  verification of every existing record. Migration `0004` must run with the key the service
  uses.
- Removing the newest rows is visible only against a head recorded elsewhere. Recording the
  head outside the store is an operator duty.
- Pseudonymisation is not anonymisation. Whoever holds the key and a candidate DID can link
  them. That is how a subject still reads their own history (`L-11`).
- Rows written before the backfill are tamper-evident only from the backfill on.
