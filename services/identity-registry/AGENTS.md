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
    internal.py        GET /participants, GET /participants/{did}/check, /keycloak/mapping
    sts.py             POST /sts/{did}/token (OAuth2 client_credentials, ES256 SI JWT)
    credentials.py     POST /credentials/{did}/presentations/query (DCP VP builder)
    admin.py           /admin/* CRUD — participants, DIDs, keys, credentials, keycloak sync
  services/
    crypto.py          EC P-256 keygen, JWK, ES256 signing, JWS
    did.py             build_did_document (W3C DID doc)
    vc.py              MembershipCredential + DataSubjectCredential builders, sign_credential
    token.py           create_si_token — Self-Issued JWT for DCP auth
    presentation.py    build_presentation_response — VP JWT for DCP queries
    status_list.py     StatusList2021 bitstring ops (131072 slots)
    export.py          Export keys/credentials to shared volume
  db/
    models.py          SQLAlchemy models: Key, Did, Credential, Participant, KeycloakMapping, StatusList
    engine.py          Async engine + session factory
  schemas/
    requests.py        Pydantic request models
    responses.py       Pydantic response models
  cli/
    main.py            ir-cli (typer): bootstrap, participant, credential, key, status commands
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

PostgreSQL, 6 tables: `keys`, `dids`, `credentials`, `participants`, `keycloak_mappings`, `status_lists`. Alembic for migrations.

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

## Dev commands

```bash
task run          # uvicorn :30005 hot-reload
task debug        # debugpy :30905 + uvicorn :30005
task db:migrate   # alembic upgrade head
task test         # pytest
task lint         # ruff check
task type-check   # mypy
```
