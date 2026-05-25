# Mainnet Nginx Prep

Planning only. Do not edit nginx or certbot until Tony approves a deployment window.

## Recommended Public Routes

```text
rpc.wolo.aoe2war.com      -> 127.0.0.1:27657
rest.wolo.aoe2war.com     -> 127.0.0.1:1318
explorer.wolo.aoe2war.com -> static explorer bundle for wolo-1
```

## Safety Checks

- Mainnet RPC must never proxy to `127.0.0.1:26657`.
- Mainnet REST must never proxy to `127.0.0.1:1317`.
- Mainnet explorer must never serve the testnet Ping/pub config.
- Mainnet endpoint smoke must report `wolo-1`, not `wolo-testnet`.

## Future Smoke Commands

Run only after a future approved launch:

```bash
curl -fsS https://rpc.wolo.aoe2war.com/status
curl -fsS https://rest.wolo.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS 'https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/supply/by_denom?denom=uwolo'
curl -fsS https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
curl -fsSI https://explorer.wolo.aoe2war.com
```

