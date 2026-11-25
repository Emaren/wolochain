---
id: "aoe2war.wolochain.mainnet-nginx-notes"
title: "WoloChain Mainnet Nginx Notes"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "runtime-evidence"
authority: "mainnet-nginx-routing-reference"
reviewed_at: "2026-11-10"
review_interval_days: 30
sensitivity: "internal"
---

# WoloChain Mainnet Nginx Notes

## Current read-only Nginx/API review — 2026-11-10 UTC

HEL1 nginx.service was active; read-only nginx -T showed the mainnet hosts/path aliases forwarding to 127.0.0.1:27657 and 127.0.0.1:1318. HTTPS RPC/REST and both app aliases returned HTTP 200 with TLS verification result 0. RPC OPTIONS returned HTTP 204 and Access-Control-Allow-Origin https://aoe2war.com; REST OPTIONS returned HTTP 204 and origin *, with the documented HTTP methods. wolo-1 was confirmed on both API types. Older Nginx references to ports 26657/1317 do not by themselves identify a mainnet host route. No Nginx reload, proxy edit or signing transaction occurred; future releases still require verified rollback.

## Review Scope — 2026-10-10 UTC

Public RPC/REST identity and CORS reconfirmed. Internal proxy target configuration was not independently inspected.

No runtime, wallet, liquidity, settlement, or chain mutation was performed during this documentation review.

## Review Renewal — 2026-09-09 UTC

Read-only smoke checks reconfirmed `rpc-mainnet.aoe2war.com` and
`rest-mainnet.aoe2war.com` serving `wolo-1`. RPC CORS returned the explicit
AoE2WAR origin and REST returned a permissive wildcard; both accept
`https://aoe2war.com`. Nginx remained active. No proxy, TLS, DNS, or runtime
configuration was changed.

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
