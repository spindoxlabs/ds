# identity-registry

The dataspace **trust anchor**. Owns the DID lifecycle, issues and revokes credentials,
acts as STS and DCP Credential Service for every participant, and holds the participant,
owner and membership registries plus the organisation onboarding lifecycle.

Port 30005 (debug 30905). PostgreSQL, 14 tables. EC P-256 / ES256.

**Everything in the platform's trust story depends on this service.** A wrong edit here is
not a bug in one feature — it is a participant who cannot be revoked.

## References

| | |
|---|---|
| Requirements | [DSSC · Identity & Attestation Management](../../docs/blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) · [DSSC · Trust Framework](../../docs/blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) |
| Rules | [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/identity-registry.md](../../docs/services/identity-registry.md) |

## Two roles — classify a new route before you write it

`IDENTITY_REGISTRY_ROLE=trust-anchor|participant`. Same image; the role decides which routers
are mounted. `src/identity_registry/roles.py` is the source of truth and explains the design.

**A new route must be classified in `roles.py`, in the same change.** Both halves —
`ROUTERS` (which router, which roles) and `PATH_ROLES` (which path, which roles) — and the
service **refuses to start** if they disagree or if a mounted path is unclassified. That is
deliberate: it is the one check that fails because of something a change did not do.

Ask one question: *is this registry data or holder data?* Registry data (who is in the
dataspace, what was issued, what was agreed) is the anchor's. Holder data (a DID document, an
STS token, a presentation) belongs to whoever holds the key.

Router order in `ROUTERS` is mount order and is load-bearing twice: `credentials.check` before
`credentials.presentations` (`/check` versus `{did:path}`), and `dids` last of all — its
`/{did_path}/did.json` matches everything.

## API tiers — pick the right one for a new route

| Tier | Auth | Examples |
|---|---|---|
| Public | none | `/dids/`, `/status/`, `/health`, `GET /issuer/metadata` — must be reachable for `did:web` and revocation checking |
| Issuer | self-issued JWT proving control of the **client's own** DID + a `pre-authorized_code` | `POST /issuer/credentials` |
| STS | participant's STS client secret (PBKDF2-hashed) | `POST /sts/{did}/token` |
| DCP | self-issued JWT signed by the requested DID's registered key | `POST /credentials/{did}/presentations/query` |
| Internal | JWT scope (`identity-registry.read` / `.resolve`) | `/participants`, `/users/resolve`, `/memberships/check`, `/owners/resolve` |
| Admin | JWT scope, **narrow grant preferred over `.admin`** | `/admin/*` |

## Authorization — onboarding is not `identity-registry.admin`

`identity-registry.admin` reaches every endpoint here, **including DID and key management**.
An operator console that reviews organisation applications must not need that, so onboarding
is split into grants naming what they permit: `organizations.{read,write,promote}`,
`agreements.read`, `participants.write`, `credentials.write`, `memberships.write`,
`keycloak.sync`.

Two properties are load-bearing and `tests/test_onboarding_scopes.py` pins both: `.admin`
still satisfies all of them (so `ir-cli` and the bootstrap are unaffected), and **a narrow
grant reaches nothing else** — otherwise the split is decoration.

Two guards stayed on `.admin` deliberately, and the reasoning generalises: `GET /admin/memberships`
returns the *roster* while `memberships/check` answers one pair at a time, and
`POST /admin/credentials/membership` is participant bootstrap, not onboarding.
`DELETE /admin/credentials/{id}` is the one accepted over-reach — revocation removes an
authorisation and never grants one.

## Organisation onboarding

```
register (application) → verify (→ Owner, status=verified)
  → accept agreement (records capacity + text SHA-256, never prose)
  → enrolment-token   [gate: verified. The organisation enrols its own key]
  → issue-credential  [gate: verified AND a current agreement accepted]
  → promote           [gate: a valid, unrevoked OrganizationCredential]
  → suspend | revoke  [StatusList bit + participant deactivation, one tx]
```

**Enrolment is where a key enters, and it is not this service's key to make.**
`services/enrolment.py` + `api/v1/issuer.py` implement DCP's Credential Issuance Protocol:
the organisation generates its own keypair, publishes its own DID document, and presents a
single-use `pre-authorized_code` inside a self-issued token proving control of that key. The
anchor stores the **public** key only — `keys.private_jwk` is nullable and NULL is the correct
value for anyone but this instance itself.

Rules that are easy to break here:

- **Never verify a client against a key this registry holds.** `verify_client_identity`
  resolves through did:web every time, with no local shortcut. A shortcut passes in dev — where
  both parties live in one database — and fails in production, where the enrolling party is a
  stranger. That is the same shape as the defect `P-8a` exists to prevent.
- **Endpoints come from the resolved DID document, never from the request body.** Two sources
  for one fact means a client can claim what it does not publish.
- **Every refusal on `/issuer/*` answers alike.** Distinguishing "spent" from "unknown"
  enumerates codes; distinguishing "not verified" discloses an application's state. The
  operator's log carries the real reason — `EnrolmentError` carries both.

The gates live in **`services/org_onboarding.py`, shared by the HTTP API and the CLI**, so
both behave identically — the CLI is the reference implementation. Gates raise
`OrgOnboardingError` → 409/422; they are never enforced in documentation.

Rules that are easy to break:

- **Registration is an upsert on `alias`.** One alias is one organisation; a row per POST
  left several live applications answering differently about its state. Editing a *verified*
  application's legal identity is a **409** — the issued credential asserts the old value,
  so that is re-verification, not an edit.
- **`ir-cli org apply -f owners.yaml` walks the whole chain per entry**, idempotently, and
  is the chart's bootstrap step. It does not re-stamp `verified_at` / `agreement_accepted_at`
  on a re-run — those record when a check happened, and a bootstrap running on every pod
  start would walk them away from the event they attest. Every entry is attempted and **all**
  failures reported in one pass, then exit non-zero.
- **The public intake is invite-gated, and every refusal on it is identical.** An invalid
  code and a spent code must not be distinguishable, or the route is a guessing oracle.
- **`GET /agreements/current` must fail closed.** It is the connector's circle input: an
  unknown participant, no accepted agreement, or a non-verified owner all return 404, because
  the caller reads "no answer" as "outside the circle" and asks. Returning a capacity on weak
  evidence suppresses a consent request Art. 4(11) requires.
- **The provisioning bundle hands over no identity** (`DID-10`). It used to carry an STS secret
  this registry minted, with the STS and credential-service URLs pointing at the *anchor* — so
  the artefact an operator sent a third party configured that third party to use somebody
  else's registry as its own. It now carries trust material, the counterparties and a
  **single-use enrolment code**; the two secrets the recipient needs are *named* in the
  rendered config and left empty, because they are the recipient's to choose.
  **Nothing rotates**, so reissuing is safe for a running deployment — and is *not* revocation.
  Still use `format=all`: each call issues a new code, and the recipient needs one.

## Where to work

| Task | Where |
|---|---|
| New credential type | `services/vc.py` + `api/v1/admin.py` + `cli/main.py` |
| DID document shape | `services/did.py` |
| SI token claims / VP format | `services/token.py`, `services/presentation.py` |
| StatusList behaviour | `services/status_list.py` — allocate with `allocate_status_list_index`, revoke with `revoke_status_list_index`. **Never derive an index from the bitstring**; see below |
| Onboarding logic or a gate | `services/org_onboarding.py` — never in one caller only |
| Service agreement | `seed/agreements.dev.yaml` + `seed/content/*.md`, then `ir-cli agreement import` |
| Keycloak realm interaction | `services/keycloak_{admin,merge,mirror}.py` |
| DB table | `db/models.py` + `task db:revision MESSAGE=...` |
| Enrolment / CIP | `services/enrolment.py` + `api/v1/issuer.py` — never one without the other |

`task -d services/identity-registry run|debug|test|lint|type-check|db:migrate`.

**`test:integration` is a second suite** and needs a real Postgres on `172.17.0.1:35432`
(`IDENTITY_REGISTRY_TEST_PG` overrides it; CI does). Not collected by `test`. It starts a
**trust anchor and two participants** as three processes on three databases and runs the real
enrolment handshake — `org enrolment-token` on the anchor, `participant init --code` on the
participant, which generates its own key and sends only a signature. If you change enrolment,
`api/v1/issuer.py`, the STS or did:web publication, run it: those paths have no other live
coverage. It was red and unnoticed for one release because nothing invoked it (`T-2a`), so it
is in `integration.yml` now — keep it there.

## The StatusList register is not an allocator

`status_lists.bitstring` answers "is credential *n* revoked". `status_lists.next_index`
answers "what is the next index". Conflating them is the defect this service shipped: the
first unset bit does not move unless issuance sets it, so four call sites collided on one
index (revoking any one revoked all of them) and two set it and published credentials revoked
from birth. Both at once, which is why it looked intermittent.

Allocation goes through `allocate_status_list_index` (counter, row-locked, never reuses);
`revoke_status_list_index` is the only thing that may set a bit. The index is inside the
**signed** credential, so a collision is not repairable in place — `ir-cli status
check-indices` reports them and re-issuance is the only fix.

## Realm groups vs client scopes

**Realm groups only apply to a fresh Keycloak** — they live in `services/keycloak/realm-*.json`,
imported at first startup only. In dev that means `task docker:restart`. `clients.yaml`
scopes are re-applied on every `keycloak-sync`. See `services/keycloak/AGENTS.md`.
