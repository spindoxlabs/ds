# identity-registry — Agent Guide

Centralized identity service for the dataspace. Handles DID lifecycle, VC issuance, STS token signing, DCP credential queries, participant management, and StatusList2021 revocation.

Port: `30005` | Python 3.12 / FastAPI / SQLAlchemy async / PostgreSQL / EC P-256 / ES256

## Package layout

```
src/identity_registry/
  main.py              App factory, router registration, lifespan
  config.py            pydantic-settings (env prefix: IDENTITY_REGISTRY_)
  dependencies.py      FastAPI deps: get_db, require_admin_scope
  api/v1/
    public.py          GET /dids/{did}/did.json, GET /status/{list-id}
    sts.py             POST /sts/{did}/token (OAuth2 client_credentials, ES256 SI JWT)
    credentials.py     POST /credentials/{did}/presentations/query (DCP VP builder)
    admin.py           /admin/* CRUD — participants, DIDs, keys, credentials, owners, memberships, keycloak sync
    users.py           GET /users/resolve — resolve user by email; derive=true derives a subject_id when no mapping exists
    owners.py          /admin/owners CRUD, GET /owners/resolve
    memberships.py     /admin/memberships CRUD, GET /memberships/check
    organizations.py   /admin/organizations/applications, /admin/credentials/organization,
                       /admin/owners/{alias} (PATCH), /promote, /agreement (Block D)
    agreements.py      GET /agreements, /agreements/current, /agreements/{id},
                       /agreements/{id}/acceptances
  services/
    crypto.py          EC P-256 keygen, JWK, ES256 signing, JWS, email→subject_id HMAC derivation
    did.py             build_did_document (W3C DID doc)
    vc.py              MembershipCredential + DataSubjectCredential + OrganizationCredential builders, sign_credential
    org_onboarding.py  Block D: gated org lifecycle ops (verify→owner, agreement, issue, promote, suspend/revoke) — shared by API + CLI
    agreements.py      Block D: agreement YAML load + import (path + SHA-256, no inline prose)
    token.py           create_si_token — Self-Issued JWT for DCP auth
    presentation.py    build_presentation_response — VP JWT for DCP queries
    status_list.py     StatusList2021 bitstring ops (131072 slots)
    keycloak_admin.py   Keycloak admin API integration
    keycloak_merge.py   core clients.yaml + clients.<domain>.yaml → the effective file the sync applies
    keycloak_mirror.py  core clients.yaml → the ds section a *host* realm must carry (core only, no domain)
  db/
    models.py          SQLAlchemy models: Key, Did, Credential, Participant, KeycloakMapping, Owner,
                       OrganizationApplication, Agreement, AgreementAcceptance, OrganizationMembership, StatusList
    engine.py          Async engine + session factory
  schemas/
    requests.py        Pydantic request models
    responses.py       Pydantic response models
  cli/
    main.py            ir-cli (typer): bootstrap, participant, credential, key, status, owner,
                       membership, org (register/verify/agreement/issue-credential/promote/
                       apply/list/show/suspend/revoke/import), agreement (import/list) commands
```

## API tiers

- **Public** (no auth): `/dids/`, `/status/`, `/health` — must be publicly reachable for W3C did:web resolution
- **STS** (OAuth2 client_credentials): `/sts/{did}/token` — EDC connectors authenticate with STS client secret (PBKDF2-hashed, registered per participant)
- **DCP** (SI token verification): `/credentials/{did}/presentations/query` — EDC connectors authenticate with Self-Issued JWT
- **Internal** (JWT-authenticated): `/participants/`, `/users/resolve`, `/keycloak/mapping` — called by ds-connector, federated-catalog, portal (requires `identity-registry.read` or `identity-registry.resolve` scope)
- **Admin** (JWT with `identity-registry.admin` scope): `/admin/` — full CRUD for participants, DIDs, keys, credentials

## Key flows

**STS token issuance** (`POST /sts/{did}/token`): EDC connector sends OAuth2 client_credentials grant. `sts.py` validates the participant, `token.py` loads the private key from DB, signs an ES256 SI JWT with claims (iss, sub, aud, bearer_access_scope). Returns `{access_token, token_type, expires_in, scope}`.

**DCP presentation query** (`POST /credentials/{did}/presentations/query`): EDC sends a `presentationDefinition` with `input_descriptors`. `presentation.py` matches credential types, wraps matching VC JWS tokens in a VP JWT, returns a `PresentationResponseMessage`.

**Participant registration**: Creates EC P-256 key pair, DID record, participant record, issues MembershipCredential signed by trust anchor, exports key + VC to shared volume.

## Database

PostgreSQL, 11 tables: `keys`, `dids`, `credentials`, `participants`, `keycloak_mappings`, `owners`, `organization_applications`, `agreements`, `agreement_acceptances`, `organization_memberships`, `status_lists`. Alembic for migrations.

## Organisation onboarding (Block D)

Organisations are enabled through an admin API, `ir-cli org` and — since P8 — an
**invite-gated public intake**. There is still no open self-registration: an applicant
must present a single-use code the operator issued. That keeps an unauthenticated write off
the service holding every private key, while letting a third party apply without an account.
The lifecycle and its gates live in `services/org_onboarding.py`, shared by the HTTP API and
the CLI so both behave identically (the CLI is the reference implementation):

```
register (application) → verify (→ Owner row, status=verified)
  → accept agreement (records capacity + text SHA-256, no prose)
  → issue-credential  [gate: verified AND a current agreement accepted]
  → promote           [gate: a valid, unrevoked OrganizationCredential exists]
  → suspend | revoke  [StatusList bit + participant deactivation, one tx]
```

- **Registration is an upsert on `alias`** (`upsert_application`), shared by
  `POST /admin/organizations/applications`, `ir-cli org register`/`import` and `org apply` —
  an alias identifies one organisation, and inserting a row per POST left several live
  applications for it, so whichever query ran first answered differently about its state.
  201 on create, 200 on update. Verification state is never written by an intake, and editing
  a **verified** application's legal identity is a **409**: the issued credential asserts the
  old value, so that is a re-verification, not an edit. A *call* patches what it names
  (`exclude_unset`); a *file* is the full desired state. The public invite-gated intake keeps
  its **409 on a taken alias** — a stranger holding an invite must not mutate an existing org.
- **`ir-cli org apply -f owners.yaml` walks that whole chain per entry** (`apply_owner_entry`),
  so a fresh environment reaches a promoted participant with no human in a browser — it is the
  chart's bootstrap init step. It reads the deployment's existing `owners.yaml`, extended with an
  optional `dataspace:` block; an entry without one belongs to that file's other consumers and is
  **skipped**, not guessed at. Idempotent throughout: it will not re-issue a still-valid
  credential, and `verified_at`/`agreement_accepted_at` are **not re-stamped** on a re-run —
  they record when the check happened, and a bootstrap that runs on every pod start would
  otherwise walk them away from the event they attest. Every entry is attempted and **all**
  failures reported in one pass (the sync-gate/`ProductionGuard` shape), then exit non-zero.
  A half-declared entry (`dsp_address` with no `accepted:`) is refused **before** any write, so
  no half-onboarded owner is left behind. `dataspace.roles` is the *participant* role, validated
  against the same `VALID_ROLES` the admin API enforces — the `organization.role` beside it is
  the Keycloak axis, and mixing them is refused rather than seeding a participant the API would
  have rejected.

- `Owner` carries Gaia-X-shaped legal identity (`registration_number`/`registration_type` ∈
  `{local,EUID,EORI,vatID,leiCode}`, ISO 3166-2 `hq_country_code`/`legal_country_code`,
  `parent_organizations`/`sub_organizations`), a verification lifecycle (`status`,
  `verified_at`/`_by`, `evidence_ref`) and the current accepted agreement + **capacity** (§2.5).
  **`status` defaults to `pending`; `verified` must carry `verified_by`** — enforced by the
  `ck_owner_verified_has_evidence` CHECK, a `422` on `POST /admin/owners`, and `ir-cli owner
  add`/`import`. A seed states its own evidence (`owners.dev.yaml`); nothing reads verified for
  free. Any construction path that sets `verified` must set the trail too.
- `OrganizationCredential` (`vc.py`) is shape-compatible with `gx:LegalParticipant` — not full
  GXDCH compliance.
- Agreements are YAML-seeded (`seed/agreements.dev.yaml` + `seed/content/*.md`), imported by
  `ir-cli agreement import`; acceptance is proved by `text_sha256`, never inline text.
- `GET /agreements/current?participant_did=` is the **connector's circle input**
  (`services/connector/.../circle.py`): it answers what capacity a participant signed, which
  decides whether that party is a disclosed processor or an independent controller needing its
  own consent. It must **fail closed** — unknown participant, no accepted agreement, or a
  non-`verified` owner all return 404, because the caller reads "no answer" as "outside the
  circle" and asks. Returning a capacity on weak evidence suppresses a consent request that
  Art. 4(11) requires. Routed above `/agreements/{agreement_id}` so `current` is not read as an
  agreement id; `tests/test_agreements_current.py` pins that and every refusal path.
- The gates are enforced **in code** (raise `OrgOnboardingError` → 409/422), never in docs.
- Portal review queue (D.7) is **live** at `/admin/onboarding`, calling the same `/admin/*`
  endpoints as the CLI with the operator's own token — no service-account shortcut.
- **Invites** (`api/v1/onboarding.py`): `POST /admin/onboarding/invites` returns the code once
  and stores only a hash; `POST /onboarding/applications` is public and requires a valid,
  unexpired, unused one. Every refusal on the public route is **identical** — an invalid code
  and a spent code must not be distinguishable, or the route becomes an oracle for guessing.
- **Provisioning bundle**: `POST /admin/owners/{alias}/provisioning-bundle` returns everything a
  third party's ds instance needs, gated on `organizations.promote` (handing over working
  credentials for a DSP counterparty is the same class of act as creating one).
  - **Every call rotates the STS secret** and stores only `hash_sts_secret(...)`. The registry
    cannot re-show a secret, so rotation is the only honest meaning of "send it again" — and it
    is what makes a leaked bundle invalidatable. Say so in any UI before the button.
  - `format=json|env|properties|all`. `all` returns the bundle plus both renderings **in one
    rotation**, which is what a UI must use: three separate calls would hand over two bundles
    whose secret no longer works. An unknown value is a 422, never a silent fall-back to JSON.
  - `.env` carries the secret; `.properties` never does — EDC's `FsConfigurationExtension` does
    a plain `Properties.load()` and properties files get committed. `ir-cli org bundle` shares
    the same renderers in `services/provisioning.py`, so the CLI and API cannot drift.

## Common tasks

| Task | Where |
|------|-------|
| Add a new credential type | `services/vc.py` (builder) + `api/v1/admin.py` (endpoint) + `cli/main.py` (command) |
| Change DID document structure | `services/did.py` (`build_did_document`) |
| Modify SI token claims | `services/token.py` (`create_si_token`) |
| Change VP format | `services/presentation.py` (`build_presentation_response`) |
| Add a new API endpoint | `api/v1/` (pick the right tier) + register in `main.py` |
| Add a DB table | `db/models.py` + `task db:revision MESSAGE=...` |
| Change StatusList2021 behavior | `services/status_list.py` |
| Change org onboarding logic / gates | `services/org_onboarding.py` (shared by `api/v1/organizations.py` + `cli/main.py`) |
| Add/change a service agreement | `seed/agreements.dev.yaml` + `seed/content/*.md`, then `ir-cli agreement import` |

## Dev commands

```bash
task run          # uvicorn :30005 hot-reload
task debug        # debugpy :30905 + uvicorn :30005
task db:migrate   # alembic upgrade head
task test         # pytest
task lint         # ruff check
task type-check   # mypy
```

## Authorization — onboarding is not `identity-registry.admin`

`identity-registry.admin` reaches every endpoint here, including DID and key
management. An operator console that only reviews organisation applications should
not need that, so onboarding is split into grants that name what they permit:

| Grant | Reaches |
|---|---|
| `identity-registry.organizations.read` | list/get applications and owners |
| `identity-registry.organizations.write` | register, verify, issue an org credential, patch an owner, record an agreement acceptance |
| `identity-registry.organizations.promote` | promote / suspend / revoke as a participant |
| `identity-registry.agreements.read` | agreements, versions, acceptances |
| `identity-registry.participants.write` | create / update / delete a participant |
| `identity-registry.credentials.write` | issue a data-subject credential, revoke a credential |
| `identity-registry.memberships.write` | register / delete an organisation membership |
| `identity-registry.keycloak.sync` | push the `dataspace_did` attribute onto a Keycloak user |

The last three are what an **external onboarding application** actually does.
Until they existed such a service had to hold `identity-registry.admin` — the
superset over DID and key management — so a long-lived process that provisions
people could also mint or delete any identity in the dataspace. `svc-ds-onboarding`
now holds exactly `organizations.read` (resolve its bound owner at boot) plus those
three, and **no `*.admin`**, which is what `clients.yaml`'s own comment demands.

Two guards stayed on admin on purpose, and the reasoning generalises:

- `GET /admin/memberships` — *registering* a membership and *enumerating* who
  belongs to which organisation are different acts. `membership.read` answers one
  (user, org) pair at a time via `/memberships/check`; this returns the roster.
- `POST /admin/credentials/membership` — participant bootstrap, not onboarding.

`DELETE /admin/credentials/{id}` is the one deliberate over-reach: it revokes *any*
credential type, not only the data-subject ones. Revocation fails safe — it removes
an authorisation, never grants one — so the wider reach is tolerable where the same
grant over issuance would not be.

Two properties are load-bearing and `tests/test_onboarding_scopes.py` pins both:

- **`identity-registry.admin` still satisfies all of them** (the `{service}.admin`
  superset in `ds_auth.permissions`), so `ir-cli` and the bootstrap are unaffected.
- **A narrow grant reaches nothing else.** `organizations.write` cannot promote,
  cannot write participants, and cannot touch DIDs — otherwise the split is
  decoration.

`GET /agreements/current` deliberately stays on `identity-registry.read`: it is the
connector's circle check, and the connector holds that grant, not an onboarding one.

**Realm groups only apply to a fresh Keycloak.** The groups live in
`services/keycloak/realm-*.json`, which Keycloak imports at first startup — adding
one does *not* affect a running realm. In dev that means `task docker:restart`
(which recreates the Keycloak database); in production the realm is provisioned by
`celine-policies`. `clients.yaml` scopes, by contrast, are re-applied on every
`keycloak-sync` run — from `clients.effective.yaml`, which `ir-cli keycloak merge`
generates from the core file plus the deployment's domain overlays. `ir-cli keycloak
mirror` generates the *host* fragment from the core file only, so a domain backend's
vocabulary never crosses into a realm ds does not own.
