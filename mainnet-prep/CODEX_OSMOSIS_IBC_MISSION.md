# Codex Mission: WoloChain Mainnet ↔ Osmosis IBC Prep

Status: mission prompt only. Do not execute irreversible transactions from this document alone.

## Context

WoloChain mainnet is live.

Current confirmed state:

- Chain ID: `wolo-1`
- RPC: `https://rpc-mainnet.aoe2war.com/status`
- REST: `https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info`
- Validator moniker: `wolo-mainnet-hel1`
- Mainnet node service: `wolochaind-mainnet.service`
- Mainnet health timer: `wolo-mainnet-health.timer`
- AoE2War `/wolo` is mainnet-facing
- `/wolo-1` redirects to `/wolo`

Target Osmosis pool is documented in:

```txt
mainnet-prep/WOLO_OSMOSIS_POOL_LAUNCH.md
```

## Mission

Safely inspect, prepare, and verify the WoloChain mainnet `wolo-1` ↔ Osmosis IBC path.

Do not create liquidity yet.

Do not create the WOLO/USDC pool yet.

Do not perform the 200,000 WOLO transfer yet unless Tony explicitly confirms after the test transfer and denom trace are verified.

## Desired End State Before Final Confirmation

Codex should stop with:

1. WoloChain mainnet health verified.
2. Osmosis target wallet verified.
3. Existing relayer/IBC state inspected.
4. No testnet channels reused.
5. WoloChain ↔ Osmosis IBC path created or confirmed safe.
6. Tiny WOLO test transfer completed only if safe.
7. Osmosis-side WOLO IBC denom trace recorded.
8. Clear command prepared for the later 200,000 WOLO transfer.
9. Clear command prepared for later WOLO/USDC pool creation.
10. Stop before irreversible pool creation unless Tony confirms.

## Pool Target Later

```txt
WOLO liquidity: 200,000 WOLO
WOLO base amount: 200000000000uwolo
USDC liquidity: 20 USDC
Pool fee budget: 20 USDC
Total USDC budget: 40 USDC
Initial price: 1 WOLO = 0.0001 USDC
```

## Funding Source

WOLO source:

```txt
WOLO DEX Liquidity Reserve
wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en
```

USDC source:

```txt
Tony's Osmosis wallet
```

## Hard Stop Rules

- Do not touch `wolo-testnet`.
- Do not reuse testnet IBC channels.
- Do not create Osmosis liquidity yet.
- Do not create the WOLO/USDC pool yet.
- Do not transfer 200,000 WOLO yet.
- Do not transfer from Founder Cold.
- Do not transfer from Community Treasury.
- Do not overwrite existing relayer configs without backup.
- Do not stop existing TokenChain relayer services without explicit reason.
- Do not break the running WoloChain mainnet service.
- Do not expose mnemonics.
- Do not create new wallets unless explicitly needed and explained.
- Do not use keyring backend `test` for production mainnet custody.
- Stop if any chain ID, channel, denom, wallet, or endpoint is ambiguous.

## Required First Checks

Run checks equivalent to:

```bash
systemctl is-active wolochaind-mainnet.service
systemctl is-active wolo-mainnet-health.timer
curl -fsS https://rpc-mainnet.aoe2war.com/status
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
```

Confirm:

- network is `wolo-1`
- catching_up is false
- block height is increasing
- validator voting power is non-zero

## Required Inspection Areas

Inspect:

- Hermes / relayer installation
- existing relayer service units
- existing TokenChain/Osmosis relayer configs
- current Osmosis RPC/REST endpoints
- WoloChain mainnet RPC/REST endpoints
- any existing IBC clients/connections/channels
- firewall / ports if relevant
- chain registry style metadata if needed

## Required Output From Codex

Codex must report:

- files changed
- services touched
- backups created
- commands run
- IBC client IDs
- connection IDs
- channel IDs
- transfer port/channel
- Osmosis-side WOLO denom trace
- test transfer tx hash
- source and destination wallets
- final blockers
- whether it stopped before pool creation

## Final Stop Point

Stop after the tiny test transfer and denom trace verification.

Then ask Tony before:

1. transferring 200,000 WOLO to Osmosis
2. creating the WOLO/USDC pool
3. spending the 20 USDC pool fee
4. announcing live liquidity
