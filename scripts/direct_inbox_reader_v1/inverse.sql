-- Source-only inverse: read-only capability, no messages or user records affected.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10s';
DO $pre$ BEGIN
 IF current_database()<>'aoe2hd_db' THEN RAISE EXCEPTION 'DIRECT_READ_WRONG_DB'; END IF;
END $pre$;
DROP FUNCTION aoe2war_direct_read_hd_v1.read_direct(text,text,text,integer,text,integer);
DROP SCHEMA aoe2war_direct_read_hd_v1;
COMMIT;
