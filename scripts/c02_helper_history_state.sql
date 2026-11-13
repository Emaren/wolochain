-- Metadata only. New enrollment objects are excluded; original raw column
-- ACL items retain their order. Only the explicitly supplied new grantee is
-- stripped, and the caller separately proves the exact permitted grant set.
CREATE OR REPLACE FUNCTION pg_temp.c02_history_state(p_strip oid)
RETURNS jsonb LANGUAGE SQL STABLE SECURITY INVOKER SET search_path=pg_catalog
AS $state$
WITH targets AS (
 SELECT c.oid,c.relname,c.relowner FROM pg_catalog.pg_class c
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN
 ('war_satchel_wager_authorizations','war_satchel_wager_broadcasts','war_satchel_funded_reservations')
), rels AS (
 SELECT oid FROM targets UNION
 SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN(SELECT oid FROM targets)
), trigs AS (
 SELECT t.* FROM pg_catalog.pg_trigger t WHERE t.tgrelid IN(SELECT oid FROM targets)
 OR t.tgfoid IN(SELECT p.oid FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='war_satchel_native_source_admission' AND p.pronargs=0)
), funcs AS (SELECT DISTINCT tgfoid oid FROM trigs), cons AS (
 SELECT oid FROM pg_catalog.pg_constraint WHERE conrelid IN(SELECT oid FROM targets) OR confrelid IN(SELECT oid FROM targets)
), defs AS (SELECT oid FROM pg_catalog.pg_attrdef WHERE adrelid IN(SELECT oid FROM targets)), types AS (
 SELECT t.oid FROM pg_catalog.pg_type t WHERE t.typrelid IN(SELECT oid FROM targets)
 UNION SELECT t.typarray FROM pg_catalog.pg_type t WHERE t.typrelid IN(SELECT oid FROM targets)
), subjects AS (
 SELECT 'pg_catalog.pg_class'::regclass classid,oid objid FROM rels
 UNION SELECT 'pg_catalog.pg_proc'::regclass,oid FROM funcs
 UNION SELECT 'pg_catalog.pg_constraint'::regclass,oid FROM cons
 UNION SELECT 'pg_catalog.pg_trigger'::regclass,oid FROM trigs
 UNION SELECT 'pg_catalog.pg_attrdef'::regclass,oid FROM defs
 UNION SELECT 'pg_catalog.pg_type'::regclass,oid FROM types
 UNION SELECT 'pg_catalog.pg_policy'::regclass,oid FROM pg_policy WHERE polrelid IN(SELECT oid FROM targets)
 UNION SELECT 'pg_catalog.pg_rewrite'::regclass,oid FROM pg_rewrite WHERE ev_class IN(SELECT oid FROM targets)
), helper AS (
 SELECT p.oid FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='c02_internal' AND p.proname='matches_original_funding'
), worker AS (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='c02_journal_worker')
SELECT pg_catalog.jsonb_build_object(
 'database',current_database(),
 'owners',(SELECT jsonb_object_agg(relname,pg_get_userbyid(relowner)) FROM targets),
 'relations',(SELECT jsonb_agg(to_jsonb(c)-ARRAY['relpages','reltuples','relallvisible','relfrozenxid','relminmxid'] ORDER BY c.oid) FROM pg_class c JOIN rels r ON r.oid=c.oid),
 'attributes',(SELECT jsonb_agg(to_jsonb(a)||jsonb_build_object('attacl',CASE WHEN p_strip IS NULL THEN a.attacl::text ELSE
  (SELECT array_agg(x.item ORDER BY x.ord)::text FROM unnest(a.attacl) WITH ORDINALITY x(item,ord)
   WHERE NOT EXISTS(SELECT 1 FROM aclexplode(ARRAY[x.item]) e WHERE e.grantee=p_strip)) END) ORDER BY a.attrelid,a.attnum)
  FROM pg_attribute a WHERE a.attrelid IN(SELECT oid FROM rels) AND a.attnum>0),
 'defaults',(SELECT jsonb_agg(to_jsonb(a) ORDER BY a.oid) FROM pg_attrdef a WHERE a.oid IN(SELECT oid FROM defs)),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c WHERE c.oid IN(SELECT oid FROM cons)),
 'indexes',(SELECT jsonb_agg(to_jsonb(i) ORDER BY i.indexrelid) FROM pg_index i WHERE i.indrelid IN(SELECT oid FROM targets)),
 'types',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_type t WHERE t.oid IN(SELECT oid FROM types)),
 'inheritance',(SELECT jsonb_agg(to_jsonb(i) ORDER BY inhrelid,inhseqno) FROM pg_inherits i WHERE inhrelid IN(SELECT oid FROM targets) OR inhparent IN(SELECT oid FROM targets)),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) FROM pg_policy p WHERE polrelid IN(SELECT oid FROM targets)),
 'rules',(SELECT jsonb_agg(to_jsonb(r) ORDER BY oid) FROM pg_rewrite r WHERE ev_class IN(SELECT oid FROM targets)),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM trigs t),
 'functions',(SELECT jsonb_agg(jsonb_build_object('proc',to_jsonb(p),'definition',pg_get_functiondef(p.oid)) ORDER BY p.oid) FROM pg_proc p WHERE p.oid IN(SELECT oid FROM funcs)),
 'dependencies',(SELECT jsonb_agg(to_jsonb(d) ORDER BY d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid,d.deptype)
 FROM pg_depend d WHERE EXISTS(SELECT 1 FROM subjects s WHERE (s.classid=d.classid AND s.objid=d.objid) OR (s.classid=d.refclassid AND s.objid=d.refobjid))),
 'shared_dependencies',(SELECT jsonb_agg(to_jsonb(d) ORDER BY d.dbid,d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.deptype)
 FROM pg_shdepend d WHERE ((d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND EXISTS(SELECT 1 FROM subjects s WHERE s.classid=d.classid AND s.objid=d.objid))
 OR (d.refclassid='pg_catalog.pg_authid'::regclass AND d.refobjid=(SELECT oid FROM worker)))
 AND (p_strip IS NULL OR NOT(d.refclassid='pg_catalog.pg_authid'::regclass AND d.refobjid=p_strip AND d.deptype='a'))
 AND (p_strip IS NULL OR NOT(d.refobjid=(SELECT oid FROM worker) AND d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND
  ((d.classid='pg_catalog.pg_proc'::regclass AND d.objid IN(SELECT oid FROM helper)) OR
   (d.classid='pg_catalog.pg_namespace'::regclass AND d.objid IN(SELECT oid FROM pg_namespace WHERE nspname='c02_internal')))))),
 'public_namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='public'),
 'worker',(SELECT to_jsonb(r) FROM pg_roles r WHERE r.oid=(SELECT oid FROM worker)),
 'worker_credential',(SELECT jsonb_build_object('is_null',a.rolpassword IS NULL,
  'sha256',CASE WHEN a.rolpassword IS NULL THEN NULL ELSE encode(sha256(convert_to(a.rolpassword,'UTF8')),'hex') END)
  FROM pg_authid a WHERE a.oid=(SELECT oid FROM worker)),
 'worker_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m WHERE (SELECT oid FROM worker) IN(m.roleid,m.member,m.grantor)),
 'worker_settings',(SELECT jsonb_agg(to_jsonb(s) ORDER BY s.setdatabase,s.setrole) FROM pg_db_role_setting s WHERE s.setrole=(SELECT oid FROM worker)),
 'shape',jsonb_build_object(
  'columns',(SELECT jsonb_agg(jsonb_build_array(t.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)) ORDER BY t.relname,a.attnum)
    FROM targets t JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum),
  'constraints',(SELECT jsonb_agg(jsonb_build_array(t.relname,c.conname,pg_get_constraintdef(c.oid,false),c.convalidated,c.condeferrable,c.condeferred) ORDER BY t.relname,c.conname) FROM targets t JOIN pg_constraint c ON c.conrelid=t.oid),
  'indexes',(SELECT jsonb_agg(jsonb_build_array(t.relname,pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready) ORDER BY t.relname,pg_get_indexdef(i.indexrelid)) FROM targets t JOIN pg_index i ON i.indrelid=t.oid),
  'triggers',(SELECT jsonb_agg(jsonb_build_array(t.tgname,pg_get_triggerdef(t.oid,false),t.tgenabled) ORDER BY t.tgname) FROM trigs t WHERE NOT t.tgisinternal),
  'functions',(SELECT jsonb_agg(pg_get_functiondef(p.oid) ORDER BY n.nspname,p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.oid IN(SELECT oid FROM funcs) AND n.nspname='public'))
);
$state$;
