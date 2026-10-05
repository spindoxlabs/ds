# ds-auth

`import ds_auth`

The library that carries the platform's **authentication and authorisation decision**. Every
Python service mounts its guards; none of them re-implements the logic.

It verifies a bearer JWT against a Keycloak realm, normalises the resulting claims into one
`Principal` regardless of whether the caller is a machine or a person, expands a person's
platform roles and organisation groups into a capability set through a role-bundle table that
lives in code, and exposes the FastAPI dependencies routes actually use.

Three things ride along with that decision: a client-credentials token provider for outbound
service-to-service calls, a Verifiable-Credential verifier for the subject-facing surfaces that
do *not* use bearer tokens, and a boot-time guard that turns dev defaults into a startup
failure in production.

The core is framework-free; only two modules import FastAPI.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Trust Framework](../../blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) · [DSSC · Identity & Attestation Management](../../blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules it enforces | [Rulebook · Participation and trust](../../rulebook/participation.md) |

## Two mechanisms, one library

| Module | Authenticates | Used by |
|---|---|---|
| `jwt.py` + `fastapi.py` | a **service or an operator**, via an OIDC token, on scopes or on roles and organisation groups | almost every route |
| `user_credentials.py` | a **person's credential**, an ES256 VC-JWT signed by the trust anchor. `exp` is required, and the credential is checked against the anchor's **signed** status registers (`BitstringStatusListEntry`, and `StatusList2021Entry` on credentials issued before R3; `encodedList` as multibase base64url or plain base64), verified and cached (`DEFAULT_STATUS_CACHE_SECONDS`, 900). A status source is required unless `DS_ENV=dev` | connector `/consent/my/*` and `/consumer/*`; provenance `/prov/my/events` |
| `person_binding.py` | **the person behind the credential**: their own Keycloak access token, verified for the service's audience and bound to the credential's subject by the identity registry (`GET /users/me`, asked with that token). Required unless `DS_ENV=dev` or `*_PERSON_TOKEN_REQUIRED=false` ([ADR-0024](../../decisions/ADR-0024-a-person-route-takes-the-persons-login.md)) | the same routes |

The VC verifier lives here rather than in one service because two services verify the same
credential and must agree on what a valid one is.

## The guards

```python
Depends(require_permission("connector.provider.write", "connector.admin"))
Depends(require_exact_permission("connector.internal"))
```

| Factory | Matching |
|---|---|
| `require_permission(*perms, perimeter=…)` | **any-of, with superset** — a held grant satisfies a required one if it is equal, or if it is `{service}.admin` and the requirement starts with `{service}.` |
| `require_exact_permission(*perms, perimeter=…)` | **any-of, by name only** — `{service}.admin` never satisfies it |

The exact form is what makes machine-only permissions unreachable by an administrator.
`connector.admin` satisfies `connector.internal` under the first rule and fails it under the
second, which is why the internal API uses the second.

Both return the `Principal` on success, so a handler can take it as its dependency value. Both
accept an optional **perimeter** — a callable run *after* the permission check that can narrow
further, e.g. to the organisation the caller acts for.

Error mapping: missing or invalid token → `401`; valid token without the permission → `403`;
**auth not configured → `500`**, because that is a server fault, not a client one.

## `Principal` — one caller shape

```
subject · is_service · scopes · realm_roles · organizations · claims
```

The load-bearing property is `authority`, and it branches:

| Caller | Authority is |
|---|---|
| **service** | its `scope` claim, **verbatim** — a bundle name in a scope claim means nothing |
| **user** | `platform_authority` (allowlisted realm roles, expanded) plus, for each organisation, what that organisation's own groups grant within it — a user's `scope` claim confers nothing at all |

A person's authority has **two levels**
([ADR-0023](../../decisions/ADR-0023-a-persons-authority-has-two-levels.md)):

| | `platform_authority` | `authority_in(alias)` |
|---|---|---|
| from | `realm_access.roles`, only roles in `REALM_ROLE_BUNDLES` | `organization.<alias>.groups` |
| expands | a platform bundle (`ds-admin`, `ds-onboarding-operator`) | an organisation bundle, or a name in `ORGANISATION_PERMISSIONS` |
| valid | everywhere | that organisation only |

The `groups` claim is never read for authority: a realm-level group grants nothing. Nor is any
client's `resource_access`. `is_platform_admin` is true for a person holding `platform-admin`.

`grants_in(alias, *perms)` answers the per-organisation question: the platform authority, plus
*that organisation's* own groups for a member — never another organisation's, never a realm
group. A service principal is never owner-scoped, so `grants_in` is always false for one — a
call site that must exempt services checks `is_service` first.

`authority`'s organisation part answers "somewhere", not "here". It can only hold
`ORGANISATION_PERMISSIONS` — no `*.admin` superset, nothing only a platform bundle names — so it
cannot add up to a platform grant; a perimeter on an owner's resource still asks `grants_in`.

### An organisation's own clients

`organisation_context` is the organisation's DID (`sub`) for a token from either of an
organisation's clients, and `None` for any other token. `organisation_client_kind` says which
client minted the token. It is decided by the client id, never by `sub`:

| client | kind | holds |
|---|---|---|
| `svc-ds-connector-<alias>` | `connector` | `ORGANISATION_CLIENT_DEFAULT_SCOPES`; optional: `MANAGEMENT_API_SCOPES`, `edc.management`, `ORGANISATION_ACTION_SCOPES` |
| `svc-ds-collector-<alias>` | `collector` | nothing by default; optional: `COLLECTOR_CLIENT_OPTIONAL_SCOPES` |

`EDC_TOKEN_SCOPE` lists the 7 management scopes and `edc.management` explicitly. It no longer
means "every optional scope", which would put the organisation's acts into the token the
connector hands its EDC.

### One audience per scope (`ds_auth.audience`)

`SCOPE_AUDIENCES` maps each organisation-attributable scope to the one audience it adds
([ADR-0026](../../decisions/ADR-0026-an-organisation-acts-through-its-collector-client-one-audience-per-scope.md)).
A receiver applies the following on those routes:

- `audience_bound(perimeter)` / `check_audience_bound`: a service token must name the
  service's own audience (`OidcConfig.audience`) in `aud`. A collector token must name no
  other ds service (`DS_SERVICE_AUDIENCES`), which is the one-scope-per-token rule. A person
  is not checked here. A service without a configured audience refuses.
- `transition_bound(act, perimeter)`: the audience check, then
  `plain_service_transition`. A plain service token, meaning one that is not an
  organisation's client, doing an organisation's act is refused unless `DS_ENV=dev`. In dev
  a warning names the client. This covers the grants that moved from `svc-ds-onboarding`
  (`ONBOARDING_TRANSITION_SCOPES`).

Both helpers are `require_permission` perimeters, so the guarded route still publishes its
permission for the e2e route sweep.

### How a caller is classified

In order:

| # | Condition | Result |
|---|---|---|
| 1 | `preferred_username` starts with `service-account-` | service |
| 2 | `gty == "client-credentials"` | service |
| 3 | `email` present | user |
| 4 | a group present, at either level (classification only — it grants nothing) | user |
| 5 | `preferred_username` present | user |
| 6 | `client_id` present | service |
| 7 | `azp` present | service |
| 8 | otherwise | user |

This matters when writing tests: a token carrying only `{scope, sub}` falls through to rule 8
and is classified as a **user**, whose authority is then the expansion of an empty group list —
so its `scope` claim is ignored entirely.

## The role-bundle table

Layer A: ds's own semantics, in code, deliberately **not** deployment configuration.

| Bundle | Expands to |
|---|---|
| `ds-admin` | `identity-registry.admin`, `connector.admin`, `provenance.read`, `provenance.write`, `catalog.read` |
| `ds-participant-admin` | `connector.provider.read`, `.write`, `connector.history.read`, `connector.registry.invalidate`, `connector.ingestion.record`, `connector.disclosure.record`, `catalog.read`, `provenance.read`, `identity-registry.read`, `.membership.read` |
| `ds-participant-viewer` | `connector.provider.read`, `connector.history.read`, `catalog.read`, `provenance.read`, `identity-registry.read` |
| `ds-onboarding-operator` | `identity-registry.organizations.read`, `.write`, `.agreements.read`, `.participants.write`, `identity-registry.read` |
| `ds-member` | `catalog.read` |

`connector.consent.provision` left `ds-participant-admin` on 2026-09-17: a participant seat is
bound to no connector, so a participant operator holding it could register consent at any connector,
for any organisation's members. An organisation's own clients request it as an optional scope
(`ORGANISATION_ACTION_SCOPES`, `COLLECTOR_CLIENT_OPTIONAL_SCOPES`), and a person reaches it only
through `connector.admin`. Its read-back, `connector.consent.collector.read`, has the same
holders. The
connector decides where an organisation may write — see [ds-connector](../connector.md#a-collector-registers-consent).
`identity-registry.collectors.write`, which manages that relation, is in no bundle either.

Each bundle is granted at exactly one level (`PLATFORM_BUNDLES`, `ORGANISATION_BUNDLES`).

A **realm role** expands only if `REALM_ROLE_BUNDLES` lists it (`platform-admin` → `ds-admin`,
`ds-onboarding-operator` → itself). Any other role grants nothing; there is no pass-through at
this level.

An **organisation group** applies three rules, in order:

0. a **Layer B alias** translates a foreign group name into an organisation bundle name;
1. an organisation bundle expands into its capabilities;
2. a name in `ORGANISATION_PERMISSIONS` — what the organisation bundles grant, plus
   `connector.consent.holder.read` (ADR-0022) — grants itself.

Anything else grants nothing: a platform bundle, an `*.admin` superset, a machine identity
(`connector.internal`, `connector.webhook`), an unknown name.

`SERVICE_ONLY_PERMISSIONS` declares the scopes no bundle is allowed to reach, so a test can
prove there are no orphans in either direction.

**Layer B** — `parse_group_aliases` — is the only part that is deployment configuration. It
takes a JSON map of foreign organisation-group name → ds organisation bundle, and drops anything
whose value is not one. An alias can never name a raw capability or a platform bundle, and it
never applies to realm roles.

### The portal's generated twin

`services/portal/src/lib/server/bundles.generated.ts` is rendered from this same table — and
from the claim reading above, so the portal reads a token exactly as `Principal` does — by
`task auth:bundles:generate`, and a test asserts the checked-in file matches a fresh render
byte for byte. Do not hand-edit it. `libs/ds-auth/tests/parity/authority-cases.json` is one
case table both suites decide (`tests/test_two_levels.py`,
`services/portal/tests/unit/two-levels.test.ts`).

## Verifiable credentials

`verify_user_vc_jwt` returns a `UserCredential(did, subject_id, role, issuer, linked_participant)`
after checking, in order: the token and subject header are present; three JWT parts; `alg` is
`ES256`; a trust-anchor key is configured (or `insecure_dev` is explicitly opted into); the
ECDSA P-256 signature over `header.payload`; the credential subject equals the claimed subject
id; the issuer matches; the subject DID is `did:web:`; the linked participant matches; `nbf`
and `exp`; the role is one of the accepted ones; and, when a status list is configured, that
the credential is not revoked.

Everything before "signature" is a `401`; identity mismatches are `403`; an unconfigured
verifier is a `503`.

## The production guard

`DS_ENV` is the switch, read in exactly one place. **Unset, empty, or any value other than
`dev` is production.**

| `DS_ENV` | Behaviour |
|---|---|
| `dev` (any case, surrounding spaces ignored) | violations are logged as one warning; startup proceeds |
| anything else — unset, empty, `production`, `prod`, `staging`, `test`, a typo | **all** violations are collected and the service refuses to start, naming every one |

It is an allow-list of one: only the explicit value `dev` relaxes. An exact match on
`production` would let `prod`, an empty `${DS_ENV:-}` or a typo disarm every guard silently.
`is_production()` and `ProductionGuard.is_production` are the only questions to ask — never
compare `current_env()` with `"production"`.

The predicates: `forbid_default` (the value equals a declared dev default, **or** is one of
`""`, `admin`, `changeme`, `change-me`, `password`, `postgres`, `secret`, `test`),
`forbid_dev_database_url` (the **password** of a database URL is `dev` or one of those weak
values — a whole-value compare never matches a URL), `forbid_secret_equal_to_client_id`,
`require_set`, `forbid_true`, `require_https`, and `add` for a bespoke reason.

Every service registers its own dangerous defaults at startup. The reason all violations are
collected rather than raised one at a time is operational: a chart author gets the complete
list from one failed deploy instead of discovering them one rollout at a time.

## Configuration

The library reads exactly **one** environment variable — `DS_ENV`. Everything else arrives as
an `OidcConfig` the consuming service builds from its own prefixed settings.

| `OidcConfig` field | Default | Meaning |
|---|---|---|
| `issuer_url` | `None` | the realm issuer. **Non-empty ⇒ verification is enabled**, regardless of `insecure_dev` |
| `jwks_uri` | *(derived)* | `{issuer}/protocol/openid-connect/certs` |
| `audience` | `None` | the expected `aud` — each service passes its own client id |
| `allowed_audiences` | `()` | additional accepted audiences |
| `algorithms` | `("RS256", "ES256")` | accepted JWS algorithms |
| `leeway` | `30` | clock skew, seconds |
| `insecure_dev` | `False` | opt in to accepting tokens when no issuer is configured |
| `group_aliases` | `{}` | Layer B |

Three states, and the difference between them matters:

| Condition | Effect |
|---|---|
| issuer set | full verification: signature, issuer, expiry, and audience when one is configured |
| issuer unset, `insecure_dev` **false** | **fail-closed** — `AuthConfigError` → HTTP 500 |
| issuer unset, `insecure_dev` **true** | claims decoded without verification, after a warning. Signature, issuer *and expiry* are all unchecked — an expired token is accepted on this path |

Every service defaults the issuer to unset and `insecure_dev` to true, so a zero-config dev
stack runs on the third row. The production guard is what stops that reaching a real
deployment.

## Outbound calls the library makes

| Call | Target | Timeout |
|---|---|---|
| JWKS fetch | the derived or configured JWKS URI | 10 s, key set cached 1 h |
| `client_credentials` token | the token URL handed to `ServiceTokenProvider` | 10 s, cached until 30 s before expiry |
| credential-status list | the configured status URL | 5 s |

## Tasks

| Task | Effect |
|---|---|
| `task auth:test` | the library's own suite |
| `task auth:bundles:generate` | re-render the portal's bundle table and re-run the drift test |
| `task -d libs/ds-auth lint` / `format` | ruff |

`libs/ds-auth/tests/test_vocabulary.py` is the reconciliation gate between this table and
[`services/keycloak/clients.yaml`](../keycloak.md) — run it after touching either.
