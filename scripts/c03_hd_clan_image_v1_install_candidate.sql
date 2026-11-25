-- SOURCE CANDIDATE ONLY. Separate HD member-only single-image capability.
-- Requires independently admitted exact production catalog, writer, storage and inverse.
-- Existing Social V2 functions, grants and data are not reinstalled or altered.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10s';
DO $pre$
BEGIN
 IF current_database()<>'aoe2hd_db' OR
 NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_writer' AND rolcanlogin AND NOT rolsuper AND NOT rolinherit AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication) OR
 NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2hd_user' AND NOT rolsuper) OR
 EXISTS(SELECT 1 FROM pg_auth_members WHERE member='aoe2war_social_writer'::regrole) OR
 to_regprocedure('aoe2war_social_hd_v2.clan_text(text,text,text,text)') IS NULL OR
 EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='aoe2war_clan_image_hd_v1') OR
 EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_clan_image_exec_v1')
 THEN RAISE EXCEPTION 'CLAN_IMAGE_PREIMAGE_HOLD'; END IF;
 IF (SELECT count(*) FROM pg_class WHERE oid IN ('public.users'::regclass,'public.clans'::regclass,'public.clan_members'::regclass,'public.clan_messages'::regclass,'public.clan_message_attachments'::regclass) AND relowner='aoe2hd_user'::regrole AND relkind='r' AND NOT relrowsecurity AND NOT relforcerowsecurity)<>5 OR
 EXISTS(SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgenabled<>'D' AND tgrelid IN ('public.clan_messages'::regclass,'public.clan_message_attachments'::regclass)) OR
 EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class IN ('public.clan_messages'::regclass,'public.clan_message_attachments'::regclass)) OR
 EXISTS(SELECT 1 FROM pg_class c WHERE c.oid IN ('public.users'::regclass,'public.clans'::regclass,'public.clan_members'::regclass,'public.clan_messages'::regclass,'public.clan_message_attachments'::regclass) AND (has_table_privilege('aoe2war_social_writer',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE') OR has_any_column_privilege('aoe2war_social_writer',c.oid,'INSERT,UPDATE')))
 THEN RAISE EXCEPTION 'CLAN_IMAGE_OBJECT_DRIFT'; END IF;
END $pre$;
CREATE ROLE aoe2war_clan_image_exec_v1 NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA aoe2war_clan_image_hd_v1;
REVOKE ALL ON SCHEMA aoe2war_clan_image_hd_v1 FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_clan_image_hd_v1 TO aoe2war_clan_image_exec_v1,aoe2war_social_writer,aoe2hd_user;
CREATE TABLE aoe2war_clan_image_hd_v1.request_keys(
 actor_id integer NOT NULL, request_key text NOT NULL, clan_id integer NOT NULL,
 payload_sha256 text NOT NULL, attachment_ref text NOT NULL UNIQUE, attachment_name text NOT NULL,
 attachment_mime text NOT NULL, attachment_bytes integer NOT NULL CHECK(attachment_bytes BETWEEN 1 AND 10000000),
 message_id integer NOT NULL UNIQUE, attachment_id integer NOT NULL UNIQUE,
 PRIMARY KEY(actor_id,request_key)
);
ALTER TABLE aoe2war_clan_image_hd_v1.request_keys OWNER TO aoe2war_clan_image_exec_v1;
REVOKE ALL ON aoe2war_clan_image_hd_v1.request_keys FROM PUBLIC,aoe2war_social_writer;
-- The legacy owner runs only fixed SQL. No arbitrary actor input is accepted
-- from a browser: signed-session sidecar must derive p_uid server-side.
CREATE FUNCTION aoe2war_clan_image_hd_v1.leaf_scope(p_uid text,p_slug text)
RETURNS TABLE(actor_id integer,clan_id integer) LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $fn$
 SELECT u.id,c.id FROM public.users u JOIN public.clan_members m ON m.user_id=u.id
 JOIN public.clans c ON c.id=m.clan_id
 WHERE u.uid=p_uid AND u.verification_method IS DISTINCT FROM 'system'
 AND u.uid !~ '^aoe2hd_ai_' AND u.uid NOT IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry')
 AND c.slug=p_slug AND c.status='active' AND c.chat_audience_policy IN ('clan','users','public') AND m.status='active'
 FOR SHARE OF u,c,m
$fn$;
ALTER FUNCTION aoe2war_clan_image_hd_v1.leaf_scope(text,text) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_clan_image_hd_v1.leaf_scope(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_image_hd_v1.leaf_scope(text,text) TO aoe2war_clan_image_exec_v1;
CREATE FUNCTION aoe2war_clan_image_hd_v1.leaf_append(p_uid text,p_slug text,p_ref text,p_name text,p_mime text,p_bytes integer)
RETURNS TABLE(message_id integer,attachment_id integer) LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $fn$
DECLARE s record; mid integer; aid integer;
BEGIN
 SELECT * INTO s FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug);
 IF NOT FOUND THEN RAISE EXCEPTION 'CLAN_IMAGE_MEMBER_REQUIRED'; END IF;
 IF p_mime IS NULL OR p_mime NOT IN ('image/png','image/jpeg','image/webp') OR p_ref IS NULL OR
 p_ref !~ ('^file:v1:clan-[0-9a-f]{32}[.]'||CASE p_mime WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$') OR
 p_name IS NULL OR length(p_name) NOT BETWEEN 1 AND 160 OR p_name ~ '[[:cntrl:]/]' OR strpos(p_name,chr(92))>0 OR p_bytes IS NULL OR p_bytes NOT BETWEEN 1 AND 10000000
 THEN RAISE EXCEPTION 'CLAN_IMAGE_INVALID_LEAF'; END IF;
 -- Shared actor lock with installed clan_text. Empty image-only body cannot
 -- collide with nonempty text replay. Do not add captions without dedup review.
 PERFORM pg_advisory_xact_lock(84912,s.actor_id);
 IF EXISTS(SELECT 1 FROM public.clan_messages m WHERE m.clan_id=s.clan_id AND m.author_user_id=s.actor_id AND clock_timestamp()-m.created_at<interval '3 seconds')
 THEN RETURN; END IF;
 INSERT INTO public.clan_messages(clan_id,author_user_id,body,audience,created_at,updated_at)
 VALUES(s.clan_id,s.actor_id,'','clan',clock_timestamp(),clock_timestamp()) RETURNING id INTO mid;
 INSERT INTO public.clan_message_attachments(message_id,kind,name,mime_type,storage_ref,size_bytes,created_at)
 VALUES(mid,'image',p_name,p_mime,p_ref,p_bytes,clock_timestamp()) RETURNING id INTO aid;
 RETURN QUERY SELECT mid,aid;
END $fn$;
ALTER FUNCTION aoe2war_clan_image_hd_v1.leaf_append(text,text,text,text,text,integer) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_clan_image_hd_v1.leaf_append(text,text,text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_image_hd_v1.leaf_append(text,text,text,text,text,integer) TO aoe2war_clan_image_exec_v1;
CREATE FUNCTION aoe2war_clan_image_hd_v1.leaf_read(p_uid text,p_slug text,p_mid integer,p_aid integer,p_ref text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $fn$
 SELECT jsonb_build_object('storageRef',a.storage_ref,'mimeType',a.mime_type,'name',a.name,'sizeBytes',a.size_bytes)
 FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug) s JOIN public.clan_messages m ON m.clan_id=s.clan_id
 JOIN public.clan_message_attachments a ON a.message_id=m.id
 WHERE m.id=p_mid AND m.audience='clan' AND a.id=p_aid AND a.kind='image' AND a.storage_ref=p_ref
$fn$;
ALTER FUNCTION aoe2war_clan_image_hd_v1.leaf_read(text,text,integer,integer,text) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_clan_image_hd_v1.leaf_read(text,text,integer,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_image_hd_v1.leaf_read(text,text,integer,integer,text) TO aoe2war_clan_image_exec_v1;
CREATE FUNCTION aoe2war_clan_image_hd_v1.post_image(p_uid text,p_slug text,p_key text,p_digest text,p_ref text,p_name text,p_mime text,p_bytes integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $fn$
DECLARE s record; r record; n record;
BEGIN
 IF p_uid IS NULL OR p_uid !~ '^[A-Za-z0-9_.:-]{1,100}$' OR p_slug IS NULL OR p_slug !~ '^[a-z0-9][a-z0-9_-]{0,79}$' OR
 p_key IS NULL OR p_key !~ '^[0-9a-f]{32}$' OR p_digest IS NULL OR p_digest !~ '^[0-9a-f]{64}$' OR
 p_mime IS NULL OR p_mime NOT IN ('image/png','image/jpeg','image/webp') OR p_ref IS NULL OR
 p_ref !~ ('^file:v1:clan-[0-9a-f]{32}[.]'||CASE p_mime WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$') OR
 p_name IS NULL OR length(p_name) NOT BETWEEN 1 AND 160 OR p_name ~ '[[:cntrl:]/]' OR strpos(p_name,chr(92))>0 OR p_bytes IS NULL OR p_bytes NOT BETWEEN 1 AND 10000000
 THEN RETURN jsonb_build_object('status',400,'detail','INVALID_CLAN_IMAGE'); END IF;
 SELECT * INTO s FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug);
 IF NOT FOUND THEN RETURN jsonb_build_object('status',403,'detail','CLAN_MEMBERSHIP_REQUIRED'); END IF;
 PERFORM pg_advisory_xact_lock(84912,s.actor_id);
 SELECT * INTO r FROM aoe2war_clan_image_hd_v1.request_keys k WHERE k.actor_id=s.actor_id AND k.request_key=p_key;
 IF FOUND THEN
 IF r.clan_id<>s.clan_id OR r.payload_sha256<>p_digest OR r.attachment_name<>p_name OR r.attachment_mime<>p_mime OR r.attachment_bytes<>p_bytes
 OR aoe2war_clan_image_hd_v1.leaf_read(p_uid,p_slug,r.message_id,r.attachment_id,r.attachment_ref) IS NULL
 THEN RETURN jsonb_build_object('status',409,'detail','CLAN_IMAGE_REPLAY_CONFLICT'); END IF;
 RETURN jsonb_build_object('status',201,'messageId',r.message_id,'attachmentId',r.attachment_id,'replayed',true);
 END IF;
 SELECT * INTO n FROM aoe2war_clan_image_hd_v1.leaf_append(p_uid,p_slug,p_ref,p_name,p_mime,p_bytes);
 IF NOT FOUND THEN RETURN jsonb_build_object('status',429,'detail','CLAN_SEND_COOLDOWN'); END IF;
 INSERT INTO aoe2war_clan_image_hd_v1.request_keys VALUES(s.actor_id,p_key,s.clan_id,p_digest,p_ref,p_name,p_mime,p_bytes,n.message_id,n.attachment_id);
 RETURN jsonb_build_object('status',201,'messageId',n.message_id,'attachmentId',n.attachment_id,'replayed',false);
END $fn$;
ALTER FUNCTION aoe2war_clan_image_hd_v1.post_image(text,text,text,text,text,text,text,integer) OWNER TO aoe2war_clan_image_exec_v1;
REVOKE ALL ON FUNCTION aoe2war_clan_image_hd_v1.post_image(text,text,text,text,text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_image_hd_v1.post_image(text,text,text,text,text,text,text,integer) TO aoe2war_social_writer;
CREATE FUNCTION aoe2war_clan_image_hd_v1.read_image(p_uid text,p_slug text,p_aid integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $fn$
DECLARE r record; s record; result jsonb;
BEGIN
 IF p_uid IS NULL OR p_uid !~ '^[A-Za-z0-9_.:-]{1,100}$' OR p_slug IS NULL OR p_slug !~ '^[a-z0-9][a-z0-9_-]{0,79}$' OR p_aid IS NULL OR p_aid<=0 THEN RETURN NULL; END IF;
 SELECT * INTO s FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug);
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO r FROM aoe2war_clan_image_hd_v1.request_keys k WHERE k.attachment_id=p_aid AND k.clan_id=s.clan_id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 result:=aoe2war_clan_image_hd_v1.leaf_read(p_uid,p_slug,r.message_id,r.attachment_id,r.attachment_ref);
 IF result IS NULL OR result->>'mimeType' IS DISTINCT FROM r.attachment_mime OR result->>'name' IS DISTINCT FROM r.attachment_name OR result->>'sizeBytes' IS DISTINCT FROM r.attachment_bytes::text THEN RETURN NULL; END IF;
 RETURN result;
END $fn$;
ALTER FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer) OWNER TO aoe2war_clan_image_exec_v1;
REVOKE ALL ON FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer) TO aoe2war_social_writer;
COMMIT;
