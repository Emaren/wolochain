-- Safe only before use; never erase replay history or media association.
BEGIN;
DO $hold$ BEGIN
 IF current_database()<>'aoe2hd_db' OR EXISTS(SELECT 1 FROM aoe2war_social_hd_v2.image_request_keys) THEN RAISE EXCEPTION 'MEDIA_INVERSE_USED_OR_WRONG_DB_HOLD'; END IF;
END $hold$;
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
DROP FUNCTION aoe2war_social_hd_v2.direct_delivered(text,text,integer[]);
DROP FUNCTION aoe2war_social_hd_v2.leaf_ack_direct_delivery(integer,integer,integer[]);
DROP VIEW aoe2war_social_hd_v2.v_direct_text_ids;
DROP FUNCTION aoe2war_social_hd_v2.direct_image(text,text,text,integer,text,text,text,text,text,integer);
DROP FUNCTION aoe2war_social_hd_v2.leaf_send_direct_image(integer,integer,integer,text,integer,text,text,text);
DROP TABLE aoe2war_social_hd_v2.image_request_keys;
COMMIT;
