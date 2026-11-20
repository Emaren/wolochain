-- WE1 Lobby Chat HD-only gateway candidate. Separate admission from Social V2.
-- PR #251 Social role/schema MUST already have INSTALLED_POSTIMAGE_PASS.
-- Requires signed-session AF_UNIX sidecar to bind p_verified_uid to real session.
-- Never expose raw guest-session IDs, grant public.chat_messages INSERT,
-- or broaden privileges of aoe2war_web_prod or financial roles.
BEGIN;
SET LOCAL statement_timeout='15000ms';
SET LOCAL lock_timeout='3000ms';

DO $pre$
BEGIN
 IF to_regrole('aoe2war_social_writer') IS NULL
 OR to_regrole('aoe2war_social_exec_v2') IS NULL
 OR to_regnamespace('aoe2war_social_hd_v2') IS NULL
 OR to_regclass('public.chat_messages') IS NULL
 OR to_regclass('public.chat_rooms') IS NULL
 OR to_regclass('public.chat_message_guest_reactions') IS NULL
 OR to_regclass('public.chat_message_reactions') IS NULL
 OR to_regclass('public.users') IS NULL
 OR to_regclass('aoe2war_social_hd_v2.v_users') IS NULL
 THEN RAISE EXCEPTION 'LOBBY_REQUIRES_INSTALLED_SOCIAL_V2_AND_HD_TABLES'; END IF;
 IF has_table_privilege('aoe2war_social_writer','public.chat_messages','INSERT')
 OR has_table_privilege('aoe2war_social_writer','public.chat_message_guest_reactions','SELECT')
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member='aoe2war_social_writer'::regrole)
 THEN RAISE EXCEPTION 'LOBBY_SOCIAL_WRITER_RAW_ACCESS_DRIFT'; END IF;
 IF to_regprocedure('aoe2war_social_hd_v2.lobby_send(text,text,text)') IS NOT NULL
 OR to_regprocedure('aoe2war_social_hd_v2.lobby_history(integer,integer,text)') IS NOT NULL
 THEN RAISE EXCEPTION 'LOBBY_GATEWAY_ALREADY_INSTALLED'; END IF;
END $pre$;

-- Preserve idempotency records across rollback and future re-install.
-- No user-controlled SQL, no money table, no raw session identifiers.
CREATE TABLE IF NOT EXISTS aoe2war_social_hd_v2.lobby_message_request_keys (
 actor_uid text NOT NULL,
 request_key varchar(32) NOT NULL,
 body varchar(280) NOT NULL,
 message_id integer,
 created_at timestamp(6) NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(actor_uid,request_key)
);
ALTER TABLE aoe2war_social_hd_v2.lobby_message_request_keys OWNER TO aoe2hd_user;
REVOKE ALL ON TABLE aoe2war_social_hd_v2.lobby_message_request_keys FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON TABLE aoe2war_social_hd_v2.lobby_message_request_keys
 TO aoe2war_social_exec_v2;

CREATE VIEW aoe2war_social_hd_v2.v_lobby_room WITH(security_barrier=true) AS
 SELECT id,slug FROM public.chat_rooms
 WHERE slug='main-lobby' AND scope='lobby';
CREATE VIEW aoe2war_social_hd_v2.v_lobby_users WITH(security_barrier=true) AS
 SELECT id,uid,verification_method,in_game_name,steam_persona_name,
        verification_level,verified FROM public.users;
CREATE VIEW aoe2war_social_hd_v2.v_lobby_messages WITH(security_barrier=true) AS
 SELECT m.id,m.room_id,m.user_id,m.body,m.created_at
 FROM public.chat_messages m JOIN public.chat_rooms r ON r.id=m.room_id
 WHERE r.slug='main-lobby' AND r.scope='lobby';
CREATE VIEW aoe2war_social_hd_v2.v_lobby_guest_counts WITH(security_barrier=true) AS
 SELECT g.message_id,g.emoji,count(*)::bigint AS guest_count
 FROM public.chat_message_guest_reactions g
 JOIN public.chat_messages m ON m.id=g.message_id
 JOIN public.chat_rooms r ON r.id=m.room_id
 WHERE r.slug='main-lobby' AND r.scope='lobby'
 GROUP BY g.message_id,g.emoji;
CREATE VIEW aoe2war_social_hd_v2.v_lobby_user_reactions WITH(security_barrier=true) AS
 SELECT r.message_id,r.emoji,u.uid,u.in_game_name,u.steam_persona_name
 FROM public.chat_message_reactions r
 JOIN public.chat_messages m ON m.id=r.message_id
 JOIN public.chat_rooms cr ON cr.id=m.room_id
 JOIN public.users u ON u.id=r.user_id
 WHERE cr.slug='main-lobby' AND cr.scope='lobby';
ALTER VIEW aoe2war_social_hd_v2.v_lobby_room OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_lobby_users OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_lobby_messages OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_lobby_guest_counts OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_lobby_user_reactions OWNER TO aoe2hd_user;
REVOKE ALL ON
 aoe2war_social_hd_v2.v_lobby_room,
 aoe2war_social_hd_v2.v_lobby_users,
 aoe2war_social_hd_v2.v_lobby_messages,
 aoe2war_social_hd_v2.v_lobby_guest_counts,
 aoe2war_social_hd_v2.v_lobby_user_reactions FROM PUBLIC;
GRANT SELECT ON
 aoe2war_social_hd_v2.v_lobby_room,
 aoe2war_social_hd_v2.v_lobby_users,
 aoe2war_social_hd_v2.v_lobby_messages,
 aoe2war_social_hd_v2.v_lobby_guest_counts,
 aoe2war_social_hd_v2.v_lobby_user_reactions TO aoe2war_social_exec_v2;

CREATE FUNCTION aoe2war_social_hd_v2.leaf_lobby_append(
 p_room integer,p_user integer,p_body text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE v_id integer;
BEGIN
 IF p_room IS NULL OR p_user IS NULL OR p_body IS NULL
 OR length(p_body)=0 OR length(p_body)>280 OR octet_length(p_body)>1120
 OR NOT EXISTS(SELECT 1 FROM public.chat_rooms WHERE id=p_room
               AND slug='main-lobby' AND scope='lobby')
 THEN RAISE EXCEPTION 'LOBBY_LEAF_DENIED'; END IF;
 INSERT INTO public.chat_messages(room_id,user_id,body,created_at)
 VALUES(p_room,p_user,p_body,clock_timestamp()) RETURNING id INTO v_id;
 RETURN v_id;
END $leaf$;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_lobby_append(integer,integer,text)
 OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_social_hd_v2.leaf_lobby_append(integer,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_hd_v2.leaf_lobby_append(integer,integer,text)
 TO aoe2war_social_exec_v2;

-- Inputs MUST be issued by the verified Unix sidecar, never browser body uid.
-- A failed call raises SQL exception and rolls back all idempotency DML.
CREATE FUNCTION aoe2war_social_hd_v2.lobby_send(
 p_verified_uid text,p_body text,p_idempotency_key text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $send$
DECLARE v_actor record; v_room integer; v_body text; v_old record;
        v_recent timestamp; v_id integer;
BEGIN
 v_body:=btrim(regexp_replace(coalesce(p_body,''),'[[:space:]]+',' ','g'));
 IF p_verified_uid IS NULL OR length(p_verified_uid)>100
 OR p_idempotency_key IS NULL OR p_idempotency_key !~ '^[0-9a-f]{32}$'
 OR v_body='' OR length(v_body)>280 OR octet_length(v_body)>1120
 THEN RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','LOBBY_INVALID_MESSAGE')); END IF;
 SELECT id,uid,verification_method INTO v_actor
 FROM aoe2war_social_hd_v2.v_lobby_users WHERE uid=p_verified_uid;
 IF NOT FOUND OR v_actor.verification_method='system' OR
    v_actor.uid LIKE 'aoe2hd_ai_%' OR
    v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
      'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
      'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry')
 THEN RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED')); END IF;
 SELECT id INTO v_room FROM aoe2war_social_hd_v2.v_lobby_room WHERE slug='main-lobby';
 IF NOT FOUND THEN RETURN jsonb_build_object('status',503,'body',jsonb_build_object('detail','LOBBY_ROOM_NOT_PROVISIONED')); END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(84915,v_actor.id::integer);
 SELECT message_id,body INTO v_old
 FROM aoe2war_social_hd_v2.lobby_message_request_keys
 WHERE actor_uid=v_actor.uid AND request_key=p_idempotency_key;
 IF FOUND THEN
   IF v_old.body=v_body AND v_old.message_id IS NOT NULL THEN
     RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
       'ok',true,'messageId',v_old.message_id,'replayed',true));
   END IF;
   RETURN jsonb_build_object('status',409,'body',jsonb_build_object('detail','LOBBY_REQUEST_KEY_CONFLICT'));
 END IF;
 SELECT created_at INTO v_recent FROM aoe2war_social_hd_v2.v_lobby_messages
 WHERE room_id=v_room AND user_id=v_actor.id ORDER BY id DESC LIMIT 1;
 IF FOUND AND clock_timestamp()-v_recent < interval '4 seconds' THEN
   RETURN jsonb_build_object('status',429,'body',jsonb_build_object('detail','LOBBY_SEND_COOLDOWN'));
 END IF;
 INSERT INTO aoe2war_social_hd_v2.lobby_message_request_keys(actor_uid,request_key,body)
 VALUES(v_actor.uid,p_idempotency_key,v_body);
 SELECT aoe2war_social_hd_v2.leaf_lobby_append(v_room,v_actor.id,v_body) INTO v_id;
 UPDATE aoe2war_social_hd_v2.lobby_message_request_keys SET message_id=v_id
 WHERE actor_uid=v_actor.uid AND request_key=p_idempotency_key;
 RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
  'ok',true,'messageId',v_id,'roomSlug','main-lobby','replayed',false));
END $send$;

-- Public history remains visible through a shaped function, not raw
-- guest-session SELECT to the website role. Guest reaction IDs never returned.
CREATE FUNCTION aoe2war_social_hd_v2.lobby_history(
 p_limit integer,p_before_id integer,p_viewer_uid text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $history$
DECLARE v_result jsonb;
BEGIN
 IF p_limit IS NULL OR p_limit<1 OR p_limit>120 OR
    (p_before_id IS NOT NULL AND p_before_id<1)
 THEN RAISE EXCEPTION 'LOBBY_HISTORY_INVALID_PAGE'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object(
  'id',m.id,'roomSlug','main-lobby','body',m.body,
  'createdAt',to_char(m.created_at,'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
  'user',jsonb_build_object('uid',u.uid,'inGameName',u.in_game_name,
    'steamPersonaName',u.steam_persona_name,
    'verified',coalesce(u.verified,false),
    'verificationLevel',coalesce(u.verification_level,0),
    'isAi',u.uid LIKE 'aoe2hd_ai_%'),
  'reactions',coalesce((
    SELECT jsonb_agg(jsonb_build_object(
      'emoji',q.emoji,'count',q.total,
      'anonymousCount',q.anonymous_count,
      'viewerReacted',EXISTS(
        SELECT 1 FROM aoe2war_social_hd_v2.v_lobby_user_reactions own
        WHERE own.message_id=m.id AND own.emoji=q.emoji AND own.uid=p_viewer_uid),
      'users',coalesce((SELECT jsonb_agg(jsonb_build_object(
        'uid',ur.uid,'displayName',
          coalesce(nullif(ur.in_game_name,''),nullif(ur.steam_persona_name,''),ur.uid)))
        FROM aoe2war_social_hd_v2.v_lobby_user_reactions ur
        WHERE ur.message_id=m.id AND ur.emoji=q.emoji),'[]'::jsonb)
    )) FROM (
      SELECT emoji,sum(total)::integer AS total,
             sum(anonymous_count)::integer AS anonymous_count
      FROM (
        SELECT emoji,guest_count AS total,guest_count AS anonymous_count
        FROM aoe2war_social_hd_v2.v_lobby_guest_counts
        WHERE message_id=m.id
        UNION ALL
        SELECT emoji,count(*)::bigint,0::bigint
        FROM aoe2war_social_hd_v2.v_lobby_user_reactions
        WHERE message_id=m.id GROUP BY emoji
      ) z GROUP BY emoji
    ) q
  ),'[]'::jsonb))
  ORDER BY m.id ASC),'[]'::jsonb) INTO v_result
 FROM (SELECT * FROM aoe2war_social_hd_v2.v_lobby_messages
       WHERE p_before_id IS NULL OR id<p_before_id
       ORDER BY id DESC LIMIT p_limit) m
 JOIN aoe2war_social_hd_v2.v_lobby_users u ON u.id=m.user_id;
 RETURN v_result;
END $history$;

GRANT CREATE ON SCHEMA aoe2war_social_hd_v2 TO aoe2war_social_exec_v2;
ALTER FUNCTION aoe2war_social_hd_v2.lobby_send(text,text,text)
 OWNER TO aoe2war_social_exec_v2;
ALTER FUNCTION aoe2war_social_hd_v2.lobby_history(integer,integer,text)
 OWNER TO aoe2war_social_exec_v2;
REVOKE CREATE ON SCHEMA aoe2war_social_hd_v2 FROM aoe2war_social_exec_v2;
REVOKE ALL ON FUNCTION
 aoe2war_social_hd_v2.lobby_send(text,text,text),
 aoe2war_social_hd_v2.lobby_history(integer,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
 aoe2war_social_hd_v2.lobby_send(text,text,text),
 aoe2war_social_hd_v2.lobby_history(integer,integer,text)
 TO aoe2war_social_writer;

DO $post$
BEGIN
 IF has_table_privilege('aoe2war_social_writer','public.chat_messages','INSERT')
 OR has_table_privilege('aoe2war_social_writer','public.chat_message_guest_reactions','SELECT')
 OR has_table_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.lobby_message_request_keys','SELECT')
 OR has_function_privilege('aoe2war_social_writer',
    'aoe2war_social_hd_v2.leaf_lobby_append(integer,integer,text)','EXECUTE')
 OR has_schema_privilege('aoe2war_social_exec_v2','aoe2war_social_hd_v2','CREATE')
 OR has_table_privilege('aoe2war_social_exec_v2','public.chat_messages','INSERT')
 OR has_table_privilege('aoe2war_social_exec_v2','public.chat_message_guest_reactions','SELECT')
 THEN RAISE EXCEPTION 'LOBBY_RAW_OR_TRANSITIVE_GRANT_DRIFT'; END IF;
END $post$;
COMMIT;
