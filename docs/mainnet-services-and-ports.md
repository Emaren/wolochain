# WoloChain Mainnet Services And Ports

This document records the verified `wolo-1` service shape as of June 2, 2026, plus the reserved mainnet settlement port if a separate settlement service is intentionally deployed later.

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
| Settlement API | `8092` | Reserved for a future mainnet settlement service. Not part of the verified live surface today. |

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

## Mainnet Settlement Env Shape

Use this only when deploying a separate mainnet settlement service. Do not point AoE2HDBets at the old testnet settlement service for mainnet stake verification.

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
WOLO_SETTLEMENT_KEYRING_BACKEND=os
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state
```

Wallet-specific values must come from fresh mainnet keys:

```bash
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=mainnet-payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_ESCROW_KEY_NAME=mainnet-escrow
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_TREASURY_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_AUTH_TOKEN=<secret outside git>
```

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
WOLO_FAUCET_CHAIN_ID=wolo-1
WOLO_FAUCET_NODE_RPC=http://127.0.0.1:27657
```

`WOLO_SETTLEMENT_URL` should remain empty for AoE2HDBets mainnet unless `wolochain-mainnet-settlement.service` is deliberately deployed on `127.0.0.1:8092` and verified against `wolo-1`.

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
| Faucet Hot Wallet | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` | `498999.996989 WOLO` |
| IBC Escrow: transfer/channel-0 to Osmosis | `wolo1a53udazy8ayufvy0s434pfwjcedzqv347h8lzn` | `200001 WOLO` |
| Jim | `wolo10zspyrrphzctrpysh6l9dsqj4wcwmj3tk660sz` | `1000 WOLO` |
| Validator Ops Reserve | `wolo1fl48vsnmsdzcv85q5d2q4z5ajdha8yu3aqv4s2` | `1000 WOLO` |
| Sniper | `wolo1mcmckkr360n47wyc408xmlsv4tzw95kkczvfp9` | `1000 WOLO` |
| Staking Wallet | `wolo1rmr39nd5gnnv5y5f66qtq367xfwvx9jt5w7ucr` | `110 WOLO` |
| Wolo-Osmosis Relayer Gas | `wolo1m8qzq92hkktgqp47aewzylkatk6c22vc8c4vgj` | `99.997730 WOLO` |
| Bet Escrow | `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4` | `52 WOLO` |
| Faucet/Test Wallet 10 | `wolo1jv65s3grqf6v6jl3dp4t6c9t9rk99cd80ypxqz` | `0.048269 WOLO` |

Configured zero-balance signer to keep visible in operator surfaces:

| Role | Address | Balance |
| --- | --- | ---: |
| Bet Payout | `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5` | `0 WOLO` |

Do not show a zero-balance signer as funded. If faucet claims or payout execution should run on mainnet, fund the configured signer or switch the app env to a reviewed funded signer; do not fall back to `wolo-testnet`.

## Service Safety Rules

- Do not stop or repoint testnet services while updating mainnet docs/config.
- Do not reuse `/var/lib/wolochaind-testnet` or testnet settlement state for mainnet.
- Do not set AoE2HDBets `WOLO_SETTLEMENT_URL` to the old `127.0.0.1:8091` testnet service for mainnet betting.
- Do not set AoE2HDBets `WOLO_STAKING_HOME` or `WOLO_FAUCET_HOME` to `/var/lib/wolochaind-testnet` for mainnet.
- Use mainnet RPC/REST tx lookup for AoE2HDBets stake verification unless `wolochain-mainnet-settlement.service` is deployed and verified against `wolo-1`.
