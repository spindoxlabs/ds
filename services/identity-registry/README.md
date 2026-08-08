# ds-identity-registry

Centralized identity service for the dataspace. Manages participant identities, DID lifecycle, Verifiable Credentials, key material, and token issuance. Provides STS and DCP Credential Service endpoints consumed by EDC connectors.

Port: `30005`

DSSC alignment: BB02 (Identity & Attestation) — participant identity management, DID resolution, VC lifecycle, trust anchor bootstrapping.

> **Concepts live in the docs site, not here.** This README is the local entry
> point: what runs, which endpoints exist, how to configure and start it. The
> reasoning is published at **<https://spindoxlabs.github.io/ds/>** — start with [this service's page](https://spindoxlabs.github.io/ds/services/identity-registry/) and
> [Participation and trust](https://spindoxlabs.github.io/ds/rulebook/participation/).
> Working on the code? Read `AGENTS.md` in this directory first.

---

## Technology

Python 3.12 / FastAPI / SQLAlchemy 2 (async) / PostgreSQL / Alembic / `cryptography` / `pyjwt` / EC P-256 / ES256

---

## What it does

| Capability | Description |
|------------|-------------|
| DID lifecycle | Generates EC P-256 key pairs, creates `did:web` DIDs, serves DID documents at `GET /dids/{did}/did.json` |
| VC issuance | Issues `MembershipCredential` and `DataSubjectCredential` VCs, signed by the trust anchor |
| STS | OAuth2 `client_credentials` grant at `POST /sts/{did}/token` — signs ES256 Self-Issued JWTs for DCP authentication |
| Credential Service (DCP) | `POST /credentials/{did}/presentations/query` — builds Verifiable Presentations for DCP negotiation |
| Participant registry | Manages participants with roles, scopes, DSP addresses |
| StatusList2021 | W3C StatusList2021 revocation at `GET /status/{list-id}` |
| Key management | Key rotation, key deactivation. Private keys never leave the service. |

---

## Database

11 tables:

- `keys` — EC P-256 key pairs (JSONB for private_jwk/public_jwk), owner_did, kid, active flag, rotation tracking
- `dids` — DID records with type (participant/user), service_endpoints (JSONB), FK to keys
- `credentials` — VCs (JSONB credential_json), type, issuer/subject DIDs, status (active/suspended/revoked), StatusList2021 index
- `participants` — participant registry with DID (FK), role, allowed_scopes (JSONB), dsp_address, sts_client_secret
- `keycloak_mappings` — DID-to-Keycloak user mappings (realm, user_id, email, subject_id)
- `owners` — owner registry + Gaia-X legal identity, verification lifecycle, current agreement + capacity (Block D)
- `organization_applications` — pre-verification org registration data, promoted into `owners` on verify (Block D)
- `agreements` — service-agreement definitions (id + version, capacity, per-locale text path + SHA-256) (Block D)
- `agreement_acceptances` — an org's acceptance of an agreement version (capacity, locale, text SHA-256) (Block D)
- `organization_memberships` — user-DID → owner-alias memberships
- `status_lists` — StatusList2021 bitstrings (LargeBinary), purpose: `1` is `revocation` (terminal), `2` is `suspension` (cleared on reinstatement)

---

## REST API — 3 trust tiers

### Public (no auth) — must be reachable for W3C did:web resolution

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/dids/{did}/did.json` | Resolve DID document (`application/did+ld+json`) |
| `GET` | `/status/{list-id}` | StatusList2021 credential (`application/ld+json`) |
| `GET` | `/health` | Liveness check |
| `POST` | `/onboarding/applications` | Apply to join, **requires a valid invite code**. Not open self-registration — an unauthenticated write on the service holding every private key would be. Every refusal is identical, so the route is not an oracle |

### DCP protocol — authenticated per-endpoint (called by EDC connectors)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/sts/{did}/token` | STS client secret (participant-specific) | Issue Self-Issued JWT (OAuth2 client_credentials, ES256) |
| `POST` | `/credentials/{did}/presentations/query` | DCP self-issued token signed by the DID's key | Build VP for DCP presentation query |

### Service-to-service — JWT with `identity-registry.read` or `.admin` scope

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/admin/participants` | List all active participants |
| `GET` | `/admin/participants/check?did=&scope=` | Check if participant is allowed for scope |

### Admin (JWT with `identity-registry.admin` scope)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/admin/participants` | Register participant (auto-creates DID + key + exports) |
| `GET` | `/admin/participants` | List all participants |
| `GET` | `/admin/participants/{did}` | Get participant detail with credentials |
| `PATCH` | `/admin/participants/{did}` | Update participant |
| `DELETE` | `/admin/participants/{did}` | Deactivate participant + revoke credentials |
| `POST` | `/admin/dids` | Create DID with auto-generated key |
| `GET` | `/admin/dids/{did}` | Get DID details |
| `DELETE` | `/admin/dids/{did}` | Deactivate DID + revoke credentials |
| `POST` | `/admin/credentials/membership` | Issue MembershipCredential |
| `POST` | `/admin/credentials/data-subject` | Issue DataSubjectCredential |
| `POST` | `/admin/credentials/organization` | Issue OrganizationCredential (gate: verified + agreement) |
| `POST` | `/admin/organizations/applications` | Register an organisation application |
| `GET` | `/admin/organizations/applications` | List applications (`?status=&alias=`) |
| `GET`/`PATCH` | `/admin/organizations/applications/{id}` | Get / update (verify) an application |
| `PATCH` | `/admin/owners/{alias}` | Promote / update owner legal identity + lifecycle |
| `POST` | `/admin/owners/{alias}/agreement` | Record agreement acceptance |
| `POST` | `/admin/owners/{alias}/promote` | Promote a credentialled owner to a participant |
| `POST` | `/admin/owners/{alias}/provisioning-bundle` | Everything a third party needs to stand up its own instance. `?format=json\|env\|properties\|all`. **Every call rotates the STS secret** — the registry stores a hash and cannot re-show one, so "send it again" can only mean "issue a new one". Gated on `organizations.promote` |
| `POST`/`GET` | `/admin/onboarding/invites` | Issue / list single-use invitation codes. The code is returned once; only a hash is stored |
| `GET` | `/admin/credentials/{id}` | Get credential JSON |
| `GET` | `/admin/credentials` | List credentials (optional `?subject_did=`) |
| `DELETE` | `/admin/credentials/{id}` | Revoke credential |
| `POST` | `/admin/keycloak/sync` | Sync DID-to-Keycloak mapping |
| `POST` | `/admin/keys/rotate/{did}` | Rotate key for DID |
| `GET` | `/keycloak/mapping/{did}` | Get KC mapping by DID |
| `GET` | `/keycloak/mapping?subject_id=` | Get KC mapping by subject ID |

---

## CLI (ir-cli)

Entry point: `ir-cli = "identity_registry.cli.main:run"`

| Command | Purpose |
|---------|---------|
| `ir-cli bootstrap` | Create trust-anchor DID + key (idempotent) |
| `ir-cli participant add` | Register participant with auto MembershipCredential |
| `ir-cli participant list` | List all participants |
| `ir-cli participant remove` | Deactivate a participant |
| `ir-cli credential issue-membership` | Issue MembershipCredential |
| `ir-cli credential issue-data-subject` | Issue DataSubjectCredential |
| `ir-cli credential revoke` | Revoke a credential |
| `ir-cli credential list` | List all credentials |
| `ir-cli key rotate` | Rotate key for a DID |
| `ir-cli status export` | Export StatusList2021 as JSON |
| `ir-cli org register/verify/agreement/issue-credential/promote` | Organisation onboarding lifecycle (Block D) |
| `ir-cli org apply --file owners.yaml` | Walk that whole lifecycle per `owners.yaml` entry carrying a `dataspace:` block — idempotent, reports every failure in one pass, `--dry-run` available |
| `ir-cli org list/show/suspend/reinstate/revoke/import` | Manage organisations |
| `ir-cli agreement import/list` | Import + list service-agreement definitions |
| `ir-cli org bundle --alias --format` | Render a connection bundle (same renderers as the HTTP endpoint, so the two cannot drift) |

---

## Internals

The module-by-module walkthrough that used to sit here is in `AGENTS.md`, beside
the source it describes — it is a map for someone editing the code, not something
an operator or integrator needs. The security model (trust tiers, key management,
credential lifecycle, network posture) is published at
[Identity registry](https://spindoxlabs.github.io/ds/services/identity-registry/), with the
rules it enforces in [Participation and trust](https://spindoxlabs.github.io/ds/rulebook/participation/).

---

## Configuration

Env prefix: `IDENTITY_REGISTRY_`

| Variable | Default | Purpose |
|----------|---------|---------|
| `IDENTITY_REGISTRY_DATABASE_URL` | `postgresql+asyncpg://...172.17.0.1:35432/...` | PostgreSQL connection string |
| `IDENTITY_REGISTRY_ENCRYPTION_KEY` | `dev-encryption-key-...` | Fernet key for encrypting private keys at rest |
| `IDENTITY_REGISTRY_OIDC_ISSUER_URL` | `None` | OIDC issuer for JWT verification (admin endpoints) |
| `IDENTITY_REGISTRY_ADMIN_SCOPE` | `identity-registry.admin` | Required JWT scope for admin endpoints |
| `KEYCLOAK_ADMIN_URL` | `None` | Keycloak admin API base URL |
| `KEYCLOAK_CLIENT_ID` | `ds-identity-registry` | Keycloak service account client ID |
| `KEYCLOAK_CLIENT_SECRET` | `insecure-dev-secret` | Keycloak service account secret |
| `IDENTITY_REGISTRY_DEFAULT_CREDENTIAL_TTL_DAYS` | `365` | Default credential validity |
| `IDENTITY_REGISTRY_MAX_CREDENTIAL_TTL_DAYS` | `730` | Maximum credential validity |
| `IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN` | `trust-anchor.dataspaces.localhost` | Domain for the trust-anchor DID |
| `IDENTITY_REGISTRY_CREDENTIALS_CONTEXT_URL` | `https://dataspaces.localhost/ns/credentials/v1` | Credentials JSON-LD context URL |
| `IDENTITY_REGISTRY_DATASPACE_URI` | `https://dataspaces.localhost/dataspace` | Dataspace membership URI |
| `IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL` | `https://<trust_anchor_domain>` | Externally reachable base URL written into provisioning bundles. An in-cluster DNS name here produces a connector that cannot resolve its own trust anchor |
| `KEYCLOAK_ISSUER_URL` | `None` | Realm issuer handed to a third party's connector in its bundle |
| `KEYCLOAK_REALM` | `dataspaces` | Realm the third party's client is created in |
| `KEYCLOAK_ADMIN_USERNAME` / `_PASSWORD` | `None` | Realm admin, used **only** to provision a third party's connector client at bundle time. Unset, the bundle is still issued — without Keycloak credentials in it |

---

## Development

```bash
cd services/identity-registry
task setup                # uv sync
task db:migrate           # alembic upgrade head
task run                  # uvicorn on :30005 with hot-reload
task debug                # debugpy on :30905 + uvicorn on :30005

# Tests and linters run through uv rather than a task:
uv run pytest
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
```

---

## Docker

Two-stage Dockerfile (builder + runtime). Port 30005, non-root `app` user. Healthcheck via `/health`.

```bash
docker compose -f services/identity-registry/docker-compose.yml up -d
```
