#!/usr/bin/env python3
"""C08 Intel owner-only dedicated loopback SSHD DENY-ALL launchd controller.

This tool intentionally NEVER permits a witness command. The existing
dedicated SSHD config and restricted authorized_keys BOTH force
/usr/bin/false. It does not edit either file, any key, the owner witness
runtime, HEL1 tunnel, nonce records, database, Wolo signer or payment port.

plan: SHA verify existing owner-private deny-only config/auth/host metadata.
install: explicit owner action, exact private LaunchAgent, reversible.
rollback: exact plist-only bootout/removal (no witness config/key changes).
All success is transport hard-HOLD, never C08 financial acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import socket
import stat
import subprocess
import sys
import time

SCHEMA="wolo.c08.intel-deny-only-sshd-launchd.v1"
LABEL="com.aoe2war.c08-dedicated-witness-deny-sshd"
USER_HOME=Path("/Users/tonyblum")
DEDICATED=USER_HOME/".wolo-owner-authority/witness-sshd"
CONFIG=DEDICATED/"sshd_config"
AUTH=DEDICATED/"authorized_keys"
HOST_PUB=DEDICATED/"ssh_host_ed25519_key.pub"
HOST_PRIVATE=DEDICATED/"ssh_host_ed25519_key"
PLIST=USER_HOME/"Library/LaunchAgents"/(LABEL+".plist")
SSHD=Path("/usr/sbin/sshd")
CONFIG_SHA256="1d41b7586376ba846c3bb14fecdadc8e96d5e41ce7a9b40f084c748fa9caa051"
AUTHORIZED_SHA256="8e4115b4798d3eda6ab482212ad4d1a2ccd42cf20a84eb47b917c4409f9b2907"
HOST_BLOB_SHA256="45c6153f1a67b5585662aa072e03dde6b09ad607e030b40834262aa436687194"
PORT=22996
HOST="127.0.0.1"

class Hold(ValueError):
    pass

def need(ok,reason):
    if not ok:raise Hold(reason)

def digest(b):return hashlib.sha256(b).hexdigest()

def assert_owner_host():
    need(sys.platform=="darwin" and platform.machine()=="x86_64"
         and os.geteuid()!=0 and os.geteuid()==os.getuid()
         and Path.home()==USER_HOME,"NOT_OWNER_INTEL_ACCOUNT")

def secure_dir(path,mode):
    s=path.lstat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid()
         and stat.S_IMODE(s.st_mode)==mode and not path.is_symlink(),
         "UNSAFE_OWNER_DIRECTORY")

def private_file(path,mode,read=False):
    need(path.is_absolute() and not path.is_symlink(),"UNSAFE_WITNESS_FILE_PATH")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        start=os.fstat(fd)
        need(stat.S_ISREG(start.st_mode) and start.st_uid==os.geteuid()
             and start.st_nlink==1 and stat.S_IMODE(start.st_mode)==mode
             and 0<start.st_size<=131072,"WITNESS_FILE_MODE_OWNER_DRIFT")
        if not read:return None
        raw=os.read(fd,131073)
        end=os.fstat(fd)
        need(len(raw)==start.st_size and all(getattr(start,k)==getattr(end,k)
          for k in ("st_dev","st_ino","st_mode","st_uid","st_size","st_mtime_ns","st_ctime_ns")),
          "WITNESS_FILE_RACE")
        return raw
    finally:os.close(fd)

def listen_active():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST,PORT))==0

def state():
    result=subprocess.run(["/bin/launchctl","print",
      "gui/"+str(os.geteuid())+"/"+LABEL],
      capture_output=True,timeout=6)
    return result.returncode==0

def plist():
    record={
        "Label":LABEL,
        "ProgramArguments":[str(SSHD),"-D","-e","-f",str(CONFIG)],
        "RunAtLoad":True,
        "KeepAlive":True,
        "ThrottleInterval":30,
        "ProcessType":"Background",
        "Umask":63,
        "StandardErrorPath":str(DEDICATED/"denied-witness-sshd-stderr.log"),
        "StandardOutPath":str(DEDICATED/"denied-witness-sshd-stdout.log"),
    }
    return plistlib.dumps(record,fmt=plistlib.FMT_XML,sort_keys=True)

def preflight():
    assert_owner_host()
    secure_dir(USER_HOME/".wolo-owner-authority",0o700)
    secure_dir(DEDICATED,0o700)
    secure_dir(USER_HOME/"Library/LaunchAgents",0o755)
    config=private_file(CONFIG,0o600,read=True)
    auth=private_file(AUTH,0o600,read=True)
    host_pub=private_file(HOST_PUB,0o600,read=True)
    private_file(HOST_PRIVATE,0o600)
    need(config is not None and digest(config)==CONFIG_SHA256,
         "EXACT_DENY_ONLY_SSHD_CONFIG_CHANGED")
    need(auth is not None and digest(auth)==AUTHORIZED_SHA256,
         "EXACT_DENY_ONLY_SSH_KEY_COMMAND_CHANGED")
    need(b"ForceCommand /usr/bin/false" in config and
         b'command="/usr/bin/false"' in auth,
         "C08_DENY_ONLY_FORCE_COMMAND_MISSING")
    need(b"ListenAddress 127.0.0.1" in config and
         b"Port 22996" in config and
         b"PasswordAuthentication no" in config and
         b"AllowTcpForwarding no" in config,
         "C08_DEDICATED_WITNESS_SSHD_NOT_LOOPBACK_DENY_ONLY")
    parts=host_pub.split()
    need(len(parts)>=2 and parts[0]==b"ssh-ed25519" and
         digest(parts[1])==HOST_BLOB_SHA256,"DEDICATED_HOST_IDENTITY_CHANGED")
    need(SSHD.is_file() and not SSHD.is_symlink()
         and SSHD.stat().st_uid==0 and not SSHD.stat().st_mode&0o022,
         "OS_SSHD_BINARY_NOT_TRUSTED")
    result=subprocess.run([str(SSHD),"-t","-f",str(CONFIG)],
       capture_output=True,timeout=10)
    need(result.returncode==0,"PINNED_DENY_ONLY_SSHD_SYNTAX_INVALID")
    result2=subprocess.run([str(SSHD),"-T","-f",str(CONFIG)],
       capture_output=True,text=True,timeout=10)
    need(result2.returncode==0 and
         "forcecommand /usr/bin/false" in result2.stdout.lower(),
         "EFFECTIVE_DENY_ALL_COMMAND_NOT_ENFORCED")
    return {
        "schema":SCHEMA,
        "status":"HOLD_DENY_ONLY_SSHD_PRECHECK",
        "expected_config_sha256":CONFIG_SHA256,
        "expected_restricted_authorized_keys_sha256":AUTHORIZED_SHA256,
        "dedicated_host_key_pinned":True,
        "force_command_is_usr_bin_false":True,
        "sshd_config_syntax_and_effective_deny_pass":True,
        "launchd_loaded":state(),
        "loopback_deny_only_listener_active":listen_active(),
        "source_admits_real_witness_executable":False,
        "offhost_nonce_consumed":False,
        "funded_financial_release_authorized":False,
        "production_hel1_changed":False,
    }

def atomic_new(path,data):
    need(not path.exists() and not path.is_symlink(),
         "EXACT_LAUNCHD_PLIST_ALREADY_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),0o600)
            f.write(data);f.flush();os.fsync(f.fileno())
        need(private_file(path,0o600,read=True)==data,
             "ATOMIC_LAUNCHD_PLIST_WRITE_DRIFT")
    except BaseException:
        if path.exists() and path.read_bytes()==data:
            path.unlink()
        raise

def launchctl(args):
    return subprocess.run(["/bin/launchctl"]+list(args),capture_output=True,
            timeout=12,env={"PATH":"/usr/bin:/bin","HOME":str(USER_HOME)})

def install():
    r=preflight()
    need(not r["launchd_loaded"] and not r["loopback_deny_only_listener_active"],
         "WITNESS_SSHD_PREEXISTING_PROCESS_OR_SERVICE")
    desired=plist()
    atomic_new(PLIST,desired)
    result=launchctl(["bootstrap","gui/"+str(os.geteuid()),str(PLIST)])
    if result.returncode:
        need(private_file(PLIST,0o600,read=True)==desired,
             "FAILED_LAUNCHD_PLIST_WAS_MODIFIED")
        PLIST.unlink()
        raise Hold("C08_DENY_ONLY_LAUNCHCTL_BOOTSTRAP_FAILED")
    for _ in range(15):
        if listen_active():
            return dict(r,status="HOLD_DENY_ONLY_SSHD_STARTED_NO_WITNESS",
                launchd_loaded=True,loopback_deny_only_listener_active=True)
        time.sleep(0.3)
    result=launchctl(["bootout","gui/"+str(os.geteuid()),str(PLIST)])
    need(result.returncode==0 and private_file(PLIST,0o600,read=True)==desired,
         "C08_FAILED_START_REQUIRES_OPERATOR_RECOVERY")
    PLIST.unlink()
    raise Hold("C08_DENY_ONLY_LISTENER_DID_NOT_START_ROLLED_BACK")

def rollback():
    # Permitted even if the underlying SSHD config changed, but only the
    # exact source-owned plist may be removed.
    assert_owner_host()
    secure_dir(USER_HOME/"Library/LaunchAgents",0o755)
    desired=plist()
    need(private_file(PLIST,0o600,read=True)==desired,
         "C08_ROLLBACK_NOT_EXACT_OWNED_PLIST")
    if state():
        result=launchctl(["bootout","gui/"+str(os.geteuid()),str(PLIST)])
        need(result.returncode==0,"C08_LAUNCHD_STOP_NOT_CONFIRMED")
    need(private_file(PLIST,0o600,read=True)==desired,
         "C08_PLIST_RACED_DURING_ROLLBACK")
    PLIST.unlink()
    return {"schema":SCHEMA,
            "status":"HOLD_C08_DENY_ONLY_LAUNCHAGENT_REMOVED",
            "financial_release_authorized":False,
            "c08_witness_nonce_consumed":False,
            "production_hel1_changed":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("plan","install","rollback"),default="plan")
    args=p.parse_args()
    try:
        data=rollback() if args.mode=="rollback" else (
            install() if args.mode=="install" else preflight())
    except (Hold,OSError,ValueError,subprocess.SubprocessError,UnicodeError):
        print(json.dumps({"schema":SCHEMA,"status":"HOLD_C08_DEDICATED_DENY_ONLY_SSHD_NOT_QUALIFIED",
                          "financial_release_authorized":False,
                          "production_hel1_changed":False},sort_keys=True))
        return 2
    print(json.dumps(data,sort_keys=True))
    return 3

if __name__=="__main__":
    sys.exit(main())
