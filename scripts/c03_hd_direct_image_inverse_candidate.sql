-- Safe only before use; never erase replay history or media association.
BEGIN;
DO $hold$ BEGIN
 IF current_database()<>'aoe2hd_db' OR EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.image_request_keys) THEN RAISE EXCEPTION 'MEDIA_INVERSE_USED_OR_WRONG_DB_HOLD'; END IF;
END $hold$;
DROP FUNCTION aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer);
DROP FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text);
DROP TABLE aoe2war_social_hd_v2.image_request_keys;
COMMIT;
