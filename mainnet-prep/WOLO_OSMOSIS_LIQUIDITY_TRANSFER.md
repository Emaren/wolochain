# WoloChain Mainnet → Osmosis Liquidity Transfer

Status: complete.

## Transfer

- Amount: `200000000000uwolo`
- Display amount: `200,000 WOLO`
- Source chain: `wolo-1`
- Destination chain: `osmosis-1`
- Source port: `transfer`
- Source channel: `channel-0`
- Destination channel: `channel-110224`
- Sender: `wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en`
- Receiver: `osmo1yyuu097eppte7qya48r3dth86smdl3sjyx7qc6`
- Tx hash: `6A324B8070FF558B0188F3B0DD3E290BA8594A94E3C3500757D35808BB9C81D5`
- Packet sequence: `2`

## Osmosis WOLO Denom

- Trace: `transfer/channel-110224/uwolo`
- Osmosis denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`

## Expected Osmosis Balance

- Prior test transfer: `1000000uwolo`
- Liquidity transfer: `200000000000uwolo`
- Expected total: `200001000000uwolo`
- Display total: `200,001 WOLO`

## Safety Confirmations

- Liquidity transfer came from the WOLO DEX Liquidity Reserve.
- No Founder Cold funds were used.
- No Community Treasury funds were used.
- No pool has been created yet.

## Next Step

Create the first WOLO/USDC Osmosis pool:

- `200,000 WOLO`
- `20 USDC`
- Initial price: `1 WOLO = 0.0001 USDC`
