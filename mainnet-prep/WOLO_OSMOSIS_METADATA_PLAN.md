# WOLO Osmosis Metadata Plan

Status: post-launch metadata planning only. Pool `3461` is live; this document does not require touching funds, relayers, services, genesis, validators, or chain state.

## Current Live State

- WOLO mainnet chain ID: `wolo-1`
- Base denom: `uwolo`
- Display denom: `wolo`
- Symbol: `WOLO`
- Decimals/exponent: `6`
- Bech32 prefix: `wolo`
- Fixed supply: `100,000,000 WOLO`
- Osmosis Pool ID: `3461`
- Pool URL: `https://app.osmosis.zone/pool/3461`
- Pool pair: `WOLO / USDC`
- Initial liquidity: `200,000 WOLO / 20 USDC`
- Launch price:
  - `1 WOLO = 0.0001 USDC`
  - `1 USDC = 10,000 WOLO`
- Launch FDV: `$10,000`
- Swap fee: `0.2%`
- Wolo transfer port: `transfer`
- Wolo source channel to Osmosis: `channel-0`
- Osmosis counterparty channel: `channel-110224`
- Osmosis trace: `transfer/channel-110224/uwolo`
- Osmosis WOLO IBC denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`
- Osmosis USDC denom: `ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4`

Current frontend display issue:

- Osmosis pool `3461` is live, but the Osmosis frontend may display WOLO as the raw `ibc/D091...` denom until asset metadata propagates.
- This is expected for a newly bridged asset before Chain Registry and Osmosis assetlist metadata are merged and generated into downstream interfaces.

## Required Metadata Work

Add WoloChain chain metadata:

- Chain name and chain ID:
  - `WoloChain`
  - `wolo-1`
- Bech32 prefix:
  - `wolo`
- Denom units:
  - base: `uwolo`
  - display: `wolo`
  - exponent: `6`
- Public endpoints:
  - RPC: `https://rpc-mainnet.aoe2war.com`
  - REST: `https://rest-mainnet.aoe2war.com`
- Recommended fee denom:
  - `uwolo`

Add WOLO asset metadata:

- Name: `WoloChain`
- Symbol: `WOLO`
- Base denom: `uwolo`
- Display denom: `wolo`
- Decimals/exponent: `6`
- Fixed supply: `100,000,000 WOLO`
- Primary use/context:
  - AoE2War mainnet token.

Add IBC path and denom metadata:

- Source chain: `wolo-1`
- Destination chain: `osmosis-1`
- Source port: `transfer`
- Source channel: `channel-0`
- Osmosis counterparty channel: `channel-110224`
- Osmosis trace: `transfer/channel-110224/uwolo`
- Osmosis WOLO IBC denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`

Add logo/icon metadata:

- Prepare a square WOLO logo asset suitable for Chain Registry.
- Prepare any Osmosis-compatible assetlist image references.
- Keep icon filenames and paths stable so generated assetlists can resolve them predictably.

Prepare Chain Registry PR later:

- Add WoloChain chain metadata.
- Add WoloChain asset metadata.
- Add the WoloChain to Osmosis IBC connection/channel metadata.
- Include logo assets and references.
- Verify denom trace and IBC hash before opening the PR.

Prepare Osmosis assetlists visibility path later:

- Osmosis assetlists use Cosmos Chain Registry as the source of truth during generated assetlist updates.
- After the Chain Registry metadata and IBC connection data are merged, the Osmosis assetlists generation path should be able to detect and display WOLO metadata.
- Do not create a second pool or move liquidity to work around missing frontend metadata.

## Immediate AoE2War Workaround

AoE2War `/wolo` should display WOLO cleanly using local known metadata instead of waiting for Osmosis metadata propagation.

Recommended app-side display:

- Headline: `WOLO is live on Osmosis`
- Launch price: `$0.0001`
- Pool: `#3461`
- Pair: `WOLO/USDC`
- Initial liquidity: `200,000 WOLO / 20 USDC`
- Fixed supply: `100,000,000 WOLO`
- Launch FDV: `$10,000`
- Primary link: `https://app.osmosis.zone/pool/3461`

AoE2War can include a compact technical note explaining that Osmosis may temporarily show WOLO as the raw IBC denom:

- WOLO denom on Osmosis: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`
- USDC denom on Osmosis: `ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4`

## Hard Safety Statement

- No additional liquidity is required for metadata polish.
- No new pool is required for metadata polish.
- No new IBC transfer is required for metadata polish.
- No relayer or service changes are required for metadata polish.
- Do not touch funds for this task.
- Do not run wallet commands for this task.
- Do not run transfer commands for this task.
- Do not alter genesis, validators, relayer config, or live chain state for this task.

## Next Metadata Step

Prepare a Chain Registry PR containing WoloChain chain metadata, WOLO asset metadata, logo assets, and the `wolo-1` to `osmosis-1` IBC path metadata. After that lands, follow the Osmosis assetlists generation/visibility path so Pool `3461` can display `WOLO` instead of the raw IBC denom.
