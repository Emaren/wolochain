-- Read-only preflight; no installation or authorization.
BEGIN READ ONLY;
SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='350ms';
DO $check$
DECLARE r record; f record; rel record;
BEGIN
 IF current_database()<>'aoe2hd_db' OR current_user<>'postgres' OR current_setting('server_version_num')::integer NOT BETWEEN 160000 AND 169999 OR to_regnamespace('aoe2war_clan_legacy_hd_v1') IS NOT NULL THEN RAISE EXCEPTION 'CLAN_LEGACY_SCOPE_HOLD'; END IF;
 IF EXISTS(SELECT 1 FROM pg_default_acl WHERE defaclrole='postgres'::regrole AND defaclnamespace=0) THEN RAISE EXCEPTION 'CLAN_LEGACY_DEFAULT_ACL_HOLD'; END IF;
 FOR r IN SELECT * FROM (VALUES ('aoe2war_social_writer',true),('aoe2war_clan_image_exec_v1',false),('aoe2war_web_prod',true)) v(name,login) LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r.name AND rolcanlogin=r.login AND NOT rolsuper AND NOT rolinherit AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication) OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=to_regrole(r.name)) THEN RAISE EXCEPTION 'CLAN_LEGACY_ROLE_HOLD %',r.name; END IF;
 END LOOP;
 FOR r IN SELECT * FROM (VALUES
 ('aoe2war_clan_read_hd_v1.read_hall(text,text,integer,integer)','aoe2hd_user','aoe2war_social_writer','4ebc7082f12bf54278c2b176ce5df061',true),
 ('aoe2war_clan_image_hd_v1.read_image(text,text,integer)','aoe2war_clan_image_exec_v1','aoe2war_social_writer','c69983152249f706d89d7efa2226d072',false),
 ('aoe2war_clan_image_hd_v1.leaf_scope(text,text)','aoe2hd_user','aoe2war_clan_image_exec_v1','5da8b258ccd8259be26635dd39fe50a3',false)) v(sig,owner_name,caller,body_md5,stable) LOOP
  SELECT * INTO f FROM pg_proc WHERE oid=to_regprocedure(r.sig);
  IF NOT FOUND OR f.proowner<>to_regrole(r.owner_name) OR NOT f.prosecdef OR md5(f.prosrc)<>r.body_md5 OR f.provolatile<>(CASE WHEN r.stable THEN 's'::"char" ELSE 'v'::"char" END) OR (f.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']) IS NOT TRUE OR cardinality(f.proconfig)<>(CASE WHEN r.stable THEN 2 ELSE 1 END) OR (r.stable AND (f.proconfig @> ARRAY['TimeZone=UTC']) IS NOT TRUE) OR f.proacl IS NULL OR NOT has_function_privilege(r.caller,f.oid,'EXECUTE') OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee NOT IN (f.proowner,to_regrole(r.caller)) OR (a.grantee<>f.proowner AND a.is_grantable)) THEN RAISE EXCEPTION 'CLAN_LEGACY_FUNCTION_HOLD %',r.sig; END IF;
 END LOOP;
 FOR rel IN SELECT * FROM pg_class WHERE oid IN ('public.users'::regclass,'public.clans'::regclass,'public.clan_members'::regclass,'public.clan_messages'::regclass,'public.clan_message_attachments'::regclass,'aoe2war_clan_image_hd_v1.request_keys'::regclass) LOOP
  IF rel.relkind<>'r' OR rel.relrowsecurity OR rel.relforcerowsecurity OR rel.relowner<>(CASE WHEN rel.oid='aoe2war_clan_image_hd_v1.request_keys'::regclass THEN 'aoe2war_clan_image_exec_v1'::regrole ELSE 'aoe2hd_user'::regrole END) THEN RAISE EXCEPTION 'CLAN_LEGACY_RELATION_HOLD %',rel.relname; END IF;
  FOR r IN SELECT * FROM (VALUES ('aoe2war_social_writer'),('aoe2war_web_prod'),('aoe2war_clan_image_exec_v1')) v(name) LOOP
   -- Exact display-column contract: app-prodn 15c693d141640ae51dea416ae996b3e3c0357c0f
   -- config/nonfinancial-production-auth.sql and scripts/r25_c_start_root.py.
   IF r.name='aoe2war_web_prod' AND rel.oid='public.users'::regclass THEN
    IF has_table_privilege(r.name,rel.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(r.name,rel.oid,'INSERT,UPDATE,REFERENCES') OR
       (SELECT array_agg(a.attname::text ORDER BY a.attname::text COLLATE "C") FROM pg_attribute a WHERE a.attrelid=rel.oid AND a.attnum>0 AND NOT a.attisdropped AND has_column_privilege(r.name,rel.oid,a.attnum,'SELECT')) IS DISTINCT FROM ARRAY['created_at','gender_division','gender_division_updated_at','id','in_game_name','last_seen','lock_name','preferred_language','represented_country','represented_country_updated_at','steam_id','steam_persona_name','twitch_stream_url','uid','verification_level','verification_method','verified','verified_at' ] OR
       EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid=rel.oid AND a.attnum>0 AND NOT a.attisdropped AND has_column_privilege(r.name,rel.oid,a.attnum,'SELECT WITH GRANT OPTION')) THEN RAISE EXCEPTION 'CLAN_LEGACY_WEB_DISPLAY_ACL_DRIFT'; END IF;
    CONTINUE;
   END IF;
   IF rel.relowner<>to_regrole(r.name) AND (has_table_privilege(r.name,rel.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(r.name,rel.oid,'SELECT,INSERT,UPDATE,REFERENCES')) THEN RAISE EXCEPTION 'CLAN_LEGACY_RAW_PRIVILEGE_HOLD % %',r.name,rel.relname; END IF;
  END LOOP;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgenabled<>'D' AND tgrelid IN ('public.clan_messages'::regclass,'public.clan_message_attachments'::regclass)) OR EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class IN ('public.clan_messages'::regclass,'public.clan_message_attachments'::regclass)) THEN RAISE EXCEPTION 'CLAN_LEGACY_TRIGGER_RULE_HOLD'; END IF;
END $check$;
SELECT 'PASS_NATIVE_CLAN_LEGACY_CATALOG_PREFLIGHT_READ_ONLY' AS status,
 current_database() AS database,
 (SELECT count(*) FROM aoe2war_clan_image_hd_v1.request_keys) AS original_upload_receipts,
 (SELECT count(*) FROM public.clan_message_attachments WHERE storage_ref LIKE 'file:v1:clan-hall/%') AS legacy_rows,
 false AS production_admitted;
ROLLBACK;
