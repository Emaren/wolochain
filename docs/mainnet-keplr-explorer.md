# WoloChain Mainnet Keplr And Explorer Metadata

This document records the current `wolo-1` mainnet metadata that wallets, registries, explorers, and AoE2HDBets should treat as chain truth.

## Current Mainnet Metadata

| Field | Value |
| --- | --- |
| `chain_id` | `wolo-1` |
| `chain_name` | `WoloChain` |
| `pretty_name` | `WoloChain` |
| `network_type` | `mainnet` |
| RPC | `https://rpc-mainnet.aoe2war.com` |
| REST | `https://rest-mainnet.aoe2war.com` |
| RPC path alias | `https://aoe2war.com/rpc-mainnet/` |
| REST path alias | `https://aoe2war.com/rest-mainnet/` |
| Browser origin allowed by RPC/REST CORS | `https://aoe2war.com` |
| Explorer | not yet verified as a separate mainnet explorer route |
| Bech32 account prefix | `wolo` |
| Bech32 validator operator prefix | `wolovaloper` |
| Bech32 consensus prefix | `wolovalcons` |
| Coin type | `118` |
| Base denom | `uwolo` |
| Display unit | `wolo` |
| Human symbol | `WOLO` |
| Decimals | `6` |
| Minimum fee denom | `uwolo` |
| Suggested gas price | `0.025uwolo` |

Reject wallet, registry, or explorer config for mainnet if it reports `wolo-testnet`, uses `https://aoe2war.com/rpc/`, uses `https://aoe2war.com/rest/`, or depends on the old `/wolo-testnet` explorer route.

Keplr/CosmJS browser signing also requires the public mainnet RPC to answer `Origin: https://aoe2war.com` preflights and POSTs with CORS headers. A chain suggestion that points at the right RPC still fails in-browser if nginx strips those headers.

## Keplr Chain Suggestion

```json
{
  "chainId": "wolo-1",
  "chainName": "WoloChain",
  "rpc": "https://rpc-mainnet.aoe2war.com",
  "rest": "https://rest-mainnet.aoe2war.com",
  "bip44": {
    "coinType": 118
  },
  "bech32Config": {
    "bech32PrefixAccAddr": "wolo",
    "bech32PrefixAccPub": "wolopub",
    "bech32PrefixValAddr": "wolovaloper",
    "bech32PrefixValPub": "wolovaloperpub",
    "bech32PrefixConsAddr": "wolovalcons",
    "bech32PrefixConsPub": "wolovalconspub"
  },
  "currencies": [
    {
      "coinDenom": "WOLO",
      "coinMinimalDenom": "uwolo",
      "coinDecimals": 6
    }
  ],
  "feeCurrencies": [
    {
      "coinDenom": "WOLO",
      "coinMinimalDenom": "uwolo",
      "coinDecimals": 6,
      "gasPriceStep": {
        "low": 0.01,
        "average": 0.025,
        "high": 0.04
      }
    }
  ],
  "stakeCurrency": {
    "coinDenom": "WOLO",
    "coinMinimalDenom": "uwolo",
    "coinDecimals": 6
  },
  "features": ["stargate", "ibc-transfer"]
}
```

## Explorer Boundary

The live chain truth is the `wolo-1` RPC/REST surface above. A separate mainnet explorer route should only be advertised after it is configured to read `wolo-1`, `uwolo`, `wolo`, `WOLO`, exponent `6`, and the `wolo` bech32 prefix from the mainnet endpoints.

The old `https://aoe2war.com/wolo-testnet` route is allowed to remain as a legacy testnet surface, but it must not be linked or labeled as current mainnet. If a mainnet explorer is added later, add a separate mainnet chain config rather than overwriting a testnet config in place.

## Verification

```bash
curl -fsS https://rpc-mainnet.aoe2war.com/status
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
curl -fsS https://rest-mainnet.aoe2war.com/cosmos/tx/v1beta1/txs/3D660226EF33143B62F5BFE922DB84FC8FF224938DD49166A5ABC27DD8874EDD
```

Expected results:

- RPC and REST report `wolo-1`.
- RPC `other.tx_index` is `on`.
- denom metadata reports base `uwolo`, display `wolo`, symbol `WOLO`, and exponent `6`.
- the tx lookup by hash returns a mainnet transaction, proving AoE2HDBets can verify signed stake or escrow txs against chain truth.
