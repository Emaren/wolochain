-- WE1 C03 HD-only additive v2: source-only install candidate, NOT a permit.
-- Exact HD original catalog: 8 existing social/identity tables owned aoe2hd_user,
-- their raw ACLs explicit; four social serial sequences have raw relacl NULL.
-- DE lacks five objects: this script MUST NEVER target aoe2de_db.
-- Existing broad aoe2hd_user can trigger financial ON DELETE CASCADE via users.
-- ONLY the 3 fixed leaf functions below execute under that broad owner. New
-- high-level SECURITY DEFINER functions are owned by a separate NOLOGIN,
-- NOINHERIT, NOSUPERUSER restricted executor with no original-table access.
-- The website's authenticated AF_UNIX sidecar alone supplies verified UID;
-- raw writer credential compromise can impersonate UID: root service secret,
-- HBA/peer checks, and JWT acceptance are independent mandatory conditions.
-- No source review/CI authorizes live PG installation.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10000ms';
DO $pre$
DECLARE n record;
BEGIN
 IF current_database()<>'aoe2hd_db' THEN
   RAISE EXCEPTION 'C03_HD_ONLY_DATABASE_MISMATCH';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aoe2hd_user' AND NOT rolsuper)
    OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aoe2war_web_prod' AND NOT rolsuper AND NOT rolinherit)
    OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('aoe2war_social_writer','aoe2war_social_exec_v2'))
    OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='aoe2war_social_hd_v2')
 THEN RAISE EXCEPTION 'C03_HD_ROLE_OR_SCHEMA_PREIMAGE_HOLD'; END IF;
 FOR n IN
   WITH objects(relname,relkind,raw_acl) AS (
   VALUES
   ('users','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clans','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_members','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_messages','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_conversations','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_conversation_participants','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_messages','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_message_drafts','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_messages_id_seq','S',NULL),
   ('direct_conversations_id_seq','S',NULL),
   ('direct_conversation_participants_id_seq','S',NULL),
   ('direct_messages_id_seq','S',NULL))
   SELECT o.relname, o.relkind, o.raw_acl, c.oid, c.relowner,
          c.relkind AS actual_kind,c.relacl,c.relrowsecurity,c.relforcerowsecurity
   FROM objects o LEFT JOIN pg_class c ON c.oid=to_regclass(format('public.%I',o.relname))
 LOOP
  IF n.oid IS NULL OR n.relowner<>'aoe2hd_user'::regrole OR
     n.actual_kind::text<>n.relkind OR n.relrowsecurity OR n.relforcerowsecurity OR
     n.relacl::text IS DISTINCT FROM n.raw_acl
   THEN RAISE EXCEPTION 'C03_HD_OBJECT_OWNER_KIND_RAW_ACL_MISMATCH %',n.relname; END IF;
 END LOOP;
 IF EXISTS (
   SELECT 1 FROM pg_trigger t WHERE t.tgenabled IN ('O','A','R')
     AND NOT t.tgisinternal AND t.tgrelid IN (
        SELECT to_regclass(format('public.%I',x))
        FROM unnest(ARRAY['users','clans','clan_members','clan_messages',
          'direct_conversations','direct_conversation_participants',
          'direct_messages','direct_message_drafts']) x)
 ) THEN RAISE EXCEPTION 'C03_HD_UNREVIEWED_USER_TRIGGER'; END IF;
 -- This source does NOT prove the original owner has no other financial power.
 -- A separate real owner/member/definer/FDW authority witness is required.
END $pre$;
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER
 NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
CREATE ROLE aoe2war_social_exec_v2 NOLOGIN NOINHERIT NOSUPERUSER
 NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA aoe2war_social_hd_v2 AUTHORIZATION aoe2hd_user;
REVOKE ALL ON SCHEMA aoe2war_social_hd_v2 FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_social_hd_v2
 TO aoe2war_social_writer,aoe2war_social_exec_v2;
-- All views are owned by broad legacy table owner, SELECT only to restricted
-- NONLOGIN executor. NO view SELECT to the external social writer.
CREATE VIEW aoe2war_social_hd_v2.v_users WITH(security_barrier=true) AS
 SELECT id,uid,is_admin,verification_method,in_game_name,steam_persona_name,created_at
 FROM public.users;
CREATE VIEW aoe2war_social_hd_v2.v_clans WITH(security_barrier=true) AS
 SELECT id,slug,status,chat_audience_policy FROM public.clans;
CREATE VIEW aoe2war_social_hd_v2.v_clan_members WITH(security_barrier=true) AS
 SELECT clan_id,user_id,status FROM public.clan_members;
CREATE VIEW aoe2war_social_hd_v2.v_clan_messages WITH(security_barrier=true) AS
 SELECT id,clan_id,author_user_id,body,audience,created_at FROM public.clan_messages;
CREATE VIEW aoe2war_social_hd_v2.v_direct_conversations WITH(security_barrier=true) AS
 SELECT id,pair_key FROM public.direct_conversations;
CREATE VIEW aoe2war_social_hd_v2.v_direct_messages WITH(security_barrier=true) AS
 SELECT id,conversation_id,sender_user_id,body,reply_to_message_id,created_at
 FROM public.direct_messages;
CREATE VIEW aoe2war_social_hd_v2.v_direct_participants WITH(security_barrier=true) AS
 SELECT conversation_id,user_id FROM public.direct_conversation_participants;
ALTER VIEW aoe2war_social_hd_v2.v_users OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_clans OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_clan_members OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_clan_messages OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_direct_conversations OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_direct_messages OWNER TO aoe2hd_user;
ALTER VIEW aoe2war_social_hd_v2.v_direct_participants OWNER TO aoe2hd_user;
GRANT SELECT ON
 aoe2war_social_hd_v2.v_users,
 aoe2war_social_hd_v2.v_clans,
 aoe2war_social_hd_v2.v_clan_members,
 aoe2war_social_hd_v2.v_clan_messages,
 aoe2war_social_hd_v2.v_direct_conversations,
 aoe2war_social_hd_v2.v_direct_messages,
 aoe2war_social_hd_v2.v_direct_participants
 TO aoe2war_social_exec_v2;

-- Leaf 1: static INSERT only; inherited serial sequence access remains with
-- original owner. No user DELETE, financial DML, dynamic SQL, or SELECT leak.
CREATE FUNCTION aoe2war_social_hd_v2.leaf_append_clan(
 p_clan integer,p_actor integer,p_body text,p_audience text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE result_id integer;
BEGIN
 IF p_clan IS NULL OR p_actor IS NULL OR p_body IS NULL OR
   btrim(p_body)='' OR length(p_body)>1200 OR
   p_audience NOT IN ('clan','users','public')
 THEN RAISE EXCEPTION 'C03_DENY_CLAN_LEAF'; END IF;
 INSERT INTO public.clan_messages(clan_id,author_user_id,body,audience,created_at,updated_at)
 VALUES(p_clan,p_actor,p_body,p_audience,clock_timestamp(),clock_timestamp())
 RETURNING id INTO result_id;
 RETURN result_id;
END $leaf$;

-- Leaf 2: static pair/participant creation only, never user or finance writes.
CREATE FUNCTION aoe2war_social_hd_v2.leaf_ensure_direct_pair(
 p_actor integer,p_target integer,p_key text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE result_id integer;
BEGIN
 IF p_actor IS NULL OR p_target IS NULL OR p_actor=p_target OR
   p_key IS DISTINCT FROM least(p_actor,p_target)::text||':'||
     greatest(p_actor,p_target)::text
 THEN RAISE EXCEPTION 'C03_DENY_PAIR_LEAF'; END IF;
 INSERT INTO public.direct_conversations(pair_key,created_at,updated_at)
 VALUES(p_key,clock_timestamp(),clock_timestamp())
 ON CONFLICT(pair_key) DO NOTHING;
 SELECT id INTO result_id FROM public.direct_conversations WHERE pair_key=p_key;
 IF result_id IS NULL THEN RAISE EXCEPTION 'C03_PAIR_NOT_CREATED'; END IF;
 INSERT INTO public.direct_conversation_participants(conversation_id,user_id,joined_at)
 VALUES(result_id,p_actor,clock_timestamp()),(result_id,p_target,clock_timestamp())
 ON CONFLICT(conversation_id,user_id) DO NOTHING;
 RETURN result_id;
END $leaf$;

-- Leaf 3: one fixed message insert + receipt update + own-draft cleanup.
CREATE FUNCTION aoe2war_social_hd_v2.leaf_send_direct(
 p_conversation integer,p_actor integer,p_body text,p_reply integer
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE result_id integer;
BEGIN
 IF p_conversation IS NULL OR p_actor IS NULL OR p_body IS NULL OR
   btrim(p_body)='' OR length(p_body)>1000
 THEN RAISE EXCEPTION 'C03_DENY_DIRECT_LEAF'; END IF;
 INSERT INTO public.direct_messages(conversation_id,sender_user_id,body,
   reply_to_message_id,created_at)
 VALUES(p_conversation,p_actor,p_body,p_reply,clock_timestamp())
 RETURNING id INTO result_id;
 UPDATE public.direct_conversations SET updated_at=clock_timestamp()
  WHERE id=p_conversation;
 UPDATE public.direct_conversation_participants
  SET last_read_at=clock_timestamp(),typing_updated_at=NULL
  WHERE conversation_id=p_conversation AND user_id=p_actor;
 DELETE FROM public.direct_message_drafts
  WHERE conversation_id=p_conversation AND user_id=p_actor;
 RETURN result_id;
END $leaf$;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text)
 OWNER TO aoe2hd_user;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_ensure_direct_pair(integer,integer,text)
 OWNER TO aoe2hd_user;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_send_direct(integer,integer,text,integer)
 OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION
 aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text),
 aoe2war_social_hd_v2.leaf_ensure_direct_pair(integer,integer,text),
 aoe2war_social_hd_v2.leaf_send_direct(integer,integer,text,integer)
 FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
 aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text),
 aoe2war_social_hd_v2.leaf_ensure_direct_pair(integer,integer,text),
 aoe2war_social_hd_v2.leaf_send_direct(integer,integer,text,integer)
 TO aoe2war_social_exec_v2;

-- High-level fixed business functions follow; their effective owner is
-- restricted NOLOGIN executor, never postgres or aoe2hd_user.
CREATE FUNCTION aoe2war_social_hd_v2.clan_text(
  p_verified_uid text, p_slug text, p_body text, p_audience text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $social$
DECLARE
  v_actor record; v_clan record; v_member boolean; v_policy text;
  v_recent record; v_id integer; v_body text;
BEGIN
  v_body := btrim(replace(replace(p_body, E'\r\n', E'\n'), E'\r', E'\n'));
  IF p_verified_uid IS NULL OR p_slug IS NULL OR
     p_slug !~ '^[a-z0-9][a-z0-9_-]{0,79}$' OR
     p_audience NOT IN ('clan','users','public') OR
     v_body IS NULL OR length(v_body)=0 OR length(v_body)>1200 OR
     octet_length(v_body)>4800 THEN
    RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','INVALID_CLAN_TEXT_REQUEST'));
  END IF;
  SELECT u.id,u.is_admin,u.verification_method,u.uid INTO v_actor
  FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=p_verified_uid;
  IF NOT FOUND OR v_actor.verification_method='system' OR
     v_actor.uid ~ '^aoe2hd_ai_' OR
     v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
    RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED'));
  END IF;
  SELECT c.id,c.chat_audience_policy INTO v_clan
  FROM aoe2war_social_hd_v2.v_clans c WHERE c.slug=p_slug AND c.status='active';
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status',404,'body',jsonb_build_object('detail','CLAN_NOT_FOUND'));
  END IF;
  SELECT EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.v_clan_members m
    WHERE m.clan_id=v_clan.id AND m.user_id=v_actor.id AND m.status='active') INTO v_member;
  v_policy := CASE WHEN v_clan.chat_audience_policy IN ('clan','users','public')
                   THEN v_clan.chat_audience_policy ELSE 'public' END;
  IF (CASE p_audience WHEN 'clan' THEN 0 WHEN 'users' THEN 1 ELSE 2 END)>
     (CASE v_policy WHEN 'clan' THEN 0 WHEN 'users' THEN 1 ELSE 2 END) THEN
    RETURN jsonb_build_object('status',403,'body',jsonb_build_object('detail','CLAN_POLICY_DENIED'));
  END IF;
  IF p_audience='clan' AND NOT v_member AND NOT coalesce(v_actor.is_admin,false) THEN
    RETURN jsonb_build_object('status',403,'body',jsonb_build_object('detail','CLAN_MEMBERSHIP_REQUIRED'));
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(84912,v_actor.id::integer);
  SELECT m.id,m.body,m.audience,m.created_at INTO v_recent
  FROM aoe2war_social_hd_v2.v_clan_messages m WHERE m.clan_id=v_clan.id AND m.author_user_id=v_actor.id
  ORDER BY m.created_at DESC,m.id DESC LIMIT 1;
  IF FOUND AND clock_timestamp()-v_recent.created_at < interval '3 seconds' THEN
    IF v_recent.body=v_body AND v_recent.audience=p_audience THEN
      RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
        'ok',true,'messageId',v_recent.id,'clanSlug',p_slug,'replayed',true));
    END IF;
    RETURN jsonb_build_object('status',429,'body',jsonb_build_object('detail','CLAN_SEND_COOLDOWN'));
  END IF;
  SELECT aoe2war_social_hd_v2.leaf_append_clan(v_clan.id,v_actor.id,v_body,p_audience)
    INTO v_id;
  RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,
    'messageId',v_id,'clanSlug',p_slug));
END
$social$;

CREATE FUNCTION aoe2war_social_hd_v2.direct_text(
 p_verified_uid text,p_target_uid text,p_body text,p_reply_id integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp
AS $social$
DECLARE
  v_actor record; v_target record; v_recent record;
  v_body text; v_key text; v_conversation integer; v_id integer;
BEGIN
  v_body := btrim(replace(replace(p_body,E'\r\n',E'\n'),E'\r',E'\n'));
  IF v_body IS NULL OR length(v_body)=0 OR length(v_body)>1000 OR
     octet_length(v_body)>4000 OR (p_reply_id IS NOT NULL AND p_reply_id<=0) OR
     (p_target_uid IS NOT NULL AND
      (length(p_target_uid)>100 OR p_target_uid!~'^[A-Za-z0-9_.:-]+$')) THEN
    RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','INVALID_DIRECT_TEXT_REQUEST'));
  END IF;
  SELECT u.id,u.uid,u.verification_method,u.is_admin INTO v_actor
    FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=p_verified_uid;
  IF NOT FOUND OR v_actor.verification_method='system' OR
     v_actor.uid ~ '^aoe2hd_ai_' OR
     v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
    RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED'));
  END IF;
  IF p_target_uid IS NOT NULL THEN
    SELECT u.id,u.uid,u.verification_method INTO v_target
      FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=p_target_uid;
  ELSE
    SELECT u.id,u.uid,u.verification_method INTO v_target
      FROM aoe2war_social_hd_v2.v_users u WHERE u.is_admin=true ORDER BY
        CASE WHEN lower(coalesce(u.in_game_name,''))='emaren' OR
                  lower(coalesce(u.steam_persona_name,''))='emaren' THEN 0 ELSE 1 END,
        u.created_at,u.id LIMIT 1;
  END IF;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status',404,'body',jsonb_build_object('detail','DIRECT_RECIPIENT_NOT_FOUND'));
  END IF;
  IF v_target.id=v_actor.id THEN
    RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','CANNOT_MESSAGE_SELF'));
  END IF;
  IF v_target.verification_method='system' OR v_target.uid ~ '^aoe2hd_ai_' OR
     v_target.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
    RETURN jsonb_build_object('status',403,'body',jsonb_build_object('detail','DIRECT_HUMAN_ONLY_V1'));
  END IF;
  v_key := least(v_actor.id,v_target.id)::text||':'||greatest(v_actor.id,v_target.id)::text;
  PERFORM pg_catalog.pg_advisory_xact_lock(84913,v_actor.id::integer);
  -- All business-rule failure decisions happen BEFORE DML; unlike returning
  -- an error after creating participants, this preserves rollback semantics.
  SELECT c.id INTO v_conversation FROM aoe2war_social_hd_v2.v_direct_conversations c WHERE c.pair_key=v_key;
  IF p_reply_id IS NOT NULL AND
     (v_conversation IS NULL OR NOT EXISTS(
       SELECT 1 FROM aoe2war_social_hd_v2.v_direct_messages m WHERE m.id=p_reply_id
         AND m.conversation_id=v_conversation)) THEN
    RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','REPLY_OUTSIDE_CONVERSATION'));
  END IF;
  IF v_conversation IS NOT NULL THEN
    SELECT m.id,m.body,m.reply_to_message_id,m.created_at INTO v_recent
      FROM aoe2war_social_hd_v2.v_direct_messages m
      WHERE m.conversation_id=v_conversation AND m.sender_user_id=v_actor.id
      ORDER BY m.created_at DESC,m.id DESC LIMIT 1;
    IF FOUND AND clock_timestamp()-v_recent.created_at < interval '1 second' THEN
      IF v_recent.body=v_body AND v_recent.reply_to_message_id IS NOT DISTINCT FROM p_reply_id THEN
        RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
          'ok',true,'messageId',v_recent.id,'targetUid',v_target.uid,'replayed',true));
      END IF;
      RETURN jsonb_build_object('status',429,'body',jsonb_build_object('detail','DIRECT_SEND_COOLDOWN'));
    END IF;
  END IF;
  SELECT aoe2war_social_hd_v2.leaf_ensure_direct_pair(v_actor.id,v_target.id,v_key)
    INTO v_conversation;
  IF v_conversation IS NULL THEN
    RETURN jsonb_build_object('status',503,'body',jsonb_build_object('detail','DIRECT_CONVERSATION_UNAVAILABLE'));
  END IF;
  SELECT aoe2war_social_hd_v2.leaf_send_direct(v_conversation,v_actor.id,v_body,p_reply_id)
    INTO v_id;
  RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,
    'messageId',v_id,'targetUid',v_target.uid));
END
$social$;


-- ALTER OWNER of a function requires the receiving role to have CREATE in
-- the function schema at transfer time. Revoke before COMMIT and verify.
GRANT CREATE ON SCHEMA aoe2war_social_hd_v2 TO aoe2war_social_exec_v2;
ALTER FUNCTION aoe2war_social_hd_v2.clan_text(text,text,text,text)
 OWNER TO aoe2war_social_exec_v2;
ALTER FUNCTION aoe2war_social_hd_v2.direct_text(text,text,text,integer)
 OWNER TO aoe2war_social_exec_v2;
REVOKE CREATE ON SCHEMA aoe2war_social_hd_v2 FROM aoe2war_social_exec_v2;
REVOKE ALL ON FUNCTION
 aoe2war_social_hd_v2.clan_text(text,text,text,text),
 aoe2war_social_hd_v2.direct_text(text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
 aoe2war_social_hd_v2.clan_text(text,text,text,text),
 aoe2war_social_hd_v2.direct_text(text,text,text,integer)
 TO aoe2war_social_writer;
DO $post$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
  WHERE p.pronamespace='aoe2war_social_hd_v2'::regnamespace AND p.prosecdef
    AND (
      (p.proname IN ('clan_text','direct_text') AND r.rolname<>'aoe2war_social_exec_v2')
      OR (p.proname LIKE 'leaf_%' AND r.rolname<>'aoe2hd_user')
      OR r.rolsuper OR r.rolcanlogin
    ))
  OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member='aoe2war_social_exec_v2'::regrole)
  OR has_schema_privilege('aoe2war_social_exec_v2','aoe2war_social_hd_v2','CREATE')
  OR has_table_privilege('aoe2war_social_exec_v2','public.users','DELETE')
  OR has_table_privilege('aoe2war_social_exec_v2','public.bet_wagers','INSERT')
  OR has_table_privilege('aoe2war_social_exec_v2','public.clan_messages','INSERT')
  OR has_sequence_privilege('aoe2war_social_exec_v2','public.clan_messages_id_seq','USAGE')
  OR has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text)','EXECUTE')
 THEN RAISE EXCEPTION 'C03_HD_GATEWAY_OWNER_OR_FINANCE_CAPABILITY_DRIFT'; END IF;
END $post$;
COMMIT;
