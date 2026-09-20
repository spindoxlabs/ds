# ADR-0018 — The EDC schema migrates through EDC's own bootstrapper

**Date:** 2026-09-19
**Status:** accepted

## Context

Each EDC runs with `edc.sql.schema.autocreate=true`. At boot,
`SqlSchemaBootstrapperExtension` runs the `*-schema.sql` file each packaged SQL store
queued on the `SqlSchemaBootstrapper`. Every one of those files is
`CREATE TABLE IF NOT EXISTS`. **A table that already exists is left as it is, so a column
a newer EDC adds never reaches a database an older EDC created.**

Between 0.16.0 and 0.18.0, three such columns were added to two stores ds packages. The
stores read and write all three unconditionally:

| EDC | table | column |
|---|---|---|
| 0.17.0 | `edc_contract_agreement` | `claims JSON` |
| 0.17.0 | `edc_transfer_process` | `claims JSON` |
| 0.18.0 | `edc_transfer_process` | `data_address_owner BOOLEAN DEFAULT FALSE` |

The 0.18.0 upgrade found them and documented three `ALTER TABLE`s as a manual pre-deploy
step. Nothing ran that step. A deployment upgraded in place then lost every negotiation.
The consumer could not store the agreement
(`column "claims" of relation "edc_contract_agreement" does not exist`), and the provider
reported it as `401 Unauthorized` on the agreement message, so it looked like an
authentication fault.

What the pinned EDC and its ecosystem offer:

- **EDC 0.18.0 ships no migration tooling.** Flyway is not on its classpath. Its
  participant-context decision record says a distribution "should provide a migration
  script", and names Flyway as one way to do it. The one schema mechanism it ships is the
  `SqlSchemaBootstrapper`. Its contract is that statements are queued during
  `initialize()` and **must not rely on ordering**, because the order is the extension
  order. The queued files for one datasource run as one statement, in one transaction.
- **Eclipse Tractus-X EDC** turns autocreate off and runs Flyway inside the runtime. It
  began with one Flyway stream per store, deprecated that in 0.12.0, and now keeps one
  stream for the whole connector. The first file is a full snapshot of the upstream DDL,
  and every later file is an idempotent `ADD COLUMN IF NOT EXISTS`. Its
  `V1_9_0__Add_ClaimsColumn.sql` holds the two 0.17.0 statements above, verbatim.

## Decision

1. **ds ships versioned migrations inside `connector.jar`, and queues them on EDC's own
   bootstrapper.** `EdcSchemaMigrationExtension` (`services/edc-extensions`) queues
   `ds-edc-schema/<store>/V<edc version>__<what>.sql` against the datasource EDC gives that
   store (`edc.sql.store.<store>.datasource`). The migrations therefore run where the store
   DDL runs, in the same transaction, and only when autocreate is on.
2. **A migration is an addition guarded twice:**
   `ALTER TABLE IF EXISTS … ADD COLUMN IF NOT EXISTS …`. That is what the bootstrapper's
   "no ordering" contract demands. Queued before the store's `CREATE`, the migration skips a
   fresh database, and the `CREATE` then makes the new shape. Queued after it, the
   migration adds the column, or finds it already there. It runs on every boot, and running
   it again changes nothing. `EdcSchemaMigrationExtensionTest` holds every file to this form.
3. **The upstream schema is committed per version and held to the jar.**
   `services/edc-extensions/tests/integration/edc-schema/v<version>/` holds the packaged
   stores' schema files for each version an existing database may come from.
   `SchemaFixtureTest` (`services/edc-connector`) requires the pinned version's directory to
   equal the jar's files byte for byte. So **an EDC bump fails the build until someone has
   read the DDL diff**, which is the step that was skipped at 0.18.0.
4. **The proof is against PostgreSQL.** `task -d services/edc-extensions test:integration`
   applies each older schema, then boots it the way the runtime does. It requires the
   result to equal what the pinned files create on an empty database: every column, index
   and constraint. It checks both queue orders, a fresh database, a second boot, and rows
   already present. It also asserts the gap that autocreate leaves on its own, so the suite
   is shown able to fail.

## Alternatives rejected

- **Flyway in the image, as Tractus-X does.** It brings a new dependency and a history
  table in every EDC database. ds would also own a full copy of EDC's DDL (the baseline
  snapshot) and would have to maintain it at every bump. What it adds is a history,
  checksums, and room for migrations that are not additive, such as a rename, a type change
  or a data backfill. **No migration so far has needed any of that.** Revisit this decision
  at the first migration that is not an addition.
- **A migration job in compose and in the chart.** Every deployment would need a new
  container or init container, and the job and the image could disagree about the EDC
  version. A migration that ships inside the image that needs it cannot disagree.
- **Keep the manual step.** It was documented, and a deployment that upgraded in place lost
  its negotiations anyway.

## Consequences

- An existing database needs nothing from its operator. A new image brings its schema up
  to date at boot.
- **The range starts at 0.16.0.** A database created before 0.16.0 also needs the
  participant-context data migration (Tractus-X `V1_5_0`). That migration is not additive,
  and ds does not ship it.
- **With `sqlSchemaAutocreate: false` nothing runs.** The operator then applies the store
  files and `ds-edc-schema/*` from the jar as a gated step, and the extension warns at boot
  with the files named.
- A later EDC bump adds a fixture directory and, for each added column, one file under
  `ds-edc-schema/<store>/` and one line in `EdcSchemaMigrationExtension.MIGRATIONS`. The
  unit test fails if that line is missing.
