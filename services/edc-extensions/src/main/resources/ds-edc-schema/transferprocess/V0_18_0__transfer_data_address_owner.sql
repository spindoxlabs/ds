-- EDC 0.18.0 added `data_address_owner` to edc_transfer_process
-- (transfer-process-schema.sql). Its CREATE TABLE IF NOT EXISTS never reaches a table
-- an older EDC created, and SqlTransferProcessStore reads and writes the column
-- unconditionally. The default is the upstream DDL's, so existing rows read FALSE.
--
-- Additive and guarded twice, so it depends neither on the queue order nor on how
-- often it runs: see EdcSchemaMigrationExtension and docs/decisions/ADR-0018.
ALTER TABLE IF EXISTS edc_transfer_process ADD COLUMN IF NOT EXISTS data_address_owner BOOLEAN DEFAULT FALSE;
