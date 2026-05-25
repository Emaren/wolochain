# WoloChain Mainnet Keplr And Explorer Plan

This is a planning document only. Do not deploy Keplr or explorer config from this doc until the mainnet endpoint plan is approved.

## Mainnet Metadata

| Field | Recommended Value |
| --- | --- |
| `chain_id` | `wolo-1` |
| `chain_name` | `WoloChain` |
| `pretty_name` | `WoloChain` |
| `network_type` | `mainnet` |
| RPC | `https://rpc.wolo.aoe2war.com` |
| REST | `https://rest.wolo.aoe2war.com` |
| Explorer | `https://explorer.wolo.aoe2war.com` |
| Bech32 account prefix | `wolo` |
| Bech32 validator operator prefix | `wolovaloper` |
| Bech32 consensus prefix | `wolovalcons` |
| Coin type | `118` |
| Base denom | `uwolo` |
| Display denom | `wolo` |
| Symbol | `WOLO` |
| Decimals | `6` |
| Minimum fee denom | `uwolo` |
| Suggested gas price | `0.025uwolo` |
| Logo | final `wolo-keplr-256.png` URL under the mainnet explorer or static asset host |

## Keplr Chain Suggestion Skeleton

```json
{
  "chainId": "wolo-1",
  "chainName": "WoloChain",
  "rpc": "https://rpc.wolo.aoe2war.com",
  "rest": "https://rest.wolo.aoe2war.com",
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
        "low": 0.001,
        "average": 0.025,
        "high": 0.05
      }
    }
  ],
  "stakeCurrency": {
    "coinDenom": "WOLO",
    "coinMinimalDenom": "uwolo",
    "coinDecimals": 6
  },
  "features": ["stargate"]
}
```

Add `ibc-transfer` only after IBC transfer readiness is verified.

## Explorer Config Checklist

Explorer config must be separate from testnet:

- chain name: `wolo-1`
- registry name: `wolo-1`
- network type: `mainnet`
- REST provider: `https://rest.wolo.aoe2war.com`
- RPC provider: `https://rpc.wolo.aoe2war.com`
- address prefix: `wolo`
- base denom: `uwolo`
- symbol: `WOLO`
- exponent: `6`
- logo URL: final mainnet logo URL
- explorer route: `https://explorer.wolo.aoe2war.com`

Do not overwrite `chains/testnet/wolo.json` in the Ping.pub repo for mainnet. Add a separate mainnet chain config.

## Verification

Before publishing mainnet explorer config:

```bash
curl -fsS https://rpc.wolo.aoe2war.com/status
curl -fsS https://rest.wolo.aoe2war.com/cosmos/base/tendermint/v1beta1/node_info
curl -fsS https://rest.wolo.aoe2war.com/cosmos/bank/v1beta1/denoms_metadata/uwolo
```

Reject the config if any response reports `wolo-testnet` instead of `wolo-1`.

