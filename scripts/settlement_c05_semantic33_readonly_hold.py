#!/usr/bin/env python3
"""C05 read-only 24 HD + 9 DE monetary-schema table census, NEVER authority.

Counts are not obligations, and HD/DE reads are not atomic together.
Each exact table is a required separate classification scope in the
one-height accounting source. No application values or user identifiers read.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,re,stat,sys
from pathlib import Path
VERSION="wolo.c05.semantic33-counts.v1"
HEX=re.compile(r"[a-f0-9]{64}\Z")
NUM=re.compile(r"(?:0|[1-9][0-9]{0,30})\Z")
SRC=Path(__file__).with_name("settlement_financial_one_height_arithmetic.py")
spec=importlib.util.spec_from_file_location("c05_source_scope_for_semantic",SRC)
accounting=importlib.util.module_from_spec(spec);spec.loader.exec_module(accounting)
EXPECTED=accounting.SEMANTIC_C05_TABLES
class Hold(ValueError):pass
def need(ok,why):
 if not ok:raise Hold(why)
def sql(db):
 need(db in EXPECTED,"UNKNOWN_DATABASE")
 objs=EXPECTED[db]
 need(len(objs)==len(set(objs)) and len(objs)==(24 if db=="hd" else 9),"INVENTORY_CHANGED")
 lines=["BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;",
      "SET LOCAL statement_timeout='9000ms';",
      "SET LOCAL lock_timeout='1000ms';",
      "SELECT json_build_object('schema','wolo.c05.semantic33-counts.v1','database','"+db+"',",
      "'tables',json_build_object(",
      ",\n".join("'"+name+"',(SELECT count(*)::text FROM public."+name+")" for name in objs),
      "))::text;","ROLLBACK;"]
 return "\n".join(lines)+"\n"
def decoded(blob):
 def no_dupes(pairs):
  out={}
  for k,v in pairs:
   need(k not in out,"DUPLICATE_JSON_KEY");out[k]=v
  return out
 try:return json.loads(blob,object_pairs_hook=no_dupes,
            parse_float=lambda _:need(False,"FLOAT_DENIED"),
            parse_constant=lambda _:need(False,"NONFINITE_DENIED"))
 except (UnicodeError,ValueError,RecursionError,TypeError) as e:
  if isinstance(e,Hold):raise
  raise Hold("INVALID_JSON") from e
def private_read(path,expected_sha):
 need(type(expected_sha) is str and HEX.fullmatch(expected_sha) is not None,"DIGEST_REQUIRED")
 need(path.is_absolute() and ".." not in path.parts and not path.is_symlink(),"UNSAFE_SOURCE_PATH")
 parent=path.parent.lstat()
 need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.geteuid()
   and stat.S_IMODE(parent.st_mode)==0o700,"PRIVATE_DIR_REQUIRED")
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(fd)
  need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.geteuid()
      and stat.S_IMODE(st.st_mode)==0o600 and 0<st.st_size<=131072,"PRIVATE_FILE_REQUIRED")
  blob=os.read(fd,131073)
  after=os.fstat(fd)
  need(len(blob)==st.st_size and all(getattr(st,k)==getattr(after,k) for k in
       ("st_ino","st_dev","st_size","st_mtime_ns","st_ctime_ns")),"FILE_RACED")
 finally:os.close(fd)
 need(hashlib.sha256(blob).hexdigest()==expected_sha,"SOURCE_SHA_DRIFT")
 return decoded(blob)
def validate(obj,db):
 need(db in EXPECTED and type(obj) is dict and set(obj)=={"schema","database","tables"}
  and obj["schema"]==VERSION and obj["database"]==db,"SOURCE_IDENTITY_DRIFT")
 rows=obj["tables"]
 need(type(rows) is dict and set(rows)==set(EXPECTED[db]),"TABLE_SCOPE_INCOMPLETE")
 values={}
 for name,v in rows.items():
  need(type(v) is str and NUM.fullmatch(v) is not None,"NONCANONICAL_COUNT")
  values[name]=int(v)
 return {"source_database":db,"total_table_count":len(values),
         "nonempty_count":sum(n>0 for n in values.values()),
         "total_records":sum(values.values()),
         "table_row_counts":values,
         "fenced_and_role_isolated":False,
         "all_money_column_outcomes_reconciled":False}
def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 modes=ap.add_mutually_exclusive_group(required=True)
 modes.add_argument("--emit-hd-sql",action="store_true")
 modes.add_argument("--emit-de-sql",action="store_true")
 modes.add_argument("--classify",action="store_true")
 ap.add_argument("--hd",type=Path)
 ap.add_argument("--de",type=Path)
 ap.add_argument("--hd-sha256");ap.add_argument("--de-sha256")
 a=ap.parse_args(argv)
 if a.emit_hd_sql or a.emit_de_sql:
  need(all(x is None for x in (a.hd,a.de,a.hd_sha256,a.de_sha256)),"SQL_MODE_NO_PATHS")
  print(sql("hd" if a.emit_hd_sql else "de"),end="")
  return 0
 need(a.hd and a.de,"SOURCES_REQUIRED")
 h=validate(private_read(a.hd,a.hd_sha256),"hd")
 d=validate(private_read(a.de,a.de_sha256),"de")
 print(json.dumps({"schema":"wolo.c05.semantic33-classification-hold.v1",
  "status":"HOLD_33_MONETARY_RELATIONS_NOT_FULLY_LIABILITY_CLASSIFIED",
  "hd":h,"de":d,"total_checked":h["total_table_count"]+d["total_table_count"],
  "hd_de_snapshots_jointly_atomic":False,"source_values_automatically_liabilities":False,
  "cross_source_economic_disjointness_proven":False,"native_chain_finality_authenticated":False,
  "financial_release_authorized":False,"production_mutated":False},
  sort_keys=True,separators=(",",":")))
 return 3
if __name__=="__main__":
 try:sys.exit(main())
 except (Hold,OSError) as e:
  print(json.dumps({"status":"HOLD_SEMANTIC_C05_EVIDENCE_INVALID",
        "reason":str(e)[:130],"financial_release_authorized":False},sort_keys=True))
  sys.exit(2)
