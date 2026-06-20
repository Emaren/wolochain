# AoE2WAR Warbound Trophies

Status: local first implementation pass. This module is not deployed on `wolo-1`.

## Boundary

AoE2WAR remains the gameplay judge. It verifies replays, nationality, ELO, title-match eligibility, and winners. WoloChain only records the resulting trophy entitlement after an authorized Trophy Authority signs a transaction.

The chain does not parse replays, infer match rules, or decide who deserves a trophy.

## Existing `x/nft` audit

The repository already includes `cosmossdk.io/x/nft v0.1.0`.

| Surface | Finding |
| --- | --- |
| Dependency | Present in `go.mod`. |
| Module registration | Registered through depinject in `app/app_config.go`. |
| Keeper wiring | Constructed by the NFT module provider from its KV store, codec, account keeper, and bank keeper. The app did not previously expose it as a field. |
| Genesis | `nft` is in the runtime `InitGenesis` order and uses the standard NFT genesis state. |
| Module account | The `nft` module account exists and is bank-blocked. It has no minter/burner bank permissions because NFT minting does not mint WOLO. |
| Queries | gRPC/REST/AutoCLI expose `Balance`, `Owner`, `Supply`, `NFTs`, `NFT`, `Class`, and `Classes`. |
| Transactions | The only public NFT message is `cosmos.nft.v1beta1.MsgSend`. AutoCLI exposes `wolochaind tx nft send`. |
| Minting | The keeper has `SaveClass`, `Mint`, `Update`, `Burn`, and `Transfer`, and genesis can contain NFTs. There is no public standard `MsgMint`; a custom module must call the keeper to mint. |
| Transfers | A holder can sign `MsgSend`, and the standard message server transfers any NFT owned by that signer. |
| Warbound restriction | Standard `x/nft` has no class-specific non-transferable/soulbound policy. A wrapper that mints the NFT to a user can be bypassed through raw `MsgSend`. |

Conclusion: standard `x/nft` is useful for NFT storage and wallet/explorer compatibility, but it is not sufficient by itself for Warbound trophies.

Globally disabling `MsgSend` through `x/circuit` could block all NFT transfers, but that is a chain-wide operational policy rather than a class-level invariant. It would also prevent unrelated transferable NFTs. This pass does not rely on that switch.

## Chosen first-pass design

`x/wartrophy` is a state-backed authority module:

- collection/class convention: `aoe2war-war-trophies`
- stable trophy IDs use lowercase snake case
- lifecycle: `draft` -> `active` -> `retired`
- `mint` activates a registered chain trophy; it does **not** mint a holder-owned `x/nft` in this pass
- only the current Trophy Authority can register, mint, assign, reassign, update, retire, or rotate authority
- there is no holder-signed transfer message
- retirement clears the current owner, preserves transaction/event history, and cannot be reversed
- current ownership is the future tribute entitlement source
- economics fields are informational snapshots in this pass; no funds are held by the module

This deliberately favors correct Warbound ownership over premature wallet visibility. The app should report `state_backed`/`chain_backed`, not `nft_minted`, until an actual restricted NFT layer is implemented.

### First trophy IDs

- `canada_champion_belt`
- `usa_champion_belt`
- `mexico_champion_belt`
- `uk_champion_belt`
- `elite_champion_belt`

Recommended metadata:

- metadata: `https://aoe2war.com/api/trophies/{trophy_id}/metadata`
- external URL inside metadata: `https://aoe2war.com/trophies/{trophy_id}`

## Authority

The module app configuration defaults to the governance module account. A fresh genesis can instead configure a dedicated bech32 Trophy Authority address.

For an existing chain upgrade with no stored authority, the keeper safely falls back to the configured authority. If the default remains governance, rotate to the dedicated operational signer through an executed governance message after the upgrade.

Operational rules:

- use a dedicated app keyring/home, not the validator key
- do not hard-code a private key or mnemonic
- fund the authority only for transaction fees
- back up and document authority rotation
- AoE2WAR should submit idempotent jobs and store the tx hash plus emitted event

## Messages

- `MsgRegisterTrophy`
- `MsgMintTrophy`
- `MsgAssignTrophy`
- `MsgReassignTrophy`
- `MsgRetireTrophy`
- `MsgUpdateTrophyMetadata`
- `MsgSetTrophyAuthority`

All messages are authority-signed. There is intentionally no `MsgTransferTrophy`.

## Queries

- `QueryTrophy`
- `QueryTrophies`
- `QueryTrophyOwner`
- `QueryTrophiesByOwner`
- `QueryTrophyAuthority`

REST routes are under `/wolochain/wartrophy/v1`.

## Events

Successful mutations emit:

- `wartrophy.registered`
- `wartrophy.minted`
- `wartrophy.assigned`
- `wartrophy.reassigned`
- `wartrophy.retired`
- `wartrophy.metadata_updated`
- `wartrophy.authority_updated`

Failed transactions use normal Cosmos transaction errors. They do not emit misleading committed error events.

## Example local flow

The amounts below use `uwolo`; `10000000uwolo` is `10 WOLO`.

```bash
wolochaind tx wartrophy register \
  canada_champion_belt \
  "Canada Champion Belt" \
  "https://aoe2war.com/api/trophies/canada_champion_belt/metadata" \
  "https://aoe2war.com/images/trophies/canada_champion_belt.png" \
  10000000 \
  10000000 \
  --from trophy-authority \
  --chain-id localwolo

wolochaind tx wartrophy mint canada_champion_belt \
  --from trophy-authority \
  --chain-id localwolo

wolochaind tx wartrophy assign canada_champion_belt wolo1... \
  --from trophy-authority \
  --chain-id localwolo

wolochaind query wartrophy trophy canada_champion_belt
wolochaind query wartrophy owner canada_champion_belt
wolochaind query wartrophy owner-trophies wolo1...

wolochaind tx wartrophy reassign canada_champion_belt wolo1newwinner... \
  --from trophy-authority \
  --chain-id localwolo
```

Suggested end-to-end proof:

1. Register and mint the Canada belt.
2. Assign it to Emaren's Wolo address.
3. Register and mint the Mexico belt.
4. Assign it to Julio's Wolo address.
5. After an app-verified challenge, reassign the Mexico belt to the winner.
6. Confirm `wartrophy.reassigned`, query the new owner, and store the tx hash in `trophy_events`.

## Tribute and dethrone bounty

No custody or payout message is implemented in this pass.

Interim model:

- holder tribute is calculated by AoE2WAR from the active chain owner
- dethrone bounty accumulates per `trophy_id`, never per player
- the app-side trophy ledger and Trophy Rewards wallet remain the operational source of payout scheduling
- the existing WoloChain settlement service can execute explicit app-calculated payouts
- the UI must not call an amount an escrowed pool unless funds are actually reserved

Recommended policy is bounty growth equal to daily tribute, while keeping both fields independently versioned in the app.

A later chain-native design can add a module account plus fund/pay messages only after reserve rules, idempotency, payout failure recovery, and upgrade behavior are proven.

## Wallet-visible NFT follow-up

Do not mint `aoe2war-war-trophies` through standard `x/nft` to user addresses with the current code. The holder could immediately call `MsgSend`.

Safe future options require a separate reviewed upgrade:

1. add a chain-level NFT transfer policy hook that rejects `MsgSend` for the Warbound class while allowing `x/wartrophy` keeper moves;
2. fork/extend `x/nft` with class-level transfer policy and migration coverage; or
3. globally disable standard NFT sends and formally reserve the chain NFT module for Warbound assets.

Only after one option is enforced in code and tested should `x/wartrophy` mint/link holder-visible NFTs and let explorers report them as wallet assets.

## Mainnet upgrade and migration requirements

This change requires a coordinated `wolo-1` binary upgrade. It must not be copied over the live binary and restarted ad hoc.

Required before mainnet:

1. choose an upgrade name and height;
2. register an upgrade handler;
3. configure an upgrade store loader that adds the `wartrophy` KV store;
4. include `wartrophy` version `1` in the module version map;
5. decide whether the initial authority is governance or a dedicated address;
6. build reproducibly for Linux, checksum the binary, and test the exact artifact on a state snapshot;
7. prove pre-upgrade halt, post-upgrade restart, queries, authority rotation, and all mutation messages;
8. back up chain home and the protected settlement state before any production action;
9. update explorer/API clients only after the chain upgrade is healthy.

No bank balance or existing NFT state migration is required because this pass has no module account and does not write `x/nft`. A new module store and module version initialization are still required.

Fresh local/testnet genesis can initialize `wartrophy` normally without a state migration.

## App integration points

AoE2HDBets already has trophy, economics-version, event, payout, and challenge tables. The integration service should:

- query `TrophyAuthority` during health checks
- map app `trophy_id` directly to chain `trophy_id`
- submit register/mint/assign/reassign/retire/update transactions only after app validation
- store request payload, tx hash, height, event type, and error text in `trophy_events`
- reconcile app holder against `QueryTrophyOwner`
- use `QueryTrophiesByOwner` for profile entitlement views
- treat chain owner as payout entitlement truth once a trophy is chain-backed
- keep tribute and bounty money movement on the existing settlement rail for now
- label this implementation `state_backed`, not wallet NFT
