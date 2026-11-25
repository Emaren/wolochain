#!/usr/bin/env python3
"""C08 Intel witness transport: source-pinned, reversible SSH key admission.

SUPERSEDED normal-macOS-SSH witness enrollment. The correct C08 witness has
its own Intel loopback-only SSHD on port 22996 and distinct host identity.
This controller's old --mode apply path is permanently disabled; it must never
append a witness key to normal ~/.ssh/authorized_keys or modify C06's receiver.
The strictly compared --mode revert path survives solely to recover a prior
exactly matching historical mistake. --mode plan is read-only, not authority.
Never consumes witness nonce, signs, starts services or authorizes WOLO.
Successful plans and exact recovery return 3/HOLD; errors return 2/STOP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA = "wolo.c08.intel-offhost-witness-ssh-key-nonauthorizing.v1"
EXPECTED_CONFIG_SHA = "5fae8033a2c3d5e38e5e0a59369c9567d9c71caa09b8b92e5ad20add29b45299"
EXPECTED_SCRIPT_SHA = "b8cd22ab3df7a4b3385bd5ed0c9886638f737adf538e236875df3b807d1404fb"
EXPECTED_OLD_KEYS_SHA = "b8773230ef71735030d2c9a362c4f2cfc517922af3f51b0cdc871554fe3128e9"
EXPECTED_PUB_BLOB_SHA = "ce07e3593fc557cafbbeabe05f1a7c6a1200c01984595a75a726b8f414180fe6"
EXPECTED_CONFIG_SOURCE = "b35f294d619e6bf5d07b337cea46095f2eea9f76"
INTERPRETER = "/usr/local/bin/python3.13"
MODELS = frozenset({"plan", "apply", "revert"})
PUB_PATTERN = re.compile(r"ssh-ed25519 ([A-Za-z0-9+/]+={0,2})(?:\s+[A-Za-z0-9._@-]+)?\s*\Z")
MAX_BYTES = 131072


class HoldError(ValueError):
    pass


def require(ok: bool, code: str):
    if not ok:
        raise HoldError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def secure_read(path: Path, *, mode: int = 0o600) -> bytes:
    require(path.is_absolute() and ".." not in path.parts and not path.is_symlink(),
            "C08_PRIVATE_PATH_NOT_CANONICAL")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES
                    and stat.S_IMODE(before.st_mode) == mode and before.st_uid == os.geteuid()
                    and before.st_nlink == 1, "C08_PRIVATE_FILE_MODE_OWNER_OR_TYPE")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                part = os.read(fd, min(65536, MAX_BYTES + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size",
                      "st_ctime_ns", "st_mtime_ns", "st_nlink")
            require(len(raw) == before.st_size and all(
                getattr(before, k) == getattr(after, k) for k in fields),
                "C08_PRIVATE_FILE_CHANGED_WHILE_READING")
            return bytes(raw)
        finally:
            os.close(fd)
    except OSError:
        raise HoldError("C08_PRIVATE_FILE_UNAVAILABLE") from None


def private_directory(path: Path):
    require(path.is_dir() and not path.is_symlink()
            and path.lstat().st_uid == os.geteuid()
            and stat.S_IMODE(path.lstat().st_mode) == 0o700,
            "C08_PRIVATE_DIRECTORY_UNSAFE")


def public_key_blob(raw: bytes) -> str:
    try:
        text = raw.decode("ascii").strip()
    except UnicodeError:
        raise HoldError("C08_TRANSPORT_PUBKEY_INVALID") from None
    m = PUB_PATTERN.fullmatch(text)
    require(m is not None and sha(m.group(1).encode("ascii")) == EXPECTED_PUB_BLOB_SHA,
            "C08_TRANSPORT_PUBKEY_PIN_MISMATCH")
    return m.group(1)


def key_line(home: Path, blob: str) -> bytes:
    require(re.fullmatch(r"/Users/[a-zA-Z0-9._-]+", str(home)) is not None,
            "C08_INTEL_HOME_PATH_UNSAFE")
    runtime = home / ".wolo-owner-authority/witness-runtime/source/settlement_solo_runtime.py"
    cmd = f"{INTERPRETER} -B {runtime} --witness-stdin"
    # No local-shell expansion, writable environment variable, forwarding,
    # PTY, agent or remote caller-selected command is permitted by this key.
    return (f'restrict,from="127.0.0.1,::1",command="{cmd}" '
            f"ssh-ed25519 {blob}\n").encode("ascii")


def classify_keys(raw: bytes, blob: str, line: bytes):
    pub = b"ssh-ed25519 " + blob.encode("ascii")
    found = [x for x in raw.splitlines() if pub in x.split(b"ssh-ed25519 ", 1)[-1]]
    # The above string containment is deliberately supplemented by exact
    # token parsing: no same-key different-authority admission is accepted.
    matches = [x for x in raw.splitlines() if re.search(
        rb"(?:^|\s)ssh-ed25519\s+" + re.escape(blob.encode("ascii")) + rb"(?:\s|$)", x)]
    require(len(matches) <= 1, "C08_DUPLICATE_TRANSPORT_KEY")
    if matches:
        require(matches[0] + b"\n" == line, "C08_TRANSPORT_KEY_WRONG_RESTRICTIONS")
        return "ALREADY_ENROLLED"
    require(b"aoe2war-receiver-20261102.py" in raw
            and raw.count(b"aoe2war-receiver-20261102.py") == 1,
            "C08_C06_RECEIVER_RECORD_NOT_PRESERVED")
    return "ABSENT"


def preflight(home: Path, pub: bytes):
    require(sys.version_info >= (3, 11), "C08_PY311_REQUIRED")
    require(os.geteuid() != 0, "C08_REFUSE_ROOT_INTEL_ACCOUNT")
    base = home / ".wolo-owner-authority/witness-runtime"
    private_directory(home / ".ssh")
    private_directory(base)
    private_directory(base / "authority")
    private_directory(base / "nonces")
    config_raw = secure_read(base / "authority/solo-witness.json")
    require(sha(config_raw) == EXPECTED_CONFIG_SHA, "C08_WITNESS_ENROLLMENT_DIGEST_DRIFT")
    try:
        c = json.loads(config_raw)
    except (ValueError, UnicodeError):
        raise HoldError("C08_ENROLLMENT_JSON_INVALID") from None
    require(type(c) is dict and c.get("schema") ==
            "wolo.solo-maintenance-runtime-enrollment.v1"
            and c.get("source_commit") == EXPECTED_CONFIG_SOURCE
            and c.get("controller_files", {}).get("settlement_solo_runtime.py")
            == EXPECTED_SCRIPT_SHA, "C08_WITNESS_SOURCE_PIN_DRIFT")
    require(sha(secure_read(base / "authority/solo-owner.json"))
            == c.get("owner_enrollment_sha256"), "C08_OWNER_ENROLLMENT_SHA_DRIFT")
    require(sha(secure_read(base / "source/settlement_solo_runtime.py"))
            == EXPECTED_SCRIPT_SHA, "C08_INSTALLED_WITNESS_SOURCE_DRIFT")
    spec = c.get("crypto", {}).get("witness", {})
    binary = Path(spec.get("path", ""))
    require(binary.is_absolute() and binary == binary.resolve(strict=True)
            and binary.is_file() and not binary.is_symlink(),
            "C08_PINNED_WITNESS_OPENSSL_PATH_DRIFT")
    require(sha(binary.read_bytes()) == spec.get("sha256"),
            "C08_PINNED_WITNESS_OPENSSL_BINARY_DRIFT")
    p = subprocess.run(["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                       capture_output=True, check=False, timeout=6)
    import re as _re
    matches = _re.findall(rb'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]{36})"',p.stdout)
    require(p.returncode == 0 and len(matches)==1,
            "C08_INTEL_HOST_UUID_UNAVAILABLE")
    identity = sha(matches[0].lower())
    require(identity == c.get("witness",{}).get("host_identity_sha256")
            and identity != c.get("host_identity_sha256"),
            "C08_WITNESS_HOST_NOT_INDEPENDENT")
    nonce_entries = list((base / "nonces").iterdir())
    require(len(nonce_entries) <= 4096, "C08_NONCE_DIR_UNBOUNDED")
    for n in nonce_entries:
        st = n.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
                and stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1,
                "C08_NONCE_LEDGER_FILE_UNSAFE")
    binary_py = Path(INTERPRETER)
    require(binary_py.exists() and binary_py.is_file(),
            "C08_PINNED_PY313_BINARY_UNAVAILABLE")
    raw = secure_read(home / ".ssh/authorized_keys")
    blob = public_key_blob(pub)
    line = key_line(home, blob)
    return {
        "keys": raw, "line": line, "sha": sha(raw), "blob": blob,
        "existing_state": classify_keys(raw, blob, line),
        "nonce_count": len(nonce_entries),
    }


def atomic_replace(path: Path, original: bytes, new: bytes):
    require(secure_read(path) == original, "C08_AUTHORIZED_KEYS_CHANGED_BEFORE_WRITE")
    fd, tmp = tempfile.mkstemp(prefix=".wolo-c08-witness-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(new)
            out.flush()
            os.fsync(out.fileno())
        require(secure_read(path) == original,
                "C08_AUTHORIZED_KEYS_CHANGED_DURING_WRITE")
        os.replace(tmp, path)
        require(secure_read(path) == new, "C08_AUTHORIZED_KEYS_POSTCHECK_FAILED")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_backup(folder: Path, original: bytes):
    require(not folder.exists() and folder.parent.is_dir()
            and not folder.parent.is_symlink(),
            "C08_BACKUP_ALREADY_EXISTS_OR_UNSAFE")
    folder.mkdir(mode=0o700)
    private_directory(folder)
    p = folder / "authorized_keys.before"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(original)
        out.flush()
        os.fsync(out.fileno())
    require(secure_read(p) == original, "C08_BACKUP_INTEGRITY_FAILED")
    return p


def action(home: Path, pub: bytes, mode: str, expected_keys_sha: str | None = None):
    require(mode in MODELS, "C08_MODE_INVALID")
    # Superseded: this helper modifies NORMAL macOS ~/.ssh/authorized_keys,
    # not the source-reviewed Intel dedicated witness SSHD at localhost:22996.
    # Retain only read-only plan and exact rollback for a preexisting entry.
    require(mode != "apply",
            "C08_SUPERSEDED_NORMAL_MACOS_SSH_KEY_ADMISSION_DISABLED")
    data = preflight(home,pub)
    old, line = data["keys"], data["line"]
    path = home / ".ssh/authorized_keys"
    backup_dir = home / ".wolo-owner-authority/witness-runtime/c08-ssh-enrollment-backup"
    if mode == "plan":
        return dict(status="HOLD_UNFUNDED_SSH_PLAN",current_keys_sha256=sha(old),
                    expected_keys_sha256=EXPECTED_OLD_KEYS_SHA,
                    transport_key_state=data["existing_state"],nonce_entries=data["nonce_count"],
                    financial_release_authorized=False)
    require(type(expected_keys_sha) is str
            and re.fullmatch(r"[a-f0-9]{64}",expected_keys_sha) is not None
            and expected_keys_sha == sha(old), "C08_AUTHORIZED_KEYS_COMPARE_AND_SWAP_FAILED")
    if mode == "apply":
        require(data["existing_state"] == "ABSENT"
                and sha(old) == EXPECTED_OLD_KEYS_SHA,
                "C08_BASELINE_KEYS_OR_EXISTING_WITNESS_DRIFT")
        backup=save_backup(backup_dir,old)
        new=old+(b"" if old.endswith(b"\n") else b"\n")+line
        atomic_replace(path,old,new)
        return dict(status="HOLD_SSH_KEY_ADMITTED_ONLY",
                    before_sha256=sha(old),after_sha256=sha(new),
                    backup_sha256=sha(secure_read(backup)),
                    transport_key_state="ENROLLED",
                    financial_release_authorized=False)
    # Rollback is scoped to exactly our appended line, with no editing of a
    # concurrent operator key or C06 receiver entry.
    require(data["existing_state"] == "ALREADY_ENROLLED",
            "C08_NOT_OUR_AUTHORIZED_KEY")
    private_directory(backup_dir)
    original = secure_read(backup_dir/"authorized_keys.before")
    require(sha(original) == EXPECTED_OLD_KEYS_SHA
            and old == original + (b"" if original.endswith(b"\n") else b"\n") + line,
            "C08_ROLLBACK_MUST_PRESERVE_C06_AND_ALL_OTHER_KEYS")
    atomic_replace(path,old,original)
    return dict(status="HOLD_OWN_ENTRY_ROLLED_BACK",
                restored_sha256=sha(original),financial_release_authorized=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",required=True,choices=sorted(MODELS))
    parser.add_argument("--public-key-file",type=Path,required=True)
    parser.add_argument("--expected-authorized-keys-sha256",default=None)
    args=parser.parse_args(argv)
    try:
        require(args.public_key_file.is_absolute() and not args.public_key_file.is_symlink(),
                "C08_PUBLIC_KEY_PATH_UNSAFE")
        pub=args.public_key_file.read_bytes()
        require(0<len(pub)<4096, "C08_PUBLIC_KEY_SIZE_INVALID")
        report=action(Path.home(),pub,args.mode,args.expected_authorized_keys_sha256)
    except (HoldError,OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        reason=str(exc) if type(exc) is HoldError else "C08_TRANSPORT_ENROLLMENT_UNAVAILABLE"
        print(json.dumps({"schema":SCHEMA,"status":"STOP","reason":reason,
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(dict(schema=SCHEMA,**report),sort_keys=True))
    return 3


if __name__=="__main__":
    sys.exit(main())
