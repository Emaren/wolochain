-- C02 FINANCIAL source-only integration candidate, deliberate HOLD.
-- Canonical B App PR #1283 HEAD a070e0e70bad0f000f2aa24929265acb6f82e5b2
-- Original 13 historical migrations + 14th native journal are NOT installed on HEL1.
-- Execution deliberately raises 42501 BEFORE DDL. Owner/Central must separately
-- authorize exact runnable source, historical immutability and native worker roles.
BEGIN;
DO $REQUIRES_C02_PRODUCTION_ADMISSION$ BEGIN
 RAISE EXCEPTION 'HOLD:C02_NO_EXACT_SOURCE_SIGNED_OWNER_MAINTENANCE_PERMIT' USING ERRCODE='42501';
END $REQUIRES_C02_PRODUCTION_ADMISSION$;
-- Confirm actual original historic TABLE/trigger preimage separately:
-- war_satchel_wager_authority_admission BEFORE INSERT enforces
-- reservation owner, request, snapshot identity and amount; immutable
-- source triggers must remain ENABLED and owned by non-worker authority.
-- CREATE SCHEMA c02_internal and c02_row_lock NOLOGIN NOINHERIT, if absent,
-- must be owner-approved in the B 13+14 actual migration chain.
-- Prerequisite privileges: c02_row_lock only SELECT on a/b/r, UPDATE of
-- a.operation_id, b.operation_id and r.id to perform FOR SHARE; no LOGIN.
-- c02_journal_worker: EXECUTE on this fn and insert-only native journal,
-- no UPDATE/DELETE on historic a/b/r; no role membership/SET ROLE.
CREATE FUNCTION c02_internal.matches_original_funding(
       p_operation_id varchar(128),p_owner integer,p_hash varchar(64),
       p_ticket integer,p_amount bigint) RETURNS boolean
     LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $F$
    DECLARE a_owner integer;b_hash varchar(64);
      r_ticket integer;r_status varchar(24);r_owner integer;
      r_request varchar(128);r_amount bigint;r_hash varchar(64);
    BEGIN
      SELECT a.owner_user_id,b.tx_hash,r.ticket_id,r.status,
             r.owner_user_id,r.ticket_request_id,r.amount_uwolo,r.tx_hash
      INTO a_owner,b_hash,r_ticket,r_status,r_owner,
           r_request,r_amount,r_hash
      FROM public.war_satchel_wager_authorizations a
      JOIN public.war_satchel_wager_broadcasts b
        ON b.operation_id=a.operation_id
      JOIN public.war_satchel_funded_reservations r
        ON r.id=a.reservation_id
      WHERE a.operation_id=p_operation_id FOR SHARE OF a,b,r;
      RETURN a_owner IS NOT DISTINCT FROM p_owner
       AND r_owner IS NOT DISTINCT FROM p_owner
       AND b_hash IS NOT DISTINCT FROM p_hash
       AND r_hash IS NOT DISTINCT FROM p_hash
       AND r_ticket IS NOT DISTINCT FROM p_ticket
       AND r_request IS NOT DISTINCT FROM p_operation_id
       AND r_amount IS NOT DISTINCT FROM p_amount
       AND r_status IS NOT DISTINCT FROM 'committed';
    END $F$;
ALTER FUNCTION c02_internal.matches_original_funding(varchar,integer,varchar,integer,bigint) OWNER TO c02_row_lock;
REVOKE ALL ON FUNCTION c02_internal.matches_original_funding(varchar,integer,varchar,integer,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION c02_internal.matches_original_funding(varchar,integer,varchar,integer,bigint) TO c02_journal_worker;
-- No financial writer fence, no role enrollment, no 8092/8094, no funded POST.
COMMIT;
