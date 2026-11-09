BEGIN READ ONLY;
WITH roles AS (
  SELECT oid, rolname
  FROM pg_roles
  WHERE rolname IN (
    'aoe2hd_user',
    'aoe2de_user',
    'aoe2war_auth_owner',
    'aoe2war_web_prod',
    'aoe2war_r25_web_ro'
  )
)
SELECT 'SCHEMA_EFFECTIVE|'||r.rolname||'|'||md5(string_agg(n.nspname||'|U:'||has_schema_privilege(r.oid,n.oid,'USAGE')||'|C:'||has_schema_privilege(r.oid,n.oid,'CREATE'),E'\n' ORDER BY n.nspname))
FROM roles r CROSS JOIN pg_namespace n WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema' GROUP BY r.rolname ORDER BY r.rolname;
WITH roles AS (
  SELECT oid, rolname
  FROM pg_roles
  WHERE rolname IN (
    'aoe2hd_user',
    'aoe2de_user',
    'aoe2war_auth_owner',
    'aoe2war_web_prod',
    'aoe2war_r25_web_ro'
  )
)
SELECT 'REL_EFFECTIVE|'||r.rolname||'|'||md5(string_agg(n.nspname||'.'||c.relname||'|'||c.relkind::text||'|R:'||(CASE WHEN c.relkind='S' THEN has_sequence_privilege(r.oid,c.oid,'SELECT') ELSE has_table_privilege(r.oid,c.oid,'SELECT') END)||'|W:'||(CASE WHEN c.relkind='S' THEN has_sequence_privilege(r.oid,c.oid,'UPDATE') ELSE has_table_privilege(r.oid,c.oid,'UPDATE') END)||'|I:'||(CASE WHEN c.relkind='S' THEN has_sequence_privilege(r.oid,c.oid,'USAGE') ELSE has_table_privilege(r.oid,c.oid,'INSERT') END)||'|D:'||(CASE WHEN c.relkind='S' THEN false ELSE has_table_privilege(r.oid,c.oid,'DELETE') END),E'\n' ORDER BY n.nspname,c.relname,c.relkind))
FROM roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema' AND c.relkind IN ('r','p','S','v','m','f') GROUP BY r.rolname ORDER BY r.rolname;
WITH roles AS (
  SELECT oid, rolname
  FROM pg_roles
  WHERE rolname IN (
    'aoe2hd_user',
    'aoe2de_user',
    'aoe2war_auth_owner',
    'aoe2war_web_prod',
    'aoe2war_r25_web_ro'
  )
)
SELECT 'FUNCTION_EFFECTIVE|'||r.rolname||'|'||coalesce(md5(string_agg(n.nspname||'.'||p.proname||'('||pg_get_function_identity_arguments(p.oid)||')|X:'||has_function_privilege(r.oid,p.oid,'EXECUTE'),E'\n' ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid))),'EMPTY')
FROM roles r CROSS JOIN pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema' GROUP BY r.rolname ORDER BY r.rolname;
COMMIT;
