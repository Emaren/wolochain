-- WE1 C03 source-only fixed-purpose gateway exact absent-preimage inverse.
-- NOT authorized on HEL1 without a source-/preimage-pinned one-use permit.
-- Requires aoe2war_social_gateway + role were BOTH absent before admission;
-- no unrelated grants, memberships, objects or active sessions since.
-- Do not use CASCADE or touch legacy table/sequence raw ACLs.
BEGIN;
REVOKE EXECUTE ON FUNCTION aoe2war_social_gateway.clan_text(text,text,text,text)
  FROM aoe2war_social_writer;
REVOKE EXECUTE ON FUNCTION aoe2war_social_gateway.direct_text(text,text,text,integer)
  FROM aoe2war_social_writer;
DROP FUNCTION aoe2war_social_gateway.clan_text(text,text,text,text);
DROP FUNCTION aoe2war_social_gateway.direct_text(text,text,text,integer);
REVOKE USAGE ON SCHEMA aoe2war_social_gateway FROM aoe2war_social_writer;
DROP SCHEMA aoe2war_social_gateway RESTRICT;
DROP ROLE aoe2war_social_writer;
COMMIT;
