---
id: "aoe2war.wolochain.c06-intel-offhost-recovery-hostkey-hold"
title: "C06 Intel offhost receiver host identity — transport-only evidence"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-c06-hostkey-observation-no-backup-authority"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C06 Intel offhost receiver host identity — transport-only evidence

## Existing protected C06 enrollment

On November 7 the Intel Mac recovery receiver created a dedicated
outbound SSH reverse forward from its own SSH daemon to HEL1 loopback
127.0.0.1:22996. HEL1 preserved a root-owned, mode0600 enrollment
receipt with SHA256
3371c79a3728ebbadc9f186e9492313c2a5039aae9eee337b9c83dc816210562
at
/root/aoe2war-c06-transport-enrollment-20261107/c06-intel-physical-accepted.json.

That receipt explicitly states
PASS_C06_ONLY_TRANSPORT_PHYSICALLY_VERIFIED,
scope transport-only, the Intel ED25519 host-key fingerprint,
observed Intel launchd reconnect, and all of the following as false:
C03 global writer fence, C06 formal acceptance, C07 formal acceptance,
coherent joint HD/DE financial backup captured, and funded release.

Do not call this **C06 backup acceptance**. An SSH transport identity
check does not establish an authenticated login to Intel, independent
file custody, ciphertext transfer, a recovery-key decryption, actual
consistent HD/DE snapshots or an isolated same-capture restoration.

## Fresh HEL1 physical check, November 8

HEL1 loopback 22996 had an SSH2 banner. An exact remote
ssh-keyscan -t ed25519 for the 22996 endpoint, with the
SSH public-key blob SHA256 computed locally, matched the
**previously enrolled** Intel SSH host-key fingerprint.

The C08 witness reverse tunnel on HEL1 22995 was still absent
at that observation. C08 is independently controlled, uses a
separate dedicated Intel witness SSHD, and is not to be replaced
with the C06 receiver SSH tunnel.

The source-only observer
scripts/settlement_c06_intel_offhost_transport_identity_hold.py
requires root on the exact HEL1 host, an exact mode0600 root-owned
pre-enrollment file and its byte-exact SHA256, exact schema and
nonrelease status, live SSH2 banner, exact loopback port and
a SINGLE matching ED25519 SSH host fingerprint. Unknown key
algorithms, changed endpoints, malformed key blobs, duplicate
results or a forged C06/C07/financial PASS return STOP.

No client login or SSH command is sent to the Intel receiver.
No new keys are created. No backup is captured, encrypted,
transferred, restored, or deleted. No systemd, database, firewall
or financial service is changed.

Source SHA256:
bc3d98084d93ef18941af7a077cbe4449444a04edc5a334c93b20b1712f13bb0.

The exact source ran physically on HEL1, exited 3, and returned
HOLD_C06_TRANSPORT_HOST_IDENTITY_MATCHED_BACKUP_NOT_CAPTURED.
Private root0600 sealed source/evidence receipt SHA256:
2421949885cbca310276dffad939ae9aa2b0dc943178e8d4c8f035ca638b2b53.
Private evidence path:
/root/aoe2war-session-a-c06-identity-observer-20261108/physical-c06-offhost-identity-hold-20261108.json.
All 16 dedicated adversarial tests passed.

## Required C06/C07 closure, still outstanding

1. Complete approved C03 writer/service/reconnect/DB signer fencing,
   with read-only public website, protected 3030 fallback and native
   chain observation intact.
2. Enroll exact operator, custody/reviewer and independent receiver
   identities with verifiable root-of-trust (not plaintext keys).
3. Authenticate the receiver with a known authorized SSH client and
   an exact non-financial transfer/receipt capability. The server's
   host fingerprint alone is not sufficient.
4. Use separately approved, time-bounded coherent HD/DE,
   settlement/journal/native-state snapshot capture, encryption
   and offhost ciphertext proof with hash/size/WAL manifests.
5. Independently decrypt and restore the **same** sealed snapshot
   into a properly isolated no-network PG16/native test domain.
   Verify financial state and negative tamper/failure cases;
   do not restore over live production.
6. Preserve all previous good recovery points, complete all
   C01-C09 acceptance dependencies and require fresh
   transaction-specific human authorization for any funded move.

No step in this source observer grants permission for the next step.
Formal C06/C07 and funded WOLO remain HARD HOLD.
