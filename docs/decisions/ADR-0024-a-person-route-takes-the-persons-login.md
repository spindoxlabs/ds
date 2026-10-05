# ADR-0024 — A person route takes the person's own login, bound to their credential

**Date:** 2026-10-05
**Status:** accepted, implemented 2026-10-05
**Rules affected:** `D-20` (subject-facing surfaces authenticate the subject, never a
service's scope), `L-11` (a subject reads their own history), `P-8b` (the revocation list
is served signed)

## Context

A person's user credential (`X-User-VC`) is a **bearer** credential. The person holds no
key and signs nothing (`D-22`): the identity registry issues the credential, and the
services that act for the person (the portal, or another platform's member service) fetch
it from the registry with their own service token and forward it. Every route that
accepted the credential (`/consent/my/*`, `/consent/status`, `/consumer/*` with a
credential, `/prov/my/events`) therefore accepted **any** caller that could read it from the
registry. That caller could act as that person, approve or withdraw their consent and read
their history, without that person ever having logged in.

Two other gaps applied to the same routes. A credential with no `exp` never expired. The
revocation check was optional: no deployment configured it, it read the unsigned JSON form
of the register, and it had no cache.

The protocols ds builds on do not cover a person:

- **DCP** (EDC 0.18.0 on the classpath) binds a presentation to its holder through a
  self-issued token (`iss == sub`, `aud`, `jti`) signed by the participant's key, held in
  its STS or IdentityHub. That binding applies only between participants, and its trust
  model says "presentation protocols that rely on end-user (i.e., human) consent are not
  applicable".
- **OID4VP / SIOPv2** would bind a person through a wallet-held key, a nonce and the
  audience. ds has no wallet and no key per person, and the requester's working
  assumption is that people do not act on the dataspace side directly. At most they log
  in to a portal, and intermediate services act for them.

What a person does have is a **Keycloak login**. Every service that acts for them received
the login token on the request it is serving.

## Decision

1. **Every person route also takes the person's own Keycloak access token**
   (`Authorization: Bearer`). It is verified like any other token: signature, issuer, and
   the service's **own audience**. A person's token through the gateway carries every ds
   service's audience, because of the realm's `oauth2_proxy_client` mapper. The token's
   **identity must be the subject the credential names**.
2. **The binding key is the Keycloak user id (`sub`) within its realm.** The identity
   registry already stores it: one `keycloak_mappings` row per (realm, user id), unique,
   written at onboarding (`POST /admin/keycloak/sync`). Email and username were rejected
   because both can change, and `resolve_mapping` calls the email a bootstrap seed.
3. **The registry answers with the person's own token.** `GET /users/me`, which the
   service calls with the token it was handed, returns the DID that login is bound to.
   The response is a 404 when the login is bound to no DID and a 403 for a service token.
   The service needs no credential or grant of its own for this, and it can learn a
   person's DID only while it holds that person's login. Positive answers are cached for
   60 s.
4. **Posture.** The binding is required everywhere except `DS_ENV=dev`. A presented person
   token is always verified and bound, in dev too. `*_PERSON_TOKEN_REQUIRED=false` is an
   explicit **transition switch** for a caller that does not forward the token yet. The
   service logs a warning at startup when the switch is set outside dev.
5. **Revocation and expiry are required.** `exp` is mandatory on a user credential. A
   status source is required outside dev: `ProductionGuard` requires
   `*_CREDENTIAL_STATUS_URL`, and the verifier answers 503 at the point of use when it is
   missing. The register is read as the trust anchor's **signed VC-JWT** and verified
   against the key its DID document publishes. An unsigned register is refused, as is an
   unknown `credentialStatus` type; EDC logs and passes an unknown type. Verified
   registers are cached for `*_CREDENTIAL_STATUS_CACHE_SECONDS`, 900 s by default, the same
   as EDC's `edc.iam.credential.revocation.cache.validity`. That value is the revocation
   latency. The register is a `BitstringStatusListCredential` and new credentials carry
   `BitstringStatusListEntry` (DCP v1.0 issuance MUST, and what EDC's IssuerService
   publishes); `StatusList2021Entry`, on credentials issued before, is read against the
   same register, so they verify through the transition. `/status/{id}` answers the
   signed VC-JWT by default, JSON only when asked for by name, and 415 otherwise.

## Alternatives rejected

- **A holder-signed presentation (OID4VP-style), with a key per person.** This is real
  holder binding, but it needs a wallet or a per-person key, recovery and a client in the
  browser. If the key were held by the server, it would bind nothing that this decision
  does not already bind. It stays open for when wallets come into scope, for example
  EUDI.
- **DCP for persons.** Every person would need a participant context and an STS. The key
  would be held by the server, so nothing would be gained, and the protocol excludes
  people.
- **A DID claim in the Keycloak token** (a user attribute plus a protocol mapper). This
  was removed earlier because it needs write access to a realm ds may only be a guest in.
- **A login reference inside the credential.** Every credential in circulation would need
  re-issuing, and a correlatable identifier would travel with it.
- **A yes/no binding route behind a service scope.** The first implementation did this.
  It was replaced by `GET /users/me`, because that route needs no new service client for
  provenance and lets no service ask about a person whose login it does not hold.

## Consequences

- A caller **outside ds** that relays a person's credential without the person's token is
  refused outside dev, unless the deployment sets the switch. Callers must forward the
  person's access token. When the token they hold lacks the ds audiences, they must
  exchange it (RFC 8693) for one that has them.
- Provenance needs `PROVENANCE_IDENTITY_REGISTRY_URL`, and its chart's egress to the
  authority namespace on port 30005.
- A revoked credential stays usable for up to the status cache TTL. The credential lifetime
  (365 days by default) is unchanged. Short lifetimes need an automatic re-issue path
  first: today an expired credential is simply no longer offered.
- What the binding proves is "this request carries a login of the person the credential
  names". It does not prove that the person consented to this specific call. That would
  need a per-call presentation, which is the OID4VP option above.
