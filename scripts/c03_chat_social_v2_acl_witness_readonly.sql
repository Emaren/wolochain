-- Exact read-only fingerprint of the 8 legacy Social tables, 4 sequences,
-- and every surviving original column ACL. Run before/after fixed SQL.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10000ms';
SELECT 'rel|'||c.relname||'|'||c.relkind::text||'|'||
       pg_get_userbyid(c.relowner)||'|'||
       COALESCE(c.relacl::text,'<NULL>')||'|'||
       c.relrowsecurity::text||'|'||c.relforcerowsecurity::text
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN (
 'users','clans','clan_members','clan_messages',
 'direct_conversations','direct_conversation_participants',
 'direct_messages','direct_message_drafts',
 'clan_messages_id_seq','direct_conversations_id_seq',
 'direct_conversation_participants_id_seq','direct_messages_id_seq')
ORDER BY c.relname;
SELECT 'column|'||c.relname||'|'||a.attnum::text||'|'||
       a.attname||'|'||COALESCE(a.attacl::text,'<NULL>')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid
WHERE n.nspname='public' AND c.relname IN (
 'users','clans','clan_members','clan_messages',
 'direct_conversations','direct_conversation_participants',
 'direct_messages','direct_message_drafts')
 AND a.attnum>0 AND NOT a.attisdropped
ORDER BY c.relname,a.attnum;
ROLLBACK;
