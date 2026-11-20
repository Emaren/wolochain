-- WE1 Lobby Chat HD-only inverse: disable the least-privilege functions/views.
-- Leave public.chat_messages, chat_rooms, all reactions AND the private
-- lobby_message_request_keys idempotency ledger intact for repeat install.
BEGIN;
SET LOCAL statement_timeout='15000ms';
SET LOCAL lock_timeout='3000ms';
DO $pre$
BEGIN
 IF to_regprocedure('aoe2war_social_hd_v2.lobby_send(text,text,text)') IS NULL
 OR to_regprocedure('aoe2war_social_hd_v2.lobby_history(integer,integer,text)') IS NULL
 THEN RAISE EXCEPTION 'LOBBY_INVERSE_REQUIRES_INSTALLED_GATEWAY'; END IF;
END $pre$;
REVOKE ALL ON FUNCTION
 aoe2war_social_hd_v2.lobby_send(text,text,text),
 aoe2war_social_hd_v2.lobby_history(integer,integer,text)
 FROM aoe2war_social_writer;
DROP FUNCTION aoe2war_social_hd_v2.lobby_send(text,text,text);
DROP FUNCTION aoe2war_social_hd_v2.lobby_history(integer,integer,text);
DROP FUNCTION aoe2war_social_hd_v2.leaf_lobby_append(integer,integer,text);
DROP VIEW aoe2war_social_hd_v2.v_lobby_user_reactions;
DROP VIEW aoe2war_social_hd_v2.v_lobby_guest_counts;
DROP VIEW aoe2war_social_hd_v2.v_lobby_messages;
DROP VIEW aoe2war_social_hd_v2.v_lobby_users;
DROP VIEW aoe2war_social_hd_v2.v_lobby_room;
REVOKE SELECT,INSERT,UPDATE ON
 aoe2war_social_hd_v2.lobby_message_request_keys
 FROM aoe2war_social_exec_v2;
DO $post$
BEGIN
 IF to_regprocedure('aoe2war_social_hd_v2.lobby_send(text,text,text)') IS NOT NULL
 OR to_regprocedure('aoe2war_social_hd_v2.lobby_history(integer,integer,text)') IS NOT NULL
 OR to_regclass('aoe2war_social_hd_v2.lobby_message_request_keys') IS NULL
 THEN RAISE EXCEPTION 'LOBBY_INVERSE_POSTIMAGE_DRIFT'; END IF;
END $post$;
COMMIT;
