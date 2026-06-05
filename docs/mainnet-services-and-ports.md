# WoloChain Mainnet Services And Ports

This document records the verified `wolo-1` service shape as of June 4, 2026, including the dedicated mainnet settlement service shape on `127.0.0.1:8092`.

## Verified Live Runtime

| Item | Current Mainnet |
| --- | --- |
| Chain ID | `wolo-1` |
| Node service | `wolochaind-mainnet.service` |
| Node home | `/var/lib/wolochaind-mainnet` |
| Repo path | `/var/www/WoloChain-wolo-1` |
| Binary | `/usr/local/bin/wolochaind-mainnet` |
| Public RPC | `https://rpc-mainnet.aoe2war.com` |
| Public REST | `https://rest-mainnet.aoe2war.com` |
| RPC path alias | `https://aoe2war.com/rpc-mainnet/` |
| REST path alias | `https://aoe2war.com/rest-mainnet/` |
| Browser origin allowed by RPC/REST CORS | `https://aoe2war.com` |
| AoE2HDBets app signer home | `/var/lib/aoe2hdbets-wolo-mainnet` |

The old `wolochaind-testnet.service`, `wolochain-settlement.service`, `/var/lib/wolochaind-testnet`, `/var/www/WoloChain`, `https://aoe2war.com/rpc/`, `https://aoe2war.com/rest/`, and `https://aoe2war.com/wolo-testnet` names belong to the legacy testnet surface unless an operator explicitly says otherwise.

## Verified Mainnet Ports

| Surface | Mainnet | Notes |
| --- | ---: | --- |
| P2P | `27656` | Public node gossip. |
| RPC | `27657` | Proxied by `https://rpc-mainnet.aoe2war.com`. |
| REST | `1318` | Proxied by `https://rest-mainnet.aoe2war.com`. |
| Settlement API | `8092` | Mainnet-only loopback settlement service. Never point mainnet callers at old testnet `8091`. |

## Mainnet Node Env Shape

```bash
WOLO_HOME=/var/lib/wolochaind-mainnet
CHAIN_ID=wolo-1
MIN_GAS_PRICES=0.025uwolo
```

The verified public node reports:

- network `wolo-1`
- moniker `wolo-mainnet-hel1`
- `tx_index=on`
- earliest block time `2026-05-25T03:54:33Z`
- `catching_up=false`
- mainnet REST tx search uses the `query=` parameter, for example `query=transfer.recipient='wolo1...'`

## Mainnet Settlement Env Shape

Use this only for the dedicated mainnet settlement service. Do not point AoE2HDBets at the old testnet settlement service for mainnet stake verification or payouts.

```bash
WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-mainnet
WOLO_SETTLEMENT_NODE=tcp://127.0.0.1:27657
WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:27657
WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1318
WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest-mainnet.aoe2war.com
WOLO_SETTLEMENT_CHAIN_ID=wolo-1
WOLO_SETTLEMENT_BASE_DENOM=uwolo
WOLO_SETTLEMENT_DISPLAY_DENOM=wolo
WOLO_SETTLEMENT_ADDRESS_PREFIX=wolo
WOLO_SETTLEMENT_KEYRING_BACKEND=file
WOLO_SETTLEMENT_KEYRING_DIR=/var/lib/wolochain-mainnet-settlement/keyring
WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE=/etc/wolochain-mainnet-settlement.keyring-passphrase
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state
```

Wallet-specific values must come from fresh mainnet keys:

```bash
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=mainnet-payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_SETTLEMENT_ESCROW_KEY_NAME=mainnet-escrow
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_SETTLEMENT_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
WOLO_SETTLEMENT_AUTH_TOKEN=<secret outside git>
```

The signer keyring is separate from the node home keyring. Do not replace `/var/lib/wolochaind-mainnet/keyring-file`; it contains older operational keyring data. Store the mainnet settlement file-keyring passphrase only in `/etc/wolochain-mainnet-settlement.keyring-passphrase` with root-only permissions.

## AoE2HDBets Mainnet App Env Shape

AoE2HDBets mainnet browser and server reads should use the public or loopback `wolo-1` endpoints:

```bash
NEXT_PUBLIC_WOLO_CHAIN_ID=wolo-1
NEXT_PUBLIC_WOLO_RPC_URL=https://rpc-mainnet.aoe2war.com
NEXT_PUBLIC_WOLO_REST_URL=https://rest-mainnet.aoe2war.com
WOLO_INTERNAL_RPC_URL=http://127.0.0.1:27657
WOLO_INTERNAL_REST_URL=http://127.0.0.1:1318
```

Mainnet app signer operations must not use the testnet home or old testnet RPC port. The verified deployment uses a separate app signer home so the web process can access only its app keys, not the validator/node config:

```bash
WOLO_STAKING_CLI=/usr/local/bin/wolochaind-mainnet
WOLO_STAKING_HOME=/var/lib/aoe2hdbets-wolo-mainnet
WOLO_STAKING_CHAIN_ID=wolo-1
WOLO_STAKING_NODE_RPC=http://127.0.0.1:27657
WOLO_FAUCET_CLI=/usr/local/bin/wolochaind-mainnet
WOLO_FAUCET_HOME=/var/lib/aoe2hdbets-wolo-mainnet
WOLO_FAUCET_FROM=faucet-hot-mainnet
WOLO_FAUCET_CHAIN_ID=wolo-1
WOLO_FAUCET_NODE_RPC=http://127.0.0.1:27657
WOLO_FAUCET_KEYRING_BACKEND=test
```

`WOLO_FAUCET_FROM` must resolve inside `/var/lib/aoe2hdbets-wolo-mainnet` to the funded Faucet Hot Wallet `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0`. The suggested key name is `faucet-hot-mainnet` so it cannot be confused with the old `faucetgrowth` key. As of the June 4, 2026 faucet audit after AoE2HDBets app-prod `7a706ee`, the VPS key `faucetgrowth` resolves to `wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx` and has `0 WOLO`; do not use it as the mainnet faucet unless Tony deliberately funds that legacy signer as a separate app faucet account.

`WOLO_SETTLEMENT_URL` is ready to set after the June 4, 2026 funding check: `wolochain-mainnet-settlement.service` is deployed on `127.0.0.1:8092`, verified against `wolo-1`, and the payout/escrow signers are funded above their reserve floors.

```bash
WOLO_SETTLEMENT_URL=http://127.0.0.1:8092
WOLO_SETTLEMENT_AUTH_TOKEN=<copy from /etc/wolochain-mainnet-settlement.env on the VPS>
WOLO_BET_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_BET_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_COMMUNITY_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
```

Current mainnet holder aliases from the June 4, 2026 holder audit:

| Role | Address | Balance |
| --- | --- | ---: |
| Founder Cold | `wolo1r8kvt7me33rsv9ldaczj03xjrld4yumx0c0jkg` | `60000000 WOLO` |
| Community Treasury | `wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2` | `10000000 WOLO` |
| DEX Liquidity Reserve | `wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en` | `9799999.995 WOLO` |
| Faucet Growth Reserve | `wolo12c009ektp58rr0gkjz3nk8f4kgvfpfzwfk86l3` | `6500000 WOLO` |
| Validator Ops | `wolo1nalsh7y0hzp33j996c90yxqgerxxvgpqtumfjt` | `4998898.99 WOLO` |
| Founder Operating / Emaren | `wolo1wue7vyque2pssskgdrww0fcadlq9ps6mtn605e` | `4998837.972012 WOLO` |
| Ecosystem Bounties | `wolo1dmj5dnm7g9hmj005yzy5e5xcygudyt7wxzpxjq` | `3000000 WOLO` |
| Faucet Hot Wallet | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` | `493499.991819 WOLO` |
| IBC Escrow: transfer/channel-0 to Osmosis | `wolo1a53udazy8ayufvy0s434pfwjcedzqv347h8lzn` | `200001 WOLO` |
| Jim | `wolo10zspyrrphzctrpysh6l9dsqj4wcwmj3tk660sz` | `1000 WOLO` |
| Julio Alvarez | `wolo1n0yg6ltqxl05ljaqftvvtgec5qavf9a3uh090h` | `1007 WOLO` |
| Validator Ops Reserve | `wolo1fl48vsnmsdzcv85q5d2q4z5ajdha8yu3aqv4s2` | `1000 WOLO` |
| Sniper | `wolo1mcmckkr360n47wyc408xmlsv4tzw95kkczvfp9` | `1000 WOLO` |
| Staking Wallet | `wolo1rmr39nd5gnnv5y5f66qtq367xfwvx9jt5w7ucr` | `110 WOLO` |
| Wolo-Osmosis Relayer Gas | `wolo1m8qzq92hkktgqp47aewzylkatk6c22vc8c4vgj` | `99.997730 WOLO` |
| Legacy Bet Escrow | `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4` | `52 WOLO` |
| Faucet/Test Wallet 10 | `wolo1jv65s3grqf6v6jl3dp4t6c9t9rk99cd80ypxqz` | `0.048269 WOLO` |
| Legacy app `faucetgrowth` key | `wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx` | `0 WOLO` |

Fixed supply is `100000000000000 uwolo` (`100,000,000 WOLO`). Any app surface that reports less than this as "known addresses" is missing at least one holder row; on June 4, 2026 the app network table was short by Julio Alvarez's `1,007 WOLO` until `wolo1n0yg6ltqxl05ljaqftvvtgec5qavf9a3uh090h` is included.

Fresh settlement signers created on June 4, 2026:

| Role | Address | Balance |
| --- | --- | ---: |
| Bet Payout Signer | `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` | `5000 WOLO` |
| Bet Escrow Signer | `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` | `500 WOLO` |

Funding txs from Faucet Hot Wallet on June 4, 2026:

| Purpose | Tx Hash |
| --- | --- |
| Seed Bet Payout Signer with `5000 WOLO` | `F9BBCD8439538E23181F8EC7F43FF6FCA705CB5675C35B2FFA84030DB5DB304C` |
| Seed Bet Escrow Signer with `500 WOLO` | `1FD8AE967608737E3FDD8F8D9E473C1D1FE3D638A221E6C1892284BA26564233` |

Previously configured zero-balance signer retained only for historical operator context:

| Role | Address | Balance |
| --- | --- | ---: |
| Retired Bet Payout | `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5` | `0 WOLO` |

Do not show a zero-balance signer as funded. If faucet claims or payout execution should run on mainnet, use the reviewed funded signer for that role; do not fall back to `wolo-testnet`.

## Service Safety Rules

- Do not stop or repoint testnet services while updating mainnet docs/config.
- Do not reuse `/var/lib/wolochaind-testnet` or testnet settlement state for mainnet.
- Do not set AoE2HDBets `WOLO_SETTLEMENT_URL` to the old `127.0.0.1:8091` testnet service for mainnet betting.
- Do not retry mainnet payout, staking reward, or Community Treasury calls against `127.0.0.1:8091`; that port is `wolo-testnet`.
- Do not set AoE2HDBets `WOLO_STAKING_HOME` or `WOLO_FAUCET_HOME` to `/var/lib/wolochaind-testnet` for mainnet.
- Do not set AoE2HDBets `WOLO_FAUCET_FROM=faucetgrowth` for mainnet unless that legacy app key is intentionally funded and documented as a new hot faucet signer. The funded current Faucet Hot Wallet is `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0`.
- Use mainnet RPC/REST tx lookup for AoE2HDBets stake verification unless `wolochain-mainnet-settlement.service` is deployed and verified against `wolo-1`.
