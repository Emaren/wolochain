package cmd

// Regression contract for upgrading the exact October 1 legacy settlement
// writer to a source with durable PRE-broadcast markers. These tests failed against
// the previous held implementation and now guard the explicit repair. They MUST NOT use live chain access.
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

func TestLegacyPreflightRetryAllowlistNeverIncludesPostBroadcastErrors(t *testing.T) {
    t.Parallel()
    for _, tc := range []struct {
        role string
        code string
        allowed bool
    }{
        {settlementSignerRole, "PAYOUT_BALANCE_LOOKUP_FAILED", true},
        {settlementSignerRole, "PAYOUT_BALANCE_TOO_LOW", true},
        {settlementSignerRole, "PAYOUT_FEE_HEADROOM_TOO_LOW", true},
        {settlementSignerRole, "PAYOUT_RESERVE_FLOOR_HIT", true},
        {settlementEscrowSignerRole, "ESCROW_BALANCE_LOOKUP_FAILED", true},
        {settlementEscrowSignerRole, "ESCROW_BALANCE_TOO_LOW", true},
        {settlementEscrowSignerRole, "ESCROW_FEE_HEADROOM_TOO_LOW", true},
        {settlementEscrowSignerRole, "ESCROW_RESERVE_FLOOR_HIT", true},
        {settlementSignerRole, "RPC_UNREACHABLE", false},
        {settlementEscrowSignerRole, "RPC_UNREACHABLE", false},
        {settlementSignerRole, "BROADCAST_FAILED", false},
        {settlementEscrowSignerRole, "BROADCAST_FAILED", false},
        {settlementSignerRole, "SEQUENCE_MISMATCH", false},
        {settlementEscrowSignerRole, "SEQUENCE_MISMATCH", false},
        {settlementSignerRole, "INSUFFICIENT_FUNDS", false},
        {settlementSignerRole, "TX_CONFIRMATION_UNVERIFIABLE", false},
        {settlementEscrowSignerRole, "PAYOUT_BALANCE_TOO_LOW", false},
        {settlementSignerRole, "ESCROW_BALANCE_TOO_LOW", false},
    } {
        response := settlementExecuteResponse{
            OK: false, Status: "failed", Retryable: true,
            FailureCode: tc.code, SignerRole: tc.role,
        }
        if got := legacySettlementPreflightRetryProven(response, tc.role); got != tc.allowed {
            t.Errorf("role=%q code=%q: retryable preflight proved=%v, wanted %v",
                tc.role, tc.code, got, tc.allowed)
        }
        // A crafted or inconsistent historical state is never enough evidence
        // for a new signing operation.
        response.TxHash = "DEADBEEF"
        if legacySettlementPreflightRetryProven(response, tc.role) {
            t.Errorf("%s %s: existing tx hash must never be retried",tc.role,tc.code)
        }
        response.TxHash = ""
        response.Status = "unverifiable"
        if legacySettlementPreflightRetryProven(response,tc.role){
            t.Errorf("%s %s: contradictory status must not be retried",tc.role,tc.code)
        }
    }
}

func TestLegacyAmbiguousQuarantinePreservesOriginalJournalUnmodified(t *testing.T) {
    t.Parallel()
    const payout = "wolo14hteq5qgk8gzme3z2d20enyyannru3hgpue70n"
    const recipient = "wolo1uyge4kml7ecajn8gjrvgeuw0h2fq4alywnf7ux"
    cfg := newTestSettlementConfig(t,payout,map[string]string{payout:"1000000"})
    request := settlementExecuteRequest{
        RequestID:"legacy-ambiguous-do-not-mutate",
        ToAddress:recipient,AmountUWolo:"100",
    }
    normalized, err := normalizeSettlementRequest(request)
    if err != nil {t.Fatal(err)}
    normalized.SignerRole=settlementSignerRole
    path:=cfg.requestRecordPath(normalized.RequestID)
    record:=settlementStoredResult{
        Request:normalized,
        Fingerprint:hashSettlementRequest(normalized,payout),
        Response:settlementExecuteResponse{
            Status:"failed",FailureCode:"RPC_UNREACHABLE",Retryable:true,
            RequestID:normalized.RequestID,ChainID:cfg.ChainID,
            SignerRole:settlementSignerRole,SignerAddress:payout,
            ToAddress:recipient,AmountUWolo:normalized.AmountUWolo,
        },
    }
    if err:=writeSettlementStoredResult(path,record); err!=nil {t.Fatal(err)}
    old,err:=readSettlementStoredResult(path)
    if err!=nil{t.Fatal(err)}
    got,err:=cfg.executeSettlement(t.Context(),request)
    if err!=nil{t.Fatal(err)}
    if !got.IdempotentReplay || got.Retryable || got.FailureCode!="LEGACY_BROADCAST_OUTCOME_UNRECORDED"{
        t.Fatalf("ambiguous legacy send was not quarantined: %+v",got)
    }
    later,err:=readSettlementStoredResult(path)
    if err!=nil{t.Fatal(err)}
    if later.Fingerprint!=old.Fingerprint || later.Response.FailureCode!=old.Response.FailureCode ||
       later.Response.Retryable!=old.Response.Retryable || later.UpdatedAt!=old.UpdatedAt {
       t.Fatalf("quarantine must not silently rewrite historical ledger records: %+v",later)
    }
}
