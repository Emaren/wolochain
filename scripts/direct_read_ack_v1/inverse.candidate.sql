-- Isolated fixture inverse candidate only. Preserve read receipts; no DROP or DELETE.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10s';
REVOKE EXECUTE ON FUNCTION aoe2war_direct_ack_hd_v1.direct_read_ack(text,text,integer[]) FROM aoe2war_social_writer;
CREATE OR REPLACE FUNCTION aoe2war_direct_read_hd_v1.read_direct(
 p_actor text,p_op text,p_target text,p_before integer,p_query text,p_message integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $fn$
DECLARE a integer; t integer; c integer; result jsonb;
BEGIN
 IF p_actor IS NULL OR p_actor !~ '^[A-Za-z0-9_.:-]{1,100}$' OR p_op IS NULL OR
 p_op NOT IN ('summary','history','sync','search','attachment') THEN RETURN NULL; END IF;
 IF p_op='summary' THEN
  IF p_target IS NOT NULL OR p_before IS NOT NULL OR p_query IS NOT NULL OR p_message IS NOT NULL THEN RETURN NULL; END IF;
 ELSE
  IF (p_op='attachment' AND p_target IS NOT NULL) OR (p_op<>'attachment' AND (p_target IS NULL OR p_target !~ '^[A-Za-z0-9_.:-]{1,100}$' OR p_target=p_actor)) THEN RETURN NULL; END IF;
  IF (p_op<>'history' AND p_before IS NOT NULL) OR (p_before IS NOT NULL AND p_before<=0)
  OR (p_op<>'search' AND p_query IS NOT NULL) OR
  (p_op='search' AND (p_query IS NULL OR char_length(p_query) NOT BETWEEN 2 AND 120))
  OR (p_op<>'attachment' AND p_message IS NOT NULL) OR
  (p_op='attachment' AND (p_message IS NULL OR p_message<=0)) THEN RETURN NULL; END IF;
 END IF;
 SELECT u.id INTO a FROM public.users u WHERE u.uid=p_actor AND u.verification_method IS DISTINCT FROM 'system';
 IF a IS NULL THEN RETURN NULL; END IF;
 IF p_op='summary' THEN
  -- Only canonical exact two-member pairs; no arbitrary user enumeration.
  WITH pairs AS (
   SELECT d.id cid, other.id tid,other.uid,coalesce(nullif(other.in_game_name,''),nullif(other.steam_persona_name,''),other.uid) display_name,
   other.is_admin,me.last_read_at,d.updated_at
   FROM public.direct_conversation_participants me
   JOIN public.direct_conversations d ON d.id=me.conversation_id
   JOIN public.direct_conversation_participants them ON them.conversation_id=d.id AND them.user_id<>a
   JOIN public.users other ON other.id=them.user_id
   WHERE me.user_id=a AND d.pair_key=least(a,other.id)::text||':'||greatest(a,other.id)::text
   AND (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=d.id)=2
   ORDER BY d.updated_at DESC,d.id DESC LIMIT 101
  ), page AS (SELECT * FROM pairs ORDER BY updated_at DESC,cid DESC LIMIT 100)
  SELECT jsonb_build_object('threads',coalesce(jsonb_agg(jsonb_build_object(
    'targetUid',p.uid,'displayName',p.display_name,'isAdmin',p.is_admin,
    'lastMessageAt',last.created_at AT TIME ZONE 'UTC','lastMessageSnippet',left(coalesce(nullif(last.body,''),CASE WHEN last.attachment_kind IS NOT NULL THEN 'Attachment' END),160),
    'unreadCount',(SELECT count(*) FROM public.direct_messages m WHERE m.conversation_id=p.cid AND m.sender_user_id=p.tid AND (p.last_read_at IS NULL OR m.created_at>p.last_read_at))
   ) ORDER BY p.updated_at DESC,p.cid DESC),'[]'::jsonb),'hasMore',(SELECT count(*)>100 FROM pairs))
   INTO result FROM page p LEFT JOIN LATERAL (
    SELECT m.body,m.attachment_kind,m.created_at FROM public.direct_messages m
    WHERE m.conversation_id=p.cid AND m.sender_user_id IN(a,p.tid) ORDER BY m.id DESC LIMIT 1
   ) last ON true;
  RETURN jsonb_build_object('viewer', (SELECT jsonb_build_object('uid',u.uid,'displayName',coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid),'isAdmin',u.is_admin) FROM public.users u WHERE u.id=a),'summary',result,'defaultContact',(SELECT u.uid FROM public.users u WHERE u.id<>a AND u.is_admin AND u.verification_method IS DISTINCT FROM 'system' AND u.uid !~ '^aoe2hd_ai_' ORDER BY (lower(coalesce(u.in_game_name,''))='emaren' OR lower(coalesce(u.steam_persona_name,''))='emaren') DESC,u.id LIMIT 1));
 END IF;
 IF p_op='attachment' THEN
  -- The existing attachment URL carries only the message ID. Resolve the
  -- counterpart from the exact pair, never from a browser actor assertion.
  SELECT them.user_id INTO t FROM public.direct_messages m
  JOIN public.direct_conversation_participants me ON me.conversation_id=m.conversation_id AND me.user_id=a
  JOIN public.direct_conversation_participants them ON them.conversation_id=m.conversation_id AND them.user_id<>a
  WHERE m.id=p_message AND (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=m.conversation_id)=2;
 ELSE
  SELECT u.id INTO t FROM public.users u WHERE u.uid=p_target;
 END IF;
 IF t IS NULL OR t=a THEN RETURN NULL; END IF;
 SELECT d.id INTO c FROM public.direct_conversations d
 WHERE d.pair_key=least(a,t)::text||':'||greatest(a,t)::text
 AND EXISTS(SELECT 1 FROM public.direct_conversation_participants p WHERE p.conversation_id=d.id AND p.user_id=a)
 AND EXISTS(SELECT 1 FROM public.direct_conversation_participants p WHERE p.conversation_id=d.id AND p.user_id=t)
 AND (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=d.id)=2;
 IF c IS NULL THEN
  -- No conversation exists yet: permit only a known non-system counterpart
  -- to open an empty thread; malformed existing pair remains denied.
  IF p_op='history' AND p_before IS NULL AND NOT EXISTS(
    SELECT 1 FROM public.direct_conversations d WHERE d.pair_key=least(a,t)::text||':'||greatest(a,t)::text)
  THEN
   RETURN (SELECT jsonb_build_object('conversationId',NULL,'counterpart',jsonb_build_object('uid',u.uid,'displayName',coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid),'isAdmin',u.is_admin),'messages','[]'::jsonb,'hasMore',false,'beforeMessageId',NULL)
    FROM public.users u WHERE u.id=t AND u.verification_method IS DISTINCT FROM 'system'
    AND u.uid !~ '^aoe2hd_ai_' AND u.uid NOT IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry'));
  END IF;
  RETURN NULL;
 END IF;
 IF p_op='sync' THEN
  SELECT jsonb_build_object('conversationId',c,'rows',coalesce(jsonb_agg(jsonb_build_object('id',m.id,'deliveredAt',m.delivered_at AT TIME ZONE 'UTC','editedAt',m.edited_at AT TIME ZONE 'UTC') ORDER BY m.id DESC),'[]'::jsonb)) INTO result
  FROM (SELECT id,delivered_at,edited_at FROM public.direct_messages WHERE conversation_id=c AND sender_user_id IN(a,t) ORDER BY id DESC LIMIT 80) m;
 ELSIF p_op='search' THEN
  SELECT jsonb_build_object('results',coalesce(jsonb_agg(jsonb_build_object('messageId',m.id,'body',left(coalesce(nullif(m.body,''),m.transcription,'Message'),4000),'createdAt',m.created_at AT TIME ZONE 'UTC','senderName',coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid)) ORDER BY m.created_at DESC,m.id DESC),'[]'::jsonb)) INTO result
  FROM (SELECT id,sender_user_id,body,transcription,created_at FROM public.direct_messages
   WHERE conversation_id=c AND sender_user_id IN(a,t) AND
   (strpos(lower(coalesce(body,'')),lower(p_query))>0 OR strpos(lower(coalesce(transcription,'')),lower(p_query))>0)
   ORDER BY created_at DESC,id DESC LIMIT 40) m JOIN public.users u ON u.id=m.sender_user_id;
 ELSIF p_op='attachment' THEN
  -- Only the exact private reference format introduced by the admitted image writer.
  SELECT jsonb_build_object('messageId',m.id,'storageRef',m.attachment_data_url,'mimeType',m.attachment_mime_type,'name',left(m.attachment_name,255)) INTO result
  FROM public.direct_messages m WHERE m.id=p_message AND m.conversation_id=c AND m.sender_user_id IN(a,t)
  AND m.attachment_kind='image' AND m.attachment_mime_type IN ('image/png','image/jpeg','image/webp')
  AND m.attachment_data_url ~ ('^file:v1:dm-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]'||CASE m.attachment_mime_type WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$');
 ELSE
  WITH batch AS (
   SELECT m.id,m.sender_user_id,m.body,m.created_at,m.delivered_at,m.edited_at,m.reply_to_message_id,m.attachment_kind,m.attachment_name,m.attachment_mime_type,m.attachment_data_url
   FROM public.direct_messages m WHERE m.conversation_id=c AND m.sender_user_id IN(a,t) AND (p_before IS NULL OR m.id<p_before)
   ORDER BY m.id DESC LIMIT 81
  ), page AS (SELECT * FROM batch ORDER BY id DESC LIMIT 80)
  SELECT jsonb_build_object('conversationId',c,'counterpart',(SELECT jsonb_build_object('uid',u.uid,'displayName',coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid),'isAdmin',u.is_admin) FROM public.users u WHERE u.id=t),'messages',coalesce(jsonb_agg(jsonb_build_object(
   'messageId',m.id,'senderUid',u.uid,'senderName',coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid),'senderIsAdmin',u.is_admin,
   'body',left(coalesce(m.body,''),4000),'bodyTruncated',char_length(coalesce(m.body,''))>4000,
   'createdAt',m.created_at AT TIME ZONE 'UTC','deliveredAt',m.delivered_at AT TIME ZONE 'UTC','editedAt',m.edited_at AT TIME ZONE 'UTC',
   'replyToMessageId',CASE WHEN reply.id IS NOT NULL THEN reply.id END,
   'attachment',CASE WHEN m.attachment_kind='image' AND m.attachment_mime_type IN ('image/png','image/jpeg','image/webp')
   AND m.attachment_data_url ~ ('^file:v1:dm-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]'||CASE m.attachment_mime_type WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$')
   THEN jsonb_build_object('kind','image','name',left(m.attachment_name,255),'mimeType',m.attachment_mime_type) END,
   'unsupportedAttachment',m.attachment_kind IS NOT NULL AND NOT coalesce(m.attachment_kind='image' AND m.attachment_mime_type IN ('image/png','image/jpeg','image/webp') AND m.attachment_data_url ~ ('^file:v1:dm-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]'||CASE m.attachment_mime_type WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$'),false)
   ) ORDER BY m.id ASC),'[]'::jsonb),'hasMore',(SELECT count(*)>80 FROM batch),
   'beforeMessageId',CASE WHEN (SELECT count(*)>80 FROM batch) THEN min(m.id) END)
   INTO result FROM page m JOIN public.users u ON u.id=m.sender_user_id
   LEFT JOIN public.direct_messages reply ON reply.id=m.reply_to_message_id AND reply.conversation_id=c AND reply.sender_user_id IN(a,t);
 END IF;
 RETURN result;
END $fn$;
COMMIT;
