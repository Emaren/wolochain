-- WE1 Lobby Chat restricted HD-only gateway: source-only candidate.
-- Requires separately admitted Social V2 role aoe2war_social_writer and a
-- trusted signed-session AF_UNIX service; request uid MUST originate there.
-- No raw public.chat_messages, guest reaction SELECT, DE or financial grants.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='20000ms';

DO $pre$
BEGIN
  IF to_regrole('aoe2war_social_writer') IS NULL
     OR to_regrole('aoe2hd_user') IS NULL
     OR to_regrole('aoe2war_lobby_exec_v1') IS NOT NULL
     OR to_regnamespace('aoe2war_lobby_hd_v1') IS NOT NULL
     OR to_regclass('public.chat_rooms') IS NULL
     OR to_regclass('public.chat_messages') IS NULL
     OR to_regclass('public.chat_message_guest_reactions') IS NULL
     OR to_regclass('public.users') IS NULL
  THEN RAISE EXCEPTION 'LOBBY_PREIMAGE_OR_SOCIAL_WRITER_MISSING'; END IF;
  IF EXISTS(SELECT 1 FROM pg_roles
            WHERE rolname='aoe2war_social_writer' AND
                  (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
  THEN RAISE EXCEPTION 'LOBBY_SOCIAL_WRITER_UNSAFE'; END IF;
END $pre$;

CREATE ROLE aoe2war_lobby_exec_v1 NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA aoe2war_lobby_hd_v1 AUTHORIZATION aoe2hd_user;
REVOKE ALL ON SCHEMA aoe2war_lobby_hd_v1 FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_lobby_hd_v1
  TO aoe2war_social_writer,aoe2war_lobby_exec_v1;

-- Only sanitized inputs needed by the high-level function.
CREATE VIEW aoe2war_lobby_hd_v1.v_users WITH(security_barrier=true) AS
 SELECT id,uid,verification_method
 FROM public.users;
CREATE VIEW aoe2war_lobby_hd_v1.v_rooms WITH(security_barrier=true) AS
 SELECT id,slug,scope
 FROM public.chat_rooms;
CREATE VIEW aoe2war_lobby_hd_v1.v_messages WITH(security_barrier=true) AS
 SELECT id,room_id,user_id,body,created_at
 FROM public.chat_messages;
ALTER VIEW aoe2war_lobby_hd_v1.v_users OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_lobby_hd_v1.v_rooms OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_lobby_hd_v1.v_messages OWNER TO aoe2hd_user;
REVOKE ALL ON TABLE
 aoe2war_lobby_hd_v1.v_users,aoe2war_lobby_hd_v1.v_rooms,
 aoe2war_lobby_hd_v1.v_messages FROM PUBLIC;
GRANT SELECT ON TABLE
 aoe2war_lobby_hd_v1.v_users,aoe2war_lobby_hd_v1.v_rooms,
 aoe2war_lobby_hd_v1.v_messages TO aoe2war_lobby_exec_v1;

-- Private, durable, client-generated 128-bit idempotency token map.
-- Does not rewrite or re-key any historical messages.
CREATE TABLE aoe2war_lobby_hd_v1.request_keys(
 actor_id integer NOT NULL,
 room_id integer NOT NULL,
 request_key char(32) NOT NULL,
 body text NOT NULL,
 message_id integer NOT NULL,
 created_at timestamp without time zone NOT NULL DEFAULT clock_timestamp(),
 CONSTRAINT request_keys_pkey PRIMARY KEY(actor_id,room_id,request_key)
);
REVOKE ALL ON TABLE aoe2war_lobby_hd_v1.request_keys FROM PUBLIC;

-- Static leaf owns one, narrowly restricted legacy INSERT; it has no public or writer execute.
CREATE FUNCTION aoe2war_lobby_hd_v1.leaf_append_lobby(
 p_room_id integer,p_actor_id integer,p_body text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE inserted_id integer;
BEGIN
 IF p_room_id IS NULL OR p_actor_id IS NULL OR p_body IS NULL OR
    btrim(p_body)='' OR length(p_body)>280 OR octet_length(p_body)>1120 OR
    NOT EXISTS(SELECT 1 FROM public.chat_rooms
       WHERE id=p_room_id AND slug='main-lobby' AND scope='lobby')
 THEN RAISE EXCEPTION 'LOBBY_LEAF_DENIED'; END IF;
 INSERT INTO public.chat_messages(room_id,user_id,body,created_at)
 VALUES(p_room_id,p_actor_id,p_body,clock_timestamp())
 RETURNING id INTO inserted_id;
 RETURN inserted_id;
END $leaf$;
ALTER FUNCTION aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)
 OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)
 FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)
 TO aoe2war_lobby_exec_v1;

-- High level function accepts a UID ONLY from trusted AF_UNIX signed-session service.
-- Raw database logins can spoof the UID; never expose direct writer credentials to web.
CREATE FUNCTION aoe2war_lobby_hd_v1.post_text(
 p_verified_uid text,p_body text,p_request_key text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $lobby$
DECLARE
 v_actor record;v_room record;v_last record;v_replay record;
 v_body text;v_id integer;
BEGIN
 v_body:=btrim(replace(replace(p_body,E'\r\n',E'\n'),E'\r',E'\n'));
 IF p_verified_uid IS NULL OR length(p_verified_uid)>100 OR
    p_verified_uid='' OR v_body IS NULL OR
    length(v_body)=0 OR length(v_body)>280 OR octet_length(v_body)>1120 OR
    p_request_key IS NULL OR p_request_key !~ '^[0-9a-f]{32}$'
 THEN RETURN jsonb_build_object('status',400,'detail','INVALID_LOBBY_MESSAGE'); END IF;

 SELECT id,uid,verification_method INTO v_actor
 FROM aoe2war_lobby_hd_v1.v_users
 WHERE uid=p_verified_uid;
 IF NOT FOUND OR v_actor.verification_method IN ('system','none') OR
    v_actor.uid ~ '^aoe2hd_ai_' OR
    v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry')
 THEN RETURN jsonb_build_object('status',401,'detail','SIGNED_HUMAN_REQUIRED'); END IF;

 SELECT id,slug INTO v_room FROM aoe2war_lobby_hd_v1.v_rooms
 WHERE slug='main-lobby' AND scope='lobby';
 IF NOT FOUND THEN RETURN jsonb_build_object('status',503,'detail','LOBBY_ROOM_UNAVAILABLE'); END IF;

 -- Serialize each actor's writes; retry of same token/body returns original id.
 PERFORM pg_catalog.pg_advisory_xact_lock(91325,v_actor.id);
 SELECT body,message_id INTO v_replay FROM aoe2war_lobby_hd_v1.request_keys
 WHERE actor_id=v_actor.id AND room_id=v_room.id AND request_key=p_request_key;
 IF FOUND THEN
   IF v_replay.body<>v_body THEN
     RETURN jsonb_build_object('status',409,'detail','LOBBY_IDEMPOTENCY_CONFLICT');
   END IF;
   RETURN jsonb_build_object('status',201,'ok',true,'messageId',v_replay.message_id,'replayed',true);
 END IF;
 SELECT created_at INTO v_last FROM aoe2war_lobby_hd_v1.v_messages
 WHERE room_id=v_room.id AND user_id=v_actor.id
 ORDER BY created_at DESC,id DESC LIMIT 1;
 IF FOUND AND clock_timestamp()-v_last.created_at < interval '4 seconds' THEN
   RETURN jsonb_build_object('status',429,'detail','LOBBY_SEND_COOLDOWN');
 END IF;
 SELECT aoe2war_lobby_hd_v1.leaf_append_lobby(v_room.id,v_actor.id,v_body)
 INTO v_id;
 INSERT INTO aoe2war_lobby_hd_v1.request_keys(actor_id,room_id,request_key,body,message_id)
 VALUES(v_actor.id,v_room.id,p_request_key,v_body,v_id);
 RETURN jsonb_build_object('status',201,'ok',true,'messageId',v_id,'replayed',false);
END $lobby$;

-- Transfer only the high-level function and private dedupe table.
GRANT CREATE ON SCHEMA aoe2war_lobby_hd_v1 TO aoe2war_lobby_exec_v1;
ALTER TABLE aoe2war_lobby_hd_v1.request_keys OWNER TO aoe2war_lobby_exec_v1;
ALTER FUNCTION aoe2war_lobby_hd_v1.post_text(text,text,text)
 OWNER TO aoe2war_lobby_exec_v1;
REVOKE CREATE ON SCHEMA aoe2war_lobby_hd_v1 FROM aoe2war_lobby_exec_v1;
REVOKE ALL ON FUNCTION aoe2war_lobby_hd_v1.post_text(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_lobby_hd_v1.post_text(text,text,text)
 TO aoe2war_social_writer;

DO $post$
BEGIN
 IF has_schema_privilege('aoe2war_lobby_exec_v1','aoe2war_lobby_hd_v1','CREATE')
 OR has_table_privilege('aoe2war_social_writer','public.chat_messages','INSERT')
 OR has_table_privilege('aoe2war_social_writer','public.chat_message_guest_reactions','SELECT')
 OR has_table_privilege('aoe2war_social_writer','aoe2war_lobby_hd_v1.request_keys','SELECT')
 OR has_table_privilege('aoe2war_lobby_exec_v1','public.chat_messages','INSERT')
 OR has_function_privilege('aoe2war_social_writer',
    'aoe2war_lobby_hd_v1.leaf_append_lobby(integer,integer,text)','EXECUTE')
 OR has_table_privilege('aoe2war_lobby_exec_v1','public.bet_wagers','INSERT')
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member='aoe2war_lobby_exec_v1'::regrole)
 THEN RAISE EXCEPTION 'LOBBY_LEAST_PRIVILEGE_POSTIMAGE_FAILED'; END IF;
END $post$;
COMMIT;
