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
    users.py           GET /users/resolve — resolve user by email
    owners.py          /admin/owners CRUD, GET /owners/resolve
    memberships.py     /admin/memberships CRUD, GET /memberships/check
    organizations.py   /admin/organizations/applications, /admin/credentials/organization,
                       /admin/owners/{alias} (PATCH), /promote, /agreement (Block D)
    agreements.py      GET /agreements, /agreements/current, /agreements/{id},
                       /agreements/{id}/acceptances
  services/
    crypto.py          EC P-256 keygen, JWK, ES256 signing, JWS
    did.py             build_did_document (W3C DID doc)
    vc.py              MembershipCredential + DataSubjectCredential + OrganizationCredential builders, sign_credential
    org_onboarding.py  Block D: gated org lifecycle ops (verify→owner, agreement, issue, promote, suspend/revoke) — shared by API + CLI
    agreements.py      Block D: agreement YAML load + import (path + SHA-256, no inline prose)
    token.py           create_si_token — Self-Issued JWT for DCP auth
    presentation.py    build_presentation_response — VP JWT for DCP queries
    status_list.py     StatusList2021 bitstring ops (131072 slots)
    keycloak_admin.py   Keycloak admin API integration
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
                       list/show/suspend/revoke/import), agreement (import/list) commands
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

Organisations are enabled through an admin API + `ir-cli org`, following the seed-and-import
pattern — **no public self-registration** this iteration. The lifecycle and its gates live in
`services/org_onboarding.py`, shared by the HTTP API and the CLI so both behave identically
(the CLI is the reference implementation):

```
register (application) → verify (→ Owner row, status=verified)
  → accept agreement (records capacity + text SHA-256, no prose)
  → issue-credential  [gate: verified AND a current agreement accepted]
  → promote           [gate: a valid, unrevoked OrganizationCredential exists]
  → suspend | revoke  [StatusList bit + participant deactivation, one tx]
```

- `Owner` carries Gaia-X-shaped legal identity (`registration_number`/`registration_type` ∈
  `{local,EUID,EORI,vatID,leiCode}`, ISO 3166-2 `hq_country_code`/`legal_country_code`,
  `parent_organizations`/`sub_organizations`), a verification lifecycle (`status`,
  `verified_at`/`_by`, `evidence_ref`) and the current accepted agreement + **capacity** (§2.5).
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
- Portal review queue (D.7) is deferred; it will call the same `/admin/*` endpoints as the CLI.

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
