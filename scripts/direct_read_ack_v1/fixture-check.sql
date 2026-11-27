\set ON_ERROR_STOP on
SET ROLE aoe2war_social_writer;
DO $t$ DECLARE q jsonb; BEGIN
 IF has_table_privilege(current_user,'aoe2war_direct_ack_hd_v1.receipts','SELECT,INSERT,UPDATE,DELETE') OR has_table_privilege(current_user,'public.direct_messages','SELECT,INSERT,UPDATE,DELETE') OR has_table_privilege(current_user,'public.financial_sentinel','SELECT,INSERT,UPDATE,DELETE') THEN RAISE EXCEPTION 'RAW_ACL'; END IF;
 q=aoe2war_direct_read_hd_v1.read_direct('alice','summary',NULL,NULL,NULL,NULL); IF (q#>>'{summary,threads,0,unreadCount}')::int<>2 THEN RAISE EXCEPTION 'BASELINE %',q; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[91,100]); IF (q->>'status')::int<>404 THEN RAISE EXCEPTION 'MIXED_FOREIGN'; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[90]); IF (q->>'status')::int<>404 THEN RAISE EXCEPTION 'OUTGOING'; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','extra',ARRAY[101]); IF (q->>'status')::int<>404 THEN RAISE EXCEPTION 'CORRUPT_PAIR'; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[91,91]); IF (q->>'status')::int<>400 THEN RAISE EXCEPTION 'DUPLICATE'; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[91]); IF (q#>>'{body,updatedCount}')::int<>1 THEN RAISE EXCEPTION 'ACK'; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[91]); IF (q#>>'{body,updatedCount}')::int<>0 THEN RAISE EXCEPTION 'IDEMPOTENCY'; END IF;
 q=aoe2war_direct_read_hd_v1.read_direct('alice','summary',NULL,NULL,NULL,NULL); IF (q#>>'{summary,threads,0,unreadCount}')::int<>1 THEN RAISE EXCEPTION 'SUMMARY'; END IF;
END $t$;
RESET ROLE;
-- Simulate arrival with timestamp older than historical baseline and legacy cursor movement.
INSERT INTO public.direct_messages(id,conversation_id,sender_user_id,body,created_at) VALUES(999,1,2,'late arrival','2000-01-01');
UPDATE public.direct_conversation_participants SET last_read_at='2099-01-01' WHERE conversation_id=1 AND user_id=1;
SET ROLE aoe2war_social_writer;
DO $t$ DECLARE q jsonb; BEGIN
 q=aoe2war_direct_read_hd_v1.read_direct('alice','summary',NULL,NULL,NULL,NULL); IF (q#>>'{summary,threads,0,unreadCount}')::int<>2 THEN RAISE EXCEPTION 'LATE_ARRIVAL_OR_LEGACY_CURSOR %',q; END IF;
 q=aoe2war_direct_ack_hd_v1.direct_read_ack('alice','bob',ARRAY[92,999]); IF (q#>>'{body,updatedCount}')::int<>2 THEN RAISE EXCEPTION 'FINAL_ACK'; END IF;
 q=aoe2war_direct_read_hd_v1.read_direct('alice','summary',NULL,NULL,NULL,NULL); IF (q#>>'{summary,threads,0,unreadCount}')::int<>0 THEN RAISE EXCEPTION 'FINAL_SUMMARY'; END IF;
 q=aoe2war_direct_read_hd_v1.read_direct('bob','summary',NULL,NULL,NULL,NULL); IF (q#>>'{summary,threads,0,unreadCount}')::int<>45 THEN RAISE EXCEPTION 'RECIPIENT_ISOLATION'; END IF;
END $t$;
RESET ROLE;
DO $t$ BEGIN IF has_function_privilege('aoe2war_web_prod','aoe2war_direct_ack_hd_v1.direct_read_ack(text,text,integer[])','EXECUTE') OR has_table_privilege('aoe2war_web_prod','aoe2war_direct_ack_hd_v1.receipts','SELECT,INSERT,UPDATE,DELETE') THEN RAISE EXCEPTION 'WEB_ACL'; END IF; IF (SELECT count(*) FROM public.financial_sentinel)<>1 THEN RAISE EXCEPTION 'FINANCIAL_SENTINEL'; END IF; END $t$;
SELECT 'PASS READ ACK ISOLATED PG16 FIXTURE';
