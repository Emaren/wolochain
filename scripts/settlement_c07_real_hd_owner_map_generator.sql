WITH commands AS (
 SELECT 0 AS ord, '0'::text AS key,
    format('ALTER DATABASE %I OWNER TO %I;', 'c07_hd_isolated',pg_get_userbyid(d.datdba)) AS cmd
 FROM pg_database d WHERE d.datname=current_database()
 UNION ALL
 SELECT 1,n.nspname,format('ALTER SCHEMA %I OWNER TO %I;',n.nspname,pg_get_userbyid(n.nspowner))
 FROM pg_namespace n WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema'
 UNION ALL
 SELECT 2,n.nspname||'.'||c.relname,
    format('ALTER %s %I.%I OWNER TO %I;',
      CASE c.relkind WHEN 'r' THEN 'TABLE' WHEN 'p' THEN 'TABLE'
           WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW'
           WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE' END,
      n.nspname,c.relname,pg_get_userbyid(c.relowner))
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema' AND c.relkind IN ('r','p','S','v','m','f')
 UNION ALL
 SELECT 3,n.nspname||'.'||p.proname||'.'||p.oid::text,
    format('ALTER %s %I.%I(%s) OWNER TO %I;',
      CASE p.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END,
      n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner))
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname!='information_schema'
)
SELECT cmd FROM (
 SELECT -1 AS ord, ''::text AS key, 'BEGIN;' AS cmd
 UNION ALL
 SELECT ord,key,cmd FROM commands
 UNION ALL
 SELECT 99 AS ord, ''::text AS key, 'COMMIT;' AS cmd
) x ORDER BY ord,key;
