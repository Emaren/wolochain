---
id: "aoe2war.wolochain.documentation-control-plane"
title: "WoloChain Documentation Index"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "repository-documentation-index"
reviewed_at: "2026-08-10"
review_interval_days: 30
sensitivity: "internal"
---

# WoloChain Documentation Index

Repository ID: `wolochain`

Documentation owner: `wolochain-ops`

Implementation baseline: `wolo-1-mainnet-prep` at `d5dea8d6f1a2b0b57489a5e468dd21e34246891e`

The implementation baseline identifies the code commit described by this documentation. Documentation-only commits may follow it without creating a self-referential registry hash.

This page is generated from the validated front matter in this repository. Cross-system architecture, governance, and the unified portal live in the sibling `AoE2WAR-docs` control-plane repository.

## Documentation health

- Authoritative repository documents: **32**
- Path moves in this migration: **0**
- Every listed document has an explicit owner, lifecycle, authority, and review interval.

### Types

- `historical`: 14
- `reference`: 14
- `runbook`: 2
- `working`: 2

### Lifecycle

- `active`: 16
- `draft`: 2
- `historical`: 14

## Documents

| Document | Type | Status | Authority |
| --- | --- | --- | --- |
| [WoloChain](../README.md) | `reference` | `active` | `chain-repository-entrypoint` |
| [WoloChain Branch Authority](BRANCH_AUTHORITY.md) | `reference` | `active` | `git-branch-authority-contract` |
| [WoloChain Mainnet Cutover Checklist](mainnet-cutover-checklist.md) | `historical` | `historical` | `mainnet-launch-cutover-evidence` |
| [WoloChain Mainnet Tony Decision Checklist](mainnet-decision-checklist.md) | `historical` | `historical` | `mainnet-launch-decision-evidence` |
| [WoloChain Mainnet DNS, Nginx, And TLS](mainnet-dns-nginx-tls.md) | `reference` | `active` | `mainnet-public-endpoint-routing` |
| [WoloChain Mainnet Genesis Allocation Template](mainnet-genesis-allocation-template.md) | `historical` | `historical` | `prelaunch-genesis-allocation-template` |
| [WoloChain Mainnet IBC And Osmosis Plan](mainnet-ibc-osmosis.md) | `historical` | `historical` | `pre-ibc-osmosis-planning-evidence` |
| [WoloChain Mainnet Keplr And Explorer Metadata](mainnet-keplr-explorer.md) | `reference` | `active` | `mainnet-wallet-registry-metadata` |
| [WoloChain Mainnet Launch Plan](mainnet-launch-plan.md) | `historical` | `historical` | `mainnet-launch-plan-evidence` |
| [WoloChain Mainnet Services And Ports](mainnet-services-and-ports.md) | `reference` | `active` | `mainnet-service-and-port-contract` |
| [WoloChain Mainnet Settlement Runbook](mainnet-settlement-runbook.md) | `runbook` | `active` | `mainnet-settlement-operations` |
| [WoloChain Mainnet Template Report](mainnet-template.md) | `historical` | `historical` | `mainnet-preparation-template-evidence` |
| [WoloChain Mainnet Wallet And Key Plan](mainnet-wallets.md) | `reference` | `active` | `mainnet-wallet-role-and-custody-map` |
| [Settlement Contracts](settlement-contracts/README.md) | `reference` | `active` | `machine-readable-settlement-contract-index` |
| [WoloChain Testnet Ops](testnet-ops.md) | `runbook` | `active` | `legacy-testnet-operations` |
| [AoE2WAR Warbound Trophies](warbound-trophies.md) | `working` | `draft` | `undeployed-warbound-module-design` |
| [Codex Mission: WoloChain Mainnet ↔ Osmosis IBC Prep](../mainnet-prep/CODEX_OSMOSIS_IBC_MISSION.md) | `historical` | `historical` | `ibc-mission-prompt-evidence` |
| [WoloChain Mainnet Osmosis Hermes Relayer Staging](../mainnet-prep/HERMES_OSMOSIS_RELAYER_STAGING.md) | `reference` | `active` | `ibc-relayer-operating-reference` |
| [WoloChain Mainnet IBC Recon Summary](../mainnet-prep/IBC_RECON_SUMMARY.md) | `historical` | `historical` | `pre-ibc-reconnaissance-evidence` |
| [WoloChain Mainnet Osmosis IBC Path Live](../mainnet-prep/IBC_WOLO_OSMOSIS_LIVE.md) | `reference` | `active` | `live-ibc-path-receipt` |
| [WoloChain wolo-1 Prep Templates](../mainnet-prep/README.md) | `reference` | `active` | `mainnet-prep-artifact-index` |
| [Relayer Keys and Funding Checklist](../mainnet-prep/RELAYER_KEYS_AND_FUNDING_CHECKLIST.md) | `historical` | `historical` | `relayer-key-funding-preparation-evidence` |
| [WoloChain wolo-1 Mainnet Prep Status](../mainnet-prep/STATUS.md) | `reference` | `active` | `mainnet-prep-chronological-handoff` |
| [WoloChain Mainnet → Osmosis Liquidity Transfer](../mainnet-prep/WOLO_OSMOSIS_LIQUIDITY_TRANSFER.md) | `historical` | `historical` | `liquidity-transfer-receipt` |
| [WOLO Osmosis Metadata Plan](../mainnet-prep/WOLO_OSMOSIS_METADATA_PLAN.md) | `working` | `draft` | `post-launch-osmosis-metadata-plan` |
| [WOLO Osmosis Pool Launch Plan](../mainnet-prep/WOLO_OSMOSIS_POOL_LAUNCH.md) | `historical` | `historical` | `pre-pool-launch-plan-evidence` |
| [WoloChain Mainnet → Osmosis Test Transfer](../mainnet-prep/WOLO_OSMOSIS_TEST_TRANSFER.md) | `historical` | `historical` | `ibc-test-transfer-receipt` |
| [WOLO/USDC Osmosis Pool](../mainnet-prep/WOLO_USDC_OSMOSIS_POOL_LIVE.md) | `reference` | `active` | `live-osmosis-pool-receipt` |
| [Mainnet Genesis Prep](../mainnet-prep/genesis/README.md) | `historical` | `historical` | `prelaunch-genesis-scaffold` |
| [WoloChain Mainnet Validator Gentx Checklist](../mainnet-prep/genesis/VALIDATOR_GENTX_CHECKLIST.md) | `historical` | `historical` | `prelaunch-validator-gentx-evidence` |
| [WoloChain Mainnet Nginx Notes](../mainnet-prep/nginx/README.md) | `reference` | `active` | `mainnet-nginx-routing-reference` |

## Canonical commands

```bash
python3 scripts/docs_v2_check.py
python3 scripts/docs_v2_check.py --write
python3 scripts/docs_v2_check.py --write --refresh-baseline
```

Use `--write` for documentation-only changes. Use `--refresh-baseline` only after intentional implementation changes, then review the generated index and registry before committing them.
