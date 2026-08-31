# Keycloak requirements

Keycloak is **externally managed**. These charts consume it and never install it. This page is
the contract the external realm must satisfy.

The declaration itself — every scope, every client, the group vocabulary — lives in
`services/keycloak/clients.yaml` and is described on the
[keycloak service page](../services/keycloak.md). This page is what an operator has to
provision, and the two places the contract is Keycloak-specific.

!!! danger "Never import the dev realm into a production deployment"
    `services/keycloak/realm-dataspaces-dev.json` ships users whose password equals their
    username, a literal client secret, `directAccessGrantsEnabled: true` and
    `sslRequired: external`. `realm-production.example.json` is the correct reference.

## 1. Realm settings

| Setting | Required value | Why |
|---|---|---|
| `sslRequired` | `all` | dev uses `external`, which leaves internal traffic in plaintext |
| `bruteForceProtected` | `true` | credential-stuffing resistance |
| `passwordPolicy` | length, complexity, history — set something | there is no policy at all in dev |
| `eventsEnabled` | `true` | login/logout audit trail |
| `adminEventsEnabled` | `true` | realm-mutation audit trail |
| `adminEventsDetailsEnabled` | `true` | *what* changed, not only *that* it changed |
| `eventsExpiration` | ≥ your retention window | reporting deadlines need retained evidence |
| `directAccessGrantsEnabled` (per client) | `false` | dev enables the password grant on every client |

The three event flags are the only Keycloak-side audit trail available. **Ship them to the same
log sink as the application logs** — an audit trail that expires inside Keycloak's own database
is not evidence.

**Do not use email-as-username.** A person's DID derives from their email while the data plane
joins on their username, so in such a realm one address change moves both at once. See
[Identifier changes](#identifier-changes).

## 2. What ds actually asks of a realm

Five requirements. They are not equally portable, and treating them as one thing is what makes
"can ds run on our IdP?" look harder than it is.

| # | Requirement | Portable? |
|---|---|---|
| 1 | The confidential clients in `clients.yaml`, with `client_credentials`, their scopes and their audiences | Yes — any OIDC provider. Somebody must perform the **registration** |
| 2 | A login client emitting `groups`, `organization.<alias>.groups` and `email` | Yes — the group vocabulary is **five names**, not one per endpoint |
| 3 | Resolving a user to a DID (realm, user id, email) | Yes — ds resolves on demand and derives a subject id when no mapping exists |
| 4 | **Write** access to the realm | ✗ Not required. Off by default |
| 5 | Native organisations | Convenience only. The identity registry is the authority for data decisions |

### The scope vocabulary — point, do not copy

Every scope and client ds needs is declared in **`services/keycloak/clients.yaml`**, and what
a realm ds *owns* adds on top is in **`clients.dataspaces.yaml`**. Both are tool-agnostic:
apply them with the shipped syncer, by hand, or with any provisioner that can create client
scopes and confidential clients.

**To add ds to a realm you already own**, mount `clients.yaml` — the file that crosses — as
an overlay on your own declaration:

```bash
celine-policies keycloak sync your-clients.yaml --overlay /path/to/ds/services/keycloak/clients.yaml
```

There is nothing to copy and nothing to keep in step: the syncer merges the files, so ds's
declaration is read from ds. Your file adds whatever your own services need from a ds-owned
client — `client_id` plus grants, nothing else, since ds owns those clients' identity.

!!! warning "Sync every file that declares the realm, never a subset"
    A domain overlay declares what the backend deployed beside ds needs, including grants on
    clients another file declares. The syncer recomputes each client's grants from what it is
    given — so handing it a subset does not under-provision, it **removes** the missing file's
    grants from the live realm, silently and with no flag involved.

    Pass them all to one sync, with the file that does not cross as the base:

    ```bash
    celine-policies keycloak sync clients.dataspaces.yaml \
        --overlay clients.yaml --overlay clients.energy.yaml
    ```

    `clients.dataspaces.yaml` declares `requires: [ds]`, so a sync missing `clients.yaml` is
    refused before it authenticates.

### The group vocabulary — five names, not thirty

A human's authority arrives as Keycloak **groups**, never roles. Each group names a *role
bundle* that ds expands into capabilities in its own code:

```
ds-admin                 the deployment operator
ds-participant-admin     acts for a participant: publish, sync, manage assets
ds-participant-viewer    read-only within a participant
ds-onboarding-operator   reviews organisation applications
ds-member                an authenticated human who may browse the catalogue
```

This is the part an external realm owner has to reproduce, which is why it is five names and
not one per endpoint family. What each bundle may do is ds's code, versioned with the
enforcement it feeds — **adding an endpoint is a ds release, not a change request against your
realm**.

Realm-level groups carry deployment-wide seats; `organization.<alias>.groups` carries
participant-scoped ones. An unrecognised group passes through as its own literal capability, so
a realm still carrying older group names keeps working.

**If your realm cannot use these names, do not rename anything — map them.**
`global.keycloak.aliases.groups` translates your group names into bundle names, and
`.owners` translates your organisation aliases into ds owner ids. Both are deployment
configuration; a group alias may only name a *bundle*, never a raw capability, and anything else
is dropped and logged.

## 3. The two Keycloak-specific things

Everything above is ordinary OIDC. Exactly two items assume Keycloak:

1. **The `organization.<alias>.groups` claim shape**, produced by the `organization` client
   scope with an organisation-membership mapper (Keycloak 24+ native organisations). On another
   IdP, emit the same claim shape — or scope authority realm-wide and accept that per-owner
   scoping is unavailable.
2. **The syncer**, which is a Keycloak admin-API client. Nothing at runtime depends on it having
   run in a particular way.

## 4. Human login — one browser client

The portal is **not** an OIDC client. It has no client secret, no callback registration and no
session of its own; it reads the access token oauth2-proxy forwards. One login surface for the
whole deployment, and one fewer registration to negotiate.

So the realm needs **one browser-login client**, named as `oauth2_proxy_client:` in
`clients.yaml`:

- redirect URI `https://portal.<baseDomain>/oauth2/callback`;
- **post-logout redirect URI `https://portal.<baseDomain>/oauth2/sign_out`** — see below;
- it must request the scope `organization:*`, or Keycloak emits no `organization.<alias>.groups`
  and every participant-scoped seat silently grants nothing;
- naming it in `clients.yaml` is what makes the syncer attach an audience mapper per service
  client, so a user's token passes the `aud` check at each service.

!!! warning "Without the post-logout URI, signing out leaves the SSO session alive"
    Two sessions exist behind the proxy: Keycloak's SSO session and the proxy's cookie. The
    portal signs out by sending the browser to the realm's `end_session` endpoint — naming this
    client, and asking to be returned to the proxy's `/oauth2/sign_out` so the cookie is cleared
    too (`services/portal/src/lib/server/signout.ts`). Keycloak 18+ **rejects an unregistered
    `post_logout_redirect_uri` outright**, so if it is missing the chain stops at a Keycloak
    error page with the SSO session untouched, and the next visit re-authenticates silently.

    It is the **portal** host, not a separate SSO host: the chart serves `/oauth2/*` on the
    portal origin (`ds-portal`'s `_env.tpl` sets `OAUTH2_PROXY_BASE_URL` to it), so a realm
    registering `https://sso.<baseDomain>/oauth2/sign_out` instead does not match what the
    portal sends. If the client id is not `oauth2_proxy`, set `auth.proxy.clientId` on the
    `ds-portal` release to match — Keycloak validates the return URI against the client named
    in the logout request.

!!! warning "A Keycloak access token carries `sub` only if the client has a mapper for it"
    The stock route is the `basic` client scope. A realm import that declares its own
    `clientScopes` **replaces** the stock set, and listing a scope that does not exist is
    silently ignored. The token then authenticates, authorises, and identifies nobody. An ID
    token carries `sub` regardless, so a browser login hides this completely — it surfaces as
    provenance attributing acts to `""`.

## 5. Organisations (optional)

Keycloak native organisations gate the portal per owner, in parallel with identity-registry
memberships.

The org claim **is** the correct source for *operator* authority — who may act on behalf of an
organisation. It is not, and must never become, the source for *disclosure* decisions: whose
data may be shared is keyed on the data subject's DID and answered by the identity registry. The
two membership systems never query each other, deliberately.

## 6. Optional sync from the charts

```yaml
global:
  keycloak:
    sync:
      enabled: true
      clientsConfigMap: ds-keycloak-clients        # holds clients.yaml and each overlay
      organizationsConfigMap: ds-keycloak-organizations
    mutate: false   # runtime writes at participant promotion; a separate switch
```

Off by default: an externally managed Keycloak is not ours to mutate. When enabled, init
containers apply the clients and the organisations against `global.keycloak.adminUrl`. Both are
idempotent.

`sync` is boot-time provisioning. `mutate` is different: it governs whether the identity
registry may create a per-participant client at promotion time and hand over its secret.

Enabling either requires Keycloak admin credentials in `secrets.sops.yaml`. **Prefer
provisioning the realm out-of-band and leaving both off** — it keeps admin credentials out of
the application namespace entirely.

## Identifier changes

ds keys a person on three identifiers with three different jobs, and only one of them means
"the same human":

| Identifier | Role | Mutable? |
|---|---|---|
| `(realm, user_id)` | **continuity key** | no, within a realm |
| `username` | **data-plane join** — external systems resolve members by it | yes → refreshed, never an identity |
| `email` | **bootstrap seed only** | yes → never a lookup key once a mapping exists |

Two consequences for whoever runs the realm:

- **A weaker-identifier match that conflicts with a recorded stronger one is quarantined, not
  reconciled.** "The account was deleted and re-created" and "the username was recycled to a
  different person" are indistinguishable from ds's side, and guessing wrong hands one person's
  credentials and consent history to somebody else. Resolving it is an operator action.
- **A realm migration changes every user id at once**, so it quarantines the whole population by
  design. That is the right default — a migration should be deliberate — but it means the bulk
  re-key operation must be run as part of it.

## Verification

```bash
ISSUER=https://sso.example.org/realms/dataspaces

curl -sf $ISSUER/.well-known/openid-configuration | jq -r .issuer
curl -sf $ISSUER/protocol/openid-connect/certs | jq '.keys | length'

# a service client can mint a token carrying the expected scopes and audiences
curl -sf -X POST $ISSUER/protocol/openid-connect/token \
  -d grant_type=client_credentials \
  -d client_id=svc-ds-connector -d client_secret=$SECRET \
  | jq -r '.access_token' | cut -d. -f2 | base64 -d 2>/dev/null | jq '{scope, aud}'
```

If `aud` does not contain the services this client calls, its tokens are rejected at the callee.
The same question asked of the whole realm at once is a dry run of the merge — it reports what
would change without touching the realm, and refuses before authenticating if any file grants a
scope no file declares:

```bash
celine-policies keycloak sync your-clients.yaml \
  --overlay /path/to/ds/services/keycloak/clients.yaml --dry-run
```
