-- EXACT WE3 source-review packet SQL. NOT A FINANCIAL INSTALLER OR HEL1 AUTHORIZATION.
-- app-prodn PR #1418 HEAD a3d043c37643d2fad564d0084299329a9a64a0cf
-- doc Git blob c463bf658fef2ebeb890bc71c7abf051c8ae3cdd
-- Only run in an explicitly fresh disposable PostgreSQL cluster under WE1 CI.
BEGIN;
-- PRECONDITIONS: WE1 captures exact pg_authid, pg_auth_members, pg_namespace,
-- pg_database, pg_class, pg_attribute, pg_sequence, pg_proc, pg_trigger,
-- pg_depend, pg_constraint, pg_default_acl, proacl and raw relacl/attacl
-- before any mutation. All expected objects must exist as ordinary HD
-- tables, with no unapproved side-effect triggers, dangerous definer paths,
-- financial foreign-key/trigger descendants or role inheritance.
-- Abort if either principal exists unexpectedly.
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
-- LOGIN intentionally has no password until WE2's separately approved
-- local SCRAM credential/HBA enrollment. No secrets are stored here.
GRANT USAGE ON SCHEMA public TO aoe2war_social_writer;
GRANT SELECT(id,uid,is_admin,verification_method,in_game_name,
  steam_persona_name,created_at)
  ON public.users TO aoe2war_social_writer;
GRANT SELECT(id,slug,status,chat_audience_policy)
  ON public.clans TO aoe2war_social_writer;
GRANT SELECT(clan_id,user_id,status,role)
  ON public.clan_members TO aoe2war_social_writer;
GRANT SELECT(id,clan_id,author_user_id,body,audience,created_at),
  INSERT(clan_id,author_user_id,body,audience,created_at,updated_at)
  ON public.clan_messages TO aoe2war_social_writer;
GRANT SELECT(id,pair_key), INSERT(pair_key,created_at,updated_at),
  UPDATE(updated_at)
  ON public.direct_conversations TO aoe2war_social_writer;
GRANT SELECT(id,conversation_id,user_id),
  INSERT(conversation_id,user_id,joined_at),
  UPDATE(last_read_at,typing_updated_at)
  ON public.direct_conversation_participants TO aoe2war_social_writer;
GRANT SELECT(id,conversation_id,sender_user_id,body,
  reply_to_message_id,created_at),
  INSERT(conversation_id,sender_user_id,body,reply_to_message_id,created_at)
  ON public.direct_messages TO aoe2war_social_writer;
GRANT SELECT(conversation_id,user_id), DELETE
  ON public.direct_message_drafts TO aoe2war_social_writer;
GRANT USAGE ON SEQUENCE public.clan_messages_id_seq,
  public.direct_conversations_id_seq,
  public.direct_conversation_participants_id_seq,
  public.direct_messages_id_seq TO aoe2war_social_writer;
-- Before COMMIT, WE1 MUST assert: role membership empty, no CREATE on
-- any DB/schema, no unexpected SECURITY DEFINER EXECUTE via PUBLIC,
-- no unapproved enabled user triggers/definer/FK-to-finance descendants,
-- no other table/column write, no financial sequence USAGE/UPDATE and
-- no connectivity to DE/other DBs. A test-role SELECT of all permitted
-- columns, denial of all others, and transitive side-effect isolation.
-- If ANY unknown: ROLLBACK; HOLD. COMMIT only with signed independent proof.
COMMIT;
