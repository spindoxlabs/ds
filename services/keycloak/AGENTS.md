# services/keycloak

Config only — no code, no Dockerfile, no Taskfile. **The declaration of what the platform
needs from an OIDC realm.** Keycloak is the source of truth for authentication and for the
scope/group vocabulary `libs/ds-auth` authorizes against, so a wrong change here breaks
authorization across every service at once.

## References

| | |
|---|---|
| Requirements | [DSSC · Trust Framework](../../docs/blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) · [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/keycloak.md](../../docs/services/keycloak.md) — renders the configuration in full |

## Layout

Two hand-written declarations, two generated projections, one org file, two realm imports:

| File | |
|---|---|
| `clients.yaml` | what **ds** needs from a realm — hand-written |
| `clients.<domain>.yaml` | what the **domain backend** needs — hand-written overlay |
| `clients.effective.yaml` | GENERATED, core + overlays — what `keycloak-sync` applies |
| `clients.host.generated.yaml` | GENERATED, core only — the ds section a *host* realm must carry |
| `organizations.yaml` | KC native organizations and members |
| `realm-dataspaces-dev.json` | the dev realm import — mounted by `docker-compose.yml` only |
| `realm-production.example.json` | **an importable artifact, selected by nothing here** — see below |

Regenerate **both** projections after editing either hand-written file —
`libs/ds-auth/tests/test_vocabulary.py` and
`services/identity-registry/tests/test_keycloak_merge.py` fail on a stale copy:

```bash
task keycloak:merge     # → clients.effective.yaml
task keycloak:mirror    # → clients.host.generated.yaml
```

## The merge is mandatory, and skipping it fails silently

`celine-policies keycloak sync` takes **exactly one file**. There is no include and no
repeatable `--config`. `--prune` is opt-in and guards only orphan scopes and clients — **but
scope assignments and audience mappers are recomputed and removed unconditionally**, outside
the prune branch, for every client present in the file it was handed.

So syncing the core alone does not delete a domain scope; it **strips the grant from the ds
client that holds it**, with no flag involved. The data-plane symptom is a row filter that
resolves nobody: fewer rows, no error, no log.

A client absent from the synced file entirely *is* left alone. That asymmetry is the point:
moving a client out is safe, moving a grant off a client that stays is not.

An overlay may **add** scopes and clients and **widen** a core client's `default_scopes` /
`extra_audiences`. It may **not** redefine a core client's identity or set `realm` /
`oauth2_proxy_client` — an overlay is a backend asking for grants, not a second authority
file. A named overlay that does not exist is an error, never a thinner realm.

## `clients.yaml` — read the file

This section used to enumerate the scopes and clients and was wrong within two releases. A
permission table maintained by eye beside the file it describes is a second source of truth
that only ever disagrees. `task auth:test` reconciles it against the bundle table in both
directions; `test_vocabulary.py` fails on a scope in neither a bundle nor
`SERVICE_ONLY_PERMISSIONS`, because that is a permission no human could be granted.

What is stable enough to write down:

- **Each secret defaults to its own `client_id`** — dev convenience, overridden in production
  via `SVC_<CLIENT>_SECRET`.
- **No service client holds a `*.admin`.** Admin is an operator grant held by an interactive,
  revocable human, and it is a superset satisfying every `{service}.*` — including the
  machine-identity permissions a process must never inherit. The host mirror drops `*.admin`
  on the way across.
- **`connector.internal` and `connector.webhook` are in no bundle, ever.** They are checked
  with `require_exact_permission` because holding one means "I *am* that component".
- **`extra_audiences` is not decoration.** `ds_auth` verifies `aud`, so a token minted without
  the callee listed is rejected before its scopes are read.

## Groups name bundles, not scopes

`ds_auth.extract_groups` merges realm `groups` with `organization.<alias>.groups` — **`.groups`,
not `.roles`**. Each group names one of five bundles expanded by
`libs/ds-auth/src/ds_auth/bundles.py`; see `libs/ds-auth/AGENTS.md` for the table and the two
layers. Mapping a foreign realm's group names onto bundles is deployment config
(`<SVC>_OIDC_GROUP_ALIASES`), set on **every** service or none.

**A realm group is deployment-wide; an org group is scoped to that organisation.** Both
flatten into `extract_groups` — correct for "may this caller do X at all", useless for "to
whose data", which is why `Principal.grants_in` also exists.

### The login client needs an explicit `sub` mapper

A Keycloak **access** token carries `sub` only if the client has a mapper for it, normally
via the stock `basic` client scope. This realm has no `basic`: a realm import declaring its
own `clientScopes` replaces the stock set, and listing a scope that does not exist is
**silently ignored**. The result was a token that authenticated, authorised and identified
**nobody** — every provenance attribution of a human act recorded `""`. An ID token carries
`sub` regardless, so a browser login hides this completely; it surfaces only where the access
token is the identity, which is everywhere ds authorises. `oauth2_proxy` therefore carries an
explicit `oidc-sub-mapper`.

## Two membership systems

| System | Authority for | Source |
|---|---|---|
| KC organizations | Portal UX gating only | `organizations.yaml` |
| IR `OrganizationMembership` | Data-access decisions | identity-registry DB |

They never query each other.

## Three provisioning paths, three latencies

| | Defined in | Applied by | On a running stack |
|---|---|---|---|
| Client scopes | `clients.effective.yaml` | `keycloak-sync` | re-applied every run |
| Realm groups | `realm-*.json` | Keycloak realm import | **only at first startup** |
| Org groups | `organizations.yaml` | `ir-cli keycloak org-sync` | re-applied every run |

**If a user's token is missing a realm group you just added, this is almost always why** —
it needs a Keycloak database reset (`task docker:restart` in dev). A participant-scoped seat
via `organizations.yaml` needs no reset, which is the path to prefer.

## Common tasks

| Task | Where |
|---|---|
| Add a scope or service client | `clients.yaml`, then merge + mirror |
| Grant a service a permission | that client's `default_scopes`, then merge + mirror |
| Add a **domain** scope or client | `clients.<domain>.yaml`, then merge |
| Let service A call service B | add B's client_id to A's `extra_audiences`, then regenerate |
| Change what a seat may do | `libs/ds-auth/src/ds_auth/bundles.py`, then `task auth:bundles:generate` |
| Add a participant-scoped seat | `organizations.yaml` — live |
| Add a realm-wide seat | realm JSON `groups:` — needs a KC db reset |
| Re-provision | `task keycloak:reload` |

## The two realm files, and which is which

**`realm-dataspaces-dev.json` is not safe to deploy**: seven users whose password is their
username, `registrationAllowed: true`, `directAccessGrantsEnabled: true` on the login client
and a literal `oauth2_proxy` secret. It is mounted by `docker-compose.yml` and by nothing else.
`task secrets:check` fails if a production env file so much as names it.

**`realm-production.example.json` is an artifact to import into an existing Keycloak, not
something this repository installs.** *No chart selects it, and that is correct* — **helm does
not install Keycloak at all**, by design. Earlier notes here and in `helm/AGENTS.md` said a
production chart "must select" it; there is no such chart, and both are corrected.

Two defects in it are fixed and worth not reintroducing:

- **The `organization` claim was an `oidc-usermodel-attribute-mapper`** with
  `jsonType.label: String`, emitting a *string*. `extract_groups` needs KC's native
  object-per-alias shape, so every org-scoped seat would have resolved to nothing — a silent
  under-grant, not an error. It is now `oidc-organization-membership-mapper`, the same mapper
  the dev realm uses and the one whose output ds actually parses.
- **`organizationsEnabled` was absent**, so `ir-cli keycloak org-sync` had nothing to write
  organizations into — and the mapper above would have emitted nothing even once corrected.
  The two are one fix; either alone still yields no organization claim.
