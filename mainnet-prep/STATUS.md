# WoloChain wolo-1 Mainnet Prep Status

Status: local prep complete through draft genesis validation.

## Completed

- Created `wolo-1-mainnet-prep` branch.
- Created mainnet prep package under `mainnet-prep/`.
- Created 8 real Keplr `wolo1...` recipient wallets.
- Updated `mainnet-prep/genesis/allocation-template.csv`.
- Verified total supply:
  - `100000000000000uwolo`
  - `100000000 WOLO`
- Verified genesis readiness:
  - `ready_for_genesis: true`
  - placeholders: `0`
  - real addresses: `8`
  - blockers: none
  - warnings: none
- Built disposable draft chain home:
  - `build/mainnet-prep/wolo-1-home`
- Validated draft genesis:
  - chain_id: `wolo-1`
  - balance count: `8`
  - supply: `100000000000000uwolo`
  - errors: none
- Go tests pass.
- Go build passes.

## Not Done Yet

- Mainnet has not launched.
- Final genesis has not been installed.
- No VPS mainnet service has been started.
- No validator key has been created.
- No validator gentx has been created.
- No IBC channels have been created.
- No Osmosis liquidity has been created.
- `wolo-testnet` has not been touched.

## Next Phase

VPS launch-host staging:

1. Sync this prep branch to the VPS in a separate path.
2. Build the mainnet binary there.
3. Prepare `/var/lib/wolochaind-mainnet`.
4. Create/import the fresh mainnet validator key on the VPS.
5. Generate the validator gentx.
6. Validate final genesis.
7. Stop before starting mainnet services until final review.

## Launch Update

`wolo-1` mainnet was launched on the VPS.

Confirmed:

- `wolochaind-mainnet.service` is active.
- RPC is listening on `127.0.0.1:27657`.
- REST is listening on `127.0.0.1:1318`.
- P2P is listening on `0.0.0.0:27656`.
- Chain ID is `wolo-1`.
- Blocks are being produced.
- Validator voting power is `1000`.
- `wolochaind-testnet.service` remained active.
- `wolochain-settlement.service` remained active.

Next steps:

1. Clean pprof/log warnings.
2. Add public Nginx routes for mainnet RPC/REST.
3. Update AoE2War/Keplr/explorer configs.
4. Add monitoring checks.
5. Do not create Osmosis liquidity until public endpoints and explorer are stable.

## Public Endpoint Update

Public HTTPS endpoints are live:

- RPC: `https://rpc-mainnet.aoe2war.com/status`
- REST: `https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info`

Confirmed:

- RPC reports network `wolo-1`.
- RPC block height is increasing.
- RPC reports `catching_up: false`.
- Validator voting power is `1000`.
- REST reports network `wolo-1`.
- Nginx is active.
- `wolochaind-mainnet.service` is active.

Next steps:

1. Add mainnet endpoint monitoring.
2. Update Keplr config for `wolo-1`.
3. Update explorer config for `wolo-1`.
4. Update AoE2War app wallet/network surfaces.
5. Delay Osmosis liquidity until explorer and wallet UX are confirmed stable.

## Monitoring Update

Mainnet health monitoring is installed.

Confirmed:

- `/usr/local/bin/check-wolo-mainnet-health` exists.
- `wolo-mainnet-health.timer` is enabled and active.
- `wolo-mainnet-health.service` runs successfully.
- Health check validates:
  - `wolochaind-mainnet.service` is active.
  - Nginx is active.
  - Public HTTPS RPC responds.
  - Public HTTPS REST responds.
  - Chain ID is `wolo-1`.
  - `catching_up` is false.
  - Block height is increasing.

Latest observed health output:

```txt
OK: wolo-1 healthy height=138 catching_up=False
```

Next steps:

1. Wire mainnet into Keplr/AoE2War wallet UX.
2. Add explorer mainnet config.
3. Add VPSSentry/Traffic visibility for mainnet health.
4. Delay Osmosis liquidity until wallet and explorer surfaces are stable.

## Osmosis Relayer Staging Update

WoloChain mainnet Osmosis Hermes relayer staging is documented.

Confirmed:

- Dedicated config staged on the VPS:
  - `/etc/wolochain-mainnet/hermes-osmosis.toml`
- Dedicated service unit staged on the VPS:
  - `/etc/systemd/system/wolochain-mainnet-osmosis-relayer.service`
- Dedicated relayer home staged on the VPS:
  - `/var/lib/wolochain-mainnet-relayer`
- Hermes config validation passed.
- Systemd unit validation passed.
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not modified.
- No IBC clients, connections, or channels have been created.
- No WOLO transfer, liquidity action, or WOLO/USDC pool creation has happened.

Next steps:

1. Review `mainnet-prep/HERMES_OSMOSIS_RELAYER_STAGING.md`.
2. Review `mainnet-prep/RELAYER_KEYS_AND_FUNDING_CHECKLIST.md`.
3. Create/import dedicated relayer gas keys only after Tony confirms.
4. Fund only the dedicated relayer gas wallets with small `uwolo` and `uosmo` amounts.
5. Stop before Phase 3 IBC path creation until Tony explicitly confirms.

## Relayer Keys and Funding Prep Update

WoloChain mainnet Osmosis relayer key state was inspected using the dedicated Hermes home and config.

Confirmed:

- Dedicated Hermes home used:
  - `/var/lib/wolochain-mainnet-relayer`
- Dedicated Hermes config used:
  - `/etc/wolochain-mainnet/hermes-osmosis.toml`
- `wolo-mainnet-osmosis-relayer` is not present yet.
- `osmosis-mainnet-wolo-relayer` is not present yet.
- No relayer addresses are available yet.
- `uwolo` balance check is blocked by the missing Wolo relayer key.
- `uosmo` balance check is blocked by the missing Osmosis relayer key.
- No relayer keys were generated or imported.
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not modified.
- No IBC clients, connections, or channels have been created.
- No WOLO transfer, OSMO transfer, liquidity action, or WOLO/USDC pool creation has happened.

Next steps:

1. Tony confirms the secure relayer key creation/import method.
2. Import dedicated relayer gas keys into Hermes without exposing private material.
3. Record the Wolo and Osmosis relayer gas wallet addresses.
4. Fund those gas wallets only with small `uwolo` and `uosmo` amounts.
5. Stop before Phase 3 IBC path creation until Tony explicitly confirms.

## Secure Relayer Key Import Plan Update

WoloChain mainnet Osmosis relayer key creation/import planning is documented.

Confirmed:

- Hermes supports importing a relayer key from a mnemonic file.
- Hermes supports importing a relayer key from a Comet keyring JSON file.
- The installed Hermes CLI does not expose an internal fresh-key generation command that avoids supplying private key material.
- No relayer keys were created or imported.
- No mnemonics or private keys were displayed.
- Prepared private-material directory path:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material`
- Prepared Wolo mnemonic placeholder:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic`
- Prepared Osmosis mnemonic placeholder:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic`
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not modified.
- No IBC clients, connections, or channels have been created.
- No WOLO transfer, OSMO transfer, liquidity action, or WOLO/USDC pool creation has happened.

Next steps:

1. Tony explicitly confirms the mnemonic-file or key-file import workflow.
2. Create/import the two dedicated relayer gas keys without exposing private material.
3. Record the Wolo and Osmosis relayer gas addresses.
4. Fund only those relayer gas wallets with small `uwolo` and `uosmo` amounts.
5. Stop before Phase 3 IBC path creation until Tony explicitly confirms.
