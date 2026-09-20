# ADR-0019 — A collector says why it withdrew

**Date:** 2026-09-19
**Status:** accepted
**Amends:** ADR-0015 (what a collector's registration carries)
**Rules affected:** `D-12a` (new); `D-2` and `D-15c` apply unchanged

## Context

An organisation that collects its members' consent withdraws on its own authority when a
membership ends (`decided_by="collector"`, ADR-0015). The onboarding service that does this
sends a cause with the withdrawal, as `message`. `AdminShareRequest` is `extra="forbid"` and
had no such field, so the withdrawal was a `422` and revoking a membership failed its
share step at every connector. The maintainer decided on 2026-09-19 that the route takes an
optional cause.

`POST /consent/admin/shares` has an out-of-repo caller, so what it accepts is a seam.

Nothing new had to be stored. The consent row has carried `revocation_reason` since the
first migration, the writer already filled it on both withdrawal branches, and the
`ConsentRevoked` provenance event already has a `reason`. What was missing was a way for
this caller to supply one.

## Decision

1. **The field is `reason`.** ds calls the cause of an ending `reason` everywhere:
   `revocation_reason` and `termination_reason` on its rows, `reason` on `AccessRevoked`,
   `NegotiationTerminated` and `ConsentRevoked`. EDC's terminate calls and DSP's
   termination messages call it the same.
2. **`message` is not accepted as an alias.** The aliases this router keeps (`recipient` /
   `controller`) preserve a spelling that used to work. `message` never worked on this
   route, so no working client needs it. It also already names another field of the same
   row: the text the row was created with, which `ConsentResponse` returns to every reader.
   An alias would give one word two meanings, and the second one is returned to readers.
   The caller renames one key.
3. **No vocabulary term is borrowed.** PROV-O has no term for a reason.
   `dpv:hasJustification` in DPV 2.3 ranges over `dpv:Justification` concepts. The DPV
   justifications extension has none for a withdrawal or a membership ending, and a
   free-text cause is not a concept. The JSON-LD context is unchanged, as it is for every
   other `external_meta` key. A global `reason` term would also relabel the two other events
   that use the key. DPV does separate `dpv:ConsentWithdrawn` (withdrawn by the subject)
   from `dpv:ConsentRevoked` (revoked by another entity). `decided_by` already records the
   same distinction.
4. **Only an organisation's own withdrawal carries one.** A reason is accepted only with
   `enabled: false` and `decided_by: "collector"`, and is a `422` otherwise:
   - A relayed withdrawal is the member's (`D-15c`), so the organisation's text would be
     recorded as the cause of a decision the organisation did not take.
   - A grant has no cause to record.
   - No need has been stated for the operator. A narrow rule can be widened later without
     breaking callers; narrowing a wide one would break them.
5. **One line, 200 characters, no `@`, returned by no read.** The rule, and why it is
   drawn there, is `D-12a` in the rulebook, because it is a personal-data rule and is
   measured there.

## Consequences

- The onboarding service sends `reason` instead of `message` on its withdrawal body.
  Until it does, the withdrawal is still a `422`.
- A withdrawal over a withdrawal that already stands changes nothing, and that includes
  its reason. The first cause recorded is the one that stays.

## Amendment, 2026-09-20 — "returned by no read" was true of ds's consent reads and false of the graph

**Status:** accepted. **Rules affected:** `D-12a` (wording), `L-13`.

Measured live against a deployment where two participants share one realm: three separate
organisation clients — the collector's, the holder's own, and the community's onboarding
service — each holding `provenance.write` and **nothing else**, read every event in the
holder's provenance store over `GET /prov/events`, `reason` included.

Decision 5 was written about ds's *consent* surface, and there it holds: no consent read
projects `revocation_reason`. What it did not account for is that the same fact reaches
provenance by design (`ConsentRevoked` carries it, and this ADR says so in its Context), and
that **provenance's read guard accepted a write scope**. So the field was reachable by any
realm client that could write anywhere.

The defect is not in this decision and the field is not withdrawn from the event. It is a
provenance authorization defect, fixed in the same change as this amendment: the scopes are
split per route, so `provenance.write` no longer reads. See `provenance/dependencies.py`,
rulebook `L-13`.

What stands after the fix is what this ADR already said in decision 5's own rationale:
**who sees it is the holder** — its own operators, who hold `provenance.read` at their own
participant — **and the subject**, through `GET /prov/my/events`, which authenticates a
person by credential and is not scope-guarded at all.

Two things this amendment does **not** do, deliberately:

- **It does not scope the projection to the caller's participant.** A provenance store *is*
  one participant's by deployment; adding a per-event participant filter would be a second
  mechanism guarding a boundary the deployment already draws, and it cannot be done
  uniformly — `provider_did`/`consumer_did` exist on the exchange events, while
  `ConsentRevoked` is keyed on a subject and a collector. Splitting the scope is the fix
  that matches the authority model; a filter would be a guess layered over it.
- **It does not clean the rows already written.** Any event a deployment has already
  recorded still carries whatever it carried. See the rulebook note under `L-13`.
