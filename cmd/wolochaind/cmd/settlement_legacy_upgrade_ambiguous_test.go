package cmd

// Regression contract for upgrading the exact October 1 legacy settlement
// writer to a source with durable PRE-broadcast markers. These tests intentionally
// fail on the held current implementation. They MUST NOT use live chain access.
//
// The old writer classified RPC/timeout errors after invoking the bank-send CLI
// as Retryable=true even when the CLI did not report a tx hash. An old on-disk
// result therefore cannot prove the payout did not already reach the chain.
// The new prebroadcast hold protects NEW calls but cannot undo that historical
// uncertainty. A source upgrade must never retry such legacy records.

import (
    "testing"
)

func TestUpgradeRefusesLegacyPostBroadcastUnknownWithoutSignerRetry(t *testing.T) {
    const payout = "wolo14hteq5qgk8gzme3z2d20enyyannru3hgpue70n"
    const recipient = "wolo1uyge4kml7ecajn8gjrvgeuw0h2fq4alywnf7ux"

    for _, tc := range []struct {
        name   string
        role   string
        escrow bool
    }{
        {name: "payout-legacy-rpc-timeout", role: settlementSignerRole},
        {name: "escrow-legacy-rpc-timeout", role: settlementEscrowSignerRole, escrow: true},
    } {
        t.Run(tc.name, func(t *testing.T) {
            cfg := newTestSettlementConfig(t, payout, map[string]string{payout: "10000000000"})
            request := settlementExecuteRequest{
                RequestID:   "legacy-uncertain-" + tc.name,
                ToAddress:   recipient,
                AmountUWolo: "100",
                Memo:        "original-october1-ambiguous",
            }
            normalized, err := normalizeSettlementRequest(request)
            if err != nil {
                t.Fatal(err)
            }
            normalized.SignerRole = tc.role
            path := cfg.requestRecordPath(normalized.RequestID)
            legacy := settlementStoredResult{
                Request: normalized,
                Fingerprint: hashSettlementRequest(normalized, payout),
                Response: settlementExecuteResponse{
                    OK:            false,
                    Status:        "failed",
                    FailureCode:   "RPC_UNREACHABLE",
                    Retryable:     true,
                    RequestID:     normalized.RequestID,
                    ChainID:       cfg.ChainID,
                    SignerRole:    tc.role,
                    SignerAddress: payout,
                    ToAddress:     normalized.ToAddress,
                    AmountUWolo:   normalized.AmountUWolo,
                },
            }
            // Written in the exact old JSON result shape (no prebroadcast
            // marker), like an interrupted live legacy RPC send.
            if err := writeSettlementStoredResult(path, legacy); err != nil {
                t.Fatal(err)
            }

            var got settlementExecuteResponse
            if tc.escrow {
                got, err = cfg.executeEscrowTransfer(t.Context(), request)
            } else {
                got, err = cfg.executeSettlement(t.Context(), request)
            }
            if err != nil {
                t.Fatal(err)
            }
            // An ambiguous prior bank send is not a valid retryable preflight
            // refusal. It must be quarantined before any signer command.
            if got.OK || got.Retryable || got.TxHash != "" ||
                got.Status != "unverifiable" || !got.IdempotentReplay {
                t.Fatalf("legacy no-hash RPC failure may have broadcast; must hold for manual reconciliation, got %+v", got)
            }
        })
    }
}
