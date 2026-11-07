#!/usr/bin/env python3
"""C04/C05 full-public-catalog and WOLO gift/bond/NFT provenance source HOLD.

No recipient identifiers or wallet addresses leave PostgreSQL. Source emits
fixed READ ONLY SQL and SHA-pinned offline classifier. A valid observation
always exits 3/HOLD, never authorizes retry, bank custody or a funded transfer.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,re,sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("c05_semantic_private_source",SCRIPTS/"settlement_c05_semantic33_readonly_hold.py")
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
VERSION="wolo.c05.gifts-nft-bonds-full-public-catalog.v1"
EXPECTED={"hd":190,"de":52}
HD_RISK=frozenset(("user_gifts","oracle_market_proposals",
 "championship_custody_seats","championship_challenge_participants",
 "war_graph_watcher_attestations","oracle_paper_positions"))
DE_RISK=frozenset(("user_gifts",))
class Hold(ValueError):pass
def need(v,why):
 if not v:raise Hold(why)
def number(v):
 need(type(v) is str and re.fullmatch(r"(?:0|[1-9][0-9]{0,30})",v) is not None,"NONCANONICAL_COUNT")
 return int(v)
def sql(db):
 need(db in EXPECTED,"DB_NOT_ALLOWLISTED")
 pre="""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='9000ms';
SET LOCAL lock_timeout='1000ms';
SELECT json_build_object(
 'schema','wolo.c05.gifts-nft-bonds-full-public-catalog.v1',
 'database',current_database(),
 'catalog',coalesce((SELECT json_agg(c.relname ORDER BY c.relname)
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')),'[]'::json),
"""
 if db=="de":
  pieces=["'gifts',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.kind,x.status) FROM (SELECT kind,status,count(*)::text AS rows,coalesce(sum(amount::numeric),0)::text AS nominal_amount,count(accepted_at)::text AS accepted_rows FROM public.user_gifts GROUP BY kind,status) x),'[]'::json)"]
 else:
  pieces=[
  "'gifts',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.kind,x.status) FROM (SELECT kind,status,count(*)::text AS rows,coalesce(sum(amount::numeric),0)::text AS nominal_amount,count(accepted_at)::text AS accepted_rows FROM public.user_gifts GROUP BY kind,status) x),'[]'::json)",
  "'oracle_bonds',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.status,x.bond_status) FROM (SELECT status,bond_status,count(*)::text AS rows,coalesce(sum(bond_wolo::numeric),0)::text AS nominal_bond_wolo,coalesce(sum(max_pool_wolo::numeric),0)::text AS nominal_max_pool_wolo FROM public.oracle_market_proposals GROUP BY status,bond_status) x),'[]'::json)",
  "'custody_seats',(SELECT json_build_object('rows',count(*)::text,'nft_id_present',count(*) FILTER(WHERE NULLIF(btrim(coalesce(nft_id,'')),'') IS NOT NULL)::text,'class_id_present',count(*) FILTER(WHERE NULLIF(btrim(coalesce(nft_class_id,'')),'') IS NOT NULL)::text) FROM public.championship_custody_seats)",
  "'funding_participants',(SELECT json_build_object('rows',count(*)::text,'funding_linked',count(funding_scheduled_match_id)::text) FROM public.championship_challenge_participants)",
  "'watcher_provenance',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.finality_status) FROM (SELECT finality_status,count(*)::text AS rows,count(*) FILTER(WHERE result_trusted IS TRUE)::text AS trusted_labeled_rows FROM public.war_graph_watcher_attestations GROUP BY finality_status) x),'[]'::json)",
  "'paper_positions',(SELECT json_build_object('rows',count(*)::text,'nominal_paper_marks',coalesce(sum(amount_marks::numeric),0)::text) FROM public.oracle_paper_positions)"
  ]
 suffix=""",
 'chain_finality_authenticated',false,
 'financial_release_authorized',false
)::text WHERE current_database()='aoe2"""+("hd" if db=="hd" else "de")+"""_db';
ROLLBACK;
"""
 return pre+",\n".join(pieces)+suffix
def validate(doc,db):
 need(type(doc) is dict and db in EXPECTED,"DOC_INVALID")
 fields={"schema","database","catalog","gifts","chain_finality_authenticated","financial_release_authorized"}
 if db=="hd":fields|={"oracle_bonds","custody_seats","funding_participants","watcher_provenance","paper_positions"}
 need(set(doc)==fields and doc["schema"]==VERSION and
  doc["database"]==("aoe2hd_db" if db=="hd" else "aoe2de_db") and
  doc["chain_finality_authenticated"] is False and
  doc["financial_release_authorized"] is False,"SOURCE_IDENTITY_OR_AUTHORITY_DRIFT")
 names=doc["catalog"]
 need(type(names) is list and len(names)==EXPECTED[db] and
  len(names)==len(set(names)) and all(type(x) is str and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}",x) for x in names)
  and names==sorted(names),"FULL_PUBLIC_SCHEMA_DRIFT")
 need((HD_RISK if db=="hd" else DE_RISK).issubset(names),"CRITICAL_MONEY_NFT_TABLE_MISSING")
 gifts=doc["gifts"]
 need(type(gifts) is list and len(gifts)<=16,"GIFT_BUCKETS_DRIFT")
 gift_seen=set();pending_wolo=0;pending_rows=0
 for r in gifts:
  need(type(r) is dict and set(r)=={"kind","status","rows","nominal_amount","accepted_rows"},
       "GIFT_BUCKET_INVALID")
  key=(r["kind"],r["status"])
  need(all(type(x) is str and 1<=len(x)<=60 for x in key) and key not in gift_seen,"GIFT_BUCKET_DUPLICATE")
  gift_seen.add(key)
  n=number(r["rows"]);amount=number(r["nominal_amount"]);accepted=number(r["accepted_rows"])
  need(0< n and accepted<=n,"GIFT_BUCKET_COUNTER_DRIFT")
  if key==("WOLO","pending"):
   pending_wolo+=amount;pending_rows+=n
 result={"database":db,"public_base_table_count":len(names),
         "catalog_names_sha256":hashlib.sha256(json.dumps(names,separators=(",",":")).encode()).hexdigest(),
         "gift_pending_wolo_rows":pending_rows,
         "gift_pending_nominal_wolo":str(pending_wolo),
         "all_gift_fates_resolved":False}
 if db=="hd":
  bonds=doc["oracle_bonds"]
  need(type(bonds) is list and len(bonds)<=50,"BOND_BUCKETS_INVALID")
  for r in bonds:
   need(type(r) is dict and set(r)=={"status","bond_status","rows","nominal_bond_wolo","nominal_max_pool_wolo"},"BOND_FIELDS")
   for k in ("rows","nominal_bond_wolo","nominal_max_pool_wolo"):number(r[k])
  def pair(name,keys):
   obj=doc[name];need(type(obj) is dict and set(obj)==set(keys),"AGGREGATE_FIELDS_"+name)
   return {k:number(obj[k]) for k in keys}
  seats=pair("custody_seats",("rows","nft_id_present","class_id_present"))
  participants=pair("funding_participants",("rows","funding_linked"))
  paper=pair("paper_positions",("rows","nominal_paper_marks"))
  need(seats["nft_id_present"]<=seats["rows"] and seats["class_id_present"]<=seats["rows"] and
   participants["funding_linked"]<=participants["rows"],"NOMINAL_ASSET_COUNT_DRIFT")
  watcher=doc["watcher_provenance"]
  need(type(watcher) is list and len(watcher)<=100,"WATCHER_GROUPS_INVALID")
  names_seen=set()
  for row in watcher:
   need(type(row) is dict and set(row)=={"finality_status","rows","trusted_labeled_rows"} and
    type(row["finality_status"]) is str and row["finality_status"] not in names_seen,"WATCHER_GROUP_INVALID")
   names_seen.add(row["finality_status"])
   need(number(row["trusted_labeled_rows"])<=number(row["rows"]),"WATCHER_TRUST_COUNTER_INVALID")
  result.update({"oracle_bond_status_groups":len(bonds),
   "nft_custody_seats_recorded":seats["rows"],
   "nft_ids_recorded":seats["nft_id_present"],
   "funding_participant_links_recorded":participants["funding_linked"],
   "oracle_paper_marks_not_wolo":str(paper["nominal_paper_marks"]),
   "watcher_provenance_groups":len(watcher),
   "nft_chain_ownership_authenticated":False})
 return result
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 g=p.add_mutually_exclusive_group(required=True)
 g.add_argument("--emit-hd-sql",action="store_true")
 g.add_argument("--emit-de-sql",action="store_true")
 g.add_argument("--classify",action="store_true")
 p.add_argument("--hd",type=Path);p.add_argument("--de",type=Path)
 p.add_argument("--hd-sha256");p.add_argument("--de-sha256")
 a=p.parse_args(argv)
 if a.emit_hd_sql or a.emit_de_sql:
  need(all(x is None for x in (a.hd,a.de,a.hd_sha256,a.de_sha256)),"SQL_MODE_NO_FILES")
  print(sql("hd" if a.emit_hd_sql else "de"),end="");return 0
 need(a.hd and a.de and a.hd_sha256 and a.de_sha256,"SOURCE_MISSING")
 hd=validate(helper.private_read(a.hd,a.hd_sha256),"hd")
 de=validate(helper.private_read(a.de,a.de_sha256),"de")
 print(json.dumps({"schema":"wolo.c05.secondary-custody-gift-full-catalog-hold.v1",
   "status":"HOLD_GIFTS_BONDS_NFT_AND_FULL_PUBLIC_WRITER_SCOPE_UNRECONCILED",
   "hd":hd,"de":de,"hd_de_jointly_atomic":False,
   "gift_pending_additive_to_other_liabilities_proven":False,
   "oracle_paper_positions_valued_as_wolo":False,
   "nft_seats_valued_as_wolo":False,"bank_finality_authenticated":False,
   "financial_release_authorized":False,"production_mutated":False},sort_keys=True))
 return 3
if __name__=="__main__":
 try:sys.exit(main())
 except (Hold,helper.Hold,OSError,TypeError) as e:
  print(json.dumps({"status":"HOLD_SECONDARY_C05_SOURCE_INVALID",
      "reason":str(e)[:140],"financial_release_authorized":False},sort_keys=True))
  sys.exit(2)
