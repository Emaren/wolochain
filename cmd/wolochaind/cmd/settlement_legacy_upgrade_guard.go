package cmd

import "context"

// A journal result is not itself independent chain evidence. Preserve it, but
// do not let a truncated, contradictory or pre-confirmation-contract success
// inherit the newer exact-confirmation authority merely through JSON replay.
// This path never calls a signer, queries the chain or rewrites old bytes.
func (cfg settlementConfig) guardSettlementStoredReplay(ctx context.Context, record settlementStoredResult) *settlementExecuteResponse {
	request, response := record.Request, record.Response
	role := normalizeStoredSettlementSignerRole(request.SignerRole)
	code := ""
	if record.Fingerprint != hashSettlementRequest(request, response.SignerAddress) ||
		response.RequestID != request.RequestID || response.ChainID != cfg.ChainID ||
		response.SignerRole != role || response.ToAddress != request.ToAddress ||
		response.AmountUWolo != request.AmountUWolo {
		code = "STATE_FILE_INVALID"
	} else if response.OK {
		if len(response.TxHash) != 64 || !isHexHash(response.TxHash) || response.Code != 0 || response.Retryable ||
			(response.Status != "accepted" && response.Status != "confirmed") {
			code = "STATE_FILE_INVALID"
		} else if response.Status == "confirmed" {
			if response.ConfirmationStatus != "confirmed" {
				code = "LEGACY_CONFIRMATION_UNVERIFIED"
			} else if cfg.verifySettlementConfirmationReplay(ctx, request, response.SignerAddress, response.TxHash) != nil {
				code = "TX_RECEIPT_UNAVAILABLE"
			}
		}
	}
	if code == "" {
		return nil
	}
	response.OK = false
	response.Status = "unverifiable"
	response.ConfirmationStatus = "unverifiable"
	response.FailureCode = code
	response.Retryable = false
	response.IdempotentReplay = true
	response.Detail = "Stored settlement evidence cannot establish an exact, uniquely owned confirmation; historical bytes are preserved and no new signing or broadcast is permitted."
	return &response
}

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
