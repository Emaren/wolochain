---
id: "aoe2war.wolochain.ibc-recon-summary"
title: "WoloChain Mainnet IBC Recon Summary"
type: "historical"
status: "historical"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "historical-evidence"
authority: "pre-ibc-reconnaissance-evidence"
reviewed_at: "2026-08-10"
review_interval_days: 0
sensitivity: "internal"
---

# WoloChain Mainnet IBC Recon Summary

Status: read-only reconnaissance summary. No IBC path, transfer, or pool was created by this recon.

## Confirmed Wolo Mainnet State

- Chain ID: wolo-1
- Node ID: de5830b2fabca2657b5da258b5e7917d354778ce
- Mainnet service: wolochaind-mainnet.service
- Health timer: wolo-mainnet-health.timer
- Latest observed height during recon: 764
- catching_up: False
- Validator voting power: 1000

## Confirmed Hermes / Relayer State

Hermes is installed:

- Binary: /usr/local/bin/hermes
- Version: hermes 1.13.2+bab3b80

The existing running Hermes process is TokenChain-specific:

- /usr/local/bin/hermes --config /etc/tokenchain/hermes.toml start

Existing relayer service:

- tokenchain-relayer.service

Existing bootstrap service:

- tokenchain-osmo-ibc-bootstrap.service

These are TokenChain/Osmosis testnet-oriented and must not be overwritten or casually reused for WoloChain mainnet.

## Likely Existing Hermes Configs

Important paths found:

- /etc/tokenchain/hermes.toml
- /var/www/tokenchain-ops/relayer/hermes-config.toml

Recommendation:

Create a separate WoloChain mainnet Hermes config/service rather than modifying the live TokenChain relayer in place.

## Wolo Mainnet IBC State

Observed Wolo mainnet IBC state:

- client_states: []
- channels: []

Only localhost connection exists:

- connection-localhost
- client_id: 09-localhost

Conclusion:

WoloChain mainnet has no external IBC client/connection/channel yet.

## Denom Trace Command Correction

The attempted command is not supported by this binary:

- wolochaind-mainnet query ibc-transfer denom-traces

Available ibc-transfer query subcommands include:

- denom
- denom-hash
- denoms
- escrow-address
- params
- total-escrow

Use this for future denom listing:

- /usr/local/bin/wolochaind-mainnet query ibc-transfer denoms --home /var/lib/wolochaind-mainnet --node http://127.0.0.1:27657 --output json

## Codex Guidance

Codex should:

1. Leave /etc/tokenchain/hermes.toml and tokenchain-relayer.service alone unless explicitly backing up and explaining changes.
2. Prefer a separate WoloChain mainnet relayer config and service.
3. Verify Osmosis endpoint and wallet before any transfer.
4. Create or verify WoloChain ↔ Osmosis IBC path only after explicit inspection.
5. Perform only a tiny WOLO test transfer first.
6. Record the Osmosis-side WOLO IBC denom.
7. Stop before transferring 200,000 WOLO.
8. Stop before creating the WOLO/USDC pool.
