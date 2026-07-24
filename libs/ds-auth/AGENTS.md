# ds-auth — Agent Guide

Shared JWT authentication and **unified scope/group authorization** for all Python services in the dataspaces platform. Importable package (`import ds_auth`); lives under `libs/` (no Dockerfile, no port).

## Why it exists

Two principal kinds must authorize against one permission vocabulary:

- **Service tokens** (Keycloak client-credentials) carry authority as OAuth **scopes** (`scope` claim).
- **User tokens** (OIDC login) carry authority as Keycloak **groups** (realm `groups` + org `organization.<alias>.groups`).

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
└── fastapi.py       require_permission() dependency (needs the `fastapi` extra)
```

`errors.py`/`config.py`/`jwt.py`/`permissions.py`/`principal.py` are framework-free; only `fastapi.py` imports FastAPI.

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

## Fail-closed verification

`verify_token` verifies signature + audience + issuer via JWKS whenever `issuer_url` is set. With no issuer it **raises `AuthConfigError`** unless `insecure_dev=True` (a loud, dev-only escape hatch). Never ship `insecure_dev=True` with a production issuer unset.

## Tests

`uv run --extra dev pytest -q` — covers permission matching, claim extraction, signed-token verification (aud/iss/exp), fail-closed vs insecure-dev, and the FastAPI guard (service-scope allow, user-group allow, missing-group 403, user-scope-does-not-grant, perimeter deny).
