-- WE1/WE3 Library PUBLIC-PROJECTION source candidate, never direct base grants.
-- HD-ONLY implementation tied to the already owner-present authenticated
-- HD/DE 2026-11-19 supplementary private catalog witness. SHA256:
-- HD cc3b8e7016497f0f4576d01999988a890249066ec703951d61e4ba2d2cff9c24
-- DE a54e48bb94ae5d5f3b14607051cde5280e0d8c28f7e3b54d60f5185e2553da60
-- HD original event owner aoe2hd_user ALSO has financial authority;
-- that owner is only used to execute fixed projection reads. Web gets
-- SELECT on NEW filtered views; NO original table or sequence grant.
-- The source is not a production SQL permit. WE2 owns protected installation.
BEGIN;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='10000ms';
DO $pre$
DECLARE obj record;
BEGIN
 IF current_database()<>'aoe2hd_db'
 OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aoe2hd_user' AND NOT rolsuper)
 OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aoe2war_web_prod'
                AND NOT rolsuper AND NOT rolinherit)
 OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN
      ('aoe2war_library_activity_public','aoe2war_library_watcher_public'))
 THEN RAISE EXCEPTION 'LIBRARY_HD_ONLY_ROLE_OR_SCHEMA_PREIMAGE_HOLD'; END IF;
 FOR obj IN
 SELECT x.name,c.oid,c.relkind,c.relowner,c.relacl,c.relrowsecurity,c.relforcerowsecurity
 FROM (VALUES ('user_activity_events'),('watcher_client_events'),('users')) x(name)
 LEFT JOIN pg_class c ON c.oid=to_regclass(format('public.%I',x.name))
 LOOP
  IF obj.oid IS NULL OR obj.relkind<>'r' OR
     obj.relowner<>'aoe2hd_user'::regrole OR
     obj.relrowsecurity OR obj.relforcerowsecurity
  THEN RAISE EXCEPTION 'LIBRARY_BASE_OWNER_OR_RLS_PREIMAGE_HOLD %',obj.name; END IF;
  IF obj.name IN ('user_activity_events','watcher_client_events') AND
     obj.relacl::text IS DISTINCT FROM
     '{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'
  THEN RAISE EXCEPTION 'LIBRARY_EVENT_RAW_ACL_PREIMAGE_HOLD %',obj.name; END IF;
 END LOOP;
 IF has_table_privilege('aoe2war_web_prod','public.user_activity_events','SELECT')
    OR has_table_privilege('aoe2war_web_prod','public.watcher_client_events','SELECT')
 THEN RAISE EXCEPTION 'LIBRARY_WEB_ALREADY_READS_PROTECTED_BASE'; END IF;
END
$pre$;
CREATE SCHEMA aoe2war_library_activity_public AUTHORIZATION aoe2hd_user;
CREATE SCHEMA aoe2war_library_watcher_public AUTHORIZATION aoe2hd_user;
REVOKE ALL ON SCHEMA aoe2war_library_activity_public FROM PUBLIC;
REVOKE ALL ON SCHEMA aoe2war_library_watcher_public FROM PUBLIC;

-- NO general event JSON: allow only the metadata fields actually used by
-- public Activity summaries and explicit new-package replay provenance.
-- Historic arbitrary filenames remain PRIVATE / not exposed from this view.
CREATE VIEW aoe2war_library_activity_public.replay_uploads
WITH (security_barrier=true) AS
 SELECT e.id,e.user_id,e.type,NULL::varchar(80) AS label,e.created_at,
 jsonb_strip_nulls(jsonb_build_object(
   'packageUpload',CASE WHEN jsonb_typeof(e.metadata::jsonb->'packageUpload')='boolean'
                    THEN e.metadata::jsonb->'packageUpload' END,
   'viaWatcher',CASE WHEN jsonb_typeof(e.metadata::jsonb->'viaWatcher')='boolean'
                    THEN e.metadata::jsonb->'viaWatcher' END,
   'receivedCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'receivedCount')='number'
                    THEN e.metadata::jsonb->'receivedCount' END,
   'uploadedCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'uploadedCount')='number'
                    THEN e.metadata::jsonb->'uploadedCount' END,
   'parsedCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'parsedCount')='number'
                    THEN e.metadata::jsonb->'parsedCount' END,
   'resultReadyCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'resultReadyCount')='number'
                    THEN e.metadata::jsonb->'resultReadyCount' END,
   'duplicateCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'duplicateCount')='number'
                    THEN e.metadata::jsonb->'duplicateCount' END,
   'failedCount',CASE WHEN jsonb_typeof(e.metadata::jsonb->'failedCount')='number'
                    THEN e.metadata::jsonb->'failedCount' END,
   'gameIds',CASE WHEN jsonb_typeof(e.metadata::jsonb->'gameIds')='array'
                      AND jsonb_array_length(e.metadata::jsonb->'gameIds')<=256
                    THEN (SELECT coalesce(jsonb_agg(g.value ORDER BY g.ordinality),'[]'::jsonb)
                          FROM jsonb_array_elements(e.metadata::jsonb->'gameIds')
                            WITH ORDINALITY AS g(value,ordinality)
                          WHERE jsonb_typeof(g.value)='number'
                            AND g.value::text ~ '^[1-9][0-9]{0,11}$') END
 )) AS metadata
 FROM public.user_activity_events e
 WHERE e.type='replay_upload'
   AND EXISTS (SELECT 1 FROM public.users u WHERE u.id=e.user_id
     AND u.uid IS NOT NULL AND u.verification_method IS DISTINCT FROM 'system'
     AND u.uid !~ '^aoe2hd_ai_');
ALTER VIEW aoe2war_library_activity_public.replay_uploads
 OWNER TO aoe2hd_user;

CREATE VIEW aoe2war_library_watcher_public.batch_receipts
WITH (security_barrier=true) AS
 SELECT e.id,e.user_id,e.user_uid,e.event_type,e.created_at,
   CASE WHEN e.watcher_id IS NULL THEN NULL
        ELSE 'w-'||md5(coalesce(e.user_uid,e.user_id::text,'')||':'||e.watcher_id) END
        AS watcher_id,
   CASE WHEN e.session_id IS NULL THEN NULL
        ELSE 's-'||md5(coalesce(e.user_uid,e.user_id::text,'')||':'||e.session_id) END
        AS session_id,
   e.replay_hash
 FROM public.watcher_client_events e
 WHERE e.event_type IN (
   'batch_upload_started','batch_upload_scanned',
   'batch_upload_file_started','batch_upload_file_stable',
   'batch_upload_file_skipped','batch_upload_file_succeeded',
   'batch_upload_file_failed','batch_upload_finished',
   'batch_upload_failed')
   AND (e.user_id IS NOT NULL OR e.user_uid IS NOT NULL)
   AND EXISTS (SELECT 1 FROM public.users u
     WHERE (e.user_id IS NULL OR u.id=e.user_id)
       AND (e.user_uid IS NULL OR u.uid=e.user_uid)
       AND u.uid IS NOT NULL
       AND u.verification_method IS DISTINCT FROM 'system'
       AND u.uid !~ '^aoe2hd_ai_');
ALTER VIEW aoe2war_library_watcher_public.batch_receipts
 OWNER TO aoe2hd_user;
GRANT USAGE ON SCHEMA aoe2war_library_activity_public TO aoe2war_web_prod;
GRANT USAGE ON SCHEMA aoe2war_library_watcher_public TO aoe2war_web_prod;
GRANT SELECT ON aoe2war_library_activity_public.replay_uploads TO aoe2war_web_prod;
GRANT SELECT ON aoe2war_library_watcher_public.batch_receipts TO aoe2war_web_prod;
COMMIT;
