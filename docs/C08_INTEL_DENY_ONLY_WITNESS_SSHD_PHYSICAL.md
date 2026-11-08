---
id: "aoe2war.wolochain.c08-intel-dedicated-deny-only-sshd-physical-service"
title: "C08 Intel Dedicated Witness SSHD: Persistent Loopback Deny-Only Launchd Service"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "reviewed-deny-only-ssh-transport-no-nonce-or-financial-authority"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Intel Dedicated Witness SSHD: Persistent Loopback Deny-Only Launchd Service

## Why two entirely separate reverse tunnels matter

The existing off-host Intel **C06 encrypted recovery transport** reaches the Intel user's normal SSH through HEL1 `127.0.0.1:22996`. It already passed authenticated independent host-key and 8192-byte synthetic transfer verification.

The distinct **C08 off-host one-use nonce witness** is intended to reach an Intel-dedicated, loopback-only SSHD via a *different* reverse tunnel on HEL1 `127.0.0.1:22995`, landing on Intel `127.0.0.1:22996`. The identical numeric 22996 applies to *different hosts/ports*. This must never substitute normal user SSH port 22 or directly expose a wallet/reviewer service.

Before this change, the Intel-dedicated SSHD configuration/authorized key existed, with dual `/usr/bin/false` forced commands, but no persistent listener. The C08 reverse tunnel's controller intentionally rejects a missing backend and its live authorization is not enrolled.

## Exact reviewed source and hardened profile

`scripts/settlement_c08_intel_deny_only_sshd_launchd.py` provides `--mode plan|install|rollback`, defaulting to non-mutating plan. Runs **only** as unprivileged `tonyblum` on x86_64 Darwin Intel, and binds these pre-existing root-independent private files by byte-exact SHA:

- `~/.wolo-owner-authority/witness-sshd/sshd_config`: `1d41b7586376ba846c3bb14fecdadc8e96d5e41ce7a9b40f084c748fa9caa051`.
- `.../authorized_keys`: `8e4115b4798d3eda6ab482212ad4d1a2ccd42cf20a84eb47b917c4409f9b2907`.
- Existing separately pinned dedicated ED25519 host public key; private host-key metadata mode0600 only, private bytes never read.

The exact existing configuration binds Intel `127.0.0.1:22996` only, disables password authentication and all TCP forwarding, and enforces `ForceCommand /usr/bin/false`. The restricted dedicated SSH key separately forces `/usr/bin/false`. The controller verifies actual effective `sshd -T` output and syntax using `sshd -t`, then creates **one** user-private mode0600 launchd plist without a shell or privilege escalation. Launchd runs `/usr/sbin/sshd -D -e -f <exact path>`, with RunAtLoad/KeepAlive and 0077 umask. Both logs stay inside the owner0700 witness directory.

`--mode rollback` only bootouts the matching launchd unit and deletes its **byte-exact** plist. It cannot edit or destroy the original authorized key, witness code, private key, host key, C06 normal SSH or HEL1 services. If the plist was modified by another operator, rollback fails closed.

## Physical acceptance — November 8, 2026

1. M1 source preflight through the pre-enrolled authenticated Intel C06 recovery SSH: exit **3** `HOLD_DENY_ONLY_SSHD_PRECHECK`, `launchd_loaded=false`, `loopback_deny_only_listener_active=false`. Native Intel `sshd -t` and `-T` passed, effective forced command still `/usr/bin/false`.
2. Re-streamed **exact M1 source SHA256** `d0fa59695d0e7ba4d5dd62ff49f12f4e302afcffd8e79da024868a9518e533f5` to Intel as a temporary owner-private file, verified separately enrolled remote SSH host fingerprint and explicitly executed `--mode install`. Source returned exit **3** `HOLD_DENY_ONLY_SSHD_STARTED_NO_WITNESS`, with physical loopback listener active and funded false.
3. Separate authenticated M1-to-Intel SSH returned: exact launchd plist mode0600 SHA256 `37594ef33ba794805f4e6b2cfc1ac17176c81b97370c3edf09309306a543e07e`, launchd loaded, KeepAlive=true, Intel loopback 22996 listening, effective force command still false.
4. Intel-local no-identity SSH command using strict pinned host-key and **no authentication methods** was rejected with SSH exit **255**; unauthorized marker command was not executed.
5. Fresh HEL1 status: Wolo validator PID1009 unchanged and zero restarts; HEL1 22995 remains closed, existing C06 recovery 22996 remains listening, legacy 8092/8093 remain listening, new funded 8094/8095 remain closed.

Owner-private M1 physical acceptance receipt mode0600:

`~/.wolo-owner-authority/witness-runtime/c08-intel-dedicated-deny-only-sshd-physical-20261108.json`

SHA256 `64cc688b493bfde47d6c51d6ee7454f2b11f3b6b7de91b0f54404f2e9d87bd59`.

The M1 and Intel had no private signing key material copied and no witness packet submitted/nonce consumed. Source and test suite only contain fixed public fingerprints, not private PEM, wallet or database credentials. **The dedicated C08 witness backend is still deliberately deny-only, not a ratified governance or financial release.**

## Qualification and next actual gate

12/12 hermetic source fixture tests include exact launchd arguments/no shell, full config/key/host identity mutation denial, private permissions, preserved nonfinance state, bounded starts, strict plist-only rollback and refusing unreviewed listeners. CI must include this suite; DocsV2 registry must be resealed.

The already merged source-review of the next distinct command admission is `scripts/settlement_c08_intel_reverse_tunnel_hold.py`, source SHA256 `d7a634d02ee127acbf82db884d067c478e2f087c4dc91e72073f049d4ab54161`; it still physically classifies this deny-only SSHD as NOT admitted. Any transition to actual one-use witness must separately review and apply the exact forced-command substitution, reverse tunnel, current source-key enrollment, adversarial invalid/expired/replayed signed packets, independent receipt and rollback. Do not use the old Nov7 nonfinancial owner direction as a C08 funded ratification or any C09 transaction permit.

This is **nonfunded infrastructure**. All C01–C09 remain HARD HOLD until original physical gate receipts pass; no financial release authorization.
