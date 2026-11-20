-- WE1 Lobby Chat inverse: remove ONLY new restricted gateway namespace,
-- preserving public.chat_messages, user rows, room rows and historical messages.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='15000ms';
DO $pre$
BEGIN
 IF to_regnamespace('aoe2war_lobby_hd_v1') IS NULL
    OR to_regrole('aoe2war_lobby_exec_v1') IS NULL
    OR to_regrole('aoe2war_social_writer') IS NULL
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='aoe2war_lobby_hd_v1'
      AND c.relname NOT IN ('v_users','v_rooms','v_messages','request_keys','request_keys_pkey'))
    OR (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='aoe2war_lobby_hd_v1')<>2
 THEN RAISE EXCEPTION 'LOBBY_INVERSE_UNEXPECTED_SCHEMA_OR_DEPENDENCY'; END IF;
END $pre$;
DROP FUNCTION aoe2war_lobby_hd_v1.post_text(text,text,text);
DROP FUNCTION aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text);
DROP TABLE aoe2war_lobby_hd_v1.request_keys;
DROP VIEW aoe2war_lobby_hd_v1.v_users,
          aoe2war_lobby_hd_v1.v_rooms,
          aoe2war_lobby_hd_v1.v_messages;
DROP SCHEMA aoe2war_lobby_hd_v1 RESTRICT;
DROP ROLE aoe2war_lobby_exec_v1;
COMMIT;
