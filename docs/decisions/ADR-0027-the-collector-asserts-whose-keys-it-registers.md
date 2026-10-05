# ADR-0027 — The collector asserts whose keys it registers, and the holder can show it

**Date:** 2026-10-05
**Status:** accepted, implemented 2026-10-05
**Refines:** ADR-0015 (the collector registers at the holder), ADR-0022 (the holder's key
ledger), ADR-0025 (the provenance hash chain), ADR-0026 (the collector client)
**Amends:** ADR-0022 decision 5 (the ledger is no longer erased with its decision row)
**Rules affected:** `D-12` (the evidence record gains the key assertion), `D-12b` (new), `L-1`
(a seventeenth event type, `KeySuspension`)

## Context

A collector (a community, `example-rec`) registers its members' decisions at the holder
(`example-dso`) with their typed data keys, and the holder's data plane releases the readings
of those keys (ADR-0015). For a `pod:` key the holder releases a household's metering data on
the collector's word that the supply point is the member's. The agreement in force between
such a pair is a plain export by supply point: no fiscal code goes on the wire, and the holder
does not look the customer up at grant time.

So the platform cannot *check* ownership. What it can do is make the collector's word
**auditable** and make the collector **answerable** for it. Before this decision, an auditor
could follow a key from the ledger to the decision row and on to the collector's
`submission_ref`, and no further:

- nothing recorded **what** the collector asserted, **how** it verified, **when**, or on
  **what** evidence;
- the decision row and the ledger could be edited unnoticed, because the provenance chain
  carried no keys and no digest of them;
- a read could not be tied to the grants that authorised it: the data plane's report carried
  the agreement and no key set;
- two subjects could be registered for the same supply point at one holder;
- erasing a decision row cascaded away its key history (ADR-0022 decision 5);
- a holder that learned a supply point had changed hands could not act on it on the platform.

**EDC does not model this.** At the pinned tag (0.18.0) the policy engine evaluates a duty only
through registered constraint functions (`PolicyEvaluator.visitDuty`) and tracks no
fulfilment, so an ODRL duty "the collector verified ownership" would be decorative. An
agreement also binds the provider and the **consumer**, not the collector, and consent offers
are ds's own (ADR-0015). DSP and DCP define no record of an assertion of this kind.

## Decision

1. **The collector asserts, in the evidence record.** `AdminShareLegalBasis` (`D-12`) gains
   `key_assertion`, sent by the collector client (ADR-0026) with the keys it asserts. Codes and
   hashes only, `extra="forbid"`:

   | field | is |
   |---|---|
   | `terms` | the version id of the collector's responsibility statement (`rec-pod-assertion/1`) |
   | `terms_sha256` | SHA-256 of the exact text of that statement the collector accepted |
   | `method` | `uploaded-document` or `offline-with-evidence` — a plain "offline" check is **not** accepted |
   | `verification_ref` | the collector's verification record, by UUID |
   | `verified_by` | HMAC-SHA256 of the verifying operator's id under a key only the collector holds |
   | `verified_at` | when it verified; ISO-8601 with a timezone, not in the future (2 minutes' skew) |
   | `evidence` | at least one `{kind: utility_bill \| id_document \| other, sha256}` — the digest of a file the collector keeps |

   No fiscal code, no supply point, no hash of either: both are low-entropy and a hash of one
   is brute-forced. A digest of a document reveals nothing without the document. An assertion
   sent without keys is refused (`422`).
2. **The holder's offer governance says what it accepts.** A sharing offer may declare
   `key_assertion: {required, methods}` (shorthand `key_assertion: required`). Missing when
   required, or a method the offer does not accept, is a `422`. **An offer that declares
   nothing requires an assertion for a `pod:` key outside `DS_ENV=dev`**, accepting both
   methods; in dev, and for other key types, it does not, and an assertion that is sent is
   still checked. Fail-closed where the platform runs for real; zero-config where it does not.
   The declaration is not a user-visible fact, so adding it asks nobody again.
3. **One subject per `pod:` key at a holder.** `consent_key_owners` (migration `0016`) holds the
   active owner of each `pod:` key, by its keyed blind index (`connector.db.sealed.blind_index`),
   never the key. A second subject registering an owned key is a `409` naming neither the key
   nor the other subject; the same subject re-registering is not. A partial unique index on
   the active owner is the database's backstop. The owner is **released** — marked, not deleted
   — when the last grant carrying the key ends; the ledger, read past the holder's own entries,
   is what says whether any grant still carries it.
4. **The record carries the assertion and the keys, as digests.**
   - The assertion is stored in the decision's `legal_basis` and, by its `assertion_ref` —
     `sha256_hex(canonical(assertion))`, canonical being sorted-keys compact JSON — in
     `consent_key_assertions`.
   - `ConsentGranted` carries the assertion (inside `legal_basis`), `assertion_ref` and
     `keys_digest = sha256_hex("\n".join(sorted(set(key_index))))`. The event id gains a suffix
     derived from both, so a registration that changes the keys or the assertion is a new fact
     on the chain, and an identical re-run is still a duplicate.
   - Every ledger entry carries the `assertion_ref` its decision carried.
   - A newer assertion for a standing grant replaces only `legal_basis.key_assertion`; the
     consent evidence stays the grant's own.
5. **The release link.** `POST /internal/dataplane/authorize` returns `decision_ref` on an
   allow:

   ```
   decision_ref = sha256_hex(agreement_id + "\n" + "\n".join(sorted(set(key_index))))
   ```

   over every key the allowed row filters serve (an allow serving no key hashes
   `agreement_id + "\n"`), and `null` on a deny. The data plane treats it as opaque and echoes
   it, with `agreement_id`, in its own audit record and in `POST /internal/audit/query`, which
   forwards both to `QueryExecuted` (a value that is not a SHA-256 hex digest is a `422`). An
   auditor holding the holder's ledger recomputes it for a candidate key set without opening a
   key, and matches it to the grants whose `keys_digest` cover the same indexes. The field is
   added with a default at both ends (`ds.governance.DataplaneDecision`), so the order is **the
   data plane first, the connector second**. A failed provenance emit is logged at `ERROR`.
6. **The holder can suspend a key.** `POST /consent/admin/holder/keys/suspend
   {key, reason: "holder_change"}`, for the holder's own organisation client or the deployment
   operator only — `connector.consent.holder.read` reads, it does not write. The key leaves the
   served set for every decision carrying it (`get_granted_subjects` drops it, so the row filter,
   the holder's key list and the audience agree); the ledger gets a `holder_suspension` entry
   per such decision; provenance gets a `KeySuspension` event (`action: suspended`, the key's
   digest, never the key); the collector's read-back lists it in `suspended_keys`. **It is
   lifted only by a grant whose `key_assertion.verified_at` is later than the suspension** —
   which writes `suspension_lifted` entries and a `KeySuspension` event with
   `action: lifted` and the `assertion_ref`. An older verification is a `409`, for the same
   subject and for a new one. Idempotent while it stays suspended.
7. **The key records outlive the decision row, for a stated period.** The ledger's reference
   to its decision becomes `ON DELETE SET NULL` (it was `CASCADE`). The ledger, the owners, the
   assertions and the lifted suspensions are kept for `CONNECTOR_KEY_RECORD_RETENTION_DAYS`
   after the key stopped being carried — **default 3650 days, the Italian ordinary limitation
   period (art. 2946 c.c.), pending legal counsel** — on the basis of GDPR **Art. 17(3)(e)**
   (the establishment, exercise or defence of legal claims). Nothing deletes them on a
   schedule; `python -m connector.db.retention purge` counts, and with `--apply` deletes, only
   what the period has passed, and never a key a grant still carries or a suspension still in
   force.

## What the collector asserts, in plain words

*For a community's operators; the onboarding service writes the words its screens use.*

When your community registers a member's decision at a grid operator together with the
member's supply point, it is telling the grid operator: **"this supply point is this member's;
we checked, and we can show how."** The grid operator releases that supply point's readings on
your word and does not check it again. So the platform records, alongside the decision:

- **which statement you agreed to** — the version and a fingerprint of the exact text that
  sets out your community's responsibility;
- **how you checked** — from a document the member uploaded, or offline, in person or by
  phone; an offline check counts only if you keep a copy of what you were shown;
- **when, and by whom** — the moment of the check, and a code for the operator who did it that
  only your community can turn back into a name;
- **a fingerprint of each document you relied on** — a bill, an identity document — never the
  document or what it says.

Your community is responsible for that statement being true when it was made. Keep the
documents for as long as the platform keeps the record (ten years by default), so the
fingerprints can be matched to them. If you learn that a supply point has changed hands, withdraw
the registration; if the grid operator learns it first, it suspends the supply point, and it is
released again only when your community checks again and registers it with that newer check.

## Alternatives rejected

- **Send the fiscal code with the supply point** so the holder can cross-check. The agreement in
  force is a plain export by supply point; this puts more personal data on the wire for a check
  the holder does not run. Open to revisit if a holder can answer "is X the customer of record of
  P" at grant time.
- **An ODRL duty on the agreement.** EDC 0.18.0 does not track fulfilment, and the agreement
  binds the consumer, not the collector (Context).
- **Accept a plain "offline" verification, flagged.** It leaves nothing to match later; the
  requester chose evidence always.
- **Hash the supply point into the record** for the auditor. Low-entropy: anyone with the record
  recovers the supply point by enumeration. The keyed blind index needs the holder's secret.
- **Keep the ledger cascading and rely on provenance.** The chain carries no key, so without
  the ledger the digests cannot be matched to supply points at all.
- **Delete the owner on release.** It would lose who held a supply point when, which is the
  question a holder change raises.

## Consequences

- A registration carrying a `pod:` key outside dev now needs an assertion. Collectors must send
  one before a holder upgrades; the onboarding service is changed in the same round.
- Migration `0016` backfills the owners from the ledger and **stops** when a `pod:` key is
  carried by two subjects' grants: which one holds it is the collectors' fact, not the
  migration's guess. The operator has the wrong registration withdrawn, then migrates.
- Deploy order: provenance (new fields and event type) before the connector; the data plane
  before the connector (`decision_ref`).
- The suspension acts on keys. A dataset whose row filter matches on usernames
  (`principals`) is not narrowed by it.
- What the platform still cannot show is who held a supply point on the day of a given reading:
  that fact is in the holder's own register. The record shows who asserted what, when and on
  what evidence, and every release under that assertion.
- The retention period is a deployment setting pending counsel; changing it does not
  re-run anything, and the purge is an operator's act.
