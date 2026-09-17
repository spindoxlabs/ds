# EDC internals

How Eclipse Dataspace Components (EDC) works inside, for the version this repository pins.
**Read this before building anything around the connector.** Much of what a data-space
platform needs — contract state machines, policy scopes, credential checks, callbacks,
per-tenant APIs — EDC and the protocols it implements already provide, and a local copy of
an upstream feature is a second thing to keep correct.

These pages describe **upstream EDC**, not ds. Where a page can state what ds adds from ds's
own code, it says so in a closing section; everything else is about EDC. For ds's own
assembly see [edc-connector](../services/edc-connector.md) and
[edc-extensions](../services/edc-extensions.md).

## One directory per pinned version

The version is `edcVersion` in `gradle.properties`. The rule:

1. **Each pinned EDC version has its own directory**, `docs/edc/v<version>/`, written from
   that version's source tag — not from `main`, and not from memory.
2. **An upgrade adds a new directory.** The old one stays until nothing in the repository
   refers to that version any more, then it is removed in its own change.
3. **Every claim cites a path** relative to the EDC repository root (`Connector:`,
   `IdentityHub:`, `Runtime-Metamodel:`), and decision records are cited only if present in
   that version's tree. What could not be checked is marked *not verified*.
4. Specification references name the tag read (DSP `2025-1-err1`, DCP `v1.0.1`).

| Version | Pinned since | Pages |
|---|---|---|
| [0.18.0](v0.18.0/index.md) | current | runtime · control plane · policy engine · identity and trust · Management API · participant context · data plane · events and extensibility |

To re-check a page, fetch the tagged sources and grep for the cited class:

```
git clone --depth 1 --branch v0.18.0 https://github.com/eclipse-edc/Connector
grep -rn "class ContractValidationServiceImpl" Connector/core
```

## If you are about to build X, EDC already does it

All links are to the 0.18.0 pages.

| You are about to build… | EDC 0.18.0 already has | Where |
|---|---|---|
| a "who may see this offer" filter | the contract definition's **access policy**, evaluated in `catalog` scope | [Control plane](v0.18.0/control-plane.md#access-policy-versus-contract-policy) |
| a "may this contract be signed" check | the **contract policy**, `contract.negotiation` scope, `ContractValidationServiceImpl` | [Policy engine](v0.18.0/policy-engine.md#every-scope-in-0180) |
| a check when a transfer starts | the `transfer.process` scope on the agreement policy | [Policy engine](v0.18.0/policy-engine.md#every-scope-in-0180) |
| a job that re-checks running transfers and stops them | the **policy monitor** (`policy.monitor` scope) | [Policy engine](v0.18.0/policy-engine.md#the-policy-monitor) |
| contract expiry | `ContractExpiryCheckFunction`, left operand `edc:inForceDate` | [Policy engine](v0.18.0/policy-engine.md#built-in-functions) |
| a way to hold a negotiation until someone decides | `ContractNegotiationPendingGuard` and the entity `pending` flag | [Control plane](v0.18.0/control-plane.md#contract-negotiation) |
| negotiation / transfer state tracking, retries | the two state machines, `RetryProcessor`, leases | [Control plane](v0.18.0/control-plane.md) |
| a notifier for negotiation or transfer changes | `EventRouter` subscribers, per-request and static **callbacks**, CloudEvents / NATS publishers | [Events and extensibility](v0.18.0/events-and-extensibility.md#events) |
| a caller identity from a DSP request | `ProtocolTokenValidatorImpl` → `ParticipantAgent` | [Policy engine](v0.18.0/policy-engine.md#participantagent) |
| credential verification, trusted-issuer lists, revocation | DCP in `decentralized-claims-*`, `edc.iam.trustedissuer.*`, StatusList2021 / Bitstring status list | [Identity and trust](v0.18.0/identity-and-trust.md#credential-verification) |
| a mapping from policy to requested credentials | DCP scope extractors and `edc.iam.dcp.scopes.*` | [Identity and trust](v0.18.0/identity-and-trust.md#scopes) |
| a token service, DID publishing, a credential store | IdentityHub (STS, credential service, DID publisher, Identity API) | [Identity and trust](v0.18.0/identity-and-trust.md#identityhub) |
| an API-key or JWT guard for the Management API | `auth-tokenbased`, `auth-delegated`, `management-api-oauth2-authentication` | [Management API](v0.18.0/management-api.md#authentication) |
| per-tenant authorisation on the Management API | `@RequiredScope`, `AuthorizationService`, `management-api:<resource>:<action>` scopes (v5beta) | [Management API](v0.18.0/management-api.md#scope-grammar) |
| one connector serving several organisations | participant contexts and the virtual control plane | [Participant context](v0.18.0/participant-context.md) |
| per-organisation settings and secrets | `ParticipantContextConfig` (encrypted private entries), partitioned `Vault` | [Participant context](v0.18.0/participant-context.md#per-participant-configuration) |
| a signed access token for consumer pull | `data-plane-iam`: EDR creation, token signing, `AccessTokenDataStore`, `DataPlaneAuthorizationService.authorize` | [Data plane](v0.18.0/data-plane.md#pull-the-edr-and-its-token) |
| a consumer-side EDR cache | `edr-store-receiver` and `/v3/edrs` — **deprecated**; ds takes the EDR from the transfer's own callback instead | [Data plane](v0.18.0/data-plane.md#how-the-edr-reaches-the-consumer) |
| an integration for an external data plane | the Data Plane Signaling protocol stack | [Data plane](v0.18.0/data-plane.md#integrating-an-external-data-plane-current-stack) |
| input validation for the Management API | `JsonObjectValidatorRegistry`, JSON Schemas | [Events and extensibility](v0.18.0/events-and-extensibility.md#extension-points) |
| a federated catalogue crawler | `catalog-crawler-core` and `federated-catalog-api` | [Control plane](v0.18.0/control-plane.md#catalogue) |
| database schema creation | `edc.sql.schema.autocreate` and the SQL store modules | [Events and extensibility](v0.18.0/events-and-extensibility.md#stores-and-sql) |
| service wiring, config loading, env-var mapping | the extension loader, `@Inject` / `@Provider` / `@Setting` | [Runtime model](v0.18.0/index.md) |

## Behaviour that surprises people

A short list, each explained on its page.

- **An unbound left operand is removed from the policy before evaluation**, so the
  constraint is silently ignored. A bound one with no function fails.
  ([Policy engine](v0.18.0/policy-engine.md#rule-bindings-and-the-scope-filter))
- **The provider agrees to a valid request automatically**; holding it needs a pending guard.
  ([Control plane](v0.18.0/control-plane.md#contract-negotiation))
- **The classic Management API (v3, v4) has no per-resource authorisation.** Scopes and
  ownership checks exist only on `/v5beta`, in the virtual control plane.
  ([Management API](v0.18.0/management-api.md#2-oauth2-principal-scopes-management-api-oauth2-authentication-management-api-authorization))
- **The EDC data plane is deprecated**, there is no data-plane public API module, and no
  EDR endpoint generator is registered upstream.
  ([Data plane](v0.18.0/data-plane.md))
- **A credential with an unknown status type is not treated as revoked.**
  ([Identity and trust](v0.18.0/identity-and-trust.md#credential-verification))
