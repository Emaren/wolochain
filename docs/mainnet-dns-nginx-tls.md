# WoloChain Mainnet DNS, Nginx, And TLS

The currently verified mainnet public endpoints are:

- RPC: `https://rpc-mainnet.aoe2war.com`
- REST: `https://rest-mainnet.aoe2war.com`
- RPC path alias: `https://aoe2war.com/rpc-mainnet/`
- REST path alias: `https://aoe2war.com/rest-mainnet/`

The earlier planned hosts `rpc.wolo.aoe2war.com`, `rest.wolo.aoe2war.com`, and `explorer.wolo.aoe2war.com` were not the verified live hosts during the June 1, 2026 check. Do not publish them in wallet, registry, or AoE2HDBets config unless DNS, TLS, and smoke checks are completed first.

## Nginx Proxy Targets

Verified mainnet targets:

```text
rpc-mainnet.aoe2war.com  -> 127.0.0.1:27657
rest-mainnet.aoe2war.com -> 127.0.0.1:1318
```

Path aliases under `aoe2war.com` are also present:

```text
/rpc-mainnet/  -> 127.0.0.1:27657
/rest-mainnet/ -> 127.0.0.1:1318
```

The dedicated public mainnet hosts must allow browser-origin requests from `https://aoe2war.com`:

```text
Access-Control-Allow-Origin: https://aoe2war.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

This is required for Keplr/CosmJS browser wallet broadcasts to `https://rpc-mainnet.aoe2war.com` and browser REST reads from `https://rest-mainnet.aoe2war.com`.

RPC WebSocket subscriptions must also preserve HTTP/1.1 upgrade headers when nginx proxies to CometBFT:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

Without those headers, valid browser or wallet clients can reach CometBFT's `/websocket` endpoint as plain HTTP and trigger noisy daemon logs like `websocket: the client is not using the websocket protocol`.

The old paths below are testnet-era surfaces and must not be presented as `wolo-1`:

```text
https://aoe2war.com/rpc/
https://aoe2war.com/rest/
https://aoe2war.com/wolo-testnet
```

## Smoke Checks

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
curl --http1.1 -i --max-time 3 https://rpc-mainnet.aoe2war.com/websocket \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13'
```

Expected mainnet chain ID is `wolo-1`. Do not accept `wolo-testnet` on mainnet endpoints. RPC `other.tx_index` must remain `on` so AoE2HDBets can verify signed mainnet stake and escrow transactions by hash.

## Future Explorer Host

A separate mainnet explorer can be added later, but it must read from `https://rpc-mainnet.aoe2war.com` and `https://rest-mainnet.aoe2war.com`, use `wolo-1`, and display `uwolo` / `wolo` / `WOLO` with exponent `6`. Keep any legacy testnet explorer route explicitly labeled testnet.
