# Relayer Keys and Funding Checklist

Status: preparation checklist only. Do not create keys, fund wallets, create IBC clients/channels, transfer WOLO, transfer OSMO, create liquidity, or create the WOLO/USDC pool without Tony's explicit confirmation.

## Required Hermes Keys

- WoloChain mainnet key name: `wolo-mainnet-osmosis-relayer`
- Osmosis mainnet key name: `osmosis-mainnet-wolo-relayer`

These are relayer gas wallets only. They are not liquidity wallets.

## Phase 2.75 Key Inspection

Inspection date: 2026-05-25 UTC.

Commands run:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys list --chain wolo-1
```

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys list --chain osmosis-1
```

Result:

- `wolo-mainnet-osmosis-relayer` is not present yet.
- `osmosis-mainnet-wolo-relayer` is not present yet.
- No relayer addresses are available until keys are created or imported.

Balance check commands run:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys balance --chain wolo-1 --denom uwolo
```

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys balance --chain osmosis-1 --denom uosmo
```

Result:

- Wolo balance check cannot run yet because the Wolo relayer key file is missing:
  - `/var/lib/wolochain-mainnet-relayer/.hermes/keys/wolo-1/keyring-test/wolo-mainnet-osmosis-relayer.json`
- Osmosis balance check cannot run yet because the Osmosis relayer key file is missing:
  - `/var/lib/wolochain-mainnet-relayer/.hermes/keys/osmosis-1/keyring-test/osmosis-mainnet-wolo-relayer.json`

No keys were generated or imported during Phase 2.75 because Hermes key creation/import requires private key material from a key file or mnemonic file. Stop for Tony confirmation before creating or importing private material.

## Phase 2.8 Secure Import Plan

Inspection date: 2026-05-25 UTC.

Installed Hermes key support:

- Supported: import from a mnemonic file with `keys add --mnemonic-file`.
- Supported: import from a Comet keyring JSON file with `keys add --key-file`.
- Not exposed by this installed Hermes CLI: generating a fresh key internally without supplying mnemonic or key-file material.

No keys were created or imported during Phase 2.8. No mnemonics or private keys were displayed.

Preferred secure operator workflow, NOT RUN:

```bash
install -d -o root -g root -m 0700 \
  /root/wolo-1-mainnet-prep-markers/private-relayer-key-material
```

Place the WoloChain relayer mnemonic at this root-only path:

```txt
/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic
```

Place the Osmosis relayer mnemonic at this root-only path:

```txt
/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic
```

Set file permissions, NOT RUN:

```bash
chmod 0600 \
  /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic \
  /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic
```

Import the WoloChain relayer key, NOT RUN:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys add \
  --chain wolo-1 \
  --key-name wolo-mainnet-osmosis-relayer \
  --mnemonic-file /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic
```

Import the Osmosis relayer key, NOT RUN:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys add \
  --chain osmosis-1 \
  --key-name osmosis-mainnet-wolo-relayer \
  --mnemonic-file /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic
```

If using Comet keyring JSON files instead of mnemonic files, replace `--mnemonic-file <path>` with `--key-file <path>` and keep the same root-only directory and `0600` file permissions.

Post-import verification, NOT RUN:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys list --chain wolo-1
```

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys list --chain osmosis-1
```

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys balance --chain wolo-1 --denom uwolo
```

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  keys balance --chain osmosis-1 --denom uosmo
```

After import verification succeeds, record:

- Wolo relayer address.
- Osmosis relayer address.
- Whether each balance is funded or still zero.

Optional cleanup after confirmed Hermes import and secure backup, NOT RUN:

```bash
shred -u \
  /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic \
  /root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic
```

Only run cleanup after Tony confirms the mnemonic material is backed up safely elsewhere.

## Command Prefix

Use the dedicated WoloChain mainnet relayer home and config:

```bash
export HERMES_HOME=/var/lib/wolochain-mainnet-relayer
export HERMES_CONFIG=/etc/wolochain-mainnet/hermes-osmosis.toml
```

## Check Whether Keys Exist

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys list --chain wolo-1
```

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys list --chain osmosis-1
```

Expected before key creation/import:

- `wolo-mainnet-osmosis-relayer` may be missing.
- `osmosis-mainnet-wolo-relayer` may be missing.

## Import or Create Keys

Do not store mnemonics in the repo. Use secure operator handling only.

Prepared import commands, NOT RUN.

If Tony supplies secure mnemonic files:

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys add \
  --chain wolo-1 \
  --key-name wolo-mainnet-osmosis-relayer \
  --mnemonic-file /secure/path/to/wolo-mainnet-osmosis-relayer.mnemonic
```

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys add \
  --chain osmosis-1 \
  --key-name osmosis-mainnet-wolo-relayer \
  --mnemonic-file /secure/path/to/osmosis-mainnet-wolo-relayer.mnemonic
```

If importing Comet keyring JSON instead of mnemonics, use `--key-file` in place of `--mnemonic-file`.

If Tony explicitly approves fresh key generation, generate the key material through a secure operator flow that does not print mnemonics into logs or chat, then import it into Hermes with the commands above. Keep any temporary key seed files root-only and outside the repo, then remove them after Hermes import is verified.

Expected Hermes key storage after import:

- `/var/lib/wolochain-mainnet-relayer/.hermes/keys/wolo-1/keyring-test/wolo-mainnet-osmosis-relayer.json`
- `/var/lib/wolochain-mainnet-relayer/.hermes/keys/osmosis-1/keyring-test/osmosis-mainnet-wolo-relayer.json`

## Show Relayer Addresses

After keys are created or imported, show the WoloChain relayer address:

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys list --chain wolo-1
```

After keys are created or imported, show the Osmosis relayer address:

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys list --chain osmosis-1
```

Record both addresses before Phase 3.

## Required Funding

Fund only the relayer gas wallets:

- WoloChain relayer wallet: a small amount of `uwolo` for WoloChain relayer fees.
- Osmosis relayer wallet: a small amount of `uosmo` for Osmosis relayer fees.

Funding status as of Phase 2.75:

- `uwolo`: not funded; Wolo relayer address is not available yet.
- `uosmo`: not funded; Osmosis relayer address is not available yet.

Prepared funding instructions, NOT RUN:

```txt
Send a small uwolo gas amount to the Wolo relayer address after it exists.
Send a small uosmo gas amount to the Osmosis relayer address after it exists.
```

Example WoloChain gas funding command, NOT RUN:

```bash
/usr/local/bin/wolochaind-mainnet tx bank send \
  <approved-wolo-gas-source-key-or-address> \
  <wolo-relayer-address> \
  <small-amount>uwolo \
  --chain-id wolo-1 \
  --home /var/lib/wolochaind-mainnet \
  --node http://127.0.0.1:27657 \
  --fees 5000uwolo
```

Example Osmosis gas funding command from an operator machine with `osmosisd`, NOT RUN:

```bash
osmosisd tx bank send \
  <approved-osmosis-gas-source-key-or-address> \
  <osmosis-relayer-address> \
  <small-amount>uosmo \
  --chain-id osmosis-1 \
  --node https://rpc.osmosis.zone:443 \
  --fees 5000uosmo
```

Keplr or another Osmosis wallet UI may also be used for the `uosmo` gas funding transfer, as long as it sends only a small gas amount to the recorded Osmosis relayer address.

Funding checks after gas funding:

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys balance --chain wolo-1 --denom uwolo
```

```bash
HOME="$HERMES_HOME" /usr/local/bin/hermes --config "$HERMES_CONFIG" \
  keys balance --chain osmosis-1 --denom uosmo
```

## Funding Warnings

- These are relayer gas wallets, not liquidity wallets.
- Do not use Founder Cold for relayer gas.
- Do not use Community Treasury for relayer gas.
- Do not use the WOLO DEX Liquidity Reserve for relayer gas.
- The 200,000 WOLO liquidity transfer remains separate.
- The 200,000 WOLO liquidity transfer must come from the WOLO DEX Liquidity Reserve only after Tony confirms:
  - `wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en`
- Do not execute the 200,000 WOLO transfer during relayer setup.
- Do not create the WOLO/USDC pool during relayer setup.
