# WoloChain Mainnet Settlement Runbook

This runbook is for `wolo-1` mainnet settlement only. Do not reuse the old testnet service, state, signer keys, or port.

## Hard Rules

- Mainnet settlement API: `http://127.0.0.1:8092`.
- Old testnet settlement API: `http://127.0.0.1:8091`.
- Never point AoE2HDBets mainnet settlement, staking reward, or Community Treasury payout calls at `8091`.
- Never commit or print mnemonics, keyring passphrases, or auth tokens.
- Do not replace `/var/lib/wolochaind-mainnet/keyring-file`; use the dedicated settlement keyring dir below.

## Live Shape

| Item | Value |
| --- | --- |
| Node service | `wolochaind-mainnet.service` |
| Settlement service | `wolochain-mainnet-settlement.service` |
| Chain ID | `wolo-1` |
| RPC | `tcp://127.0.0.1:27657` |
| REST | `http://127.0.0.1:1318` |
| Public REST | `https://rest-mainnet.aoe2war.com` |
| Settlement bind | `127.0.0.1:8092` |
| State dir | `/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state` |
| Keyring backend | `file` |
| Keyring dir | `/var/lib/wolochain-mainnet-settlement/keyring` |
| Passphrase file | `/etc/wolochain-mainnet-settlement.keyring-passphrase` |
| Payout signer | `mainnet-payout` / `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` |
| Escrow signer | `mainnet-escrow` / `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` |
| Community Treasury | `wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2` |

## Env File

Install `/etc/wolochain-mainnet-settlement.env` with root-only permissions:

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
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=mainnet-payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_SETTLEMENT_ESCROW_KEY_NAME=mainnet-escrow
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_SETTLEMENT_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED=true
WOLO_SETTLEMENT_GAS=auto
WOLO_SETTLEMENT_GAS_ADJUSTMENT=1.5
WOLO_SETTLEMENT_GAS_PRICES=0.025uwolo
WOLO_SETTLEMENT_BROADCAST_MODE=sync
WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO=1000000000
WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO=10000000
WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO=100000000
WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO=10000000
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state
WOLO_SETTLEMENT_AUTH_TOKEN=<secret outside git>
```

## Key Setup

Create the passphrase file and dedicated keyring before starting the service:

```bash
sudo install -d -m 0700 /var/lib/wolochain-mainnet-settlement/keyring
sudo install -d -m 0700 /root/wolochain-mainnet-settlement-keys
sudo sh -c 'openssl rand -base64 48 > /etc/wolochain-mainnet-settlement.keyring-passphrase'
sudo chmod 0600 /etc/wolochain-mainnet-settlement.keyring-passphrase
```

Generate fresh mainnet signer keys with `--keyring-dir /var/lib/wolochain-mainnet-settlement/keyring` and store mnemonic JSON backups only under `/root/wolochain-mainnet-settlement-keys`.

## Funding Gate

The fresh signers were funded on June 4, 2026 from the approved mainnet Faucet Hot Wallet `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0`. Tony restored that Faucet Hot Wallet into the AoE2HDBets app keyring at `/var/lib/aoe2hdbets-wolo-mainnet` as `faucet-hot-mainnet`; do not use old testnet `faucetgrowth` for mainnet faucet claims.

Current seeded balances:

```text
Bet Payout Signer: 5000 WOLO
Bet Escrow Signer: 500 WOLO
```

Funding txs:

| Purpose | Tx Hash |
| --- | --- |
| Seed Bet Payout Signer with `5000 WOLO` | `F9BBCD8439538E23181F8EC7F43FF6FCA705CB5675C35B2FFA84030DB5DB304C` |
| Seed Bet Escrow Signer with `500 WOLO` | `1FD8AE967608737E3FDD8F8D9E473C1D1FE3D638A221E6C1892284BA26564233` |

The service must refuse live payouts when the payout signer would fall below `1000 WOLO` plus fee headroom. It must refuse escrow-signed runs when escrow would fall below `100 WOLO` plus fee headroom.

## Validation

After restart:

```bash
curl -fsS http://127.0.0.1:8092/settlement/v1/health
sudo SETTLEMENT_ENV_FILE=/etc/wolochain-mainnet-settlement.env \
  WOLOCHAIND_BIN=/usr/local/bin/wolochaind-mainnet \
  /var/www/WoloChain-wolo-1/scripts/verify-live-settlement.sh
```

As of the June 4 funding check, `/settlement/v1/health` must report `ok=true`, `chain_id=wolo-1`, and funded payout and escrow signer balances above their configured reserve floors.

Every grouped app run should be submitted to `POST /settlement/v1/runs/validate` first. Execute the matching `POST /settlement/v1/runs` only after the dry-run response confirms:

- `chain_id` is `wolo-1`
- `signer_role` is expected
- `signer_address` matches payout or escrow signer above
- requested total and projected remaining balance are acceptable
- no reserve-floor or fee-headroom refusal exists

## AoE2HDBets Cutover Values

Use these values in the separate AoE2HDBets app pass now that funding and health are green:

```bash
WOLO_SETTLEMENT_URL=http://127.0.0.1:8092
WOLO_SETTLEMENT_AUTH_TOKEN=<copy from /etc/wolochain-mainnet-settlement.env>
WOLO_BET_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_BET_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_COMMUNITY_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
```

Leave `127.0.0.1:8091` out of every mainnet app env.
