#!/usr/bin/env python3
"""C03 post-Atlas topology rebaseline evidence ONLY. No enrollment or finance mutation.

Reconciles the existing root-only V1 and V2 financial HOLD auditor outputs.
Original 57 and 67 fingerprints must be recovered by removing the SAME five
newly source-reviewed units; V2 must still discover the ten TokenChain units.
This can qualify a candidate topology, never replace the installed baseline,
cut over the spent V2 controller, or grant a financial-writer permit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

V1_HISTORIC_SHA="83f15ae92e7420822f0c10ce3ad0d9e39eef2b913f6697bd750c36a91f80a1de"
V2_HISTORIC_SHA="96026be468a9fd2cc6a65c8119ad83c8fd915a3233ef98c247fe90a319d745f0"
V1_LIVE_SHA="593da19d3d7d0f16781b6c11885fa3cf468294ec516444b88fd2e826ced6c64a"
V2_LIVE_SHA="3d8896b93de31bd4550651cb5d030614755ce5801e58c776b3f42e2a0d26aa39"
FIVE=frozenset((
    "aoe2war-appearance-writer.service",
    "aoe2war-product-steam-nft-boot.service",
    "aoe2war-social-writer.service",
    "aoe2war-wolo-public-daemon-feed.service",
    "aoe2war-wolo-public-daemon-feed.timer",
))
TOKENCHAIN=frozenset((
    "tokenchain-callisto.service",
    "tokenchain-daily-allocation.service",
    "tokenchain-daily-allocation.timer",
    "tokenchain-faucet.service",
    "tokenchain-hasura.service",
    "tokenchain-indexer.service",
    "tokenchain-osmo-ibc-bootstrap.service",
    "tokenchain-osmo-ibc-bootstrap.timer",
    "tokenchain-relayer.service",
    "tokenchain-web.service",
))
STATUS="PASS_C03_POST_ATLAS_EXACT_FIVE_TOPOLOGY_RECONCILED_FINANCIAL_HOLD"
class Hold(ValueError): pass

def need(ok, message):
    if not ok: raise Hold(message)
def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def names_sha(names):return sha(canonical(sorted(names)))
def unique(pairs):
    o={}
    for k,v in pairs:
        need(k not in o,"DUPLICATE_AUDIT_JSON_KEY")
        o[k]=v
    return o
def audited_names(raw,expected_count,unscoped):
    need(type(raw) is dict and
         raw.get("schema")=="wolo.c03.physical-writer-universe-hold.v1"
         and raw.get("status")=="HOLD"
         and all(raw.get(k) is False for k in (
             "paymentAuthorized","backupAuthorized",
             "fenceAndQuiescenceProven","databaseOwnershipChanged",
             "unitsModified")),"ORIGINAL_AUDITOR_MUST_BE_FINANCE_HOLD")
    rows=raw.get("census",{}).get("systemdUnits")
    need(type(rows) is list and len(rows)==expected_count
         and raw.get("discoveredUnitCount")==expected_count
         and type(raw.get("unscopedUnitCount")) is int
         and raw["unscopedUnitCount"]==unscoped,
         "POST_ATLAS_UNIT_OR_UNSCOPED_COUNT_DRIFT")
    names=[]
    for r in rows:
        need(type(r) is dict and type(r.get("unit")) is str
             and re.fullmatch(r"[a-zA-Z0-9@_.-]+\.(?:service|timer)",r["unit"]),
             "UNSAFE_OR_MISSING_UNIT_NAME")
        names.append(r["unit"])
    need(len(set(names))==len(names),"DUPLICATE_UNIT_IDENTITY")
    db=raw.get("census",{}).get("legacyDbOwner")
    need(type(db) is dict and set(db)=={"aoe2hd_db","aoe2de_db"}
         and all(type(x) is dict and
                 x.get("finance_writer_capability") is True and
                 x.get("implicit_owner_or_schema_bypass") is True
                 for x in db.values()),
         "FINANCIAL_WRITER_EXCLUSION_NOT_PROVEN_CANNOT_DOWNGRADE")
    need(type(raw.get("unprovenDomains")) is list and raw["unprovenDomains"],
         "MISSING_UNPROVEN_WRITER_DOMAINS")
    return frozenset(names)

def reconcile(v1,v2):
    old=audited_names(v1,62,38)
    extended=audited_names(v2,72,48)
    need(len(FIVE)==5 and FIVE<=old and FIVE<=extended,
         "EXACT_FIVE_PRODUCT_FEED_UNITS_ABSENT")
    need(names_sha(old)==V1_LIVE_SHA and names_sha(extended)==V2_LIVE_SHA,
         "UNREVIEWED_NEW_POST_ATLAS_NAME")
    need(len(old-FIVE)==57 and names_sha(old-FIVE)==V1_HISTORIC_SHA,
         "V1_57_ENROLLED_BASELINE_CANNOT_BE_RECONSTRUCTED")
    need(len(extended-FIVE)==67 and names_sha(extended-FIVE)==V2_HISTORIC_SHA,
         "V2_67_REVIEWED_BASELINE_CANNOT_BE_RECONSTRUCTED")
    need(extended-old==TOKENCHAIN and not (old-extended),
         "EXTENDED_TOKENCHAIN_TEN_NOT_EXACT")
    return {
        "schema":"wolo.c03.post-atlas-exact-five-topology-reconciliation.v1",
        "status":STATUS,
        "v1":{"current_count":62,"unscoped_count":38,"current_names_sha256":V1_LIVE_SHA,
              "original_count":57,"original_names_sha256":V1_HISTORIC_SHA},
        "v2":{"current_count":72,"unscoped_count":48,"current_names_sha256":V2_LIVE_SHA,
              "original_count":67,"original_names_sha256":V2_HISTORIC_SHA},
        "exact_added_names":sorted(FIVE),
        "extended_additional_tokenchain_names":sorted(TOKENCHAIN),
        "financial_writer_exclusion_proven":False,
        "c06_consistent_backup_certified":False,
        "installed_enrollment_modified":False,
        "v2_cutover_authorized":False,
        "funding_authorized":False,
        "requires_new_reviewed_source_and_owner_native_c03_cutover":True,
    }
def load(p):
    s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and not p.is_symlink()
         and 1<=s.st_size<=300000,"UNSAFE_AUDITOR_REPORT_FILE")
    b=p.read_bytes()
    need(len(b)==s.st_size,"AUDITOR_REPORT_RACE")
    return json.loads(b,object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Hold("NONFINITE_AUDIT")))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--v1-report",type=Path,required=True)
    parser.add_argument("--v2-report",type=Path,required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(reconcile(load(args.v1_report),load(args.v2_report)),
                         sort_keys=True,separators=(",",":")))
        return 0
    except (Hold,ValueError,OSError,KeyError,TypeError) as e:
        print(json.dumps({"status":"HOLD_C03_POST_ATLAS_REBASELINE_NOT_QUALIFIED",
                          "reason":str(e)[:130],"funding_authorized":False,
                          "financial_writer_exclusion_proven":False},sort_keys=True))
        return 2
if __name__=="__main__":raise SystemExit(main())
