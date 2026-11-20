-- No writes. Exact intended object/owner/privilege graph after Social V2.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
DO $we1$
DECLARE n record;
BEGIN
 IF current_database()<>'aoe2hd_db' OR
  NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_writer'
    AND rolcanlogin AND NOT rolsuper AND NOT rolinherit AND NOT rolcreatedb
    AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=2) OR
  NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_social_exec_v2'
    AND NOT rolcanlogin AND NOT rolsuper AND NOT rolinherit AND NOT rolcreatedb
    AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) OR
  NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='aoe2war_social_hd_v2' AND nspowner='aoe2hd_user'::regrole) OR
  EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN (
   'aoe2war_social_writer'::regrole,'aoe2war_social_exec_v2'::regrole))
 THEN RAISE EXCEPTION 'WE1_SOCIAL_POST_ROLE_OR_SCHEMA_DENIED'; END IF;
 IF (SELECT count(*) FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
     WHERE ns.nspname='aoe2war_social_hd_v2')<>7 OR
  (SELECT count(*) FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
   WHERE ns.nspname='aoe2war_social_hd_v2' AND c.relkind='v' AND
      c.relowner='aoe2hd_user'::regrole AND c.reloptions @> ARRAY['security_barrier=true'])<>7 OR
  (SELECT count(*) FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
   WHERE ns.nspname='aoe2war_social_hd_v2' AND c.relname IN
    ('v_users','v_clans','v_clan_members','v_clan_messages',
     'v_direct_conversations','v_direct_messages','v_direct_participants'))<>7
 THEN RAISE EXCEPTION 'WE1_SOCIAL_POST_EXACT_VIEW_SET_DENIED'; END IF;
 IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
     WHERE ns.nspname='aoe2war_social_hd_v2')<>5 OR
  (SELECT count(*) FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
   WHERE ns.nspname='aoe2war_social_hd_v2' AND p.prosecdef AND
    ((p.proname IN ('clan_text','direct_text') AND p.proowner='aoe2war_social_exec_v2'::regrole)
     OR (p.proname IN ('leaf_append_clan','leaf_ensure_direct_pair','leaf_send_direct')
         AND p.proowner='aoe2hd_user'::regrole)))<>5
 THEN RAISE EXCEPTION 'WE1_SOCIAL_POST_EXACT_DEFINER_SET_DENIED'; END IF;
 IF NOT has_function_privilege('aoe2war_social_writer',
   'aoe2war_social_hd_v2.clan_text(text,text,text,text)','EXECUTE') OR
  NOT has_function_privilege('aoe2war_social_writer',
   'aoe2war_social_hd_v2.direct_text(text,text,text,integer)','EXECUTE') OR
  has_function_privilege('aoe2war_social_writer',
   'aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text)','EXECUTE') OR
  has_table_privilege('aoe2war_social_writer','public.users','SELECT') OR
  has_table_privilege('aoe2war_social_writer','public.clan_messages','INSERT') OR
  has_table_privilege('aoe2war_social_writer','public.direct_messages','SELECT') OR
  has_sequence_privilege('aoe2war_social_writer','public.direct_messages_id_seq','USAGE') OR
  has_table_privilege('aoe2war_social_exec_v2','public.users','DELETE') OR
  has_table_privilege('aoe2war_social_exec_v2','public.clan_messages','INSERT') OR
  has_sequence_privilege('aoe2war_social_exec_v2','public.direct_messages_id_seq','USAGE') OR
  has_schema_privilege('aoe2war_social_exec_v2','aoe2war_social_hd_v2','CREATE')
 THEN RAISE EXCEPTION 'WE1_SOCIAL_POST_RAW_LEAF_OR_CREATE_PRIVILEGE_DENIED'; END IF;
 FOR n IN SELECT c.oid,c.relname FROM pg_class c
  JOIN pg_namespace ns ON ns.oid=c.relnamespace
  WHERE ns.nspname='public' AND c.relkind IN ('r','p','v','S')
   AND c.relname ~* '(wallet|wager|bet|payout|withdraw|deposit|balance|claim|reserve|ledger|escrow|settlement|trader|order)'
 LOOP
  IF (CASE WHEN (SELECT relkind FROM pg_class WHERE oid=n.oid)='S'
      THEN has_sequence_privilege('aoe2war_social_writer',n.oid,'USAGE') OR
           has_sequence_privilege('aoe2war_social_writer',n.oid,'SELECT') OR
           has_sequence_privilege('aoe2war_social_writer',n.oid,'UPDATE') OR
           has_sequence_privilege('aoe2war_social_exec_v2',n.oid,'USAGE') OR
           has_sequence_privilege('aoe2war_social_exec_v2',n.oid,'UPDATE')
      ELSE has_table_privilege('aoe2war_social_writer',n.oid,'SELECT') OR
           has_table_privilege('aoe2war_social_writer',n.oid,'INSERT') OR
           has_table_privilege('aoe2war_social_writer',n.oid,'UPDATE') OR
           has_table_privilege('aoe2war_social_writer',n.oid,'DELETE') OR
           has_table_privilege('aoe2war_social_exec_v2',n.oid,'SELECT') OR
           has_table_privilege('aoe2war_social_exec_v2',n.oid,'INSERT') OR
           has_table_privilege('aoe2war_social_exec_v2',n.oid,'UPDATE') OR
           has_table_privilege('aoe2war_social_exec_v2',n.oid,'DELETE') END)
  THEN RAISE EXCEPTION 'WE1_SOCIAL_POST_FINANCE_GRANT_DENIED %',n.relname; END IF;
 END LOOP;
END $we1$;
SELECT 'PASS_WE1_SOCIAL_HD_POSTIMAGE';
ROLLBACK;
