# WOLO Osmosis Pool Launch Plan

Status: planning packet only. Do not execute IBC, pool creation, or liquidity transactions from this document alone.

## Target

Create the first WOLO/USDC pool on Osmosis after WoloChain mainnet IBC is safely wired.

## Launch Price

Target initial price:

```txt
1 WOLO = 0.0001 USDC
```

Equivalent ratios:

```txt
10,000 WOLO = 1 USDC
100,000 WOLO = 10 USDC
200,000 WOLO = 20 USDC
100,000,000 WOLO = 10,000 USDC implied FDV
```

## Initial Pool Size

```txt
WOLO liquidity: 200,000 WOLO
USDC liquidity: 20 USDC
Pool creation fee budget: 20 USDC
Total USDC budget: 40 USDC
```

Base-unit WOLO amount:

```txt
200,000 WOLO = 200000000000uwolo
```

## Funding Source

WOLO should come from:

```txt
WOLO DEX Liquidity Reserve
```

Genesis allocation address:

```txt
wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en
```

USDC should come from Tony's Osmosis wallet.

## Required Before Pool Creation

- WoloChain mainnet `wolo-1` remains healthy.
- Public RPC remains live:
  - `https://rpc-mainnet.aoe2war.com/status`
- Public REST remains live:
  - `https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info`
- Osmosis wallet has at least:
  - `40 USDC`
  - enough OSMO for gas
- IBC path WoloChain ↔ Osmosis is created and verified.
- WOLO is transferred to Osmosis.
- Osmosis-side WOLO denom trace is recorded.
- Test transfer is proven before the 200,000 WOLO transfer.
- Pool is created only after denom trace and wallet balances are verified.

## Execution Sequence

1. Verify WoloChain mainnet health.
2. Verify Osmosis wallet address.
3. Create or verify IBC connection/channel.
4. Send tiny test transfer from WoloChain to Osmosis.
5. Confirm WOLO arrives on Osmosis.
6. Record Osmosis-side WOLO IBC denom.
7. Send 200,000 WOLO to Osmosis.
8. Confirm Osmosis wallet has:
   - 200,000 WOLO
   - 40+ USDC
   - OSMO gas
9. Create WOLO/USDC pool at:
   - 200,000 WOLO
   - 20 USDC
10. Confirm visible price:
   - `1 WOLO = $0.0001`
11. Screenshot Osmosis pool.
12. Announce launch.

## Hard Stop Rules

- Do not use testnet channels.
- Do not use `wolo-testnet`.
- Do not transfer from Founder Cold.
- Do not transfer from Community Treasury.
- Do not create pool at wrong ratio.
- Do not create pool before Osmosis-side WOLO denom trace is verified.
- Do not add more liquidity until first pool is visible and confirmed.

## Launch Line

```txt
WOLO is live on Osmosis at $0.0001.
100M fixed supply. Built for AoE2War.
```

## Codex Mission Later

Safely establish WoloChain mainnet `wolo-1` ↔ Osmosis IBC, verify the channel and denom trace, perform a tiny WOLO test transfer to Osmosis, then prepare the 200,000 WOLO / 20 USDC Osmosis pool launch. Stop before irreversible pool creation unless Tony explicitly confirms.
