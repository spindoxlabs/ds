# EDC 0.18.0 — Management API

Which Management API versions exist in 0.18.0, which module ships each, and every way a
caller can be authenticated and authorised. Paths are relative to the `Connector`
repository at `v0.18.0` unless another repository is named.

## Versions

`extensions/common/api/management-api-configuration/src/main/resources/management-api-version.json`
— the content served by the version API:

| Version | URL prefix | Maturity | Shipped by |
|---|---|---|---|
| 3.1.6 | `/v3` | **deprecated** | `extensions/control-plane/api/management-api` (classic) |
| 4.1.0 | `/v4` | **stable** | `extensions/control-plane/api/management-api` (classic) |
| 5.0.0-beta | `/v5beta` | **beta** | `extensions/control-plane/api/management-api-v5` (virtual) |

There is **no `/v4beta` and no `/v5`** path in 0.18.0; the v5 prefix is literally `/v5beta`.
Every v3 controller carries `@Deprecated(since = "management-api:v3")`, and
`ManagementApiConfigurationExtension` registers a `DeprecatedVersionLog` filter that logs a
deprecation warning for any `v3/` request.

The version API itself is `GET /v1/version` (`extensions/common/api/version-api/`,
`VersionApiController`), registered **without** a context alias, i.e. on the `default`
context.

### Resources per version

Classic controllers: `extensions/control-plane/api/management-api/<module>/`. v5:
`extensions/control-plane/api/management-api-v5/<module>-v5/`.

| Resource | v3 | v4 | v5beta |
|---|---|---|---|
| `assets` | ✓ | ✓ | `/v5beta/participants/{participantContextId}/assets` |
| `policydefinitions` | ✓ | ✓ | `…/{participantContextId}/policydefinitions` |
| `contractdefinitions` | ✓ | ✓ | `…/{participantContextId}/contractdefinitions` |
| `contractnegotiations` | ✓ | ✓ | `…/{participantContextId}/contractnegotiations` |
| `contractagreements` | ✓ | ✓ | `…/{participantContextId}/contractagreements` |
| `transferprocesses` | ✓ | ✓ | `…/{participantContextId}/transferprocesses` |
| `catalog` | ✓ | ✓ | `…/{participantContextId}/catalog` |
| `edrs` | ✓ | — | — |
| `secrets` | ✓ | ✓ | — (module `secrets-api` is in no BOM) |
| `dataplanes` | ✓ | ✓ | `…/{participantContextId}/dataplanes` |
| participant contexts | — | — | `/v5beta/participants` |
| participant config | — | — | `…/{participantContextId}/config` |
| dataspace profiles | — | — | `…/{participantContextId}/profiles` |
| discovery | — | — | `…/{participantContextId}/discover` |
| CEL expressions | — | — | `/v5beta/celexpressions` |

The EDR cache API exists only as v3 (module `edr-cache-api`, still part of the classic
aggregate). DR `2026-04-09-edr-cache-deprecation` removed it from v4 because EDR handling moves
to the data plane under the Data Plane Signaling protocol (see [Data plane](data-plane.md)).

`dataplanes`: `DataPlaneSignalingApiExtension`
(`data-protocols/data-plane-signaling/data-plane-signaling-core/.../port/api/management/`)
registers the v4 registration controller when a `SingleParticipantContextSupplier` exists, and
the v5 one otherwise — and then **fails if no `AuthorizationService` is present**.

## The management context

`ApiContext` (`spi/common/web-spi/.../configuration/ApiContext.java`) declares `management`,
`control`, `signaling` and `protocol`. `ManagementApiConfigurationExtension`
(`extensions/common/api/management-api-configuration/`):

| Setting | Default | Meaning |
|---|---|---|
| `web.http.management.port` | `8181` | port |
| `web.http.management.path` | `/api/management` | path |
| `edc.management.endpoint` | — | externally visible URL (`ManagementApiUrl`) |
| `edc.management.context.enabled` | `false` | register the EDC management JSON-LD context for v3 instead of plain namespaces |

It registers JSON-LD scopes `MANAGEMENT_API`, `MANAGEMENT_API:v4`, `MANAGEMENT_API:v5`
(`extensions/common/api/lib/management-api-lib/.../ManagementApi.java`) and transformers under
`management-api`. The module's README still says it registers an `AuthenticationRequestFilter`;
the 0.18.0 code does not.

**JSON Schema validation** (`extensions/common/api/management-api-schema-validator/`,
`ManagementApiSchemaValidatorExtension`) validates v4 and v5 payloads against
`classpath:schema/management/v4|v5`, extensible via `edc.mgmt.api.schema.*` (DR
`2025-08-01-json-schema-adoption`, "starting from `v4`"). Among the aggregates it is a
dependency of `management-api-v5` only; whether a classic runtime validates v4 payloads
against these schemas was not verified.

## Authentication

There are **two independent mechanisms**; which one applies depends on the modules present.

### 1. Per-context authentication (`auth-configuration`)

DR `2024-06-24-api-authentication-configuration`. `ApiAuthenticationConfigurationExtension`
(`extensions/common/auth/auth-configuration/`) reads, in `prepare()`, `web.http.<ctx>.auth.type`
for each context, resolves an `ApiAuthenticationProvider` of that type from the
`ApiAuthenticationProviderRegistry`, hands it the `web.http.<ctx>.auth.*` config, and
installs an `AuthenticationRequestFilter` on the context. An unknown type fails startup.
**No `auth.type` → no filter.** SPI: `spi/common/auth-spi/.../api/auth/spi/`
(`AuthenticationService.isAuthenticated(headers)`, `ApiAuthenticationRegistry`,
`ApiAuthenticationProviderRegistry`). This yields a yes/no; it sets **no principal**.

| Type | Module | Checks | Settings |
|---|---|---|---|
| `tokenbased` | `extensions/common/auth/auth-tokenbased` | exactly one `x-api-key` header (name case-insensitive); value compared with `equalsIgnoreCase` | `web.http.<ctx>.auth.key`, or `web.http.<ctx>.auth.key.alias` (vault; takes precedence) |
| `delegated` | `extensions/common/auth/auth-delegated` | exactly one `Authorization: Bearer` JWT; signature against a JWKS, `aud`, `nbf`, `exp`/`iat`. **No issuer check** | `web.http.<ctx>.auth.dac.key.url` (JWKS), `.auth.dac.cache.validity`, `web.http.management.auth.dac.audience` (falls back to `edc.participant.id` with a warning), `edc.api.auth.dac.validation.tolerance` (5000 ms) |

Both are in `controlplane-base-bom` and `controlplane-virtual-base-bom`.

The tokenbased key comparison ignores case — a note for anyone sizing the key's entropy.

### 2. OAuth2 principal + scopes (`management-api-oauth2-authentication` + `management-api-authorization`)

DR `2026-06-06-scope-based-api-authorization`. These modules are in
**`controlplane-virtual-base-bom` only**.

`ManagementApiOauth2AuthenticationExtension`
(`extensions/common/api/management-api-oauth2-authentication/`) installs two filters on
`management`:

1. `JwtValidatorFilter` (`extensions/common/auth/auth-authentication-oauth2-lib/.../filter/`)
   — requires `Authorization: Bearer`; validates signature against
   `edc.iam.oauth2.jwks.url` (required; cache `edc.iam.oauth2.jwks.cache.validity`, 300000 ms),
   `iss` against `edc.iam.oauth2.issuer` (optional), `nbf`, `exp`. **No audience check.**
   401 on failure.
2. `ServicePrincipalAuthenticationFilter` (same package) — reads `sub` and `scope`. If `scope`
   satisfies `management-api:admin`, the token is accepted whatever `sub` is. Otherwise `sub`
   must name an existing participant context, else 401. Sets a `SecurityContext` whose
   principal is `ParticipantPrincipal(sub, scope)` (`spi/common/auth-spi`).
   `isUserInRole` always returns false — there are no roles.

`ManagementApiAuthorizationExtension`
(`extensions/common/api/management-api-authorization/`) registers:

- `ScopeBasedAccessFeature` → `ScopeBasedAccessFilter` on every method annotated
  `@RequiredScope` (`extensions/common/auth/auth-authorization-oauth2-lib/.../filter/`):
  no principal → 403; not a `ParticipantPrincipal` → 401; scope not satisfied →
  403 `Required scope '…' missing`.
- `AuthorizationServiceImpl` (`.../service/`) — the ownership check a controller calls with
  `authorize(securityContext, resourceOwnerId, resourceId, resourceClass)`: resolve the
  resource through a registered lookup function (none → unauthorised, not found → 404);
  admin → allowed; otherwise principal name == owner id == the resource's
  `participantContextId`.

**The classic v3/v4 controllers use neither `@RequiredScope` nor `AuthorizationService`.**
Only v5 controllers (and the v5 data-plane registration controller) do. Adding the two OAuth2
modules to a classic runtime therefore authenticates v3/v4 requests but does not authorise
them per resource — not tested, inferred from the code.

### Scope grammar

`spi/common/auth-spi/.../Scope.java`, `ScopeMatcher.java`, `ManagementApiScopes.java`:

```
scope    := "management-api" [ ":" resource ] ":" action
resource := <term> | "*"          (default "*")
action   := "read" | "write" | "admin"      admin ⊇ write ⊇ read
```

A granted scope satisfies a required one when the prefix matches, the resource is equal or
`*`, and the action level is at least the required one. The `scope` claim is space-delimited;
unparseable entries are ignored. DR rules: `admin` is the only cross-tenant elevation
(`*:write` does not imply it), and `*` covers tenant-owned resources only.

Scopes required by the v5 controllers:

| Controller | Scopes |
|---|---|
| assets | `management-api:assets:read` / `:write` |
| policydefinitions | `management-api:policies:read` / `:write` |
| contractdefinitions | `management-api:contractdefinitions:read` / `:write` |
| contractnegotiations | `management-api:negotiations:read` / `:write` |
| contractagreements | `management-api:agreements:read` |
| transferprocesses | `management-api:transfers:read` / `:write` |
| catalog | `management-api:catalog:read` |
| discover | `management-api:discovery:read` |
| profiles | GET `management-api:profiles:read`; PUT `management-api:admin` |
| dataplanes | `management-api:dataplanes:write` |
| participants, participant config, CEL expressions | `management-api:admin` |

`AssetApiV5Controller.removeAssetV5` (`DELETE …/assets/{assetId}`) is annotated
`management-api:assets:read`, unlike every other v5 delete — the ownership check still
applies, but a read-only token of the owning participant can delete its assets. Observed in
the 0.18.0 source, not tested.

The DR lists per-resource scopes as a later step; the 0.18.0 code already uses them.

### Binding a caller to a participant context

In v5 the path parameter `{participantContextId}` is the tenant, and the token's **`sub`** is
the caller. There is no `participant_context_id` claim and no `role` claim in 0.18.0 (both
removed by DR `2026-06-06`).

- Collection and create endpoints call
  `authorize(sc, participantContextId, participantContextId, ParticipantContext.class)`;
  the lookup in `ParticipantContextManagementApiExtension`
  (`extensions/control-plane/api/management-api-v5/participant-context-api-v5/`) only
  matches when the ids are equal, so a non-admin `sub` must equal the path id.
- Item endpoints call `authorize(sc, participantContextId, id, <Type>.class)`, which also
  requires the stored resource's `participantContextId` to equal the path id. Lookup functions
  are registered by each `*ApiV5Extension`.
- Created entities are stamped with the path `participantContextId`; queries are filtered by
  it.
- Participant, config and CEL endpoints are guarded by `@RequiredScope("management-api:admin")`
  alone.

The Keycloak-side consequence (from the DR): a token needs only standard `sub` and `scope`
claims; no custom IdP mapper is required.

## Which modules to add

| You want | Modules | In |
|---|---|---|
| v3/v4, API key | `management-api`, `auth-configuration`, `auth-tokenbased` + `web.http.management.auth.type=tokenbased` | `controlplane-base-bom` |
| v3/v4, JWT checked against a JWKS | `auth-delegated` + `web.http.management.auth.type=delegated` | `controlplane-base-bom` |
| v5beta, per-tenant OAuth2 with scopes | `management-api-v5`, `management-api-oauth2-authentication`, `management-api-authorization`, plus a participant-context store and the virtual control plane | `controlplane-virtual-base-bom` |

v5 controllers inject `AuthorizationService`; without `management-api-authorization` (or
another provider) the runtime does not boot.

## IdentityHub's management API

IdentityHub 0.18.0 uses the same `ScopeBasedAccessFeature` and `AuthorizationServiceImpl`,
with its own scope namespaces `identity-api:…` and `issuer-admin-api:…`
(`IdentityHub: spi/participant-context-spi/.../IdentityApiScopes.java`). Its default
authentication is an `x-api-key` whose prefix encodes the participant context id, checked
against the vault; an OAuth2 variant (`identity-api-authentication-oauth2`) reuses the
Connector's `JwtValidatorFilter`. Its API prefix is `/v1beta`
(`IdentityHub: extensions/api/identity-api/identity-api-configuration/.../Versions.java`).

## What ds adds on top

ds packages `controlplane-dcp-bom` — the classic `management-api` (v3, v4) — and sets
`web.http.management.auth.type=tokenbased`, so the Management API is guarded by an
`X-Api-Key`. It adds one route, `POST /dataspaces/negotiations/{id}/resume`
(`services/edc-extensions/.../NegotiationResumeController.java`). See
[edc-connector](../../services/edc-connector.md#the-api-contexts).
