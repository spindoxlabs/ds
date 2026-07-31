# ds-auth

`import ds_auth`

The library that carries the platform's **authentication and authorisation decision**. Every
Python service mounts its guards; none of them re-implements the logic.

It verifies a bearer JWT against a Keycloak realm, normalises the resulting claims into one
`Principal` regardless of whether the caller is a machine or a person, expands a person's
Keycloak groups into a capability set through a role-bundle table that lives in code, and
exposes the FastAPI dependencies routes actually use.

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
| `jwt.py` + `fastapi.py` | a **service or an operator**, via an OIDC token, on scopes or groups | almost every route |
| `user_credentials.py` | a **person**, via an ES256 VC-JWT signed by the trust anchor, checked against StatusList2021 | connector `/consent/my/*` and `/consumer/*`; provenance `/prov/my/events` |

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
subject · is_service · scopes · groups · organizations · realm_groups · claims
```

The load-bearing property is `authority`, and it branches:

| Caller | Authority is |
|---|---|
| **service** | its `scope` claim, **verbatim** — a bundle name in a scope claim means nothing |
| **user** | its groups, **expanded** through the bundle table — a user's `scope` claim confers nothing at all |

`grants_in(alias, *perms)` answers the per-organisation question: it returns false if the
principal is not a member of that organisation, and otherwise expands *that organisation's*
groups plus the realm groups. A service principal carries no organisations, so `grants_in` is
always false for one — a call site that must exempt services checks `is_service` first.

### How a caller is classified

In order:

| # | Condition | Result |
|---|---|---|
| 1 | `preferred_username` starts with `service-account-` | service |
| 2 | `gty == "client-credentials"` | service |
| 3 | `email` present | user |
| 4 | groups present | user |
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
| `ds-participant-admin` | `connector.provider.read`, `.write`, `connector.history.read`, `connector.registry.invalidate`, `connector.consent.provision`, `connector.ingestion.record`, `catalog.read`, `provenance.read`, `identity-registry.read`, `.membership.read` |
| `ds-participant-viewer` | `connector.provider.read`, `connector.history.read`, `catalog.read`, `provenance.read`, `identity-registry.read` |
| `ds-onboarding-operator` | `identity-registry.organizations.read`, `.write`, `.agreements.read`, `.participants.write`, `identity-registry.read` |
| `ds-member` | `catalog.read` |

Expansion applies four rules per group, in order:

0. a **Layer B alias** translates a foreign group name into a ds bundle name;
1. a known bundle expands into its capabilities;
2. a machine-identity permission (`connector.internal`, `connector.webhook`) is **dropped** —
   a group *named* after one grants nothing;
3. anything else passes through verbatim as its own capability, so a realm carrying older group
   names keeps working.

`SERVICE_ONLY_PERMISSIONS` declares the scopes no bundle is allowed to reach, so a test can
prove there are no orphans in either direction.

**Layer B** — `parse_group_aliases` — is the only part that is deployment configuration. It
takes a JSON map of foreign group → ds bundle, and drops anything whose value is not a bundle
name. An alias can never name a raw capability.

### The portal's generated twin

`services/portal/src/lib/server/bundles.generated.ts` is rendered from this same table by
`task auth:bundles:generate`, and a test asserts the checked-in file matches a fresh render
byte for byte. Do not hand-edit it.

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

`DS_ENV` is the switch, read in exactly one place, defaulting to `dev`.

| `DS_ENV` | Behaviour |
|---|---|
| `production` | **all** violations are collected and the service refuses to start, naming every one |
| anything else | the same violations are logged as one warning; startup proceeds |

Only the literal string `production` enforces — `prod` and `staging` behave as dev.

Five predicates: `forbid_default` (the value equals a declared dev default, **or** is one of
`""`, `admin`, `changeme`, `change-me`, `password`, `postgres`, `secret`, `test`),
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
