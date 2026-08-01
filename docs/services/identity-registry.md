# identity-registry

The dataspace's **trust anchor**. Everything the platform believes about who someone is
comes from here.

It generates and stores participant key pairs, serves their `did:web` documents, issues and
revokes Verifiable Credentials signed by a bootstrapped trust-anchor key, publishes the
revocation list those credentials are checked against, holds the registries of participants,
owners and memberships that the connectors read, runs the organisation onboarding lifecycle
end to end, and acts as the DCP **Secure Token Service** and **Credential Service** for every
participant whose key it holds.

One instance per dataspace, not one per participant. It is the authority; a participant that
disagrees with it is wrong.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Identity & Attestation Management](../blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) · [DSSC · Trust Framework](../blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) |
| Rules it enforces | [Rulebook · Participation and trust](../rulebook/participation.md) |

DSSC splits identity into *attestation* (who says what about whom) and *trust* (why anyone
should believe it). This service is both: the issuer of attestations and the anchor of the
trust chain.

## What it does

**DID lifecycle.** Generates EC P-256 key pairs, encrypts every private JWK at rest with a
Fernet key derived from `IDENTITY_REGISTRY_ENCRYPTION_KEY` and a per-row salt, and serves
`GET /dids/{did}/did.json` publicly so any `did:web` resolver can verify a signature.

**Credentials.** Issues three types, all signed by the trust anchor:

| Credential | Says |
|---|---|
| `MembershipCredential` | this participant belongs to the dataspace, with these scopes |
| `DataSubjectCredential` | this person is a data subject (or a consumer user) linked to this participant |
| `OrganizationCredential` | this organisation is verified and has accepted an agreement |

Revocation is a StatusList2021 bitstring published at `GET /status/{list_id}` — public by
necessity, because a verifier that cannot fetch it cannot tell a live credential from a
revoked one.

**The bitstring records revocations and allocates nothing.** A credential's index comes from
the `status_lists.next_index` counter, taken under a row lock; a bit is set only when
something is revoked, and an index is never reused. Reading the register for its first unset
bit — which is what this service did before schema 0011 — cannot work: leaving the bit clear
never advances it, so consecutive credentials collide and revoking one revokes them all;
setting it to make it advance publishes the credential revoked from birth. Both were true at
once, at different call sites. `ir-cli status check-indices` reports credentials still
carrying colliding indices; because the index sits inside the signed credential, they can
only be repaired by re-issuance (see
[Operations](../deployment/operations.md#upgrading-past-identity-registry-schema-0011-credentials-may-need-re-issuing)).

**DCP endpoints.** `POST /sts/{did}/token` mints a self-issued token for a participant that
proves the STS client secret; `POST /credentials/{did}/presentations/query` answers a
presentation query with a signed VP. These replaced what used to be per-participant `ds-sts`
and `ds-vc-wallet` processes — the EDC connectors point at this service for both.

**Registries.** Participants (DID, DSP address, allowed scopes, roles), owners (organisations
with their legal identity), memberships (which person acts for which organisation), and
service agreements with their acceptances. The connector and the federated catalogue read
these; the connector's cache is invalidated by a push from here on change.

**Organisation onboarding.** A five-gate chain, identical whether it runs over HTTP or
through the CLI:

```
application → verified owner → agreement acceptance → organization credential → participant
```

Each gate refuses to run before its predecessor: a credential needs a verified owner *and* an
accepted agreement *and* a DID; promotion to participant needs an active credential. The last
step optionally produces a **provisioning bundle** — the config a third party needs to stand
up their own connector — and rotates the STS secret every time it is generated, storing only
a hash. It cannot re-show a secret, which is exactly what makes a leaked bundle invalidatable.

**Identity mapping.** `GET /users/resolve` turns a Keycloak identity into a dataspace DID and
its credentials; `POST /users/identities` turns DIDs back into the usernames the data plane
joins on.

## How it works

### Five ways to authenticate, one service

This is the part most easily misread. The API has five tiers and they are not interchangeable.

| Tier | Credential | Routes |
|---|---|---|
| Public | none | `/dids/*`, `/status/*`, `/health`, and the invite-gated onboarding intake |
| STS | the participant's own STS client secret, PBKDF2-verified | `POST /sts/{did}/token` |
| DCP | a self-issued JWT signed by the requested DID's registered key | `POST /credentials/{did}/presentations/query` |
| Internal | OIDC scope (`identity-registry.read`, `.resolve`, `.membership.read`, `.credentials.read`) | `/users/*`, `/memberships/check`, `/credentials/check`, `/owners/resolve`, participant reads |
| Admin | OIDC scope, narrow grant preferred over `.admin` | `/admin/*` |

The admin tier is deliberately split into eight narrow permissions
(`organizations.read` / `.write` / `.promote`, `participants.write`, `credentials.write`,
`memberships.write`, `agreements.read`, `keycloak.sync`) rather than one. An onboarding
operator can verify an application and issue a credential without being able to enumerate an
organisation's roster or register a participant.

**Enumerating and checking are different disclosures.** `/admin/memberships` and
`/admin/credentials` list what a person has and stay on `.admin`; `/memberships/check` and
`/credentials/check` answer one (subject, thing) question and are reachable with a narrow
read. A service that decides admission needs the second and must never be given the first —
`clients.yaml` refuses `*.admin` to a service client, and these two endpoints are what make
that possible to honour.

`GET /credentials/check` also decides **validity** — active, and unexpired — rather than
returning state for the caller to interpret. The connector used to read the roster and judge
for itself, against a `revoked` field the response has never carried; every entry therefore
read as valid. Deciding it where the state lives is what stops that shape recurring.

### A DCP presentation query, traced

1. The EDC posts `client_credentials` with `client_id = <its own DID>` and the STS secret to
   `POST /sts/{did}/token`. A `client_id` that is not the path DID is `401`.
2. The participant row is loaded and must be active. A participant with **no** stored secret
   is rejected — an empty secret means "cannot authenticate", never "no check required".
3. The secret is verified with PBKDF2-HMAC-SHA256, 600 000 iterations, constant-time compare.
4. The registry decrypts that participant's private key and signs an ES256 token valid for
   300 seconds, with `iss = sub = did`.
5. The holder presents that token to `POST /credentials/{did}/presentations/query`. It is
   verified against the DID's *registered active key*: `alg` must be ES256, `iss` must equal
   `sub` and the path DID, `exp` must be present and current.
6. The response is a signed VP holding every active credential for that subject, filtered by
   the types the presentation definition asked for.

Every verification failure produces the same undifferentiated `401`.

### Identifier changes

A person is keyed on three identifiers with three different jobs, and only one means "the
same human":

| Identifier | Role | Mutable? |
|---|---|---|
| `(realm, user_id)` | **continuity key** | no, within a realm |
| `username` | **data-plane join** — external systems resolve members by it | yes, refreshed |
| `email` | **bootstrap seed only** | yes, never a lookup key once mapped |

A weaker-identifier match that conflicts with a recorded stronger one is **quarantined, not
reconciled**. "The account was deleted and re-created" and "the username was recycled to a
different person" look identical from here, and guessing wrong hands one person's consent
history to somebody else.

## Configuration

`pydantic-settings`, prefix `IDENTITY_REGISTRY_`. Fields carrying a `validation_alias` — every
`KEYCLOAK_*` name below — are read under that literal name, **without** the prefix, and the
prefixed form does not work.

| Variable | Default | Meaning |
|---|---|---|
| `IDENTITY_REGISTRY_DATABASE_URL` | Postgres on `172.17.0.1:35432/identity_registry` | **secret** |
| `IDENTITY_REGISTRY_ENCRYPTION_KEY` | `dev-encryption-key-change-in-production` | **secret** — encrypts every DID private key at rest, and derives subject ids. Losing it makes stored keys unrecoverable |
| `IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN` | `trust-anchor.dataspaces.localhost` | the trust anchor's DID domain and status-list host |
| `IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL` | *(derived from the domain)* | externally reachable URL written into provisioning bundles. The doubled prefix is correct — the field is `identity_registry_public_url` |
| `IDENTITY_REGISTRY_DEFAULT_CREDENTIAL_TTL_DAYS` | `365` | issued-credential lifetime |
| `IDENTITY_REGISTRY_MAX_CREDENTIAL_TTL_DAYS` | `730` | cap on a requested lifetime |
| `IDENTITY_REGISTRY_CREDENTIALS_CONTEXT_URL` | `https://dataspaces.localhost/ns/credentials/v1` | JSON-LD context in issued VCs |
| `IDENTITY_REGISTRY_DATASPACE_URI` | `https://dataspaces.localhost/dataspace` | the `memberOf` value in issued VCs |

### Authorisation

| Variable | Default | Meaning |
|---|---|---|
| `IDENTITY_REGISTRY_OIDC_ISSUER_URL` | — | Keycloak realm issuer. Set ⇒ JWTs fully verified |
| `IDENTITY_REGISTRY_OIDC_INSECURE_DEV` | `true` | accept unverified JWTs when no issuer. **Refused in production** |
| `IDENTITY_REGISTRY_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-identity-registry` | own credentials; the id is the expected JWT audience |
| `IDENTITY_REGISTRY_OIDC_GROUP_ALIASES` | `""` | JSON map: foreign group → ds role bundle |

### Keycloak (no prefix)

| Variable | Default | Meaning |
|---|---|---|
| `KEYCLOAK_ISSUER_URL` | — | realm issuer handed to a third party in its provisioning bundle |
| `KEYCLOAK_REALM` | `dataspaces` | |
| `KEYCLOAK_ADMIN_URL` | — | admin API base, used only when creating a participant's client |
| `KEYCLOAK_ADMIN_USERNAME` / `KEYCLOAK_ADMIN_PASSWORD` | — | **secret**; needed only when `KEYCLOAK_MUTATE` is on |
| `KEYCLOAK_MUTATE` | `true` | may this registry create clients in the realm at promotion time |

### Outbound notification

| Variable | Default | Meaning |
|---|---|---|
| `IDENTITY_REGISTRY_CONNECTOR_URLS` | `""` | comma-separated connectors to notify when the registry changes. Empty disables |
| `IDENTITY_REGISTRY_KEYCLOAK_TOKEN_URL` | — | token endpoint for those calls. Unset disables |

## `ir-cli`

The service ships a Typer CLI that is the reference implementation of the onboarding gates —
the HTTP API and the CLI call the same service layer, so they cannot drift. Every
database-touching command verifies the schema revision first, and every command is idempotent.

| Group | Commands |
|---|---|
| *(top level)* | `bootstrap` — create the trust-anchor key pair and DID |
| `participant` | `add`, `list`, `remove` |
| `credential` | `issue-membership`, `issue-data-subject`, `revoke`, `list` |
| `owner` | `add`, `list`, `remove`, `import` |
| `membership` | `add`, `list`, `remove`, `import` |
| `agreement` | `import`, `list` |
| `org` | `register`, `verify`, `agreement`, `issue-credential`, `promote`, `apply`, `import`, `list`, `show`, `suspend`, `revoke`, `bundle` |
| `key` | `rotate` |
| `status` | `export` |
| `keycloak` | `org-sync`, `merge`, `mirror`, `sync` |

`ir-cli org apply` composes the whole onboarding chain from a single `owners.yaml` entry and
reports each entry's outcome, rolling back only the failures. `ir-cli keycloak merge` and
`mirror` do not touch the database at all — they generate the two projections of
[`services/keycloak/clients.yaml`](keycloak.md).

## Persistence

Twelve tables in `identity_registry`, Alembic-managed; the service and every CLI command
refuse to run against a schema that is not at head.

| Table | Holds |
|---|---|
| `keys` | key pairs — public JWK plain, private JWK as Fernet ciphertext with its own salt |
| `dids` | DID documents: type (`participant` / `user`), service endpoints, active flag |
| `credentials` | the signed VC JSON, its status and its status-list index |
| `participants` | DSP address, roles, allowed scopes, hashed STS secret |
| `owners` | organisations: legal identity, verification evidence, accepted agreement and capacity |
| `organization_applications` | the onboarding intake, before it becomes an owner |
| `onboarding_invites` | single-use, hashed invite codes |
| `agreements` / `agreement_acceptances` | agreement versions (path + SHA-256 of the text, never the prose) and who accepted which |
| `organization_memberships` | person → organisation, with a role |
| `keycloak_mappings` | `(realm, user_id)` → DID, plus username and email |
| `status_lists` | the revocation bitstring |

## Running it

| Task | Effect |
|---|---|
| `task identity-registry:run` | uvicorn on `:30005` with reload |
| `task identity-registry:debug` | same under debugpy on `:30905` |
| `task db:migrate:identity-registry` | `alembic upgrade head` |
| `task keycloak:merge` / `keycloak:mirror` | regenerate the two client projections |
| `task identity:bootstrap` | run the dev seed (trust anchor, participants, credentials, owners) |

Port **30005**, hardcoded — it is not a setting.
