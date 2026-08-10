---
id: "aoe2war.wolochain.osmosis-pool-live"
title: "WOLO/USDC Osmosis Pool"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "runtime-evidence"
authority: "live-osmosis-pool-receipt"
reviewed_at: "2026-08-10"
review_interval_days: 30
sensitivity: "public"
---

# WOLO/USDC Osmosis Pool

Status: live.

## Pool

- Pool ID: `3461`
- Pool URL: `https://app.osmosis.zone/pool/3461`
- Pool address: `osmo1kt0m5gfjunhgd2z7emnqqejrygwcuw7h5w39rqtq3ykzc55m09nqyzt5yj`
- Swap fee: `0.2%`
- Exit fee: `0%`

## Assets

### USDC

- Denom: `ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4`
- Pool amount: `20000000`
- Display amount: `20 USDC`

### WOLO

- Denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`
- Trace: `transfer/channel-110224/uwolo`
- Pool amount: `200000000000`
- Display amount: `200,000 WOLO`

## Launch Price

- `20 USDC / 200,000 WOLO`
- `1 WOLO = 0.0001 USDC`
- `1 USDC = 10,000 WOLO`

## Safety Confirmations

- Pool uses WoloChain mainnet WOLO bridged to Osmosis.
- Pool uses USDC, not OSMO.
- Pool uses the confirmed WOLO Osmosis IBC denom.
- Pool does not use WoloChain testnet WOLO.
- Liquidity came from the WOLO DEX Liquidity Reserve.
