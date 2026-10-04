# ADR-0023 — A person's authority has two levels: a platform role, or an organisation's own group

**Date:** 2026-10-03
**Status:** accepted, implemented 2026-10-03
**Rules affected:** `C-16` (a publisher is authorised for the owner whose datasets it
publishes) and `C-17` (an unauthorised write is denied) — both now hold for a person whatever
an organisation's groups are called

## Context

ds authorises a person on Keycloak groups, each naming a role bundle (`ds-admin`,
`ds-participant-admin`, …). Until this change it read them **flat**: `ds_auth.extract_groups`
merged the realm-level `groups` claim with every organisation's `organization.<alias>.groups`
into one list, and any name that was not a bundle passed through as its own capability.

That was written for one realm per deployment, where a realm group meant "this deployment".
A realm that hosts many organisations breaks it in three ways:

- **An organisation group could be a platform grant.** An organisation that has a group named
  `ds-admin`, or `connector.admin`, made its members deployment operators, because the
  organisation it came from was dropped before expansion. The same names exist in every
  organisation of a shared realm, so the two levels collide by construction.
- **The portal and the API read different claims.** The portal also counted
  `realm_access.roles` and **every client's** `resource_access` roles, and the backend counted
  neither. A role on an unrelated client that happened to share a permission name showed
  buttons the API refused; a realm role the dev realm assigned (`ds-admin`, `dataset.admin`)
  did the same.
- **`Principal.grants_in` asked the right question with the wrong input.** It confined
  authority to one organisation, but added every realm group to it, and only three perimeters
  called it; every other guard used the flat list.

## Decision

A person's authority comes from exactly two places, and nothing in between:

| Level | Comes from | Valid | Grants |
|---|---|---|---|
| **platform** | a realm role in `realm_access.roles`, on an explicit allowlist (`ds_auth.REALM_ROLE_BUNDLES`) | everywhere | a **platform bundle**: `platform-admin` → `ds-admin`; `ds-onboarding-operator` → itself |
| **organisation** | a group inside one organisation, `organization.<alias>.groups` | that organisation only | an **organisation bundle** (`ds-participant-admin`, `ds-participant-viewer`, `ds-member`), or one of `ORGANISATION_PERMISSIONS` by name |

Everything else grants nothing:

- a **realm-level group**, whatever its name — the `groups` claim is not read for authority;
- a realm role **not** on the allowlist, and **any** client's `resource_access` role;
- an organisation group naming a platform bundle, a `{service}.admin` superset, a machine
  identity, or anything unknown — there is no pass-through any more;
- a Layer B alias whose target is not an organisation bundle.

`platform-admin` is the role name the host platform uses for its single platform-wide grant;
ds maps it to `ds-admin`. `ds-onboarding-operator` stays a platform seat because reviewing
organisation applications is the dataspace authority's job and not any one organisation's.

`Principal.authority` — what a route-level guard checks — is the platform authority plus
what each organisation grants within itself. Its organisation part can only hold
`ORGANISATION_PERMISSIONS`, so it cannot add up to a platform grant however many
organisations a person is in. `Principal.grants_in(alias, …)` is the platform authority plus
**that** organisation's own groups.

**The portal reads a token through the same code.** `bundles_export.py` renders the claim
reading — not only the bundle table — into `services/portal/src/lib/server/bundles.generated.ts`,
and one hand-written case table (`libs/ds-auth/tests/parity/authority-cases.json`) is decided
by both suites.

## Consequences

- **A realm group is not a migration path.** A deployment that granted bundles as realm groups
  must move them: platform seats to realm roles, participant seats into organisations. The dev
  realm import declares no realm group.
- **There is no realm-level participant seat**, so a single-owner deployment models its owner
  as an organisation. The connector's no-organisations exemption
  (`CONNECTOR_OWNER_SCOPING_STRICT=false`) therefore decides nothing for a person any more: a
  person with no organisation holds no provider permission unless they are the platform
  administrator, who passes the perimeter as `connector.admin`.
- **A host realm's platform administrator is ds's operator.** Where ds is a guest in a realm
  whose platform administrator holds `platform-admin`, that person is `ds-admin` in ds. A
  host's organisation groups (`admins`, `managers`, …) grant nothing in ds unless the
  deployment maps them onto organisation bundles (Layer B).
- **The `groups` claim still classifies.** A token naming any group, at either level, is a
  person's (`is_service_account`); that grants nothing by itself.
- Unchanged: services authorise on their `scope` claim, the organisation client
  (`svc-ds-connector-<alias>`, ADR-0014) and EDC's management-API scopes, the VC-JWT surfaces,
  DSP and DCP.
