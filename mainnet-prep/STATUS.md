# WoloChain wolo-1 Mainnet Prep Status

Status: WoloChain mainnet is live; WoloChain mainnet to Osmosis mainnet IBC path is open; no WOLO transfer, liquidity action, or WOLO/USDC pool creation has happened.

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

## Remaining Not Done

- No WOLO transfer over IBC has been performed.
- No Osmosis-side WOLO denom trace has been recorded.
- No 200,000 WOLO liquidity transfer has been performed.
- No Osmosis liquidity has been created.
- No WOLO/USDC Osmosis pool has been created.
- `wolo-testnet` has not been touched.

## Next Phase

Phase 4 should be a tiny 1 WOLO test transfer only, after Tony explicitly confirms.

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

## Private Relayer Mnemonic File Update

Fresh relayer-only mnemonic files were created privately on the VPS outside git.

Confirmed:

- Mnemonic command exists:
  - `/usr/local/bin/wolochaind-mainnet keys mnemonic`
- Private directory:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material`
- Directory permissions:
  - `0700 root:root`
- Wolo relayer mnemonic file:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/wolo-relayer.mnemonic`
  - permissions: `0600 root:root`
  - word count: `24`
- Osmosis relayer mnemonic file:
  - `/root/wolo-1-mainnet-prep-markers/private-relayer-key-material/osmosis-relayer.mnemonic`
  - permissions: `0600 root:root`
  - word count: `24`
- Mnemonic contents were not displayed, printed, echoed, catted, or copied into the repo.
- These are relayer gas wallet mnemonics only.
- They are not liquidity wallets, Founder Cold, Community Treasury, or DEX Liquidity Reserve.
- No keys were imported into Hermes.
- No relayer addresses are available yet.
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not modified.
- No IBC clients, connections, or channels have been created.
- No WOLO transfer, OSMO transfer, liquidity action, or WOLO/USDC pool creation has happened.

Next step:

Phase 2.9 should import the mnemonic files into Hermes, list the resulting relayer addresses, and stop before gas funding or Phase 3 unless Tony explicitly confirms.

## Relayer Key Import Update

Relayer-only gas keys were imported into the dedicated WoloChain mainnet Osmosis Hermes home.

Confirmed:

- Hermes home:
  - `/var/lib/wolochain-mainnet-relayer`
- Wolo relayer key name:
  - `wolo-mainnet-osmosis-relayer`
- Wolo relayer address:
  - `wolo1m8qzq92hkktgqp47aewzylkatk6c22vc8c4vgj`
- Osmosis relayer key name:
  - `osmosis-mainnet-wolo-relayer`
- Osmosis relayer address:
  - `osmo1tu4gfazupfyhf7zcxmtzvkuynaclgkaavhj4g7`
- Wolo key file:
  - `/var/lib/wolochain-mainnet-relayer/.hermes/keys/wolo-1/keyring-test/wolo-mainnet-osmosis-relayer.json`
- Osmosis key file:
  - `/var/lib/wolochain-mainnet-relayer/.hermes/keys/osmosis-1/keyring-test/osmosis-mainnet-wolo-relayer.json`
- Key file permissions:
  - `0600 root:root`
- Mnemonic contents were not displayed, printed, echoed, catted, logged, or copied into the repo.
- Wolo relayer balance:
  - `0 uwolo`
- Osmosis relayer balance:
  - `0 uosmo`
- These are relayer gas wallets only.
- They are not liquidity wallets, Founder Cold, Community Treasury, or DEX Liquidity Reserve.
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not modified.
- No IBC clients, connections, or channels have been created.
- No WOLO transfer, OSMO transfer, liquidity action, or WOLO/USDC pool creation has happened.

Next step:

Fund only the relayer gas wallets with small `uwolo` and `uosmo` amounts, then stop before Phase 3 IBC path creation until Tony explicitly confirms.

## WoloChain Osmosis IBC Path Update

WoloChain mainnet `wolo-1` is now connected to Osmosis mainnet `osmosis-1` for ICS-20 transfer.

Confirmed:

- Hermes config:
  - `/etc/wolochain-mainnet/hermes-osmosis.toml`
- Hermes home:
  - `/var/lib/wolochain-mainnet-relayer`
- Wolo client ID:
  - `07-tendermint-0`
- Osmosis client ID:
  - `07-tendermint-3705`
- Wolo connection ID:
  - `connection-0`
- Osmosis connection ID:
  - `connection-11058`
- Wolo transfer channel ID:
  - `channel-0`
- Osmosis transfer channel ID:
  - `channel-110224`
- Channel state is open on both sides.
- Port is `transfer` on both sides.
- Ordering is `unordered`.
- Channel version is `ics20-1`.
- Wolo relayer balance after path creation:
  - `99998485uwolo`
- Osmosis relayer balance after path creation:
  - `199266uosmo`
- Marker written on the VPS:
  - `/root/wolo-1-mainnet-prep-markers/wolo-osmosis-ibc-path-20260525T070440Z.txt`
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- `tokenchain-relayer.service` remains active and was not stopped or modified.
- `/etc/tokenchain/hermes.toml` was not touched.
- No WOLO transfer, OSMO transfer, 200,000 WOLO liquidity transfer, liquidity action, or WOLO/USDC pool creation happened.

Operational note:

- Osmosis primary RPC `https://rpc.osmosis.zone` returned HTTP 429 during proof-bearing Hermes steps.
- The isolated WoloChain Hermes config was backed up before each Osmosis endpoint fallback.
- Current Osmosis RPC in the WoloChain Hermes config:
  - `https://osmosis.rpc.kjnodes.com`
- Current Osmosis gRPC in the WoloChain Hermes config:
  - `https://grpc.osmosis.validatus.com:443`

Next step:

Phase 4 should perform only a tiny 1 WOLO test transfer, base amount `1000000uwolo`, over Wolo channel `channel-0` after Tony explicitly confirms.
