# WoloChain Mainnet Wallet And Key Plan

This is a planning document only. Do not generate mnemonics in this repo and do not expose mnemonics in terminal output, docs, commits, screenshots, or tickets.

Every mainnet key must be fresh. Testnet equivalents must not be reused.

## Wallet Inventory

| Wallet | Purpose | In Genesis | Custody | Signs Tx | Must Back Up | Testnet Reuse |
| --- | --- | --- | --- | --- | --- | --- |
| Validator / operator | Validator account, gentx self-delegation, validator ops, chain administration where needed. | yes | hot or warm on validator host; backup cold | yes | yes | never |
| Community treasury | Long-lived community reserve and public credibility treasury. | yes | cold or multisig | rarely | yes | never |
| Staking rewards | Funds staking or reward programs that are policy-owned outside core chain code. | yes | cold or multisig, with controlled hot distribution path | sometimes | yes | never |
| Community war chest | Strategic community campaigns, partnerships, tournaments, and emergency ecosystem funding. | yes | cold or multisig | rarely | yes | never |
| Watcher / player rewards | Reward inventory for app-owned watcher/player programs. | yes | warm or cold with a separate distribution signer | yes if used directly | yes | never |
| Settlement payout signer | Mainnet settlement sends for approved payouts. | yes, if launch settlement is live | hot, tightly scoped, reserve-limited | yes | yes | never |
| Escrow signer | Escrow-signed grouped runs and challenge top-up path if enabled. | yes, if escrow settlement is live | hot or warm, tightly scoped | yes | yes | never |
| Relayer wallet | IBC relayer fees on WoloChain side. | maybe | hot with small balance | yes | yes | never |
| Osmosis LP wallet | Custodies WOLO intended for Osmosis liquidity operations. | yes or funded later | cold until liquidity operation | yes during pool creation | yes | never |
| Emergency / reserve | Recovery, incident response, and reserve custody. | yes | cold or multisig | rarely | yes | never |

## Current Mainnet Address Labels

Use these labels when app or explorer surfaces render `wolo-1` holder and transfer tables.

| Label | Address | Notes |
| --- | --- | --- |
| Founder Cold | `wolo1r8kvt7me33rsv9ldaczj03xjrld4yumx0c0jkg` | Long-term founder reserve. |
| Community Treasury | `wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2` | Protocol treasury and community reserve. |
| DEX Liquidity Reserve | `wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en` | Osmosis and future liquidity reserve. |
| Faucet Growth Reserve | `wolo12c009ektp58rr0gkjz3nk8f4kgvfpfzwfk86l3` | Onboarding and growth reserve. |
| Validator Ops | `wolo1nalsh7y0hzp33j996c90yxqgerxxvgpqtumfjt` | Validator operations and self-delegation reserve. |
| Founder Operating / Emaren | `wolo1wue7vyque2pssskgdrww0fcadlq9ps6mtn605e` | Founder operating and shipping budget. |
| Ecosystem Bounties | `wolo1dmj5dnm7g9hmj005yzy5e5xcygudyt7wxzpxjq` | Contributor rewards, tools, and bug bounties. |
| Faucet Hot Wallet | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` | App-facing faucet wallet. |
| IBC Escrow: transfer/channel-0 to Osmosis | `wolo1a53udazy8ayufvy0s434pfwjcedzqv347h8lzn` | WoloChain-side ICS-20 escrow for the live Osmosis path. |
| Jim | `wolo10zspyrrphzctrpysh6l9dsqj4wcwmj3tk660sz` | Player wallet. |
| Validator Ops Reserve | `wolo1fl48vsnmsdzcv85q5d2q4z5ajdha8yu3aqv4s2` | Validator ops reserve wallet. |
| Sniper | `wolo1mcmckkr360n47wyc408xmlsv4tzw95kkczvfp9` | Player wallet. |
| Staking Wallet | `wolo1rmr39nd5gnnv5y5f66qtq367xfwvx9jt5w7ucr` | AoE2HDBets staking custody wallet. |
| Wolo-Osmosis Relayer Gas | `wolo1m8qzq92hkktgqp47aewzylkatk6c22vc8c4vgj` | Wolo side relayer gas wallet. |
| Legacy Bet Escrow | `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4` | Historical AoE2HDBets escrow wallet with no current mainnet settlement signer configured. |
| Retired Bet Payout | `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5` | Historical configured payout signer; zero-balance and not used for the June 4 mainnet settlement service. |
| Bet Payout Signer | `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` | Fresh mainnet payout signer in `/var/lib/wolochain-mainnet-settlement/keyring`; funded June 4, 2026. |
| Bet Escrow Signer | `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` | Fresh mainnet escrow signer in `/var/lib/wolochain-mainnet-settlement/keyring`; route new app escrow deposits here after cutover. |
| Faucet/Test Wallet 10 | `wolo1jv65s3grqf6v6jl3dp4t6c9t9rk99cd80ypxqz` | Small legacy faucet/test balance. |
| Legacy app `faucetgrowth` key | `wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx` | Present in `/var/lib/aoe2hdbets-wolo-mainnet` but not the funded mainnet Faucet Hot Wallet. |

## Operational Notes

- Mainnet validator private keys must be generated fresh for `wolo-1`.
- Mainnet settlement payout and escrow signers must be separate from testnet payout and escrow signers.
- Mainnet relayer and Osmosis LP wallets should hold only the amount needed for their role.
- Hot wallets should have reserve floors and alerting before production app traffic depends on them.
- Cold wallets should have a tested restore procedure before launch.
- Any multisig policy must be documented before funds are placed in genesis.

## Day-One Settlement Posture

Recommended default: prepare mainnet settlement infrastructure for day one, but do not switch AoE2War production payouts to mainnet until the chain, explorer, public REST, wallet backups, and hot-wallet alerting have survived a short observation window.

If Tony wants settlement ready at launch:

- include fresh payout and escrow signers in the wallet plan
- fund them through explicit genesis allocation or a post-genesis treasury transfer
- use `WOLO_SETTLEMENT_KEYRING_BACKEND=file` with a dedicated keyring dir and root-only passphrase file, or a stronger production backend; never use the testnet `test` backend
- keep `WOLO_SETTLEMENT_AUTH_TOKEN` enabled
- set reserve floors before any app calls production routes
- verify dry-run settlement requests before enabling execution from app systems

If Tony wants a quieter launch:

- launch chain, public endpoints, explorer, and Keplr first
- leave settlement service stopped or operator-only
- fund payout and escrow signers later from treasury
- switch AoE2War only after Tony approves a cutover window

## June 4, 2026 Mainnet Settlement Signers

The deployed `wolo-1` settlement service shape uses these fresh signer roles:

| Role | Key name | Address | Keyring |
| --- | --- | --- | --- |
| Bet Payout Signer | `mainnet-payout` | `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` | `/var/lib/wolochain-mainnet-settlement/keyring` |
| Bet Escrow Signer | `mainnet-escrow` | `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` | `/var/lib/wolochain-mainnet-settlement/keyring` |

The file-keyring passphrase path is `/etc/wolochain-mainnet-settlement.keyring-passphrase`; keep it root-only and outside git. The signer mnemonic JSON backups are root-only under `/root/wolochain-mainnet-settlement-keys`; never print or copy those into docs, tickets, shell history, screenshots, or app config.

Initial funding completed June 4, 2026:

| Role | Balance | Funding tx |
| --- | ---: | --- |
| Bet Payout Signer | `5000 WOLO` | `F9BBCD8439538E23181F8EC7F43FF6FCA705CB5675C35B2FFA84030DB5DB304C` |
| Bet Escrow Signer | `500 WOLO` | `1FD8AE967608737E3FDD8F8D9E473C1D1FE3D638A221E6C1892284BA26564233` |

The app-facing mainnet faucet source is the funded Faucet Hot Wallet `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0`. Restore or import that key into `/var/lib/aoe2hdbets-wolo-mainnet` under a mainnet-specific name such as `faucet-hot-mainnet`, then set `WOLO_FAUCET_FROM=faucet-hot-mainnet` in AoE2HDBets. Do not use the old testnet `faucetgrowth` key as a fallback; it resolves on the VPS to `wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx` and currently has `0 WOLO`.

## June 4, 2026 Mainnet Faucet Gate

AoE2HDBets app-prod commit `7a706ee` configured the faucet route with `WOLO_FAUCET_FROM=faucetgrowth`. The chain-side audit found that this key exists in `/var/lib/aoe2hdbets-wolo-mainnet`, but it is not the funded mainnet Faucet Hot Wallet:

| Key name | Address | Balance | Status |
| --- | --- | ---: | --- |
| `faucetgrowth` | `wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx` | `0 WOLO` | legacy app/test key, do not use for current mainnet faucet claims |
| `faucet-hot-mainnet` | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` | `493499.991819 WOLO` | intended funded mainnet Faucet Hot Wallet after secure key restore |

There is no new funding tx to document when the app is switched to the existing funded Faucet Hot Wallet. If Tony instead chooses to keep `faucetgrowth` as a separate app hot faucet signer, fund it intentionally from the Faucet Hot Wallet and document that new tx hash here.

Safe restore pattern for the intended Faucet Hot Wallet:

```bash
sudo install -d -m 0700 /var/lib/aoe2hdbets-wolo-mainnet
sudo /usr/local/bin/wolochaind-mainnet keys add faucet-hot-mainnet \
  --recover \
  --home /var/lib/aoe2hdbets-wolo-mainnet \
  --keyring-backend test
sudo /usr/local/bin/wolochaind-mainnet keys show faucet-hot-mainnet \
  --home /var/lib/aoe2hdbets-wolo-mainnet \
  --keyring-backend test -a
sudo /usr/local/bin/wolochaind-mainnet query bank balances \
  wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0 \
  --node tcp://127.0.0.1:27657 \
  --output json
```

Paste the mnemonic interactively only when explicitly restoring the key. Never place the mnemonic in shell history, docs, env files, screenshots, or tickets.

## Backup Requirements

For every mainnet wallet:

- record wallet purpose
- record owner or custody location
- record whether it is hot, warm, cold, or multisig
- record recovery method outside this repo
- test restore before launch
- confirm the address is mainnet-intended and uses `wolo1...`

Do not store mnemonics in:

- git
- WoloChain docs
- WoloChain env files
- VPS-readable shell history
- app config
- screenshots
- issue trackers

## Launch Gate

Before launch, Tony must approve:

- final wallet list
- final custody model
- final genesis allocation per wallet
- which wallets are allowed to sign transactions after launch
- alert thresholds for hot wallets
- who can rotate keys and how emergency rotation works
