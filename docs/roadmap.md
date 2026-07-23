# Roadmap

Where the platform stands today, and what is deliberately deferred. This page exists so that
work scoped *out* of an iteration keeps its design rationale instead of being rediscovered later.

## Where this version arrives

The consumer-pull data exchange is complete end to end: catalogue discovery, ODRL contract
negotiation, EDR-gated transfer, consent-based row filtering, and PROV-O provenance.
Participants hold `did:web:` identities issued by the identity registry, and organisations are
registered as owners with memberships binding user DIDs to them.

The onboarding chain — an external participant onboarding service provisioning DIDs,
credentials, memberships and Keycloak mappings on approval — is wired and fail-closed.

Consent is expressed as **sharing offers**: purpose-scoped bundles a person agrees to once,
described in human terms (what data, at what resolution, over what period, for what purpose)
rather than as dataset identifiers. Purposes form a local SKOS hierarchy aligned to the
[W3C Data Privacy Vocabulary](https://w3id.org/dpv/), and purpose limitation is enforced at
negotiation time, not merely declared.

Organisation onboarding — verification, service agreement, organisation credential, promotion
to participant — is available as an **API surface plus a CLI** (`ir-cli org`), driven by
templated YAML in the established seed-and-import pattern.

## Next developments

### Self-service organisation registration in the portal

**Status: designed, deferred.** Organisations are currently enabled through an external
interface calling the registration API; there is no public sign-up.

The intended shape, when it is picked up:

- A public route group in the portal (`/onboarding/organization`) carrying the applicant
  wizard: legal entity details → registration number and country → legal representative
  contact → requested role (consumer or provider) → DSP endpoint if provider → evidence
  upload → service agreement acceptance → submit.
- An operator review queue at `/admin/onboarding` — already delivered in read-only form with
  action buttons; the wizard adds applications to the same queue.
- Applicant authentication is the open design question. An applicant is by definition not yet
  a participant, so the portal's participant-scoped auth does not cover them. The preferred
  answer is a self-registered Keycloak user in an `applicants` group, reusing the existing
  group-to-scope mapping; the alternative is a session-token pattern, which has the drawback
  of adding a further authentication mechanism to a codebase that already carries several.
- The hard constraint carries over: every action the wizard performs goes through the same
  registry endpoints the CLI calls. The CLI remains the reference implementation.

Deferring this costs nothing structurally — the state machine, credential type, agreement
records and review queue all exist. What is missing is only the applicant-facing surface.

### Data holder as a second provider participant

Today a data holder such as a distribution system operator can hand over data offline, under a
data processing agreement, with the disclosure recorded as a provenance event. That is
auditable but not sovereign: once the data lands in the receiving participant's dataset API,
the original policies no longer govern that copy.

The target is the standard dataspace arrangement — the data holder runs its own connector,
data stays at source, and the consent list travels as a verifiable credential the holder
verifies independently. The substrate exists (`DataSubjectCredential` plus StatusList2021
revocation); what is missing is a consent credential type carrying subject, offer, purpose and
validity, and a verifier on the holder's side.

### Gaia-X compliance

Organisation credentials are deliberately **shape-compatible** with `gx:LegalParticipant` —
the registration number enum, ISO 3166-2 country codes, and the headquarters/legal address
split are adopted verbatim, and the service agreement record is shaped so it can become a
`gx:GaiaXTermsAndConditions` credential.

Full compliance is a separate project: it requires integration with a Gaia-X Digital Clearing
House notary to validate registration numbers against authoritative registries, SHACL shape
conformance, and a keypair lifecycle with revocation on inaccurate statements. The door is
open at near-zero ongoing cost; walking through it is a decision about federation ambitions,
not a technical gap.

### Auditable consumer access requests

A consumer's declared intent is not persisted — the access request model records the asset,
offer, assigner and status, but not the purpose, timeframe or justification the consumer
stated. Adding these turns a negotiation into an auditable request. This becomes more
valuable now that purpose is a validated taxonomy term rather than free text.

### Anonymisation as an alternative to consent

Where a recipient needs only aggregate insight, anonymised output would fall outside the scope
of data protection law entirely, removing the need to ask each person. This is worth exploring,
but it is not a shortcut: fifteen-minute household load curves are notoriously re-identifiable,
and reaching genuine anonymity means either sophisticated treatment of load shapes or
aggregation coarse enough to destroy much of the analytical value. It deserves its own
assessment rather than being assumed.

### Subject identifier hardening

User DIDs are derived from a hash of the login email, which correctly keeps personal data out
of DID paths. Because the hash is unsalted, a DID is computable from a known email address and
therefore correlatable across deployments. A per-deployment salt closes this; it is small,
independent, and low urgency.
