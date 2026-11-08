"""Offline adversarial C03 grants plus live-client identity HOLD tests."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import settlement_c03_effective_grants_bound_sessions_hold as c

NOW=datetime(2026,11,8,8,35,tzinfo=timezone.utc)

def evidence():
    gr={"schema":c.GRANTS_SCHEMA,"status":"HOLD",
        "observed_utc":"2026-11-08T08:35:00+00:00",
        "financial_writers_quiesced":False,
        "funded_release_authorized":False,
        "database_permissions_changed":False,
        "all_schemas_roles_and_bypass_paths_certified":False,"databases":{}}
    for db,total in c.PUBLIC_TABLES.items():
        rows={}
        for role in c.EXPECTED_ROLES:
            full=total if role==c.LEGACY[db] else (1 if db=="aoe2hd_db" and role=="aoe2war_auth_owner" else 0)
            # The two reviewed auth functions are accessible to non-legacy roles.
            definer_count=3 if (db=="aoe2hd_db" and
                                role not in c.LEGACY.values()) else 0
            rows[role]={
              "role_exists":True,"public_relations":total,
              "finance_named_relations":30 if db=="aoe2hd_db" else 11,
              "public_write_capable_relations":full,
              "finance_write_capable_relations":30 if db=="aoe2hd_db" and role==c.LEGACY[db] else (11 if db=="aoe2de_db" and role==c.LEGACY[db] else 0),
              "selected_security_definer_functions_executable":definer_count,
              "superuser":False,"bypass_rls":False}
        gr["databases"][db]=rows
    records=[]
    for i,(db,role,svc) in enumerate((
       ("aoe2hd_db","aoe2hd_user","aoe2hdbets-web.service"),
       ("aoe2hd_db","aoe2hd_user","aoe2hdbets-api.service"),
       ("aoe2de_db","aoe2de_user","aoe2dewarwagers-api.service"),
       ("aoe2hd_db","aoe2war_web_prod","aoe2hdbets-web-prod.service"))):
        records.append({"database":db,"role":role,"source_service":svc,
                        "pg_backend_pid": 12000+i,
                        "finance_write_permission_denied":False,
                        "safe_to_terminate":False})
    sess={"schema":c.SESSIONS_SCHEMA,"status":"HOLD",
          "observed_utc":"2026-11-08T08:35:01+00:00",
          "finance_writer_denial_proven":False,"global_c03_gate_accepted":False,
          "funded_release_authorized":False,"production_modified":False,
          "live_pg_session_termination_authorized":False,
          "protected_3030_rollback_pg_client_proven":True,
          "exact_socket_to_process_to_systemd_binding":True,
          "process_population_fresh_for_this_observation_only":True,
          "total_bound_existing_sessions":len(records),"records":records}
    return gr,sess

class C03DualSourceHold(unittest.TestCase):
    def setUp(self):
        self.g,self.s=evidence()

    def classify(self):
        return c.classify(self.g,self.s,now=NOW+timedelta(seconds=2))

    def stop(self):
        with self.assertRaises(c.Hold):
            self.classify()

    def test_exact_baseline_holds_with_privileged_owner_sessions(self):
        result=self.classify()
        self.assertEqual(result["status"],
          "HOLD_C03_LIVE_OWNER_SESSIONS_RETAIN_EFFECTIVE_WRITE_CAPABILITY")
        self.assertEqual(result["legacy_owner_connected_sessions"],3)
        self.assertEqual(result["protected_3030_owner_role_sessions"],1)
        self.assertEqual(result["tables"]["aoe2hd_db"]["legacy_owner_write_capable_tables"],190)
        self.assertEqual(result["tables"]["aoe2de_db"]["legacy_owner_write_capable_tables"],52)
        for key in ("c03_writer_fence_complete","financial_release_authorized",
                    "production_mutated","c06_backup_authorized","c07_restore_authorized",
                    "privileged_existing_sessions_terminated"):
            self.assertIs(result[key],False)

    def test_session_order_not_significant(self):
        self.s["records"].reverse()
        self.assertEqual(self.classify()["legacy_owner_connected_sessions"],3)

    def test_role_owner_grant_fence_without_live_session_still_never_authorizes(self):
        for db in c.PUBLIC_TABLES:
            r=self.g["databases"][db][c.LEGACY[db]]
            r["public_write_capable_relations"]=0
            r["finance_write_capable_relations"]=0
        self.assertEqual(self.classify()["status"],
          "HOLD_C03_OWNER_CONNECTIONS_EXIST_BUT_NEGATIVE_DML_UNPROVEN")
        self.assertIs(self.classify()["financial_release_authorized"],False)

    def test_restricted_r25_write_regression_rejected(self):
        self.g["databases"]["aoe2hd_db"]["aoe2war_web_prod"]["public_write_capable_relations"]=1
        self.stop()

    def test_restricted_r25_finance_write_regression_rejected(self):
        r=self.g["databases"]["aoe2de_db"]["aoe2war_web_prod"]
        r["public_write_capable_relations"]=1
        r["finance_write_capable_relations"]=1
        self.stop()

    def test_auth_owner_privilege_scope_expansion_rejected(self):
        self.g["databases"]["aoe2hd_db"]["aoe2war_auth_owner"]["public_write_capable_relations"]=2
        self.stop()

    def test_role_elevation_rejected(self):
        self.g["databases"]["aoe2hd_db"]["aoe2hd_user"]["superuser"]=True
        self.stop()

    def test_role_bypass_rls_rejected(self):
        self.g["databases"]["aoe2hd_db"]["aoe2hd_user"]["bypass_rls"]=True
        self.stop()

    def test_schema_count_drift_rejected(self):
        self.g["databases"]["aoe2de_db"]["aoe2de_user"]["public_relations"]=53
        self.stop()

    def test_role_missing_rejected(self):
        del self.g["databases"]["aoe2hd_db"]["aoe2war_auth_owner"]
        self.stop()

    def test_unknown_client_role_rejected(self):
        self.s["records"][0]["role"]="postgres"
        self.stop()

    def test_cross_role_unit_swapping_rejected(self):
        self.s["records"][0]["source_service"]="aoe2hdbets-web-prod.service"
        self.stop()

    def test_rollback_missing_rejected(self):
        self.s["records"][0]["source_service"]="aoe2hdbets-api.service"
        self.stop()

    def test_rollback_identity_not_attested_rejected(self):
        self.s["protected_3030_rollback_pg_client_proven"]=False
        self.stop()

    def test_falsely_claimed_finance_denial_rejected(self):
        self.s["records"][0]["finance_write_permission_denied"]=True
        self.stop()

    def test_duplicate_postgres_backend_rejected(self):
        self.s["records"][1]["pg_backend_pid"]=self.s["records"][0]["pg_backend_pid"]
        self.stop()

    def test_client_count_mismatch_rejected(self):
        self.s["total_bound_existing_sessions"]=3
        self.stop()

    def test_definer_role_write_count_inconsistency_rejected(self):
        self.g["databases"]["aoe2hd_db"]["aoe2hd_user"]["finance_write_capable_relations"]=99
        self.stop()

    def test_notice_staleness_rejected(self):
        self.s["observed_utc"]="2026-11-08T07:30:00+00:00"
        self.stop()

    def test_census_skew_rejected(self):
        self.s["observed_utc"]="2026-11-08T08:30:01+00:00"
        self.stop()

    def test_future_dated_evidence_rejected(self):
        self.g["observed_utc"]="2026-11-09T08:35:00+00:00"
        self.stop()

    def test_bogus_timezone_rejected(self):
        self.g["observed_utc"]="2026-11-08T08:35:00"
        self.stop()

    def test_hardcoded_release_flag_rejected(self):
        self.g["funded_release_authorized"]=True
        self.stop()
        self.g,self.s=evidence()
        self.s["global_c03_gate_accepted"]=True
        self.stop()

    def test_noncanonical_numeric_rejected(self):
        for value in (True,-1,190.0,"190",None):
            self.g,self.s=evidence()
            self.g["databases"]["aoe2hd_db"]["aoe2hd_user"]["public_write_capable_relations"]=value
            self.stop()

    def test_private_json_digest_and_owner_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.json"
            p.write_text(json.dumps(self.g));p.chmod(0o600)
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(c.private_json(p,sha),self.g)
            with self.assertRaises(c.Hold):
                c.private_json(p,"0"*64)
            p.chmod(0o644)
            with self.assertRaises(c.Hold):
                c.private_json(p,sha)
            p.chmod(0o600)
            (Path(d)/"link").symlink_to(p)
            with self.assertRaises(OSError):
                c.private_json(Path(d)/"link",sha)

    def test_status_always_holds_when_owner_acl_appears_removed(self):
        for db in c.PUBLIC_TABLES:
            r=self.g["databases"][db][c.LEGACY[db]]
            r["public_write_capable_relations"]=0
            r["finance_write_capable_relations"]=0
        self.assertFalse(self.classify()["c03_writer_fence_complete"])
        self.assertFalse(self.classify()["non_database_native_rpc_rest_and_external_paths_fenced"])

if __name__=="__main__":
    unittest.main()
