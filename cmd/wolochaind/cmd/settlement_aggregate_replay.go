package cmd

// Aggregate caches are observations, never a replacement for the leaf request
// and its physical effect owner. These guards only read existing local state;
// they cannot call execute*, sign, query chain state or rewrite historical bytes.
import (
	"context"
	"reflect"
	"strings"
	"time"
)

const aggregateReplayUnverified = "AGGREGATE_REPLAY_UNVERIFIABLE"

func (cfg settlementConfig) guardSettlementRunStoredReplay(ctx context.Context, record settlementRunStoredResult) *settlementRunResponse {
	if ctx != nil {
		bounded, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		ctx = bounded
	}
	if cfg.settlementRunReplayEvidenceValid(ctx, record) {
		return nil
	}
	held := quarantineSettlementRunReplay(record.Response)
	return &held
}

func (cfg settlementConfig) settlementRunReplayEvidenceValid(ctx context.Context, record settlementRunStoredResult) bool {
	request, response := record.Request, record.Response
	if ctx == nil || ctx.Err() != nil || len(request.Payouts) == 0 || len(request.Payouts) > settlementMaxRunPayouts ||
		record.Fingerprint != hashSettlementRunRequest(request) || response.SettlementRunID != request.SettlementRunID ||
		response.SourceApp != request.SourceApp || response.SourceEventID != request.SourceEventID || response.Note != request.Note ||
		response.Memo != request.Memo || response.SignerRole != request.SignerRole || len(response.Payouts) != len(request.Payouts) {
		return false
	}
	seen := map[string]bool{}
	for i, payout := range request.Payouts {
		item := response.Payouts[i]
		if ctx.Err() != nil || seen[payout.RequestID] || payout.Index != i || item.Index != i || item.RequestID != payout.RequestID ||
			item.ToAddress != payout.ToAddress || item.AmountUWolo != payout.AmountUWolo || item.Memo != payout.Memo ||
			item.SignerRole != request.SignerRole {
			return false
		}
		seen[payout.RequestID] = true
		// A wholly refused preflight need not have created a leaf record. Every
		// attempted/positive/hash-bearing effect must retain its original leaf.
		if !item.Attempted && !item.OK && item.TxHash == "" && item.Status != "confirmed" && item.Status != "accepted" && item.ConfirmationStatus != "confirmed" {
			if item.Retryable && !legacySettlementPreflightRetryProven(settlementExecuteResponse{Status: item.Status, FailureCode: item.FailureCode, Retryable: true, SignerRole: item.SignerRole}, request.SignerRole) {
				return false
			}
			continue
		}
		leaf, err := readSettlementStoredResult(cfg.requestRecordPath(payout.RequestID))
		expected := normalizedSettlementRequest{RequestID: payout.RequestID, ToAddress: payout.ToAddress, AmountUWolo: payout.AmountUWolo, Memo: payout.Memo, SignerRole: request.SignerRole}
		if err != nil || leaf.Request != expected || cfg.guardSettlementStoredReplay(ctx, leaf) != nil {
			return false
		}
		leafResponse := leaf.Response
		leafResponse.IdempotentReplay = item.IdempotentReplay
		projected := settlementRunPayoutResultFromExecuteResponse(payout, leafResponse)
		if !sameSettlementPayoutEvidence(item, projected) {
			return false
		}
		if item.OK && item.SignerAddress != response.SignerAddress {
			return false
		}
	}
	calculated := resetSettlementRunAccounting(response)
	calculated.Status = ""
	calculated.OK = false
	calculated.FailureCode = ""
	calculated.Retryable = false
	calculated.RequestedPayoutCount = 0
	calculated.RequestedTotalUWolo = ""
	calculated.RequestedTotalWolo = ""
	calculated = finalizeSettlementRunResponse(calculated)
	return ctx.Err() == nil && sameSettlementRunAccounting(response, calculated) && response.Status == calculated.Status && response.OK == calculated.OK && response.Retryable == calculated.Retryable
}

func sameSettlementPayoutEvidence(a, b settlementRunPayoutResult) bool {
	return a.Index == b.Index && a.RequestID == b.RequestID && a.Attempted == b.Attempted && a.Outcome == b.Outcome && a.OK == b.OK && a.Status == b.Status &&
		a.ConfirmationStatus == b.ConfirmationStatus && a.FailureCode == b.FailureCode && a.Retryable == b.Retryable &&
		a.SignerRole == b.SignerRole && a.SignerAddress == b.SignerAddress && a.ToAddress == b.ToAddress &&
		a.AmountUWolo == b.AmountUWolo && a.AmountWolo == b.AmountWolo && a.AmountWolo == formatDisplayAmount(a.AmountUWolo) && a.Memo == b.Memo && a.TxHash == b.TxHash
}

func resetSettlementRunAccounting(r settlementRunResponse) settlementRunResponse {
	r.ExecutedPayoutCount = 0
	r.ConfirmedPayoutCount = 0
	r.AcceptedPayoutCount = 0
	r.RefusedPayoutCount = 0
	r.RejectedPayoutCount = 0
	r.ReplayPayoutCount = 0
	r.ExecutedTotalUWolo = ""
	r.ExecutedTotalWolo = ""
	r.ConfirmedTotalUWolo = ""
	r.ConfirmedTotalWolo = ""
	r.AcceptedTotalUWolo = ""
	r.AcceptedTotalWolo = ""
	r.RefusedTotalUWolo = ""
	r.RefusedTotalWolo = ""
	r.RejectedTotalUWolo = ""
	r.RejectedTotalWolo = ""
	return r
}

func sameSettlementRunAccounting(a, b settlementRunResponse) bool {
	return reflect.DeepEqual([]int{a.RequestedPayoutCount, a.ExecutedPayoutCount, a.ConfirmedPayoutCount, a.AcceptedPayoutCount, a.RefusedPayoutCount, a.RejectedPayoutCount, a.ReplayPayoutCount},
		[]int{b.RequestedPayoutCount, b.ExecutedPayoutCount, b.ConfirmedPayoutCount, b.AcceptedPayoutCount, b.RefusedPayoutCount, b.RejectedPayoutCount, b.ReplayPayoutCount}) &&
		reflect.DeepEqual([]string{a.RequestedTotalUWolo, a.ExecutedTotalUWolo, a.ConfirmedTotalUWolo, a.AcceptedTotalUWolo, a.RefusedTotalUWolo, a.RejectedTotalUWolo, a.RequestedTotalWolo, a.ExecutedTotalWolo, a.ConfirmedTotalWolo, a.AcceptedTotalWolo, a.RefusedTotalWolo, a.RejectedTotalWolo},
			[]string{b.RequestedTotalUWolo, b.ExecutedTotalUWolo, b.ConfirmedTotalUWolo, b.AcceptedTotalUWolo, b.RefusedTotalUWolo, b.RejectedTotalUWolo, b.RequestedTotalWolo, b.ExecutedTotalWolo, b.ConfirmedTotalWolo, b.AcceptedTotalWolo, b.RefusedTotalWolo, b.RejectedTotalWolo})
}

func quarantineSettlementRunReplay(r settlementRunResponse) settlementRunResponse {
	r = resetSettlementRunAccounting(r)
	r.OK = false
	r.Status = "unverifiable"
	r.FailureCode = aggregateReplayUnverified
	r.Retryable = false
	r.IdempotentReplay = true
	r.Detail = "Aggregate cache lacks exact leaf/effect ownership or conserved accounting; original state is preserved, payment outcome remains uncertain and no signing or retry is permitted."
	r.Payouts = append([]settlementRunPayoutResult(nil), r.Payouts...)
	for i := range r.Payouts {
		p := &r.Payouts[i]
		p.OK = false
		p.Status = "unverifiable"
		p.ConfirmationStatus = "unverifiable"
		p.Outcome = "unverifiable"
		p.FailureCode = aggregateReplayUnverified
		p.Retryable = false
		p.IdempotentReplay = true
	}
	return r
}

func (cfg settlementConfig) guardSettlementChallengeStoredReplay(ctx context.Context, record settlementChallengeStoredResult, current settlementChallengeResponse) *settlementChallengeResponse {
	if ctx != nil {
		bounded, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		ctx = bounded
	}
	if current.FailureCode != "INVALID_CHALLENGE" && current.FailureCode != "INVALID_TRANSFER" &&
		record.Response.FundingCount == current.FundingCount && record.Response.FundingVerifiedCount == current.FundingVerifiedCount &&
		record.Response.ParticipantCount == current.ParticipantCount && record.Response.FundingTotalUWolo == current.FundingTotalUWolo &&
		record.Response.FundingTotalWolo == current.FundingTotalWolo && reflect.DeepEqual(record.Response.Funding, current.Funding) &&
		cfg.settlementChallengeReplayEvidenceValid(ctx, record) {
		return nil
	}
	r := record.Response
	r.OK = false
	r.Status = "unverifiable"
	r.FailureCode = aggregateReplayUnverified
	r.Retryable = false
	r.IdempotentReplay = true
	r.ExecutedTransferCount = 0
	r.ConfirmedTransferCount = 0
	r.AcceptedTransferCount = 0
	r.RefusedTransferCount = 0
	r.RejectedTransferCount = 0
	r.ReplayTransferCount = 0
	r.ExecutedTotalUWolo = ""
	r.ExecutedTotalWolo = ""
	r.ConfirmedTotalUWolo = ""
	r.ConfirmedTotalWolo = ""
	r.AcceptedTotalUWolo = ""
	r.AcceptedTotalWolo = ""
	r.RefusedTotalUWolo = ""
	r.RefusedTotalWolo = ""
	r.RejectedTotalUWolo = ""
	r.RejectedTotalWolo = ""
	r.Detail = "Challenge cache lacks exact run/leaf/effect ownership or conserved accounting; original state and unresolved obligations are preserved; no signing or retry is permitted."
	r.Funding = nil
	r.FundingVerifiedCount = 0
	r.Transfers = append([]settlementChallengeTransferResult(nil), r.Transfers...)
	for i := range r.Transfers {
		p := &r.Transfers[i]
		p.OK = false
		p.Status = "unverifiable"
		p.ConfirmationStatus = "unverifiable"
		p.Outcome = "unverifiable"
		p.FailureCode = aggregateReplayUnverified
		p.Retryable = false
		p.IdempotentReplay = true
	}
	r.BucketTotals = append([]settlementChallengeBucketTotals(nil), r.BucketTotals...)
	for i := range r.BucketTotals {
		p := &r.BucketTotals[i]
		p.ExecutedUWolo = ""
		p.ExecutedWolo = ""
		p.ConfirmedUWolo = ""
		p.ConfirmedWolo = ""
		p.AcceptedUWolo = ""
		p.AcceptedWolo = ""
		p.RefusedUWolo = ""
		p.RefusedWolo = ""
		p.RejectedUWolo = ""
		p.RejectedWolo = ""
	}
	if r.Run != nil {
		held := quarantineSettlementRunReplay(*r.Run)
		r.Run = &held
	}
	if r.TopUp != nil {
		top := *r.TopUp
		r.TopUp = &top
		top.FailureCode = aggregateReplayUnverified
		if top.Response != nil {
			leaf := *top.Response
			leaf.OK = false
			leaf.Status = "unverifiable"
			leaf.ConfirmationStatus = "unverifiable"
			leaf.FailureCode = aggregateReplayUnverified
			leaf.Retryable = false
			leaf.IdempotentReplay = true
			top.Response = &leaf
			r.TopUp = &top
		}
	}
	return &r
}

func (cfg settlementConfig) settlementChallengeReplayEvidenceValid(ctx context.Context, record settlementChallengeStoredResult) bool {
	q, r := record.Request, record.Response
	if ctx == nil || ctx.Err() != nil || len(q.Transfers) == 0 || len(q.Transfers) > settlementMaxRunPayouts ||
		record.Fingerprint != hashSettlementChallengeRequest(q) || r.SettlementRunID != q.SettlementRunID || r.SourceApp != q.SourceApp ||
		r.ChallengeID != q.ChallengeID || r.SourceEventID != q.SourceEventID || r.TreasuryAddress != q.TreasuryAddress || r.Note != q.Note || r.Memo != q.Memo ||
		len(r.Transfers) != len(q.Transfers) || r.Run == nil {
		return false
	}
	run, err := readSettlementRunStoredResult(cfg.runRecordPath(q.SettlementRunID))
	expected := normalizedSettlementRunRequest{SettlementRunID: q.SettlementRunID, SourceApp: q.SourceApp, SourceEventID: firstNonEmpty(q.SourceEventID, q.ChallengeID), Note: q.Note, Memo: q.Memo, SignerRole: settlementSignerRole}
	for _, p := range q.Transfers {
		expected.Payouts = append(expected.Payouts, normalizedSettlementPayout{Index: p.Index, RequestID: p.RequestID, ToAddress: p.ToAddress, AmountUWolo: p.AmountUWolo, Memo: p.Memo})
	}
	if err != nil || run.Fingerprint != hashSettlementRunRequest(expected) || !cfg.settlementRunReplayEvidenceValid(ctx, run) ||
		!sameSettlementRunAccounting(*r.Run, run.Response) || r.Run.Status != run.Response.Status || r.Run.OK != run.Response.OK ||
		r.Run.SettlementRunID != run.Response.SettlementRunID || r.Run.SourceApp != run.Response.SourceApp ||
		r.Run.SourceEventID != run.Response.SourceEventID || r.Run.Note != run.Response.Note || r.Run.Memo != run.Response.Memo ||
		r.Run.SignerRole != run.Response.SignerRole || r.Run.SignerAddress != run.Response.SignerAddress || len(r.Run.Payouts) != len(run.Response.Payouts) {
		return false
	}
	for i := range run.Response.Payouts {
		if !sameSettlementPayoutEvidence(r.Run.Payouts[i], run.Response.Payouts[i]) {
			return false
		}
	}
	if !reflect.DeepEqual(r.Transfers, mergeChallengeRunResults(q.Transfers, run.Response)) {
		return false
	}
	if top := r.TopUp; top != nil {
		if !top.Required {
			if top.Response != nil {
				return false
			}
		} else {
			if top.Response == nil || top.AmountWolo != formatDisplayAmount(top.AmountUWolo) || top.Response.AmountWolo != formatDisplayAmount(top.Response.AmountUWolo) || top.RequestID != deriveSettlementChallengeTopUpRequestID(q.SettlementRunID) || top.ToAddress != run.Response.SignerAddress {
				return false
			}
			memo := "challenge top-up " + q.SettlementRunID
			if len(memo) > 180 {
				memo = memo[:180]
			}
			expected := normalizedSettlementRequest{RequestID: top.RequestID, ToAddress: top.ToAddress, AmountUWolo: top.AmountUWolo, Memo: memo, SignerRole: settlementEscrowSignerRole}
			leaf, e := readSettlementStoredResult(cfg.requestRecordPath(top.RequestID))
			leafResponse := leaf.Response
			leafResponse.IdempotentReplay = top.Response.IdempotentReplay
			if e != nil || leaf.Request != expected || cfg.guardSettlementStoredReplay(ctx, leaf) != nil ||
				!reflect.DeepEqual(*top.Response, leafResponse) || top.FromAddress != leaf.Response.SignerAddress {
				return false
			}
		}
	}
	calculated := r
	calculated.ExecutedTransferCount = 0
	calculated.ConfirmedTransferCount = 0
	calculated.AcceptedTransferCount = 0
	calculated.RefusedTransferCount = 0
	calculated.RejectedTransferCount = 0
	calculated.ReplayTransferCount = 0
	calculated.RequestedTransferCount = 0
	calculated.RequestedTotalUWolo = ""
	calculated.RequestedTotalWolo = ""
	calculated.Status = ""
	calculated.OK = false
	calculated.FailureCode = ""
	calculated.Retryable = false
	calculated = finalizeSettlementChallengeResponse(calculated)
	return ctx.Err() == nil && r.Status == calculated.Status && r.OK == calculated.OK && r.Retryable == calculated.Retryable &&
		reflect.DeepEqual(r.BucketTotals, calculated.BucketTotals) &&
		reflect.DeepEqual([]int{r.RequestedTransferCount, r.ExecutedTransferCount, r.ConfirmedTransferCount, r.AcceptedTransferCount, r.RefusedTransferCount, r.RejectedTransferCount, r.ReplayTransferCount},
			[]int{calculated.RequestedTransferCount, calculated.ExecutedTransferCount, calculated.ConfirmedTransferCount, calculated.AcceptedTransferCount, calculated.RefusedTransferCount, calculated.RejectedTransferCount, calculated.ReplayTransferCount}) &&
		reflect.DeepEqual([]string{r.RequestedTotalUWolo, r.ExecutedTotalUWolo, r.ConfirmedTotalUWolo, r.AcceptedTotalUWolo, r.RefusedTotalUWolo, r.RejectedTotalUWolo, r.RequestedTotalWolo, r.ExecutedTotalWolo, r.ConfirmedTotalWolo, r.AcceptedTotalWolo, r.RefusedTotalWolo, r.RejectedTotalWolo},
			[]string{calculated.RequestedTotalUWolo, calculated.ExecutedTotalUWolo, calculated.ConfirmedTotalUWolo, calculated.AcceptedTotalUWolo, calculated.RefusedTotalUWolo, calculated.RejectedTotalUWolo, calculated.RequestedTotalWolo, calculated.ExecutedTotalWolo, calculated.ConfirmedTotalWolo, calculated.AcceptedTotalWolo, calculated.RefusedTotalWolo, calculated.RejectedTotalWolo}) &&
		!strings.EqualFold(r.Status, "validated")
}
