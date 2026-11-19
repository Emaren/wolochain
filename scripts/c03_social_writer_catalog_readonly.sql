-- WE1 C03 SOCIAL SQL FINANCIAL BOUNDARY: READ-ONLY CATALOG WITNESS CANDIDATE.
-- Not an installer, privilege grant, inverse executor, authorization or permit.
-- Requires an existing separately authorized read-only PostgreSQL connection.
-- Execute on BOTH intended HD and protected DE separately, as permitted;
-- independently authenticate/signed-check the whole output, cluster ID,
-- source SHA, pg_hba/systemd and captured ORIGINAL raw catalog preimage.
-- The audit does not resolve dynamic SQL, FDW/dblink, or trigger descendants.
-- Never treat an empty result, absent role or this script's success as ACCEPT.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SET LOCAL lock_timeout = '400ms';
SELECT 'AUDIT_META' AS section, jsonb_build_object(
  'db', current_database(), 'database_oid', (SELECT oid FROM pg_database WHERE datname=current_database()),
  'actor', current_user, 'pg_version', current_setting('server_version'),
  'started_at', pg_postmaster_start_time(), 'snapshot', txid_current_snapshot()::text,
  'transaction_read_only', current_setting('transaction_read_only'),
  'admission', 'HOLD_SOURCE_ONLY') AS result;
SELECT 'ROLE_PREIMAGE' AS section, row_to_json(r) AS result
FROM (
 SELECT oid, rolname, rolcanlogin, rolinherit, rolsuper, rolcreaterole,
        rolcreatedb, rolreplication, rolbypassrls, rolconnlimit,
        rolvaliduntil::text
 FROM pg_roles WHERE rolname IN ('aoe2war_social_writer','aoe2war_web_prod')
 ORDER BY rolname
) r;
SELECT 'ROLE_PRESENCE' AS section, jsonb_build_object(
 'social_writer_absent', NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_writer'),
 'web_prod_present', EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_web_prod')) AS result;
WITH RECURSIVE chain(root_name, root_oid, reached_oid, seen, inherit_path, set_path, depth) AS (
 SELECT r.rolname, r.oid, r.oid, ARRAY[r.oid], true, true, 0
 FROM pg_roles r WHERE r.rolname IN ('aoe2war_social_writer','aoe2war_web_prod')
 UNION ALL
 SELECT ch.root_name,ch.root_oid,m.roleid,ch.seen||m.roleid,
        ch.inherit_path AND m.inherit_option,ch.set_path AND m.set_option,ch.depth+1
 FROM chain ch JOIN pg_auth_members m ON m.member=ch.reached_oid
 WHERE NOT m.roleid=ANY(ch.seen)
)
SELECT 'ROLE_TRANSITIVE_MEMBERSHIP' AS section, row_to_json(v) AS result
FROM (
 SELECT ch.root_name, ch.depth, pg_get_userbyid(ch.reached_oid) AS reachable_role,
        ch.inherit_path, ch.set_path, ch.seen::text AS role_oid_path
 FROM chain ch WHERE ch.depth>0 ORDER BY ch.root_name,ch.depth,ch.reached_oid
) v;
SELECT 'DATABASE_RIGHTS' AS section, row_to_json(v) AS result FROM (
 SELECT r.rolname, current_database() AS db,
        has_database_privilege(r.oid,current_database(),'CONNECT') AS can_connect,
        has_database_privilege(r.oid,current_database(),'CREATE') AS can_create,
        has_database_privilege(r.oid,current_database(),'TEMP') AS can_temp
 FROM pg_roles r WHERE r.rolname IN ('aoe2war_social_writer','aoe2war_web_prod')
 ORDER BY rolname
) v;
SELECT 'PUBLIC_SCHEMA_ACL' AS section, row_to_json(v) AS result FROM (
 SELECT n.oid,n.nspname,pg_get_userbyid(n.nspowner) AS owner,
        n.nspacl::text AS raw_nullable_acl,
        r.rolname,
        has_schema_privilege(r.oid,n.oid,'USAGE') AS can_use,
        has_schema_privilege(r.oid,n.oid,'CREATE') AS can_create
 FROM pg_namespace n CROSS JOIN pg_roles r
 WHERE n.nspname='public' AND r.rolname IN ('aoe2war_social_writer','aoe2war_web_prod')
 ORDER BY r.rolname
) v;
WITH target(relname,category) AS (VALUES
 ('users','identity_read'), ('clans','clan_read'),('clan_members','clan_read'),
 ('clan_messages','social_write'),('direct_conversations','social_write'),
 ('direct_conversation_participants','social_write'),('direct_messages','social_write'),
 ('direct_message_drafts','social_write'),
 ('clan_messages_id_seq','social_sequence'),
 ('direct_conversations_id_seq','social_sequence'),
 ('direct_conversation_participants_id_seq','social_sequence'),
 ('direct_messages_id_seq','social_sequence')
)
SELECT 'NAMED_RELATION_RAW_PREIMAGE' AS section, row_to_json(v) AS result FROM (
 SELECT t.category,t.relname,c.oid, c.relkind,c.relpersistence,
        CASE WHEN c.oid IS NOT NULL THEN pg_get_userbyid(c.relowner) END AS owner,
        c.relacl::text AS raw_nullable_acl,c.relrowsecurity,c.relforcerowsecurity,
        CASE WHEN c.oid IS NULL THEN 'MISSING_RELATION' WHEN c.relkind NOT IN ('r','p','S')
             THEN 'UNEXPECTED_RELKIND' ELSE 'REQUIRES_TRIGGER_DEPENDENCY_REVIEW' END AS review_state
 FROM target t LEFT JOIN pg_class c ON c.oid=to_regclass(format('%I.%I','public',t.relname))
 ORDER BY t.category,t.relname
) v;
WITH names(relname) AS (VALUES
 ('users'),('clans'),('clan_members'),('clan_messages'),
 ('direct_conversations'),('direct_conversation_participants'),
 ('direct_messages'),('direct_message_drafts')
)
SELECT 'COLUMN_RAW_ACL' AS section, row_to_json(v) AS result FROM (
 SELECT c.oid::regclass::text AS relation,a.attnum,a.attname,
        format_type(a.atttypid,a.atttypmod) AS data_type,
        a.attacl::text AS raw_nullable_column_acl,
        a.attgenerated, a.attidentity, a.attnotnull
 FROM names n JOIN pg_class c ON c.oid=to_regclass(format('%I.%I','public',n.relname))
 JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE a.attnum>0 AND NOT a.attisdropped
 ORDER BY relation,a.attnum
) v;
WITH names(relname) AS (VALUES
 ('clan_messages'),('direct_conversations'),
 ('direct_conversation_participants'),('direct_messages'),
 ('direct_message_drafts'),('users'),('clans'),('clan_members')
)
SELECT 'TRIGGER_OWNER_AND_FUNCTION' AS section, row_to_json(v) AS result FROM (
 SELECT c.oid::regclass::text AS relation,t.oid AS trigger_oid,t.tgname,
        t.tgenabled,t.tgisinternal,t.tgtype,
        t.tgfoid::regprocedure::text AS function_identity,
        pg_get_userbyid(p.proowner) AS function_owner,
        p.prosecdef,p.proacl::text AS raw_nullable_function_acl,
        p.proconfig::text AS function_settings,md5(p.prosrc) AS body_md5_diagnostic_only,
        pg_get_triggerdef(t.oid) AS trigger_definition
 FROM names n JOIN pg_class c ON c.oid=to_regclass(format('%I.%I','public',n.relname))
 JOIN pg_trigger t ON t.tgrelid=c.oid
 JOIN pg_proc p ON p.oid=t.tgfoid
 ORDER BY relation,t.oid
) v;
WITH names(relname) AS (VALUES
 ('users'),('clans'),('clan_members'),('clan_messages'),
 ('direct_conversations'),('direct_conversation_participants'),
 ('direct_messages'),('direct_message_drafts')
)
SELECT 'FOREIGN_KEY_DESCENDANT' AS section, row_to_json(v) AS result FROM (
 SELECT con.oid,con.conname,con.conrelid::regclass::text AS source_relation,
        con.confrelid::regclass::text AS referenced_relation,
        con.confupdtype,con.confdeltype,con.condeferrable
 FROM pg_constraint con WHERE con.contype='f'
   AND (con.conrelid IN (SELECT to_regclass(format('%I.%I','public',relname)) FROM names)
        OR con.confrelid IN (SELECT to_regclass(format('%I.%I','public',relname)) FROM names))
 ORDER BY con.conrelid,con.oid
) v;
SELECT 'NON_SYSTEM_SECURITY_DEFINER' AS section, row_to_json(v) AS result FROM (
 SELECT p.oid,p.oid::regprocedure::text AS function_identity,
        n.nspname AS schema,pg_get_userbyid(p.proowner) AS function_owner,
        p.prosecdef,p.proacl::text AS raw_nullable_function_acl,
        p.proconfig::text AS settings,md5(p.prosrc) AS body_md5_diagnostic_only,
        COALESCE((
          SELECT bool_or(e.grantee=0 AND e.privilege_type='EXECUTE')
          FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) e
        ),false) AS public_execute
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
 ORDER BY n.nspname,p.oid
) v;
SELECT 'DEFAULT_GRANTS' AS section, row_to_json(v) AS result FROM (
 SELECT d.oid,pg_get_userbyid(d.defaclrole) AS grantor_owner,
        n.nspname AS schema,d.defaclobjtype,d.defaclacl::text AS raw_nullable_default_acl
 FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
 ORDER BY d.oid
) v;
SELECT 'ROLE_MEMBERSHIP_FULL_RAW' AS section, row_to_json(v) AS result FROM (
 SELECT m.roleid,m.member,m.grantor,m.admin_option,m.inherit_option,m.set_option
 FROM pg_auth_members m
 WHERE m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('aoe2war_social_writer','aoe2war_web_prod'))
 OR m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('aoe2war_social_writer','aoe2war_web_prod'))
 ORDER BY m.member,m.roleid
) v;
SELECT 'FINAL_NONAUTHORIZATION' AS section, jsonb_build_object(
 'audit_only',true,'mutations',false,'admitted_financial_writer_exclusion',false,
 'social_writer_install_authorized',false,
 'transitive_dynamic_sql_and_fdw_proven',false,
 'independent_signed_root_witness_present',false,
 'requires_exact_raw_inverse',true,'funding','DENIED') AS result;
COMMIT;
