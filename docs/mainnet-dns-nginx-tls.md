# WoloChain Mainnet DNS, Nginx, And TLS Plan

This is a planning document only. Do not edit nginx or certbot from this doc until Tony explicitly approves a deployment window.

## Endpoint Options

### Option A: Dedicated Subdomains

Recommended:

- RPC: `https://rpc.wolo.aoe2war.com`
- REST: `https://rest.wolo.aoe2war.com`
- Explorer: `https://explorer.wolo.aoe2war.com`

Pros:

- clean separation from the existing `aoe2war.com/rpc/` testnet path
- simpler for chain registry, Keplr, wallets, relayers, and explorer config
- avoids path-rewrite surprises with CometBFT RPC and Cosmos REST routes
- easier to move mainnet infra later without changing app paths
- clear public distinction between testnet and mainnet

Cons:

- requires DNS records for each host
- requires TLS certs for each host or a wildcard certificate
- requires separate nginx server blocks

### Option B: Path-Based Routes Under aoe2war.com

Possible:

- RPC: `https://aoe2war.com/wolo-mainnet/rpc/`
- REST: `https://aoe2war.com/wolo-mainnet/rest/`
- Explorer: `https://aoe2war.com/wolo-mainnet`

Pros:

- fewer DNS records
- can reuse the existing `aoe2war.com` certificate
- feels consistent with the current testnet route style

Cons:

- path prefixes can confuse clients that expect RPC or REST at the origin root
- more nginx rewrite risk
- less clean for chain registry, wallet, relayer, and explorer config
- increases collision risk with the AoE2War app shell

## Recommendation

Use dedicated subdomains for mainnet:

```text
rpc.wolo.aoe2war.com
rest.wolo.aoe2war.com
explorer.wolo.aoe2war.com
```

Keep the existing testnet routes unchanged:

```text
https://aoe2war.com/rpc/
https://aoe2war.com/rest/
https://aoe2war.com/wolo-testnet
```

## DNS Checklist

- Add `A` or `CNAME` record for `rpc.wolo.aoe2war.com`.
- Add `A` or `CNAME` record for `rest.wolo.aoe2war.com`.
- Add `A` or `CNAME` record for `explorer.wolo.aoe2war.com`.
- Decide whether seed or peer hostnames are needed.
- Verify DNS points to the intended VPS before requesting certs.

## TLS Checklist

- Issue or expand certificates only after DNS resolves.
- Prefer one certificate that covers all three mainnet subdomains if operationally convenient.
- Keep testnet certs and routes unchanged.
- Record certbot certificate names in the launch runbook.

## Nginx Proxy Targets

Recommended local mainnet targets:

```text
rpc.wolo.aoe2war.com      -> 127.0.0.1:27657
rest.wolo.aoe2war.com     -> 127.0.0.1:1318
explorer.wolo.aoe2war.com -> static explorer bundle for wolo-1
```

Nginx should not proxy mainnet traffic to testnet ports.

## Smoke Checks After Future Nginx Work

```bash
curl -fsS https://rpc.wolo.aoe2war.com/status
curl -fsS https://rest.wolo.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS 'https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/supply/by_denom?denom=uwolo'
curl -fsSI https://explorer.wolo.aoe2war.com
```

Expected mainnet chain ID is `wolo-1`. Do not accept `wolo-testnet` on mainnet endpoints.

