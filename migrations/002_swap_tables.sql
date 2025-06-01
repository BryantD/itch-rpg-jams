-- Migration 002: Swap normalized tables into production and drop old JSON blob table
BEGIN TRANSACTION;

-- Drop legacy JSON-backed table
DROP TABLE IF EXISTS itch_jams;

-- Rename normalized jams table into place
ALTER TABLE itch_jams_new RENAME TO itch_jams;

COMMIT;