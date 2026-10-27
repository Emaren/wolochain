#!/usr/bin/env python3
"""Identity-bound maintenance recovery. Never restores SQL or retries payments.

Only the original lease holder may call execute, after a fresh owner signature
and off-host nonce admission. Evidence readers do not grant that authority.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

import settlement_financial_maintenance as m
import settlement_resume_producer_identities as identities

CAPTURE_SCHEMA = "wolo.maintenance-resume-capture.v1"
PLAN_SCHEMA = "wolo.maintenance-resume-plan.v1"
SOURCE_SCHEMA = "wolo.maintenance-producer-source.v1"
TIMER_SCHEMA = "wolo.maintenance-timer-qualification.v1"
FENCE_SCHEMA = "wolo.financial-maintenance-fence.v2"
JOURNAL = "RESUME_COMMITTED.json"


def read_sealed(spec, reason):
    m.require(type(spec) is dict and set(spec) == {"path", "sha256"} and
              type(spec["path"]) is str and type(spec["sha256"]) is str and
              m.SHA.fullmatch(spec["sha256"]), reason)
    value, actual = m.private_json(spec["path"])
    m.require(actual == spec["sha256"], reason)
    return value


def source_file_sha(path, uid):
    """Require a root-controlled build; service peers cannot substitute bytes.

    Hashing app-writable files only proves a past observation. Actual ExecStart
    and every parent must be protected against that runtime uid after hashing.
    Existing mutable app checkouts therefore require separate provisioning.
    """
    m.require(uid == 0, "RESUME_PRODUCER_SOURCE_MUST_BE_ROOT_CONTROLLED")
    p = Path(path)
    m.require(p.is_absolute() and p == p.resolve(strict=True), "PRODUCER_SOURCE_PATH_UNSAFE")
    for parent in p.parents:
        info = parent.lstat()
        m.require(stat.S_ISDIR(info.st_mode) and info.st_uid in {0, uid} and
                  not info.st_mode & 0o022, "PRODUCER_SOURCE_PARENT_UNSAFE")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        m.require(stat.S_ISREG(before.st_mode) and before.st_uid in {0, uid} and
                  before.st_nlink == 1 and not before.st_mode & 0o022 and
                  0 < before.st_size <= 256 << 20, "PRODUCER_SOURCE_FILE_UNSAFE")
        h = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        fields = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        m.require(fields(before) == fields(after) == fields(p.lstat()),
                  "PRODUCER_SOURCE_CHANGED_DURING_READ")
    return h, before.st_size


def verify_sources(specs, runner):
    m.require(type(specs) is dict and set(specs) == set(m.APPS + m.ONESHOTS),
              "PRODUCER_SOURCE_COVERAGE_MISSING")
    total = 0
    for unit, spec in specs.items():
        manifest = read_sealed(spec, "SIGNED_PRODUCER_MANIFEST_CHANGED")
        m.require(type(manifest) is dict and set(manifest) ==
                  {"schema", "unit", "source_commit", "uid", "files"} and
                  manifest["schema"] == SOURCE_SCHEMA and manifest["unit"] == unit and
                  type(manifest["source_commit"]) is str and
                  len(manifest["source_commit"]) == 40 and
                  all(c in "0123456789abcdef" for c in manifest["source_commit"]) and
                  manifest["source_commit"] != "0" * 40 and
                  type(manifest["uid"]) is int and manifest["uid"] >= 0 and
                  type(manifest["files"]) is list and 2 <= len(manifest["files"]) <= 50000,
                  "PRODUCER_SOURCE_MANIFEST_INVALID")
        paths, kinds, entrypoints = set(), set(), set()
        for item in manifest["files"]:
            m.require(type(item) is dict and set(item) == {"path", "sha256", "kind"} and
                      type(item["path"]) is str and item["path"] not in paths and
                      type(item["sha256"]) is str and m.SHA.fullmatch(item["sha256"]) and
                      item["kind"] in {"executable", "entrypoint", "build_metadata", "code"},
                      "PRODUCER_SOURCE_MANIFEST_INVALID")
            paths.add(item["path"])
            kinds.add(item["kind"])
            if item["kind"] == "entrypoint":
                entrypoints.add(item["path"])
            actual, size = source_file_sha(item["path"], manifest["uid"])
            total += size
            m.require(total <= 8 << 30, "PRODUCER_SOURCE_HASH_BUDGET_EXCEEDED")
            m.require(actual == item["sha256"], "PRODUCER_BUILD_OR_ENTRYPOINT_DRIFT")
        # A node/python/bash interpreter hash alone does not identify its app.
        m.require({"entrypoint", "build_metadata"}.issubset(kinds),
                  "PRODUCER_BUILD_AND_ENTRYPOINT_REQUIRED")
        fields = identities.read_properties(unit, runner)
        native = identities.native_execution_configuration(unit, fields, runner)
        commands = [row for rows in native.values() for row in rows]
        m.require(commands and all(row[0] in paths and
                  entrypoints.intersection([row[0]] + row[1]) for row in commands),
                  "PRODUCER_ENTRYPOINT_NOT_BOUND_TO_NATIVE_ARGV")
        for executable, argv, _ in commands:
            name = Path(executable).name
            interpreter = name in {"node", "nodejs", "bash", "dash", "sh", "zsh", "ksh",
                                   "ruby", "perl", "php"} or name.startswith(("python", "pypy"))
            # Never guess the source of an inline shell, -m, eval, env/PATH or
            # preload command. A reviewed absolute wrapper is required instead.
            m.require(name not in {"env", "npm", "npx", "yarn", "pnpm", "bun", "deno"} and
                      argv[0] == executable and
                      (not interpreter or (len(argv) >= 2 and argv[1] in entrypoints and argv[1].startswith("/"))) and
                      not any(a in {"-c", "-lc", "-xc", "-e", "--eval", "-m"} or
                              a.startswith(("--require=", "--import=", "--eval=")) for a in argv[1:]) and
                      all(a in paths for a in argv[1:] if a.startswith("/")),
                      "PRODUCER_INTERPRETER_INPUT_NOT_SEALED")


def verify_capture(spec, *, runner, gated=False):
    capture = read_sealed(spec, "SIGNED_CAPTURE_IDENTITIES_CHANGED")
    m.require(type(capture) is dict and set(capture) ==
              {"schema", "producer_identities", "producer_sources"} and
              capture["schema"] == CAPTURE_SCHEMA, "RESUME_CAPTURE_IDENTITIES_MISSING")
    observed = identities.verify_producer_identities(capture["producer_identities"],
                      runner=runner, allow_owned_gate=gated)
    verify_sources(capture["producer_sources"], runner)
    if not gated:
        # Before HOLD the signed original active state must match, too.
        fresh = identities.collect_producer_identities(runner=runner)
        m.require(fresh == capture["producer_identities"], "SIGNED_CAPTURE_PRESTATE_CHANGED")
    return capture, observed


def phase_current(phase):
    m.require(type(phase) is dict and phase.get("phase") == "resume_existing" and
              phase.get("resume_actions_allowed") is True, "RESUME_PHASE_ONLY")
    m.require(callable(phase.get("_admission_guard")), "RESUME_AUTHENTIC_ADMISSION_REQUIRED")
    phase["_admission_guard"]()
    from settlement_solo_runtime import validate_request, REQUEST_KEYS
    validate_request({k: phase[k] for k in REQUEST_KEYS}, m.clock())


def verify_timers(plan, capture, active_timers):
    """No generic 'certified' boolean. Review binds exact code/config/test bytes.

    These are owner-reviewed source qualification receipts, NOT financial or
    chain attestations. Missing qualification holds the whole resume operation.
    """
    specs = plan["timer_qualifications"]
    m.require(type(specs) is dict and set(specs) == set(active_timers),
              "PERSISTENT_TIMER_CATCHUP_NOT_QUALIFIED")
    for timer, spec in specs.items():
        value = read_sealed(spec, "TIMER_QUALIFICATION_CHANGED")
        service = timer[:-6] + ".service"
        m.require(type(value) is dict and set(value) == {"schema", "timer", "service",
                  "timer_configuration_sha256", "service_configuration_sha256",
                  "producer_source_manifest_sha256", "idempotence_test", "uncertainty_test"} and
                  value["schema"] == TIMER_SCHEMA and value["timer"] == timer and
                  value["service"] == service and
                  value["timer_configuration_sha256"] == capture["producer_identities"]["units"][timer]["configuration_sha256"] and
                  value["service_configuration_sha256"] == capture["producer_identities"]["units"][service]["configuration_sha256"] and
                  value["producer_source_manifest_sha256"] == capture["producer_sources"][service]["sha256"],
                  "PERSISTENT_TIMER_CATCHUP_NOT_QUALIFIED")
        # Retain actual reviewed CI receipts; a path/hash must read at point of
        # use, never an environment variable or a self-declared pass value.
        for key in ("idempotence_test", "uncertainty_test"):
            receipt = read_sealed(value[key], "TIMER_TEST_EVIDENCE_UNAVAILABLE")
            m.require(type(receipt) is dict and receipt.get("source_manifest_sha256") ==
                      value["producer_source_manifest_sha256"] and
                      receipt.get("test_contract") == key and receipt.get("result") == "PASS" and
                      type(receipt.get("ci_run_url")) is str and
                      receipt["ci_run_url"].startswith("https://github.com/Emaren/"),
                      "TIMER_TEST_EVIDENCE_UNAVAILABLE")


def verify_state(fence_path, backup_dir, restore_path, sealed, *, runner):
    fence, fence_sha = m.private_json(fence_path)
    m.require(fence.get("schema") == FENCE_SCHEMA and type(fence.get("capture_seal")) is dict,
              "RESUME_CAPTURE_IDENTITIES_MISSING")
    plan = read_sealed(sealed, "SIGNED_RESUME_PLAN_CHANGED")
    m.require(set(plan) == {"schema", "source_commit", "fence_receipt_sha256",
              "backup_manifest_sha256", "restore_receipt_sha256", "timer_qualifications"} and
              plan["schema"] == PLAN_SCHEMA and fence_sha == plan["fence_receipt_sha256"],
              "SIGNED_RESUME_PLAN_MISMATCH")
    backup_dir, restore_path = Path(backup_dir), Path(restore_path)
    m.require(restore_path == backup_dir / "restore.json", "RESUME_RESTORE_PATH_MISMATCH")
    retained = m.verify_retained_fence(fence_path, m.scope_digest(), runner=runner,
                           expected_receipt_sha256=plan["fence_receipt_sha256"])
    verified = m.verify_current_backup(restore_path, m.scope_digest(), fence_sha)
    m.require(verified["restore_receipt_sha256"] == plan["restore_receipt_sha256"] and
              verified["backup_manifest_sha256"] == plan["backup_manifest_sha256"],
              "SIGNED_RESTORE_OR_BACKUP_CHANGED")
    manifest, manifest_sha = m.private_json(backup_dir / "backup.json")
    m.require(manifest_sha == plan["backup_manifest_sha256"], "SIGNED_MANIFEST_CHANGED_AT_USE")
    capture, identities_now = verify_capture(fence["capture_seal"], runner=runner, gated=True)
    for unit in m.UNITS:
        m.require((fence["prestate"][unit]["ActiveState"] == "active") ==
                  capture["producer_identities"]["units"][unit]["originally_active"],
                  "FENCE_PRESTATE_IDENTITY_MISMATCH")
    verify_timers(plan, capture, identities_now["originally_active_timers"])
    permit = retained["permit"]
    for lane in ("hd", "de"):
        contract = permit["databases"][lane]
        m.require(m.financial_census(contract, m.pg_environment(contract), runner) ==
                  manifest["financial_censuses"][lane], "FINANCIAL_DATABASE_CHANGED_BEFORE_RESUME")
    m.settlement_states_unchanged(Path(manifest["settlement_snapshot"]), permit["max_total_bytes"])
    m.no_jobs(runner)
    # Long census/build reads cannot hide a concurrent authority replacement.
    for path, expected in ((fence_path, fence_sha), (backup_dir / "backup.json", manifest_sha),
                           (restore_path, verified["restore_receipt_sha256"])):
        _, actual = m.private_json(path)
        m.require(actual == expected, "RESUME_EVIDENCE_CHANGED_DURING_VERIFICATION")
    m.require(read_sealed(sealed, "SIGNED_RESUME_PLAN_CHANGED") == plan,
              "SIGNED_RESUME_PLAN_CHANGED")
    verify_capture(fence["capture_seal"], runner=runner, gated=True)
    return dict(identities_now, fence=fence, plan=plan, resume_authorized=False,
                financial_release_authorized=False)


def unlink_owned_hold(expected):
    # Parent is a protected root-only directory. Recheck the exact bytes and
    # inode immediately before unlink, then fsync the directory.
    before = m.HOLD.lstat()
    m.require(m.digest(m.private_read(m.HOLD)) == expected, "OWNED_HOLD_CHANGED_BEFORE_RESUME")
    after = m.HOLD.lstat()
    m.require((before.st_dev, before.st_ino, before.st_ctime_ns) ==
              (after.st_dev, after.st_ino, after.st_ctime_ns), "OWNED_HOLD_CHANGED_BEFORE_RESUME")
    m.HOLD.unlink()
    fd = os.open(m.HOLD.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def execute(fence_path, backup_dir, *, phase_window, runner=None):
    phase_current(phase_window)  # Refuse before any systemd/file changes.
    m.require(os.geteuid() == 0, "ROOT_REQUIRED")
    containment_runner = runner or m.run
    runner = m.bounded_runner(containment_runner, phase_window)
    path = Path(backup_dir) / JOURNAL
    m.require(not path.exists() and not path.is_symlink(),
              "RESUME_ALREADY_COMMITTED_FRESH_RECOVERY_AUTHORITY_REQUIRED")
    sealed = phase_window["resume_sealed"]
    observed = verify_state(fence_path, backup_dir, Path(backup_dir) / "restore.json", sealed, runner=runner)
    m.require(observed["plan"]["source_commit"] == phase_window["source_commit"],
              "RESUME_SOURCE_MISMATCH")
    phase_current(phase_window)  # Census/build I/O must not outlive authority.
    # Irreversible admission boundary: never auto-replay after this durable
    # marker, even if killed immediately before the HOLD unlink.
    journal = {"schema": "wolo.maintenance-resume-commit.v1", "state": "RESUME_COMMITTED",
               "source_commit": phase_window["source_commit"],
               "plan_sha256": sealed["sha256"], "nonce": phase_window["nonce"],
               "original_hold_sha256": observed["fence"]["hold_sha256"],
               "apps": observed["originally_active_apps"], "timers": observed["originally_active_timers"],
               "financial_release_authorized": False}
    m.write_new(path, m.canonical(journal))
    phase_current(phase_window)
    try:
        unlink_owned_hold(observed["fence"]["hold_sha256"])
        for unit in observed["originally_active_apps"] + observed["originally_active_timers"]:
            phase_current(phase_window)
            runner(["systemctl", "start", "--", unit])
            m.require(m.show(unit, runner)["ActiveState"] == "active", "RESUMED_UNIT_NOT_ACTIVE")
        m.no_jobs(runner)
        phase_current(phase_window)
        m.write_new(Path(backup_dir) / "RESUME_COMPLETED.json", m.canonical(dict(journal, state="RESUME_COMPLETED")))
    except Exception:
        # SIGKILL cannot run cleanup. The durable COMMITTED marker is an
        # explicit partial-return state, never a promise of automatic re-fence.
        failures = []
        try:
            if not m.HOLD.exists() and not m.HOLD.is_symlink():
                m.write_new(m.HOLD, m.canonical({"scope_sha256": m.scope_digest(),
                                               "permit_sha256": observed["fence"]["permit_sha256"]}))
            m.require(m.digest(m.private_read(m.HOLD)) == observed["fence"]["hold_sha256"],
                      "PARTIAL_RESUME_HOLD_REASSERTION_UNCERTAIN")
        except (OSError, RuntimeError):
            failures.append("hold")
        # Containment has its own bounded budget after the authority expires;
        # it can only STOP the exact original scope, never admit new work.
        for unit in m.TIMERS + m.ONESHOTS + m.APPS:
            try:
                containment_runner(["systemctl", "stop", "--", unit], timeout=5)
            except (OSError, RuntimeError):
                failures.append(unit)
        try:
            m.inactive_observation(containment_runner)
        except (OSError, RuntimeError):
            failures.append("inactive_scope")
        m.require(not failures, "PARTIAL_RESUME_CONTAINMENT_UNCERTAIN")
        raise m.MaintenanceError("PARTIAL_RESUME_FENCED_FRESH_RECOVERY_AUTHORITY_REQUIRED") from None
    return {"status": "ORIGINAL_PRODUCERS_RESUMED", "financial_release_authorized": False,
            "custody_or_solvency_certified": False}
