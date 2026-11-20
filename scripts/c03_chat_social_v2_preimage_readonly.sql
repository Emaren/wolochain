-- No writes. Independent fixed-source preimage witness of actual HEL1 HD.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
DO $we1$
DECLARE n record;
BEGIN
 IF current_database()<>'aoe2hd_db' OR
  NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2hd_user' AND rolcanlogin AND NOT rolsuper) OR
  NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aoe2war_web_prod' AND NOT rolsuper AND NOT rolinherit) OR
  EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('aoe2war_social_writer','aoe2war_social_exec_v2')) OR
  EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='aoe2war_social_hd_v2')
 THEN RAISE EXCEPTION 'WE1_SOCIAL_PREIMAGE_ROLE_OR_DATABASE_DENIED'; END IF;
 FOR n IN
  WITH expected(name,kind,acl) AS (VALUES
   ('users','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clans','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_members','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_messages','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_conversations','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_conversation_participants','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_messages','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('direct_message_drafts','r','{aoe2hd_user=arwdDxt/aoe2hd_user,aoe2war_r25_web_ro=r/aoe2hd_user}'),
   ('clan_messages_id_seq','S',NULL),
   ('direct_conversations_id_seq','S',NULL),
   ('direct_conversation_participants_id_seq','S',NULL),
   ('direct_messages_id_seq','S',NULL))
  SELECT e.name,e.kind,e.acl,c.oid,c.relkind,c.relacl,c.relowner,
   c.relrowsecurity,c.relforcerowsecurity
  FROM expected e LEFT JOIN pg_class c ON c.oid=to_regclass(format('public.%I',e.name))
 LOOP
  IF n.oid IS NULL OR n.relkind::text<>n.kind OR n.relowner<>'aoe2hd_user'::regrole OR
     n.relacl::text IS DISTINCT FROM n.acl OR n.relrowsecurity OR n.relforcerowsecurity
  THEN RAISE EXCEPTION 'WE1_SOCIAL_PREIMAGE_RAW_ACL_DENIED %',n.name; END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_trigger t
  WHERE t.tgenabled IN ('O','A','R') AND NOT t.tgisinternal
   AND t.tgrelid IN (
     SELECT to_regclass(format('public.%I',x))
     FROM unnest(ARRAY['users','clans','clan_members','clan_messages',
      'direct_conversations','direct_conversation_participants',
      'direct_messages','direct_message_drafts']) x))
 THEN RAISE EXCEPTION 'WE1_SOCIAL_UNREVIEWED_TRIGGER'; END IF;
END $we1$;
SELECT 'PASS_WE1_SOCIAL_HD_PREIMAGE';
ROLLBACK;
