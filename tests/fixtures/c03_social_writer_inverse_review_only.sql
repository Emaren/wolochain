-- EXACT WE3 source-review packet inverse SQL. NOT A PRODUCTION ROLLBACK PERMIT.
-- app-prodn PR#1418 HEAD a3d043c37643d2fad564d0084299329a9a64a0cf
-- doc Git blob c463bf658fef2ebeb890bc71c7abf051c8ae3cdd
-- Execute only against a freshly generated synthetic PostgreSQL16 fixture.
BEGIN;
REVOKE USAGE ON SEQUENCE public.clan_messages_id_seq,
  public.direct_conversations_id_seq,
  public.direct_conversation_participants_id_seq,
  public.direct_messages_id_seq FROM aoe2war_social_writer;
REVOKE SELECT(conversation_id,user_id),DELETE
  ON public.direct_message_drafts FROM aoe2war_social_writer;
REVOKE SELECT(id,conversation_id,sender_user_id,body,reply_to_message_id,created_at),
  INSERT(conversation_id,sender_user_id,body,reply_to_message_id,created_at)
  ON public.direct_messages FROM aoe2war_social_writer;
REVOKE SELECT(id,conversation_id,user_id),INSERT(conversation_id,user_id,joined_at),
  UPDATE(last_read_at,typing_updated_at)
  ON public.direct_conversation_participants FROM aoe2war_social_writer;
REVOKE SELECT(id,pair_key),INSERT(pair_key,created_at,updated_at),UPDATE(updated_at)
  ON public.direct_conversations FROM aoe2war_social_writer;
REVOKE SELECT(id,clan_id,author_user_id,body,audience,created_at),
  INSERT(clan_id,author_user_id,body,audience,created_at,updated_at)
  ON public.clan_messages FROM aoe2war_social_writer;
REVOKE SELECT(clan_id,user_id,status,role)
  ON public.clan_members FROM aoe2war_social_writer;
REVOKE SELECT(id,slug,status,chat_audience_policy)
  ON public.clans FROM aoe2war_social_writer;
REVOKE SELECT(id,uid,is_admin,verification_method,in_game_name,
  steam_persona_name,created_at)
  ON public.users FROM aoe2war_social_writer;
REVOKE USAGE ON SCHEMA public FROM aoe2war_social_writer;
DROP ROLE aoe2war_social_writer; -- never CASCADE
COMMIT;
