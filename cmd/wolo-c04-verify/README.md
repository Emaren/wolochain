# C04 — bounded original-request / chain-proof observation

The `wolo-c04-verify` CLI is a strictly **noncrediting, root-only** historical proof reader. It joins a SHA-256 fingerprint of the original settlement request ID (not the request ID itself) to one protected recorded `accepted` request, then reuses `internal/satchel.ChainReader.ReadTransfer` to cross-check the **actual immutable memo, sender, recipient, amount, MsgSend bytes, CometBFT transaction Merkle proof and H/H+1 result commitments**. It outputs only the public hash, block height/hash, source fingerprint and explicit refusal booleans. The original wallet addresses, memo and request ID never appear in reports or diagnostics.

Example from the root-only financial host, **read-only**:

```sh
wolo-c04-verify --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state \
  --request-fingerprint 2ed7062c8d9c44411401e4705fac55159dc3b2d936ad962459ef2869b126c020 \
  --tx-hash D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699 \
  --rpc https://aoe2war.com/rpc-mainnet --rest https://aoe2war.com/rest-mainnet
```

All outcomes deliberately exit with code 3 / HOLD, including cryptographically consistent positive candidates. A primary public RPC operated by AoE2WAR is **not** an independently trusted consensus witness; adding another operator URL does not automatically prove independence. No missing/failed/ambiguous read may authorize retry. The separate founder #889 claim is not reconciled by this check. Source QA: `go test ./cmd/wolo-c04-verify` plus `go vet ./cmd/wolo-c04-verify`; `go test ./...` in CI already includes this command.
