# WoloChain Mainnet Launch Plan

This is a planning document only. It does not launch mainnet, start a new chain, reset testnet, create IBC channels, or create Osmosis liquidity.

Mainnet must clone the WoloChain architecture, not the `wolo-testnet` state.

## Mission

Launch a separate future WoloChain mainnet for WOLO with clean chain identity, fresh operational keys, fresh genesis, fresh allocation decisions, and public infrastructure that does not depend on testnet state.

## Mainnet Identity

- Chain ID: `wolo-1`
- Chain name: `WoloChain`
- Binary: `wolochaind`
- Base denom: `uwolo`
- Display denom: `wolo`
- Symbol: `WOLO`
- Decimals: `6`
- Address prefix: `wolo`
- User addresses: `wolo1...`
- Supply target: `100000000000000uwolo` / `100000000 WOLO`
- Supply model: fixed supply, no silent inflation

Do not change the testnet identity while preparing mainnet. `wolo-testnet` remains the active testnet.

## Non-Negotiables

- Do not convert `wolo-testnet` into mainnet.
- Do not reset `wolo-testnet`.
- Do not reuse `/var/lib/wolochaind-testnet`.
- Do not reuse testnet validator private keys.
- Do not reuse testnet settlement signer keys.
- Do not copy testnet chain databases.
- Do not carry testnet balances into mainnet.
- Do not copy testnet genesis as-is.
- Do not move `/mnt/HC_Volume_105319120/wolochain/settlement-state`.
- Do not create IBC channels during planning.
- Do not create Osmosis liquidity during planning.
- Do not move AoE2 app, betting, faucet, growth, or entitlement logic into WoloChain.

## Launch Phases

### Phase 0: Review

- Review all docs in this package.
- Review [Tony's decision checklist](mainnet-decision-checklist.md).
- Freeze final mainnet identity.
- Confirm final wallet list and custody model.
- Confirm final allocation table.
- Confirm public endpoint naming.
- Confirm testnet remains live and separate.

### Phase 1: Prep Branch

Recommended local prep setup:

```bash
cd /Users/tonyblum/projects
git clone /Users/tonyblum/projects/WoloChain WoloChain-wolo-1
cd WoloChain-wolo-1
git checkout -b wolo-1-mainnet-prep
```

Alternative remote clone:

```bash
cd /Users/tonyblum/projects
git clone git@github.com:Emaren/wolochain.git WoloChain-wolo-1
cd WoloChain-wolo-1
git checkout -b wolo-1-mainnet-prep
```

Do not run either command until Tony explicitly asks for a separate prep clone.

### Phase 2: Mainnet Config Design

- Add mainnet-specific scripts or config only in the prep clone.
- Keep testnet scripts defaulting to `wolo-testnet`.
- Keep testnet ports and homes unchanged.
- Produce genesis from a fresh allocation table.
- Produce gentx from fresh validator keys.

### Phase 3: Host Prep

- Create a separate mainnet chain user or verify the service-user model.
- Create `/var/lib/wolochaind-mainnet`.
- Create a separate mainnet settlement state directory.
- Create separate env files.
- Create separate systemd services.
- Configure separate local ports.
- Do not start services until the final launch window.

### Phase 4: Public Surface Prep

- Create DNS for mainnet endpoints.
- Issue TLS certs for mainnet endpoints.
- Add nginx routes that proxy to mainnet ports.
- Keep testnet `/rpc/`, `/rest/`, and `/wolo-testnet` unchanged.
- Prepare Ping.pub and Keplr config separately from testnet config.

### Phase 5: Dry Verification

- Verify binary build.
- Verify generated genesis identity and supply.
- Verify generated genesis has no testnet chain ID.
- Verify no validator private key reuse.
- Verify no testnet balances were copied.
- Verify systemd units point at mainnet home, env files, and ports.
- Verify nginx routes point at mainnet ports.

### Phase 6: Launch Window

This phase is intentionally not performed by this planning package.

At launch time only, the operator would initialize mainnet, collect or create gentx, validate genesis, start mainnet services, and smoke public endpoints.

## Required Launch Inputs

- Final allocation table in `uwolo`.
- Fresh validator/operator mnemonic or key material, stored outside git.
- Fresh operational wallet mnemonics, stored outside git.
- Final service user and permissions model.
- Final port map.
- Final DNS names.
- Final TLS certificate names.
- Final Ping.pub chain config.
- Final Keplr metadata.
- Final AoE2War endpoint switch plan.
- IBC and Osmosis plan approved separately.

## Current Testnet Reference

- Chain ID: `wolo-testnet`
- Public RPC: `https://aoe2war.com/rpc/`
- Public REST: `https://aoe2war.com/rest/`
- Explorer: `https://aoe2war.com/wolo-testnet`
- Node service: `wolochaind-testnet.service`
- Settlement service: `wolochain-settlement.service`
- Chain home: `/var/lib/wolochaind-testnet`
- Settlement state: `/mnt/HC_Volume_105319120/wolochain/settlement-state`

Use this as a reference for architecture and checks only. Do not copy its runtime state into mainnet.
