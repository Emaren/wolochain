---
id: "aoe2war.wolochain.osmosis-test-transfer"
title: "WoloChain Mainnet → Osmosis Test Transfer"
type: "historical"
status: "historical"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "historical-evidence"
authority: "ibc-test-transfer-receipt"
reviewed_at: "2026-08-10"
review_interval_days: 0
sensitivity: "internal"
---

# WoloChain Mainnet → Osmosis Test Transfer

Status: complete.

## Transfer

- Amount: `1000000uwolo`
- Display amount: `1 WOLO`
- Source chain: `wolo-1`
- Destination chain: `osmosis-1`
- Source port: `transfer`
- Source channel: `channel-0`
- Destination channel: `channel-110224`
- Sender: `wolo1nalsh7y0hzp33j996c90yxqgerxxvgpqtumfjt`
- Receiver: `osmo1yyuu097eppte7qya48r3dth86smdl3sjyx7qc6`
- Tx hash: `63877698D884CE7BC92002F97A24333102DB21F52E8343C3997F9E8D5BBB5C08`
- Packet sequence: `1`

## Osmosis WOLO Denom

- Trace: `transfer/channel-110224/uwolo`
- Osmosis denom: `ibc/D09120C7085DFA412DF77608DAD3A4797F5F097A038DA0C2E1D1426FC9CD836D`

## Relay Result

Hermes successfully relayed:

- `WriteAcknowledgement` on Osmosis
- `AcknowledgePacket` back on WoloChain

## Safety Confirmations

- No `200,000 WOLO` liquidity transfer happened.
- No liquidity was created.
- No WOLO/USDC pool was created.
- TokenChain relayer was not modified.
- Wolo mainnet relayer service was not started as a long-running service.

## Next Step

After Tony confirms, transfer `200000000000uwolo` / `200,000 WOLO` from the WOLO DEX Liquidity Reserve to the Osmosis wallet over `channel-0`, then create the WOLO/USDC pool with `20 USDC`.
