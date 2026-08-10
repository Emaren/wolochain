---
id: "aoe2war.wolochain.mainnet-decision-checklist"
title: "WoloChain Mainnet Tony Decision Checklist"
type: "historical"
status: "historical"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "historical-evidence"
authority: "mainnet-launch-decision-evidence"
reviewed_at: "2026-08-10"
review_interval_days: 0
sensitivity: "internal"
---

# WoloChain Mainnet Tony Decision Checklist

This checklist began as launch planning context. `wolo-1` is now live; use it for historical decisions, not as the current endpoint or deployment source of truth.

Recommended posture: decide the irreversible identity and custody questions early, defer public launch and liquidity questions until the chain has been generated and verified, and keep `wolo-testnet` untouched throughout.

## Must Decide Before Creating Mainnet Branch

These decisions shape the prep branch and should be settled before creating `/Users/tonyblum/projects/WoloChain-wolo-1`.

| Decision | Recommended Default | Notes |
| --- | --- | --- |
| Mainnet chain ID | `wolo-1` | Keep `wolo-testnet` unchanged. |
| Denom metadata | `uwolo` / `wolo` / `WOLO` / `6` | Same asset identity, fresh chain state. |
| Address prefix | `wolo` | Mainnet user addresses remain `wolo1...`. |
| Prep clone path | `/Users/tonyblum/projects/WoloChain-wolo-1` | Do not create until explicitly requested. |
| Prep branch | `wolo-1-mainnet-prep` | Mainnet-only scripts/config live in the prep clone. |
| Architecture rule | clone architecture, not state | No testnet DB, validator key, home, balance, or genesis copy. |
| Service names | `wolochaind-mainnet.service`, `wolochain-mainnet-settlement.service` | Clear split from testnet units. |
| Chain home | `/var/lib/wolochaind-mainnet` | Never `/var/lib/wolochaind-testnet`. |
| Port plan | P2P `27656`, RPC `27657`, REST `1318`, settlement `8092` | Non-conflicting with testnet. |
| Endpoint style | dedicated subdomains | Prefer wallet/relayer-friendly origins over path rewrites. |
| Public endpoints | `rpc-mainnet.aoe2war.com`, `rest-mainnet.aoe2war.com` | Verified live on June 1, 2026. A separate mainnet explorer route is not verified yet. |
| Day-one settlement posture | prepare infra, delay app cutover | Run chain first; cut over production settlement after observation. |
| Binary isolation | prefer versioned mainnet binary path | Avoid coupling testnet and mainnet restarts during launch. |

## Must Decide Before Genesis

These decisions become chain state or key custody and are expensive or impossible to undo cleanly.

| Decision | Recommended Default | Notes |
| --- | --- | --- |
| Final allocation table | use the template as review scaffold, not truth | Must sum to `100000000000000uwolo`. |
| Validator self-delegation | choose from operator/validator reserve | Placeholder only; Tony must approve exact amount. |
| Validator/operator wallet | fresh mainnet key | Never reuse testnet validator/operator key material. |
| Consensus key flow | fresh mainnet init/gentx flow | Do not copy testnet `priv_validator_key.json`. |
| Treasury custody | cold or multisig | Must be backed up and restore-tested before genesis. |
| Rewards custody | cold/multisig plus controlled distributor if needed | App logic stays outside WoloChain. |
| Watcher/player reward funding | genesis bucket or later treasury transfer | Eligibility remains app-owned. |
| Settlement payout signer funding | fund only if day-one settlement is needed | Otherwise fund later from treasury. |
| Escrow signer funding | fund only if escrow settlement is needed | Must be separate from payout signer. |
| Relayer wallet | create later unless IBC is immediate | Usually not needed in genesis. |
| Osmosis LP wallet | cold wallet, funded by liquidity bucket or later transfer | Do not send funds to Osmosis before IBC approval. |
| Emergency reserve | cold or multisig | Should be separate from treasury if Tony wants blast-radius control. |
| Keyring backend | production backend, not `test` | `os` is the current documented default. |

## Must Decide Before Public Launch

These decisions gate external users, wallets, explorers, and app integrations.

| Decision | Recommended Default | Notes |
| --- | --- | --- |
| DNS records | create dedicated subdomains | Verify they resolve before certbot. |
| TLS cert names | one cert covering all mainnet subdomains if convenient | Record certbot names in launch notes. |
| Nginx routing | subdomain server blocks to mainnet ports | Never proxy mainnet endpoints to testnet ports. |
| Explorer config | separate mainnet Ping/pub config | Do not overwrite testnet config. |
| Keplr metadata | use `wolo-1` values from Keplr doc | Add `ibc-transfer` only after IBC readiness. |
| Public smoke acceptance | endpoints must report `wolo-1` | Reject anything reporting `wolo-testnet`. |
| Settlement service public readiness | operator-only until dry-run and alerts pass | Keep auth token enabled. |
| AoE2War endpoint switch | separate app cutover plan | Do not move app business logic into WoloChain. |
| Monitoring | endpoint, service, storage, and hot-wallet alerts | Required before production settlement traffic. |
| Backup/restore proof | restore-tested wallets and operator state | Especially treasury, validator, payout, escrow. |

## Can Decide After Launch

These decisions can wait until the chain is stable.

| Decision | Recommended Default | Notes |
| --- | --- | --- |
| IBC channel creation | after public chain stability | Do not create during launch prep. |
| Relayer operator and software | decide during IBC phase | Needs WoloChain and Osmosis fee funding. |
| Chain registry publication | after public endpoint facts are final | Include IBC data only after channel creation. |
| Osmosis pool creation | later, explicit Tony approval | Planned pool is `200000 WOLO` + `20 USDC`, 50/50, `0.2%`. |
| WOLO IBC denom hash | after channel exists | Do not hard-code before trace verification. |
| USDC denom choice | during Osmosis prep | Verify decimals and source. |
| AoE2War full production settlement switch | after observation window | Start with read-only wallet/explorer visibility if desired. |
| Additional validators or peers | after first stable launch | Avoid expanding blast radius too early. |
| Governance parameter tuning | after launch observations | Keep denom and fixed-supply invariants stable. |

## Safety Summary

- Mainnet is a new chain, not a testnet conversion.
- Testnet balances do not migrate automatically.
- Testnet keys are never reused.
- Testnet chain home is never reused.
- Testnet settlement state is never moved into mainnet.
- IBC and Osmosis happen after launch, not during branch prep.
