# ADR-0020 — Each withdrawal is its own record

**Date:** 2026-09-21
**Status:** accepted; amended the same day (below)
**Refines:** ADR-0015 (decision 4, whose decision it is) and ADR-0019 (its consequence on a
withdrawal over a withdrawal)
**Rules affected:** `D-15c` (how a stacked withdrawal is stored); `D-15a` (now dated
correctly); `D-12a` unchanged

## Context

A member's collector can withdraw a member's consent on its own authority, for example when
a membership ends (`decided_by="collector"`, with a `reason`, ADR-0019). The member can then
say stop as well, directly or relayed by the collector (`decided_by="subject"`).

The consent writer did not record the member's act as a new row. It **re-stamped** the
collector's row: `decided_by` became `subject` and `collector` became the member call's, while
`revoked_at` and `revocation_reason` stayed the collector's. The row then said the member
decided, for the collector's reason, at the collector's time. Measured live on 2026-09-21.

`consent_requests` is the only history. A grant appends a row. A withdrawal over a grant
mutates that row. A withdrawal over nothing appends a refusal. A withdrawal over a refusal
changed nothing except the re-stamp above. So no copy of the collector's row as written was
kept. Provenance did not keep the member's act either. Its `ConsentRevoked` event reused the
row's id as `event_id`, and the provenance store drops a repeated `event_id` as a duplicate.

Keeping the collector's time also broke `D-15a`. Suppose the member granted one party directly
between the two withdrawals. The member's later "stop for everyone" then looked older than
that grant, so the grant still stood.

The maintainer decided on 2026-09-21: *"If both withdrawal, both are stored, since the
subjects are different. Still after the first withdrawal I expect it is enforced."* And, on
which of two withdrawals a read presents: *"yes prioritize the member if both, still if it's a
withdrawal on both side I do not see the problem. It's withdrawn right?"*

## Decision

1. **A subject's withdrawal over another authority's standing refusal is a row of its own.**
   It has its own `revoked_at` and `decided_by="subject"`, the collector of the call that
   recorded it, and no keys. The standing refusal keeps its `decided_by`, `collector`,
   `revoked_at` and `revocation_reason` exactly as written. Only an organisation's own
   withdrawal carries a caller's reason (`D-12a`).
2. **One record per withdrawing authority, not one per call.** When the same authority
   repeats a withdrawal, nothing is recorded. ADR-0019's rule still holds: when a collector
   repeats itself, its first recorded reason is the one that stays.
3. **Enforcement starts at the first withdrawal and does not change.** Every reader decides
   from the newest row in a cell. After the first withdrawal that row is a refusal, and after
   the second it is still a refusal. Because the member's withdrawal now has its own time,
   `D-15a` compares it correctly, which enforces more strictly than before.
4. **`D-15c` is unchanged.** The member's row is now the newest in the cell, and only the
   subject can lift it (or an operator with the evidenced override). So the collector, the
   holder's services and an operator provisioning normally are refused with the existing
   `409`, which now names the member's own row. Decision 9 extends the check to every
   withdrawal standing in the cell.
5. **No new fields, no migration.** Response shapes are unchanged.
6. **Nothing to reuse.** EDC and DSP have no consent concept (ADR-0015). DPV separates
   `dpv:ConsentWithdrawn` (withdrawn by the subject) from `dpv:ConsentRevoked` (revoked by
   another entity). Those are two acts by two actors, which is what two rows now record.
   `decided_by` already carries the distinction on the provenance event, so the JSON-LD
   context is unchanged.

## Amendment, 2026-09-21: the member first, then a collector

The first version of this record left this order open. Storing the collector's row would have
made it the newest, and every current-decision read would have shown it instead of the
member's withdrawal. A collector that reads back which decisions are the member's (an
onboarding service relaying for a community does) could then have relayed an older member
grant. That grant is the subject's, so it would have lifted both withdrawals. The maintainer
answered: prioritise the member.

7. **Any withdrawal by an authority with no withdrawal already standing is its own row.**
   This includes a collector over the member, and one collector over another. It keeps its
   own time and reason. Withdrawals stand from the newest decision back to the last grant.
8. **A cell presents the member's standing withdrawal whenever there is one**, even under a
   newer withdrawal by anybody else. Otherwise it presents its newest decision.
   `present_current` / `_presented` in `consent_service` apply this for every reader that
   takes "the latest row":
   - the write path and `_may_lift`;
   - the consent checks, the data-plane row filter and the audience read;
   - `missing_prerequisites`;
   - `GET /consent/my/shares`, `GET /consent/admin/subject-shares` and `GET /consent/status`.

   `GET /consent/my` still lists every row, with the presented one first in its cell.
9. **Lifting a cell needs authority over every withdrawal standing in it**, not only the
   presented one. So a collector cannot lift the cell over the member's withdrawal, nor over
   another collector's. The `409` names the member's withdrawal when there is one. The member
   (directly or relayed) lifts them all, and so does the operator's evidenced override, as
   before (`D-15c`).
10. **Enforcement is unchanged:** the cell is withdrawn from the first withdrawal on,
    whichever withdrawal is presented.

ds does not refuse a grant relayed as the member's, and cannot: `D-15c` makes that grant the
member's to make. What closes the relay hazard is the read. The member's withdrawal is always
in the read-back, dated when they made it, so a relayer ranking the member's own decisions
sees it as newer than the grant.

**One consequence to confirm.** `D-15a` compares a wider-scope withdrawal's time with a
per-party grant, and it uses the presented row. Suppose the member withdrew the offer, then
granted one party directly, and then a collector withdrew the offer. The per-party grant still
stands, because the member's withdrawal is older than it, and the collector's later
withdrawal does not close it. That is exactly what happened before this change (the
collector's withdrawal was not stored at all), so enforcement is unchanged. Whether a
collector's later withdrawal should close such a grant is a separate question.

## Consequences

- The row count grows by one for each authority that withdraws over another's withdrawal.
  `GET /consent/my`, which lists every row, shows all of them.
- The writer's answer is always the row it recorded. For a collector's withdrawal over the
  member's, that is the collector's new row (`decided_by: collector`). Before, it was the
  member's row, returned unchanged. The reads that follow present the member's.
- What the writer returns for such a withdrawal is the new row: a new `id`, the member's
  `revoked_at`, and `decided_at: null`. `GET /consent/status` therefore reports `decided_at`
  as `null` where it used to report the withdrawn grant's time.
- The member's act is now a separate `ConsentRevoked` event in provenance.
- `GET /consent/admin/subject-shares` now dates the member's withdrawal to when the member
  made it. A caller that ranks decisions by time sees the real moment of the withdrawal
  instead of the collector's.
- Rows written before this change are not rewritten. A row that was re-stamped earlier still
  carries the other authority's time and reason under `decided_by="subject"`.
