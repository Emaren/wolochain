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
