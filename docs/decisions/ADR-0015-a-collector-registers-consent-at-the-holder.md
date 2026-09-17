# ADR-0015 — A collector registers consent at the holder

**Date:** 2026-09-17
**Status:** accepted
**Rules affected:** `D-14`, `D-15c`, `D-18`, `D-19`, `D-20` (amended), `D-21`; scope and
deviations §3.3; blueprint `DSSC-XCT-06`, `DSSC-XCT-26`

## Context

An organisation that holds people's data is not always the organisation those people belong
to. A grid operator holds meter readings; the people are members of an energy community, and
the community is where they consent. ds's consent model gates a personal dataset at the
connector that serves it, so the consent has to be on the grid operator's connector.

Before this decision the connector could not accept it from the community:

- `POST /consent/admin/shares` checked the subject's membership against the offer's
  recipient, which is the wrong organisation whenever the recipient is not the members' own;
- a service principal carried no organisation, so the connector could not tell whom a caller
  spoke for, and `connector.consent.provision` in the `ds-participant-admin` bundle let any
  participant's operator register consent anywhere;
- a withdrawal a service recorded could be lifted by the next service provision (`D-15c`);
- the holder's data plane keys the rows by supply point, which only the community knows.

The blueprints describe the need (cross-organisational consent management, an intermediary
managing consent for natural persons) and prescribe no mechanism. EDC has no consent concept.

## Decision

1. **The collector relation lives in the identity registry.** "Organisation X is an accepted
   consent collector for holder Y" is a pair of DIDs the trust anchor records
   (`identity-registry.collectors.write`). The connector reads it through
   `GET /consent-collectors/check`, cached for `CONNECTOR_COLLECTOR_CACHE_TTL`, dropped by the
   invalidation hint the registry already sends, and failing closed. A holder always collects
   for itself.
2. **The collector writes with its own organisation token** — the plan-2 client
   `svc-ds-connector-<alias>`, which now holds `connector.consent.provision`. This is the one
   exception to "an organisation token is bound to its own participant", and it covers the
   consent write and a per-subject read-back only.
3. **Membership is checked against the organisation the writer speaks for**: the collector, or
   the holder itself for its services and operators.
4. **Whose decision it is, is stated and recorded.** An organisation token says `decided_by`:
   `subject` when it relays the member's decision, `collector` when it decides itself. A relayed
   withdrawal is the member's and no provision lifts it. The collector is recorded on the row,
   in the evidence and in provenance.
5. **The data keys travel with the consent.** `keys: ["<type>:<value>"]` are stored on the
   consent row, replaced by a new registration, dropped by a withdrawal, and carried in the
   data-plane row filter beside `principals`. Provenance records only that keys were supplied.
6. **An offer may require another** (`requires_offers`). Where both are bound to a dataset, the
   dependent offer admits a subject only while the required one does.
7. **Only an organisation's own client registers consent** (the maintainer, 2026-09-17).
   `connector.consent.provision` leaves `ds-participant-admin` **and every plain service
   client**: a realm group and a shared service client are bound to no connector, so either
   could write at any connector for anyone's members. A plain service token is refused with a
   `403` naming the client to use. A person holding `connector.admin` — the deployment operator
   — is kept, for one act no organisation token may perform: the evidenced
   `override_subject_withdrawal` somebody asks for at a desk (`D-15c`). Rows the retired path
   wrote keep `decided_by = "service"`, and the holder's own organisation client or its operator
   may lift those withdrawals.

## Consequences

- **The connector database now holds data keys**, which are personal data. They stay on the
  consent row and in the row filter, and nowhere else: not in `legal_basis`, not in provenance,
  not in logs, and only the registering organisation reads them back.
- **The data-plane contract gained `keys`.** A PEP that refuses unknown fields refuses every
  filtered decision until it is upgraded; the celine `dataset-api` ignores the field until its
  own matching lands. `services/dataset-api-mock` implements `subject_key_match`.
- **`POST /consent/admin/shares` refuses unknown body fields** (`extra="forbid"`), so a
  mistyped `keys` is a `422` rather than a registration without keys.
- **A participant operator's console can no longer register consent**, and neither can a plain
  service client. A deployment whose console or onboarding service did so moves that act to its
  organisation client (`svc-ds-connector-<alias>`), which already holds the permission, and
  states `decided_by`. **This is breaking for the celine onboarding service**, which switches in
  its own plan (`consent-goes-to-the-connector-that-holds-the-data`); `svc-ds-onboarding` no
  longer carries the grant in `services/keycloak/clients.yaml`, and
  [Operations](../deployment/operations.md#upgrading-past-connector-schema-0012-consent-is-registered-by-an-organisation-client)
  has the migration.
- The grid operator's dev fixture holds members' readings now, with offers of its own, and runs
  its own mock data plane on `32022`.
- Membership checks for the holder's own services moved from the offer's recipient to the
  holder's organisation. On the dev fixtures these coincide for every offer except those whose
  recipient is another organisation.
- A member cannot see a holder's asks; their collector sees them in its read-back (`D-18`).

An ADR is not a rule (ADR-0004). What a collector may reach is `D-20` and `D-21`; how the
platform gets there is recorded here.
