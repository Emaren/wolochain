-- SOURCE REVIEW ONLY. Caller must have admitted exact native delivery receipts.
-- Temporary input table populated using bound parameters on the same connection.
-- No arbitrary direct caller, no grants, no mutation of original rows.
-- This fragment requires an explicit transaction; ON COMMIT DROP input table.
DO $guard$
DECLARE expected integer; inserted integer;
BEGIN
 IF current_database()<>'aoe2hd_db' OR current_user<>'postgres' OR
 NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=to_regprocedure('aoe2war_clan_read_hd_v1.read_hall(text,text,integer,integer)') AND proowner='aoe2hd_user'::regrole AND prosecdef AND md5(prosrc)='0908ca9668f4a032f8c8834ef532376e') OR
 NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=to_regprocedure('aoe2war_clan_image_hd_v1.read_image(text,text,integer)') AND proowner='aoe2war_clan_image_exec_v1'::regrole AND prosecdef AND md5(prosrc)='6b00530657375de4c4df42a1b60d9d3d') OR
 NOT has_function_privilege('aoe2war_clan_image_exec_v1','aoe2war_clan_legacy_hd_v1.read_mapped(text,text,integer)','EXECUTE')
 THEN RAISE EXCEPTION 'CLAN_LEGACY_BATCH_READER_HOLD'; END IF;
 LOCK TABLE aoe2war_clan_legacy_hd_v1.admitted IN SHARE ROW EXCLUSIVE MODE;
 -- Exact rows and sibling/reference cardinality must remain stable while
 -- admitted. Bounded lock timeout is set by the enclosing native controller.
 LOCK TABLE public.clan_message_attachments, public.clan_messages, public.clans IN SHARE MODE;
 SELECT count(*) INTO expected FROM pg_temp.clan_legacy_batch;
 IF expected NOT BETWEEN 1 AND 624 OR EXISTS(SELECT 1 FROM aoe2war_clan_legacy_hd_v1.admitted) THEN RAISE EXCEPTION 'CLAN_LEGACY_BATCH_COUNT_OR_REPLAY_HOLD'; END IF;
 IF EXISTS(SELECT 1 FROM pg_temp.clan_legacy_batch b JOIN aoe2war_clan_image_hd_v1.request_keys k ON k.attachment_id=b.attachment_id OR k.message_id=b.message_id OR k.attachment_ref=b.protected_ref) OR EXISTS(SELECT 1 FROM pg_temp.clan_legacy_batch b JOIN public.clan_message_attachments a ON a.storage_ref=b.protected_ref) THEN RAISE EXCEPTION 'CLAN_LEGACY_BATCH_COLLISION'; END IF;
 INSERT INTO aoe2war_clan_legacy_hd_v1.admitted(attachment_id,message_id,original_ref,protected_ref,mime,name,size_bytes,content_sha256)
 SELECT b.attachment_id,b.message_id,b.original_ref,b.protected_ref,b.mime,a.name,b.size_bytes,b.content_sha256
 FROM pg_temp.clan_legacy_batch b JOIN public.clan_message_attachments a ON a.id=b.attachment_id AND a.message_id=b.message_id AND a.storage_ref=b.original_ref AND a.mime_type=b.mime AND a.size_bytes=b.size_bytes AND a.kind='image'
 JOIN public.clan_messages m ON m.id=a.message_id JOIN public.clans c ON c.id=m.clan_id
 WHERE m.audience='clan' AND c.status='active' AND c.chat_audience_policy IN ('clan','users','public')
 AND a.name IS NOT NULL AND length(a.name) BETWEEN 1 AND 160 AND a.name !~ '[[:cntrl:]/]' AND strpos(a.name,chr(92))=0
 AND (SELECT count(*) FROM public.clan_message_attachments s WHERE s.message_id=a.message_id)=1
 AND (SELECT count(*) FROM public.clan_message_attachments s WHERE s.storage_ref=a.storage_ref)=1;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 IF inserted<>expected OR (SELECT count(*) FROM aoe2war_clan_legacy_hd_v1.qualified)<>expected THEN RAISE EXCEPTION 'CLAN_LEGACY_BATCH_PARITY_HOLD'; END IF;
END $guard$;
