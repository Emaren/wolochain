# WoloChain Mainnet Template Report

This report is a planning template only. It must not be used to launch mainnet, reset testnet, clone validator state, or create liquidity.

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
- Public RPC route: `https://aoe2war.com/rpc/`
- Public REST route: `https://aoe2war.com/rest/`
- Public explorer route: `https://aoe2war.com/wolo-testnet`
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

## Recommended Future Mainnet Values

- Chain ID: `wolo-1`
- Base denom: `uwolo`
- Display denom: `wolo`
- Symbol: `WOLO`
- Decimals: `6`
- Address prefix: `wolo`
- Supply model: fixed supply, no silent inflation
- Chain home: separate mainnet home, not `/var/lib/wolochaind-testnet`
- Node service: separate mainnet systemd service, not `wolochaind-testnet.service`
- Settlement service: separate mainnet settlement service, not `wolochain-settlement.service`
- Ports: separate RPC, REST, P2P, and settlement ports from testnet
- Public endpoints: separate mainnet RPC, REST, and explorer URLs
- Validator keys: fresh mainnet validator keys
- Genesis: fresh mainnet genesis
- Allocations: fresh mainnet allocation table
- Balances: no automatic migration from `wolo-testnet`

The future mainnet should use WoloChain as the reference implementation, not as copied state. Do not reuse testnet validator keys, chain home, settlement state, or balances.

## Mainnet Blockers

- DNS plan for mainnet RPC, REST, explorer, seed, and any app-facing routes
- TLS certificates for the mainnet public routes
- Nginx config for separate mainnet ports and hosts
- Genesis allocation table
- Validator key generation and gentx workflow
- Explorer/Ping config for mainnet
- Keplr config for mainnet
- AoE2War endpoint switch plan
- IBC channel planning
- Relayer planning
- Osmosis and chain-registry prep
- WOLO/USDC pool creation later, not now

## Non-Goals

- Do not convert `wolo-testnet` into mainnet.
- Do not reset `wolo-testnet`.
- Do not clone testnet balances into mainnet.
- Do not reuse testnet validator keys.
- Do not create Osmosis liquidity during template hardening.
- Do not move AoE2 game, wager, faucet, premium, or growth logic into WoloChain.
