# WoloChain Mainnet Nginx Notes

Verified public mainnet routing:

```text
rpc-mainnet.aoe2war.com  -> 127.0.0.1:27657
rest-mainnet.aoe2war.com -> 127.0.0.1:1318
```

The `aoe2war.com` app host also exposes:

```text
/rpc-mainnet/  -> 127.0.0.1:27657
/rest-mainnet/ -> 127.0.0.1:1318
```

Mainnet RPC must never proxy to `127.0.0.1:26657`.
Mainnet REST must never proxy to `127.0.0.1:1317`.
Mainnet endpoint smoke must report `wolo-1`, not `wolo-testnet`.
Browser-origin wallet traffic from `https://aoe2war.com` must receive CORS headers on both public mainnet hosts.

Smoke:

```bash
curl -fsS https://rpc-mainnet.aoe2war.com/status
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS 'https://rest-mainnet.aoe2war.com/cosmos/bank/v1beta1/supply/by_denom?denom=uwolo'
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/tx/v1beta1/txs/3D660226EF33143B62F5BFE922DB84FC8FF224938DD49166A5ABC27DD8874EDD
```

CORS smoke:

```bash
curl -i -X OPTIONS https://rpc-mainnet.aoe2war.com/ \
  -H 'Origin: https://aoe2war.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'

curl -i -X OPTIONS https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info \
  -H 'Origin: https://aoe2war.com' \
  -H 'Access-Control-Request-Method: GET'

curl https://rpc-mainnet.aoe2war.com/ \
  -H 'Origin: https://aoe2war.com' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"broadcast_tx_sync","params":{"tx":"AAAA"}}'
```

Expected:

- preflights return `204`
- `Access-Control-Allow-Origin: https://aoe2war.com`
- the invalid broadcast reaches CometBFT and returns a tx parse error, not a browser CORS failure

A separate mainnet explorer route can be added later, but it should read from the verified mainnet RPC/REST endpoints and must be labeled separately from the legacy testnet explorer.
