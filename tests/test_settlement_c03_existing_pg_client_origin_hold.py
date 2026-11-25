"""Fail-closed C03 exact process-to-role evidence. No database or host changes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/settlement_c03_existing_pg_client_origin_hold.py"
spec = importlib.util.spec_from_file_location("c03_origin_hold", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample():
    raw = (
        "aoe2de_db|aoe2de_user|100|idle|127.0.0.1|51201|1790000001\n"
        "aoe2hd_db|aoe2hd_user|101|idle|127.0.0.1|51202|1790000001\n"
        "aoe2hd_db|aoe2hd_user|102|idle|127.0.0.1|51203|1790000001\n"
        "aoe2hd_db|aoe2war_web_prod|103|idle|127.0.0.1|51204|1790000001\n"
    )
    return m.parse_catalog(raw)


def sockets():
    return m.parse_sockets(
        'ESTAB 0 0 127.0.0.1:51201 127.0.0.1:5432 users:(("uvicorn",pid=2001,fd=6))\n'
        'ESTAB 0 0 127.0.0.1:51202 127.0.0.1:5432 users:(("python",pid=2002,fd=6))\n'
        'ESTAB 0 0 127.0.0.1:51203 127.0.0.1:5432 users:(("next-server (v15.5.28)",pid=2003,fd=7))\n'
        'ESTAB 0 0 127.0.0.1:51204 127.0.0.1:5432 users:(("next-server (v15.5.28)",pid=2004,fd=7))\n'
    )


def identities():
    return {
        2001: ("aoe2dewarwagers-api.service", 111),
        2002: ("aoe2hdbets-api.service", 222),
        2003: ("aoe2hdbets-web.service", 333),
        2004: ("aoe2hdbets-web-prod.service", 444),
    }


class C03Binding(unittest.TestCase):
    def test_positive_still_hold_and_rollback_preserved(self):
        rows = sample()
        result = m.qualify(rows, sockets(), rows.copy(), identities())
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["total_bound_existing_sessions"], 4)
        self.assertTrue(result["protected_3030_rollback_pg_client_proven"])
        self.assertFalse(result["global_c03_gate_accepted"])
        self.assertFalse(result["funded_release_authorized"])
        self.assertTrue(all(not x["safe_to_terminate"] for x in result["records"]))

    def test_real_kernel_socket_parse(self):
        mapping = sockets()
        self.assertEqual(mapping[("127.0.0.1", 51203)], {2003})
        self.assertEqual(len(mapping), 4)

    def test_catalog_requires_both_hd_and_de(self):
        with self.assertRaises(m.AuditHold):
            m.parse_catalog("aoe2hd_db|aoe2hd_user|101|idle|127.0.0.1|51202|1790000001\n")

    def test_catalog_rejects_nonlocal(self):
        with self.assertRaisesRegex(m.AuditHold, "NONLOCAL"):
            m.parse_catalog(
                "aoe2de_db|aoe2de_user|100|idle|10.0.0.7|51201|1790000001\n"
                "aoe2hd_db|aoe2hd_user|101|idle|127.0.0.1|51202|1790000001\n"
            )

    def test_catalog_rejects_wrong_role(self):
        with self.assertRaises(m.AuditHold):
            m.parse_catalog(
                "aoe2de_db|postgres|100|idle|127.0.0.1|51201|1790000001\n"
                "aoe2hd_db|aoe2hd_user|101|idle|127.0.0.1|51202|1790000001\n"
            )

    def test_catalog_rejects_duplicate_backend(self):
        with self.assertRaises(m.AuditHold):
            m.parse_catalog(
                "aoe2de_db|aoe2de_user|101|idle|127.0.0.1|51201|1790000001\n"
                "aoe2hd_db|aoe2hd_user|101|idle|127.0.0.1|51202|1790000001\n"
            )

    def test_pg_population_changes_during_audit(self):
        first = sample()
        other = sample()
        other[101]["source_port"] = 61202
        with self.assertRaisesRegex(m.AuditHold, "POPULATION_CHANGED"):
            m.qualify(first, sockets(), other, identities())

    def test_socket_pid_unavailable(self):
        loc = sockets()
        del loc[("127.0.0.1", 51203)]
        with self.assertRaisesRegex(m.AuditHold, "SOCKET_AMBIGUOUS"):
            m.qualify(sample(), loc, sample(), identities())

    def test_multiple_os_pids_for_source_port(self):
        loc = sockets()
        loc[("127.0.0.1", 51203)].add(2121)
        with self.assertRaises(m.AuditHold):
            m.qualify(sample(), loc, sample(), identities())

    def test_unknown_process_service(self):
        ids = identities()
        ids[2003] = ("unknown-privileged-worker.service", 333)
        with self.assertRaises(m.AuditHold):
            m.qualify(sample(), sockets(), sample(), ids)

    def test_cross_role_process_service_does_not_substitute(self):
        ids = identities()
        ids[2001] = ("aoe2hdbets-api.service", 333)
        with self.assertRaises(m.AuditHold):
            m.qualify(sample(), sockets(), sample(), ids)

    def test_rollback_cannot_disappear(self):
        ids = identities()
        ids[2003] = ("aoe2hdbets-api.service", 333)
        with self.assertRaisesRegex(m.AuditHold, "ROLLBACK"):
            m.qualify(sample(), sockets(), sample(), ids)

    def test_process_cgroup_ambiguous(self):
        self.assertEqual(
            m.parse_cgroup("0::/system.slice/aoe2hdbets-web.service\n"),
            "aoe2hdbets-web.service"
        )
        with self.assertRaises(m.AuditHold):
            m.parse_cgroup(
                "0::/system.slice/aoe2hdbets-web.service/other.service\n"
            )

    def test_process_stat_comm_with_spaces(self):
        stat = "2003 (next-server (v15.5.28)) S " + " ".join(
            [str(x) for x in range(1, 40)]
        )
        self.assertEqual(m.parse_stat_start(stat), 19)

    def test_ss_requires_pid_for_local_postgres_socket(self):
        with self.assertRaises(m.AuditHold):
            m.parse_sockets(
                "ESTAB 0 0 127.0.0.1:51201 127.0.0.1:5432 users:((NO_PID))"
            )

    def test_ipv6_socket_parsing(self):
        self.assertEqual(m.endpoint("[::1]:5432"), ("::1", 5432))
        self.assertIsNone(m.endpoint("unbounded-host:5432"))
        self.assertIsNone(m.endpoint("127.0.0.1:99999"))

    def test_source_is_non_mutating(self):
        src = SOURCE.read_text()
        self.assertNotIn("pg_terminate_backend", src)
        self.assertNotIn("systemctl stop", src)
        self.assertNotIn("ALTER ROLE", src)
        self.assertNotIn("ALTER TABLE", src)
        self.assertNotIn("INSERT INTO", src)
        self.assertIn("READ ONLY", m.SOURCE_SQL)
        self.assertIn("ROLLBACK", m.SOURCE_SQL)


if __name__ == "__main__":
    unittest.main()
