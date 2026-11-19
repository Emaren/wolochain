-- WE1 C03. Fixed-purpose social gateway source candidate, NOT a live installer.
-- In a separately owner-authorized admission, replace EXACT NONFINANCIAL owner
-- token after a signed read-only HD/DE owner+trigger+PUBLIC/definer census.
-- No direct grants on any original public table or sequence.
-- A successful synthetic PG test is NEVER a production maintenance permit.
-- WE3 sidecar MUST verify HS256 session and supply only its DB-derived signed UID.
-- This separate caller->DB trust boundary is NOT resistant to stolen DB credentials.
BEGIN;
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
CREATE SCHEMA aoe2war_social_gateway AUTHORIZATION __NONFINANCIAL_OWNER__;
REVOKE ALL ON SCHEMA aoe2war_social_gateway FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_social_gateway TO aoe2war_social_writer;

-- Return {"status":<HTTP>,"body":{...}} so WE3 preserves its JSON contract.
-- No caller-provided author ID, conversation ID, table name, SQL or function name.
CREATE FUNCTION aoe2war_social_gateway.clan_text(
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
  FROM public.users u WHERE u.uid=p_verified_uid;
  IF NOT FOUND OR v_actor.verification_method='system' OR
     v_actor.uid ~ '^aoe2hd_ai_' OR
     v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
    RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED'));
  END IF;
  SELECT c.id,c.chat_audience_policy INTO v_clan
  FROM public.clans c WHERE c.slug=p_slug AND c.status='active';
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status',404,'body',jsonb_build_object('detail','CLAN_NOT_FOUND'));
  END IF;
  SELECT EXISTS(SELECT 1 FROM public.clan_members m
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
  FROM public.clan_messages m WHERE m.clan_id=v_clan.id AND m.author_user_id=v_actor.id
  ORDER BY m.created_at DESC,m.id DESC LIMIT 1;
  IF FOUND AND clock_timestamp()-v_recent.created_at < interval '3 seconds' THEN
    IF v_recent.body=v_body AND v_recent.audience=p_audience THEN
      RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
        'ok',true,'messageId',v_recent.id,'clanSlug',p_slug,'replayed',true));
    END IF;
    RETURN jsonb_build_object('status',429,'body',jsonb_build_object('detail','CLAN_SEND_COOLDOWN'));
  END IF;
  INSERT INTO public.clan_messages(clan_id,author_user_id,body,audience,created_at,updated_at)
  VALUES(v_clan.id,v_actor.id,v_body,p_audience,clock_timestamp(),clock_timestamp())
  RETURNING id INTO v_id;
  RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,
    'messageId',v_id,'clanSlug',p_slug));
END
$social$;

CREATE FUNCTION aoe2war_social_gateway.direct_text(
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
    FROM public.users u WHERE u.uid=p_verified_uid;
  IF NOT FOUND OR v_actor.verification_method='system' OR
     v_actor.uid ~ '^aoe2hd_ai_' OR
     v_actor.uid IN ('aoe2hd-moose','challenge-protocol',
       'aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie',
       'aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
    RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED'));
  END IF;
  IF p_target_uid IS NOT NULL THEN
    SELECT u.id,u.uid,u.verification_method INTO v_target
      FROM public.users u WHERE u.uid=p_target_uid;
  ELSE
    SELECT u.id,u.uid,u.verification_method INTO v_target
      FROM public.users u WHERE u.is_admin=true ORDER BY
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
  INSERT INTO public.direct_conversations(pair_key,created_at,updated_at)
    VALUES(v_key,clock_timestamp(),clock_timestamp()) ON CONFLICT(pair_key) DO NOTHING;
  SELECT c.id INTO v_conversation FROM public.direct_conversations c WHERE c.pair_key=v_key;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status',503,'body',jsonb_build_object('detail','DIRECT_CONVERSATION_UNAVAILABLE'));
  END IF;
  INSERT INTO public.direct_conversation_participants(conversation_id,user_id,joined_at)
    VALUES(v_conversation,v_actor.id,clock_timestamp()),
          (v_conversation,v_target.id,clock_timestamp())
    ON CONFLICT(conversation_id,user_id) DO NOTHING;
  IF p_reply_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM public.direct_messages m WHERE m.id=p_reply_id
      AND m.conversation_id=v_conversation) THEN
    RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','REPLY_OUTSIDE_CONVERSATION'));
  END IF;
  SELECT m.id,m.body,m.reply_to_message_id,m.created_at INTO v_recent
    FROM public.direct_messages m
    WHERE m.conversation_id=v_conversation AND m.sender_user_id=v_actor.id
    ORDER BY m.created_at DESC,m.id DESC LIMIT 1;
  IF FOUND AND clock_timestamp()-v_recent.created_at < interval '1 second' THEN
    IF v_recent.body=v_body AND v_recent.reply_to_message_id IS NOT DISTINCT FROM p_reply_id THEN
      RETURN jsonb_build_object('status',201,'body',jsonb_build_object(
        'ok',true,'messageId',v_recent.id,'targetUid',v_target.uid,'replayed',true));
    END IF;
    RETURN jsonb_build_object('status',429,'body',jsonb_build_object('detail','DIRECT_SEND_COOLDOWN'));
  END IF;
  INSERT INTO public.direct_messages(conversation_id,sender_user_id,body,
      reply_to_message_id,created_at)
    VALUES(v_conversation,v_actor.id,v_body,p_reply_id,clock_timestamp())
    RETURNING id INTO v_id;
  UPDATE public.direct_conversations SET updated_at=clock_timestamp()
    WHERE id=v_conversation;
  UPDATE public.direct_conversation_participants
    SET last_read_at=clock_timestamp(),typing_updated_at=NULL
    WHERE conversation_id=v_conversation AND user_id=v_actor.id;
  DELETE FROM public.direct_message_drafts
    WHERE conversation_id=v_conversation AND user_id=v_actor.id;
  RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,
    'messageId',v_id,'targetUid',v_target.uid));
END
$social$;

-- Must be the actual, verified NONFINANCIAL owner of all touched relations.
ALTER FUNCTION aoe2war_social_gateway.clan_text(text,text,text,text)
  OWNER TO __NONFINANCIAL_OWNER__;
ALTER FUNCTION aoe2war_social_gateway.direct_text(text,text,text,integer)
  OWNER TO __NONFINANCIAL_OWNER__;
REVOKE ALL ON FUNCTION aoe2war_social_gateway.clan_text(text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION aoe2war_social_gateway.direct_text(text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_gateway.clan_text(text,text,text,text) TO aoe2war_social_writer;
GRANT EXECUTE ON FUNCTION aoe2war_social_gateway.direct_text(text,text,text,integer) TO aoe2war_social_writer;
COMMIT;
