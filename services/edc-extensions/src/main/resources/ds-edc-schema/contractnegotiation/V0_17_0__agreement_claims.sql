-- EDC 0.17.0 added `claims` to edc_contract_agreement (contract-negotiation-schema.sql).
-- Its CREATE TABLE IF NOT EXISTS never reaches a table an older EDC created, and
-- SqlContractNegotiationStore reads and writes the column unconditionally.
--
-- Additive and guarded twice, so it depends neither on the queue order nor on how
-- often it runs: see EdcSchemaMigrationExtension and docs/decisions/ADR-0018.
ALTER TABLE IF EXISTS edc_contract_agreement ADD COLUMN IF NOT EXISTS claims JSON;
