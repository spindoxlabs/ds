# ds-auth — Agent Guide

Shared JWT authentication and **unified scope/group authorization** for all Python services in the dataspaces platform. Importable package (`import ds_auth`); lives under `libs/` (no Dockerfile, no port).

## Why it exists

Two principal kinds must authorize against one permission vocabulary:

- **Service tokens** (Keycloak client-credentials) carry authority as OAuth **scopes** (`scope` claim).
- **User tokens** (OIDC login) carry authority as Keycloak **groups** (realm `groups` + org `organization.<alias>.groups`), each naming a **role bundle** that this library expands into capabilities.

`require_permission("connector.provider.write")` accepts either — the caller asks for a permission and doesn't care which token satisfied it. `{service}.admin` is a superset of `{service}.*`.

The claim semantics deliberately mirror `celine-sdk` (`extract_groups`, `is_service_account`) so a Keycloak realm synced from `clients.yaml` by the shared `celine-policies` CLI authorizes identically in both projects. **This is a mirrored approach, not a code dependency — there is no import edge to celine.** If a change here would benefit both projects, prefer upstreaming a backward-compatible feature over diverging.

## Layout

```
src/ds_auth/
├── __init__.py      Public API re-exports
├── errors.py        AuthError hierarchy (framework-free)
├── config.py        OidcConfig — issuer/jwks/audience, fail-closed dev toggle
├── jwt.py           verify_token, extract_groups, extract_scopes, is_service_account
├── permissions.py   grant_satisfies / has_permission (admin-superset rule)
├── principal.py     Principal — normalized caller (scopes vs groups → grants())
├── bundles.py       Layer A: the bundle → capabilities table, expand_bundles, parse_group_aliases
├── bundles_export.py  Generates the portal's TS mirror of that table (no-diff tested)
├── models.py        Organization — alias, type, attributes AND its groups
├── production.py    ProductionGuard — dangerous dev defaults, refused under DS_ENV=production
├── service_token.py ServiceTokenProvider — client-credentials token minting with refresh
├── user_credentials.py  verify_user_vc_jwt — the *person*-facing mechanism
└── fastapi.py       require_permission() dependency (needs the `fastapi` extra)
```

`errors.py`/`config.py`/`jwt.py`/`permissions.py`/`principal.py` are framework-free; only `fastapi.py` imports FastAPI.

### Two mechanisms, one library

| Module | Authenticates | Used by |
|---|---|---|
| `jwt.py` + `fastapi.py` | a **service or an operator**, via an OIDC token, authorized on scopes/groups | almost everything |
| `user_credentials.py` | a **person**, via an ES256 VC-JWT signed by the trust anchor, checked against StatusList2021 | ds-connector `/consent/my/*`, `/consumer/*`; ds-provenance `/prov/my/events` |

`verify_user_vc_jwt` lives here rather than in one service because **two services
verify the same credential**. A subject presents one VC to the connector to change
a sharing decision and to provenance to read their own history; if each service
carried its own copy they could drift on issuer, expiry or revocation handling —
and disagree about who someone is. It returns the subject id from the *credential*,
never from the caller's header.

## Role bundles — two layers, two owners

A human's authority used to arrive as groups named **identically to scope names**
— ~30 of them, one per endpoint family. That made ds's internal API surface
something an external realm owner had to reproduce, and those groups could only be
created by realm import (i.e. only against an empty Keycloak database). Adding an
endpoint meant a change request against somebody else's IAM.

**Layer A — bundle → capabilities.** ds's own semantics, `bundles.py`, shipped as
**code** and versioned with the enforcement it feeds. Five seats:

| Bundle | Roughly |
|---|---|
| `ds-admin` | the deployment operator |
| `ds-participant-admin` | acts for a participant: publish, sync, manage assets |
| `ds-participant-viewer` | read-only within a participant |
| `ds-onboarding-operator` | reviews organisation applications |
| `ds-member` | an authenticated human who may browse the catalogue |

Three properties are load-bearing:

- **`connector.internal` and `connector.webhook` are in no bundle**, ever. See
  "When admin must *not* apply" below.
- **`identity-registry.organizations.promote` is in `ds-admin` only** — promotion
  is the irreversible act that makes an applicant a DSP counterparty.
- **An unrecognised group passes through as its own literal capability**, so a
  realm still carrying the old scope-named groups keeps working. Migration is
  additive, not a cutover.

`ds-member` exists because four bundles left no way to say "an authenticated human
who may browse the catalogue" — which is exactly what a data subject or consumer
holds *in the group plane*. Their real authority is a **credential**, not a group.

**Layer B — foreign claim → bundle.** Deployment config, because it is about
*someone else's* naming. `parse_group_aliases` reads a JSON env var into
`OidcConfig.group_aliases`:

```
CONNECTOR_OIDC_GROUP_ALIASES='{"host-manager": "ds-participant-admin"}'
```

A value must be a **bundle name**, never a capability. An alias pointing straight
at `connector.provider.write` would make deployment configuration a permission
table, which is the thing Layer A exists to prevent — so an unknown target is
**dropped and logged**, not honoured. Dropping is the safe direction: the group
then falls through to pass-through and grants only itself, which matches nothing.

> **Wire the alias map into every service or none.** A half-wired map is a
> deployment where a caller's authority depends on which service answered.

### Per-organisation authority

`extract_groups` flattens realm groups and every `organization.<alias>.groups` into
one list — which answers "does this caller hold X *somewhere*", not "*within owner
A*". `Organization` therefore also carries its own `groups`, and
`Principal.grants_in(alias, *perms)` asks the per-organisation question.

Use `grants_in` in a perimeter whenever the resource belongs to an owner. Plain
`has_permission` plus a membership check is **not** equivalent: a caller who is a
viewer in owner A and an admin in owner B passes it for A.

### Changing the table

`bundles.py` is the source; the portal has a generated TS mirror. After any edit:

```bash
task auth:bundles:generate   # regenerate services/portal/src/lib/server/bundles.generated.ts
task auth:test               # reconciles the table against clients.yaml, both directions
```

`test_vocabulary.py` fails on a scope that is in neither a bundle nor
`SERVICE_ONLY_PERMISSIONS` — deliberately, because that is a permission no human
could ever be granted.

## Using it in a service

1. Depend on it: `pyproject.toml` → `[project].dependencies` add `"ds-auth"`, and `[tool.uv.sources]` add `ds-auth = { path = "../../libs/ds-auth", editable = true }`.
2. In the app factory, set the static config so it's available without lifespan (tests don't run lifespan):
   ```python
   from ds_auth import OidcConfig
   app.state.oidc_config = OidcConfig(
       issuer_url=settings.oidc_issuer_url,
       audience=settings.service_client_id,
       insecure_dev=settings.oidc_insecure_dev,
   )
   ```
3. Guard endpoints:
   ```python
   from ds_auth.fastapi import require_permission
   require_admin = require_permission("connector.admin")
   ...
   @router.post("/sync")
   async def sync(_p = Depends(require_permission("connector.provider.write", "connector.admin"))):
       ...
   ```
4. `Dockerfile`: `COPY libs/ds-auth/ /build/ds-auth/`, install it, and strip `ds-auth` from the copied service `pyproject.toml` before installing the rest (see `services/connector/Dockerfile`).

## When admin must *not* apply

`{service}.admin` is a superset — that is right for permissions describing
authority over a resource, and wrong for permissions describing **machine
identity**. `require_exact_permission(...)` matches by name only:

```python
require_webhook  = require_exact_permission("connector.webhook")
require_internal = require_exact_permission("connector.internal")
```

The test: *should the platform operator be able to do this with their own
token?* For "accept an EDC transfer-state callback" and "read the EDR signing
keys" the answer is no — holding those means "I am that component", and an
administrator is not. Granting them by name also makes the realm config
readable: you can see exactly which client is allowed to be the EDC.

Corollary, enforced in `services/keycloak/clients.yaml`: **no service client
carries a `*.admin` scope.** Admin belongs to an operator's own token or an
admin CLI. A long-lived process holding it acquires every permission of that
service, including the ones above.

## Perimeter narrowing

`require_permission(..., perimeter=fn)` runs `fn(principal, request) -> bool` after the permission check to bound a valid caller to the resources it may touch (its own participant/subject). Raise `PermissionDenied` or return False to deny. This turns a coarse permission into bounded authority ("user token valid, but only within its perimeter").

The connector's `_own_owner_only` is the worked example — see
`services/connector/AGENTS.md`. Two lessons from building it that generalise:

- **Ask the per-organisation question** (`grants_in`), not the membership one.
- **A guard that reads a field written elsewhere needs an end-to-end assertion
  against the real writer.** The first version read the asset owner from
  `properties["ds:owner"]`; a real EDC returns `dsp-policy:owner`, so the guard
  read *no* owner, treated every asset as unowned, and allowed every write — while
  six unit tests passed, because they asserted against a key the tests invented.

## Fail-closed verification

`verify_token` verifies signature + audience + issuer via JWKS whenever `issuer_url` is set. With no issuer it **raises `AuthConfigError`** unless `insecure_dev=True` (a loud, dev-only escape hatch). Never ship `insecure_dev=True` with a production issuer unset.

## Tests

`uv run --extra dev pytest -q` — covers permission matching, claim extraction,
signed-token verification (aud/iss/exp), fail-closed vs insecure-dev, the FastAPI
guard (service-scope allow, user-group allow, missing-group 403,
user-scope-does-not-grant, perimeter deny), bundle expansion and its
machine-identity exclusion, alias parsing and its rejection of non-bundle targets,
and `test_vocabulary.py`, which reconciles the bundle table against
`services/keycloak/clients.yaml` in both directions.

Note `test_vocabulary.py` reads the **core** `clients.yaml` only. A domain
overlay's scopes are not ds's to classify, and a deployment may carry a different
overlay or none — so a bundle may never expand to one, and that is asserted.
