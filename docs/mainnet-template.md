# WoloChain Testnet/Mainnet Alignment Notes

This doc is a boundary checklist for keeping `wolo-testnet` useful without leaking testnet copy, endpoints, balances, or assumptions into the live AoE2WAR mainnet app. It must not be used to launch or modify mainnet, reset testnet, clone validator state, move funds, alter relayer config, or create liquidity.

## What Testnet Owns

The WoloChain testnet owns chain-development and integration proof work only:

- validating WoloChain code, scripts, settlement surfaces, and operator runbooks
- exercising fixed-supply `uwolo` accounting and `wolo` display metadata before mainnet-facing changes
- supporting local and VPS testnet RPC, REST, explorer, and settlement checks
- providing testnet-only faucet and bootstrap flows
- proving app-facing balance/status/settlement primitives before AoE2WAR mainnet consumes equivalent mainnet surfaces

Testnet does not own live app value, mainnet liquidity claims, mainnet wallet onboarding copy, production faucet policy, or AoE2WAR user-facing economic language.

## What Mainnet Owns

The live mainnet surface is separate chain and product truth:

- Chain ID: `wolo-1`
- Public app route: `https://aoe2war.com/wolo`
- Mainnet WOLO/USDC Osmosis pool: `#3461`
- Mainnet pool URL: `https://app.osmosis.zone/pool/3461`
- Mainnet endpoints, explorer routes, Keplr config, relayer config, validator state, and liquidity status

The mainnet app may share WOLO concepts with testnet, but it must not inherit testnet endpoints, faucet language, test balances, operator caveats, or pool placeholders.

## Confirmed Testnet Values

- Chain ID: `wolo-testnet`
- Chain name: `WoloChain`
- Binary: `wolochaind`
- Base denom: `uwolo`
- Display denom: `wolo`
- Symbol: `WOLO`
- Decimals: `6`
- Address prefix: `wolo`
- Fixed supply: `100000000000000uwolo` / `100000000 WOLO`
- Mint inflation: `0`
- Local RPC: `127.0.0.1:26657`
- Local REST: `127.0.0.1:1317`
- Local settlement API: `127.0.0.1:8091`
- P2P: `*:26656`
- Public testnet RPC route: `https://aoe2war.com/rpc/`
- Public testnet REST route: `https://aoe2war.com/rest/`
- Public testnet explorer route: `https://aoe2war.com/wolo-testnet`
- Node service: `wolochaind-testnet.service`
- Settlement service: `wolochain-settlement.service`
- Repo path on VPS: `/var/www/WoloChain`
- Binary path on VPS: `/var/www/WoloChain/build/wolochaind`
- Binary build metadata seen on May 24, 2026: `server_name=<appd>`, `version=""`, `commit=""`, `cosmos_sdk_version=v0.53.3`, `go1.24.0 linux/amd64`
- Chain home: `/var/lib/wolochaind-testnet`
- Mounted volume: `/mnt/HC_Volume_105319120`
- Build cache: `/mnt/HC_Volume_105319120/wolochain/go-cache`
- Build temp: `/mnt/HC_Volume_105319120/wolochain/go-tmp`
- Settlement/operator state: `/mnt/HC_Volume_105319120/wolochain/settlement-state`

The testnet settlement state is operator truth for request and grouped-run history. Back it up before risky settlement work. Do not move it without stopping mapped services and verifying ownership and endpoints afterward.

## What Must Stay Aligned

These concepts should remain consistent across testnet, mainnet, docs, and app integrations where appropriate:

- Base denom concept: micro-WOLO is `uwolo`
- Display denom concept: user-facing WOLO is `wolo`
- Symbol and decimals: `WOLO`, `6`
- Bech32 account prefix: `wolo`
- Wallet UX assumptions that depend on denom metadata, address prefix, and display precision
- Fixed-supply philosophy: no silent inflation, hidden mint behavior, or casual burn mechanics
- Settlement proof concepts, after endpoint and chain ID are explicitly switched to the target environment

## What Must Stay Separate

These must not be copied from testnet into mainnet without an explicit mainnet-specific review:

- Chain ID: testnet remains `wolo-testnet`; mainnet remains `wolo-1`
- RPC, REST, P2P, settlement, seed, and public proof endpoints
- Explorer URLs and Ping/static chain config
- Faucet behavior, faucet eligibility, growth buckets, and local faucet copy
- Pool/liquidity status, Osmosis copy, price, live-value, market cap, or FDV language
- Keplr config snippets, especially `chainId`, `rpc`, `rest`, `stakeCurrency`, and `currencies`
- Relayer config, IBC channel IDs, counterparty IDs, and packet paths
- Validator keys, keyring backend assumptions, homes, systemd service names, and mounted storage paths
- Genesis, allocation tables, balances, snapshots, local validator state, and settlement operator state
- App copy for AoE2WAR betting, premium, faucet, refund, entitlement, and growth flows

## What Must Not Be Copied To Mainnet

- Testnet chain ID, endpoints, explorer route, service names, chain home, validator state, or settlement state
- Any faucet wording that suggests free or test WOLO exists on mainnet
- Any testnet balance, local snapshot, generated address file, or operator caveat
- Any statement that `wolo-testnet` has the mainnet Osmosis pool, liquidity, live price, FDV, or app value
- Any `aoe2war.com/wolo-testnet` route as the live app destination
- Any example Keplr or explorer config that still names `wolo-testnet`

## Mainnet Reference Only

When this repo mentions mainnet, it is documenting separation, not operating mainnet. Mainnet facts that may be referenced for alignment are:

- `wolo-1` is the mainnet chain ID.
- `https://aoe2war.com/wolo` is the public mainnet app route.
- Osmosis pool `#3461` is the mainnet WOLO/USDC pool.
- `https://app.osmosis.zone/pool/3461` is the mainnet pool URL.

Do not use this testnet repo to change those resources. Update AoE2WAR, explorer, relayer, or mainnet operational repositories directly when the real mainnet surface changes.

## Non-Goals

- Do not convert `wolo-testnet` into mainnet.
- Do not reset `wolo-testnet`.
- Do not clone testnet balances into mainnet.
- Do not reuse testnet validator keys.
- Do not create, seed, or promise Osmosis liquidity from testnet docs or scripts.
- Do not move AoE2 game, wager, faucet, premium, or growth logic into WoloChain.
