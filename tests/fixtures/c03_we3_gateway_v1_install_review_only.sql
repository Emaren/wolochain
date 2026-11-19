-- SOURCE-EXACT immutable WE3 PR #1418 head 48dcf1103562e629ffb4b123feb83e9f1bafa185
-- SOURCE REVIEW DOC Git blob 6535da9c8fe7aee8b567e9475ab96619e23634bc
-- DISPOSABLE PG16 ONLY. NOT AN INSTALLER OR FINANCIAL SQL AUTHORIZATION.
BEGIN;
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
-- Root/WE2 later provisions approved local HBA/SCRAM only; no password here.
CREATE SCHEMA social_gateway_v1;
CREATE VIEW social_gateway_v1.users WITH (security_barrier=true) AS
  SELECT id,uid,is_admin,verification_method,in_game_name,steam_persona_name,created_at
  FROM public.users;
CREATE VIEW social_gateway_v1.clans WITH (security_barrier=true) AS
  SELECT id,slug,status,chat_audience_policy FROM public.clans;
CREATE VIEW social_gateway_v1.clan_members WITH (security_barrier=true) AS
  SELECT clan_id,user_id,status,role FROM public.clan_members;
CREATE VIEW social_gateway_v1.clan_messages WITH (security_barrier=true) AS
  SELECT id,clan_id,author_user_id,body,audience,created_at
  FROM public.clan_messages;
CREATE VIEW social_gateway_v1.direct_messages WITH (security_barrier=true) AS
  SELECT id,conversation_id,sender_user_id,body,reply_to_message_id,created_at
  FROM public.direct_messages;

CREATE FUNCTION social_gateway_v1.append_clan_message(
  p_clan_id integer,p_author integer,p_body text,p_audience text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $f$
DECLARE new_id integer;
BEGIN
  IF p_body IS NULL OR btrim(p_body)='' OR char_length(p_body)>1200
     OR p_audience NOT IN ('clan','users','public') THEN
    RAISE EXCEPTION 'INVALID_CLAN_TEXT' USING ERRCODE='22023';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.users
     WHERE id=p_author AND verification_method IS DISTINCT FROM 'system')
     OR NOT EXISTS (SELECT 1 FROM public.clans
     WHERE id=p_clan_id AND status='active') THEN
    RAISE EXCEPTION 'INVALID_CLAN_IDENTITY' USING ERRCODE='22023';
  END IF;
  IF EXISTS(
    SELECT 1 FROM public.clans c WHERE c.id=p_clan_id
    AND (
      CASE p_audience WHEN 'clan' THEN 0
         WHEN 'users' THEN 1 ELSE 2 END
    ) > (
      CASE c.chat_audience_policy WHEN 'clan' THEN 0
         WHEN 'users' THEN 1 ELSE 2 END
    )
  ) THEN
    RAISE EXCEPTION 'CLAN_POLICY_DENIED' USING ERRCODE='42501';
  END IF;
  IF p_audience='clan' AND NOT EXISTS(
    SELECT 1 FROM public.clan_members
    WHERE clan_id=p_clan_id AND user_id=p_author AND status='active'
  ) AND NOT EXISTS (SELECT 1 FROM public.users
                    WHERE id=p_author AND is_admin=true) THEN
    RAISE EXCEPTION 'CLAN_MEMBERSHIP_REQUIRED' USING ERRCODE='42501';
  END IF;
  INSERT INTO public.clan_messages(
    clan_id,author_user_id,body,audience,created_at,updated_at)
    VALUES (p_clan_id,p_author,p_body,p_audience,clock_timestamp(),clock_timestamp())
    RETURNING id INTO new_id;
  RETURN new_id;
END $f$;

CREATE FUNCTION social_gateway_v1.ensure_direct_pair(
  p_actor integer,p_target integer
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $f$
DECLARE key text; row_id integer;
BEGIN
  IF p_actor IS NULL OR p_target IS NULL OR p_actor=p_target
    OR NOT EXISTS(SELECT 1 FROM public.users
       WHERE id=p_actor AND verification_method IS DISTINCT FROM 'system')
    OR NOT EXISTS(SELECT 1 FROM public.users
       WHERE id=p_target AND verification_method IS DISTINCT FROM 'system') THEN
    RAISE EXCEPTION 'INVALID_DIRECT_PAIR' USING ERRCODE='22023';
  END IF;
  key=least(p_actor,p_target)::text || ':' || greatest(p_actor,p_target)::text;
  INSERT INTO public.direct_conversations(pair_key,created_at,updated_at)
     VALUES(key,clock_timestamp(),clock_timestamp())
     ON CONFLICT(pair_key) DO NOTHING;
  SELECT id INTO row_id FROM public.direct_conversations WHERE pair_key=key;
  IF row_id IS NULL THEN
    RAISE EXCEPTION 'DIRECT_PAIR_UNAVAILABLE' USING ERRCODE='55000';
  END IF;
  INSERT INTO public.direct_conversation_participants(
     conversation_id,user_id,joined_at)
     VALUES(row_id,p_actor,clock_timestamp()),(row_id,p_target,clock_timestamp())
     ON CONFLICT(conversation_id,user_id) DO NOTHING;
  RETURN row_id;
END $f$;

CREATE FUNCTION social_gateway_v1.send_direct_text(
  p_conversation integer,p_sender integer,p_body text,p_reply integer
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $f$
DECLARE new_id integer;
BEGIN
  IF p_conversation IS NULL OR p_sender IS NULL OR p_body IS NULL
     OR btrim(p_body)='' OR char_length(p_body)>1000
     OR NOT EXISTS(SELECT 1 FROM public.direct_conversation_participants
      WHERE conversation_id=p_conversation AND user_id=p_sender) THEN
    RAISE EXCEPTION 'INVALID_DIRECT_SEND' USING ERRCODE='22023';
  END IF;
  IF p_reply IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM public.direct_messages
    WHERE id=p_reply AND conversation_id=p_conversation
  ) THEN
    RAISE EXCEPTION 'REPLY_OUTSIDE_CONVERSATION' USING ERRCODE='22023';
  END IF;
  INSERT INTO public.direct_messages(
     conversation_id,sender_user_id,body,reply_to_message_id,created_at)
     VALUES(p_conversation,p_sender,p_body,p_reply,clock_timestamp())
     RETURNING id INTO new_id;
  UPDATE public.direct_conversations SET updated_at=clock_timestamp()
    WHERE id=p_conversation;
  UPDATE public.direct_conversation_participants
    SET last_read_at=clock_timestamp(),typing_updated_at=NULL
    WHERE conversation_id=p_conversation AND user_id=p_sender;
  DELETE FROM public.direct_message_drafts
    WHERE conversation_id=p_conversation AND user_id=p_sender;
  RETURN new_id;
END $f$;

-- PUBLIC has default function EXECUTE until explicitly revoked.
-- Do both before this transaction is committed, fail on drift.
REVOKE ALL ON FUNCTION
  social_gateway_v1.append_clan_message(integer,integer,text,text),
  social_gateway_v1.ensure_direct_pair(integer,integer),
  social_gateway_v1.send_direct_text(integer,integer,text,integer)
  FROM PUBLIC;
GRANT USAGE ON SCHEMA social_gateway_v1 TO aoe2war_social_writer;
GRANT SELECT ON social_gateway_v1.users,
  social_gateway_v1.clans,social_gateway_v1.clan_members,
  social_gateway_v1.clan_messages,social_gateway_v1.direct_messages
  TO aoe2war_social_writer;
GRANT EXECUTE ON FUNCTION
  social_gateway_v1.append_clan_message(integer,integer,text,text),
  social_gateway_v1.ensure_direct_pair(integer,integer),
  social_gateway_v1.send_direct_text(integer,integer,text,integer)
  TO aoe2war_social_writer;
-- Independently compare all legacy raw ACL/attacl/proacl and trigger graphs
-- with the signed preimage. No unexpected rights, side effects or owner drift.
-- Otherwise ROLLBACK. Never accept a partial footprint.
COMMIT;
