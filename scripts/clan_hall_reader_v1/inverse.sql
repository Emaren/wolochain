-- Unused or withdrawn read-only capability; no data changes and no CASCADE.
BEGIN;
SET LOCAL lock_timeout='350ms';
DO $pre$ BEGIN IF current_database()<>'aoe2hd_db' THEN RAISE EXCEPTION 'HD_ONLY'; END IF; END $pre$;
DROP FUNCTION aoe2war_clan_read_hd_v1.read_hall(text,text,integer,integer);
DROP SCHEMA aoe2war_clan_read_hd_v1;
COMMIT;
