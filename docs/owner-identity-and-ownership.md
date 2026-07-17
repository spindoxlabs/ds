# Owner Identity & Ownership

This document describes the owner identity model: how organizations are registered as data owners, how ownership binds datasets to organizations via governance rules, how owner DIDs flow into ODRL policies, and how organization memberships gate consent.

---

## Two DID levels

The dataspace uses two levels of DID identity:

| Level | Example | Issued to | Used for |
|-------|---------|-----------|----------|
| **Participant DID** | `did:web:provider.dataspaces.localhost` | The dataspace participant (provider/consumer node) | DSP protocol, STS tokens, EDC negotiation, credential service |
| **Owner DID** | `did:web:example-org.dataspaces.localhost` | The organization that owns the data | ODRL assigner, provenance attribution, membership scope gating |

A participant DID represents the **infrastructure node**. An owner DID represents the **organization** whose data the node manages. A single provider node can host datasets owned by multiple organizations — the governance rule determines which owner is the assigner for each dataset.

When no ownership is declared, the participant DID is used as the ODRL assigner (backward compatible).

---

## Owner registry

Owners are stored in the identity-registry `Owner` table:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (PK) | Kebab-case alias used in `governance.yaml` ownership blocks |
| `type` | string | Schema.org CURIE (`schema:Organization`, `schema:NGO`, etc.) |
| `name` | string | Human-readable display name |
| `did` | string (nullable) | `did:web:` URI — preferred canonical URI |
| `url` | string (nullable) | Homepage URI — fallback when no DID |
| `aliases` | JSON array | Alternative lookup keys |
| `organization_config` | JSON (nullable) | Keycloak org provisioning config |

### Canonical URI resolution

The `canonical_uri` for an owner follows this precedence:

1. `did` (if set) — the DID is authoritative
2. `url` (if set, no DID) — fallback for external open-data providers
3. `None` — no canonical URI; ODRL assigner falls back to participant DID

### Managing owners

```bash
# CLI
ir-cli owner add --id example-org --type schema:NGO --name "Example Organization" --did did:web:example-org.dataspaces.localhost
ir-cli owner import --file seed/owners.dev.yaml
ir-cli owner list
ir-cli owner remove --id example-org

# API (admin)
POST   /admin/owners          — create
GET    /admin/owners           — list all
GET    /admin/owners/{id}      — get by id
PUT    /admin/owners/{id}      — update
DELETE /admin/owners/{id}      — delete

# API (service — used by connector)
GET    /owners/resolve?alias=<name>  — resolve alias or id → OwnerEntry
```

### Seed file format

```yaml
owners:
  - id: example-org
    type: schema:NGO
    name: Example Organization
    did: did:web:provider.dataspaces.localhost
    aliases: [example]
    organization:
      create: true
      role: community

  - id: open-data-provider
    type: schema:Organization
    name: Open Data Provider
    url: https://open-data.example.org
```

The dev seed file (`services/identity-registry/seed/owners.dev.yaml`) is imported automatically by the `identity-registry-bootstrap` init container during `task start`.

---

## Ownership in governance rules

Governance rules declare ownership via the `ownership` block:

```yaml
defaults:
  ownership:
    - name: example-org
      type: DATA_OWNER
```

Individual datasets can override the default:

```yaml
sources:
  datasets.gold.external_weather:
    ownership:
      - name: open-data-provider
```

### Resolution chain at sync time

When `POST /provider/sync` is called:

```
governance.yaml  →  GovernanceResolver  →  GovernanceRuleV2
                                              ↓ ownership[0].name
                                         HttpOwnersRegistry
                                              ↓ GET /owners/resolve?alias=example-org
                                         OwnerEntry.canonical_uri
                                              ↓ did:web:example-org.dataspaces.localhost
                                         ODRL Offer assigner
```

1. The connector pre-resolves all owner aliases from the governance config via `HttpOwnersRegistry`
2. The resolved DIDs are passed to `GovernanceMapper` as a sync dict lookup
3. `_resolve_assigner` uses the owner DID as the ODRL assigner
4. If the alias is unknown or has no DID, the assigner falls back to the participant DID

### Effect on ODRL policy

| Governance field | Without ownership | With ownership |
|-----------------|-------------------|----------------|
| `odrl:assigner` | `did:web:provider.dataspaces.localhost` | `did:web:example-org.dataspaces.localhost` |
| `ds:accessScope` right operand | `dataspaces.query` | `owner:example-org:member` |
| Consent subject-pool check | Skipped | Enforced via IR `/memberships/check` |

---

## Governance overlay

A governance overlay merges deployment-specific configuration on top of the base `governance.yaml` without modifying the committed file. This is the primary mechanism for binding generic owner aliases to real organizations.

### How it works

1. Create `governance.<name>.yaml` alongside `governance.yaml`
2. Set `CONNECTOR_GOVERNANCE_OVERLAY_NAME=<name>` (or pass programmatically)
3. The overlay merges at two levels:
   - **defaults**: field-level merge; non-empty lists (including `ownership`) fully replace the base
   - **sources**: existing keys get rule-level merge; new keys are added

### Example

Base (`governance.yaml`):
```yaml
defaults:
  access_level: internal
sources:
  datasets.gold.meters:
    title: Meter Readings
    dataspace:
      expose: true
```

Overlay (`governance.production.yaml`):
```yaml
defaults:
  ownership:
    - name: production-org
```

Result: all datasets inherit `ownership: [{name: production-org}]`.

### Local overrides

`*.local.yaml` is gitignored. Use `governance.local.yaml` for personal dev overrides that should never be committed.

---

## Organization memberships

The `OrganizationMembership` table tracks which user DIDs belong to which owner organizations:

| Field | Type | Description |
|-------|------|-------------|
| `user_did` | string (PK, FK → dids) | The member's DID |
| `organization_alias` | string (PK) | Owner alias from the owners table |
| `role` | string (nullable) | Role within the org (consumer, prosumer, admin) |
| `status` | string | `active`, `suspended`, `revoked` |

### Managing memberships

```bash
# CLI
ir-cli membership add --user-did did:web:users.dataspaces.localhost:data-subject --organization example-org --role consumer
ir-cli membership list --organization example-org
ir-cli membership remove --user-did did:web:users.dataspaces.localhost:data-subject --organization example-org
ir-cli membership import --community-registry members.yaml --organization example-org --did-prefix users.dataspaces.localhost

# API (admin)
POST   /admin/memberships                            — register membership
GET    /admin/memberships?organization=<alias>        — list members of org
GET    /admin/memberships?user_did=<did>              — list orgs for user
DELETE /admin/memberships/{user_did}/{org_alias}      — remove membership

# API (service — used by connector consent path)
GET    /memberships/check?user_did=<did>&organization=<alias>  — boolean check
```

### Community registry import

The `ir-cli membership import` command reads any YAML with a top-level `members` dict:

```yaml
members:
  member-001:
    user_id: "member-001"
    role: consumer
    status: active
    # domain-specific fields (assets, delivery_points, etc.) are silently ignored
```

The `--did-prefix` option maps `user_id` → DID: `did:web:<prefix>:<user_id>`. Without it, the command looks up `KeycloakMapping` records.

---

## Consent subject-pool validation

When a dataset has ownership, the consent endpoint validates that each subject belongs to the owner's organization before creating a consent request:

```
POST /consent/request
  ↓ dataset_id → GovernanceResolver → ownership[0].name
  ↓ for each subject_id:
  ↓   derive subject DID
  ↓   GET /memberships/check?user_did=<did>&organization=<alias>
  ↓   if not member → 403 "subject not a member of dataset owner organization"
  ↓ all subjects pass → create consent records
```

Datasets without ownership skip the check entirely (backward compatible).

---

## Provisioning example

A complete provisioning sequence for a new owner and its members:

```bash
# 1. Register the owner
ir-cli owner add \
  --id example-org \
  --type schema:NGO \
  --name "Example Organization" \
  --did did:web:provider.dataspaces.localhost \
  --alias example

# 2. Add ownership to governance (or use an overlay)
# governance.yaml defaults.ownership: [{name: example-org}]

# 3. Provision owner-relative scope on consumers
ir-cli participant add \
  --did did:web:consumer.dataspaces.localhost \
  --scope owner:example-org:member \
  ...

# 4. Register memberships
ir-cli membership add \
  --user-did did:web:users.dataspaces.localhost:data-subject \
  --organization example-org \
  --role consumer

# 5. Sync to EDC
# POST /provider/sync → ODRL assigner = owner DID, scope = owner:example-org:member
```

### Safe rollout order

When adding ownership to an existing dataset:

1. **First** provision `owner:<alias>:member` scope on consumers
2. **Then** add `ownership` to the governance rule
3. **Then** re-sync: `POST /provider/sync`

Never reverse steps 1 and 2 — adding ownership before provisioning scopes locks out existing consumers.

---

## IR memberships vs Keycloak organizations

Two independent systems, same upstream source, different consumers:

| | IR `OrganizationMembership` | Keycloak Organizations |
|---|---|---|
| **Authority for** | Data access (consent gating, membership check) | Authentication + portal UX |
| **Written by** | `ir-cli membership add/import` | External policies CLI |
| **Read by** | Connector consent path (HTTP API) | Portal (JWT claims) |
| **Required?** | Yes, for consent and owner-relative policy | Optional — only for portal org-scoped UI |

They never query each other. The consent path checks IR, never Keycloak. The portal checks JWT claims, never IR.
