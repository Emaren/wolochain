"""C06 durable orchestration kernel; no live host driver or permit issuer.

The native integration must authenticate every phase using the existing owner
trust anchor and independent witness, bind the complete exact plan and hold the
shared Factory lease. This module cannot establish those facts on its own.
No production service commands, credentials or authority enrollment are here.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from settlement_c06_checkpoint_rehearsal import Hold, canonical, digest, hash64, require

STEPS = (
    "ADMITTED", "FENCE_INTENT", "FENCED", "CHECKPOINT_INTENT", "CHECKPOINT",
    "CAPTURE_INTENT", "CAPTURED", "RECEIVER_VERIFIED",
    "RESTORE_ADMITTED", "RESTORED", "RESUME_ADMITTED",
    "RESTART_INTENT", "RESTORED_SERVICES", "COMPLETE",
)
# Intent without matching observation is ambiguous; never automatically replay.
INTENTS = frozenset({"FENCE_INTENT", "CHECKPOINT_INTENT", "CAPTURE_INTENT",
                     "RESTART_INTENT"})
MAX_RECORD = 65536

def _private(st, mode, kind):
    return (kind(st.st_mode) and st.st_uid == os.geteuid()
            and stat.S_IMODE(st.st_mode) == mode)

class Journal:
    """Append-only, exclusive, fsync'd phase evidence. Existing run is HOLD.

    Local durability cannot attest rollback resistance: native external witness
    must anchor each intent before its associated operation.
    """
    def __init__(self, path, plan_sha):
        require(hash64(plan_sha), "PLAN_SHA")
        self.path = Path(path)
        self.plan_sha = plan_sha
        require(self.path.is_absolute() and self.path.resolve() == self.path,
                "JOURNAL_CANONICAL_PATH")
        self.fd = self.lock = None
        self.records = []

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(_private(os.fstat(self.fd), 0o700, stat.S_ISDIR),
                    "JOURNAL_PRIVATE")
            self.lock = os.open(".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                                0o600, dir_fd=self.fd)
            st = os.fstat(self.lock)
            require(_private(st, 0o600, stat.S_ISREG) and st.st_nlink == 1,
                    "JOURNAL_LOCK_PRIVATE")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.records = self.read()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        for name in ("lock", "fd"):
            val = getattr(self, name)
            if val is not None:
                os.close(val)
                setattr(self, name, None)

    @property
    def tip(self):
        return digest(canonical(self.records[-1])) if self.records else None

    def read(self):
        files = sorted(set(os.listdir(self.fd)) - {".lock"})
        require(len(files) <= len(STEPS), "JOURNAL_LENGTH")
        records = []
        for n, name in enumerate(files):
            require(name == f"{n:02d}.json", "JOURNAL_GAP_OR_FOREIGN_FILE")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.fd)
            with os.fdopen(fd, "rb") as stream:
                st = os.fstat(stream.fileno())
                require(_private(st, 0o600, stat.S_ISREG) and st.st_nlink == 1
                        and 0 < st.st_size <= MAX_RECORD, "JOURNAL_RECORD_PRIVATE")
                raw = stream.read(MAX_RECORD + 1)
            try:
                r = json.loads(raw)
            except ValueError as e:
                raise Hold("JOURNAL_CORRUPT") from e
            require(type(r) is dict and set(r) == {"schema", "index", "step",
                "plan", "previous", "evidence"} and canonical(r) == raw and
                r["schema"] == "wolo.c06.checkpoint-journal.v1" and
                type(r["index"]) is int and r["index"] == n and
                r["step"] == STEPS[n] and r["plan"] == self.plan_sha and
                r["previous"] == (digest(canonical(records[-1])) if records else None)
                and hash64(r["evidence"]), "JOURNAL_BINDING")
            records.append(r)
        return records

    def append(self, step, evidence):
        n = len(self.records)
        require(n < len(STEPS) and STEPS[n] == step and hash64(evidence),
                "PHASE_ORDER_OR_EVIDENCE")
        r = {"schema":"wolo.c06.checkpoint-journal.v1","index":n,"step":step,
             "plan":self.plan_sha,"previous":self.tip,"evidence":evidence}
        raw = canonical(r)
        fd = os.open(f"{n:02d}.json", os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                     os.O_WRONLY, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self.fd)
        self.records.append(r)
        require(self.read() == self.records, "JOURNAL_READBACK")
        return self.tip

def validate_plan(plan):
    require(type(plan) is dict and set(plan) == {
        "schema","source","host","boot","scope","producer_prestate",
        "shared_database_scope","b_prepare","we2_window","archive_budget",
        "quarantine","restart_plan","abort_plan","recovery_target"} and
        plan["schema"] == "wolo.c06.coordinated-plan.v1", "PLAN_SCHEMA")
    require(all(hash64(v) for k,v in plan.items() if k != "schema"),
            "PLAN_EXACT_BINDINGS")
    return digest(canonical(plan))

def validate_receipt(receipt, phase, plan_sha, previous):
    """Only shape/binding, not signature verification. Native provider mandatory."""
    require(type(receipt) is dict and set(receipt) == {
        "phase","plan","previous","packet","witness","nonce","expires"} and
        receipt["phase"] == phase and receipt["plan"] == plan_sha and
        receipt["previous"] == previous and
        all(hash64(receipt[k]) for k in ("packet","witness","nonce")) and
        type(receipt["expires"]) is int and receipt["expires"] > int(time.time()),
        "PHASE_ADMISSION_BINDING")
    return digest(canonical(receipt))

class Coordinator:
    """Orchestrate a reviewed host driver, not arbitrary shell commands.

    Driver callbacks must use exact authenticated receipts, check the lease
    at every mutation, and implement fail-closed producer/start prevention.
    No live driver ships in this increment. A fixture cannot authorize live work.
    """
    def __init__(self, plan, journal, driver):
        self.plan = plan
        self.sha = validate_plan(plan)
        require(journal.plan_sha == self.sha, "JOURNAL_PLAN_DRIFT")
        self.j = journal
        self.d = driver
        self.seen = set()

    def record(self, step, evidence):
        tip = self.j.append(step, evidence)
        # Native witness must durably anchor the exact journal tip; losing the
        # acknowledgement leaves a HOLD, never a replay or automatic restart.
        self.d.anchor(self.sha, step, tip)
        return tip

    def admit(self, phase):
        self.d.verify_lease(self.plan)
        previous = self.j.tip
        r = self.d.authenticate_and_consume(phase, self.plan, previous)
        h = validate_receipt(r, phase, self.sha, previous)
        require(r["nonce"] not in self.seen, "PHASE_NONCE_REPLAY")
        self.seen.add(r["nonce"])
        return h

    def run(self):
        require(not self.j.records, "EXISTING_RUN_MANUAL_RECONCILIATION")
        # Deliberately fixture-only until the separately reviewed native host
        # driver and exact expanded snapshot phase have genuine enrollment.
        require(self.d.is_disposable_fixture is True, "NATIVE_DRIVER_NOT_ADMITTED")
        self.record("ADMITTED", self.admit("capture"))
        self.record("FENCE_INTENT", self.plan["producer_prestate"])
        self.d.verify_lease(self.plan)
        fence = self.d.fence_and_deny_reconnect(self.plan)
        self.record("FENCED", fence)
        self.record("CHECKPOINT_INTENT", fence)
        self.d.verify_lease(self.plan)
        checkpoint = self.d.checkpoint(self.plan)
        self.record("CHECKPOINT", checkpoint)
        self.record("CAPTURE_INTENT", checkpoint)
        self.d.verify_lease(self.plan)
        cipher = self.d.capture_encrypted(self.plan, checkpoint)
        require(hash64(cipher), "CIPHERTEXT_DIGEST")
        self.record("CAPTURED", cipher)
        require(self.d.verify_frozen(self.plan, checkpoint) is True,
                "CHECKPOINT_DRIFT")
        require(self.d.verify_receiver(cipher) == cipher, "RECEIVER_DIGEST")
        self.record("RECEIVER_VERIFIED", cipher)
        self.record("RESTORE_ADMITTED", self.admit("restore"))
        require(self.d.restore_isolated(cipher) == cipher, "RESTORE_DIGEST")
        self.record("RESTORED", cipher)
        self.record("RESUME_ADMITTED", self.admit("resume"))
        require(self.d.verify_frozen(self.plan, checkpoint) is True,
                "CHECKPOINT_DRIFT")
        self.record("RESTART_INTENT", self.plan["restart_plan"])
        self.d.verify_lease(self.plan)
        post = self.d.restore_original_nonfinancial_services(self.plan)
        self.record("RESTORED_SERVICES", post)
        require(self.d.verify_quarantine_and_poststate(self.plan) is True,
                "POSTSTATE_OR_QUARANTINE")
        self.record("COMPLETE", post)
        return cipher

def recovery_disposition(journal):
    """Read-only crash classification. Never invokes a host action."""
    if not journal.records:
        return "NO_PHASE_RECORDED"
    last = journal.records[-1]["step"]
    if last == "COMPLETE":
        return "COMPLETE_REVERIFY_EXTERNAL_ANCHOR"
    if last in INTENTS:
        return "AMBIGUOUS_EFFECT_FRESH_CONTAINMENT_AUTHORITY_REQUIRED"
    return "HOLD_FRESH_RECONCILIATION_AND_AUTHORITY_REQUIRED"
