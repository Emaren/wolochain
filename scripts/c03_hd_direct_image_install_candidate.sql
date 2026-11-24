-- Source candidate only. HD-only, separate admission required.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10s';
DO $pre$
BEGIN
 IF current_database()<>'aoe2hd_db' OR
 NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_exec_v2' AND NOT rolcanlogin AND NOT rolsuper AND NOT rolinherit AND NOT rolbypassrls) OR
 NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_writer' AND rolcanlogin AND NOT rolsuper AND NOT rolinherit AND NOT rolbypassrls) OR
 EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN ('aoe2war_social_exec_v2'::regrole,'aoe2war_social_writer'::regrole)) OR
 has_table_privilege('aoe2war_social_writer','public.direct_messages','INSERT') OR
 has_table_privilege('aoe2war_social_exec_v2','public.direct_messages','INSERT') OR
 has_table_privilege('aoe2war_social_exec_v2','public.users','DELETE') OR
 has_schema_privilege('aoe2war_social_exec_v2','aoe2war_social_hd_v2','CREATE') OR
 EXISTS(SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgenabled<>'D' AND tgrelid IN ('public.direct_messages'::regclass,'public.direct_conversations'::regclass,'public.direct_conversation_participants'::regclass,'public.direct_message_drafts'::regclass)) OR
 EXISTS(SELECT 1 FROM pg_class WHERE oid IN ('public.direct_messages'::regclass,'public.direct_conversations'::regclass,'public.direct_conversation_participants'::regclass,'public.direct_message_drafts'::regclass) AND (relowner<>'aoe2hd_user'::regrole OR relrowsecurity OR relforcerowsecurity)) OR
 EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class IN ('public.direct_messages'::regclass,'public.direct_conversations'::regclass,'public.direct_conversation_participants'::regclass,'public.direct_message_drafts'::regclass))
 THEN RAISE EXCEPTION 'MEDIA_PREIMAGE_HOLD'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid='aoe2war_social_hd_v2.direct_text(text,text,text,integer)'::regprocedure AND p.proowner='aoe2war_social_exec_v2'::regrole AND p.prosecdef AND md5(p.prosrc)='29748632792ceb09d6260bbb51900dba')
 THEN RAISE EXCEPTION 'MEDIA_TEXT_PREIMAGE_DRIFT'; END IF;
END $pre$;
-- New private replay ledger; no FK to users or financial relations, no raw writer access.
CREATE TABLE aoe2war_social_hd_v2.image_request_keys (
 actor_id integer NOT NULL, request_key text NOT NULL, target_id integer NOT NULL,
 payload_sha256 text NOT NULL, message_id integer NOT NULL, attachment_ref text NOT NULL UNIQUE,
 caption text NOT NULL, reply_id integer, attachment_name text NOT NULL, attachment_mime text NOT NULL,
 attachment_bytes integer NOT NULL CHECK(attachment_bytes BETWEEN 1 AND 10000000),
 PRIMARY KEY(actor_id,request_key), UNIQUE(message_id)
);
ALTER TABLE aoe2war_social_hd_v2.image_request_keys OWNER TO aoe2war_social_exec_v2;
REVOKE ALL ON aoe2war_social_hd_v2.image_request_keys FROM PUBLIC,aoe2war_social_writer,aoe2war_web_prod;
CREATE FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(p_conversation integer,p_actor integer,p_target integer,p_caption text,p_reply integer,p_ref text,p_name text,p_mime text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $leaf$
DECLARE v_id integer;
BEGIN
 IF p_actor=p_target OR NOT EXISTS(SELECT 1 FROM public.direct_conversations c WHERE c.id=p_conversation AND c.pair_key=least(p_actor,p_target)::text||':'||greatest(p_actor,p_target)::text)
 OR (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=p_conversation)<>2
 OR (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=p_conversation AND p.user_id IN(p_actor,p_target))<>2
 OR (p_reply IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.direct_messages m WHERE m.id=p_reply AND m.conversation_id=p_conversation))
 THEN RAISE EXCEPTION 'MEDIA_PARTICIPANT_DRIFT'; END IF;
 INSERT INTO public.direct_messages(conversation_id,sender_user_id,body,reply_to_message_id,attachment_kind,attachment_name,attachment_mime_type,attachment_data_url,created_at)
 VALUES(p_conversation,p_actor,p_caption,p_reply,'image',p_name,p_mime,p_ref,clock_timestamp()) RETURNING id INTO v_id;
 UPDATE public.direct_conversations SET updated_at=clock_timestamp() WHERE id=p_conversation;
 UPDATE public.direct_conversation_participants SET last_read_at=clock_timestamp(),typing_updated_at=NULL WHERE conversation_id=p_conversation AND user_id=p_actor;
 DELETE FROM public.direct_message_drafts WHERE conversation_id=p_conversation AND user_id=p_actor;
 RETURN v_id;
END $leaf$;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text) TO aoe2war_social_exec_v2;
CREATE FUNCTION aoe2war_social_hd_v2.direct_image(actor_uid text,target_uid text,caption text,reply_id integer,request_key text,payload_sha256 text,attachment_ref text,attachment_name text,attachment_mime text,attachment_bytes integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $media$
DECLARE a record; t record; r record; c integer; m integer; k text; ext text; status_code integer; detail text;
BEGIN
 ext:=CASE attachment_mime WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' WHEN 'image/webp' THEN 'webp' END;
 IF actor_uid IS NULL OR actor_uid !~ '^[A-Za-z0-9_.:-]{1,100}$' OR (target_uid IS NOT NULL AND target_uid !~ '^[A-Za-z0-9_.:-]{1,100}$')
 OR caption IS NULL OR length(caption)>1000 OR octet_length(caption)>4000 OR (reply_id IS NOT NULL AND reply_id<=0)
 OR request_key IS NULL OR request_key !~ '^[0-9a-f]{32}$' OR payload_sha256 IS NULL OR payload_sha256 !~ '^[0-9a-f]{64}$'
 OR ext IS NULL OR attachment_ref IS NULL OR attachment_ref !~ ('^file:v1:dm-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]'||ext||'$')
 OR attachment_name IS NULL OR length(attachment_name)>160 OR attachment_name ~ '[[:cntrl:]/]' OR strpos(attachment_name,chr(92))>0
 OR attachment_bytes IS NULL OR attachment_bytes NOT BETWEEN 1 AND 10000000
 THEN status_code:=400;detail:='INVALID_DIRECT_IMAGE_REQUEST';
 ELSE
 SELECT u.id,u.uid,u.verification_method INTO a FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=actor_uid;
 IF NOT FOUND OR a.verification_method='system' OR a.uid ~ '^aoe2hd_ai_' OR a.uid IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN
 status_code:=401;detail:='SIGNED_IN_HUMAN_REQUIRED';
 ELSE
 IF target_uid IS NULL THEN
 SELECT u.id,u.uid,u.verification_method INTO t FROM aoe2war_social_hd_v2.v_users u WHERE u.is_admin=true ORDER BY CASE WHEN lower(coalesce(u.in_game_name,''))='emaren' OR lower(coalesce(u.steam_persona_name,''))='emaren' THEN 0 ELSE 1 END,u.created_at,u.id LIMIT 1;
 ELSE SELECT u.id,u.uid,u.verification_method INTO t FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=target_uid; END IF;
 IF NOT FOUND THEN status_code:=404;detail:='DIRECT_RECIPIENT_NOT_FOUND';
 ELSIF a.id=t.id THEN status_code:=400;detail:='CANNOT_MESSAGE_SELF';
 ELSIF t.verification_method='system' OR t.uid ~ '^aoe2hd_ai_' OR t.uid IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry') THEN status_code:=403;detail:='DIRECT_HUMAN_ONLY_V1';
 ELSE
 PERFORM pg_catalog.pg_advisory_xact_lock(84913,a.id::integer);
 k:=least(a.id,t.id)::text||':'||greatest(a.id,t.id)::text;
 SELECT v.id INTO c FROM aoe2war_social_hd_v2.v_direct_conversations v WHERE v.pair_key=k;
 IF c IS NOT NULL AND ((SELECT count(*) FROM aoe2war_social_hd_v2.v_direct_participants p WHERE p.conversation_id=c)<>2 OR (SELECT count(*) FROM aoe2war_social_hd_v2.v_direct_participants p WHERE p.conversation_id=c AND p.user_id IN(a.id,t.id))<>2) THEN status_code:=403;detail:='DIRECT_PARTICIPANT_REQUIRED';
 ELSE
 SELECT q.target_id,q.payload_sha256,q.message_id,q.attachment_bytes,q.caption,q.reply_id,q.attachment_name,q.attachment_mime INTO r FROM aoe2war_social_hd_v2.image_request_keys q WHERE q.actor_id=a.id AND q.request_key=direct_image.request_key;
 IF FOUND THEN
 IF r.target_id<>t.id OR r.payload_sha256<>direct_image.payload_sha256 OR r.attachment_bytes<>direct_image.attachment_bytes OR r.caption IS DISTINCT FROM direct_image.caption OR r.reply_id IS DISTINCT FROM direct_image.reply_id OR r.attachment_name IS DISTINCT FROM direct_image.attachment_name OR r.attachment_mime IS DISTINCT FROM direct_image.attachment_mime THEN status_code:=409;detail:='MEDIA_REPLAY_CONFLICT';
 ELSIF c IS NULL OR NOT EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.v_direct_messages v WHERE v.id=r.message_id AND v.conversation_id=c AND v.sender_user_id=a.id) THEN status_code:=409;detail:='MEDIA_REPLAY_MESSAGE_UNAVAILABLE';
 ELSE RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,'messageId',r.message_id,'targetUid',t.uid,'replayed',true)); END IF;
 ELSIF reply_id IS NOT NULL AND (c IS NULL OR NOT EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.v_direct_messages v WHERE v.id=reply_id AND v.conversation_id=c)) THEN status_code:=400;detail:='REPLY_OUTSIDE_CONVERSATION';
 ELSE
 c:=aoe2war_social_hd_v2.leaf_ensure_direct_pair(a.id,t.id,k);
 m:=aoe2war_social_hd_v2.leaf_send_direct_image(c,a.id,t.id,caption,reply_id,attachment_ref,attachment_name,attachment_mime);
 INSERT INTO aoe2war_social_hd_v2.image_request_keys(actor_id,request_key,target_id,payload_sha256,message_id,attachment_ref,attachment_bytes,caption,reply_id,attachment_name,attachment_mime) VALUES(a.id,direct_image.request_key,t.id,direct_image.payload_sha256,m,direct_image.attachment_ref,direct_image.attachment_bytes,direct_image.caption,direct_image.reply_id,direct_image.attachment_name,direct_image.attachment_mime);
 RETURN jsonb_build_object('status',201,'body',jsonb_build_object('ok',true,'messageId',m,'targetUid',t.uid,'replayed',false));
 END IF;
 END IF;
 END IF;
 END IF;
 END IF;
 RETURN jsonb_build_object('status',status_code,'body',jsonb_build_object('detail',detail));
END $media$;
ALTER FUNCTION aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer) OWNER TO aoe2war_social_exec_v2;
REVOKE ALL ON FUNCTION aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer) TO aoe2war_social_writer;
-- Latest message still determines cooldown; only plain text may replay.
CREATE VIEW aoe2war_social_hd_v2.v_direct_text_ids WITH(security_barrier=true) AS
 SELECT id FROM public.direct_messages WHERE attachment_kind IS NULL AND attachment_data_url IS NULL AND shared_lobby_message_id IS NULL;
ALTER VIEW aoe2war_social_hd_v2.v_direct_text_ids OWNER TO aoe2hd_user;
REVOKE ALL ON aoe2war_social_hd_v2.v_direct_text_ids FROM PUBLIC,aoe2war_social_writer,aoe2war_web_prod;
GRANT SELECT ON aoe2war_social_hd_v2.v_direct_text_ids TO aoe2war_social_exec_v2;
CREATE OR REPLACE FUNCTION aoe2war_social_hd_v2.direct_text(
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
      IF EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.v_direct_text_ids x WHERE x.id=v_recent.id) AND v_recent.body=v_body AND v_recent.reply_to_message_id IS NOT DISTINCT FROM p_reply_id THEN
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
-- Explicit recipient acknowledgement of bounded exact message IDs.
CREATE FUNCTION aoe2war_social_hd_v2.leaf_ack_direct_delivery(p_actor integer,p_target integer,p_ids integer[])
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $delivery$
DECLARE c integer; n integer;
BEGIN
 IF p_actor IS NULL OR p_target IS NULL OR p_actor=p_target OR p_ids IS NULL OR cardinality(p_ids) NOT BETWEEN 1 AND 50
 OR array_ndims(p_ids)<>1 OR array_position(p_ids,NULL) IS NOT NULL
 OR EXISTS(SELECT 1 FROM unnest(p_ids) i WHERE i<=0)
 OR (SELECT count(DISTINCT i) FROM unnest(p_ids) i)<>cardinality(p_ids) THEN RETURN -1; END IF;
 SELECT id INTO c FROM public.direct_conversations WHERE pair_key=least(p_actor,p_target)::text||':'||greatest(p_actor,p_target)::text;
 IF c IS NULL OR (SELECT count(*) FROM public.direct_conversation_participants WHERE conversation_id=c)<>2
 OR (SELECT count(*) FROM public.direct_conversation_participants WHERE conversation_id=c AND user_id IN(p_actor,p_target))<>2 THEN RETURN -1; END IF;
 PERFORM id FROM public.direct_messages WHERE conversation_id=c AND sender_user_id=p_target AND id=ANY(p_ids) ORDER BY id FOR UPDATE;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>cardinality(p_ids) THEN RETURN -1; END IF;
 UPDATE public.direct_messages SET delivered_at=clock_timestamp() WHERE conversation_id=c AND sender_user_id=p_target AND id=ANY(p_ids) AND delivered_at IS NULL;
 GET DIAGNOSTICS n=ROW_COUNT;
 RETURN n;
END $delivery$;
ALTER FUNCTION aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[]) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[]) TO aoe2war_social_exec_v2;
CREATE FUNCTION aoe2war_social_hd_v2.direct_delivered(actor_uid text,target_uid text,message_ids integer[])
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $delivery$
DECLARE a integer; t integer; n integer;
BEGIN
 IF actor_uid IS NULL OR target_uid IS NULL OR actor_uid !~ '^[A-Za-z0-9_.:-]{1,100}$' OR target_uid !~ '^[A-Za-z0-9_.:-]{1,100}$'
 OR message_ids IS NULL OR cardinality(message_ids) NOT BETWEEN 1 AND 50
 OR array_ndims(message_ids)<>1 OR array_position(message_ids,NULL) IS NOT NULL
 OR EXISTS(SELECT 1 FROM unnest(message_ids) i WHERE i<=0)
 OR (SELECT count(DISTINCT i) FROM unnest(message_ids) i)<>cardinality(message_ids)
 THEN RETURN jsonb_build_object('status',400,'body',jsonb_build_object('detail','INVALID_DIRECT_DELIVERY_REQUEST')); END IF;
 SELECT u.id INTO a FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=actor_uid AND u.verification_method IS DISTINCT FROM 'system' AND u.uid !~ '^aoe2hd_ai_' AND u.uid NOT IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry');
 IF a IS NULL THEN RETURN jsonb_build_object('status',401,'body',jsonb_build_object('detail','SIGNED_IN_HUMAN_REQUIRED')); END IF;
 SELECT u.id INTO t FROM aoe2war_social_hd_v2.v_users u WHERE u.uid=target_uid AND u.verification_method IS DISTINCT FROM 'system' AND u.uid !~ '^aoe2hd_ai_' AND u.uid NOT IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry');
 IF t IS NULL OR a=t THEN RETURN jsonb_build_object('status',403,'body',jsonb_build_object('detail','DIRECT_DELIVERY_DENIED')); END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(84913,a);
 n:=aoe2war_social_hd_v2.leaf_ack_direct_delivery(a,t,message_ids);
 IF n<0 THEN RETURN jsonb_build_object('status',403,'body',jsonb_build_object('detail','DIRECT_DELIVERY_DENIED')); END IF;
 RETURN jsonb_build_object('status',200,'body',jsonb_build_object('ok',true,'updatedCount',n));
END $delivery$;
ALTER FUNCTION aoe2war_social_hd_v2.direct_delivered(text,text,integer[]) OWNER TO aoe2war_social_exec_v2;
REVOKE ALL ON FUNCTION aoe2war_social_hd_v2.direct_delivered(text,text,integer[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_social_hd_v2.direct_delivered(text,text,integer[]) TO aoe2war_social_writer;

DO $post$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer)'::regprocedure AND a.grantee NOT IN ('aoe2war_social_exec_v2'::regrole,'aoe2war_social_writer'::regrole))
 OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text)'::regprocedure AND a.grantee NOT IN ('aoe2hd_user'::regrole,'aoe2war_social_exec_v2'::regrole))
 OR EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='aoe2war_social_hd_v2.image_request_keys'::regclass AND a.grantee<>'aoe2war_social_exec_v2'::regrole)
 OR NOT has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer)','EXECUTE')
 OR has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text)','EXECUTE')
 OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='aoe2war_social_hd_v2.direct_delivered(text,text,integer[])'::regprocedure AND a.grantee NOT IN ('aoe2war_social_exec_v2'::regrole,'aoe2war_social_writer'::regrole))
 OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[])'::regprocedure AND a.grantee NOT IN ('aoe2hd_user'::regrole,'aoe2war_social_exec_v2'::regrole))
 OR has_table_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.v_direct_text_ids','SELECT')
 OR has_function_privilege('aoe2war_social_writer','aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[])','EXECUTE')
 OR has_schema_privilege('aoe2war_social_exec_v2','aoe2war_social_hd_v2','CREATE')
 THEN RAISE EXCEPTION 'MEDIA_POSTIMAGE_AUTHORITY_DRIFT'; END IF;
END $post$;
COMMIT;
