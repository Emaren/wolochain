#!/usr/bin/env python3
"""C04 exact legacy refund #9645: prove a local prebroadcast refusal, never payment.

Offline only. This is a source-bound, independently NONAUTHORIZING case
classification against two separately hashed local observations. An absent
legacy broadcast is not proof that no other financial signer ever paid.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "wolo.c04.legacy-prebroadcast-refusal-case-9645.v1"
OBSERVATION_SCHEMA = "wolo.c04.legacy-claim-wager-identity-9645.v1"
EXPECTED_VCS = "78c25985420ee41a6678c42fab8ea8d6c3b1b519"
EXPECTED_BINARY_SHA = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
EXPECTED_JOURNAL_NAME = "aoe2-bet-market-946520.json"
EXPECTED_RUN_ID = "aoe2-bet-market-946520"
EXPECTED_REQUEST_ID = "aoe2-bet-946520-bet_refund-424105"
EXPECTED_SOURCE_EVENT_ID = "bet-market-946520"
FAILURE = "ESCROW_SIGNER_UNAVAILABLE"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
MAX_BYTES = 2 << 20


class Refusal(ValueError):
    pass


def require(ok: bool, reason: str):
    if not ok:
        raise Refusal(reason)


def unique_pairs(pairs):
    d = {}
    for key, value in pairs:
        require(key not in d, "DUPLICATE_JSON_KEY")
        d[key] = value
    return d


def read_pinned(path: Path, expected_sha: str) -> dict:
    require(type(expected_sha) is str and HEX64.fullmatch(expected_sha) is not None,
            "EXPECTED_SHA_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES,
                    "SOURCE_NOT_BOUNDED_REGULAR_FILE")
            require(stat.S_IMODE(before.st_mode) & 0o077 == 0,
                    "SOURCE_NOT_PRIVATE")
            payload = bytearray()
            while len(payload) <= MAX_BYTES:
                piece = os.read(fd, min(65536, MAX_BYTES + 1 - len(payload)))
                if not piece:
                    break
                payload.extend(piece)
            after = os.fstat(fd)
            require((len(payload), after.st_ino, after.st_mtime_ns,
                     after.st_ctime_ns, after.st_size) ==
                    (before.st_size, before.st_ino, before.st_mtime_ns,
                     before.st_ctime_ns, before.st_size), "SOURCE_CHANGED_DURING_READ")
        finally:
            os.close(fd)
        require(hashlib.sha256(payload).hexdigest() == expected_sha, "SOURCE_SHA_MISMATCH")
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_pairs,
                            parse_constant=lambda _: require(False, "NONFINITE_JSON"))
        require(type(result) is dict, "SOURCE_JSON_OBJECT_REQUIRED")
        return result
    except Refusal:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise Refusal("SOURCE_UNAVAILABLE") from None


def positive_int(v, label):
    require(type(v) is int and 0 < v < 10**12, label)
    return v


def utc_timestamp(value, reason):
    require(type(value) is str and 10 <= len(value) <= 40, reason)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Refusal(reason) from None
    require(dt.tzinfo is not None and dt.utcoffset() == timedelta(0), reason)
    return dt


def wallet_digest(address):
    require(type(address) is str and address.startswith("wolo1") and
            40 <= len(address) <= 100, "INVALID_JOURNAL_WALLET")
    return hashlib.sha256(address.lower().encode("utf-8")).hexdigest()


def classify(observation: dict, journal: dict, input_hashes: dict) -> dict:
    require(observation.get("schema") == OBSERVATION_SCHEMA, "OBSERVATION_SCHEMA_DRIFT")
    require(observation.get("legacy_binary_vcs") == EXPECTED_VCS and
            observation.get("legacy_binary_sha256") == EXPECTED_BINARY_SHA,
            "LEGACY_SOURCE_BINARY_NOT_PINNED")
    require(observation.get("wallet_material_exported") is False and
            observation.get("production_mutated") is False,
            "OBSERVATION_NOT_NONMUTATING")
    require(observation.get("service_name") == "wolochain-mainnet-settlement.service"
            and observation.get("running_process_executable_matches_disk") is True,
            "EXECUTABLE_SERVICE_IDENTITY_NOT_VERIFIED")
    installed = utc_timestamp(observation.get("legacy_binary_mtime_utc"),
                              "BINARY_INSTALL_TIME_NOT_VERIFIED")
    started = utc_timestamp(observation.get("service_active_enter_utc"),
                            "SERVICE_START_TIME_NOT_VERIFIED")
    observed = utc_timestamp(observation.get("observed_utc"),
                             "LIVE_OBSERVATION_TIME_NOT_VERIFIED")
    recorded = utc_timestamp(journal.get("updated_at"),
                             "JOURNAL_RECORD_TIME_NOT_VERIFIED")
    require(installed <= started <= recorded <= observed,
            "BINARY_START_JOURNAL_TEMPORAL_BINDING_UNVERIFIED")
    claim = observation.get("claim")
    wager = observation.get("wager")
    require(type(claim) is dict and type(wager) is dict, "SOURCE_ROW_MISSING")
    require(claim.get("id") == 9645 and claim.get("source_market_id") == 946520
            and claim.get("amount_wolo") == 100 and claim.get("claim_kind") == "bet_refund"
            and claim.get("status") == "pending"
            and claim.get("payout_attempted_at_present") is True
            and claim.get("payout_tx_hash_present") is False,
            "CLAIM_IDENTITY_OR_FATE_UNVERIFIED")
    require(wager.get("id") == 1483 and wager.get("market_id") == 946520
            and wager.get("amount_wolo") == 100 and wager.get("status") == "void"
            and wager.get("stake_tx_hash_present") is True
            and wager.get("payout_tx_hash_present") is False,
            "ORIGINAL_WAGER_IDENTITY_UNVERIFIED")
    digest = observation.get("recipient_wallet_sha256")
    require(type(digest) is str and HEX64.fullmatch(digest) is not None,
            "RECIPIENT_HASH_MISSING")
    require(journal.get("fingerprint") is not None and
            type(journal.get("request")) is dict and
            type(journal.get("response")) is dict, "LEGACY_JOURNAL_FORMAT_INVALID")
    request, response = journal["request"], journal["response"]
    require(request.get("settlement_run_id") == EXPECTED_RUN_ID
            and request.get("source_app") == "aoe2hdbets"
            and request.get("source_event_id") == EXPECTED_SOURCE_EVENT_ID
            and request.get("signer_role") == "escrow", "JOURNAL_IDENTITY_INVALID")
    payouts = request.get("payouts")
    results = response.get("payouts")
    require(type(payouts) is list and len(payouts) == 1
            and type(results) is list and len(results) == 1
            and type(payouts[0]) is dict and type(results[0]) is dict,
            "EXACTLY_ONE_PAYOUT_REQUIRED")
    pay, result = payouts[0], results[0]
    require(pay.get("request_id") == EXPECTED_REQUEST_ID and
            pay.get("amount_uwolo") == "100000000" and
            wallet_digest(pay.get("to_address")) == digest,
            "JOURNAL_RECIPIENT_AMOUNT_NOT_BOUND")
    require(response.get("settlement_run_id") == EXPECTED_RUN_ID
            and response.get("signer_role") == "escrow"
            and response.get("status") == "failed"
            and response.get("ok") is False
            and response.get("retryable") is False
            and response.get("failure_code") == FAILURE
            and response.get("executed_payout_count") == 0
            and response.get("confirmed_payout_count") == 0
            and response.get("requested_payout_count") == 1
            and response.get("requested_total_uwolo") == "100000000"
            and response.get("idempotent_replay") is False,
            "LEGACY_RUN_NOT_PREBROADCAST_REFUSAL")
    require(type(response.get("detail")) is str and
            response["detail"].startswith('could not resolve escrow signer "mainnet-escrow"'),
            "SIGNER_RESOLUTION_PRECONDITION_MISSING")
    require(result.get("request_id") == EXPECTED_REQUEST_ID
            and result.get("amount_uwolo") == "100000000"
            and result.get("status") == "failed"
            and result.get("failure_code") == FAILURE
            and result.get("ok") is False
            and result.get("retryable") is False
            and not result.get("tx_hash"), "PAYOUT_BROADCAST_UNCERTAINTY")
    require(set(input_hashes) == {"observation", "journal"} and
            all(type(x) is str and HEX64.fullmatch(x) for x in input_hashes.values()),
            "INPUT_HASHES_NOT_BOUND")
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "scope": "claim-9645-market-946520-only",
        "source_revision_bound": EXPECTED_VCS,
        "source_binary_active_before_journal_record": True,
        "journal_recorded_utc": journal["updated_at"],
        "local_legacy_journal_prebroadcast_refusal": True,
        "legacy_run_failure_code": FAILURE,
        "local_legacy_executor_broadcast_count_evidenced": 0,
        "recipient_amount_and_wager_matched": True,
        "same_operator_evidence_only": True,
        "independent_canonical_chain_finality_proved": False,
        "any_other_signer_or_journal_absence_proved": False,
        "claim_paid_or_unpaid_proved": False,
        "retry_authorized": False,
        "financial_release_authorized": False,
        "production_mutated": False,
        "inputs_sha256": input_hashes,
        "next_evidence": "independent canonical-chain recipient/amount/memo history; complete writer/signer inventory and authenticated historical source identity"
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--sha256-observation", required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--sha256-journal", required=True)
    args = parser.parse_args(argv)
    try:
        require(args.journal.name == EXPECTED_JOURNAL_NAME,
                "JOURNAL_FILENAME_NOT_CASE_BOUND")
        hashes = {"observation": args.sha256_observation, "journal": args.sha256_journal}
        obs = read_pinned(args.observation, hashes["observation"])
        journal = read_pinned(args.journal, hashes["journal"])
        result = classify(obs, journal, hashes)
    except Refusal as exc:
        print(json.dumps({"schema": SCHEMA, "status": "STOP", "reason": str(exc),
                          "financial_release_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 3


if __name__ == "__main__":
    sys.exit(main())
