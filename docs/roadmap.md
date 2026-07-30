# Roadmap

Where the platform stands today, and what is deliberately deferred. This page exists so that
work scoped *out* of an iteration keeps its design rationale instead of being rediscovered later.

## Where this version arrives

The consumer-pull data exchange is complete end to end: catalogue discovery, ODRL contract
negotiation, EDR-gated transfer, consent-based row filtering, and PROV-O provenance.
Participants hold `did:web:` identities issued by the identity registry, and organisations are
registered as owners with memberships binding user DIDs to them.

The onboarding chain — an external participant onboarding service provisioning DIDs,
credentials, memberships and Keycloak mappings on approval — is wired and fail-closed. The
wizard also collects an **optional** data-sharing consent (never a condition of membership,
per GDPR Art. 7(4)) and provisions it to the connector on approval via
`POST /consent/admin/shares`, keyed to the sharing offer the person accepted. A failed share
never tears down a valid identity; it is retried from the admin UI.

Consent is expressed as **sharing offers**: purpose-scoped bundles a person agrees to once,
described in human terms (what data, at what resolution, over what period, for what purpose)
rather than as dataset identifiers. Purposes form a local SKOS hierarchy aligned to the
[W3C Data Privacy Vocabulary](https://w3id.org/dpv/), and purpose limitation is enforced at
negotiation time, not merely declared. An operator-provisioned consent is a **scoped
wildcard** — it admits any party inside the circle for that controller and purpose, and every
row carries a non-PII legal-basis evidence record. Consent grants and revocations, recorded
DSO/offline ingestions (`POST /admin/ingestion`), and offline CSV disclosures each emit a
PROV-O event carrying **codes, DIDs and hashes only** — a recomputable `consent_snapshot_hash`
proves which consent state authorised a handover without the provenance store holding any
subject data.

Organisation onboarding — application, verification, service agreement, organisation credential,
promotion to participant, and a provisioning bundle the new participant stands its own deployment
up from — is available as an **API surface, a CLI** (`ir-cli org`) **and a portal surface**: an
invite-gated public application form at `/join`, and an operator review queue at
`/admin/onboarding` with agreement versions and acceptances at `/admin/agreements`. Every portal
action calls the same registry endpoint as the CLI, which stays the reference implementation.
Applicants need no identity of their own: intake is gated by a single-use invite code the operator
issues, so a public write is not an open one. The bundle rotates the STS secret on every call —
the registry stores a hash and cannot re-show one — which also makes a leaked bundle revocable.

## Next developments

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

### Purpose-specific agreements

A consumer's declared intent **is** now persisted: `POST /consumer/negotiate` accepts a
purpose, a timeframe and an opaque justification reference, validated against the purposes
the offer permits and recorded on the access request and on `AccessRequested`.

What remains is that the declaration is *accountability, not enforcement*. The provider
decides on the offer's purposes, because those are what crossed the wire, and a
multi-purpose dataset is published as one `odrl:purpose` constraint with `odrl:isAnyOf` over
every permitted purpose — so the **agreement** still says "any of these three".

The declaration cannot close that at the protocol layer. EDC resolves the contract policy
from the offer id against the provider's own contract definition and discards the policy the
consumer sent, so a consumer cannot narrow what it agrees to. Two routes exist, and neither
is free:

- **One contract offer per purpose.** Choosing an offer becomes choosing a purpose, bound
  into the agreement policy where a third party can read it, with no new API and no
  self-asserted claim. Cost: the catalogue grows per dataset, and the sharing-offer model,
  the mapper and the compliance evidence all change shape.
- **A cross-participant declaration channel.** Rejected once already, on the grounds that
  DSP proves the requester cryptographically and a header-authenticated side channel
  proves less — the reasoning that removed `POST /consent/request`.

Worth noting that neither ODRL nor the DSSC blueprint requires the narrowing: the
Information Model defines `Offer` and `Agreement` as distinct policy types and says nothing
about deriving one from the other. This is a legibility and audit-quality decision, not a
conformance gap.

### Anonymisation as an alternative to consent

Where a recipient needs only aggregate insight, anonymised output would fall outside the scope
of data protection law entirely, removing the need to ask each person. This is worth exploring,
but it is not a shortcut: fifteen-minute household load curves are notoriously re-identifiable,
and reaching genuine anonymity means either sophisticated treatment of load shapes or
aggregation coarse enough to destroy much of the analytical value. It deserves its own
assessment rather than being assumed.

### Subject identifier hardening

**Done.** User DIDs are derived from an HMAC of the login email keyed by
`ENCRYPTION_KEY`, which keeps personal data out of DID paths and makes the
identifier uncomputable without the deployment's key. Previously an unsalted
SHA-256 hash was used, making DIDs correlatable across deployments. Existing
DIDs are stored and unaffected by the change.
