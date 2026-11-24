-- Radio-only metadata capture CANDIDATE. Not authorization to execute on HEL1.
-- No application rows, secrets, function source, or SQL mutations.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path = pg_catalog;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '400ms';
SELECT 'RADIO_CATALOG_META', jsonb_build_object(
 'database',current_database(),'session_user',session_user,'current_user',current_user,
 'server_version',current_setting('server_version'),'read_only',current_setting('transaction_read_only'),
 'snapshot',txid_current_snapshot()::text,'captured_at',statement_timestamp());
WITH RECURSIVE
targets(schema_name,relation_name) AS (VALUES
 ('public','radio_station_state'),('public','radio_programs'),
 ('public','radio_program_items'),('public','radio_assets'),('public','radio_submissions'),
 ('public','radio_listener_states'),('public','radio_track_ratings'),
 ('aoe2war_public_v2','radio_station_display'),('aoe2war_public_v2','radio_published_tracks')),
rels AS (
 SELECT t.*,c.oid,c.relkind,c.relowner,c.relacl,c.relrowsecurity,c.relforcerowsecurity
 FROM targets t LEFT JOIN pg_namespace n ON n.nspname=t.schema_name
 LEFT JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=t.relation_name
), seqs AS (
 SELECT DISTINCT c.oid,c.relname,c.relowner,c.relacl,d.refobjid,d.refobjsubid
 FROM pg_depend d JOIN pg_class c ON c.oid=d.objid AND c.relkind='S'
 JOIN rels r ON r.oid=d.refobjid
 WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
), funcs AS (
 SELECT DISTINCT p.oid,p.proowner,p.proacl,p.prosecdef,p.proconfig,p.prolang,p.prosrc
 FROM pg_proc p WHERE p.oid IN (
 SELECT t.tgfoid FROM pg_trigger t JOIN rels r ON r.oid=t.tgrelid
 UNION SELECT to_regprocedure('c03_auth_ro.read_user(text)')::oid
 )
), roots AS (
 SELECT oid FROM pg_roles WHERE rolname IN ('aoe2war_web_prod','c03_auth_reader')
 UNION SELECT relowner FROM rels WHERE oid IS NOT NULL
 UNION SELECT relowner FROM seqs
 UNION SELECT proowner FROM funcs
 UNION SELECT a.grantee FROM rels r CROSS JOIN LATERAL aclexplode(COALESCE(r.relacl,acldefault('r',r.relowner))) a WHERE a.grantee<>0
 UNION SELECT a.grantee FROM seqs s CROSS JOIN LATERAL aclexplode(COALESCE(s.relacl,acldefault('s',s.relowner))) a WHERE a.grantee<>0
 UNION SELECT a.grantee FROM funcs f CROSS JOIN LATERAL aclexplode(COALESCE(f.proacl,acldefault('f',f.proowner))) a WHERE a.grantee<>0
), chain(root_oid,role_oid,seen,inherit_path,set_path) AS (
 SELECT oid,oid,ARRAY[oid],true,true FROM roots
 UNION ALL SELECT c.root_oid,m.roleid,c.seen||m.roleid,c.inherit_path AND m.inherit_option,c.set_path AND m.set_option
 FROM chain c JOIN pg_auth_members m ON m.member=c.role_oid WHERE NOT m.roleid=ANY(c.seen)
), relevant_roles AS (SELECT DISTINCT role_oid AS oid FROM chain),
edges AS (
 SELECT 'relation' AS kind,r.oid AS source_oid,'pg_class'::regclass::oid AS classid,r.oid AS objid FROM rels r WHERE r.oid IS NOT NULL
 UNION ALL SELECT 'trigger',t.tgrelid,'pg_trigger'::regclass::oid,t.oid FROM pg_trigger t JOIN rels r ON r.oid=t.tgrelid
 UNION ALL SELECT 'rewrite',w.ev_class,'pg_rewrite'::regclass::oid,w.oid FROM pg_rewrite w JOIN rels r ON r.oid=w.ev_class
 UNION ALL SELECT 'function',f.oid,'pg_proc'::regclass::oid,f.oid FROM funcs f
)
SELECT 'RADIO_CATALOG',jsonb_build_object(
 'relations',COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY schema_name,relation_name) FROM rels r),'[]'::jsonb),
 'columns',COALESCE((SELECT jsonb_agg(jsonb_build_object('relation_oid',a.attrelid,'number',a.attnum,'name',a.attname,'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,'identity',a.attidentity,'generated',a.attgenerated,'acl',a.attacl) ORDER BY a.attrelid,a.attnum) FROM pg_attribute a JOIN rels r ON r.oid=a.attrelid WHERE a.attnum>0 AND NOT a.attisdropped),'[]'::jsonb),
 'constraints',COALESCE((SELECT jsonb_agg(jsonb_build_object('oid',c.oid,'name',c.conname,'type',c.contype,'relation_oid',c.conrelid,'referenced_oid',c.confrelid,'keys',c.conkey,'referenced_keys',c.confkey,'update',c.confupdtype,'delete',c.confdeltype,'validated',c.convalidated,'deferrable',c.condeferrable,'definition_hash',md5(pg_get_constraintdef(c.oid))) ORDER BY c.oid) FROM pg_constraint c WHERE c.conrelid IN (SELECT oid FROM rels) OR (c.contype='f' AND c.confrelid IN (SELECT oid FROM rels))),'[]'::jsonb),
 'indexes',COALESCE((SELECT jsonb_agg(jsonb_build_object('relation_oid',i.indrelid,'index_oid',i.indexrelid,'unique',i.indisunique,'primary',i.indisprimary,'valid',i.indisvalid,'keys',i.indkey::text,'definition_hash',md5(pg_get_indexdef(i.indexrelid))) ORDER BY i.indexrelid) FROM pg_index i JOIN rels r ON r.oid=i.indrelid),'[]'::jsonb),
 'sequences',COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY oid) FROM seqs s),'[]'::jsonb),
 'triggers',COALESCE((SELECT jsonb_agg(jsonb_build_object('relation_oid',t.tgrelid,'oid',t.oid,'name',t.tgname,'enabled',t.tgenabled,'internal',t.tgisinternal,'type',t.tgtype,'function_oid',t.tgfoid,'definition_hash',md5(pg_get_triggerdef(t.oid))) ORDER BY t.oid) FROM pg_trigger t JOIN rels r ON r.oid=t.tgrelid),'[]'::jsonb),
 'functions',COALESCE((SELECT jsonb_agg(jsonb_build_object('oid',f.oid,'identity',f.oid::regprocedure::text,'owner',f.proowner,'acl',f.proacl,'security_definer',f.prosecdef,'settings_hash',md5(f.proconfig::text),'language',f.prolang,'body_hash',md5(f.prosrc)) ORDER BY f.oid) FROM funcs f),'[]'::jsonb),
 'identity_reader_oid',to_regprocedure('c03_auth_ro.read_user(text)')::oid,
 'roles',COALESCE((SELECT jsonb_agg(jsonb_build_object('oid',r.oid,'name',r.rolname,'login',r.rolcanlogin,'inherit',r.rolinherit,'superuser',r.rolsuper,'create_role',r.rolcreaterole,'create_db',r.rolcreatedb,'replication',r.rolreplication,'bypass_rls',r.rolbypassrls,'database_connect',has_database_privilege(r.oid,current_database(),'CONNECT'),'database_create',has_database_privilege(r.oid,current_database(),'CREATE')) ORDER BY r.oid) FROM pg_roles r JOIN relevant_roles q ON q.oid=r.oid),'[]'::jsonb),
 'membership',COALESCE((SELECT jsonb_agg(to_jsonb(c) ORDER BY root_oid,role_oid,seen) FROM chain c),'[]'::jsonb),
 'effective_relation_acl',COALESCE((SELECT jsonb_agg(jsonb_build_object('role_oid',q.oid,'relation_oid',r.oid,'select',has_table_privilege(q.oid,r.oid,'SELECT'),'insert',has_table_privilege(q.oid,r.oid,'INSERT'),'update',has_table_privilege(q.oid,r.oid,'UPDATE'),'delete',has_table_privilege(q.oid,r.oid,'DELETE'),'truncate',has_table_privilege(q.oid,r.oid,'TRUNCATE'),'trigger',has_table_privilege(q.oid,r.oid,'TRIGGER')) ORDER BY q.oid,r.oid) FROM relevant_roles q CROSS JOIN rels r WHERE r.oid IS NOT NULL),'[]'::jsonb),
 'dependencies',COALESCE((SELECT jsonb_agg(jsonb_build_object('kind',e.kind,'source_oid',e.source_oid,'class_oid',d.classid,'object_oid',d.objid,'ref_class_oid',d.refclassid,'ref_object_oid',d.refobjid,'ref_column',d.refobjsubid,'type',d.deptype) ORDER BY e.kind,e.source_oid,d.classid,d.objid,d.refclassid,d.refobjid,d.refobjsubid) FROM edges e JOIN pg_depend d ON d.classid=e.classid AND d.objid=e.objid),'[]'::jsonb)
);
SELECT 'FINAL_NONAUTHORIZATION',jsonb_build_object('metadata_only',true,'mutations',false,'production_admitted',false,'dynamic_dependency_proof',false,'rights_proven',false,'funding','DENIED');
COMMIT;
