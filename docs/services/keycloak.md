# keycloak

`services/keycloak/` holds no code. It is the **declaration of what the platform needs from an
OIDC realm**: a permission vocabulary, the service clients that hold those permissions, the
organisations, and two realm imports.

Keycloak itself is externally managed in any real deployment. These files are the contract it
must satisfy, and they are tool-agnostic — apply them with the shipped syncer, by hand, or
with any provisioner that can create client scopes and confidential clients.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Trust Framework](../blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) · [DSSC · Identity & Attestation Management](../blueprints/dssc/data-sovereignty-and-trust/identity-and-attestation-management.md) |
| Rules it enforces | [Rulebook · Participation and trust](../rulebook/participation.md) |

Keycloak answers *who is calling*. The dataspace's own trust anchor — the
[identity registry](identity-registry.md) — answers *who is a participant* and *whose data is
this*. The two membership systems never query each other, deliberately.

## The files

| File | |
|---|---|
| `clients.yaml` | what **ds** needs from *any* realm, including one it does not own — hand-written. This is the file that crosses |
| `clients.dataspaces.yaml` | what a realm **ds owns** adds: the realm's identity, the e2e harness, the admin supersets, `dataset.*`. The base file in dev |
| `clients.<domain>.yaml` | what a **domain backend** deployed beside ds needs — hand-written overlay |
| `organizations.yaml` | Keycloak native organisations, their members, per-organisation group assignments, and each organisation's participant context (which gives it an [organisation client](#organisation-clients)) |
| `realm-dataspaces-dev.json` | the dev realm import — users, groups, the login client |

Every file here is hand-written. **ds generates no YAML**: where ds is a guest, the host realm
mounts `clients.yaml` itself as an overlay, so what crosses is a file boundary rather than a
rendered copy that has to be kept current.

!!! warning "Sync every file that declares the realm, never a subset"
    The syncer **recomputes** every client's grants from what it is given. Handing it fewer
    files does not under-provision — it *removes* whatever the missing file granted, silently,
    with no flag involved.

    `celine-policies keycloak sync` takes a base file and a repeatable `--overlay`, and merges
    them before applying anything:

    ```bash
    # posture A — ds owns the realm (dev)
    celine-policies keycloak sync clients.dataspaces.yaml \
        --overlay clients.yaml --overlay clients.energy.yaml

    # posture B — ds is a guest; the host's file is the base
    celine-policies keycloak sync <host clients.yaml> --overlay <ds clients.yaml>
    ```

    `clients.dataspaces.yaml` declares `requires: [ds]`, so forgetting `clients.yaml` is a
    refusal before anything is authenticated. Nothing can guard the base file itself, which is
    why the base is the file that does not cross.

## The two vocabularies

### Scopes — what a machine may do

Roughly thirty permission names in `clients.yaml`, grouped by service prefix:

| Prefix | Covers |
|---|---|
| `identity-registry.*` | admin, read, resolve, membership.read, organizations.{read,write,promote}, agreements.read, participants.write, credentials.write, memberships.write, keycloak.sync |
| `connector.*` | admin, provider.{read,write}, history.read, registry.invalidate, internal, webhook, consent.{provision,read}, ingestion.record, disclosure.record |
| `provenance.*` | read, write |
| `catalog.*` | read |
| `dataset.*` | admin, query, read, write |
| `management-api:*` | EDC's grammar, not ds's: `assets`, `policies`, `contractdefinitions`, `negotiations`, `transfers` at `write`; `catalog`, `agreements` at `read`. Granted to [organisation clients](#organisation-clients) only |

A grant is checked by name, with one rule: **`{service}.admin` satisfies any `{service}.*`** —
except where a route asks for a permission *exactly*. Two permissions are treated that way,
`connector.internal` and `connector.webhook`, precisely so a platform admin token cannot open
the machine-to-machine surface.

### Groups — what a human may do

A human's authority arrives as Keycloak **groups**, never roles, and the vocabulary is
**five names**, not one per endpoint:

| Group | Is |
|---|---|
| `ds-admin` | the deployment operator |
| `ds-participant-admin` | acts for a participant: publish, sync, manage assets — not register consent, which an organisation's own client does |
| `ds-participant-viewer` | read-only within a participant |
| `ds-onboarding-operator` | reviews organisation applications |
| `ds-member` | an authenticated human who may browse the catalogue |

Each names a **role bundle** that ds expands into capabilities in its own code
([`libs/ds-auth`](libs/ds-auth.md)). That is the point of five names: adding an endpoint is a
ds release, not a change request against somebody else's realm. An unrecognised group passes
through as its own literal capability, so a realm still carrying older group names keeps
working.

Realm-level groups carry deployment-wide seats; `organization.<alias>.groups` carries
participant-scoped ones. If a realm cannot use these names, **map them** rather than renaming
anything: `*_OIDC_GROUP_ALIASES` translates foreign group names into bundle names, and may
only ever name a *bundle*, never a raw capability.

## The clients

| Client | Authenticated by | Holds |
|---|---|---|
| `svc-ds-connector` | **nothing** — the audience every connector verifies on incoming tokens | — |
| `svc-ds-identity-registry` | the registry, notifying connectors of a change | `identity-registry.admin`, `connector.registry.invalidate` |
| `svc-ds-federated-catalog` | the crawler | `identity-registry.read` |
| `svc-ds-dataset-api` | the data-plane PEP | `connector.internal` |
| `svc-edc` | the EDC's ds extensions | `identity-registry.read`, `connector.internal`, `connector.webhook` |
| `svc-ds-portal` | the portal, for one call only | read/resolve grants across the platform |
| `svc-ds-e2e` | the e2e harness | a broad set, for probing — but **not** `connector.provider.write`, so a flow that publishes has to use an identity that may |
| `svc-ds-publisher` | whatever drives `POST /provider/sync`: a bring-up script, a CI job, the chart's sync hook | `connector.provider.read`, `connector.provider.write` — and deliberately no `management-api:*` and no `connector.admin`, so it reaches the connector and never an EDC |
| `svc-ds-provenance` | **nothing** — it exists as an audience only | — |
| `svc-ds-onboarding` | an application outside this repository | narrow onboarding grants |
| `oauth2_proxy` | the browser login flow | *(declared in the realm import, not by the syncer)* |
| `svc-ds-connector-<alias>` | an organisation's connector — **for every call it makes** — and its batch jobs | `identity-registry.read`, `.membership.read`, `.credentials.read`, `provenance.write`, `connector.consent.read`, `connector.provider.read`/`.write` (it publishes **its own** catalogue — ADR-0017), plus the `management-api:*` scopes; `sub` = the organisation's participant context. *(created by identity-registry, not by the syncer)* |

`extra_audiences` on each client is what makes a token pass the callee's `aud` check: every
Python service verifies `aud` against its own client id.

## The browser login client

The portal is not an OIDC client, so the realm needs **one** browser-login client, named as
`oauth2_proxy_client:` in `clients.yaml`. Three things it must have:

- redirect URI `…/oauth2/callback` on the public host;
- the scope `organization:*`, or Keycloak emits no `organization.<alias>.groups` and every
  participant-scoped seat silently grants nothing;
- naming it in `clients.yaml` is what makes the syncer attach an audience mapper per service
  client.

!!! warning "A Keycloak access token carries `sub` only if a mapper puts it there"
    The stock route is the `basic` client scope. A realm import that declares its own
    `clientScopes` **replaces** the stock set, and listing one that does not exist is silently
    ignored. The token then authenticates, authorises, and identifies nobody — an ID token
    carries `sub` regardless, so a browser login hides this completely. It surfaces as
    provenance attributing acts to `""`.

## What a production realm must satisfy

The dev realm must never be imported into production: it ships users whose password equals
their username, a literal client secret, `directAccessGrantsEnabled: true`, and
`sslRequired: external`.

| Setting | Required | Why |
|---|---|---|
| `sslRequired` | `all` | dev's `external` leaves internal traffic in plaintext |
| `bruteForceProtected` | `true` | credential-stuffing resistance |
| `passwordPolicy` | set something | there is none in dev |
| `eventsEnabled`, `adminEventsEnabled`, `adminEventsDetailsEnabled` | `true` | the only Keycloak-side audit trail there is |
| `eventsExpiration` | ≥ your retention window | an audit trail that expires inside Keycloak's own database is not evidence |
| `directAccessGrantsEnabled` (per client) | `false` | dev enables the password grant on every client |

**Do not use email-as-username.** A person's DID derives from their email while the data plane
joins on their username; in such a realm one address change moves both at once.

## Only two things here are Keycloak-specific

Everything else is ordinary OIDC.

1. **The `organization.<alias>.groups` claim shape**, produced by Keycloak 24+ native
   organisations. On another IdP, emit the same claim shape, or scope authority realm-wide and
   accept that per-owner scoping is unavailable.
2. **The syncer**, which is a Keycloak admin-API client. Nothing at runtime depends on it
   having run in any particular way.

## Organisation clients

EDC 0.18.0's v5 management API authenticates an OAuth2 token and reads two claims: `sub`, the
participant context the caller acts for, and `scope`, in EDC's grammar
(`management-api[:resource]:read|write|admin`). ds gives each organisation **one** confidential
client for it, `svc-ds-connector-<alias>`:

| | |
|---|---|
| grants | `ds_auth.ORGANISATION_CLIENT_SCOPES`: the connector's service grants (`CONNECTOR_SERVICE_SCOPES`) plus `MANAGEMENT_API_SCOPES` — never `management-api:admin`, never a `*` resource |
| `sub` | a hardcoded-claim mapper (`participant-context-sub`) set to the organisation's participant context, which ds sets to its DID. Keycloak's own `sub` is the service account's UUID |
| audiences | `ds_auth.CONNECTOR_AUDIENCES`: `svc-ds-identity-registry`, `svc-ds-provenance`, `svc-ds-connector` (a counterparty connector) |
| created by | `ir-cli keycloak org-sync`, for each entry of `organizations.yaml` with a `participant_context_id`; and the provisioning bundle, for a promoted third party |
| secret | `SVC_DS_CONNECTOR_<ALIAS>_SECRET`; the client id in dev, required under `DS_ENV=production`. Applied only when the client is created |

**One credential per connector, and one client per organisation** (the maintainer,
2026-09-17). The connector authenticates as this client to its EDC and to every ds service
(`CONNECTOR_CLIENT_ID` / `CONNECTOR_CLIENT_SECRET`). The organisation's batch jobs use the same
client to call the connector's `/consumer/*` routes, where the token must name the connector's
own context and hold the EDC scope of the call (see
[connector](connector.md#who-may-drive-the-consumer-side)). `svc-ds-connector` remains only as
the audience.

The realm syncer declares the `management-api:*` scopes (`clients.yaml`) and grants them to no
client: it cannot add the `sub` mapper, and it recomputes the grants of every client it is
handed, so the organisation clients are deliberately absent from every file it reads.

!!! danger "`celine-policies keycloak sync --prune` deletes the organisation clients"
    The sync lists every `svc-ds-connector-<alias>` as an orphan client, and `--prune` deletes
    orphans. Every organisation's connector and batch jobs then lose their credential, and a
    re-created client gets a new secret. ds never passes `--prune`. A deployment that does must
    re-run `ir-cli keycloak org-sync` immediately afterwards and redistribute the secrets.

!!! warning "EDC does not check `aud`"
    Any token of the realm whose `sub` names a participant context and whose `scope` matches is
    accepted by that participant's management API. Who holds a `management-api:*` scope is
    therefore the boundary, together with **where the management port can be reached**: a
    batch job holding its organisation's token could administer that organisation's contracts
    directly on any network that reaches the port. Compose publishes no EDC management port,
    and the chart keeps it ClusterIP-only
    ([ADR-0014](../decisions/ADR-0014-management-api-v5-and-the-organisation-actor.md)).
    `libs/ds-auth/tests/test_management_api_scopes.py` asserts no declared client holds a
    `management-api:*` scope; `tests/integration/test_organisation_clients.py` asserts it of a
    provisioned realm.

## Organisations

Keycloak native organisations gate the portal per owner, in parallel with identity-registry
memberships. The org claim **is** the correct source for *operator* authority — who may act on
behalf of an organisation. It is not, and must never become, the source for *disclosure*
decisions: whose data may be shared is keyed on the data subject's DID and answered by the
identity registry.

## Configuration and tasks

| Task | Effect |
|---|---|
| `task keycloak:reload` | discard and re-import the dev realm, then re-run both syncs |

`libs/ds-auth/tests/test_vocabulary.py` is the gate on editing either ds file, and it asserts
four things — every scope ds declares is reachable through a bundle or explicitly declared
service-only, no bundle invents a scope, no bundle reaches a *domain overlay's* vocabulary,
and what crosses is what should: no `*.admin` grant and no `svc-ds-e2e` in `clients.yaml`,
every other client present. "ds declares" means `clients.yaml` and `clients.dataspaces.yaml`
together: both are ds's, split by which realm applies them, not by whose vocabulary they are.

Client secrets are supplied as `${SVC_…_SECRET:-<client-id>}`, so the dev fallback for each is
its own client id.

## Bringing a dev realm up

`task infra:start` runs three containers in order:

1. **`keycloak`** — `start-dev --import-realm`, importing the dev realm: roles, client scopes,
   the `oauth2_proxy` client, the groups and the dev users. Under `start-dev` realm state
   lives in the container filesystem, so removing the container resets it.
2. **`keycloak-sync`** — applies all three declarations, passed as
   `sync /app/clients.dataspaces.yaml --overlay /app/clients.yaml --overlay
   /app/clients.energy.yaml`: creates the client scopes and the service clients, and attaches
   the audience mappers.
3. **`keycloak-org-sync`** — applies `organizations.yaml`: creates each organisation, adds its
   members and puts them into the named per-organisation groups, and ensures each
   [organisation client](#organisation-clients). Idempotent; a member the realm does not know is
   reported and skipped, and a client that cannot be provisioned fails the step.

## Dev users

All passwords equal the username. Realm `dataspaces`. The portal is at
<http://portal.dataspaces.localhost>; [Signing in](../development/running-the-stack.md#signing-in)
covers which seat to reach for.

`Authority` below is a *permission* statement, not a list of screens. A seat's Keycloak groups
and its verifiable credentials are two independent axes, and neither substitutes for the other:
`ds-member` plus a credential is what makes a data subject, which is why an operator seat —
`ds-admin` included — cannot open a consent screen.

| User | Authority | Exercises |
|---|---|---|
| `admin@example.test` | `ds-admin` | platform administration |
| `provider@example.test` | `ds-participant-admin`, realm **and** org-scoped | both provisioning paths |
| `consumer@example.test` | `ds-member` + a `ConsumerUser` credential | data consumption |
| `subject@example.test` | `ds-member` + a `DataSubject` credential | consent management |
| `dual@example.test` | both credential roles | that roles are additive, not exclusive |
| `gridops@example.test` | `ds-participant-admin` **org-scoped only** | that a cross-owner write is refused |
| `onboarding@example.test` | `ds-onboarding-operator`, realm-scoped | reviewing organisation applications without holding admin |
| `viewer@example.test` | `ds-participant-viewer` **org-scoped only** | that a read-only seat cannot write |
| `legacy@example.test` | `legacy-provider-admin` — **not a bundle**; `ds-participant-admin` only where an alias map translates it | that a foreign IdP's group name is translated, and that the translation is bounded |

Every bundle the realm declares as a group is held by one of these, and
`libs/ds-auth/tests/test_vocabulary.py` fails if that stops being true. A bundle
with no holder is a seat nobody sits in: it is expanded, unit-tested and never
exercised against a running realm, and nothing fails to say so.

`legacy@example.test` is the one seat that is not about the bundle table. Its group is
deliberately foreign-looking, is not ds vocabulary, and expands to nothing on its own — it
carries authority only where a deployment's [Layer B](libs/ds-auth.md#the-role-bundle-table)
alias map translates it, which dev sets on the connector and the identity registry (`*_OIDC_GROUP_ALIASES` in `.env.local`)
and deliberately nowhere else. That makes it an assertion about the wiring rather than about
the vocabulary, and `ds-e2e --flow user-authority` pairs it with its bound: the translated seat
must still be refused what `ds-participant-admin` does not contain, because a translation that
granted more than the bundle would be a permission table living in deployment config.
