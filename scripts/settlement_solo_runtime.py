#!/usr/bin/env python3
"""Single-owner maintenance admission and off-host one-use nonce witness.

This domain cannot authorize settlement switches, SQL, signing or funds. The
witness runs on a separately enrolled host, outside VPS backup/rollback scope.
Its SSH forced command verifies the ORIGINAL owner packet before consuming it.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

import settlement_solo_owner_intent_review as owner
import settlement_maintenance_nonce_store as nonces

DOMAIN = b"AOE2WAR-WOLO-SOLO-MAINTENANCE-RUNTIME-V1\x00"
SCHEMA = "wolo.solo-maintenance-runtime-request.v1"
PACKET_SCHEMA = "wolo.solo-maintenance-runtime-packet.v1"
CONFIG_SCHEMA = "wolo.solo-maintenance-runtime-enrollment.v1"
PROCEDURE_SCHEMA = "wolo.solo-maintenance-runtime-procedure.v2"
ACK_SCHEMA = "wolo.solo-maintenance-offhost-consumption.v1"
CONFIG = Path("/etc/wolochain-financial-maintenance/authority/solo-runtime.json")
ENROLLMENT = CONFIG.with_name("solo-owner.json")
NONCE_ROOT = Path("/var/lib/wolo-financial-authority-nonces/solo-runtime-v1")
def witness_paths(platform):
    # macOS /etc and /var are symlinks. Keep the strict canonical-file reader;
    # enroll canonical paths rather than weakening it for the owner's Mac.
    prefix = Path("/private") if platform == "darwin" else Path("/")
    return (prefix / "etc/wolochain-financial-maintenance/authority/solo-witness.json",
            prefix / "var/lib/wolo-financial-authority-nonces/solo-witness-v1")


WITNESS_CONFIG, WITNESS_NONCES = witness_paths(sys.platform)
WITNESS_ENROLLMENT = WITNESS_CONFIG.with_name("solo-owner.json")
REMOTE_COMMAND = "wolo-maintenance-witness-v1"
MODES = {"solo-capture": "live_capture", "solo-offline-restore": "offline_verify",
         "solo-resume": "resume_existing", "solo-contain": "contain_partial"}
OPS = {"live_capture": "fence-drain-capture-hd-de",
       "offline_verify": "isolated-restore-verify-sealed-archives",
       "resume_existing": "resume-original-qualified-producers",
       "contain_partial": "contain-committed-partial-resume"}
# Restore has a separate long window; it never renews the LIVE capture permit.
WINDOWS = {"live_capture": 1800, "offline_verify": 14400, "resume_existing": 1800,
           "contain_partial": 1800}
SOURCES = frozenset({"settlement_solo_runtime.py", "settlement_solo_owner_intent_review.py",
                    "settlement_maintenance_nonce_store.py", "settlement_financial_maintenance.py",
                    "settlement_resume_producer_identities.py", "settlement_solo_resume.py"})
RUNTIME_UNITS = ("wolochaind-mainnet.service", "wolochain-mainnet-settlement.service",
                 "wolochain-founder-rewards-settlement.service")
WRITERS = frozenset({"hd_web_api", "de_shared_financial_writers", "seven_timer_service_pairs",
    "postgres_dba", "manual_sql_and_ssh", "cron_and_user_systemd", "ci_and_deployment",
    "settlement_8092_8093_bearers", "offhost_wallet_and_chain_signers",
    "auxiliary_settlement_and_indexers", "hasura_secondary_targets", "wargraph_and_watcher"})
REQUEST_KEYS = {"schema", "chain_id", "phase", "operation", "source_commit",
                "host_identity_sha256", "scope_sha256", "procedure_sha256", "nonce",
                "not_before", "expires_at", "previous_phase_receipt_sha256"}
CONFIG_KEYS = {"schema", "owner_enrollment_sha256", "owner_der_sha256", "source_commit",
               "host_identity_sha256", "controller_files", "witness", "crypto"}
PROCEDURE_KEYS = {"schema", "mode", "permit_core_sha256", "fence_receipt_path", "output_path",
                  "previous_phase_receipt_path", "runtime_binaries", "writer_inventory_sha256",
                  "capture_seal", "resume_plan"}

require = owner.require
canonical = owner.canonical
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def private_file(path):
    # Portable to the owner's Mac witness. Secure final directory + no symlink
    # anywhere; source-host root additionally uses maintenance.private_read.
    p = Path(path)
    require(p.is_absolute() and p == p.resolve(strict=True), "CANONICAL_PRIVATE_PATH_REQUIRED")
    return owner.read_private(p)


def host_identity():
    if sys.platform == "darwin":
        result = subprocess.run(["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                capture_output=True, timeout=5, check=True)
        require(len(result.stdout) < 65536, "HOST_IDENTITY_UNAVAILABLE")
        values = re.findall(rb'"IOPlatformUUID"\s*=\s*"([A-Fa-f0-9-]{36})"', result.stdout)
        require(len(values) == 1, "HOST_IDENTITY_UNAVAILABLE")
        return sha(values[0].lower())
    raw = Path("/etc/machine-id").read_bytes().strip()
    require(re.fullmatch(rb"[a-f0-9]{32}", raw) is not None, "HOST_IDENTITY_UNAVAILABLE")
    return sha(raw)


def validate_request(q, now):
    require(set(q) == REQUEST_KEYS and q["schema"] == SCHEMA and q["chain_id"] == "wolo-1"
            and type(q["phase"]) is str and q["phase"] in OPS
            and q["operation"] == OPS[q["phase"]], "SOLO_RUNTIME_OPERATION_INVALID")
    require(type(q["source_commit"]) is str and owner.HEX40.fullmatch(q["source_commit"])
            and q["source_commit"] != "0" * 40 and all(owner.hex64(q[k]) for k in
                ("host_identity_sha256", "scope_sha256", "procedure_sha256")),
            "SOLO_RUNTIME_BINDINGS_INVALID")
    require(type(q["nonce"]) is str and owner.HEX32.fullmatch(q["nonce"])
            and q["nonce"] != "0" * 32, "SOLO_RUNTIME_NONCE_INVALID")
    old = q["previous_phase_receipt_sha256"]
    require(old is None if q["phase"] == "live_capture" else owner.hex64(old),
            "SOLO_RUNTIME_LINEAGE_REQUIRED")
    start, end = owner.utc(q["not_before"]), owner.utc(q["expires_at"])
    require(start <= now < end and timedelta() < end - start <=
            timedelta(seconds=WINDOWS[q["phase"]]), "SOLO_RUNTIME_WINDOW_INVALID")


def load_config(raw):
    c = owner.parse(raw)
    require(set(c) == CONFIG_KEYS and c["schema"] == CONFIG_SCHEMA,
            "SOLO_RUNTIME_ENROLLMENT_INVALID")
    require(all(owner.hex64(c[k]) for k in ("owner_enrollment_sha256", "owner_der_sha256",
                "host_identity_sha256")) and type(c["source_commit"]) is str
            and owner.HEX40.fullmatch(c["source_commit"])
            and type(c["controller_files"]) is dict and set(c["controller_files"]) == SOURCES
            and all(owner.hex64(x) for x in c["controller_files"].values()),
            "SOLO_RUNTIME_ENROLLMENT_PINS_MISSING")
    w = c["witness"]
    require(type(w) is dict and set(w) == {"host", "user", "port", "identity_path",
                "known_hosts_path", "known_hosts_sha256", "host_identity_sha256"}
            and type(w["host"]) is str and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", w["host"])
            and w["host"] not in {"localhost", "127.0.0.1"}
            and type(w["user"]) is str and re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", w["user"])
            and type(w["port"]) is int and 1 <= w["port"] <= 65535
            and all(type(w[k]) is str and Path(w[k]).is_absolute()
                    for k in ("identity_path", "known_hosts_path"))
            and owner.hex64(w["known_hosts_sha256"]) and owner.hex64(w["host_identity_sha256"])
            and w["host_identity_sha256"] != c["host_identity_sha256"],
            "SEPARATELY_ENROLLED_WITNESS_REQUIRED")
    require(type(c["crypto"]) is dict and set(c["crypto"]) == {"runtime", "witness"},
            "SOLO_RUNTIME_CRYPTO_ENROLLMENT_MISSING")
    for spec in c["crypto"].values():
        require(type(spec) is dict and set(spec) == {"path", "sha256"} and
                type(spec["path"]) is str and Path(spec["path"]).is_absolute() and
                owner.hex64(spec["sha256"]), "SOLO_RUNTIME_CRYPTO_ENROLLMENT_MISSING")
    return c


def crypto_path(config, *, witness=False):
    spec = config["crypto"]["witness" if witness else "runtime"]
    p = Path(spec["path"])
    require(p.is_absolute() and p == p.resolve(strict=True), "PINNED_OPENSSL_PATH_INVALID")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_uid in {0, os.geteuid()} and
                not st.st_mode & 0o022 and st.st_mode & 0o111 and 0 < st.st_size <= 64 << 20,
                "PINNED_OPENSSL_UNSAFE")
        require(hashlib.file_digest(stream, "sha256").hexdigest() == spec["sha256"],
                "PINNED_OPENSSL_DRIFT")
        after = os.fstat(stream.fileno())
        require((st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns, st.st_ctime_ns) ==
                (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "PINNED_OPENSSL_CHANGED")
    return str(p)


def authenticate(config, enrollment, packet, *, now=None, witness=False):
    enrolled, q, _ = owner.authenticate_owner(enrollment, packet,
        pinned_enrollment_sha256=config["owner_enrollment_sha256"],
        pinned_owner_der_sha256=config["owner_der_sha256"],
        packet_schema=PACKET_SCHEMA, domain=DOMAIN, validate_request=validate_request, now=now,
        openssl_path=crypto_path(config, witness=witness))
    require(q["source_commit"] == config["source_commit"] and
            q["host_identity_sha256"] == config["host_identity_sha256"],
            "SOLO_RUNTIME_ENROLLED_SOURCE_HOST_MISMATCH")
    require(owner.utc(enrolled["valid_from"]) <= owner.utc(q["not_before"]) and
            owner.utc(q["expires_at"]) <= owner.utc(enrolled["valid_until"]),
            "OWNER_ENROLLMENT_MUST_COVER_ENTIRE_PHASE")
    return q


def consume_witness(config, enrollment_raw, packet_raw, *, nonce_root=WITNESS_NONCES,
                    now=None):
    """Actual forced-command operation. A timeout/partial response consumes forever."""
    q = authenticate(config, enrollment_raw, packet_raw, now=now, witness=True)
    identity = host_identity()
    require(identity == config["witness"]["host_identity_sha256"] and
            identity != q["host_identity_sha256"], "WITNESS_NOT_SEPARATE_HOST")
    record = nonces.reserve_once(nonce_root, q["nonce"], sha(packet_raw), q["phase"])
    # A signature that expired during fsync cannot return successful admission.
    validate_request(q, owner.datetime.now(owner.timezone.utc) if now is None else now)
    return {"schema": ACK_SCHEMA, "packet_sha256": sha(packet_raw),
            "request_sha256": sha(canonical(q)), "phase": q["phase"],
            "witness_host_identity_sha256": identity,
            "record_sha256": record["record_sha256"], "fresh_consumption_confirmed": True}


def consume_remote(config, packet_raw):
    """Pinned SSH transport, no caller-supplied command, shell or host-key fallback."""
    from settlement_financial_maintenance import private_read, run
    w = config["witness"]
    require(sha(private_read(w["known_hosts_path"])) == w["known_hosts_sha256"],
            "WITNESS_SSH_HOST_KEY_DRIFT")
    # Existing operator transport key only. Never create, print or copy its bytes.
    p = Path(w["identity_path"])
    st = p.lstat()
    require(p == p.resolve(strict=True) and stat.S_ISREG(st.st_mode) and
            st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1,
            "WITNESS_TRANSPORT_IDENTITY_UNSAFE")
    argv = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-oBatchMode=yes",
            "-oStrictHostKeyChecking=yes", "-oGlobalKnownHostsFile=/dev/null",
            "-oUserKnownHostsFile=" + w["known_hosts_path"], "-oIdentitiesOnly=yes",
            "-oConnectionAttempts=1", "-oConnectTimeout=5", "-oForwardAgent=no",
            "-oClearAllForwardings=yes", "-p", str(w["port"]), "-i", str(p),
            w["user"] + "@" + w["host"], REMOTE_COMMAND]
    try:
        raw = run(argv, input=packet_raw, timeout=10)
        require(len(raw) < 4096, "WITNESS_RESPONSE_TOO_LARGE")
        result = owner.parse(raw)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        raise owner.AuthorityHold("WITNESS_OUTCOME_UNCERTAIN_NONCE_MAY_BE_CONSUMED") from exc
    q = owner.parse(packet_raw)["request"]
    expected_record = {"schema": nonces.SCHEMA, "nonce": q["nonce"],
                       "signed_packet_sha256": sha(packet_raw), "phase": q["phase"]}
    require(set(result) == {"schema", "packet_sha256", "request_sha256", "phase",
                "witness_host_identity_sha256", "record_sha256", "fresh_consumption_confirmed"}
            and result["schema"] == ACK_SCHEMA and result["packet_sha256"] == sha(packet_raw)
            and result["request_sha256"] == sha(canonical(q)) and result["phase"] == q["phase"]
            and result["witness_host_identity_sha256"] == w["host_identity_sha256"]
            and result["record_sha256"] == sha(nonces.canonical(expected_record)) and
            result["fresh_consumption_confirmed"] is True,
            "WITNESS_CONSUMPTION_RESPONSE_INVALID")
    return result


def source_check(config):
    for name, expected in config["controller_files"].items():
        from settlement_financial_maintenance import private_read
        require(sha(private_read(Path(__file__).with_name(name), source=True)) == expected,
                "SOLO_RUNTIME_CONTROLLER_SOURCE_DRIFT")
    require(host_identity() == config["host_identity_sha256"], "SOLO_RUNTIME_HOST_DRIFT")


def authenticate_and_reserve(args):
    """Called under the ORIGINAL maintenance lease, before any service changes."""
    import settlement_financial_maintenance as m
    config_raw = m.private_read(CONFIG)
    config = load_config(config_raw)
    enrollment = m.private_read(ENROLLMENT)
    packet = m.private_read(args.packet)
    q = authenticate(config, enrollment, packet)
    require(q["phase"] == MODES[args.mode] and q["scope_sha256"] == m.scope_digest(),
            "SOLO_RUNTIME_PHASE_SCOPE_MISMATCH")
    source_check(config)
    procedure_raw = m.private_read(args.procedure)
    proc = owner.parse(procedure_raw)
    require(sha(procedure_raw) == q["procedure_sha256"] and set(proc) == PROCEDURE_KEYS
            and proc["schema"] == PROCEDURE_SCHEMA and proc["mode"] == args.mode
            and proc["fence_receipt_path"] == str(args.fence_receipt)
            and proc["output_path"] == str(args.output)
            and type(proc["runtime_binaries"]) is dict
            and set(proc["runtime_binaries"]) == set(RUNTIME_UNITS),
            "SOLO_RUNTIME_PROCEDURE_MISMATCH")
    require(args.output is not None and args.output.parent == m.BACKUPS,
            "SOLO_RUNTIME_BACKUP_LOCATION_INVALID")
    verify_runtime(proc["runtime_binaries"])
    # Complete explicit coverage, backed by real retained observation bytes.
    inventory = owner.parse(m.private_read(args.writer_inventory))
    require(sha(canonical(inventory)) == proc["writer_inventory_sha256"] and
            set(inventory) == {"schema", "writers"} and
            inventory["schema"] == "wolo.solo-maintenance-writer-evidence.v1" and
            type(inventory["writers"]) is dict and set(inventory["writers"]) == WRITERS,
            "SOLO_RUNTIME_WRITER_COVERAGE_INCOMPLETE")
    for category, item in inventory["writers"].items():
        require(type(item) is dict and set(item) == {"observation_path", "observation_sha256"}
                and owner.hex64(item["observation_sha256"])
                and sha(m.private_read(item["observation_path"])) == item["observation_sha256"],
                "SOLO_RUNTIME_WRITER_OBSERVATION_UNAVAILABLE")
    if args.mode == "solo-capture":
        import settlement_solo_resume as recovery
        require(proc["resume_plan"] is None, "SOLO_RUNTIME_UNEXPECTED_RESUME_PLAN")
        recovery.verify_capture(proc["capture_seal"], runner=m.run)
        permit, permit_sha = m.private_json(args.permit)
        artifacts = {"permit_sha256": permit_sha}
        m.validate_permit(permit)
        core = {k: v for k, v in permit.items()
                if k not in {"packet_sha256", "procedure_sha256", "approval_refs"}}
        require(permit["schema"] == m.SOLO_SCHEMA and
                sha(m.canonical(core)) == proc["permit_core_sha256"] and
                permit["packet_sha256"] == sha(packet) and
                permit["procedure_sha256"] == sha(procedure_raw) and
                permit["not_before"] == q["not_before"] and permit["expires_at"] == q["expires_at"],
                "SOLO_RUNTIME_PERMIT_NOT_SIGNED")
        approval = permit["approval_refs"]["owner"]
        signed = owner.parse(packet)
        require(approval["identity"] == signed["owner_key_id"] and
                approval["approval_sha256"] == sha(owner.base64.b64decode(
                    signed["signature_b64"], validate=True)), "SOLO_RUNTIME_OWNER_REFERENCE_MISMATCH")
        require(proc["previous_phase_receipt_path"] is None, "SOLO_RUNTIME_UNEXPECTED_LINEAGE")
    elif args.mode == "solo-contain":
        import settlement_solo_resume as recovery
        plan = recovery.read_sealed(proc["resume_plan"], "SIGNED_CONTAINMENT_PLAN_CHANGED")
        previous, previous_sha = m.private_json(args.previous_review)
        fenced, fence_sha = m.private_json(args.fence_receipt)
        permit, permit_sha = m.private_json(fenced["permit_path"])
        m._validate_permit_contract(permit)
        require(proc["capture_seal"] is None and proc["permit_core_sha256"] is None and
                proc["previous_phase_receipt_path"] == str(args.previous_review) and
                previous_sha == q["previous_phase_receipt_sha256"] and
                previous.get("state") == "RESUME_COMMITTED" and
                previous.get("source_commit") == q["source_commit"] and
                plan.get("schema") == recovery.CONTAIN_PLAN_SCHEMA and
                plan.get("source_commit") == q["source_commit"] and
                plan.get("fence_receipt_sha256") == fence_sha and
                plan.get("backup_manifest_sha256") == m.file_sha(args.output / "backup.json") and
                plan.get("prior_resume_commit") == {"path":str(args.previous_review),"sha256":previous_sha} and
                permit_sha == fenced.get("permit_sha256"), "SOLO_RUNTIME_CONTAINMENT_LINEAGE_MISMATCH")
        artifacts = {"fence_receipt_sha256": fence_sha,
                     "backup_manifest_sha256": plan["backup_manifest_sha256"]}
    else:
        fenced = m.verify_retained_fence(args.fence_receipt, m.scope_digest())
        permit = fenced["permit"]
        require(proc["capture_seal"] is None, "SOLO_RUNTIME_UNEXPECTED_CAPTURE_SEAL")
        require(proc["permit_core_sha256"] is None and
                proc["previous_phase_receipt_path"] == str(args.previous_review),
                "SOLO_RUNTIME_ARCHIVE_LINEAGE_MISMATCH")
        previous, previous_sha = m.private_json(args.previous_review)
        require(previous_sha == q["previous_phase_receipt_sha256"],
                "SOLO_RUNTIME_ARCHIVE_LINEAGE_MISMATCH")
        require(previous.get("schema") == "wolo.solo-maintenance-completion.v1" and
                previous.get("phase") == ("offline_verify" if args.mode == "solo-resume" else "live_capture") and
                previous.get("completed") is True and
                previous.get("source_commit") == q["source_commit"] and
                previous.get("scope_sha256") == q["scope_sha256"] and
                previous.get("fence_receipt_sha256") == m.file_sha(args.fence_receipt) and
                previous.get("backup_manifest_sha256") == m.file_sha(args.output / "backup.json"),
                "SOLO_RUNTIME_CAPTURE_NOT_SEALED")
        artifacts = {"fence_receipt_sha256": previous["fence_receipt_sha256"],
                     "backup_manifest_sha256": previous["backup_manifest_sha256"]}
        if args.mode == "solo-resume":
            import settlement_solo_resume as recovery
            plan = recovery.read_sealed(proc["resume_plan"], "SIGNED_RESUME_PLAN_CHANGED")
            require(plan.get("source_commit") == q["source_commit"] and
                    plan.get("fence_receipt_sha256") == artifacts["fence_receipt_sha256"] and
                    plan.get("backup_manifest_sha256") == artifacts["backup_manifest_sha256"] and
                    plan.get("restore_receipt_sha256") == previous.get("restore_receipt_sha256"),
                    "SOLO_RUNTIME_RESUME_LINEAGE_MISMATCH")
            m.verify_resume_state(args.fence_receipt, args.output, args.output / "restore.json",
                                  proc["resume_plan"], runner=m.run)
        else:
            require(proc["resume_plan"] is None, "SOLO_RUNTIME_UNEXPECTED_RESUME_PLAN")
    # Remote FIRST. A crash before local reservation cannot replay on the VPS.
    # A lost response is never automatically retried or treated as permission.
    ack = consume_remote(config, packet)
    nonces.reserve_once(NONCE_ROOT, q["nonce"], sha(packet), q["phase"])
    validate_request(q, owner.datetime.now(owner.timezone.utc))
    source_check(config)
    verify_runtime(proc["runtime_binaries"])
    if args.mode == "solo-capture":
        recovery.verify_capture(proc["capture_seal"], runner=m.run)
    require(m.private_read(CONFIG) == config_raw and m.private_read(ENROLLMENT) == enrollment,
            "SOLO_RUNTIME_ENROLLMENT_CHANGED")
    validate_request(q, owner.datetime.now(owner.timezone.utc))
    def revalidate():
        # A long restore/census and even a slow start must not retain revoked
        # source, enrollment, binary, or phase authority across side effects.
        validate_request(q, m.clock())
        source_check(config)
        verify_runtime(proc["runtime_binaries"])
        require(m.private_read(CONFIG) == config_raw and m.private_read(ENROLLMENT) == enrollment,
                "SOLO_RUNTIME_ENROLLMENT_CHANGED")
        validate_request(q, m.clock())
    return dict(q, live_actions_allowed=args.mode == "solo-capture",
                resume_actions_allowed=args.mode == "solo-resume",
                contain_actions_allowed=args.mode == "solo-contain",
                resume_recovery_allowed=args.mode == "solo-resume" and plan.get("contained_partial") is not None,
                resume_sealed=proc["resume_plan"], capture_seal=proc["capture_seal"],
                _admission_guard=revalidate,
                max_total_bytes=permit["max_total_bytes"], witness_receipt=ack,
                artifacts=artifacts)


def verify_runtime(expected):
    """Read actual running executables; never infer parity from a checkout."""
    import settlement_financial_maintenance as m
    for unit in RUNTIME_UNITS:
        require(owner.hex64(expected[unit]), "SOLO_RUNTIME_BINARY_PIN_INVALID")
        pid = m.run(["systemctl", "show", "--value", "--property=MainPID", "--", unit]).strip()
        require(re.fullmatch(r"[1-9][0-9]*", pid) is not None, "SOLO_RUNTIME_PROCESS_UNAVAILABLE")
        with open("/proc/" + pid + "/exe", "rb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode) and
                    0 < os.fstat(stream.fileno()).st_size <= 256 << 20,
                    "SOLO_RUNTIME_BINARY_UNAVAILABLE")
            h = hashlib.file_digest(stream, "sha256").hexdigest()
        require(h == expected[unit], "SOLO_RUNTIME_EXECUTABLE_DRIFT")
        require(m.run(["systemctl", "show", "--value", "--property=MainPID", "--", unit]).strip() == pid,
                "SOLO_RUNTIME_PROCESS_CHANGED")


def prepare(config, enrollment_raw, procedure_raw, mode, *, ttl_seconds=1200,
            previous_receipt_raw=None, now=None):
    """Issue an unsigned exact-artifact challenge; never consumes authority."""
    require(mode in MODES and type(ttl_seconds) is int and
            0 < ttl_seconds <= WINDOWS[MODES[mode]], "SOLO_RUNTIME_CHALLENGE_WINDOW_INVALID")
    import settlement_financial_maintenance as m
    enrollment = owner.parse(enrollment_raw)
    require(sha(enrollment_raw) == config["owner_enrollment_sha256"],
            "EXTERNAL_ENROLLMENT_PIN_MISMATCH")
    proc = owner.parse(procedure_raw)
    require(set(proc) == PROCEDURE_KEYS and proc["schema"] == PROCEDURE_SCHEMA and
            proc["mode"] == mode, "SOLO_RUNTIME_PROCEDURE_MISMATCH")
    at = (owner.datetime.now(owner.timezone.utc) if now is None else now).replace(microsecond=0)
    q = {"schema": SCHEMA, "chain_id": "wolo-1", "phase": MODES[mode], "operation": OPS[MODES[mode]],
         "source_commit": config["source_commit"], "host_identity_sha256": config["host_identity_sha256"],
         "scope_sha256": m.scope_digest(), "procedure_sha256": sha(procedure_raw),
         "nonce": secrets.token_hex(16), "not_before": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "expires_at": (at + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "previous_phase_receipt_sha256": sha(previous_receipt_raw) if previous_receipt_raw is not None else None}
    validate_request(q, at)
    message = DOMAIN + canonical({"owner_key_id": enrollment["owner_key_id"], "request": q})
    return {"status": "UNSIGNED_NONAUTHORIZING", "packet_schema": PACKET_SCHEMA,
            "owner_key_id": enrollment["owner_key_id"], "request": q,
            "signing_message_b64": owner.base64.b64encode(message).decode(),
            "procedure": proc, "financial_release_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--witness-stdin", action="store_true")
    action.add_argument("--prepare", action="store_true")
    parser.add_argument("--mode", choices=tuple(MODES))
    parser.add_argument("--procedure", type=Path)
    parser.add_argument("--previous-receipt", type=Path)
    parser.add_argument("--ttl-seconds", type=int, default=1200)
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            import settlement_financial_maintenance as m
            require(os.geteuid() == 0 and args.mode is not None and args.procedure is not None,
                    "ROOT_AND_EXACT_PROCEDURE_REQUIRED")
            config = load_config(m.private_read(CONFIG))
            source_check(config)
            result = prepare(config, m.private_read(ENROLLMENT), m.private_read(args.procedure), args.mode,
                ttl_seconds=args.ttl_seconds,
                previous_receipt_raw=m.private_read(args.previous_receipt) if args.previous_receipt else None)
            sys.stdout.buffer.write(canonical(result) + b"\n")
            return 3
        config_raw, enrollment_raw = private_file(WITNESS_CONFIG), private_file(WITNESS_ENROLLMENT)
        config = load_config(config_raw)
        raw = sys.stdin.buffer.read(131072)
        require(0 < len(raw) < 131072, "WITNESS_INPUT_LIMIT")
        result = consume_witness(config, enrollment_raw, raw)
        require(private_file(WITNESS_CONFIG) == config_raw and
                private_file(WITNESS_ENROLLMENT) == enrollment_raw, "WITNESS_ENROLLMENT_CHANGED")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        # No packet, raw exception, key, path or original SSH command in logs.
        print('{"status":"HOLD_AUTHORITY_UNAVAILABLE"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
