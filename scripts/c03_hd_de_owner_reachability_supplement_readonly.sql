-- WE1 C03 2026-11-19: targeted SUPPLEMENTARY READ ONLY ROLE/FUNCTION
-- authority graph. DOES NOT repeat the original full HD/DE catalog.
-- Run only through explicitly owner-present existing postgres peer/sudo.
-- No HBA/role/ACL/data alteration; output is PRIVATE off GitHub/PRs.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='12000ms';
SET LOCAL lock_timeout='400ms';
SELECT 'SUPPLEMENT_META' AS section,jsonb_build_object(
 'db',current_database(),'actor',current_user,
 'pg',current_setting('server_version'),'read_only',
 current_setting('transaction_read_only'),'timestamp',now(),
 'postmaster_start',pg_postmaster_start_time(),
 'purpose','EXACT_OWNER_PRIVILEGE_FUNCTION_AND_LIBRARY_READ_HOLD') AS result;
SELECT 'TARGET_ROLE' AS section,row_to_json(t) AS result
FROM (
 SELECT r.oid::text,r.rolname,r.rolsuper,r.rolinherit,r.rolcanlogin,
   r.rolcreaterole,r.rolcreatedb,r.rolreplication,r.rolbypassrls,
   r.rolconnlimit
 FROM pg_roles r WHERE r.rolname IN (
   'aoe2hd_user','aoe2de_user','aoe2war_web_prod',
   'aoe2war_r25_web_ro','aoe2war_auth_owner',
   'aoe2war_social_writer','aoe2war_social_exec_v2')
 ORDER BY r.rolname
) t;
WITH RECURSIVE roots AS (
 SELECT oid,rolname FROM pg_roles WHERE rolname IN (
 'aoe2hd_user','aoe2de_user','aoe2war_web_prod','aoe2war_auth_owner')
), memberships AS (
 SELECT roots.oid AS root_oid,roots.rolname AS root_name,roots.oid AS reached_oid,
  ARRAY[roots.oid] AS path,0 AS depth,true AS inherit_path,true AS set_path
 FROM roots
 UNION ALL
 SELECT m.root_oid,m.root_name,g.roleid,m.path||g.roleid,m.depth+1,
        m.inherit_path AND g.inherit_option,
        m.set_path AND g.set_option
 FROM memberships m JOIN pg_auth_members g ON g.member=m.reached_oid
 WHERE NOT g.roleid=ANY(m.path) AND m.depth<30
)
SELECT 'OWNER_ROLE_CLOSURE' AS section,row_to_json(t) AS result
FROM (
 SELECT root_name,pg_get_userbyid(reached_oid) reachable_role,depth,
  inherit_path,set_path,path::text AS oid_path
 FROM memberships ORDER BY root_name,depth,reached_oid
) t;
-- Every HD/DE owner finance reachability must be visible in this graph.
SELECT 'FINANCE_ROLE_RELATION' AS section,row_to_json(t) AS result
FROM (
 SELECT n.nspname,c.relname,c.oid::text AS oid,c.relkind::text AS relkind,
   pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS raw_nullable_acl,
   r.rolname,
   CASE WHEN c.relkind='S' THEN NULL
       ELSE has_table_privilege(r.oid,c.oid,'SELECT') END can_select,
   CASE WHEN c.relkind='S' THEN NULL
       ELSE has_table_privilege(r.oid,c.oid,'INSERT') END can_insert,
   CASE WHEN c.relkind='S' THEN NULL
       ELSE has_table_privilege(r.oid,c.oid,'UPDATE') END can_update,
   CASE WHEN c.relkind='S' THEN NULL
       ELSE has_table_privilege(r.oid,c.oid,'DELETE') END can_delete,
   CASE WHEN c.relkind='S' THEN NULL
       ELSE has_table_privilege(r.oid,c.oid,'TRUNCATE') END can_truncate,
   CASE WHEN c.relkind<>'S' THEN NULL
       ELSE has_sequence_privilege(r.oid,c.oid,'USAGE') END seq_usage,
   CASE WHEN c.relkind<>'S' THEN NULL
       ELSE has_sequence_privilege(r.oid,c.oid,'UPDATE') END seq_update
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 CROSS JOIN pg_roles r
 WHERE r.rolname IN ('aoe2hd_user','aoe2de_user','aoe2war_web_prod')
  AND c.relkind IN ('r','p','S','f')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND (c.relname ~* '(^bet_|^staking_|^wallet|^trophy_payout|^bounty_claim|^warrior_claim|^financial_|^reserves?|^payout_|^custody|^settle|^claims?_.*payout)'
       OR c.relowner IN (
         SELECT oid FROM pg_roles WHERE rolname IN ('aoe2hd_user','aoe2de_user'))
          AND c.relname ~* '(claim|stake|wager|escrow|wallet|reward|payout)')
 ORDER BY c.relname,r.rolname
) t;
-- Function metadata, PUBLIC vs targeted owner ability, and source fingerprint.
-- Do not claim absence of dynamic SQL from metadata fingerprints alone.
SELECT 'NON_SYSTEM_FUNCTION_AUTH' AS section,row_to_json(t) AS result
FROM (
 SELECT p.oid::text AS oid,n.nspname,p.proname,
  p.oid::regprocedure::text AS identity,
  pg_get_userbyid(p.proowner) owner,p.prosecdef,p.prokind,
  p.proacl::text AS raw_nullable_acl,
  p.proconfig::text AS settings,
  has_function_privilege('public',p.oid,'EXECUTE') public_execute,
  CASE WHEN EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2hd_user')
    THEN has_function_privilege('aoe2hd_user',p.oid,'EXECUTE') END hd_owner_execute,
  CASE WHEN EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2de_user')
    THEN has_function_privilege('aoe2de_user',p.oid,'EXECUTE') END de_owner_execute,
  md5(coalesce(p.prosrc,'')) source_md5_diagnostic_only,
  (p.prosrc ~* '\mEXECUTE\M|\mdblink\M|\mlo_import\M|\mCOPY\M|\mALTER\M|\mDELETE\M|\mUPDATE\M|\mINSERT\M')
   AS possibly_dynamic_or_writing_source
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE p.prokind IN ('f','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
 ORDER BY n.nspname,p.proname,p.oid
) t;
SELECT 'EVENT_TRIGGER_AUTH' AS section,row_to_json(t) AS result
FROM (
 SELECT e.evtname,e.evtevent,e.evtenabled,e.evtfoid::regprocedure::text AS function_identity,
        pg_get_userbyid(p.proowner) function_owner,p.prosecdef,p.proacl::text raw_function_acl
 FROM pg_event_trigger e JOIN pg_proc p ON p.oid=e.evtfoid
 ORDER BY e.evtname
) t;
SELECT 'FOREIGN_TABLE_AUTH' AS section,row_to_json(t) AS result
FROM (
 SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner,
  srv.srvname,fdw.fdwname
 FROM pg_foreign_table ft JOIN pg_class c ON c.oid=ft.ftrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_foreign_server srv ON srv.oid=ft.ftserver
 JOIN pg_foreign_data_wrapper fdw ON fdw.oid=srv.srvfdw
 ORDER BY n.nspname,c.relname
) t;
SELECT 'LIBRARY_RELATION_PREIMAGE' AS section,row_to_json(t) AS result
FROM (
 SELECT x.relname,c.oid::text AS oid,c.relkind::text relkind,
  pg_get_userbyid(c.relowner) owner,c.relacl::text raw_nullable_acl,
  c.relrowsecurity,c.relforcerowsecurity,
  has_table_privilege('aoe2war_web_prod',c.oid,'SELECT') web_select
 FROM (VALUES ('user_activity_events'),('watcher_client_events')) x(relname)
 LEFT JOIN pg_class c ON c.oid=to_regclass(format('public.%I',x.relname))
 ORDER BY x.relname
) t;
SELECT 'LIBRARY_COLUMN_PREIMAGE' AS section,row_to_json(t) AS result
FROM (
 SELECT c.relname,a.attnum,a.attname,
  format_type(a.atttypid,a.atttypmod) AS data_type,
  a.attacl::text AS raw_nullable_attacl
 FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE c.oid IN (to_regclass('public.user_activity_events'),
                 to_regclass('public.watcher_client_events'))
   AND a.attnum>0 AND NOT a.attisdropped
 ORDER BY c.relname,a.attnum
) t;
SELECT 'SUPPLEMENT_FINAL' AS section,jsonb_build_object(
 'db',current_database(),'read_only',current_setting('transaction_read_only'),
 'source_only',true,'live_sql_installer_authorized',false,
 'funding_authorized',false,'user_confirmation_required',true
) AS result;
COMMIT;
