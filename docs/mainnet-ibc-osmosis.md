---
id: "aoe2war.wolochain.mainnet-ibc-osmosis"
title: "WoloChain Mainnet IBC And Osmosis Plan"
type: "historical"
status: "historical"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "historical-evidence"
authority: "pre-ibc-osmosis-planning-evidence"
reviewed_at: "2026-08-10"
review_interval_days: 0
sensitivity: "internal"
---

# WoloChain Mainnet IBC And Osmosis Plan

This is a planning checklist only. Do not create IBC channels, start relayers, transfer liquidity, or create an Osmosis pool from this doc.

## Readiness Checklist

- `wolo-1` is live and producing blocks.
- Public RPC and REST endpoints are stable.
- Chain ID, denom metadata, and supply are verified.
- Fresh relayer wallet exists on WoloChain.
- Counterparty relayer wallet exists on Osmosis.
- Relayer seed material is backed up outside git.
- Mainnet endpoint health is monitored.
- Peer and seed topology is stable enough for relaying.
- Chain registry metadata is ready or staged.
- IBC module and transfer path are enabled and tested.

## Relayer Planning

Document before channel creation:

- relayer operator
- relayer software
- WoloChain RPC endpoint
- Osmosis RPC endpoint
- WoloChain relayer wallet address
- Osmosis relayer wallet address
- fee funding plan on both sides
- channel naming and memo conventions
- alerting for stuck packets and relayer balance

## Channel Planning

Channel creation must be done after mainnet is live and reviewed.

Record:

- WoloChain client ID
- Osmosis client ID
- WoloChain connection ID
- Osmosis connection ID
- WoloChain transfer channel ID
- Osmosis transfer channel ID
- counterparty versions
- relayer command history

## Asset Trace Expectations

Native WoloChain denom:

```text
uwolo
```

On Osmosis, transferred WOLO will appear as an IBC denom:

```text
ibc/<HASH>
```

The exact IBC denom hash depends on the final channel path. Do not hard-code it until the channel exists and the trace is verified.

## Osmosis Pool Plan

Planned initial pool, later:

- Pool type: 50/50 weighted pool
- Assets: `200000 WOLO` and `20 USDC`
- Swap fee: `0.2%`
- Starting implied price: `$0.0001` per WOLO

Base-unit planning:

- `200000 WOLO` = `200000000000uwolo`
- `20 USDC` depends on the selected USDC denom and decimals on Osmosis

Do not create this pool during mainnet prep. Create it only after:

- mainnet launch is complete
- IBC channel path is live
- WOLO IBC denom hash on Osmosis is verified
- USDC denom is selected and verified
- LP wallet custody is ready
- Tony explicitly approves pool creation

## Chain Registry And Osmosis Prep

Prepare but do not publish until mainnet launch facts are final:

- chain ID
- bech32 prefix
- denom metadata
- fees
- staking metadata
- RPC endpoints
- REST endpoints
- logo assets
- explorer URL
- peer and seed data if public
- IBC path data after channel creation
