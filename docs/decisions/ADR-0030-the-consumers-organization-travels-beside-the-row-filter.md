# ADR-0030 — The consumer's organization travels beside the row filter, from a credential every exchange presents

**Date:** 2026-10-19
**Status:** accepted, implemented 2026-10-18
**Refines:** the per-query decision (`POST /internal/dataplane/authorize`) and the
participation credential. The rules it records the reasons for are `X-17`, `X-18`, `X-19`,
`P-30`, `P-31` and `C-10b`; this record restates none of them.

## Context

A dataset can be narrowed by **organization** as well as by person: a grid table holding
several operators' rows declares a row filter binding an organization (`binds:
organization`), and the platform's row policy has two layers, `person` and `organization`,
each stated by a filter or by a layer verdict (`allow_all`, `deny_all`).

Through an agreement, ds could say who the consenting persons were, never which
organization the consumer acted for. So the per-query verdict for a dataset that is not
consent-gated carried the organization filter naming nobody, and the data plane served
nothing (`X-17`). Serving the consumer its own organization's rows needs three things ds
did not have: the organization on the wire, a source for it that the provider can trust,
and a way to keep that source true after a credential changes.

## Decision

### `organizations` is a field of the verdict, beside `row_filter`

`DatasetVerdict.organizations` (`ds.governance.dataplane`) is a list of owner ids, next to
`row_filter`, not inside it. The verdict has one `row_filter` slot, and on a consent-gated
dataset it holds the **person** layer — the consenting subjects. Folding the organization
into it would mean either two filters in one slot or choosing which layer to drop. Beside
it, the data plane applies its **own** declaration of the organization layer to the list,
and its own declaration of which filters exist stays authoritative: the celine
`dataset-api` sets aside the organization filter ds carries and applies the one its
catalogue declares to `organizations`. The field is optional and accepted before the
connector emits it, so the data plane can be deployed first; `None` and `[]` both read as
no organization.

### The organization comes from the `OrganizationCredential`, requested as a DEFAULT DCP scope

The credential the trust anchor issues at promotion already names the organization. It
gains `organizationId` — the owner id, the key the platform's rows and the identity
provider's organization use — and `organizationType`, read from the owner's
`organization.role` only. Never from the owner's `type`, which is a schema.org class
(`schema:NGO`), and never from the participant `roles` the credential carries; an owner
with no `organization.role` gets no `organizationType`, not a guess.

EDC verifies a presented credential (signature, trusted issuer, status) and stores the
claims of the **agreement verification message** on the provider's agreement. That is the
only place a provider-side record of what the consumer presented at negotiation exists, so
the credential has to be in that message's presentation. In EDC 0.18.0 a **POLICY** scope
is extracted only for the catalogue, contract and transfer request messages
(`DynamicScopeExtractor`), never for the `ContractAgreementVerificationMessage` whose
claims `ContractNegotiationProtocolServiceImpl` stores; a **DEFAULT** scope is added to
every DSP message by a post-validator (`DefaultScopeMappingFunction`). So the scope is
DEFAULT, on every EDC configuration ds ships.

**Accepted with it:** EDC fails the whole token when a presentation lacks a requested
credential type, so a participant without an `OrganizationCredential` — or whose only
copy is retired — fails every DSP exchange, the catalogue included, not only exchanges for
organization-bound data. Participation already requires the credential (it is issued at
promotion); the cost is that nothing degrades gracefully when it is missing. Not chosen:
looking the organization up in the issuer's records at authorize time, which rests on the
issuer's records rather than on what the consumer presented in the exchange; and a POLICY
scope on organization-bound offers, which never reaches the stored agreement.

`NegotiationEventPublisher` forwards the presented `organizationId`/`organizationType` on
`FINALIZED`; the connector keeps them on its agreement row on the provider side only, and
more than one organization presented keeps none.

### The credential is re-checked per request, and an unknown organization is an empty list

An agreement outlives the credential presented for it. On each query the connector asks the
issuer whether the consumer's DID still holds a live `OrganizationCredential` with that
`organizationId` (`/credentials/check`). Not established — nothing presented, two
organizations, a credential retired since — gives `organizations: []` with the reason
`organization_unresolved`; a declared `org_type` that differs from the presented
`organizationType` gives `[]` with `organization_type_mismatch`.

**An empty list, not a `DENY`.** A `DENY` refuses the dataset whatever the data plane
declares; an empty list lets the data plane's organization layer decide, which serves no
rows from an organization-bound layer and every row from one declared `allow_all`. The
outcome for organization-bound data is the same, and the decision of what an organization
layer means stays with the declaration, in one place.

### A reissue suspends after delivery, and the holder filters its own retired copies

Adding the claims needs every organization's credential reissued. An organization's
credential lives in the holder's own store, which this registry does not control, so a
reissue cannot be one transaction: the successor is committed and delivered, and only once
the holder accepted it is the predecessor **suspended** — not revoked, because a replaced
attestation was not withdrawn (`P-30`). A failed delivery retires nothing.

DCP has no message telling a holder its copy was retired, so after a reissue the holder
keeps the suspended predecessor, and EDC rejects a whole presentation in which any
credential carries a set status bit. With the credential requested on every exchange, one
stale copy would stop the participant. So the holder checks its own credentials against the
issuer's revocation and suspension registers before presenting, and leaves out any with a
set bit or an unreadable register (`P-31`). It reads **uncached**: measured on a local
stack, a register cached by the holder for its default lifetime let a just-suspended copy
be presented while the verifier already saw the bit. Reading fresh, the holder is never the
staler side. Accepted with it: while the anchor's registers cannot be read, the holder
presents no organization credential, and every exchange fails.

### A layer verdict is a statement, and a malformed filter is refused

`allow_all` and `deny_all` state what a layer does; they are not filters (`X-19`). Counted
as consent signals they would gate every dataset that states its person layer, so
`allow_all` is no consent signal and travels in no verdict — the slot stays empty and the
data plane applies its own declaration. `deny_all` on either layer answers `DENY`
(`row_policy_denied`) before consent or organization is looked at, because nothing either
could add changes the answer, and an `ALLOW` the data plane then empties would record a
disclosure that never happened.

A malformed row filter fails the file's load instead of being dropped (`C-10b`). The
resolver used to drop an entry it could not read, and a dropped filter reads as no filter:
a person-layer verdict carries no `args`, so a person-layer `deny_all` was dropped and the
dataset served. Refusing the file surfaces the error in `ds-governance validate` where the
producer can fix it; dropping it turned a typo into a disclosure.

## Consequences

- The data plane needs the organization layer of each dataset it serves; ds does not
  send it. A data plane that predates `organizations` serves no rows from an
  organization-bound layer, which is the fail-closed outcome `X-17` already had.
- Every participant must hold a live `OrganizationCredential` to exchange anything, and a
  reissue is the only way to add a claim to it.
- An anchor whose status registers cannot be read stops every exchange, at the holder,
  at once.
- The status of each behaviour is measured on the rules named above, not here.
