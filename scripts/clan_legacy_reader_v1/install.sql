-- Source review only: do not install until native exact function/catalog and content admission.
BEGIN;
SET LOCAL lock_timeout='350ms'; SET LOCAL statement_timeout='10s';
DO $pre$ BEGIN
 IF current_database()<>'aoe2hd_db' OR current_user<>'postgres' OR to_regnamespace('aoe2war_clan_legacy_hd_v1') IS NOT NULL OR
 NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=to_regprocedure('aoe2war_clan_read_hd_v1.read_hall(text,text,integer,integer)') AND proowner='aoe2hd_user'::regrole AND prosecdef AND md5(prosrc)='4ebc7082f12bf54278c2b176ce5df061') OR
 NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=to_regprocedure('aoe2war_clan_image_hd_v1.read_image(text,text,integer)') AND proowner='aoe2war_clan_image_exec_v1'::regrole AND prosecdef AND md5(prosrc)='c69983152249f706d89d7efa2226d072')
 THEN RAISE EXCEPTION 'CLAN_LEGACY_PREIMAGE_HOLD'; END IF;
END $pre$;
CREATE SCHEMA aoe2war_clan_legacy_hd_v1;
REVOKE ALL ON SCHEMA aoe2war_clan_legacy_hd_v1 FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_clan_legacy_hd_v1 TO aoe2hd_user,aoe2war_clan_image_exec_v1;
CREATE TABLE aoe2war_clan_legacy_hd_v1.admitted (
 attachment_id integer PRIMARY KEY CHECK(attachment_id>0), message_id integer NOT NULL UNIQUE CHECK(message_id>0),
 original_ref text NOT NULL UNIQUE CHECK(original_ref ~ '^file:v1:clan-hall/[0-9]{4}/(0[1-9]|1[0-2])/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.](png|jpg|jpeg|webp)$'),
 protected_ref text NOT NULL UNIQUE, mime text NOT NULL CHECK(mime IN ('image/png','image/jpeg','image/webp')),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 160 AND name !~ '[[:cntrl:]/]' AND strpos(name,chr(92))=0),
 size_bytes integer NOT NULL CHECK(size_bytes BETWEEN 1 AND 10000000), content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 CHECK(protected_ref ~ ('^file:v1:clan-[0-9a-f]{32}[.]'||CASE mime WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$'))
);
REVOKE ALL ON aoe2war_clan_legacy_hd_v1.admitted FROM PUBLIC,aoe2war_social_writer,aoe2war_clan_image_exec_v1,aoe2war_web_prod;
GRANT SELECT ON aoe2war_clan_legacy_hd_v1.admitted TO aoe2hd_user;
CREATE VIEW aoe2war_clan_legacy_hd_v1.qualified WITH (security_barrier=true) AS
 SELECT a.attachment_id,a.message_id,a.protected_ref,a.mime,a.name,a.size_bytes
 FROM aoe2war_clan_legacy_hd_v1.admitted a JOIN public.clan_message_attachments x ON x.id=a.attachment_id AND x.message_id=a.message_id AND x.storage_ref=a.original_ref AND x.kind='image' AND x.mime_type=a.mime AND x.name=a.name AND x.size_bytes=a.size_bytes
 JOIN public.clan_messages m ON m.id=a.message_id JOIN public.clans c ON c.id=m.clan_id
 WHERE m.audience='clan' AND c.status='active' AND c.chat_audience_policy IN ('clan','users','public')
 AND (SELECT count(*) FROM public.clan_message_attachments b WHERE b.message_id=m.id)=1
 AND (SELECT count(*) FROM public.clan_message_attachments b WHERE b.storage_ref=a.original_ref)=1;
ALTER VIEW aoe2war_clan_legacy_hd_v1.qualified OWNER TO aoe2hd_user;
REVOKE ALL ON aoe2war_clan_legacy_hd_v1.qualified FROM PUBLIC,aoe2war_social_writer,aoe2war_clan_image_exec_v1,aoe2war_web_prod;
CREATE FUNCTION aoe2war_clan_legacy_hd_v1.read_mapped(p_uid text,p_slug text,p_aid integer) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $legacy$
 SELECT jsonb_build_object('storageRef',q.protected_ref,'mimeType',q.mime,'name',q.name,'sizeBytes',q.size_bytes)
 FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug) s JOIN public.clan_messages m ON m.clan_id=s.clan_id
 JOIN aoe2war_clan_legacy_hd_v1.qualified q ON q.message_id=m.id AND q.attachment_id=p_aid
 WHERE p_uid ~ '^[A-Za-z0-9_.:-]{1,100}$' AND p_slug ~ '^[a-z0-9][a-z0-9_-]{0,79}$' AND p_aid>0
$legacy$;
ALTER FUNCTION aoe2war_clan_legacy_hd_v1.read_mapped(text,text,integer) OWNER TO aoe2hd_user;
REVOKE ALL ON FUNCTION aoe2war_clan_legacy_hd_v1.read_mapped(text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aoe2war_clan_legacy_hd_v1.read_mapped(text,text,integer) TO aoe2war_clan_image_exec_v1;
CREATE OR REPLACE FUNCTION aoe2war_clan_read_hd_v1.read_hall(p_actor text,p_slug text,p_before integer,p_focus integer)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $fn$
WITH actor AS (
 SELECT u.id,u.uid,coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid) display_name,
 m.role,c.id clan_id,c.slug,c.name,c.tagline,c.description,c.crest_url,c.chat_audience_policy
 FROM public.users u JOIN public.clan_members m ON m.user_id=u.id
 JOIN public.clans c ON c.id=m.clan_id
 WHERE u.uid=p_actor AND p_actor ~ '^[A-Za-z0-9_.:-]{1,100}$'
 AND u.verification_method IS DISTINCT FROM 'system'
 AND u.uid !~ '^aoe2hd_ai_' AND u.uid NOT IN ('aoe2hd-moose','challenge-protocol','aoe2hd_betting_bot_tony','aoe2hd_betting_bot_paulie','aoe2hd_betting_bot_tommy','aoe2hd_betting_bot_henry')
 AND c.slug=p_slug AND p_slug ~ '^[a-z0-9][a-z0-9_-]{0,79}$'
 AND c.status='active' AND c.chat_audience_policy IN ('clan','users','public') AND m.status='active'
 AND (p_before IS NULL OR p_before>0) AND (p_focus IS NULL OR p_focus>0)
 AND (p_before IS NULL OR p_focus IS NULL)
), cursor AS (
 SELECT m.id,m.created_at FROM public.clan_messages m JOIN actor a ON a.clan_id=m.clan_id
 WHERE m.id=p_before AND m.audience IN ('clan','users','public')
), chosen AS (
 SELECT m.id,m.body,m.audience,m.created_at,m.updated_at,u.uid,
 coalesce(nullif(u.in_game_name,''),nullif(u.steam_persona_name,''),u.uid) display_name,
 cm.role
 FROM actor a JOIN public.clan_messages m ON m.clan_id=a.clan_id
 JOIN public.users u ON u.id=m.author_user_id
 LEFT JOIN public.clan_members cm ON cm.clan_id=a.clan_id AND cm.user_id=u.id AND cm.status='active'
 WHERE m.audience IN ('clan','users','public')
 AND (p_focus IS NULL OR m.id=p_focus)
 AND (p_before IS NULL OR EXISTS(SELECT 1 FROM cursor b WHERE (m.created_at,m.id)<(b.created_at,b.id)))
 ORDER BY m.created_at DESC,m.id DESC LIMIT (CASE WHEN p_focus IS NOT NULL THEN 1 ELSE 81 END)
), page AS (SELECT * FROM chosen ORDER BY created_at DESC,id DESC LIMIT 80)
SELECT jsonb_build_object(
 'clan',jsonb_build_object('id',a.clan_id,'slug',a.slug,'name',a.name,'tagline',a.tagline,'description',left(a.description,4000),'crestUrl',a.crest_url,'chatAudiencePolicy',a.chat_audience_policy,'memberCount',(SELECT count(*) FROM public.clan_members m WHERE m.clan_id=a.clan_id AND m.status='active')),
 'viewer',jsonb_build_object('uid',a.uid,'displayName',a.display_name,'role',a.role),
 'messages',coalesce((SELECT jsonb_agg(jsonb_build_object(
 'id',p.id,'body',p.body,'audience',p.audience,'createdAt',p.created_at AT TIME ZONE 'UTC','updatedAt',p.updated_at AT TIME ZONE 'UTC',
 'author',jsonb_build_object('uid',p.uid,'displayName',p.display_name,'role',p.role),
 'attachments',coalesce((SELECT jsonb_agg(jsonb_build_object('id',z.id,'name',z.name,'mimeType',z.mime_type,'sizeBytes',z.size_bytes) ORDER BY z.id)
 FROM (SELECT x.id,x.name,x.mime_type,x.size_bytes FROM public.clan_message_attachments x
 WHERE x.message_id=p.id AND p.audience='clan' AND x.kind='image' AND x.mime_type IN ('image/png','image/jpeg','image/webp') AND x.size_bytes BETWEEN 1 AND 10000000
 AND x.name IS NOT NULL AND length(x.name) BETWEEN 1 AND 160
 AND (x.storage_ref ~ ('^file:v1:clan-[0-9a-f]{32}[.]'||CASE x.mime_type WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$') OR EXISTS(SELECT 1 FROM aoe2war_clan_legacy_hd_v1.qualified q WHERE q.attachment_id=x.id AND q.message_id=p.id))
 ORDER BY x.id LIMIT 1) z),'[]'::jsonb),
 'unsupportedAttachment',EXISTS(SELECT 1 FROM public.clan_message_attachments x WHERE x.message_id=p.id AND NOT (p.audience='clan' AND x.kind='image' AND x.mime_type IN ('image/png','image/jpeg','image/webp') AND x.size_bytes BETWEEN 1 AND 10000000 AND x.name IS NOT NULL AND length(x.name) BETWEEN 1 AND 160 AND (x.storage_ref ~ ('^file:v1:clan-[0-9a-f]{32}[.]'||CASE x.mime_type WHEN 'image/png' THEN 'png' WHEN 'image/jpeg' THEN 'jpg' ELSE 'webp' END||'$') OR EXISTS(SELECT 1 FROM aoe2war_clan_legacy_hd_v1.qualified q WHERE q.attachment_id=x.id AND q.message_id=p.id))) IS TRUE)
 ) ORDER BY p.created_at,p.id) FROM page p),'[]'::jsonb),
 'hasMore',p_focus IS NULL AND (SELECT count(*) FROM chosen)>80,
 'beforeMessageId',(SELECT id FROM page ORDER BY created_at,id LIMIT 1)
) FROM actor a
WHERE (p_before IS NULL OR EXISTS(SELECT 1 FROM cursor))
AND (p_focus IS NULL OR EXISTS(SELECT 1 FROM chosen))
$fn$;
CREATE OR REPLACE FUNCTION aoe2war_clan_image_hd_v1.read_image(p_uid text,p_slug text,p_aid integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $fn$
DECLARE r record; s record; result jsonb;
BEGIN
 IF p_uid IS NULL OR p_uid !~ '^[A-Za-z0-9_.:-]{1,100}$' OR p_slug IS NULL OR p_slug !~ '^[a-z0-9][a-z0-9_-]{0,79}$' OR p_aid IS NULL OR p_aid<=0 THEN RETURN NULL; END IF;
 SELECT * INTO s FROM aoe2war_clan_image_hd_v1.leaf_scope(p_uid,p_slug);
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO r FROM aoe2war_clan_image_hd_v1.request_keys k WHERE k.attachment_id=p_aid AND k.clan_id=s.clan_id;
 IF NOT FOUND THEN RETURN aoe2war_clan_legacy_hd_v1.read_mapped(p_uid,p_slug,p_aid); END IF;
 result:=aoe2war_clan_image_hd_v1.leaf_read(p_uid,p_slug,r.message_id,r.attachment_id,r.attachment_ref);
 IF result IS NULL OR result->>'mimeType' IS DISTINCT FROM r.attachment_mime OR result->>'name' IS DISTINCT FROM r.attachment_name OR result->>'sizeBytes' IS DISTINCT FROM r.attachment_bytes::text THEN RETURN NULL; END IF;
 RETURN result;
END $fn$;
COMMIT;
