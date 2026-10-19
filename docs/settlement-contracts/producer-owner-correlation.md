---
id: "aoe2war.wolochain.producer-owner-triage"
title: "HD and DE Financial Producer Owner Review"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war","aoe2dewarwagers"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "non-authorizing-financial-producer-evidence-correlation"
reviewed_at: "2026-10-19"
review_interval_days: 14
sensitivity: "internal"
---

# HD and DE Financial Producer Owner Review

## Non-authorizing contract

This runbook adds a **read-only source/runtime correlation report** to WoloChain's existing six-control financial release HOLD. The standalone `scripts/settlement_producer_owner_triage.py` does **not** access any service, database, signing key, wallet, network endpoint, or production checkout; it only reads three bounded sanitized JSON observations that an authorized operator has separately collected.

Inputs are (1) the established root-run `scripts/settlement-shared-producer-inventory-readonly.py --inspect` JSON, (2) the app-owned HD `scripts/aoe2_financial_producer_source_census.py` JSON, and (3) a DE web-source scan `scripts/settlement_de_producer_source_map.py --de-root <exact clean DE checkout> --check`. These observers are **not** trusted runtime financial attestations and have deliberate nonzero/noncertifying exit codes. No tool execution by itself grants a deployment approval.

The correlation tool uses `--runtime <file> --hd-source <file> --de-source <file>`, reads only regular bounded JSON files, rejects leaf symlinks, duplicate JSON keys and changed inodes, and prints a sanitized list of *public unit names* with owner-review classifications (HD/shared, DE or unknown). It will not emit financial environment names, values, signer locations or secrets present in the input. A runtime observation is labelled fresh only for a bounded one-hour window relative to UTC; future or invalid timestamps are stale. Duplicate, unknown, malformed or omitted units must be reviewed. The tool exits **3 even if all three inputs look valid**.

The report marks the following **false unconditionally**: deployed-source-to-running-executable parity, producer isolation, reconciled transfers, financial release, website release, and mutation of production. All input sources can be mutually consistent while independent HD/DE wallets, direct mnemonic and keyring paths, processes, HTTP/timer/cron ingress, and outstanding obligations remain unknown.

## First owner-review sequence

1. Obtain the current protected-systemd inventory through its existing audited root-read-only collector, without copying process environment values or shell command lines to public documents.
2. Verify the exact clean HD/DE source checkouts separately from their running service and build identities. Local Git HEAD alone cannot prove the running production build. Preserve a restricted raw receipt and publish sanitized summaries.
3. Correlate runtime units with HD and DE source edges, including **GET /api/lobby** → market ensure → settlement, DE faucet CLI, DE claim/admin payout, conditional payout mnemonic and staking signer fallback.
4. Have named HD, DE and external financial owners classify all discovered services/timers, independent signers, user managers, containers, cron, HTTP ingress, queued/in-flight/uncertain payments and expected restarts. An active unit is **not** automatically a producer; an inactive unit is **not** automatically safe.
5. Separately and explicitly approve a bounded coordinated fence/drain only after each producer authority and its restart paths are mapped. Do **not** blanket-stop app services, consensus, 8092 or 8093 based on this report.
6. Continue the other five financial controls: authenticated per-request outcomes, claim #889 continuing hold/disposition, quiesced state snapshots, paired settlement-only rollback rehearsal, and verified bank solvency with complete liability bound.

## Protected implementation boundaries

This is source evidence for WoloChain issue #5 and held financial-evidence PR #42. It is **not** a live Satchel or Auto Bets enabler, an authorization for the website-only lane, or a reason to change the documentation implementation baseline to the running VPS Git SHA. Source-only tests prove parsing/guard invariants, not independent chain or financial truth. All six controls continue in HOLD until accepted by the existing operator approval flow.
