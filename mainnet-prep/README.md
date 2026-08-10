---
id: "aoe2war.wolochain.mainnet-prep-readme"
title: "WoloChain wolo-1 Prep Templates"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "mainnet-prep-artifact-index"
reviewed_at: "2026-08-10"
review_interval_days: 60
sensitivity: "internal"
---

# WoloChain wolo-1 Prep Templates

This directory contains launch artifacts and current templates. Nothing here launches services, creates keys, edits nginx, creates IBC channels, or creates Osmosis liquidity by itself.

`wolo-1` is live. Use these files as reference material for the verified mainnet shape and for future service changes.

## Files

- `config/wolo-1-values.env.example`: shared reference values for mainnet.
- `config/wolo-1-node.env.example`: example node env file for `wolochaind-mainnet.service`.
- `config/wolo-1-settlement.env.example`: example settlement env file for `wolochain-mainnet-settlement.service`.
- `genesis/allocation-template.csv`: review scaffold for the `100000000 WOLO` allocation table.
- `genesis/README.md`: rules for turning the allocation table into fresh genesis later.
- `systemd/wolochaind-mainnet.service.example`: example node unit.
- `systemd/wolochain-mainnet-settlement.service.example`: example settlement unit.
- `nginx/README.md`: public endpoint proxy notes.
- `../scripts/render-mainnet-allocation.sh`: validates allocation math and writes a draft JSON summary under ignored `build/`.
- `../scripts/check-mainnet-genesis-readiness.sh`: emits a yes/no readiness report under ignored `build/`.

## Read-Only Helpers

Allocation renderer:

```bash
./scripts/render-mainnet-allocation.sh
```

Default output:

```text
build/mainnet-prep/allocation-draft.json
```

Genesis readiness checker:

```bash
./scripts/check-mainnet-genesis-readiness.sh
```

Default output:

```text
build/mainnet-prep/genesis-readiness-report.json
```

The allocation renderer checks math and writes a draft allocation JSON only. The genesis readiness checker reports `ready_for_genesis: true` or `false` only. Neither script creates final genesis, accounts, keys, wallets, services, or chain state.

## Safety Rules

- Do not reuse `wolo-testnet` chain state.
- Do not reuse testnet validator keys.
- Do not reuse testnet settlement signer keys.
- Do not copy `/var/lib/wolochaind-testnet`.
- Do not move `/mnt/HC_Volume_105319120/wolochain/settlement-state`.
- Do not regenerate or replace mainnet genesis from this directory without Tony's approval.
- Do not put mnemonics, private keys, auth tokens, or cert material in this directory.
