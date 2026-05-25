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
