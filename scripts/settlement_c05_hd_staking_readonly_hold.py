#!/usr/bin/env python3
"""C04/C05 actual HD staking principal/effects observer: fixed SQL, financial HOLD.

Emits only aggregate READ ONLY SQL; can classify authenticated owner-private
0600 JSON captures with an independent SHA. Never sends, signs, retries,
modifies production, authenticates consensus or returns fund authorization.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,stat,sys
from pathlib import Path

VERSION="wolo.c05.hd-staking-principal-events.v1"
HEX=re.compile(r"[a-f0-9]{64}\Z")
NUM=re.compile(r"(?:0|[1-9][0-9]{0,38})\Z")
LIMIT=(1<<128)-1
STATES=frozenset(("active","inactive"))
EVENT_STATES=frozenset(("CONFIRMED","PENDING_CHAIN","FAILED","REJECTED","UNKNOWN"))
EVENT_TYPES=frozenset(("CLAIM","COMPOUND","STAKE","UNSTAKE"))
class Hold(ValueError):pass
def need(ok,why):
 if not ok:raise Hold(why)
def sql():
 return """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='9000ms';
SET LOCAL lock_timeout='1000ms';
SELECT json_build_object(
 'schema','wolo.c05.hd-staking-principal-events.v1',
 'database',current_database(),
 'positions',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.status)
   FROM (SELECT status,count(*)::text AS rows,
          coalesce(sum(current_staked_wolo::numeric),0)::text AS principal_wolo,
          coalesce(sum(pending_rewards_wolo::numeric),0)::text AS pending_rewards_wolo,
          coalesce(sum(micro_reward_carry_uwolo::numeric),0)::text AS reward_carry_uwolo
         FROM public.staking_positions GROUP BY status) x),'[]'::json),
 'events',coalesce((SELECT json_agg(row_to_json(x) ORDER BY x.status,x.event_type)
   FROM (SELECT status,type AS event_type,count(*)::text AS rows,
          coalesce(sum(amount_wolo::numeric),0)::text AS nominal_wolo,
          count(*) FILTER (WHERE NULLIF(btrim(coalesce(tx_hash,'')),'') IS NOT NULL)::text AS hash_present,
          count(*) FILTER (WHERE NULLIF(btrim(coalesce(tx_hash,'')),'') IS NULL)::text AS hash_missing
         FROM public.staking_events GROUP BY status,type) x),'[]'::json),
 'chain_finality_authenticated',false,
 'financial_release_authorized',false
)::text WHERE current_database()='aoe2hd_db';
ROLLBACK;
"""
def num(v):
 need(type(v) is str and NUM.fullmatch(v) is not None,"NONCANONICAL_OR_NEGATIVE_AMOUNT")
 n=int(v);need(n<=LIMIT,"AMOUNT_OVERFLOW")
 return n
def decode(raw):
 def unique(pairs):
  out={}
  for k,v in pairs:
   need(k not in out,"DUPLICATE_FIELD")
   out[k]=v
  return out
 try:return json.loads(raw,object_pairs_hook=unique,
   parse_float=lambda _:need(False,"FLOAT_FORBIDDEN"),
   parse_constant=lambda _:need(False,"NONFINITE_FORBIDDEN"))
 except (UnicodeError,RecursionError,TypeError,ValueError) as exc:
  if isinstance(exc,Hold):raise
  raise Hold("INVALID_JSON") from exc
def read(path,expected):
 need(type(expected) is str and HEX.fullmatch(expected) is not None,
      "SOURCE_DIGEST_REQUIRED")
 need(path.is_absolute() and not path.is_symlink() and ".." not in path.parts,
      "UNSAFE_INPUT_PATH")
 parent=path.parent.lstat()
 need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.geteuid()
       and stat.S_IMODE(parent.st_mode)==0o700,"UNSAFE_PRIVATE_PARENT")
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(fd)
  need(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid()
      and st.st_nlink==1 and stat.S_IMODE(st.st_mode)==0o600
      and 0<st.st_size<=131072,"UNSAFE_INPUT_FILE")
  raw=os.read(fd,131073)
  st2=os.fstat(fd)
  need(len(raw)==st.st_size and
      all(getattr(st,k)==getattr(st2,k) for k in
          ("st_ino","st_dev","st_size","st_mtime_ns","st_ctime_ns")),
      "INPUT_CHANGED")
 finally:os.close(fd)
 need(hashlib.sha256(raw).hexdigest()==expected,"INPUT_SHA_DRIFT")
 return decode(raw)
def classify(packet,source_sha):
 need(type(packet) is dict and set(packet)=={
  "schema","database","positions","events","chain_finality_authenticated",
  "financial_release_authorized"},"UNEXPECTED_FIELDS")
 need(packet["schema"]==VERSION and packet["database"]=="aoe2hd_db"
  and packet["chain_finality_authenticated"] is False
  and packet["financial_release_authorized"] is False,"UNSUPPORTED_FINANCIAL_AUTHORITY")
 positions=packet["positions"];events=packet["events"]
 need(type(positions) is list and len(positions)<=len(STATES),"POSITION_BUCKETS_INVALID")
 need(type(events) is list and len(events)<=32,"EVENT_BUCKETS_INVALID")
 seen_pos=set()
 active_principal=0;active_rewards=0;active_carry=0;active_rows=0
 for row in positions:
  need(type(row) is dict and set(row)=={"status","rows","principal_wolo",
         "pending_rewards_wolo","reward_carry_uwolo"},"POSITION_FIELDS_INVALID")
  state=row["status"]
  need(state in STATES and state not in seen_pos,"POSITION_STATUS_DRIFT")
  seen_pos.add(state)
  n=num(row["rows"])
  principal=num(row["principal_wolo"])
  rewards=num(row["pending_rewards_wolo"])
  carry=num(row["reward_carry_uwolo"])
  need(n>0,"EMPTY_STATUS_BUCKET")
  if state=="active":
   active_rows+=n;active_principal+=principal
   active_rewards+=rewards;active_carry+=carry
 for amount in (active_principal,active_rewards,active_carry):
  need(amount<=LIMIT,"ACTIVE_POSITION_SUM_OVERFLOW")
 seen_events=set()
 pending_unproven=0;pending_nominal=0
 confirmed_labeled=0;confirmed_without_hash=0
 for row in events:
  need(type(row) is dict and set(row)=={"status","event_type","rows",
       "nominal_wolo","hash_present","hash_missing"},"EVENT_FIELDS_INVALID")
  key=(row["status"],row["event_type"])
  need(key[0] in EVENT_STATES and key[1] in EVENT_TYPES
    and key not in seen_events,"EVENT_STATUS_TYPE_DRIFT")
  seen_events.add(key)
  n=num(row["rows"])
  amount=num(row["nominal_wolo"])
  have=num(row["hash_present"]);missing=num(row["hash_missing"])
  need(n>0 and have+missing==n,"INVALID_EVENT_HASH_CENSUS")
  if key[0]=="PENDING_CHAIN":
   pending_unproven+=n;pending_nominal+=amount
  if key[0]=="CONFIRMED":
   confirmed_labeled+=n;confirmed_without_hash+=missing
 need(all(n<=LIMIT for n in (pending_nominal,pending_unproven,confirmed_labeled,
                             confirmed_without_hash)),"EVENT_SUM_OVERFLOW")
 return {"schema":"wolo.c04-c05.staking-candidate-exposure-hold.v1",
  "status":"HOLD_STAKING_ACCOUNTING_AND_CHAIN_FINALITY_UNPROVEN",
  "source_sha256":source_sha,"live_active_staking_positions":active_rows,
  "live_active_principal_wolo":str(active_principal),
  "live_active_pending_rewards_wolo":str(active_rewards),
  "live_active_micro_reward_carry_uwolo":str(active_carry),
  "pending_chain_event_rows":pending_unproven,
  "pending_chain_event_nominal_wolo":str(pending_nominal),
  "confirmed_labeled_event_rows":confirmed_labeled,
  "confirmed_labeled_missing_hash_rows":confirmed_without_hash,
  "recorded_principal_is_authentic_native_custody":False,
  "all_staking_liabilities_disjoint_proven":False,
  "pending_chain_event_can_be_safely_retried":False,
  "pending_event_additive_to_staked_principal_proven":False,
  "global_liability_upper_bound_uwolo":None,
  "same_height_bank_proof_authenticated":False,
  "financial_release_authorized":False,
  "production_mutated":False}
def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 group=ap.add_mutually_exclusive_group(required=True)
 group.add_argument("--emit-hd-sql",action="store_true")
 group.add_argument("--classify",action="store_true")
 ap.add_argument("--input",type=Path)
 ap.add_argument("--input-sha256")
 a=ap.parse_args(argv)
 if a.emit_hd_sql:
  need(a.input is None and a.input_sha256 is None,"SQL_MODE_NO_INPUT")
  print(sql(),end="");return 0
 need(a.input is not None and a.input_sha256 is not None,"SOURCE_REQUIRED")
 print(json.dumps(classify(read(a.input,a.input_sha256),a.input_sha256),sort_keys=True))
 return 3
if __name__=="__main__":
 try:sys.exit(main())
 except (Hold,OSError) as e:
  print(json.dumps({"status":"HOLD_INVALID_STAKING_PROOF",
     "reason":str(e)[:120],"financial_release_authorized":False},sort_keys=True))
  sys.exit(2)
