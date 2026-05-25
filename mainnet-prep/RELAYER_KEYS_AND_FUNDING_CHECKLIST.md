# Relayer Keys and Funding Checklist

Status: preparation checklist only. Do not create keys, fund wallets, create IBC clients/channels, transfer WOLO, transfer OSMO, create liquidity, or create the WOLO/USDC pool without Tony's explicit confirmation.

## Required Hermes Keys

- WoloChain mainnet key name: `wolo-mainnet-osmosis-relayer`
- Osmosis mainnet key name: `osmosis-mainnet-wolo-relayer`

These are relayer gas wallets only. They are not liquidity wallets.

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

Prepared import commands, NOT RUN:

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
- Do not transfer from the WOLO DEX Liquidity Reserve for relayer gas unless Tony explicitly chooses that source for a tiny gas amount.
- The 200,000 WOLO liquidity transfer remains separate.
- The 200,000 WOLO liquidity transfer must come from the WOLO DEX Liquidity Reserve only after Tony confirms:
  - `wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en`
- Do not execute the 200,000 WOLO transfer during relayer setup.
- Do not create the WOLO/USDC pool during relayer setup.

