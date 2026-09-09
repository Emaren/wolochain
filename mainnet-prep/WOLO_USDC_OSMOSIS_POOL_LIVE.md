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
reviewed_at: "2026-09-09"
review_interval_days: 30
sensitivity: "public"
---

# WOLO/USDC Osmosis Pool

Status: live. The launch amounts below are historical creation receipts, not
fixed current reserves.

## Review Renewal — 2026-09-09 UTC

A read-only Osmosis LCD query reconfirmed Pool `3461`, the documented pool
address, `0.2%` swap fee, and both expected IBC denoms. Point-in-time reserves at
the review observation were `22.007451 USDC` and `181,872.725700 WOLO`, showing
normal movement from launch liquidity. No swap, liquidity change, or chain
mutation was performed by the review.

## Pool

- Pool ID: `3461`
- Pool URL: `https://app.osmosis.zone/pool/3461`
- Pool address: `osmo1kt0m5gfjunhgd2z7emnqqejrygwcuw7h5w39rqtq3ykzc55m09nqyzt5yj`
- Swap fee: `0.2%`
- Exit fee: `0%`

## Assets

### USDC

- Denom: `ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4`
- Launch pool amount: `20000000`
- Launch display amount: `20 USDC`

### WOLO

- Denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`
- Trace: `transfer/channel-110224/uwolo`
- Launch pool amount: `200000000000`
- Launch display amount: `200,000 WOLO`

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
