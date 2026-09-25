# ADR-0021 — An organisation lists its own members' decisions

**Date:** 2026-09-25
**Status:** accepted
**Refines:** ADR-0015 (the collector's read-back) and ADR-0020 (which decision a cell presents)
**Rules affected:** `D-20` (amended: the per-subject read-back gains a list form under the
same bound)

## Context

An organisation that collects its members' consent registers each decision at the connector
that holds their data (ADR-0015). It had two ways to read the decisions back, and neither
answered the question an operator asks, *who withdrew?*

| route | shape | states |
|---|---|---|
| `GET /consent/admin/shares` | the audience: a list per dataset, for one offer and one consumer | standing grants only |
| `GET /consent/admin/subject-shares` | one subject | every state that subject holds |

A subject who withdrew is absent from the audience, so they look the same as a subject nobody
asked. Finding the withdrawals took one call per member. With 48 members and four offers,
"who consents" was 4 calls and "who withdrew" was 192.

This is not a matter of convenience. A controller has to be able to show that a withdrawal was
honoured, and the collector that took the decision is the party that has to show it.
Enforcement already works: the holder's row filter stops serving as soon as consent is
withdrawn. What was missing was a readable record at the level an auditor asks about. An
audience that is shorter next month is a difference, not a record.

EDC and DSP have no consent concept (ADR-0015). DPV separates `dpv:ConsentWithdrawn` (by the
subject) from `dpv:ConsentRevoked` (by another entity). The rows already record who acted, as
`decided_by`. So a list only has to project the rows. It needs no new state.

## Decision

1. **A second route, `GET /consent/admin/decisions?offer_id=…`.** The audience route is not
   changed. It answers "who may be served", and it stays grants-only so that a reader cannot
   treat a withdrawn subject as present. That mistake would be a disclosure. The maintainer
   settled the name on 2026-09-25. It is public API.
2. **It is bounded exactly as `subject-shares` is.** It uses the same permission
   (`connector.consent.provision`, an organisation's own client or the deployment operator),
   the same acceptance check and the same membership check the write makes:
   - a caller not accepted here is refused with `403` (or `503` when the registry cannot say).
     It never gets an empty list, which would read as "nobody decided";
   - a subject is listed only while they are a current member of the caller's organisation,
     checked per subject. If the registry cannot answer for one subject, the call is a `503`
     rather than a silently shorter list;
   - only cells the caller's organisation **collected** are listed. A cell is one subject's
     standing (wildcard-consumer) decision on this offer over one dataset. The organisation
     collected it if it wrote a row there (`collector`) or registered the grant's evidence
     (`legal_basis.collector`). The evidence counts because a withdrawal over a grant rewrites
     the row's `collector` to the withdrawing caller, while the evidence record is never
     rewritten. So a member's withdrawal relayed by another organisation over this
     organisation's grant is still listed to this organisation. Another organisation's
     registrations and a consumer's per-party ask are never listed.

   A caller that may read one subject at a time may read them as a list. It reaches no
   subject and no cell it could not already read through `subject-shares`. The only thing it
   gains is asking once.
3. **Each cell shows its presented decision** (`present_current`, ADR-0020): the member's
   own withdrawal whenever one stands, otherwise the newest decision. This is the row
   `subject-shares` returns for the same cell, and the one enforcement decides from. `state` is
   `granted` or `withdrawn`, and who withdrew is `decided_by`. A subject who never decided is
   **absent**, not a third state. Coverage is the caller's diff against its own member list.
4. **One entry per subject, one decision per dataset, never flattened**, for the reason the
   audience gives. The data keys go back only to the organisation that registered them. The
   withdrawal reason goes back to nobody (`D-12a`).
5. **Paged by subject id with an opaque cursor**, `limit` 1–100, default 50. The maximum
   also caps the membership checks one request makes. A page can hold fewer than `limit`
   subjects, even none, when some are no longer members. Only `next_cursor: null` ends the
   list, so nothing is ever truncated silently.
6. **A holder route.** Each connector answers for the rows it holds. A collector that
   registers at several holders asks each one. No connector aggregates for another (the
   maintainer, 2026-09-25).

## Consequences

- An organisation can evidence a withdrawal with one call per offer and page: which member,
  when (`revoked_at`), and whose act it was (`decided_by`, `collector`).
- `D-20`'s "one at a time, never a roster" becomes "the caller's own members only, one at a
  time or as a list". The bound is unchanged, only the shape is new. Cross-subject reading by
  anyone else still needs the audience permission (`connector.consent.audience`), and that
  route still lists grants only.
- One request can make up to 100 membership checks at the identity registry, run
  concurrently.
- Rows written before ADR-0020 are not rewritten. A row that was re-stamped earlier is listed
  as it stands.
