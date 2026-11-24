-- Catalog-only witness, no player rows or raw credentials in output. FDW options are hashed, never printed.
-- One scalar JSON result. Include all user schemas, not only names matching finance.
WITH
ns AS (
 SELECT oid,nspname,nspowner,nspacl FROM pg_namespace
 WHERE nspname NOT IN ('pg_catalog','information_schema') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp_%'
),
rel AS (
 SELECT c.*,n.nspname,
 (n.nspname='aoe2war_social_hd_v2' AND (c.relname IN ('image_request_keys','v_direct_text_ids') OR EXISTS(SELECT 1 FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid WHERE i.indexrelid=c.oid AND t.relnamespace=n.oid AND t.relname='image_request_keys'))) AS new_media
 FROM pg_class c JOIN ns n ON n.oid=c.relnamespace
),
fn AS (
 SELECT p.*,n.nspname,
 (n.nspname='aoe2war_social_hd_v2' AND p.proname IN ('direct_image','leaf_send_direct_image','direct_delivered','leaf_ack_direct_delivery')) AS new_media,
 (n.nspname='aoe2war_social_hd_v2' AND p.oid=to_regprocedure('aoe2war_social_hd_v2.direct_text(text,text,text,integer)')) AS text_delta
 FROM pg_proc p JOIN ns n ON n.oid=p.pronamespace
),
types AS (
 SELECT t.*,coalesce(r.new_media,false) OR EXISTS(SELECT 1 FROM pg_type e JOIN rel q ON q.oid=e.typrelid WHERE e.oid=t.typelem AND q.new_media) AS new_media
 FROM pg_type t JOIN ns n ON n.oid=t.typnamespace LEFT JOIN rel r ON r.oid=t.typrelid
),
objects AS (
 SELECT 'pg_class'::regclass::oid classid,oid objid,new_media FROM rel
 UNION ALL SELECT 'pg_proc'::regclass::oid,oid,new_media FROM fn
 UNION ALL SELECT 'pg_type'::regclass::oid,oid,new_media FROM types
 UNION ALL SELECT 'pg_constraint'::regclass::oid,c.oid,coalesce(r.new_media,false) FROM pg_constraint c JOIN ns n ON n.oid=c.connamespace LEFT JOIN rel r ON r.oid=c.conrelid
 UNION ALL SELECT 'pg_rewrite'::regclass::oid,t.oid,r.new_media FROM pg_rewrite t JOIN rel r ON r.oid=t.ev_class
 UNION ALL SELECT 'pg_trigger'::regclass::oid,t.oid,r.new_media FROM pg_trigger t JOIN rel r ON r.oid=t.tgrelid
 UNION ALL SELECT 'pg_attrdef'::regclass::oid,t.oid,r.new_media FROM pg_attrdef t JOIN rel r ON r.oid=t.adrelid
 UNION ALL SELECT 'pg_policy'::regclass::oid,t.oid,r.new_media FROM pg_policy t JOIN rel r ON r.oid=t.polrelid
 UNION ALL SELECT 'pg_namespace'::regclass::oid,oid,false FROM ns
),
items AS (
 SELECT 'cluster_identity' k,'fixed' id,jsonb_build_array((SELECT system_identifier::text FROM pg_control_system()),pg_postmaster_start_time(),current_database(),current_setting('server_version_num'),current_setting('data_directory'),current_setting('hba_file'),current_setting('port'),current_setting('unix_socket_directories'),current_setting('listen_addresses')) val,false omit,false body_delta
 UNION ALL SELECT 'parsed_hba',concat_ws(':',rule_number,file_name,line_number),to_jsonb(h),false,false FROM pg_hba_file_rules h
 UNION ALL SELECT 'schema',oid::text,to_jsonb(ns),false,false FROM ns
 UNION ALL SELECT 'role',oid::text,to_jsonb(r)-'rolpassword',false,false FROM pg_roles r
 UNION ALL SELECT 'membership',oid::text,to_jsonb(m),false,false FROM pg_auth_members m
 UNION ALL SELECT 'database',oid::text,to_jsonb(d)-'datfrozenxid'-'datminmxid',false,false FROM pg_database d
 UNION ALL SELECT 'database_role_setting',setdatabase::text||':'||setrole::text,to_jsonb(s),false,false FROM pg_db_role_setting s
 UNION ALL SELECT 'default_acl',oid::text,to_jsonb(a),false,false FROM pg_default_acl a
 UNION ALL SELECT 'relation',oid::text,jsonb_build_array(relname,relnamespace,relowner,relkind,relpersistence,relacl,relrowsecurity,relforcerowsecurity,relispartition,reloptions,relam),new_media,false FROM rel
 UNION ALL SELECT 'type',oid::text,to_jsonb(types)-'new_media',new_media,false FROM types
 UNION ALL SELECT 'column',a.attrelid::text||':'||a.attnum::text,to_jsonb(a)-'attstattarget'-'attcacheoff',r.new_media,false FROM pg_attribute a JOIN rel r ON r.oid=a.attrelid WHERE a.attnum>0
 UNION ALL SELECT 'column_default',a.oid::text,to_jsonb(a),r.new_media,false FROM pg_attrdef a JOIN rel r ON r.oid=a.adrelid
 UNION ALL SELECT 'function',oid::text,to_jsonb(fn)-'new_media'-'text_delta'-'nspname',new_media,text_delta FROM fn
 UNION ALL SELECT 'trigger',t.oid::text,to_jsonb(t),r.new_media,false FROM pg_trigger t JOIN rel r ON r.oid=t.tgrelid
 UNION ALL SELECT 'rule',t.oid::text,to_jsonb(t),r.new_media,false FROM pg_rewrite t JOIN rel r ON r.oid=t.ev_class
 UNION ALL SELECT 'constraint',c.oid::text,to_jsonb(c),coalesce(r.new_media,false),false FROM pg_constraint c JOIN ns n ON n.oid=c.connamespace LEFT JOIN rel r ON r.oid=c.conrelid
 UNION ALL SELECT 'index',i.indexrelid::text,to_jsonb(i),r.new_media,false FROM pg_index i JOIN rel r ON r.oid=i.indrelid
 UNION ALL SELECT 'policy',p.oid::text,to_jsonb(p),r.new_media,false FROM pg_policy p JOIN rel r ON r.oid=p.polrelid
 UNION ALL SELECT 'dependency',concat_ws(':',d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid,d.deptype),to_jsonb(d),o.new_media,false FROM pg_depend d JOIN objects o ON o.classid=d.classid AND o.objid=d.objid
 UNION ALL SELECT 'shared_dependency',concat_ws(':',d.dbid,d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.deptype),to_jsonb(d),o.new_media,false FROM pg_shdepend d JOIN objects o ON o.classid=d.classid AND o.objid=d.objid WHERE d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
 UNION ALL SELECT 'extension',oid::text,to_jsonb(e),false,false FROM pg_extension e
 UNION ALL SELECT 'foreign_wrapper',oid::text,jsonb_build_array(fdwname,fdwowner,fdwhandler,fdwvalidator,fdwacl,fdwoptions),false,false FROM pg_foreign_data_wrapper
 UNION ALL SELECT 'foreign_server',oid::text,jsonb_build_array(srvname,srvowner,srvfdw,srvacl,srvoptions),false,false FROM pg_foreign_server
 UNION ALL SELECT 'user_mapping',oid::text,jsonb_build_array(umuser,umserver,umoptions),false,false FROM pg_user_mapping
 UNION ALL SELECT 'foreign_table',ftrelid::text,jsonb_build_array(ftrelid,ftserver,ftoptions),false,false FROM pg_foreign_table
 UNION ALL SELECT 'event_trigger',oid::text,to_jsonb(e),false,false FROM pg_event_trigger e
),
digests AS (
 SELECT encode(sha256(convert_to(coalesce(string_agg(jsonb_build_array(k,id,val)::text,E'\n' ORDER BY k,id),''),'UTF8')),'hex') full_sha256,
 encode(sha256(convert_to(coalesce(string_agg(jsonb_build_array(k,id,CASE WHEN body_delta THEN val-'prosrc' ELSE val END)::text,E'\n' ORDER BY k,id) FILTER(WHERE NOT omit),''),'UTF8')),'hex') invariant_sha256
 FROM items
)
SELECT jsonb_build_object('database',current_database(),'pg_version',current_setting('server_version_num'),'full_sha256',full_sha256,'invariant_sha256',invariant_sha256,
 'text_body_md5',(SELECT md5(prosrc) FROM fn WHERE text_delta),
 'media_relations',(SELECT count(*) FROM rel WHERE new_media),
 'media_functions',(SELECT count(*) FROM fn WHERE new_media),
 'enabled_event_triggers',(SELECT count(*) FROM pg_event_trigger WHERE evtenabled<>'D'),
 'postmaster_started_at',pg_postmaster_start_time(), 'hba_parse_errors',(SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL))
FROM digests
