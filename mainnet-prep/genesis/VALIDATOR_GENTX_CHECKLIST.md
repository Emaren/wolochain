---
id: "aoe2war.wolochain.validator-gentx-checklist"
title: "WoloChain Mainnet Validator Gentx Checklist"
type: "historical"
status: "historical"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "historical-evidence"
authority: "prelaunch-validator-gentx-evidence"
reviewed_at: "2026-08-10"
review_interval_days: 0
sensitivity: "internal"
---

# WoloChain Mainnet Validator Gentx Checklist

Status: planning only. No validator keys have been created by this prep package.

## Current state

- Chain ID: `wolo-1`
- Draft chain home exists only under ignored `build/mainnet-prep/wolo-1-home`
- Draft genesis validates structurally
- Allocation total is exactly `100000000000000uwolo`
- Mainnet has not been launched
- No final genesis has been installed
- No validator gentx has been created
- `wolo-testnet` has not been touched

## Decision

Create the real mainnet validator key on the launch host, not casually on the Mac.

Recommended launch-host values:

- Mainnet validator key name: `validatorops`
- Mainnet node home: `/var/lib/wolochaind-mainnet`
- Chain ID: `wolo-1`
- Bond denom: `uwolo`
- Suggested initial self-delegation: `1000000000uwolo` / `1,000 WOLO`
- Validator source wallet/bucket: `WOLO Validator Ops`
- Validator allocation address: see `mainnet-prep/genesis/allocation-template.csv`

## Why not create the validator key yet?

The validator key is operational identity. It should be created deliberately on the machine that will run the mainnet validator, or moved there using a deliberate key-transfer procedure.

This prep package can generate draft allocation genesis safely, but final validator gentx belongs to the explicit launch step.

## Future launch-only steps

Do not run these until the launch prompt says so:

1. Build/version the mainnet binary.
2. Create or prepare `/var/lib/wolochaind-mainnet`.
3. Create/import the `validatorops` key using production keyring backend.
4. Initialize `wolo-1`.
5. Apply the reviewed genesis allocation.
6. Generate gentx:

   ```bash
   wolochaind genesis gentx validatorops 1000000000uwolo \
     --chain-id wolo-1 \
     --home /var/lib/wolochaind-mainnet \
     --keyring-backend os

7. Collect gentxs.
8. Validate final genesis.
9. Only then install services and start mainnet.

## Hard stop rules

- Do not reuse testnet validator keys.
- Do not use `/var/lib/wolochaind-testnet`.
- Do not use `wolo-testnet`.
- Do not use keyring backend `test` for production mainnet.
- Do not launch before DNS/TLS/nginx/service files are reviewed.
