-- Unused-only inverse. Never erase accepted player messages or attachments.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10s';
DO $pre$
BEGIN
 IF current_database()<>'aoe2hd_db' THEN RAISE EXCEPTION 'CLAN_IMAGE_WRONG_DB'; END IF;
 LOCK TABLE aoe2war_clan_image_hd_v1.request_keys IN ACCESS EXCLUSIVE MODE;
 IF EXISTS(SELECT 1 FROM aoe2war_clan_image_hd_v1.request_keys) THEN RAISE EXCEPTION 'CLAN_IMAGE_USED_PRESERVE_HISTORY'; END IF;
END $pre$;
DROP FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer);
DROP FUNCTION aoe2war_clan_image_hd_v1.post_image(text,text,text,text,text,text,text,integer);
DROP FUNCTION aoe2war_clan_image_hd_v1.leaf_read(text,text,integer,integer,text);
DROP FUNCTION aoe2war_clan_image_hd_v1.leaf_append(text,text,text,text,text,integer);
DROP FUNCTION aoe2war_clan_image_hd_v1.leaf_scope(text,text);
DROP TABLE aoe2war_clan_image_hd_v1.request_keys;
DROP SCHEMA aoe2war_clan_image_hd_v1;
DROP ROLE aoe2war_clan_image_exec_v1;
COMMIT;
