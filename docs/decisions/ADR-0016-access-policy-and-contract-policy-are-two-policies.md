# ADR-0016 — The access policy and the contract policy are two policies, and membership is a credential claim

**Date:** 2026-09-17
**Status:** accepted
**Rules affected:** `C-21` (Partly enforced → Enforced), `C-2`, `D-11`, `D-11a`, `D-14`,
`A-7` (wording), `CR-1` (wording); scope-and-deviations §3.2 (closed); blueprint
`DSSC-PUB-03` (open → covered)

## Context

Three problems shared one cause.

**`owner:<id>:member|partner` granted nothing.** The governance mapper emitted
`Membership eq owner:<alias>:member` (or `:partner`), an EDC constraint function asked
ds-connector, ds-connector asked the trust anchor, and the anchor tested that literal string
against a hand-kept `participant.allowed_scopes` list. No code anywhere granted `:partner`,
and no owner could grant anything. Downstream producer files asked for
`owner:<alias>:partner`, which no enrolment satisfied, so those datasets could be negotiated
by nobody and nothing said why.

**The answer was already in the verifier's hands.** The anchor signs
`credentialSubject.memberOf` and `allowedScopes` into every `MembershipCredential`, and every
connector requests that credential as a DCP `DEFAULT` scope. EDC verifies the presentation —
validity period, trusted issuer, **StatusList2021 revocation and suspension** — and puts the
credentials on the `ParticipantAgent`. ds ignored that and made a central HTTP call per
negotiation, which is the centralisation DCP exists to remove. The two could also drift:
`PATCH allowed_scopes` on the anchor does not re-issue the credential.

**One policy served both slots of every ContractDefinition.** EDC's `ContractDefinition`
holds an access policy — *may this counterparty see and ask for the asset?* — and a contract
policy — *what binds once there is an agreement?* ds put one policy definition in both. So
every admission condition was published to every counterparty, nothing could be hidden from
anyone, and the membership operand was bound only in `contract.negotiation`: `C-21`
("visibility may be restricted to a subset of participants") was *Partly enforced*, and
scope-and-deviations §3.2 recorded it as accepted.

Separately, `recipients.controller` on a sharing offer meant three things at once — the
recipient, the subject's home organisation, and the GDPR Art. 4(7) controller — and only the
first held in every offer of a real four-hop chain.

## Decision

**1. The two policies are separate, and the split decides where a constraint goes.**
`to_access_policy_create` emits `<key>-access-policy`; `to_policy_create` keeps
`<key>-policy` for the contract half, which is the id an agreement references. Conditions on
being *admitted* go in the access policy; terms of *use* go in the contract policy.

**2. Dataspace membership is a constraint on a credential claim.**
`{ns}Membership eq <dataspace uri>` is evaluated by `DataspaceMembershipFunction` against the
`memberOf` claim of the counterparty's `MembershipCredential`, read off the
`ParticipantAgent`. No HTTP call, so no cache and no TTL. `AccessScopeFunction`, ds-connector's
`GET /internal/participants/check` and `HttpParticipantRegistry.check_scope` are deleted; the
anchor's `GET /admin/participants/check` remains as an operator's route.

**3. "These named organisations" is `odrl:recipient`.** ODRL 2.2 Common Vocabulary: *"the
party receiving the result/outcome of exercising the action of the Rule"*, with a right
operand identifying parties. `RecipientFunction` compares `ParticipantAgent.getIdentity()`
against the set; an empty set denies. The set is a **set** from the start (`isAnyOf`, even for
one) because a recipient is routinely several organisations.

**4. Both are bound in the `catalog` scope, and only there.** EDC evaluates an access policy
with a `CatalogPolicyContext` both when it builds a catalogue
(`ContractDefinitionResolverImpl.resolveFor`) and when it validates an initial offer
(`ContractValidationServiceImpl.validateInitialOffer`). One binding covers discovery and
negotiation; binding either operand in `contract.negotiation` would be dead. The permitted
actions are bound in `catalog` too — `ScopeFilter` deletes a rule whose action is unbound, and
a policy whose only permission was deleted evaluates to *success*.

**5. The recipient set is derived, not declared twice.** It comes from
`recipients.recipient` on the sharing offers the dataset binds — the same declaration
`circle.admits_wildcard` reads for `D-14`. One rule, one implementation; two enforcement
points that cannot disagree about who the recipients are.

**6. The restriction is opt-in per dataset, confirmed by the maintainer 2026-09-18** —
`access_requirements: partner`, the value that
used to mean `owner:<alias>:partner`. Deriving it for every dataset with an offer would close
`D-15`'s per-party grant: a person may admit a party the offer does not name, and a
negotiation the access policy refuses never reaches the consent layer that would have admitted
them. Where a dataset does opt in, the provider's restriction is the outer one and a
per-party grant cannot widen it. A `partner` dataset that binds no offer is a **validation
error** (`recipient-restriction`), because the mapper would then emit no recipient constraint
at all — a restriction that evaporates when its input is missing is the fail-open `CR-4`
forbids.

**7. `recipients.controller` becomes `recipients.recipient`**, with `controller_role` →
`recipient_role` and `controller_roles:` → `recipient_roles:`. The old spellings are still
read from a governance file and logged as deprecated; the connector's `consent_requests`
columns are renamed by migration `0013`; `user_visible_facts` keeps its payload keys, so no
consent hash changes and nobody is asked again.

**8. `dataspace.audience` is deleted in full.** `membership` and `required_role` had no reader
anywhere. `required_scope` had one — it was the membership right operand for a dataset with no
`ownership` — and had to go with them: the value the constraint compares against is the
dataspace's own identity, one per deployment, and a per-dataset override of that is the same
invention under a new name.

## Consequences

**Immediate deactivation now relies on status-list suspension**, not on a 60-second HTTP
check. Checked before deciding: ds issues every credential with two `StatusList2021Entry`
entries (revocation and suspension) on one mirrored index, publishes both registers
unauthenticated as signed VC-JWTs, and EDC 0.18.0 enforces them —
`RevocationServiceRegistryExtension` registers `StatusList2021RevocationService`,
`VerifiableCredentialValidationServiceImpl` runs `IsNotRevoked` over every credential, and
`BaseRevocationListService` validates a JWT status list through the DID public key whenever
the accepted content type is not exactly `application/json` (the default is `*/*`).

**The window is set to 60 seconds, not left at EDC's default.**
`edc.iam.credential.revocation.cache.validity` defaults to **15 minutes**, which would have
made a suspension take fifteen times longer to bite than the 60 s decision cache the HTTP
check had — a regression no test would report, because everything passes while a credential is
merely stale. The maintainer decided on 2026-09-18 to restore the old number: `60000` in all
three `services/connector/config/*.properties` and in the chart
(`revocationCacheValidityMs`).

**What that costs, precisely.** One conditional GET per **register** per **runtime** per
minute — `/status/1` and `/status/2` on the trust anchor — not one per negotiation and not one
per counterparty, because a register is shared by every credential the anchor issues. So the
anchor sees a steady, bounded rate that does not grow with exchange volume, against a call
that used to sit on the critical path of every negotiation. The register is static, signed and
unauthenticated, so an anchor outage costs freshness rather than availability; a fetch that
fails makes the credential fail closed, which is the safe direction and the reason not to push
this much lower.

`RuntimeContractTest.everyConfigSetsTheRevocationCacheValidity` holds the four copies to one
value and resolves the chart's Helm reference against `values.yaml`, so it asserts what a
cluster would run rather than that the chart has a placeholder.

**A restricted offering is invisible to the federated crawler** unless the crawler's
participant is a recipient. Accepted: the federated index is advisory (`C-2`), never
authority, and an index that listed what its reader may not have would leak the existence of
exactly the datasets a producer restricted. Recorded in
`docs/services/federated-catalog.md` and asserted by `ds-e2e --flow catalog-discovery`.

**The negotiation fail-closed gate changed target.** Consent is the only constraint family
that still calls ds-connector, so `ds-e2e --flow fail-closed` negotiates for the consent-gated
dataset and establishes the grant itself. A membership-gated target would now agree happily
with the PDP stopped, and the flow asserts that it is no longer a valid target rather than
leaving the trap for the next reader.

**A deployment must:** drop every `owner:*` grant from enrolment and from
`allowed_scopes`, re-issue `MembershipCredential`s so the `memberOf` claim is present and
correct, set `CONNECTOR_DATASPACE_URI` to the same value as
`IDENTITY_REGISTRY_DATASPACE_URI` (a mismatch denies every negotiation, which is at least the
safe direction), run connector migration `0013`, rebuild the EDC image — the constraint
functions are Java — and carry
`edc.iam.credential.revocation.cache.validity=60000` into its own EDC configuration if it
does not render the chart.

## Alternatives considered

**Keep the HTTP membership check alongside the credential claim**, for immediate
deactivation. Rejected 2026-09-17 by the maintainer: it is the central call DCP removes, it
can disagree with the signed claim, and status-list suspension already answers the question
the check was kept for. The price is a *window* rather than a lost property, and the window is
configured rather than inherited — see the consequences above.

**Declare the recipient set on the dataset** instead of deriving it from the offers.
Rejected: `circle.admits_wildcard` already reads `recipients.recipient` for `D-14`, and two
declarations of one restriction disagree the moment one is edited.

**EDC 0.18.0's CEL policy functions** (`decentralized-claims-cel`), which can express
`vc[…].credentialSubject.memberOf` directly. Rejected for now: the module ships only in the
virtual BOM and is marked experimental, and ds already has a constraint-function surface with
a registration test behind it.
