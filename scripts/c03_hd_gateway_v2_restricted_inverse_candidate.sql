-- WE1 HD-only source-only inverse of exact v2 additive objects.
-- Requires original role/schema absence preimage; no CASCADE and NO legacy
-- table/sequence/schema/function/default ACL changes. Preserve messages.
-- Not authorized for HEL1 execution without independent source/permit.
BEGIN;
REVOKE EXECUTE ON FUNCTION
 aoe2war_social_hd_v2.clan_text(text,text,text,text),
 aoe2war_social_hd_v2.direct_text(text,text,text,integer)
 FROM aoe2war_social_writer;
DROP FUNCTION
 aoe2war_social_hd_v2.clan_text(text,text,text,text),
 aoe2war_social_hd_v2.direct_text(text,text,text,integer) RESTRICT;
REVOKE EXECUTE ON FUNCTION
 aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text),
 aoe2war_social_hd_v2.leaf_ensure_direct_pair(integer,integer,text),
 aoe2war_social_hd_v2.leaf_send_direct(integer,integer,text,integer)
 FROM aoe2war_social_exec_v2;
DROP FUNCTION
 aoe2war_social_hd_v2.leaf_append_clan(integer,integer,text,text),
 aoe2war_social_hd_v2.leaf_ensure_direct_pair(integer,integer,text),
 aoe2war_social_hd_v2.leaf_send_direct(integer,integer,text,integer) RESTRICT;
REVOKE SELECT ON
 aoe2war_social_hd_v2.v_users,
 aoe2war_social_hd_v2.v_clans,
 aoe2war_social_hd_v2.v_clan_members,
 aoe2war_social_hd_v2.v_clan_messages,
 aoe2war_social_hd_v2.v_direct_conversations,
 aoe2war_social_hd_v2.v_direct_messages,
 aoe2war_social_hd_v2.v_direct_participants
 FROM aoe2war_social_exec_v2;
DROP VIEW
 aoe2war_social_hd_v2.v_users,
 aoe2war_social_hd_v2.v_clans,
 aoe2war_social_hd_v2.v_clan_members,
 aoe2war_social_hd_v2.v_clan_messages,
 aoe2war_social_hd_v2.v_direct_conversations,
 aoe2war_social_hd_v2.v_direct_messages,
 aoe2war_social_hd_v2.v_direct_participants RESTRICT;
REVOKE USAGE ON SCHEMA aoe2war_social_hd_v2
 FROM aoe2war_social_writer,aoe2war_social_exec_v2;
DROP SCHEMA aoe2war_social_hd_v2 RESTRICT;
DROP ROLE aoe2war_social_writer;
DROP ROLE aoe2war_social_exec_v2;
COMMIT;
