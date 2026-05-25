# WoloChain Mainnet Services And Ports

This is a planning document only. Do not create services, homes, env files, or ports from this doc until the launch window is explicitly approved.

## Recommended Runtime Names

| Item | Testnet Today | Recommended Mainnet |
| --- | --- | --- |
| Chain ID | `wolo-testnet` | `wolo-1` |
| Node service | `wolochaind-testnet.service` | `wolochaind-mainnet.service` |
| Settlement service | `wolochain-settlement.service` | `wolochain-mainnet-settlement.service` |
| Node env file | `/etc/wolochaind-testnet.env` | `/etc/wolochaind-mainnet.env` |
| Settlement env file | `/etc/wolochain-settlement.env` | `/etc/wolochain-mainnet-settlement.env` |
| Chain home | `/var/lib/wolochaind-testnet` | `/var/lib/wolochaind-mainnet` |
| Settlement state | `/mnt/HC_Volume_105319120/wolochain/settlement-state` | `/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state` |
| Repo path | `/var/www/WoloChain` | `/var/www/WoloChain-mainnet` |
| Binary | `/var/www/WoloChain/build/wolochaind` | `/var/www/WoloChain-mainnet/build/wolochaind` |

Using the same binary path as testnet is acceptable only if both testnet and mainnet are intentionally upgraded together. For lower blast radius, prefer the separate mainnet deploy root shown above.

## Recommended Local Ports

| Surface | Testnet Today | Recommended Mainnet | Reason |
| --- | ---: | ---: | --- |
| P2P | `26656` | `27656` | Avoids testnet listener conflict. |
| RPC | `26657` | `27657` | Keeps CometBFT RPC separate. |
| REST | `1317` | `1318` | Keeps Cosmos REST API separate. |
| gRPC | usually `9090` if enabled | `9091` | Avoids common Cosmos gRPC conflicts. |
| gRPC-web | usually `9091` if enabled | `9092` | Only if enabled. |
| Settlement API | `8091` | `8092` | Keeps operator settlement surfaces separate. |

## Planned Mainnet Node Env

```bash
WOLO_HOME=/var/lib/wolochaind-mainnet
CHAIN_ID=wolo-1
MIN_GAS_PRICES=0.025uwolo
```

The final `config.toml` and `app.toml` should bind:

```text
p2p.laddr = tcp://0.0.0.0:27656
rpc.laddr = tcp://127.0.0.1:27657
api.address = tcp://127.0.0.1:1318
grpc.address = 127.0.0.1:9091
grpc-web.address = 127.0.0.1:9092
```

## Planned Mainnet Settlement Env

```bash
WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-mainnet
WOLO_SETTLEMENT_NODE=tcp://127.0.0.1:27657
WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:27657
WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1318
WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest.wolo.aoe2war.com
WOLO_SETTLEMENT_CHAIN_ID=wolo-1
WOLO_SETTLEMENT_BASE_DENOM=uwolo
WOLO_SETTLEMENT_DISPLAY_DENOM=wolo
WOLO_SETTLEMENT_ADDRESS_PREFIX=wolo
WOLO_SETTLEMENT_KEYRING_BACKEND=os
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state
```

Wallet-specific values must be filled only after fresh mainnet wallets exist:

```bash
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=mainnet-payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_ESCROW_KEY_NAME=mainnet-escrow
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_TREASURY_ADDRESS=wolo1_REPLACE_ME
WOLO_SETTLEMENT_AUTH_TOKEN=<secret outside git>
```

## Service Safety Rules

- Do not stop `wolochaind-testnet.service` to prepare mainnet.
- Do not stop `wolochain-settlement.service` to prepare mainnet.
- Do not reuse `/var/lib/wolochaind-testnet`.
- Do not reuse the testnet settlement state path.
- Do not start mainnet services until genesis, gentx, env, DNS, and TLS have been reviewed.
- Back up any live operator state before service changes.
