-- Source-only read-only witness; no production authority is conferred.
BEGIN READ ONLY;
SET LOCAL lock_timeout='350ms';
SET LOCAL statement_timeout='5s';
SELECT current_database() AS database_name, current_setting('server_version_num') AS server_version;
SELECT rolname,rolcanlogin,rolsuper,rolinherit,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname IN ('aoe2hd_user','aoe2war_social_writer','aoe2war_web_prod') ORDER BY rolname;
SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.relacl,pg_total_relation_size(c.oid) AS bytes FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('users','direct_conversations','direct_conversation_participants','direct_messages') ORDER BY c.relname;
SELECT n.nspname,p.proname,pg_get_userbyid(p.proowner) AS owner,p.prosecdef,p.provolatile,p.proconfig,p.proacl,encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex') AS definition_sha256 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('aoe2war_direct_read_hd_v1','aoe2war_direct_ack_hd_v1') ORDER BY n.nspname,p.proname;
SELECT count(*) AS bounded_seed_rows FROM (SELECT m.id FROM public.direct_messages m JOIN public.direct_conversations d ON d.id=m.conversation_id JOIN public.direct_conversation_participants me ON me.conversation_id=d.id JOIN public.direct_conversation_participants them ON them.conversation_id=d.id AND them.user_id=m.sender_user_id AND them.user_id<>me.user_id WHERE d.pair_key=least(me.user_id,them.user_id)::text||':'||greatest(me.user_id,them.user_id)::text AND (SELECT count(*) FROM public.direct_conversation_participants p WHERE p.conversation_id=d.id)=2 AND m.created_at<=me.last_read_at LIMIT 100001) q;
ROLLBACK;
