#!/usr/bin/env python3
"""C04/C05 independent seven-surface census, strictly READ ONLY and ALWAYS HOLD.

SQL is emitted for explicit operator-run REPEATABLE READ READ ONLY PostgreSQL
transactions. Classification consumes SHA-pinned, owner-0600 local snapshots.
Paid database flags and hashes never prove native blockchain settlement.
Never infers solvency, NFT ownership, approval to retry, or funded authority.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA="wolo.c05.seven-surface-census.v1"
# (table, status SQL expression, amount expression, unit, hash SQL, retry SQL)
HD=(
 ("bounty_payouts","status","amount_wolo","wolo","tx_hash","0"),
 ("championship_transfer_groups","app_status || ':' || nft_status","frozen_bounty_wolo","wolo","NULL::text","0"),
 ("championship_transfer_seats","status","0","nft_seat","tx_hash","0"),
 ("trophy_payout_allocations","status","amount_uwolo","uwolo","tx_hash","0"),
 ("trophy_payouts","status","amount_wolo","wolo","tx_hash","retry_count"),
 ("war_graph_payout_events","status","0","event_no_amount","tx_hash","0"),
)
DE=(("trophy_payouts","status","amount_wolo","wolo","tx_hash","retry_count"),)
DB_SPECS={"hd":HD,"de":DE}
NUM=re.compile(r"(?:0|[1-9][0-9]{0,38})\Z")
DIGEST=re.compile(r"[a-f0-9]{64}\Z")

class Reject(ValueError):pass
def need(condition,reason):
 if not condition:raise Reject(reason)
def bucket_sql(spec):
 table,status,amount,unit,hashcol,retry=spec
 # Table and column identifiers are a fixed audited source allowlist; never input-derived.
 return f"""(SELECT json_build_object(
   'unit','{unit}','buckets',COALESCE(json_agg(row_to_json(x) ORDER BY x.status),'[]'::json))
  FROM (SELECT ({status})::text AS status,
        count(*)::text AS rows,
        COALESCE(sum(({amount})::numeric),0)::text AS nominal,
        count(*) FILTER (WHERE NULLIF(btrim(coalesce(({hashcol})::text,'')),'') IS NOT NULL)::text AS hash_present,
        count(*) FILTER (WHERE NULLIF(btrim(coalesce(({hashcol})::text,'')),'') IS NULL)::text AS hash_missing,
        COALESCE(sum(({retry})::numeric),0)::text AS retries
        FROM public.{table} GROUP BY ({status})) x)"""
def sql(db):
 need(db in DB_SPECS,"DATABASE_NOT_REVIEWED")
 sources=DB_SPECS[db]
 args=",\n".join(f"'{table}',{bucket_sql(spec)}" for spec in sources for table in (spec[0],))
 return ("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
         "SET LOCAL statement_timeout='9000ms';\n"
         "SELECT json_build_object('schema','"+SCHEMA+"','database','"+db+
         "','surfaces',json_build_object(\n"+args+"))::text;\nCOMMIT;\n")
def number(v):
 need(type(v) is str and NUM.fullmatch(v) is not None,"INVALID_NONCANONICAL_COUNT")
 n=int(v)
 need(n<=(1<<128)-1,"COUNT_OVERFLOW")
 return n
def strictly_decode(raw):
 def unique(pairs):
  d={}
  for k,v in pairs:
   need(k not in d,"DUPLICATE_JSON_FIELD")
   d[k]=v
  return d
 try:return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:need(False,"INVALID_JSON_CONSTANT"))
 except (UnicodeError,RecursionError,TypeError) as e:raise Reject("INVALID_JSON") from e
def validate(packet,db):
 need(type(packet) is dict and set(packet)=={"schema","database","surfaces"} and
      packet["schema"]==SCHEMA and packet["database"]==db,"SNAPSHOT_IDENTITY_INVALID")
 spec=DB_SPECS[db]
 surfaces=packet["surfaces"]
 need(type(surfaces) is dict and set(surfaces)=={s[0] for s in spec},"SEVEN_SURFACE_INVENTORY_INCOMPLETE")
 results={}
 for table,_,__,unit,___,____ in spec:
  obj=surfaces[table]
  need(type(obj) is dict and set(obj)=={"unit","buckets"} and obj["unit"]==unit,"SURFACE_UNIT_INVALID")
  buckets=obj["buckets"]
  need(type(buckets) is list and len(buckets)<=64,"SURFACE_STATUS_COUNT_INVALID")
  totals={"rows":0,"nominal":0,"hash_present":0,"hash_missing":0,"retries":0}
  labels=set()
  states={}
  for row in buckets:
   need(type(row) is dict and set(row)=={"status","rows","nominal","hash_present","hash_missing","retries"},"STATUS_BUCKET_SCHEMA_INVALID")
   label=row["status"]
   need(type(label) is str and 1<=len(label)<=96 and label not in labels,"DUPLICATE_OR_INVALID_STATUS")
   labels.add(label)
   vals={key:number(row[key]) for key in totals}
   need(vals["rows"]>0 and vals["hash_present"]+vals["hash_missing"]==vals["rows"],"HASH_CENSUS_INCONSISTENT")
   need(vals["nominal"]>=0,"AMOUNT_INVALID")
   for k,v in vals.items():
    totals[k]+=v
    need(totals[k]<=(1<<128)-1,"SUM_OVERFLOW")
   states[label]={"rows":vals["rows"],"nominal":vals["nominal"],"hash_present":vals["hash_present"],
                  "hash_missing":vals["hash_missing"],"retries":vals["retries"]}
  if unit in ("nft_seat","event_no_amount"):
   need(totals["nominal"]==0,"NONMONETARY_SURFACE_AMOUNT_FORGED")
  results[table]={"unit":unit,"totals":totals,"statuses":states}
 return results
def securely_read(path,expected_sha):
 need(type(expected_sha) is str and DIGEST.fullmatch(expected_sha) is not None,"EXPECTED_SHA_REQUIRED")
 need(path.is_absolute() and not path.is_symlink() and ".." not in path.parts,"ABSOLUTE_FILE_REQUIRED")
 parent=path.parent
 ps=parent.lstat()
 need(stat.S_ISDIR(ps.st_mode) and ps.st_uid==os.geteuid() and stat.S_IMODE(ps.st_mode)==0o700,"PRIVATE_PARENT_REQUIRED")
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  before=os.fstat(fd)
  need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.geteuid()
       and stat.S_IMODE(before.st_mode)==0o600 and 1<=before.st_size<=131072,"PRIVATE_FILE_INVALID")
  raw=os.read(fd,131073)
  after=os.fstat(fd)
  need(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k) for k in
       ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")),"FILE_RACED")
  need(hashlib.sha256(raw).hexdigest()==expected_sha,"SNAPSHOT_SHA_MISMATCH")
  return strictly_decode(raw)
 finally:os.close(fd)
def classify(hd,de,hdsha,desha):
 a=validate(securely_read(hd,hdsha),"hd")
 b=validate(securely_read(de,desha),"de")
 paid=a["trophy_payouts"]["statuses"].get("paid",{})
 dry=a["trophy_payouts"]["statuses"].get("dry_run",{})
 bad_paid=paid.get("hash_missing",0)>0
 return {
  "schema":"wolo.c04-c05.seven-surface-observer.v1",
  "status":"HOLD_C04_C05_NONFINAL_SEVEN_FINANCIAL_SURFACES",
  "source_snapshots":{"hd_sha256":hdsha,"de_sha256":desha},
  "protected_surface_count":len(a)+len(b),
  "observed":{db:{table:{"unit":v["unit"],"totals":v["totals"],"statuses":v["statuses"]}
                   for table,v in parts.items()} for db,parts in (("hd",a),("de",b))},
  "trophy_paid_labeled_rows":paid.get("rows",0),
  "trophy_dry_run_labeled_rows":dry.get("rows",0),
  "paid_labeled_missing_tx_hash":bad_paid,
  "paid_hashes_authenticated_on_chain":False,
  "dry_run_exposure_unresolved_and_not_excluded":True,
  "dry_run_nominal_wolo_unclassified":str(dry.get("nominal",0)),
  "cross_surface_economic_identity_overlap_proven":False,
  "global_liability_inventory_complete":False,
  "same_height_bank_proof_authenticated":False,
  "financial_release_authorized":False,
  "payout_retry_authorized":False,
  "production_mutated":False,
 }
def main(argv=None):
 p=argparse.ArgumentParser()
 g=p.add_mutually_exclusive_group(required=True)
 g.add_argument("--emit-hd-sql",action="store_true")
 g.add_argument("--emit-de-sql",action="store_true")
 g.add_argument("--classify",action="store_true")
 p.add_argument("--hd",type=Path)
 p.add_argument("--de",type=Path)
 p.add_argument("--hd-sha256")
 p.add_argument("--de-sha256")
 a=p.parse_args(argv)
 if a.emit_hd_sql or a.emit_de_sql:
  need(all(x is None for x in (a.hd,a.de,a.hd_sha256,a.de_sha256)),"SQL_MODE_NO_FILES")
  print(sql("hd" if a.emit_hd_sql else "de"),end="")
  return 0
 need(a.hd is not None and a.de is not None,"SNAPSHOTS_REQUIRED")
 print(json.dumps(classify(a.hd,a.de,a.hd_sha256,a.de_sha256),sort_keys=True,separators=(",",":")))
 return 3 # never authenticate solvency or payment finality
if __name__=="__main__":
 try:sys.exit(main())
 except (Reject,OSError,ValueError) as e:
  print(json.dumps({"status":"HOLD_C04_C05_INVALID_OR_INCOMPLETE_EVIDENCE",
                    "reason":str(e)[:100],"financial_release_authorized":False},sort_keys=True))
  sys.exit(2)
