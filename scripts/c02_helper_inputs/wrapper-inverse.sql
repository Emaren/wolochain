-- C02 V2 wrapper replacement/inverse; no owner/OID/ACL/trigger mutation.
-- Preserves original raw NULL or non-NULL proacl, including old PUBLIC EXECUTE.
-- Private schema USAGE and helper EXECUTE are separately enrolled prerequisites.
-- No real matcher session_user check is assumed; its ACLs supply the boundary.
-- Requires accepted writer/DDL exclusion and a fresh exact finance source permit.
BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='300ms';
DO $C02_V2_NOT_ADMITTED$ BEGIN
 RAISE EXCEPTION 'HOLD:C02_V2_EXACT_SOURCE_OWNER_AND_MAINTENANCE_NOT_ADMITTED' USING ERRCODE='42501';
END $C02_V2_NOT_ADMITTED$;
DO $c02contract$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner
 WHERE p.oid='c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)'::regprocedure
 AND owner.rolname='c02_row_lock' AND NOT owner.rolcanlogin AND NOT owner.rolinherit
 AND NOT owner.rolsuper AND NOT owner.rolcreaterole AND p.prosecdef
 AND p.proconfig=ARRAY['search_path=pg_catalog']::text[]
 AND p.proargnames=ARRAY['p_operation_id','p_owner','p_hash','p_ticket','p_amount']::text[]
 AND p.prolang=(SELECT oid FROM pg_catalog.pg_language WHERE lanname='plpgsql')
 AND p.prorettype='boolean'::regtype AND NOT p.proretset AND p.prokind='f'
 AND p.pronargs=5 AND p.pronargdefaults=0 AND p.proargdefaults IS NULL
 AND p.proargmodes IS NULL AND p.provariadic=0 AND NOT p.proisstrict
 AND NOT p.proleakproof AND p.provolatile='v' AND p.proparallel='u' AND p.prosupport=0::oid
 AND p.prosrc=$c02helper$
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
    END $c02helper$
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) x WHERE x.grantee=0 AND x.privilege_type='EXECUTE'))
 OR EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n,
 LATERAL pg_catalog.aclexplode(COALESCE(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) x
 WHERE n.nspname='c02_internal' AND ((x.grantee=0 AND x.privilege_type='USAGE') OR (x.privilege_type='CREATE' AND x.grantee<>n.nspowner)))
 OR (SELECT nspowner FROM pg_catalog.pg_namespace WHERE nspname='c02_internal') IS DISTINCT FROM (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='c02_row_lock')
 OR pg_catalog.has_function_privilege('aoe2war_web_prod','c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)','EXECUTE')
 OR pg_catalog.pg_has_role('c02_journal_worker','c02_row_lock','MEMBER')
 OR pg_catalog.pg_has_role('aoe2war_web_prod','c02_row_lock','MEMBER')
 THEN RAISE EXCEPTION 'C02_PRIVATE_HELPER_SOURCE_AUTHORITY_NOT_EXACT' USING ERRCODE='42501'; END IF;

 IF (SELECT prosrc FROM pg_catalog.pg_proc WHERE oid='public.war_satchel_native_source_admission()'::regprocedure)
 IS DISTINCT FROM $c02expected$
BEGIN
 IF NOT COALESCE(c02_internal.matches_original_funding(
   NEW.wager_operation_id,
   NEW.owner_user_id,
   NEW.funding_tx_hash,
   NEW.ticket_id,
   NEW.funded_amount_uwolo
 ),false) THEN
  RAISE EXCEPTION 'C02_AUTHENTICATED_FRESH_WAGER_FUNDING_REQUIRED'
   USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END;
$c02expected$
 OR (SELECT proconfig FROM pg_catalog.pg_proc WHERE oid='public.war_satchel_native_source_admission()'::regprocedure)
 IS DISTINCT FROM ARRAY['search_path=pg_catalog']::text[]
 THEN RAISE EXCEPTION 'C02_EXACT_FUNCTION_SOURCE_CONFIG_PREIMAGE_REQUIRED' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_class c
 ON c.oid='public.war_satchel_native_return_operations'::regclass
 JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner
 WHERE p.oid='public.war_satchel_native_source_admission()'::regprocedure
 AND p.proowner=c.relowner AND NOT p.prosecdef
 AND NOT owner.rolcanlogin AND NOT owner.rolsuper AND NOT owner.rolcreaterole
 AND NOT pg_catalog.pg_has_role('c02_journal_worker',p.proowner,'MEMBER')
 AND NOT pg_catalog.pg_has_role('aoe2war_web_prod',p.proowner,'MEMBER'))
 THEN RAISE EXCEPTION 'C02_RESTRICTED_FINANCE_OWNER_PREIMAGE_REQUIRED' USING ERRCODE='42501'; END IF;

 IF NOT pg_catalog.has_schema_privilege('c02_journal_worker','c02_internal','USAGE')
 OR NOT pg_catalog.has_function_privilege('c02_journal_worker','c02_internal.matches_original_funding(character varying,integer,character varying,integer,bigint)','EXECUTE')
 THEN RAISE EXCEPTION 'C02_PRIVATE_HELPER_ENROLLMENT_MISSING' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger t
 WHERE t.tgrelid='public.war_satchel_native_return_operations'::regclass
 AND t.tgname='c02_original_funding_bound' AND t.tgtype=7 AND t.tgenabled='O'
 AND t.tgfoid='public.war_satchel_native_source_admission()'::regprocedure)
 THEN RAISE EXCEPTION 'C02_EXISTING_NATIVE_TRIGGER_PREIMAGE_REQUIRED' USING ERRCODE='42501'; END IF;
END $c02contract$;
CREATE TEMP TABLE c02_wrapper_preimage ON COMMIT DROP AS
SELECT pg_catalog.to_jsonb(p)-ARRAY['prosrc','proconfig'] metadata,
 (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(t) ORDER BY t.oid)
 FROM pg_catalog.pg_trigger t WHERE t.tgfoid=p.oid) triggers
FROM pg_catalog.pg_proc p WHERE p.oid='public.war_satchel_native_source_admission()'::regprocedure;
CREATE OR REPLACE FUNCTION public.war_satchel_native_source_admission() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $native_source$
DECLARE owner_id integer; linked_hash varchar(64); linked_ticket integer;
  linked_status varchar(24);
BEGIN
 SELECT a.owner_user_id, b.tx_hash, r.ticket_id, r.status
 INTO owner_id, linked_hash, linked_ticket, linked_status
 FROM public.war_satchel_wager_authorizations a
 JOIN public.war_satchel_wager_broadcasts b ON b.operation_id=a.operation_id
 JOIN public.war_satchel_funded_reservations r ON r.id=a.reservation_id
 WHERE a.operation_id=NEW.wager_operation_id FOR SHARE OF a,b,r;
 IF owner_id IS DISTINCT FROM NEW.owner_user_id
    OR linked_hash IS DISTINCT FROM NEW.funding_tx_hash
    OR linked_ticket IS DISTINCT FROM NEW.ticket_id
    OR linked_status IS DISTINCT FROM 'committed'
    OR NOT EXISTS (
      SELECT 1 FROM public.war_satchel_funded_reservations
      WHERE ticket_request_id=NEW.wager_operation_id
        AND amount_uwolo=NEW.funded_amount_uwolo
        AND tx_hash=NEW.funding_tx_hash
    ) THEN
   RAISE EXCEPTION 'C02_AUTHENTICATED_FRESH_WAGER_FUNDING_REQUIRED';
 END IF;
 RETURN NEW;
END;
$native_source$;

DO $c02post$ BEGIN
 IF (SELECT pg_catalog.to_jsonb(p)-ARRAY['prosrc','proconfig'] FROM pg_catalog.pg_proc p
 WHERE p.oid='public.war_satchel_native_source_admission()'::regprocedure)
 IS DISTINCT FROM (SELECT metadata FROM pg_temp.c02_wrapper_preimage)
 OR (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(t) ORDER BY t.oid)
 FROM pg_catalog.pg_trigger t WHERE t.tgfoid='public.war_satchel_native_source_admission()'::regprocedure)
 IS DISTINCT FROM (SELECT triggers FROM pg_temp.c02_wrapper_preimage)
 THEN RAISE EXCEPTION 'C02_ORIGINAL_IDENTITY_RAW_ACL_OR_TRIGGER_CHANGED' USING ERRCODE='42501'; END IF;
END $c02post$;
COMMIT;
