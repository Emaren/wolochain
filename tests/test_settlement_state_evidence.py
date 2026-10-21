"""Adversarial local state fixtures; no live state, networking or signers."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "settlement-state-evidence.py"
spec = importlib.util.spec_from_file_location("settlement_state_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class SettlementStateEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "primary"
        self.root.mkdir()

    def request(self, request_id="request-001", status="unverifiable", tx="", role="payout", retryable=False):
        request = {"request_id": request_id, "to_address": "wolo1recipient", "amount_uwolo": "1000000", "memo": "PRIVATE_MEMO", "signer_role": role}
        signer = "wolo1PRIVATE_SIGNER"
        fingerprint = hashlib.sha256(evidence._go_json({"request": request, "signer": signer})).hexdigest()
        return {"request": request, "fingerprint": fingerprint, "response": {
            "ok": status in {"confirmed", "accepted"}, "status": status,
            "confirmation_status": "confirmed" if status == "confirmed" else "unverifiable",
            "retryable": retryable, "request_id": request_id, "chain_id": "wolo-1", "signer_role": role,
            "signer_address": signer, "tx_hash": tx,
            "detail": "PRIVATE_DETAIL", "failure_code": "PRIVATE_FAILURE"}, "updated_at": "2026-10-16T00:00:00Z"}

    def put(self, folder, name, record, root=None):
        directory = (root or self.root) / folder
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_text(json.dumps(record), encoding="utf8")
        return path

    def receipt(self, record, root=None):
        tx = record["response"]["tx_hash"] or "A" * 64
        value = {"version": "wolo.settlement.confirmation.v1", "chain_id": "wolo-1", "tx_hash": tx,
                 "transfer_index": 0, "request_id": record["request"]["request_id"],
                 "signer_address": record["response"]["signer_address"], "fingerprint": record["fingerprint"]}
        return self.put("confirmation-receipts", tx + "-0.json", value, root)

    def inspect(self, *roots):
        return evidence.inspect_state(roots or (self.root,))

    def error(self, code, *roots):
        with self.assertRaisesRegex(evidence.EvidenceError, "^" + code + "$"):
            self.inspect(*roots)

    def test_empty_is_complete_local_observation_never_global_absence_or_drain(self):
        output = self.inspect()
        self.assertEqual(output["status"], "HELD")
        self.assertTrue(output["observation_complete"])
        for key in ("observation_atomic", "chain_proof_verified", "all_historical_paths_covered", "founder_889_resolved", "financial_drained", "rollback_compatible", "release_authorized", "retry_authorized", "filesystem_writes"):
            self.assertIs(output[key], False, key)
        self.assertIn("LOCAL_STATE_CANNOT_CERTIFY_GLOBAL_DRAIN", output["blockers"])

    def test_legacy_and_current_request_shapes_preserve_holds_for_both_roles(self):
        for role in ("payout", "escrow"):
            with self.subTest(role=role):
                record = self.request(role=role)
                if role == "payout":
                    del record["response"]["confirmation_status"]  # legacy JSON ignores new optional evidence
                self.put("requests", "request-001.json", record)
                output = self.inspect()
                self.assertEqual(output["counts"]["nonretryable_nohash_holds"], 1)
                self.assertIn("UNRESOLVED_RECORDED_OUTCOME", output["blockers"])
                self.assertFalse(output["rollback_compatible"])

    def test_terminal_recorded_confirmed_and_failed_are_not_reverified_chain_outcomes(self):
        self.put("requests", "request-001.json", self.request(status="confirmed", tx="A" * 64))
        self.put("requests", "request-002.json", self.request("request-002", status="failed", tx="B" * 64))
        self.put("requests", "request-003.json", self.request("request-003", status="failed"))
        output = self.inspect()
        self.assertEqual(output["counts"]["recorded_payment_not_reverified"], 1)
        self.assertEqual(output["counts"]["recorded_chain_failure_not_reverified"], 1)
        self.assertEqual(output["counts"]["recorded_local_failure_not_payment"], 1)
        self.assertFalse(output["chain_proof_verified"])
        self.assertFalse(output["release_authorized"])

    def test_accepted_pending_retryable_and_unknown_each_hold(self):
        for status in ("accepted", "pending", "unverifiable", "new_unknown"):
            with self.subTest(status=status):
                self.put("requests", "request-001.json", self.request(status=status, retryable=True))
                output = self.inspect()
                self.assertIn("UNRESOLVED_RECORDED_OUTCOME", output["blockers"])
                self.assertIn("RETRYABLE_RECORD_REQUIRES_RECONCILIATION", output["blockers"])

    def test_fingerprint_matches_independent_go_encoding_json_reference(self):
        # Independently generated using encoding/json.Marshal and sha256 in Go.
        record = self.request()
        record["request"]["memo"] = "memo <>& · \u2028\u2029"
        record["response"]["signer_address"] = "wolo1signer"
        record["fingerprint"] = "4fb626a227cdf5c94b36d9ce1aa55b1fddad77933bec36cc664d085b49723fd9"
        self.put("requests", "request-001.json", record)
        self.assertEqual(self.inspect()["counts"]["requests"], 1)

    def test_recorded_execution_code_zero_omission_is_valid_but_forged_code_is_refused(self):
        for code in (None, 0, 7, True, -1, 1 << 32, "0"):
            with self.subTest(code=code):
                record = self.request(status="confirmed", tx="A" * 64)
                if code is not None:
                    record["response"]["code"] = code
                self.put("requests", "request-001.json", record)
                if code is None or (type(code) is int and code == 0):
                    self.assertEqual(self.inspect()["counts"]["recorded_payment_not_reverified"], 1)
                else:
                    self.error("INCONSISTENT_RECORDED_CONFIRMATION" if code == 7 else "INVALID_RECORDED_EXECUTION_CODE")

    def test_missing_legacy_optional_request_fields_use_go_omitempty(self):
        record = self.request()
        del record["request"]["memo"]
        del record["request"]["signer_role"]
        record["fingerprint"] = hashlib.sha256(evidence._go_json({"request": record["request"], "signer": record["response"]["signer_address"]})).hexdigest()
        self.put("requests", "request-001.json", record)
        self.assertEqual(self.inspect()["counts"]["requests"], 1)

    def test_hash_changes_with_content_and_layout_and_is_reproducible(self):
        path = self.put("requests", "request-001.json", self.request())
        first = self.inspect()
        before = path.read_bytes()
        self.assertEqual(first, self.inspect())
        self.assertEqual(path.read_bytes(), before)
        path.write_bytes(before + b"\n")
        second = self.inspect()
        self.assertNotEqual(first["source_tree_sha256"], second["source_tree_sha256"])
        (self.root / "locks").mkdir()
        self.assertNotEqual(second["source_tree_sha256"], self.inspect()["source_tree_sha256"])

    def test_private_addresses_memos_names_and_raw_errors_never_print(self):
        self.put("requests", "request-PRIVATE_NAME.json", self.request("request-PRIVATE_NAME"))
        output = json.dumps(self.inspect())
        for private in ("PRIVATE", "wolo1recipient", "request-PRIVATE_NAME", str(self.root)):
            self.assertNotIn(private, output)
        self.assertEqual(self.inspect()["accounting"]["leaf_record_requested_principal_uwolo"], "1000000")

    def test_locks_and_temporary_files_are_hashed_never_removed_or_declared_stale_safe(self):
        for folder, name in (("locks", "request-001.lock"), ("run-locks", "run-001.lock"), ("challenge-locks", "challenge-001.lock"), ("requests", "request-001.json.tmp"), ("confirmation-receipts", ".receipt-a.tmp")):
            self.put(folder, name, {"PRIVATE": "untouched"})
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        output = self.inspect()
        self.assertEqual(output["counts"]["locks"], 3)
        self.assertEqual(output["counts"]["temporary_files"], 2)
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_duplicate_transaction_across_obligations_holds(self):
        self.put("requests", "request-001.json", self.request(status="confirmed", tx="A" * 64))
        self.put("requests", "request-002.json", self.request("request-002", status="confirmed", tx="A" * 64))
        self.assertIn("TRANSACTION_REUSED_BY_DISTINCT_REQUESTS", self.inspect()["blockers"])

    def test_receipt_matches_complete_owner_but_does_not_certify_old_binary(self):
        record = self.request(status="confirmed", tx="A" * 64)
        self.put("requests", "request-001.json", record)
        self.receipt(record)
        output = self.inspect()
        self.assertIn("LEGACY_BINARY_IGNORES_CONFIRMATION_RECEIPTS", output["blockers"])
        self.assertNotIn("RECEIPT_REQUEST_OWNERSHIP_MISMATCH", output["blockers"])

    def test_orphan_receipt_and_prebroadcast_owner_are_explicitly_unresolved(self):
        record = self.request()
        self.receipt(record)
        self.assertIn("RECEIPT_WITHOUT_OBSERVED_REQUEST", self.inspect()["blockers"])
        self.put("requests", "request-001.json", record)
        self.assertIn("RECEIPT_WITHOUT_FINAL_REQUEST_OUTCOME", self.inspect()["blockers"])

    def test_receipt_wrong_owner_is_not_absorbed_as_valid_confirmation(self):
        record = self.request(status="confirmed", tx="A" * 64)
        self.put("requests", "request-001.json", record)
        path = self.receipt(record)
        value = json.loads(path.read_text()); value["fingerprint"] = "B" * 64
        path.write_text(json.dumps(value))
        self.assertIn("RECEIPT_REQUEST_OWNERSHIP_MISMATCH", self.inspect()["blockers"])

    def test_cross_lane_duplicate_receipt_is_held_even_same_owner(self):
        other = Path(self.tmp.name).resolve() / "founder"; other.mkdir()
        record = self.request(status="confirmed", tx="A" * 64)
        for root in (self.root, other):
            self.put("requests", "request-001.json", record, root)
            self.receipt(record, root)
        output = self.inspect(self.root, other)
        self.assertIn("CROSS_LANE_RECEIPT_REUSE", output["blockers"])
        self.assertIn("TRANSACTION_REUSED_BY_DISTINCT_REQUESTS", output["blockers"])

    def run_record(self, status="unverifiable"):
        request = {"settlement_run_id": "run-001", "signer_role": "payout", "payouts": [{"index": 0, "request_id": "request-001", "to_address": "wolo1recipient", "amount_uwolo": "1000000", "memo": "PRIVATE"}]}
        return {"request": request, "fingerprint": hashlib.sha256(evidence._go_json(request)).hexdigest(), "response": {"settlement_run_id": "run-001", "ok": False, "status": status, "retryable": False}}

    def test_group_status_compatibility_is_not_conflated_with_child_payment_proof(self):
        self.put("runs", "run-001.json", self.run_record())
        output = self.inspect()
        self.assertIn("LEGACY_AGGREGATE_UNVERIFIABLE_NOT_FINAL", output["blockers"])
        self.assertIn("AGGREGATE_CHILD_OUTCOMES_REQUIRE_RECONCILIATION", output["blockers"])
        self.assertNotIn("recorded_payment_not_reverified", output["counts"])

    def test_duplicate_run_child_and_bad_ordinal_refused(self):
        for mode in ("duplicate", "ordinal"):
            with self.subTest(mode=mode):
                record = self.run_record()
                if mode == "duplicate":
                    record["request"]["payouts"].append({**record["request"]["payouts"][0], "index": 1})
                    code = "DUPLICATE_RUN_REQUEST"
                else:
                    record["request"]["payouts"][0]["index"] = True
                    code = "INVALID_RUN_CONTEXT"
                self.put("runs", "run-001.json", record)
                self.error(code)

    def test_challenge_record_is_bounded_unvalidated_context_not_silent_certification(self):
        record = self.run_record("failed")
        record["request"]["challenge_id"] = "fixture"
        self.put("challenge-settlements", "run-001.json", record)
        self.assertIn("CHALLENGE_CONTEXT_NOT_INDEPENDENTLY_VALIDATED", self.inspect()["blockers"])

    def test_duplicate_keys_trailing_json_nan_and_malformed_are_refused(self):
        directory = self.root / "requests"; directory.mkdir()
        for data, code in ((b'{"request":{},"request":{}}', "DUPLICATE_JSON_KEY"), (b'{}{}', "INVALID_JSON"), (b'{"a":NaN}', "INVALID_JSON_NUMBER"), (b'{"a":"\\ud800"}', "INVALID_JSON_UNICODE"), (b'null', "INVALID_RECORD_SHAPE"), (b'\xff', "INVALID_JSON"), (b'{', "INVALID_JSON")):
            with self.subTest(data=data):
                (directory / "request-001.json").write_bytes(data)
                self.error(code)

    def test_request_fingerprint_identity_and_context_tampering_refused(self):
        cases = ((lambda r: r.update(fingerprint="A" * 64), "REQUEST_FINGERPRINT_MISMATCH"),
                 (lambda r: r["request"].update(amount_uwolo="00"), "INVALID_REQUEST_CONTEXT"),
                 (lambda r: r["response"].update(request_id="wrong-id"), "REQUEST_IDENTITY_MISMATCH"),
                 (lambda r: r["response"].update(chain_id="wolo-testnet"), "REQUEST_IDENTITY_MISMATCH"),
                 (lambda r: r["response"].update(signer_role="escrow"), "REQUEST_ROLE_MISMATCH"),
                 (lambda r: r["response"].update(amount_uwolo="999"), "REQUEST_CONTEXT_MISMATCH"),
                 (lambda r: r["response"].update(status="failed", ok=True), "INCONSISTENT_RECORDED_FAILURE"),
                 (lambda r: r["request"].update(unknown="PRIVATE"), "UNSUPPORTED_REQUEST_SCHEMA"),
                 (lambda r: r["response"].update(retryable="false"), "INVALID_RESPONSE_SHAPE"),
                 (lambda r: r["response"].update(tx_hash="not-a-hash"), "INVALID_TX_HASH"),
                 (lambda r: r["response"].update(status="confirmed", ok=True), "INCONSISTENT_RECORDED_CONFIRMATION"))
        for mutation, code in cases:
            with self.subTest(code=code):
                record = self.request(); mutation(record)
                self.put("requests", "request-001.json", record)
                self.error(code)

    def test_invalid_receipt_index_and_extra_fields_refused(self):
        record = self.request(status="confirmed", tx="A" * 64)
        path = self.receipt(record)
        original = path.read_text()
        for change in ({"transfer_index": True}, {"transfer_index": 1}, {"chain_id": "other"}, {"extra": "PRIVATE"}):
            with self.subTest(change=change):
                value = json.loads(original); value.update(change); path.write_text(json.dumps(value))
                self.error("INVALID_RECEIPT_CONTEXT")

    def test_symlink_file_directory_ancestor_root_and_hardlink_refused(self):
        path = self.put("requests", "request-001.json", self.request())
        target = path.with_suffix(".saved"); path.rename(target); path.symlink_to(target)
        self.error("UNSAFE_STATE_ENTRY")
        path.unlink(); target.rename(path)
        hardlink = path.parent / "request-002.json"; os.link(path, hardlink)
        self.error("UNSAFE_STATE_ENTRY")
        hardlink.unlink()
        alias = Path(self.tmp.name).resolve() / "alias"; alias.symlink_to(self.root, target_is_directory=True)
        self.error("STATE_UNAVAILABLE_OR_UNSAFE", alias)
        self.error("STATE_UNAVAILABLE_OR_UNSAFE", alias / "requests")
        path.unlink(); (self.root / "requests").rmdir()
        (self.root / "requests").symlink_to(Path(self.tmp.name).resolve(), target_is_directory=True)
        self.error("STATE_UNAVAILABLE_OR_UNSAFE")

    def test_unknown_nested_layout_is_refused_not_omitted_from_tree_hash(self):
        self.put("requests", "unknown.bin", {})
        self.error("UNSUPPORTED_STATE_LAYOUT")
        (self.root / "requests" / "unknown.bin").unlink()
        (self.root / "requests" / "nested").mkdir()
        self.error("UNSAFE_STATE_ENTRY")

    def test_limits_and_duplicate_roots_refuse_complete_observation(self):
        self.error("ROOT_COUNT_LIMIT", self.root, self.root, self.root)
        self.error("DUPLICATE_STATE_ROOT", self.root, self.root)
        path = self.put("requests", "request-001.json", self.request())
        for setting, limit, code in (("MAX_FILE_BYTES", 1, "FILE_SIZE_LIMIT"), ("MAX_TOTAL_BYTES", 1, "TOTAL_SIZE_LIMIT"), ("MAX_ENTRIES", 1, "ENTRY_LIMIT"), ("MAX_JSON_NODES", 1, "JSON_RESOURCE_LIMIT"), ("MAX_JSON_DEPTH", 1, "JSON_RESOURCE_LIMIT")):
            with self.subTest(setting=setting), mock.patch.object(evidence, setting, limit):
                self.error(code)
        self.assertTrue(path.exists())

    def test_replacement_or_change_during_read_refuses(self):
        self.put("requests", "request-001.json", self.request())
        original = evidence._read
        def changed(fd, name, budget):
            data = original(fd, name, budget)
            (self.root / "requests" / "new.lock").write_text("changed")
            return data
        with mock.patch.object(evidence, "_read", changed):
            self.error("STATE_CHANGED_DURING_READ")

    def test_cli_exit_three_is_held_and_exit_two_is_sanitized_error(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(evidence.main(["--state-root", str(self.root)]), 3)
        self.assertEqual(json.loads(output.getvalue())["status"], "HELD")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(evidence.main(["--state-root", str(self.root / "PRIVATE_ABSENT")]), 2)
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["observation_complete"])

    def test_exact_recorded_money_by_lane_role_status_is_not_chain_payment(self):
        other = Path(self.tmp.name).resolve() / "founder"; other.mkdir()
        for root, name, status, role, amount, tx in (
            (self.root, "request-001", "confirmed", "payout", "9007199254740993", "A" * 64),
            (self.root, "request-002", "accepted", "escrow", "100000001", "B" * 64),
            (other, "request-003", "failed", "payout", "7", "C" * 64),
        ):
            record = self.request(name, status=status, role=role, tx=tx)
            record["request"]["amount_uwolo"] = amount
            self.refresh_request(record)
            self.put("requests", name + ".json", record, root)
        accounting = self.inspect(self.root, other)["accounting"]
        rows = {(row["lane_index"], row["signer_role"], row["recorded_status"]):row for row in accounting["amount_groups"]}
        self.assertEqual(rows[(0,"payout","confirmed")]["recorded_requested_principal_uwolo"], "9007199254740993")
        self.assertEqual(accounting["leaf_record_requested_principal_uwolo"], "9007199354741001")
        self.assertEqual(accounting["observed_execution_principal_min_uwolo"], "0")
        self.assertEqual(accounting["observed_execution_principal_max_uwolo"], "9007199354741001")
        self.assertIsNone(accounting["global_liability_upper_bound_uwolo"])
        self.assertEqual(accounting["global_liability_bound"], "UNBOUNDED_NOT_PROVEN")
        self.assertFalse(accounting["recorded_status_is_chain_proof"])
        self.assertFalse(accounting["fees_included"])

    def refresh_request(self, record):
        record["fingerprint"] = hashlib.sha256(evidence._go_json({"request": record["request"], "signer": record["response"]["signer_address"]})).hexdigest()

    def matching_run(self, leaf, run_id="run-001"):
        req = leaf["request"]
        request = {"settlement_run_id": run_id, "signer_role": req.get("signer_role", "payout"),
                   "payouts": [{"index": 0, **{key: value for key,value in req.items() if key != "signer_role"}}]}
        return {"request": request, "fingerprint": hashlib.sha256(evidence._go_json(request)).hexdigest(),
                "response": {"settlement_run_id": run_id,"ok":True,"status":"confirmed","retryable":False}}

    def test_repeated_aggregate_references_never_add_to_leaf_money(self):
        leaf = self.request()
        self.put("requests", "request-001.json", leaf)
        for run_id in ("run-001", "run-002"):
            self.put("runs", run_id + ".json", self.matching_run(leaf, run_id))
        accounting = self.inspect()["accounting"]
        self.assertEqual(accounting["deduplicated_observed_requested_principal_uwolo"], "1000000")
        self.assertEqual(accounting["unique_obligation_count"], 1)
        self.assertEqual(accounting["deduplicated_aggregate_references"], 2)
        self.assertEqual(accounting["amount_groups"][0]["request_count"], 1)

    def test_run_only_child_is_visible_as_a_gap_not_a_confirmed_payment(self):
        self.put("runs", "run-001.json", self.matching_run(self.request()))
        accounting = self.inspect()["accounting"]
        self.assertFalse(accounting["complete_for_observed_requests_and_runs"])
        self.assertEqual(accounting["aggregate_only_obligation_count"], 1)
        self.assertIn("AGGREGATE_CHILD_WITHOUT_REQUEST_RECORD", accounting["gaps"])
        self.assertEqual(accounting["amount_groups"][0]["recorded_status"], "aggregate_only")
        self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])

    def test_conflicting_child_context_never_produces_a_finite_accounting_bound(self):
        for field, value in (("amount_uwolo","2000000"),("to_address","wolo1different"),("memo","different")):
            with self.subTest(field=field):
                leaf = self.request()
                self.put("requests", "request-001.json", leaf)
                run = self.matching_run(leaf)
                run["request"]["payouts"][0][field] = value
                run["fingerprint"] = hashlib.sha256(evidence._go_json(run["request"])).hexdigest()
                self.put("runs", "run-001.json", run)
                accounting = self.inspect()["accounting"]
                self.assertIn("ACCOUNTING_OBLIGATION_CONTEXT_CONFLICT", accounting["gaps"])
                self.assertIsNone(accounting["deduplicated_observed_requested_principal_uwolo"])
                self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])

    def test_cross_lane_ids_stay_separate_and_tx_reuse_never_nets_money(self):
        other = Path(self.tmp.name).resolve() / "founder"; other.mkdir()
        leaf = self.request(status="confirmed", tx="A" * 64)
        for root in (self.root, other):
            self.put("requests", "request-001.json", leaf, root)
        out = self.inspect(self.root, other)
        self.assertEqual(out["accounting"]["leaf_record_requested_principal_uwolo"], "2000000")
        self.assertIn("TRANSACTION_REUSED_BY_DISTINCT_REQUESTS", out["accounting"]["gaps"])
        self.assertIsNone(out["accounting"]["observed_execution_principal_max_uwolo"])

    def test_unknown_status_challenge_context_or_lock_never_looks_complete(self):
        leaf = self.request(status="future_status")
        self.put("requests", "request-001.json", leaf)
        accounting = self.inspect()["accounting"]
        self.assertFalse(accounting["complete_for_observed_requests_and_runs"])
        self.assertIn("UNKNOWN_RECORDED_STATUS", accounting["gaps"])
        self.assertEqual(accounting["amount_groups"][0]["recorded_status"], "unknown")
        self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])
        self.put("locks", "request.lock", {})
        self.assertIn("LOCK_PRESENT_NOT_SAFE_TO_DELETE", self.inspect()["accounting"]["gaps"])

    def test_integer_overflow_float_padded_and_missing_amounts_fail_closed(self):
        for value in (None, "00", "1.5", 1, True, str(1 << 63)):
            with self.subTest(amount=value):
                leaf = self.request()
                if value is None:
                    del leaf["request"]["amount_uwolo"]
                else:
                    leaf["request"]["amount_uwolo"] = value
                self.put("requests", "request-001.json", leaf)
                with self.assertRaises(evidence.EvidenceError):
                    self.inspect()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(evidence.main(["--state-root",str(self.root)]), 2)
        accounting = json.loads(output.getvalue())["accounting"]
        self.assertIsNone(accounting["leaf_record_requested_principal_uwolo"])
        self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])

    def test_sums_larger_than_signed64_stay_exact_without_float_or_wrap(self):
        for name in ("request-001","request-002"):
            leaf = self.request(name)
            leaf["request"]["amount_uwolo"] = str((1 << 63) - 1)
            self.refresh_request(leaf)
            self.put("requests",name + ".json",leaf)
        self.assertEqual(self.inspect()["accounting"]["leaf_record_requested_principal_uwolo"], "18446744073709551614")

    def test_legacy_omitted_signer_role_is_default_payout_not_zero_or_refused(self):
        leaf = self.request(status="accepted", tx="A" * 64)
        del leaf["request"]["signer_role"]
        del leaf["response"]["signer_role"]
        self.refresh_request(leaf)
        self.put("requests", "request-001.json", leaf)
        accounting = self.inspect()["accounting"]
        self.assertEqual(accounting["amount_groups"], [{"lane_index": 0, "signer_role": "payout",
                         "recorded_status": "accepted", "request_count": 1,
                         "recorded_requested_principal_uwolo": "1000000"}])

    def test_role_conflict_or_unsupported_run_role_never_nets_obligations(self):
        leaf = self.request()
        self.put("requests", "request-001.json", leaf)
        run = self.matching_run(leaf)
        run["request"]["signer_role"] = "escrow"
        run["fingerprint"] = hashlib.sha256(evidence._go_json(run["request"])).hexdigest()
        path = self.put("runs", "run-001.json", run)
        self.assertIn("ACCOUNTING_OBLIGATION_CONTEXT_CONFLICT", self.inspect()["accounting"]["gaps"])
        run["request"]["signer_role"] = "treasury"
        path.write_text(json.dumps(run))
        self.error("UNSUPPORTED_SIGNER_ROLE")

    def test_aggregate_only_duplicate_references_deduplicate_but_leave_gap(self):
        for run_id in ("run-001", "run-002"):
            self.put("runs", run_id + ".json", self.matching_run(self.request(), run_id))
        accounting = self.inspect()["accounting"]
        self.assertEqual(accounting["unique_obligation_count"], 1)
        self.assertEqual(accounting["deduplicated_aggregate_references"], 1)
        self.assertEqual(accounting["deduplicated_observed_requested_principal_uwolo"], "1000000")
        self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])

    def test_historical_attempts_and_fees_never_receive_finite_outflow_bound(self):
        self.put("requests", "request-001.json", self.request(status="failed", retryable=True))
        accounting = self.inspect()["accounting"]
        self.assertIn("RETRYABLE_RECORD_REQUIRES_RECONCILIATION", accounting["gaps"])
        self.assertIsNone(accounting["observed_execution_principal_max_uwolo"])
        self.assertIsNone(accounting["historical_outflow_upper_bound_uwolo"])
        self.assertFalse(accounting["fees_included"])

    def test_stdin_cli_is_held_without_remote_source_file_or_self_certification(self):
        self.put("requests", "request-001.json", self.request())
        before = {str(path):path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, "-I", "-", "--state-root", str(self.root)],
                                input=SCRIPT.read_bytes(), capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 3, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNone(output["reader_source_sha256"])
        self.assertEqual(output["reader_source_identity"], "EXTERNAL_EXACT_SOURCE_PROVENANCE_REQUIRED")
        self.assertFalse(output["chain_proof_verified"])
        self.assertFalse(output["release_authorized"])
        self.assertEqual(before, {str(path):path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_missing_symlink_or_nonregular_module_source_requires_external_provenance(self):
        alias = Path(self.tmp.name).resolve() / "source-link"
        alias.symlink_to(SCRIPT)
        for source in ("<stdin>", "-", str(alias), str(self.root), str(self.root / "missing")):
            with self.subTest(source=source), mock.patch.object(evidence, "__file__", source):
                output = self.inspect()
                self.assertIsNone(output["reader_source_sha256"])
                self.assertEqual(output["reader_source_identity"], "EXTERNAL_EXACT_SOURCE_PROVENANCE_REQUIRED")
        self.assertEqual(self.inspect()["reader_source_sha256"], hashlib.sha256(SCRIPT.read_bytes()).hexdigest())


    def _focus_escrow_fixture(self, request_id, status="confirmed", tx=None):
        record = self.request(request_id, status=status,
                              tx=tx if tx is not None else "A" * 64, role="escrow")
        record["request"]["amount_uwolo"] = "100000000"
        self.refresh_request(record)
        self.put("requests", request_id + ".json", record)
        return record

    def test_focus_escrow_100_returns_accepted_and_bounded_confirmed_without_wallets(self):
        accepted = self._focus_escrow_fixture("escrow-accepted", "accepted", "B" * 64)
        for i in range(20):
            self._focus_escrow_fixture(f"escrow-conf-{i:03d}", "confirmed",
                                       f"{i+1:064x}")
        one = self.request("other-amount", status="confirmed", tx="C" * 64,
                           role="escrow")
        self.put("requests", "other-amount.json", one)
        normal = evidence.inspect_state((self.root,))
        self.assertNotIn("escrow100Focus", normal)
        focused = evidence.inspect_state((self.root,), focus_escrow_100=True)
        focus = focused["escrow100Focus"]
        self.assertEqual(focus["matchedAcceptedCount"], 1)
        self.assertEqual(focus["matchedConfirmedCount"], 20)
        self.assertEqual(len(focus["acceptedRecords"]), 1)
        self.assertEqual(len(focus["recentlyModifiedConfirmedRecords"]), 16)
        self.assertEqual(focus["confirmedRecordsOmitted"], 4)
        self.assertEqual(focus["acceptedRecords"][0]["recordedPublicTxHash"], "B" * 64)
        self.assertEqual(focus["acceptedRecords"][0]["requestIdSha256"],
                         hashlib.sha256(b"escrow-accepted").hexdigest())
        self.assertTrue(focus["publicTxHashesAreUnauthenticatedJournalClaims"])
        self.assertFalse(focus["selectionProvesLatest8NewRequests"])
        self.assertFalse(focus["mtimeIsTrustedTransferTime"])
        self.assertFalse(focus["independentChainProofVerified"])
        self.assertFalse(focus["retryAuthorized"])
        self.assertFalse(focused["chain_proof_verified"])
        excerpt = json.dumps(focus)
        for token in ("PRIVATE_MEMO", "PRIVATE_DETAIL", "PRIVATE_SIGNER",
                      "wolo1recipient", "escrow-accepted", "other-amount"):
            self.assertNotIn(token, excerpt)

    def test_focus_does_not_promote_wrong_role_or_amount(self):
        self.put("requests", "request-001.json",
                 self.request("request-001", status="confirmed", tx="A" * 64,
                              role="payout"))
        r = evidence.inspect_state((self.root,), focus_escrow_100=True)
        self.assertEqual(r["escrow100Focus"]["matchedAcceptedCount"], 0)
        self.assertEqual(r["escrow100Focus"]["matchedConfirmedCount"], 0)
        self.assertFalse(r["escrow100Focus"]["financialReleaseAuthorized"])

    def test_focus_still_rejects_invalid_confirmed_transaction(self):
        record = self._focus_escrow_fixture("escrow-accepted", "confirmed", "A" * 64)
        record["response"]["tx_hash"] = "not-a-valid-hash"
        self.put("requests", "escrow-accepted.json", record)
        with self.assertRaisesRegex(evidence.EvidenceError, "INVALID_TX_HASH"):
            evidence.inspect_state((self.root,), focus_escrow_100=True)

    def test_focus_overflow_and_nonboolean_mode_fail_closed(self):
        with self.assertRaisesRegex(evidence.EvidenceError, "INVALID_FOCUS_MODE"):
            evidence.inspect_state((self.root,), focus_escrow_100=1)
        for i in range(17):
            self._focus_escrow_fixture(f"accepted-{i:03d}", "accepted",
                                       f"{i+17:064x}")
        with self.assertRaisesRegex(evidence.EvidenceError, "FOCUS_ACCEPTED_LIMIT"):
            evidence.inspect_state((self.root,), focus_escrow_100=True)

    def test_stdin_focus_cli_never_edits_journals_or_claims_release(self):
        self._focus_escrow_fixture("escrow-accepted", "accepted", "B" * 64)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*")
                  if p.is_file()}
        result = subprocess.run([sys.executable, "-I", "-",
                                 "--state-root", str(self.root),
                                 "--focus-escrow-100"],
                                input=SCRIPT.read_bytes(), capture_output=True,
                                timeout=10, check=False)
        self.assertEqual(result.returncode, 3, result.stderr)
        data = json.loads(result.stdout)
        self.assertIsNone(data["reader_source_sha256"])
        self.assertEqual(data["escrow100Focus"]["matchedAcceptedCount"], 1)
        self.assertFalse(data["escrow100Focus"]["financialReleaseAuthorized"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*")
                                  if p.is_file()})


    def _load_escrow_delta(self):
        path = SCRIPT.with_name("compare_settlement_escrow_100_manifests.py")
        spec = importlib.util.spec_from_file_location("escrow_observed_delta", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_full_manifest_proves_observed_identity_deltas_not_chain_payments(self):
        delta = self._load_escrow_delta()
        self._focus_escrow_fixture("escrow-accepted", "accepted", "B" * 64)
        before = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                        escrow_identity_manifest=True)
        self.assertEqual(before["escrow100IdentityManifest"]["count"], 1)
        self.assertFalse(before["escrow100IdentityManifest"]["financial_release_authorized"])
        self.assertNotIn("escrow100IdentityManifest",
                         evidence.inspect_state((self.root,), focus_escrow_100=True))
        self._focus_escrow_fixture("escrow-added", "confirmed", "C" * 64)
        after = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                       escrow_identity_manifest=True)
        compared = delta.compare(before, after)
        self.assertEqual((compared["added_count"], compared["removed_count"],
                          compared["changed_count"]), (1, 0, 0))
        self.assertEqual(compared["added"][0]["requestIdSha256"],
                         hashlib.sha256(b"escrow-added").hexdigest())
        self.assertFalse(compared["historical_arrival_time_proven"])
        self.assertFalse(compared["snapshots_atomic"])
        self.assertFalse(compared["chain_proof_verified"])
        self.assertFalse(compared["financial_release_authorized"])
        self.assertFalse(compared["retry_authorized"])
        exposed = json.dumps(after["escrow100IdentityManifest"])
        for secret in ("escrow-added", "escrow-accepted", "PRIVATE_MEMO",
                       "PRIVATE_SIGNER", "wolo1recipient", "B" * 64, "C" * 64):
            self.assertNotIn(secret, exposed)

    def test_full_manifest_tracks_changed_and_removed_original_records(self):
        delta = self._load_escrow_delta()
        rec = self._focus_escrow_fixture("escrow-001", "accepted", "B" * 64)
        earlier = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                         escrow_identity_manifest=True)
        rec["response"]["status"] = "confirmed"
        rec["response"]["confirmation_status"] = "confirmed"
        rec["response"]["ok"] = True
        self.put("requests", "escrow-001.json", rec)
        later = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                       escrow_identity_manifest=True)
        changes = delta.compare(earlier, later)
        self.assertEqual((changes["changed_count"], changes["added_count"]), (1, 0))
        self.assertEqual(changes["changed"][0]["beforeStatus"], "accepted")
        self.assertEqual(changes["changed"][0]["afterStatus"], "confirmed")
        (self.root / "requests" / "escrow-001.json").unlink()
        absent = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                        escrow_identity_manifest=True)
        removed = delta.compare(later, absent)
        self.assertEqual(removed["removed_count"], 1)
        self.assertEqual(removed["added_count"], 0)
        self.assertFalse(removed["payment_outcome_certified"])

    def test_full_manifest_refuses_partial_reordered_tampered_or_untrusted_input(self):
        import copy
        delta = self._load_escrow_delta()
        self._focus_escrow_fixture("escrow-001", "accepted", "B" * 64)
        self._focus_escrow_fixture("escrow-002", "confirmed", "C" * 64)
        valid = evidence.inspect_state((self.root,), focus_escrow_100=True,
                                       escrow_identity_manifest=True)
        for mutated in (
            lambda x: x.pop("escrow100IdentityManifest"),
            lambda x: x["escrow100IdentityManifest"].update(count=1),
            lambda x: x["escrow100IdentityManifest"]["records"].reverse(),
            lambda x: x["escrow100IdentityManifest"]["records"][0].update(
                requestRecordSha256="not-a-digest"),
            lambda x: x["escrow100Focus"].update(matchedConfirmedCount=500),
            lambda x: x.update(observation_atomic=True),
            lambda x: x.update(chain_proof_verified=True),
            lambda x: x.update(release_authorized=True),
            lambda x: x.update(roots_observed=0),
        ):
            bad = copy.deepcopy(valid)
            mutated(bad)
            with self.assertRaises(delta.InvalidManifest):
                delta.compare(valid, bad)
        incomplete = evidence.inspect_state((self.root,), focus_escrow_100=True)
        with self.assertRaises(delta.InvalidManifest):
            delta.compare(incomplete, valid)
        with self.assertRaisesRegex(evidence.EvidenceError, "INVALID_FOCUS_MODE"):
            evidence.inspect_state((self.root,), escrow_identity_manifest=True)

    def test_escrow_manifest_cli_is_read_only_and_comparator_exit_three_held(self):
        delta = self._load_escrow_delta()
        self._focus_escrow_fixture("escrow-001", "accepted", "B" * 64)
        before_bytes = {str(p): p.read_bytes() for p in self.root.rglob("*")
                        if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(evidence.main(["--state-root", str(self.root),
                                            "--full-escrow-100-manifest"]), 3)
        sample = json.loads(output.getvalue())
        self.assertEqual(sample["escrow100IdentityManifest"]["count"], 1)
        old = Path(self.tmp.name) / "before.json"
        new = Path(self.tmp.name) / "after.json"
        old.write_text(json.dumps(sample))
        new.write_text(json.dumps(sample))
        p = subprocess.run([sys.executable, str(SCRIPT.with_name(
            "compare_settlement_escrow_100_manifests.py")),
            "--before", str(old), "--after", str(new)],
            capture_output=True, timeout=10, check=False)
        self.assertEqual(p.returncode, 3, p.stderr)
        compared = json.loads(p.stdout)
        self.assertEqual(compared["added_count"], 0)
        self.assertFalse(compared["financial_release_authorized"])
        self.assertTrue(compared["comparison_complete_for_supplied_manifests"])
        self.assertEqual(before_bytes, {str(path): path.read_bytes()
                                         for path in self.root.rglob("*") if path.is_file()})
        old.unlink()
        old.symlink_to(new)
        bad = subprocess.run([sys.executable, str(SCRIPT.with_name(
            "compare_settlement_escrow_100_manifests.py")),
            "--before", str(old), "--after", str(new)],
            capture_output=True, timeout=10, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertFalse(json.loads(bad.stdout)["financial_release_authorized"])


if __name__ == "__main__":
    unittest.main()
