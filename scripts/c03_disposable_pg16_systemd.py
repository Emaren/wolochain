#!/usr/bin/env python3
"""Real disposable Linux systemd/PG16 mask and exact-absent-unit inverse test.

Requires owner opt-in and an ephemeral Ubuntu GitHub runner. Only unique
we1-c03-disposable-* units; never targets any existing financial service.
"""
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

PG = Path("/usr/lib/postgresql/16/bin")


def command(args, ok=True, timeout=30):
    p = subprocess.run([str(x) for x in args], text=True, capture_output=True, timeout=timeout)
    if (p.returncode == 0) != ok:
        raise AssertionError("unexpected command return: " + repr(args) + " stderr=" + p.stderr[-700:])
    return p


def check(condition, description, checks):
    if not condition:
        raise AssertionError(description)
    checks.append(description)


def main():
    if os.environ.get("WE1_C03_DISPOSABLE_SYSTEMD_ONLY") != "1":
        raise RuntimeError("C03_SYSTEMD_DISPOSABLE_EXPLICIT_OPTIN_REQUIRED")
    if os.geteuid() == 0 or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("C03_SYSTEMD_REQUIRES_UNPRIVILEGED_EPHEMERAL_GITHUB_RUNNER")
    for binary in ("initdb", "postgres", "psql", "pg_isready"):
        if not (PG / binary).is_file():
            raise RuntimeError("MISSING_PG16_BINARY_" + binary)
    command(["systemctl", "--version"])
    check_pid = os.getpid()
    unit = "we1-c03-disposable-pg16-" + str(check_pid) + ".service"
    if not unit.startswith("we1-c03-disposable-pg16-"):
        raise AssertionError("bad synthetic unit")
    unitfile = Path("/etc/systemd/system") / unit
    runtime_mask = Path("/run/systemd/system") / unit
    if unitfile.exists() or unitfile.is_symlink() or runtime_mask.exists() or runtime_mask.is_symlink():
        raise RuntimeError("SOURCE_PREIMAGE_NOT_ABSENT")
    checks = []
    installed = False
    with tempfile.TemporaryDirectory(prefix="we1-c03-systemd-pg16-") as tmp:
        root = Path(tmp)
        cluster = root / "pgdata"
        socket = root / "socket"
        socket.mkdir(mode=0o700)
        port = 40000 + os.getpid() % 10000
        owner = getpass.getuser()
        command([PG / "initdb", "-D", cluster, "--no-sync", "--auth-local=trust", "--auth-host=reject"])
        check((cluster / "PG_VERSION").read_text().strip() == "16", "fresh PG16 cluster on isolated private socket", checks)
        hba = cluster / "pg_hba.conf"
        original = hba.read_bytes()
        before_hba = hashlib.sha256(original).hexdigest()
        deny = b"local all all reject\nlocal replication all reject\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
        unit_text = (
            "[Unit]\nDescription=C03 SOURCE-ONLY disposable PostgreSQL16 systemd negative\n"
            "After=basic.target\n\n[Service]\nType=simple\n"
            "User=" + owner + "\nGroup=" + owner + "\n"
            "ExecStart=" + str(PG / "postgres") + " -D " + str(cluster)
              + " -c listen_addresses= -c unix_socket_directories=" + str(socket)
              + " -c port=" + str(port) + "\n"
            "Restart=no\nPrivateNetwork=yes\nRestrictAddressFamilies=AF_UNIX\n"
            "NoNewPrivileges=yes\nProtectSystem=strict\nReadWritePaths=" + str(root) + "\n"
            "LimitCORE=0\n\n"
        )
        def ctl(*args, ok=True):
            return command(["sudo", "systemctl", *args], ok=ok)
        def ready(expect=True):
            p = command([PG / "pg_isready", "-h", socket, "-p", port, "-U", owner], ok=expect)
            return p
        try:
            command(["sudo", "tee", unitfile], timeout=20) if False else None
            written = subprocess.run(["sudo", "tee", str(unitfile)], input=unit_text, text=True,
                                     capture_output=True, timeout=20, check=True)
            installed = True
            ctl("daemon-reload")
            ctl("start", unit)
            for _ in range(35):
                if subprocess.run([str(PG / "pg_isready"), "-h", str(socket), "-p", str(port),
                                   "-U", owner], capture_output=True).returncode == 0:
                    break
                time.sleep(0.2)
            ready(True)
            check(True, "real systemd started disposable PG16 database", checks)
            state = command(["systemctl", "show", unit, "-p", "ActiveState", "-p", "PrivateNetwork",
                             "-p", "RestrictAddressFamilies", "-p", "NoNewPrivileges",
                             "-p", "ProtectSystem", "-p", "MainPID"]).stdout
            check("ActiveState=active" in state and "MainPID=0" not in state,
                  "genuine systemd ActiveState and PG16 process PID", checks)
            check("PrivateNetwork=yes" in state and "RestrictAddressFamilies=AF_UNIX" in state
                  and "NoNewPrivileges=yes" in state and "ProtectSystem=strict" in state,
                  "kernel namespace/address family and read-write restrictions loaded", checks)
            # Stop BEFORE applying the runtime mask, then inspect both the
            # on-disk /dev/null symlink and systemd's loaded unit state.
            ctl("stop", unit)
            ctl("mask", "--runtime", unit)
            ctl("daemon-reload")
            check(runtime_mask.is_symlink() and os.readlink(runtime_mask) == "/dev/null",
                  "runtime systemd mask symlink is actual /dev/null", checks)
            masked = command(["systemctl", "show", unit, "-p", "LoadState",
                              "-p", "ActiveState", "-p", "UnitFileState"]).stdout
            check("LoadState=masked" in masked and "ActiveState=inactive" in masked,
                  "systemd effective loaded unit is masked and inactive: " + masked, checks)
            denied_start = command(["sudo", "systemctl", "start", unit], ok=False)
            check(denied_start.returncode != 0 and
                  "ActiveState=inactive" in command(["systemctl", "show", unit, "-p", "ActiveState"]).stdout,
                  "runtime systemd mask denies startup across daemon reload", checks)
            ready(False)
            check(True, "masked unit does not leave postgres socket accepting clients", checks)
            ctl("unmask", "--runtime", unit)
            hba.write_bytes(deny)
            ctl("daemon-reload")
            ctl("start", unit)
            time.sleep(0.6)
            blocked = command([PG / "psql", "-X", "-h", socket, "-p", port, "-U", owner,
                               "-d", "postgres", "-c", "SELECT 1"], ok=False)
            check("reject" in blocked.stderr.lower() or "pg_hba" in blocked.stderr.lower(),
                  "post-startup all-reject HBA denies real PostgreSQL client", checks)
            ctl("stop", unit)
            hba.write_bytes(original)
            ctl("start", unit)
            for _ in range(35):
                if subprocess.run([str(PG / "pg_isready"), "-h", str(socket), "-p", str(port),
                                   "-U", owner], capture_output=True).returncode == 0:
                    break
                time.sleep(0.2)
            query = command([PG / "psql", "-X", "-h", socket, "-p", port, "-U", owner,
                             "-d", "postgres", "-A", "-t", "-c", "SELECT 42"])
            check(query.stdout.strip() == "42", "qualified inverse restores synthetic database startup and query", checks)
            check(hashlib.sha256(hba.read_bytes()).hexdigest() == before_hba,
                  "actual PostgreSQL HBA original bytes restored exactly", checks)
        finally:
            if installed:
                ctl("stop", unit, ok=True)
                if runtime_mask.is_symlink():
                    ctl("unmask", "--runtime", unit)
                command(["sudo", "rm", "--", unitfile])
                ctl("daemon-reload")
        check(not unitfile.exists() and not unitfile.is_symlink()
              and not runtime_mask.exists() and not runtime_mask.is_symlink(),
              "original systemd unit absence restored exactly", checks)
        print(json.dumps({"status": "PASS", "case_count": len(checks), "checks": checks,
                          "real_systemd": True, "postgres": "16",
                          "ephemeral_cluster": True, "tcp_listening": False,
                          "unit_absent_after": True, "hba_original_sha256": before_hba}, sort_keys=True))


if __name__ == "__main__":
    main()
