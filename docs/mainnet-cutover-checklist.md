# WoloChain Mainnet Cutover Checklist

This is a planning checklist only. It is intentionally split into gates so mainnet is not launched accidentally.

## Gate 1: Tony Decisions

- Final chain ID approved: `wolo-1`
- Final supply approved: `100000000000000uwolo`
- Final allocation table approved.
- Final wallet list approved.
- Final custody model approved.
- Final endpoint plan approved.
- Final service names approved.
- Final port plan approved.
- Final explorer route approved.
- Final Keplr metadata approved.
- Final IBC/Osmosis plan reviewed separately.

## Gate 2: Fresh Keys

- Fresh validator/operator key generated.
- Fresh consensus key generated through the mainnet init flow.
- Fresh payout signer generated.
- Fresh escrow signer generated if settlement escrow launches with mainnet.
- Fresh treasury, rewards, liquidity, relayer, and reserve wallets generated.
- No testnet key material reused.
- Backups tested.
- Mnemonics never entered into git-tracked files.

## Gate 3: Fresh Genesis

- Fresh `wolo-1` genesis generated.
- Genesis chain ID is `wolo-1`.
- Denom metadata is `uwolo` / `wolo` / `WOLO` / `6`.
- Staking bond denom is `uwolo`.
- Mint denom is `uwolo`.
- Inflation and supply model match fixed-supply policy.
- Genesis balances sum exactly to `100000000000000uwolo`.
- No testnet balances were imported automatically.
- Gentx uses fresh validator keys.
- Genesis validates before service start.

## Gate 4: Separate Runtime

- Mainnet chain home is `/var/lib/wolochaind-mainnet`.
- Mainnet node service is `wolochaind-mainnet.service`.
- Mainnet settlement service is `wolochain-mainnet-settlement.service` only if deliberately deployed and verified; otherwise mainnet app verification uses RPC/REST tx lookup.
- Mainnet RPC binds `127.0.0.1:27657`.
- Mainnet REST binds `127.0.0.1:1318`.
- Mainnet P2P binds `0.0.0.0:27656`.
- Mainnet settlement API binds `127.0.0.1:8092`.
- Mainnet settlement state is separate from testnet.
- AoE2HDBets app signer home, if used, is mainnet-labeled and separate from the node home, for example `/var/lib/aoe2hdbets-wolo-mainnet`.
- Testnet services remain unchanged.

## Gate 5: Public Surface

- DNS resolves for mainnet RPC, REST, and explorer.
- TLS certs exist for mainnet hosts.
- Nginx proxies mainnet RPC to mainnet RPC port.
- Nginx proxies mainnet REST to mainnet REST port.
- Nginx returns CORS headers for `Origin: https://aoe2war.com` on mainnet RPC/REST.
- Explorer serves mainnet config.
- Keplr config points to mainnet endpoints.
- No mainnet endpoint reports `wolo-testnet`.

## Gate 6: Post-Launch Smoke

Run only after approved launch:

```bash
curl -fsS https://rpc-mainnet.aoe2war.com/status
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS 'https://rest-mainnet.aoe2war.com/cosmos/bank/v1beta1/supply/by_denom?denom=uwolo'
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/tx/v1beta1/txs/3D660226EF33143B62F5BFE922DB84FC8FF224938DD49166A5ABC27DD8874EDD
curl -i -X OPTIONS https://rpc-mainnet.aoe2war.com/ \
  -H 'Origin: https://aoe2war.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Expected:

- chain ID: `wolo-1`
- supply: `100000000000000uwolo`
- metadata base: `uwolo`
- metadata display: `wolo`
- metadata symbol: `WOLO`
- decimals: `6`
- CORS preflight returns `204` with `Access-Control-Allow-Origin: https://aoe2war.com`

## Rollback Boundary

If mainnet launch fails before public use:

- stop only mainnet services
- preserve failed mainnet logs and generated files for diagnosis
- do not touch `wolo-testnet`
- do not touch `/var/lib/wolochaind-testnet`
- do not touch testnet settlement state
- do not change AoE2War app endpoints until mainnet is healthy

There is no rollback path that converts testnet into mainnet. They are separate chains.
