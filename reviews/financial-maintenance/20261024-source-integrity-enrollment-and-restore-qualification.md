---
id: "aoe2war.wolochain.financial-controller-source-integrity-and-enrollment-20261024"
title: "Financial controller source integrity and five-human enrollment — 2026-10-24"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war","aoe2dewarwagers"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "non-authorizing-financial-human-signature-review"
reviewed_at: "2026-10-24"
review_interval_days: 14
sensitivity: "internal"
---

# Financial controller source integrity and five-human enrollment — 2026-10-24

**Status: HARD HOLD.** This is the independently reviewable ceremony/qualification specification for stacked maintenance review branch. No human has enrolled, no live financial writer was fenced, no production backup or restore attempted, and no source/binary switched.

## P1 code drift — actual GitHub commit-graph proof and source-versus-runtime limits

Trusted repository compare: https://github.com/Emaren/wolochain/compare/78c25985420ee41a6678c42fab8ea8d6c3b1b519...4ce11c4965da64e3d4dee6a8681b6198e1aba1eb . GitHub compare explicitly reports **171 commits ahead, zero behind, 61 changed files**. No reverse changes. This **is not** proof that the *running* VPS binary corresponds to either commit: only the owner previously reported local VPS working tree as `78c25985420ee41a6678c42fab8ea8d6c3b1b519`; a fresh on-host source and running process inventory remains REQUIRED. The source graph includes `cmd/wolochaind/cmd/settlement.go` (147 lines added, 161 removed), `settlement_challenge.go`, new `settlement_confirmation.go`, `settlement_prebroadcast.go`, `settlement_receipt.go`, their tests, dual-service release/rollback scripts, financial settlement runbook and mainnet service configs. These changes affect custody-sensitive confirmation/credit/journal semantics. **P1 must NOT be reclassified as docs drift.** Current source, current running binary and intended settled-source candidate have three distinct proof obligations.

**Fresh VPS owner READ-ONLY command (no secrets, no restarts or permissions):**

```bash
ssh -T -o BatchMode=yes -o ConnectTimeout=10 root@hel1 'sh -se' <<'SH'
repo=/var/www/WoloChain-wolo-1
printf 'SOURCE_GIT_HEAD='
git -C "$repo" rev-parse HEAD
printf 'SOURCE_DIRTY_PATHS (names only, no content):\n'
git -C "$repo" status --porcelain --untracked-files=no |
  cut -c4- | sed -n '1,80p'
for unit in wolochaind-mainnet.service wolochain-mainnet-settlement.service wolochain-founder-rewards-settlement.service; do
  printf '\nUNIT=%s\n' "$unit"
  systemctl show --property=LoadState,ActiveState,MainPID,FragmentPath,DropInPaths "$unit"
  pid=$(systemctl show --property=MainPID --value "$unit")
  case "$pid" in
    ''|0|*[!0-9]*) echo RUNTIME_BINARY_HASH=UNAVAILABLE ;;
    *) if test -r "/proc/$pid/exe"; then
         sha256sum "/proc/$pid/exe" | awk '{print "RUNTIME_BINARY_SHA256="$1}'
       else echo RUNTIME_BINARY_HASH=UNAVAILABLE; fi ;;
  esac
done
printf '\nPINNED_SOURCE_PROOF_ONLY=NO_RUNTIME_RELEASE_AUTHORITY\n'
SH
```

Running-process SHA256 binds actual binary bytes but not source version without signed build provenance. A service drop-in may select a different binary from the unit's default ExecStart. Do not print environment variables or wallet/keyring contents. Obtain independent source-to-artifact provenance before considering a change; do NOT `git pull`, fast-forward, restart, stop 8092/8093 or replace binaries under this read-only audit.

### Controlled P1 disposition plan

1. Owner and chain reviewer independently record source Git HEAD, dirty-path names, actual process executable hashes, systemd selected binaries/drop-in hashes, settlement code source SHAs, durable request/journal hashes (names and sizes only in public), chain height and relevant bank state. Preserve original executable and state hash seals.
2. Code owner independently reviews the 61-file delta grouped by prebroadcast acceptance, confirmations, receipts, signer/fee semantics, schema, rollback, source drift and docs. Resolve whether the 171-commit baseline is a proposed release candidate vs actual running code. Ancestry is insufficient.
3. Witness conducts source-locked **disposable** old/new/old tests against *copied* offline state with original 8092/8093 and consensus completely untouched; verify no replay or live mutation, migration or symlink outside disposable workspace. Record deterministic inputs/outputs and independent reviewer.
4. Reviewer creates an immutable disposition manifest with `vps_source_sha`, `running_node_binary_sha256`, `running_primary_settlement_binary_sha256`, `running_founder_settlement_binary_sha256`, `candidate_git_sha`, `source_compare_171_sha256`, `signer_ownership_signed_evidence_sha256`, `rollback_proof_sha256`, `financial_go=false`, `p1_resolved=false`. Its exact digest, independently attested, may only then be promoted as the controller's source-bound trust anchor by a separately reviewed PR.
5. Any drift, unresolved request discrepancy, incomplete lineage or unknown signer => original P1 stays BLOCKED. No automatic deployment, rollback or `git pull` to clean up the report.

## Five actual human enrollments — never substitute CI keys

The five distinct human roles are **Owner, Operator, Chain Reviewer, Finance Reviewer, Recovery Witness**. Independently identify each natural person, assignment and conflicts; each generates/holds a private Ed25519 key under sole personal control, with no key material in GitHub, AI logs or the shared server. Only public keys, nonsecret key IDs, roles, enrolled version, expiry/revocation policy and signed proof-of-possession challenges enter the trust registry. A separately controlled enrollment custodian and independent auditor countersign the registry digest using their independent custody process. No single developer/operator may self-enroll all five.

An enrollment package for each actual person must include: `role`, externally witnessed `person_id`, `key_id`, Ed25519 `public_key_pem`, out-of-band key-control confirmation, identity-verifier name, UTC issuance/expiration, key revocation status and accepted purpose. The custodian confirms five distinct persons, five distinct keys and no controlled duplicates; source-pins `registry_sha256`, expected host identity, Wolo source commit and source-drift disposition digest in controller source. Real human signatures must bind that *exact* reviewed source and evidence; rotating the registry or key requires a **new reviewed source pin and new approvals**. Revoked IDs must fail under source-pinned `revoked_key_ids`. The current source anchors are intentionally `None`; production will refuse.

The external nonce witness MUST have an **independently hosted monotonic transactional ledger** with fresh online compare-and-consume of the exact signed packet digest/nonce/source/scope. A previous local signed receipt cannot prevent a privileged host rollback. PR #98's local O_EXCL/fsync nonce primitive is reused **after** external witness acceptance. Current production online consumer is intentionally NOT CONNECTED and refuses; no mock/CI callback is installed into the operational CLI.

## Independent 12-surface financial writer fence certification

The exact 18 unit systemd scope is 4 apps + 7 oneshot/timer pairs (see the preceding PR98 runbook). Before real capture each additional category must have a named owner AND a different independent reviewer, evidence digest and scoped no-run exclusion: HD web/API; DE web/API; seven timer/service pairs; PostgreSQL DBA; manual SQL/SSH; cron/user systemd; CI/deploy; 8092/8093 bearers; off-host wallet/chain signers; auxiliary settlement/indexers; Hasura secondary targets; legacy/DE manual execution. Unknown remote credentials or absent attestation => **NO-GO**. Never claim VPS cgroup observations exclude off-host wallet holders.

The signed `independent-writer-coverage.json` is a closed 12-surface digest-bound artifact; `excluded_during_window:true` is a five-signer witnessed declaration, NOT network-enforced proof of no external chain broadcast. Independent chain reviewer must also compare eventual chain receipts before any resume.

## HD+DE production-size recovery qualification — separate phase and same immutable source

**Known historical sizing only:** HD physical approximately 9.947 GiB, DE approximately 0.014 GiB at past observation; OS root previously had approximately 108.44 GiB available and designated restore scratch existed. These are stale observations, not capacity guarantees. The already allocated bounded OS-root ext4/loop recovery storage MUST be reused, not formatted, moved, mounted anew or deleted here.

1. Before an approved maintenance window, run source-only/nonmutating preflight: verify exact controller source/hash, currently allocated restore mount + backing identity (`--mode inspect-storage`), available ext4 bounded bytes, root reserve >=8 GiB, proposed total archive byte cap, pinned container image, and actual current HD+DE physical/census metadata under separately authorized **read-only** SQL. Refuse any unknown mount or accidental storage identity change. No copy from production yet.
2. Five genuine fresh signatures + online witness consumption authorize a single ≤30 minute `LIVE_CAPTURE`. Controller v2's candidate capture executes exactly existing `fence()` then existing `backup()` under one global lock and same bounded authority. Must first establish independent residual writer exclusion, correct systemd no-jobs/cgroup drain, exclusive Pg visibility and zero prepared xacts. Snapshot settlement state + both HD/DE `pg_dump` archives. Preserve HOLD and `INCOMPLETE` on failure/expiry. Duration and peak footprint must be independently measured in an authorized pre-window full-size rehearsal; cannot guess.
3. A separately signed and independently consumed `OFFLINE_VERIFY` window authorizes only network-none disposable disk-backed PGDATA and never live systemd/wallet mutation. Require exact old fence HOLD retained but do not reuse/renew its expired live authority. Verify actual HD+DE restored canonical row-count/full-row hashes, **all declared financial tables**, pg constraints, sequences and **index definitions, uniqueness, validity and readiness** (new source `indexes_sha256` fingerprint). Independently compare producer snapshots, archive checksum, PG major, restored original ownership/privileges where applicable and off-host unseal. No successful receipt until disposable container removal/scratch cleanup and window validity.
4. Qualified verified restore evidence does **NOT** authorize any resumption. A third freshly signed `RESUME` phase must independently verify full current chain effects, historical #8477, #889, pending obligations, DE obligations, protected bank balances and original unit prestate; the actual independent resume executor is NOT implemented, so production stays fenced/HOLD until a separate security review closes it.
5. Witness signs immutable receipts containing exact source commit, host, fence, capture/restore receipts, both Pg schema/row/constraint/sequence/index digests, chain/bank height, private store identity/capacity, source drift disposition, test durations, nonces and actual responsible human signatures. Register receipt hashes with a separate independent custodian. A synthetic test fixture may prove code but is NEVER a production-size qualification.

## Codex release sequencing

The original LIVE watcher website may undergo a **separate code-only release gate** without authorizing finance or chain writes. Funded War Satchel/Mecha Auto Bets and Wolo custody mainnet operations are **NO-GO** until the source-drift P1, all 12 writers and real five-human/nonce authority, full-size recovery, independent financial liability ceiling and bank solvency are actually certified. This runbook and its current code explicitly cannot declare operational GO.
