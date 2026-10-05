# ADR-0028 — A member who moves gets a new DID and takes their login, and nothing old is rewritten

**Date:** 2026-10-05
**Status:** accepted, implemented 2026-10-05
**Refines:** ADR-0024 (the login → DID binding), ADR-0026 and its 2026-10-05 amendment (a
collector binds logins only to its own members), ADR-0027 (one subject per `pod:` key),
ADR-0021 (the read-back is bounded to what the organisation collected)
**Rules affected:** `D-20`, `D-22a`, `D-22c`, `D-12b`, `P-29`

## Context

A person cannot be a member of two communities at once. A community releases a member
(withdrawing their grants, revoking their credential), and the person can later join another
community with the same Keycloak login. Each community runs its own `participant` identity
registry, which publishes the DIDs in its namespace (`D-22a`), and each holder retires a DID
once every credential it keeps for it is revoked (`P-29`).

Before this decision, four things went wrong at such a move:

- **Issuance reused the released DID.** The anchor matched the subject id against every
  known DID and issued under the first match, so the second community's credential named
  `did:web:<first community>:users:<id>`. The first community's sweep then retired that DID,
  and the person's live credential named an identifier that answered `404` (`D-22`).
- **The login could not move.** `POST /admin/keycloak/sync` refused the new DID with a `409`
  naming the old one, and the only unbind was the operator's `DELETE`, which erased the row.
  The joining community's onboarding failed closed.
- **The read-back listed the previous community's history.** `GET
  /consent/admin/subject-shares` checks membership *now* and then listed every row of the
  DID: whatever the first community had registered for the person (datasets, purposes,
  consumers) went to the second.
- **A key owner was a subject only.** A second community registering the same DID's `pod:` key
  refreshed the first one's owner row, which still named the first community as asserting it.

## Decision

1. **A DID is reused only while it holds a credential that is not revoked.** A second role,
   from the same organisation or another, still shares it (one human, one DID while in use).
   A suspended credential counts as live, since suspension is reversible. Otherwise the
   person is issued a **new DID in the issuing organisation's namespace**. If the DID the call
   would mint is itself spent (it had credentials and all are revoked: the same community,
   the same id), the call is a `409`, and the caller sends a new opaque subject id. A spent
   DID is never revived. The API and `ir-cli credential issue-data-subject` share the rule
   (`services/issuance.py`: `live_subject_did`, `is_spent`). The `409` for a second
   organisation's credential of the same role, while the first one stands, is unchanged.
2. **The login moves through the joining collector's sync.** `POST /admin/keycloak/sync`
   rebinds a login from its current DID to the new one when:
   - the old DID is spent, and
   - the new DID holds a credential, not revoked, linked to the caller's organisation (the
     ADR-0026 amendment's check, unchanged).

   While the old DID holds anything live, the sync is still a `409`. **The old row is kept
   as history**: `keycloak_mappings.released_at` is set, and `(realm, user id)` is unique
   only among rows not released (migration `0020`). The operator still reads the released
   row (`GET /admin/keycloak/mapping/{did}`). Nothing else resolves it: `/users/me`,
   `/users/resolve`, `/users/identities` and the username and email lookups skip it, and no
   sync revives it.
3. **The collector's read-back lists only the cells the calling organisation collected**
   (`collected_by`, the same predicate as `GET /consent/admin/decisions`). Within such a
   cell it lists the presented decision, and the member's own withdrawal is listed there.
   Asks stay listed, because they are questions to the person and nobody collected them
   (`D-18`). The deployment operator reads every cell.
4. **A `pod:` key's owner is a subject and the organisation that asserted it.** The same DID
   under another organisation's assertion is a `409`, as another subject is. The supply
   point moves with the person, as a new subject: the next community's grant under the new
   DID is a `409` while the previous community's grant carries the key, and goes through
   once that community's withdrawal releases the owner.
5. **Nothing under the old DID is rewritten.** Consent rows, key owners, the key ledger and
   provenance events stay keyed to the old DID and the organisation that collected them.

## Why history and not the chain

The login → DID row is the anchor's own record. ADR-0024 makes it the binding every person
route trusts. Keeping the released row in place answers "which login acted as this DID, until
when" from the same table, with no new writer. Recording the rebind as a provenance event
would add a second writer and a new event type to answer the same question, and it would
place the pair of DIDs on a chain that holders and auditors read. The released row stays at
the anchor, which already knows the login.

## No cross-community link

The requester decided against a "same person" link (2026-10-05): the holder checks the supply
point, and the community checks its current member. Nothing here creates such a link outside
the anchor. The sync's answer and its log line name the new DID only. The old row's
`released_at` is the only trace, and it sits in the table that already holds the login.

**Residual, stated:** a caller that re-onboards a person under the **same** subject id mints
`did:web:<next community>:users:<same id>`. That DID is new and correct, but anyone who sees
both DIDs can link them through the shared suffix. `D-22c` already binds the generator: a
caller re-onboarding a released person sends a new id. The registry does not generate ids,
so it cannot enforce this. It refuses only the same-namespace case, where the result would be
the spent DID itself.

## The sweep (R35)

After a move, the old DID holds only revoked credentials, so its holder's sweep retires it
(`P-29`). This is correct: no live credential names it any more, and the new DID lives in the
next community's namespace, served by that community's registry
(`test_the_sweep_retires_the_released_did_and_not_the_new_one`).

**Residual, not fixed here:** a dual-role person's shared DID sits in the first
organisation's namespace. If that organisation revokes its credential while the second
organisation's stands, the first one's sweep sees only the credentials it holds, all revoked,
and retires a DID that is still in use. Fixing this needs the sweep to ask the anchor, or the
second role to move the DID, and that is a separate decision.

## Consequences

- Onboarding re-syncs the mapping at join, with the collector client, after the new
  credential is issued, and mints a new opaque subject id for a released person instead of
  reusing the mapping's old one.
- A person's own history under the old DID (`/prov/my/events`, `/consent/my`) is reached
  only with a credential for that DID. After the move it is no longer reachable through the
  login. Reaching it later would need the link the requester declined.
- A deployment downgrading past `0020` while history rows exist is refused by the old
  constraint. As in `0010`, which DID the login answers to is then the operator's decision.
