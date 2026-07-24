# Keycloak requirements

Keycloak is **externally managed**. These charts consume it and never install it.
This document is the contract the external realm must satisfy.

The dev realm (`services/keycloak/realm-dataspaces-dev.json`) must never be
imported into a production deployment: it ships four users whose password equals
their username, a literal client secret, `directAccessGrantsEnabled: true` and
`sslRequired: external`. `services/keycloak/realm-production.example.json` is the
correct reference.

## 1. Realm settings

| Setting | Required value | Why |
|---------|---------------|-----|
| `sslRequired` | `all` | dev uses `external`, which leaves internal traffic in plaintext |
| `bruteForceProtected` | `true` | credential-stuffing resistance |
| `passwordPolicy` | length, complexity, history — set something | no policy at all in dev |
| `eventsEnabled` | `true` | login/logout audit trail |
| `adminEventsEnabled` | `true` | realm mutation audit trail |
| `adminEventsDetailsEnabled` | `true` | *what* changed, not only *that* it changed |
| `eventsExpiration` | ≥ your retention window | Art. 23 reporting deadlines need retained evidence |
| `directAccessGrantsEnabled` (per client) | `false` | dev enables the password grant on every client |

The three event flags are the only Keycloak-side audit trail available. Ship them
to the same log sink as the application logs — an audit trail that expires inside
Keycloak's own database is not evidence.

## 2. Scopes

Every scope in `services/keycloak/clients.yaml` must exist in the realm. They are
the vocabulary `ds_auth.require_permission` authorizes against, for both
principal kinds:

- **service tokens** (client credentials) authorize on the `scope` claim
- **user tokens** (OIDC login) authorize on Keycloak **groups** — realm-level
  `groups` plus org-level `organization.<alias>.groups`
- `{service}.admin` satisfies any `{service}.*`

```
dataset.admin  dataset.query  dataset.read  dataset.write
identity-registry.admin  identity-registry.read  identity-registry.resolve
identity-registry.membership.read
connector.admin  connector.provider.read  connector.provider.write
connector.history.read  connector.internal  connector.webhook
connector.consent.provision  connector.ingestion.record
provenance.read  provenance.write
catalog.read
```

**Group names must mirror scope names**, or user tokens authorize against a
vocabulary that does not exist and every user request fails closed.

## 3. Service clients

Seven confidential clients, defined in `services/keycloak/clients.yaml`. In dev
each secret defaults to its own `client_id` — guessable, and three of these hold
admin-level authority:

| Client | Notable scopes | Blast radius if the secret leaks |
|--------|---------------|----------------------------------|
| `svc-ds-portal` | `connector.admin`, `identity-registry.read` | full provider management |
| `svc-ds-onboarding` | `identity-registry.admin`, `connector.consent.provision`, `provenance.write` | register arbitrary participants, provision subject consent, record disclosures |
| `svc-ds-identity-registry` | `identity-registry.admin` | full registry control |
| `svc-ds-connector` | `identity-registry.read`, `provenance.write` | forge provenance |
| `svc-ds-federated-catalog` | `identity-registry.read` | participant enumeration |
| `svc-ds-dataset-api` | `connector.internal` | read consented-subject lists |
| `svc-edc` | `identity-registry.read`, `connector.webhook` | forge transfer events |

Each must have a strong generated secret, supplied to the charts through
`secrets.sops.yaml` (`svcDsPortalSecret`, `svcDsConnectorSecret`, …). `extra_audiences`
matters: `ds_auth` verifies the `aud` claim, so a token minted without the callee
in its audience is rejected.

Additionally the portal needs a **public-facing OIDC client** (`ds-portal`) whose
redirect URI is `https://portal.<baseDomain>/auth/callback/keycloak`, matching the
`ORIGIN` the chart sets.

## 4. Organizations (optional, portal UX gating)

Keycloak native organizations provide portal-level gating parallel to
identity-registry memberships. Configured in
`services/keycloak/organizations.yaml`; the `organization` client scope with an
`oidc-organization-membership-mapper` maps memberships into
`organization.<alias>.groups` claims.

This is **UX gating only**. Data access decisions always go through the
identity-registry API — never treat an org claim as an authorization decision.

## 5. Optional sync from the charts

```yaml
global:
  keycloak:
    sync:
      enabled: true
      clientsConfigMap: ds-keycloak-clients
      organizationsConfigMap: ds-keycloak-organizations
```

Off by default: an externally managed Keycloak is not ours to mutate. When
enabled, init containers run `celine-policies keycloak sync` (clients and scopes)
and `ir-cli keycloak org-sync` (organizations) against `global.keycloak.adminUrl`.
Both are idempotent.

Enabling this requires Keycloak admin credentials in `secrets.sops.yaml`. Prefer
provisioning the realm out-of-band and leaving this off — it keeps admin
credentials out of the application namespace entirely.

## 6. Verification

```bash
ISSUER=https://sso.example.org/realms/dataspaces

curl -sf $ISSUER/.well-known/openid-configuration | jq -r .issuer
curl -sf $ISSUER/protocol/openid-connect/certs | jq '.keys | length'

# a service client can mint a token carrying the expected scopes
curl -sf -X POST $ISSUER/protocol/openid-connect/token \
  -d grant_type=client_credentials \
  -d client_id=svc-ds-connector -d client_secret=$SECRET \
  | jq -r '.access_token' | cut -d. -f2 | base64 -d 2>/dev/null | jq '{scope, aud}'
```

If `aud` does not contain the services this client calls, `ds_auth` will reject
its tokens at the callee.
