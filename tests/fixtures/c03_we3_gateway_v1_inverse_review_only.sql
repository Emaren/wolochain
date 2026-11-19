-- SOURCE-EXACT immutable WE3 PR #1418 head 48dcf1103562e629ffb4b123feb83e9f1bafa185
-- SOURCE REVIEW DOC Git blob 6535da9c8fe7aee8b567e9475ab96619e23634bc
-- DISPOSABLE PG16 ONLY. NOT AN INSTALLER OR FINANCIAL SQL AUTHORIZATION.
BEGIN;
REVOKE EXECUTE ON FUNCTION
  social_gateway_v1.append_clan_message(integer,integer,text,text),
  social_gateway_v1.ensure_direct_pair(integer,integer),
  social_gateway_v1.send_direct_text(integer,integer,text,integer)
  FROM aoe2war_social_writer;
REVOKE SELECT ON social_gateway_v1.users,
  social_gateway_v1.clans,social_gateway_v1.clan_members,
  social_gateway_v1.clan_messages,social_gateway_v1.direct_messages
  FROM aoe2war_social_writer;
REVOKE USAGE ON SCHEMA social_gateway_v1 FROM aoe2war_social_writer;
DROP FUNCTION
  social_gateway_v1.append_clan_message(integer,integer,text,text),
  social_gateway_v1.ensure_direct_pair(integer,integer),
  social_gateway_v1.send_direct_text(integer,integer,text,integer)
  RESTRICT;
DROP VIEW social_gateway_v1.users,social_gateway_v1.clans,
  social_gateway_v1.clan_members,social_gateway_v1.clan_messages,
  social_gateway_v1.direct_messages RESTRICT;
DROP SCHEMA social_gateway_v1 RESTRICT;
DROP ROLE aoe2war_social_writer; -- requires exact new role/no foreign dependencies
-- Compare ALL original raw SQL/catalog preimages and data after COMMIT.
COMMIT;
