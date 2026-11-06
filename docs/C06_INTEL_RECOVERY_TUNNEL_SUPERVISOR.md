---
id: "aoe2war.wolochain.c06-intel-recovery-tunnel-supervisor"
title: "C06 Intel Recovery Tunnel Supervisor"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-intel-recovery-transport-not-a-financial-permit"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C06 Intel Recovery Tunnel Supervisor

## Actual trigger and threat boundary

On November 6, 2026 at 19:24 UTC the previously working HEL1 loopback-only Intel receiver reverse tunnel on TCP 22995 was **not listening**. This is a C06 off-host transport HOLD, not evidence that encrypted recovery keys or prior backups were lost. Do not assume the Intel Mac is powered or reachable because the past restore rehearsals succeeded.

The new source-only `scripts/c06_intel_reverse_tunnel_supervisor.py` is an **installer and explicit HOLD preflight**, not a financial agent. It is designed to run only as a nonroot user on the Intel (x86_64) macOS receiver. It does not read wallet keys, transmit database content, create an SSH key, change HEL1 configuration, authorize payouts or claim C06 completion.

## One-time receiver enrollment (when Intel is available)

1. Establish a dedicated low-privilege `aoe2war-c06-reverse` SSH endpoint on HEL1. The account must be restricted to the exact **remote loopback listener** `127.0.0.1:22995`, with no remote shell, PTY, agent/X11 forwarding, password authentication, general network forwarding, or wildcard bind. A root/admin should separately review and test the key's authorized_keys options and sshd `Match User` configuration before any enrollment. This source does not provision the account automatically.
2. On the Intel, create **one dedicated transport-only SSH key**, separate from the WOLO custody, founder, reserve, signing and recovery-decryption keys. Its private path must be `~/.ssh/aoe2war_c06_intel_to_hel1`, an owner-owned non-symlink 0600 regular file. Never upload the private key to GitHub, an artifact or ChatGPT.
3. Pin the actual HEL1 SSH host key in `~/.ssh/known_hosts` under the exact alias `hel1-c06-intel`; configure the SSH alias to use **user `aoe2war-c06-reverse` and port 22**, without host-key bypass. The installer checks `ssh-keygen -F hel1-c06-intel` and `ssh -G` effective user and port before staging.
4. A nonroot owner on **the actual Intel** runs `python3 -B scripts/c06_intel_reverse_tunnel_supervisor.py --mode plan` (always returns HOLD/exit3) and only after approved enrollment `--mode install`. It refuses the M1, root, missing/too-broad key modes, symlinks, missing host pin or user mismatch.
5. Installation writes only new files: owner-private `~/.local/libexec/aoe2war-c06-intel-recovery-tunnel.sh` and `~/Library/LaunchAgents/com.aoe2war.c06.intel-recovery-tunnel.plist` (both 0600). Existing paths are NOT overwritten. The installation receipt is **STAGED_NOT_STARTED**, not PASS.
6. After independently verifying configuration and HEL1's listen restriction, use a separately reviewed user LaunchAgent bootstrap. launchd's `RunAtLoad=true`, `KeepAlive=true` and throttle 45s then supervise the outbound `ssh -N -T` command and automatically reconnect after ordinary networking failures **while the Intel is awake and logged in**. No financial content is moved by the tunnel alone.

## Fixed SSH safety properties

The exact generated SSH command uses identity-only authentication, `StrictHostKeyChecking=yes`, explicit `HostKeyAlias=hel1-c06-intel`, fixed known_hosts, `BatchMode=yes`, `ExitOnForwardFailure=yes`, bounded keepalives/timeouts and **only** `-R 127.0.0.1:22995:127.0.0.1:22`. It has no shell execution or wildcard 0.0.0.0 forwarding. On host-key mismatch it must fail closed rather than auto-accept new keys.

Automatic retries cannot wake an unpowered receiver, establish a missing trust anchor, replace a revoked key, certify encryption/decryption or initiate a funded WOLO transfer. Those remain independent admissions. Do not install or activate this agent on M1/HEL1; it is Intel-only.

## Formal acceptance

A new root-local HEL1 physical check must prove the listener is loopback-only, bound to an authorized restricted key, and reaches the **actual** Intel receiver using pinned host identity. Verify clean disconnect/reconnect, persistent launchd restart, no broader forwarding and no login shell before marking transport readiness. C06 itself requires additional fresh coordinated quiesced data, encrypted off-host ciphertext integrity and a real isolated C07 restore. No gate closes by installing this component.
