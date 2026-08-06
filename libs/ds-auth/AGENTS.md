# ds-auth

`import ds_auth`. Carries the platform's authentication and authorization decision: verifies
a bearer JWT against a Keycloak realm, normalizes the claims into one `Principal` whether the
caller is a service or a human, expands a human's groups into capabilities, and exposes the
FastAPI dependencies every Python service mounts. It also carries the outbound service-token
provider, the VC verifier for subject-facing routes, and the boot-time `ProductionGuard`.

`errors.py` / `config.py` / `jwt.py` / `permissions.py` / `principal.py` are framework-free.
The **package** is not: `user_credentials.py` raises `HTTPException` from 24 call sites and
imports FastAPI at module level, so `fastapi` and `httpx` are core dependencies rather than
extras (`AUTH-03`). `tests/test_declared_dependencies.py` fails on any module-level import
that is not declared — the check that would have caught `ServiceTokenProvider` being
unimportable from a plain install.

## References

| | |
|---|---|
| Requirements | [DSSC · Trust Framework](../../docs/blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) · [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/libs/ds-auth.md](../../docs/services/libs/ds-auth.md) |

## Two mechanisms, one library

| Module | Authenticates | Used by |
|---|---|---|
| `jwt.py` + `fastapi.py` | a **service or an operator**, via an OIDC token, on scopes/groups | almost everything |
| `user_credentials.py` | a **person**, via an ES256 VC-JWT signed by the trust anchor, checked against StatusList2021 | connector `/consent/my/*`, `/consumer/*`; provenance `/prov/my/events` |

`verify_user_vc_jwt` lives here rather than in one service because **two services verify the
same credential**. Separate copies would drift on issuer, expiry or revocation and disagree
about who someone is. It returns the subject id from the *credential*, never from a header.

`require_permission("connector.provider.write")` accepts either principal kind — the caller
asks for a permission and does not care which token satisfied it. `{service}.admin` is a
superset of `{service}.*`.

The claim semantics deliberately mirror `celine-sdk` so a realm synced by `celine-policies`
authorizes identically in both projects. **A mirrored approach, not a code dependency** —
there is no import edge. Prefer upstreaming a backward-compatible feature over diverging.

## Role bundles — two layers, two owners

**Layer A — bundle → capabilities**, `bundles.py`. ds's own semantics, shipped as **code**
and versioned with the enforcement it feeds. Five seats: `ds-admin`,
`ds-participant-admin`, `ds-participant-viewer`, `ds-onboarding-operator`, `ds-member`.

Three properties are load-bearing:

- **`connector.internal` and `connector.webhook` are in no bundle**, and `connector.admin`
  inside `ds-admin` cannot reach them either — `has_exact_permission` ignores the superset.
- **`identity-registry.organizations.promote` is in `ds-admin` only** — promotion is the
  irreversible act that makes an applicant a DSP counterparty.
- **An unrecognised group passes through as its own literal capability**, so a realm still
  carrying the old scope-named groups keeps working. Migration is additive, not a cutover.
  The one exception is a machine-identity permission, dropped however the group is named.

**Layer B — foreign claim → bundle**, deployment config, because it is about *someone else's*
naming: `<SVC>_OIDC_GROUP_ALIASES`, a JSON map. A value must be a **bundle name, never a
capability** — an alias pointing at `connector.provider.write` would make deployment config a
permission table, which is what Layer A exists to prevent. An unknown target is dropped and
logged; dropping is the safe direction.

> **Wire the alias map into every service or none.** A half-wired map is a deployment where a
> caller's authority depends on which service answered.

### Per-organisation authority

`extract_groups` flattens realm groups and every `organization.<alias>.groups` — which answers
"does this caller hold X *somewhere*", not "*within owner A*". Use
`Principal.grants_in(alias, *perms)` in any perimeter where the resource belongs to an owner.
**Plain `has_permission` plus a membership check is not equivalent**: a caller who is a viewer
in owner A and an admin in owner B passes it for A.

### Changing the table

```bash
task auth:bundles:generate   # regenerate the portal's TS mirror — never edit it by hand
task auth:test               # reconciles the table against clients.yaml, both directions
```

`test_vocabulary.py` fails on a scope in neither a bundle nor `SERVICE_ONLY_PERMISSIONS`,
because that is a permission no human could be granted. It reads the **core** `clients.yaml`
only — a domain overlay's scopes are not ds's to classify.

## When admin must *not* apply

`{service}.admin` is right for permissions describing authority over a resource and wrong for
permissions describing **machine identity**. `require_exact_permission(...)` matches by name
only. The test: *should the platform operator be able to do this with their own token?* For
"accept an EDC transfer callback" and "read the EDR signing keys" the answer is no — holding
those means "I am that component". Granting them by name also makes the realm readable: you
can see which client is allowed to be the EDC.

Corollary, enforced in `services/keycloak/clients.yaml`: **no service client carries a
`*.admin` scope.**

## Perimeter narrowing

`require_permission(..., perimeter=fn)` runs `fn(principal, request) -> bool` after the
permission check, turning a coarse permission into bounded authority. The connector's
`_own_owner_only` is the worked example; two lessons from it generalise — ask the
per-organisation question, and **a guard that reads a field written elsewhere needs an
end-to-end assertion against the real writer.**

## Fail-closed verification

`verify_token` verifies signature + audience + issuer via JWKS whenever `issuer_url` is set.
With no issuer it **raises** unless `insecure_dev=True`, a loud dev-only escape hatch. Never
ship `insecure_dev=True` with the production issuer unset.

**When you add a setting with a dev default anywhere in the platform, register it with
`ProductionGuard` in the same change** — an unregistered insecure default is invisible to the
Helm chart.

`task -d libs/ds-auth test`.

## Two traps in `jwt.py` and `production.py`

**Do not teach `is_service_account` that a bare `scope` claim means a service.** Keycloak puts
`scope` on user tokens too (`openid profile email`), so that change classifies every human as
a machine and authorizes them on OIDC scopes instead of group membership. The defect ledger
carried a row asking for exactly it; the argument is written out in the function's docstring
and in `services/federated-catalog/tests/test_auth.py`, and the real cause was test helpers
minting tokens Keycloak cannot issue. A token with **no** indicator either way is read as a
user and logged, so the 403 that follows is diagnosable.

**A guard method is a rule only once a service registers a setting with it.** `require_https`
was written, unit-tested and called by nobody for as long as it existed. `test_production.py`
now asserts that every service with an issuer URL registers it — add the assertion when you
add the method, or the method is documentation.
