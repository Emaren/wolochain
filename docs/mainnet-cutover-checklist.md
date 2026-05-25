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
- Mainnet settlement service is `wolochain-mainnet-settlement.service`.
- Mainnet RPC binds `127.0.0.1:27657`.
- Mainnet REST binds `127.0.0.1:1318`.
- Mainnet P2P binds `0.0.0.0:27656`.
- Mainnet settlement API binds `127.0.0.1:8092`.
- Mainnet settlement state is separate from testnet.
- Testnet services remain unchanged.

## Gate 5: Public Surface

- DNS resolves for mainnet RPC, REST, and explorer.
- TLS certs exist for mainnet hosts.
- Nginx proxies mainnet RPC to mainnet RPC port.
- Nginx proxies mainnet REST to mainnet REST port.
- Explorer serves mainnet config.
- Keplr config points to mainnet endpoints.
- No mainnet endpoint reports `wolo-testnet`.

## Gate 6: Post-Launch Smoke

Run only after approved launch:

```bash
curl -fsS https://rpc.wolo.aoe2war.com/status
curl -fsS https://rest.wolo.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS 'https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/supply/by_denom?denom=uwolo'
curl -fsS https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
curl -fsSI https://explorer.wolo.aoe2war.com
```

Expected:

- chain ID: `wolo-1`
- supply: `100000000000000uwolo`
- metadata base: `uwolo`
- metadata display: `wolo`
- metadata symbol: `WOLO`
- decimals: `6`

## Rollback Boundary

If mainnet launch fails before public use:

- stop only mainnet services
- preserve failed mainnet logs and generated files for diagnosis
- do not touch `wolo-testnet`
- do not touch `/var/lib/wolochaind-testnet`
- do not touch testnet settlement state
- do not change AoE2War app endpoints until mainnet is healthy

There is no rollback path that converts testnet into mainnet. They are separate chains.

