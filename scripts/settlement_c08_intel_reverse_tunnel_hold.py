#!/usr/bin/env python3
"""C08 HOLD: independent Intel -> HEL1 restricted witness tunnel supervisor.

The only remote permission held by the enrolled tunnel key is listening on
HEL1 loopback 22995, forwarding to the Intel's dedicated witness
SSHD on Intel loopback 22996 (NOT the normal macOS port 22). The purpose
is to let HEL1 contact the real offhost C08 nonce witness over SSH. It does
NOT submit a witness packet, consume a nonce, authorize funds, touch C06's
separate 22996 recovery tunnel, or alter production validator/settlement.

plan: verify installed offhost authority, ssh pins and existing launchd state.
install: explicit opt-in, installs only exact source and one LaunchAgent with
        no command-shell, runs via launchctl. No unrelated file/service writes.
rollback: bootout this one reviewed job and remove only our byte-exact files.
run: private launchd entrypoint checks source digest and execs fixed SSH -N.
All initial/rollback actions return 3/HOLD, never financial acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import stat
import subprocess
import sys

SCHEMA="wolo.c08.intel-22995-launchd-dedicated-witness-sshd.v2"
LABEL="com.aoe2war.c08-witness-reverse"
EXPECTED_HOME=Path("/Users/tonyblum")
REL_TUNNEL=Path(".wolo-owner-authority/tunnel")
SOURCE_FILE="c08_witness_reverse_guard.py"
LAUNCH_FILE=LABEL+".plist"
PYTHON=Path("/usr/local/bin/python3.13")
SSH=Path("/usr/bin/ssh")
REMOTE="wolo-witness-tunnel@157.180.114.124"
PORT_FORWARD="localhost:22995:127.0.0.1:22996"
KEY_FILE="intel-to-hel1-ed25519"
PUB_FILE=KEY_FILE+".pub"
HOST_FILE="hel1-known-hosts"
EXPECTED_PUB_BLOB_SHA="32dc6e004b2bc6a810a9dfcde27b5fd7179aaa4a17a41f8c2dc68fb2eb57ff85"
EXPECTED_KNOWN_SHA="7cfec59a6ea6346add5366c8d40e0ffd5e57e0244c598445272543ba06509e5f"
EXPECTED_HEL1_HOST_BLOB_SHA="6b7d9a5d2902d25084a59c96f6494bba79571b1999cd606e16f7098463397b86"
EXPECTED_WITNESS_CONFIG_SHA="5fae8033a2c3d5e38e5e0a59369c9567d9c71caa09b8b92e5ad20add29b45299"
EXPECTED_DEDICATED_SSHD_HOST_BLOB_SHA="45c6153f1a67b5585662aa072e03dde6b09ad607e030b40834262aa436687194"
EXPECTED_DEDICATED_C08_CLIENT_BLOB_SHA="ce07e3593fc557cafbbeabe05f1a7c6a1200c01984595a75a726b8f414180fe6"
MAX_SOURCE=65536
MAX_FILE=131072
# No active witness executable is currently source-approved. An explicit,
# reviewed exact command must replace None before the dedicated backend can
# ever be admitted; string-substring matches are NEVER authorization.
REVIEWED_WITNESS_EXEC_COMMAND:bytes|None=None


class Hold(ValueError):
    pass


def require(condition:bool,code:str):
    if not condition:
        raise Hold(code)


def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def secure_regular(path:Path,mode:int,*,read:bool=False)->bytes|None:
    require(path.is_absolute() and ".." not in path.parts and not path.is_symlink(),
            "C08_UNSAFE_FILE_PATH")
    try:
        s=path.lstat()
    except OSError:
        raise Hold("C08_REQUIRED_FILE_ABSENT") from None
    require(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid()
            and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1
            and 0<s.st_size<MAX_FILE,"C08_FILE_OWNER_MODE_TYPE_OR_SIZE_DRIFT")
    if not read:
        return None
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        out=bytearray()
        while len(out)<=MAX_FILE:
            block=os.read(fd,min(8192,MAX_FILE+1-len(out)))
            if not block:break
            out.extend(block)
        after=os.fstat(fd)
        require(len(out)==before.st_size
                and all(getattr(before,k)==getattr(after,k)
                        for k in ("st_ino","st_dev","st_size","st_ctime_ns",
                                  "st_mtime_ns","st_mode","st_uid","st_nlink")),
                "C08_FILE_CHANGED_DURING_READ")
        return bytes(out)
    finally:
        os.close(fd)


def dir_mode(path:Path,mode:int):
    require(path.is_absolute() and path.is_dir() and not path.is_symlink()
            and path.lstat().st_uid==os.geteuid()
            and stat.S_IMODE(path.lstat().st_mode)==mode,
            "C08_TUNNEL_DIRECTORY_NOT_ENROLLED")


def tunnel_paths(home:Path):
    root=home/REL_TUNNEL
    return {
        "home":home, "authority":home/".wolo-owner-authority",
        "root":root, "private":root/KEY_FILE,"pub":root/PUB_FILE,
        "known":root/HOST_FILE,
        "witness":home/".wolo-owner-authority/witness-runtime/authority/solo-witness.json",
        "dedicated":home/".wolo-owner-authority/witness-sshd",
        "dedicated_config":home/".wolo-owner-authority/witness-sshd/sshd_config",
        "dedicated_authorized":home/".wolo-owner-authority/witness-sshd/authorized_keys",
        "dedicated_host_pub":home/".wolo-owner-authority/witness-sshd/ssh_host_ed25519_key.pub",
        "installed":root/SOURCE_FILE,
        "agents":home/"Library/LaunchAgents",
        "plist":home/"Library/LaunchAgents"/LAUNCH_FILE,
    }


def dedicated_backend_status(paths:dict[str,Path])->dict:
    """Check Intel-local dedicated sshd, never substitute the normal port 22."""
    dir_mode(paths["dedicated"],0o700)
    pub=secure_regular(paths["dedicated_host_pub"],0o600,read=True)
    cfg=secure_regular(paths["dedicated_config"],0o600,read=True)
    auth=secure_regular(paths["dedicated_authorized"],0o600,read=True)
    require(pub is not None and cfg is not None and auth is not None,
            "C08_DEDICATED_WITNESS_SSHD_UNREADABLE")
    pk=pub.split()
    require(len(pk)>=2 and pk[0]==b"ssh-ed25519"
            and digest(pk[1])==EXPECTED_DEDICATED_SSHD_HOST_BLOB_SHA,
            "C08_DEDICATED_WITNESS_HOST_KEY_MISMATCH")
    lines=[line.strip() for line in cfg.splitlines()
           if line.strip() and not line.lstrip().startswith(b"#")]
    expected_dir=str(paths["dedicated"]).encode("ascii")
    required=(b"Port 22996",b"ListenAddress 127.0.0.1",
              b"HostKey "+expected_dir+b"/ssh_host_ed25519_key",
              b"AuthorizedKeysFile "+expected_dir+b"/authorized_keys",
              b"PidFile "+expected_dir+b"/sshd.pid",
              b"AllowUsers tonyblum",
              b"PubkeyAuthentication yes",b"PasswordAuthentication no",
              b"UsePAM no",b"StrictModes yes",b"PermitTTY no",
              b"AllowTcpForwarding no")
    # OpenSSH accepts many case-insensitive/first-value or additive directives.
    # Merely including the expected safe lines does NOT reject earlier unsafe
    # options, e.g. PasswordAuthentication yes before the reviewed no.
    # This exact allowlist is source-bound to the current *deny-only* Intel host.
    optional_safe=(b"AddressFamily inet",b"PermitRootLogin no",
                   b"AuthenticationMethods publickey",
                   b"ChallengeResponseAuthentication no",
                   b"AllowAgentForwarding no",b"X11Forwarding no",
                   b"PermitTunnel no",b"PermitUserEnvironment no",
                   b"MaxSessions 1")
    deny_force=b"ForceCommand /usr/bin/false"
    permitted=set(required)|set(optional_safe)|{deny_force}
    require(len(lines)==len(set(lines))
            and all(line in permitted for line in lines)
            and all(lines.count(line)==1 for line in required),
            "C08_DEDICATED_WITNESS_SSHD_CONFIG_DRIFT")
    auth_lines=[x.strip() for x in auth.splitlines() if x.strip()]
    require(len(auth_lines)==1,
            "C08_DEDICATED_WITNESS_CLIENT_AUTH_SCOPE_DRIFT")
    option,sep,key_and_comment=auth_lines[0].partition(b" ssh-ed25519 ")
    command_match=re.fullmatch(rb'restrict,command="([^"\\\\\r\n]{1,240})"',option)
    require(bool(sep) and command_match is not None,
            "C08_DEDICATED_WITNESS_CLIENT_AUTH_SCOPE_DRIFT")
    pub_fields=key_and_comment.split(None,1)
    require(len(pub_fields) in (1,2) and
            digest(pub_fields[0])==EXPECTED_DEDICATED_C08_CLIENT_BLOB_SHA,
            "C08_DEDICATED_ROOT_WITNESS_KEY_NOT_PINNED")
    forced_command=command_match.group(1)
    # The present host is deny-only. No real witness executable is approved
    # merely because its name/flags appear somewhere in an SSH option line.
    require(forced_command==b"/usr/bin/false" or
            (REVIEWED_WITNESS_EXEC_COMMAND is not None and
             forced_command==REVIEWED_WITNESS_EXEC_COMMAND),
            "C08_DEDICATED_WITNESS_COMMAND_NOT_REVIEWED")
    denied=(deny_force in lines or forced_command==b"/usr/bin/false")
    protocol_forced=(REVIEWED_WITNESS_EXEC_COMMAND is not None and
                     forced_command==REVIEWED_WITNESS_EXEC_COMMAND and
                     not denied)
    listening=False
    if not denied and protocol_forced:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.settimeout(0.35)
            listening=sock.connect_ex(("127.0.0.1",22996))==0
    return {
        "intel_dedicated_witness_sshd_host_key_pinned":True,
        "intel_dedicated_witness_sshd_port":22996,
        "dedicated_witness_deny_profile_active":bool(denied),
        "dedicated_witness_protocol_forced":bool(protocol_forced),
        "dedicated_witness_sshd_listening":bool(listening),
        "dedicated_backend_admitted":bool(not denied and protocol_forced and listening),
    }


def ssh_arguments(paths:dict[str,Path])->list[str]:
    return [str(SSH),"-F","/dev/null","-N","-T",
            "-o","BatchMode=yes",
            "-o","StrictHostKeyChecking=yes",
            "-o","HostKeyAlgorithms=ssh-ed25519",
            "-o","IdentitiesOnly=yes",
            "-o","ExitOnForwardFailure=yes",
            "-o","ServerAliveInterval=15",
            "-o","ServerAliveCountMax=3",
            "-o","ConnectTimeout=10",
            "-o","ForwardAgent=no",
            "-o","VerifyHostKeyDNS=no",
            "-o","UpdateHostKeys=no",
            "-o","ProxyCommand=none",
            "-o","ProxyJump=none",
            "-o","GlobalKnownHostsFile=/dev/null",
            "-o","UserKnownHostsFile="+str(paths["known"]),
            "-i",str(paths["private"]),
            "-R",PORT_FORWARD,
            REMOTE]


def launch_plist(paths:dict[str,Path],source_sha:str)->bytes:
    require(re.fullmatch(r"[0-9a-f]{64}",source_sha) is not None,
            "C08_SOURCE_DIGEST_INVALID")
    record={
        "Label":LABEL,
        "ProgramArguments":[str(PYTHON),"-B",str(paths["installed"]),
                            "--mode","run","--source-sha256",source_sha],
        "RunAtLoad":True,
        "KeepAlive":True,
        "ThrottleInterval":30,
        "ProcessType":"Background",
    }
    return plistlib.dumps(record,fmt=plistlib.FMT_XML,sort_keys=True)


def account_preflight(paths:dict[str,Path]):
    require(sys.version_info>=(3,11),"C08_PYTHON_TOO_OLD")
    require(os.geteuid()!=0 and os.getuid()==os.geteuid(),
            "C08_INTEL_ACCOUNT_ONLY")
    require(Path.home()==EXPECTED_HOME and paths["home"]==EXPECTED_HOME,
            "C08_INTEL_HOME_NOT_SOURCE_PINNED")
    for name,mode in (("authority",0o700),("root",0o700),("agents",0o755)):
        dir_mode(paths[name],mode)
    secure_regular(paths["private"],0o600)
    pub=secure_regular(paths["pub"],0o644,read=True)
    require(pub is not None,"C08_TUNNEL_PUBLIC_KEY_UNREADABLE")
    t=pub.split()
    require(len(t)>=2 and t[0]==b"ssh-ed25519"
            and digest(t[1])==EXPECTED_PUB_BLOB_SHA,
            "C08_TUNNEL_SSH_IDENTITY_DRIFT")
    known=secure_regular(paths["known"],0o600,read=True)
    require(known is not None and digest(known)==EXPECTED_KNOWN_SHA,
            "C08_TUNNEL_HEL1_TRUST_DRIFT")
    rows=known.strip().splitlines()
    require(len(rows)==1 and len(rows[0].split())==3,
            "C08_HOST_KEY_SCOPE_CHANGED")
    hosts,alg,blob=rows[0].split()
    require(hosts==b"157.180.114.124" and alg==b"ssh-ed25519"
            and digest(blob)==EXPECTED_HEL1_HOST_BLOB_SHA,
            "C08_HEL1_SSH_HOST_PIN_DRIFT")
    conf=secure_regular(paths["witness"],0o600,read=True)
    require(conf is not None and digest(conf)==EXPECTED_WITNESS_CONFIG_SHA,
            "C08_INTEL_WITNESS_ENROLLMENT_CHANGED")
    st=SSH.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==0
            and not (st.st_mode&0o022) and not SSH.is_symlink(),
            "C08_OS_SSH_CLIENT_UNTRUSTED")
    require(PYTHON.exists(),"C08_PINNED_PYTHON_UNAVAILABLE")
    backend=dedicated_backend_status(paths)
    return {"schema":SCHEMA,"status":"HOLD_ONLY",
            "intel_tunnel_identity_pinned":True,
            "HEL1_host_key_pinned":True,
            "reverse_scope":"HEL1_LOOPBACK_22995_ONLY",
            "c06_recovery_port_22996_untouched":True,
            "offhost_witness_nonce_consumed":False,
            "financial_release_authorized":False,
            **backend}


def atomic_new(path:Path,data:bytes,mode:int):
    require(not path.exists() and not path.is_symlink()
            and path.parent.is_dir(),"C08_DESTINATION_ALREADY_PRESENT")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb") as out:
            os.fchmod(out.fileno(),mode)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        require(secure_regular(path,mode,read=True)==data,
                "C08_SOURCE_FILE_WRITE_CORRUPTED")
    except BaseException:
        # Do not delete unexpected externally edited files after write failure.
        raise


def run_launchctl(args:list[str]):
    p=subprocess.run(["/bin/launchctl"]+args,capture_output=True,check=False,
                     timeout=10,env={"PATH":"/usr/bin:/bin","HOME":str(EXPECTED_HOME)})
    require(p.returncode==0,"C08_LAUNCHD_COMMAND_FAILED")


def plan(paths:dict[str,Path],source_bytes:bytes)->dict:
    info=account_preflight(paths)
    require(type(source_bytes) is bytes and 0<len(source_bytes)<=MAX_SOURCE,
            "C08_LAUNCH_SOURCE_UNAVAILABLE")
    label_state=subprocess.run(["/bin/launchctl","print",
                                 "gui/"+str(os.geteuid())+"/"+LABEL],
                                capture_output=True,timeout=5)
    require(label_state.returncode!=0 and not paths["installed"].exists()
            and not paths["plist"].exists(),
            "C08_EXISTING_LAUNCHD_OR_SOURCE_NOT_PRISTINE")
    info.update({"status":"HOLD_SOURCE_PINNED_TUNNEL_INSTALL_PLAN" if
                 info["dedicated_backend_admitted"] else
                 "HOLD_DEDICATED_WITNESS_SSHD_NOT_ADMITTED",
                 "code_sha256":digest(source_bytes),
                 "launch_plist_sha256":digest(launch_plist(paths,digest(source_bytes))),
                 "launchd_loaded":False})
    return info


def install(paths:dict[str,Path],source_bytes:bytes,expected_sha:str):
    pre=plan(paths,source_bytes)
    require(pre["dedicated_backend_admitted"] is True,
            "C08_DEDICATED_WITNESS_SSHD_NOT_ADMITTED")
    require(expected_sha==pre["code_sha256"],
            "C08_UNREVIEWED_TUNNEL_SOURCE")
    xml=launch_plist(paths,expected_sha)
    atomic_new(paths["installed"],source_bytes,0o500)
    atomic_new(paths["plist"],xml,0o600)
    run_launchctl(["bootstrap","gui/"+str(os.geteuid()),str(paths["plist"])])
    return dict(pre,status="HOLD_SOURCE_INSTALLED_SSH_ONLY",launchd_loaded=True)


def rollback(paths:dict[str,Path],source_sha:str):
    # Recovery must remain possible when the witness backend or its trust
    # material is unavailable. Only our byte-exact installed files can go.
    require(os.geteuid()!=0 and os.getuid()==os.geteuid()
            and Path.home()==EXPECTED_HOME
            and paths["home"]==EXPECTED_HOME,
            "C08_INTEL_ROLLBACK_ACCOUNT_NOT_PINNED")
    for name,mode in (("authority",0o700),("root",0o700),("agents",0o755)):
        dir_mode(paths[name],mode)
    info={"schema":SCHEMA,"status":"HOLD_ONLY",
          "financial_release_authorized":False,
          "offhost_witness_nonce_consumed":False,
          "c06_recovery_port_22996_untouched":True}
    require(re.fullmatch(r"[a-f0-9]{64}",source_sha) is not None,
            "C08_UNREVIEWED_ROLLBACK_SOURCE")
    source=secure_regular(paths["installed"],0o500,read=True)
    plist=secure_regular(paths["plist"],0o600,read=True)
    require(source is not None and plist is not None
            and digest(source)==source_sha
            and plist==launch_plist(paths,source_sha),
            "C08_ROLLBACK_CANNOT_DELETE_CHANGED_SERVICE")
    p=subprocess.run(["/bin/launchctl","bootout",
                      "gui/"+str(os.geteuid()),str(paths["plist"])],
                     capture_output=True,timeout=10,
                     env={"PATH":"/usr/bin:/bin","HOME":str(EXPECTED_HOME)})
    # A missing launchd unit is permissible, but any other failure is STOP.
    require(p.returncode==0 or b"Could not find service" in p.stderr,
            "C08_LAUNCHD_SHUTDOWN_NOT_CONFIRMED")
    require(secure_regular(paths["installed"],0o500,read=True)==source
            and secure_regular(paths["plist"],0o600,read=True)==plist,
            "C08_CANNOT_REMOVE_CONCURRENT_OPERATOR_EDIT")
    paths["plist"].unlink()
    paths["installed"].unlink()
    return dict(info,status="HOLD_C08_OWN_TUNNEL_SERVICE_REMOVED")


def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--mode",required=True,choices=("plan","install","rollback","run"))
    a.add_argument("--source-sha256")
    args=a.parse_args(argv)
    paths=tunnel_paths(Path.home())
    try:
        if args.mode=="run":
            pre=account_preflight(paths)
            require(pre["dedicated_backend_admitted"] is True,
                    "C08_DEDICATED_WITNESS_SSHD_NOT_ADMITTED")
            self_source=secure_regular(Path(__file__).resolve(),0o500,read=True)
            require(self_source is not None and digest(self_source)==args.source_sha256,
                    "C08_INSTALLED_TUNNEL_SOURCE_SHA_CHANGED")
            os.execv(str(SSH),ssh_arguments(paths))
            raise Hold("C08_EXEC_UNEXPECTEDLY_RETURNED")
        source=Path(__file__).read_bytes()
        if args.mode=="plan":
            report=plan(paths,source)
        elif args.mode=="install":
            report=install(paths,source,args.source_sha256)
        else:
            report=rollback(paths,args.source_sha256)
    except (Hold,OSError,ValueError,subprocess.SubprocessError):
        print(json.dumps({"schema":SCHEMA,"status":"STOP",
                          "reason":"C08_WITNESS_TUNNEL_NOT_QUALIFIED",
                          "financial_release_authorized":False},sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 3


if __name__=="__main__":
    sys.exit(main())
