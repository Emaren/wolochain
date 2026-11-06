#!/usr/bin/env python3
"""C06 Intel off-host SSH recovery tunnel supervisor installer, no finance authority.

The generated macOS LaunchAgent restarts an outbound SSH reverse loopback
forward when networking returns. It does not create credentials, enable SSHD,
change HEL1 ACLs, or send backups. Installation is separate from activation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import plistlib
import shlex
import stat
import subprocess
import sys

SCHEMA = "wolo.c06.intel-receiver-tunnel-supervision.v1"
LABEL = "com.aoe2war.c06.intel-recovery-tunnel"
PORT = 22995
KEY_NAME = "aoe2war_c06_intel_to_hel1"
SSH_HOST = "hel1-c06-intel"
EXPECTED_USER = "aoe2war-c06-reverse"

class Hold(RuntimeError):
    pass

def require(ok, reason):
    if not ok:
        raise Hold(reason)

def public_plan(home: Path) -> dict:
    return {
        "schema": SCHEMA,
        "state": "HOLD_UNENROLLED",
        "requiresIntelMacAndExistingRestrictedKey": True,
        "remoteHostAlias": SSH_HOST,
        "reverseForward": "127.0.0.1:22995:127.0.0.1:22",
        "requiresPinnedKnownHost": True,
        "sshRemoteExecution": False,
        "automatedReconnectWhileMacAwake": True,
        "offhostDecryptionOrBackupProven": False,
        "financialReleaseAuthorized": False,
    }

def ssh_command(home: Path) -> list[str]:
    key = home / ".ssh" / KEY_NAME
    return [
        "/usr/bin/ssh", "-N", "-T", "-i", str(key),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "HostKeyAlias=" + SSH_HOST,
        "-o", "UserKnownHostsFile=" + str(home / ".ssh" / "known_hosts"),
        "-o", "IdentitiesOnly=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ConnectTimeout=10",
        "-o", "ConnectionAttempts=1",
        "-o", "ControlMaster=no",
        "-o", "PermitLocalCommand=no",
        "-o", "RequestTTY=no",
        "-R", "127.0.0.1:22995:127.0.0.1:22",
        SSH_HOST,
    ]

def render_shell(home: Path) -> bytes:
    return ("#!/bin/sh\numask 077\nexec " +
            " ".join(shlex.quote(x) for x in ssh_command(home)) + "\n").encode()

def render_plist(script: Path) -> bytes:
    obj = {
        "Label": LABEL, "ProgramArguments": ["/bin/sh", str(script)],
        "RunAtLoad": True, "KeepAlive": True,
        "ThrottleInterval": 45, "ProcessType": "Background",
    }
    return plistlib.dumps(obj, sort_keys=True)

def secure_user_file(path: Path, *, private: bool):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
            and st.st_nlink == 1 and not stat.S_ISLNK(st.st_mode),
            "UNSAFE_RECEIVER_CREDENTIAL_PATH")
    mode=stat.S_IMODE(st.st_mode)
    require(mode==0o600 if private else not (mode & 0o022),
            "UNSAFE_RECEIVER_FILE_PERMISSIONS")

def check_local_enrollment(home: Path):
    require(sys.platform == "darwin" and platform.machine() == "x86_64"
            and os.geteuid() == os.getuid() and os.getuid() != 0,
            "INTEL_MAC_NONROOT_REQUIRED")
    require(home.is_absolute() and home.is_dir() and not home.is_symlink(),
            "PRIVATE_HOME_REQUIRED")
    ssh=home/".ssh"
    st=ssh.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid==os.getuid()
            and not st.st_mode & 0o022, "SSH_DIRECTORY_UNSAFE")
    secure_user_file(ssh/KEY_NAME,private=True)
    secure_user_file(ssh/"known_hosts",private=False)
    # Verify a pre-enrolled pin for the EXACT host alias, including hashed files.
    r=subprocess.run(["/usr/bin/ssh-keygen","-F",SSH_HOST,"-f",
                      str(ssh/"known_hosts")],capture_output=True,
                     timeout=5,check=False)
    require(r.returncode==0 and r.stdout, "HEL1_PINNED_HOST_KEY_MISSING")
    effective=subprocess.run(["/usr/bin/ssh","-G",SSH_HOST],
                             capture_output=True,text=True,timeout=5,check=False)
    require(effective.returncode==0 and len(effective.stdout)<32000,
            "C06_HOST_ALIAS_CONFIG_UNAVAILABLE")
    options={}
    for line in effective.stdout.splitlines():
        if " " not in line:continue
        key,value=line.split(" ",1)
        options[key]=value
    require(options.get("user")==EXPECTED_USER and options.get("port")=="22",
            "C06_DEDICATED_NONROOT_SSH_ACCOUNT_REQUIRED")
    return True

def ensure_dir(p: Path):
    if not p.exists():
        p.mkdir(mode=0o700)
    st=p.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid==os.getuid()
            and not (st.st_mode & 0o022) and not stat.S_ISLNK(st.st_mode),
            "UNSAFE_INSTALL_DIRECTORY")

def exclusive(path: Path, data: bytes):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def install(home: Path):
    check_local_enrollment(home)
    lib=home/".local"
    ensure_dir(lib)
    out=lib/"libexec"
    ensure_dir(out)
    agents=home/"Library"/"LaunchAgents"
    ensure_dir(agents)
    script=out/"aoe2war-c06-intel-recovery-tunnel.sh"
    plist=agents/(LABEL+".plist")
    require(not script.exists() and not plist.exists(),
            "EXISTING_TUNNEL_INSTALL_REQUIRES_REVIEW")
    exclusive(script,render_shell(home))
    try:
        exclusive(plist,render_plist(script))
    except BaseException:
        # Remove only the brand-new script we created, never pre-existing data.
        script.unlink(missing_ok=True)
        raise
    return {"schema":SCHEMA,"state":"STAGED_NOT_STARTED",
            "launchAgent":str(plist),"script":str(script),
            "financialReleaseAuthorized":False}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("plan","install"),default="plan")
    args=parser.parse_args(argv)
    home=Path.home()
    try:
        result=public_plan(home) if args.mode=="plan" else install(home)
    except (Hold,OSError,subprocess.SubprocessError) as e:
        reason=str(e) if isinstance(e,Hold) else "RECEIVER_INSTALL_UNAVAILABLE"
        print("HOLD:"+reason)
        return 2
    import json
    print(json.dumps(result,sort_keys=True))
    return 3

if __name__=="__main__":
    sys.exit(main())
