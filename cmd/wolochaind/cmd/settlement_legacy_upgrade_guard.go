package cmd

// Legacy settlement upgrade compatibility. The original October 1 writer
// persisted some bank-send failures as Retryable even though the signer
// command might already have broadcast WOLO without returning a tx hash.
// A post-upgrade replay must not interpret that record as proof of no send.
//
// Codes below were verified against ORIGINAL live settlement source
// 78c25985420ee41a6678c42fab8ea8d6c3b1b519. They are assigned only
// before the signing/broadcast command, not by the CLI broadcast error
// classifier. Everything else, including RPC_UNREACHABLE and
// SEQUENCE_MISMATCH, is historically ambiguous and is quarantined.
//
// No records are rewritten by this classifier; an operator must reconcile
// the chain and old state before any separate corrective operation.
func legacySettlementPreflightRetryProven(response settlementExecuteResponse, role string) bool {
    if response.OK || !response.Retryable || response.TxHash != "" ||
        response.Status != "failed" || response.ConfirmationStatus != "" ||
        response.SignerRole != role {
        return false
    }
    switch role {
    case settlementSignerRole:
        switch response.FailureCode {
        case "PAYOUT_BALANCE_LOOKUP_FAILED", "PAYOUT_BALANCE_TOO_LOW",
            "PAYOUT_FEE_HEADROOM_TOO_LOW", "PAYOUT_RESERVE_FLOOR_HIT":
            return true
        }
    case settlementEscrowSignerRole:
        switch response.FailureCode {
        case "ESCROW_BALANCE_LOOKUP_FAILED", "ESCROW_BALANCE_TOO_LOW",
            "ESCROW_FEE_HEADROOM_TOO_LOW", "ESCROW_RESERVE_FLOOR_HIT":
            return true
        }
    }
    return false
}

func quarantineAmbiguousLegacySettlementResponse(response settlementExecuteResponse) settlementExecuteResponse {
    response.OK = false
    response.Status = "unverifiable"
    response.ConfirmationStatus = "unverifiable"
    response.FailureCode = "LEGACY_BROADCAST_OUTCOME_UNRECORDED"
    response.Retryable = false
    response.IdempotentReplay = true
    response.Detail = "Historical retryable settlement error does not establish that the bank-send signer was never invoked; no retransmission is permitted without separately verified original-chain reconciliation."
    return response
}
