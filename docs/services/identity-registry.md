# identity-registry

The dataspace's **trust anchor**. Everything the platform believes about who someone is
comes from here.

It issues and revokes Verifiable Credentials signed by a bootstrapped trust-anchor key,
publishes the revocation list those credentials are checked against, holds the registries of
participants, owners and memberships that the connectors read, runs the organisation onboarding
lifecycle, and acts as the DCP **Secure Token Service** and **Credential Service** for the DIDs
whose keys it holds — which, in the split topology below, is only its own.

**It does not generate a participant's key.** An organisation generates its own, publishes its
own DID document, and proves control of it at enrolment; this registry records the public half.

## Two roles, one image

`IDENTITY_REGISTRY_ROLE` decides which half of the service an instance is.

| Role | Is | Serves |
|---|---|---|
| `trust-anchor` (default) | the governance authority's instance — **one per dataspace** | issuance, the participant/owner/membership registries, agreements, organisation onboarding, the StatusList, `GET /credentials/check`, and DID documents for its own DIDs |
| `participant` | **one organisation's own instance**, in its own infrastructure | only the holder surface: `/dids`, `/sts`, `/credentials/{did}/presentations/query` and `/users/{did}/credentials`, each answering **only for what this instance holds** |

The anchor is the authority on *who is in the dataspace*; a participant that disagrees with it
about that is wrong. It is not the authority on *who a participant is* — that is the
participant's own key, held by its own instance.

A `participant` mounts no registry, issuance or onboarding route at all, and this is checked
at startup rather than asserted in documentation: `services/identity-registry/src/identity_registry/roles.py` classifies
every path twice — once by which router mounts it, once by an independent path table — and the
service refuses to start if the two disagree. Adding a route without classifying it is a
startup failure, which is the point.

An unrecognised role is a refusal, never a fallback to `trust-anchor`. Each `participant`
instance needs its own database and its own `IDENTITY_REGISTRY_ENCRYPTION_KEY`; sharing either
puts every key back in one place and makes the split cosmetic.

!!! note "The anchor still *mounts* the holder routes, and answers nothing on them"
    A `trust-anchor` instance keeps `/sts` and `/credentials/{did}/presentations/query`
    mounted, because a single-instance deployment is still a valid topology. What narrows it
    is not routing but **custody**: it holds no private key but its own, so those routes
    answer for nothing else. Measured on the dev stack — the anchor serves **0** presentations
    and **0** STS tokens; the participant instances serve all of them.

    `ir-cli key custody-check` reports what an instance can actually sign as, and exits
    non-zero on a private key for a DID it does not publish.

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

**There are two registers, and the difference between them is a state.** `/status/1` is
published with `statusPurpose: revocation` and `/status/2` with `statusPurpose: suspension`.
A `MembershipCredential` or `OrganizationCredential` names both, on the one index they share;
a `DataSubjectCredential` names only the first, because a natural person's credential is
revoked or it is not. A revocation bit is terminal and is never cleared. A suspension bit is
held while the organisation does not currently qualify and is cleared when it is reinstated —
the same signed credential, valid again, never re-issued. EDC checks every `credentialStatus`
entry a credential carries and rejects it while either bit is set, reporting which, so
"suspended" and "revoked" are different answers at the verifier and not only in this database.

Both registers exist from the moment a credential names them. A suspension register created
lazily on first use would 404 for every credential issued before anyone was suspended, and a
verifier that cannot fetch a register fails closed — so those credentials would be rejected.

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
accepted agreement *and* an **enrolled DID**; promotion to participant needs an active
credential.

Alongside it sits the **provisioning bundle** — the config a third party stands its own
deployment up from. It carries the trust anchor's DID and trusted issuers, the counterparties,
the Keycloak client credentials its connector needs against *this* realm, and a **single-use
enrolment code**. It carries **no identity of ours**: the STS and credential-service URLs it
renders are on the recipient's own host, and the two secrets it needs
(`IDENTITY_REGISTRY_ENCRYPTION_KEY`, `IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET`) are named and
left empty, because the trust anchor mints neither. Generating one changes nothing about an
existing deployment; reissuing produces another code and does not revoke the first.

**Enrolment — where an organisation's own key enters.** The chain above ends with the
governance authority's judgement. What used to follow it was a *mint*: this service generated
the organisation's keypair, kept the private half and handed back an STS secret. It no longer
has to. `ir-cli org enrolment-token --alias <owner>` issues a single-use code; the
organisation generates its own keypair, publishes its own DID document, and presents that code
inside a self-issued token proving control of the key:

```
POST /issuer/credentials
Authorization: Bearer <SI token: iss = sub = its DID, aud = the anchor, pre-authorized_code>
{ "type": "CredentialRequestMessage", "holderPid": "...", "credentials": [{"id": "..."}] }
```

The anchor verifies the signature against the key in **the client's own DID document**,
resolved over did:web — never against a key it happens to hold — reads the DSP and credential
service endpoints from that same document, and records the DID with its **public** key only.

**Two independent factors, neither sufficient.** The code says which organisation; the
signature says which key. A leaked code without the key binds nothing. This is where
`DSSC-IAM-13` (proof of control) is satisfied — previously nowhere, because the issuer
generated the key and so had nothing to verify.

This is DCP's [Credential Issuance Protocol](https://eclipse-dataspace-dcp.github.io/decentralized-claims-protocol/),
not a local invention: `POST /issuer/credentials` is its Credential Request API,
`GET /issuer/metadata` its Issuer Metadata API, `GET /issuer/requests/{id}` its Credential
Request Status API, and `pre-authorized_code` is the claim the specification names for exactly
this purpose. The message bodies are checked against the protocol's own JSON schemas
(`services/identity-registry/tests/test_cip_conformance.py`), not against a reading of its prose.

**How an organisation finds this endpoint.** It is given the anchor's DID and nothing else. The
anchor's DID document publishes an `IssuerService` entry whose `serviceEndpoint` is the base
above — written by `ir-cli bootstrap`, which refreshes what it publishes on every run and never
rotates the key. That URL has to be *routed*: the anchor's Caddy site block in dev, the
`-issuer` Ingress in the chart in production. A published endpoint nothing serves is a discovery
mechanism that fails exactly like one that works, which is why the `dcp-trust` e2e flow follows
the entry to its metadata rather than asserting the entry is present.

**Identity mapping, in two halves** (`DID-11` step 2). `GET /users/resolve` — at the **anchor** —
turns a Keycloak identity into a dataspace DID: *who is this person* is registry data.
`GET /users/{did}/credentials` — at the **participant** — answers *what do they hold*, from what
was delivered to it. `POST /users/identities` turns DIDs back into the usernames the data plane
joins on.

A person's DID lives in the namespace of the organisation that onboarded them,
`did:web:<participant>:users:<id>`, and resolves on that participant's own host. **One human
keeps one identifier** however many organisations hold credentials about them — issuance is per
role, so deriving it per call would split a dual-role person's consent records and provenance in
half. Custody, unlike the identifier, follows each credential.

## How it works

### Five ways to authenticate, one service

This is the part most easily misread. The API has five tiers and they are not interchangeable.

| Tier | Credential | Routes |
|---|---|---|
| Public | none | `/dids/*`, `/status/*`, `/health`, `GET /issuer/metadata`, and the invite-gated onboarding intake |
| Issuer | a self-issued JWT proving control of the client's **own** DID, carrying a `pre-authorized_code` | `POST /issuer/credentials`, `GET /issuer/requests/{id}` |
| STS | the participant's own STS client secret, PBKDF2-verified | `POST /sts/{did}/token` |
| DCP | a self-issued JWT signed by the requested DID's registered key | `POST /credentials/{did}/presentations/query` |
| Internal | OIDC scope (`identity-registry.read`, `.resolve`, `.membership.read`, `.credentials.read`, `.organizations.read`, `.agreements.read`) | `/users/*`, `/memberships/check`, `/credentials/check`, `/owners/resolve`, `/agreements/current`, participant reads |
| Admin | OIDC scope, narrow grant preferred over `.admin` | `/admin/*` |

The admin tier is deliberately split into eight narrow permissions
(`organizations.read` / `.write` / `.promote`, `participants.write`, `credentials.write`,
`memberships.write`, `agreements.read`, `keycloak.sync`) rather than one. An onboarding
operator can verify an application and issue a credential without being able to enumerate an
organisation's roster or register a participant.

**A guard names the operation, not the tier it grew up in.** `GET /owners/resolve` and
`GET /agreements/current` are internal reads, so both accept `identity-registry.read`; both
*also* accept the narrow grant that describes what they do — `organizations.read` for the
first, `agreements.read` for the second. Until 2026-08-27 neither did, which meant a service
holding exactly the grant its realm entry named for the operation was refused it, and the
only way to admit it was to hand it the broad read as well.

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
| `IDENTITY_REGISTRY_ROLE` | `trust-anchor` | `trust-anchor` or `participant` — which routes this instance mounts. An unknown value refuses startup |
| `IDENTITY_REGISTRY_PARTICIPANT_DID` | *(none)* | **Required in the participant role.** The DID this instance holds the key for; without it the service refuses to start rather than 404 everything while reporting healthy |
| `IDENTITY_REGISTRY_PARTICIPANT_DSP_ADDRESS` | *(none)* | The DSP endpoint this participant publishes in its own DID document |
| `IDENTITY_REGISTRY_TRUST_ANCHOR_URL` | *(derived)* | The anchor's Issuer Service, used once at enrolment. Defaults to the anchor's did:web host over the `DID_WEB_USE_HTTPS` scheme |
| `IDENTITY_REGISTRY_DATABASE_URL` | Postgres on `172.17.0.1:35432/identity_registry` | **secret** — one per instance, never shared between roles |
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
| `IDENTITY_REGISTRY_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-identity-registry` | own credentials; the id is the expected JWT audience. The secret is **refused at its dev default in production** |
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
| `participant` | `init`, `add`, `list`, `remove` |
| `credential` | `issue-membership`, `issue-data-subject`, `revoke`, `list` |
| `owner` | `add`, `list`, `remove`, `import` |
| `membership` | `add`, `list`, `remove`, `import` |
| `agreement` | `import`, `list` |
| `org` | `register`, `verify`, `agreement`, `issue-credential`, `promote`, `apply`, `import`, `list`, `show`, `suspend`, `reinstate`, `revoke`, `bundle`, `enrolment-token` |
| `key` | `rotate`, `custody-check` |
| `status` | `export`, `check-indices` |
| `keycloak` | `org-sync`, `map-user` |

`ir-cli org apply` composes the whole onboarding chain from a single `owners.yaml` entry and
reports each entry's outcome, rolling back only the failures.

**A deployment's owners.yaml has no `dataspace:` block on any entry, and should not** — that
file is the deployment's own domain registry and its schema forbids ds fields, so the block
cannot be what selects the entries there. Given `--verified-by`, entries without one become
eligible, and two flags decide the rest:

| Flag | What it does |
|---|---|
| `--governance` (repeatable) | Selects the owners named by a dataset the file **exposes into the dataspace** (`dataspace.expose`), resolved through the registry's id/alias swap — so `dso` in a pipeline written elsewhere reaches `set-distribuzione` here. The onboarded set is derived from the data actually published rather than listed a second time |
| `--verified-by`, `--evidence-ref` | The run's verification evidence, applied to entries that supply none. Never to entries that do: a per-entry block's claim is left alone and reported as `verification unchanged`, because overwriting a DPA reference with a generic run string would downgrade the evidence behind an issued credential |

Without `--governance` the selector is *carrying a `did`*. Either way the chain stops after
verification — a verified owner holding its `did` and `aliases`, which is the whole of what
`GET /owners/resolve` needs. An agreement acceptance, a credential and a participant promotion
are legal and topological facts a run flag must not assert, so they stay with the per-entry
block. An alias governance names that the owners file does not declare, and a selected owner
carrying no `did`, are **errors** rather than skips, all of them reported in one pass. The `merge` and `mirror`
commands that used to sit beside it are gone, and ds generates no YAML:
`celine-policies keycloak sync` takes every file that declares the realm and merges them
itself, so a host realm mounts [`services/keycloak/clients.yaml`](keycloak.md) directly.

`ir-cli keycloak map-user` writes a Keycloak-user-to-DID mapping row and **does not contact
Keycloak** — it was called `sync`, which is also the name of a command that really does apply
a realm (`celine-policies keycloak sync`). Realm writes are `org-sync` and the promotion path.

`ir-cli status check-indices` reports credentials sharing a StatusList index and exits
non-zero when it finds any, so it can gate a deployment.

`ir-cli key custody-check` reports every private key this instance holds, classified as its
**own**, a hosted **data subject** (the declared deviation), or **foreign** — a private key for
a DID it does not publish, which means it can sign and present as that participant. It exits
non-zero on any foreign key. The same audit runs at startup: a violation is a warning in dev and
a refusal to start under `DS_ENV=production`, through the same `ProductionGuard` every other
dangerous default goes through.

`ir-cli org enrolment-token --alias <owner>` issues the code a verified organisation enrols
its own key with. The code goes to **stdout alone** so a bootstrap script can capture it;
everything a person needs is on stderr. It is printed once — only the hash is stored.

`ir-cli participant init` is the other side of it, and runs **on the participant's own
instance**: it generates that instance's keypair, encrypts the private half with its own
`IDENTITY_REGISTRY_ENCRYPTION_KEY`, publishes the DID document, and — given `--code` — enrols
with the anchor. Idempotent, and it never rotates: a bootstrap that generated a new key on
every restart would silently invalidate every credential bound to the old one. Rotation is
`ir-cli key rotate`, deliberately separate.

The anchor verifies that enrolment by **fetching the participant's DID document over did:web**,
so the participant must already be serving *and already be routed* before it enrols. An
instance that is up but not yet reachable at its `did:web` host fails with a resolution error
naming the URL it could not fetch.

## Persistence

Fourteen tables in `identity_registry`, Alembic-managed; the service and every CLI command
refuse to run against a schema that is not at head.

| Table | Holds |
|---|---|
| `keys` | key pairs — public JWK plain, private JWK as Fernet ciphertext with its own salt. **`private_jwk` is nullable**: an enrolled participant registers only its public key here |
| `dids` | DID documents: type (`participant` / `user`), service endpoints, active flag |
| `credentials` | the signed VC JSON, its status and its status-list index |
| `participants` | DSP address, roles, allowed scopes, hashed STS secret |
| `owners` | organisations: legal identity, verification evidence, accepted agreement and capacity |
| `organization_applications` | the onboarding intake, before it becomes an owner |
| `onboarding_invites` | single-use, hashed invite codes — the gate on the public application route |
| `enrolment_tokens` | single-use, hashed enrolment codes, and which DID redeemed each one |
| `credential_requests` | CIP credential-request state: `RECEIVED` / `REJECTED` / `ISSUED` |
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
| `task identity:bootstrap` | the dev seed's first half: trust anchor, owners, agreements, one enrolment code per participant |
| `task identity:users` | its second half — the dev users' credentials, **after** the participants have enrolled, because that is who they are delivered to |

Port **30005**, hardcoded — it is not a setting.
