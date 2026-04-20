package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type settlementChallengeAuditResponse struct {
	OK              bool                               `json:"ok"`
	FailureCode     string                             `json:"failure_code,omitempty"`
	Detail          string                             `json:"detail,omitempty"`
	SettlementRunID string                             `json:"settlement_run_id"`
	ChallengePath   string                             `json:"challenge_path,omitempty"`
	RunPath         string                             `json:"run_path,omitempty"`
	CheckedAt       time.Time                          `json:"checked_at"`
	Summary         settlementChallengeAuditSummary    `json:"summary"`
	Checks          []settlementChallengeAuditCheck    `json:"checks,omitempty"`
	Funding         []settlementChallengeAuditFunding  `json:"funding,omitempty"`
	Transfers       []settlementChallengeAuditTransfer `json:"transfers,omitempty"`
	TopUp           *settlementChallengeAuditTopUp     `json:"top_up,omitempty"`
}

type settlementChallengeAuditSummary struct {
	SourceApp                 string `json:"source_app,omitempty"`
	ChallengeID               string `json:"challenge_id,omitempty"`
	SourceEventID             string `json:"source_event_id,omitempty"`
	TreasuryAddress           string `json:"treasury_address,omitempty"`
	FundingCount              int    `json:"funding_count"`
	FundingVerifiedCount      int    `json:"funding_verified_count"`
	FundingTotalUWolo         string `json:"funding_total_uwolo,omitempty"`
	WagerFundedUWolo          string `json:"wager_funded_uwolo,omitempty"`
	GuaranteeFundedUWolo      string `json:"guarantee_funded_uwolo,omitempty"`
	RequestedTransferCount    int    `json:"requested_transfer_count"`
	TransferTxCheckedCount    int    `json:"transfer_tx_checked_count"`
	RequestedTotalUWolo       string `json:"requested_total_uwolo,omitempty"`
	WagerTransferUWolo        string `json:"wager_transfer_uwolo,omitempty"`
	GuaranteeTransferUWolo    string `json:"guarantee_transfer_uwolo,omitempty"`
	TreasuryTransferUWolo     string `json:"treasury_transfer_uwolo,omitempty"`
	TopUpRequired             bool   `json:"top_up_required"`
	TopUpAmountUWolo          string `json:"top_up_amount_uwolo,omitempty"`
	TopUpTxChecked            bool   `json:"top_up_tx_checked"`
	StoredStatus              string `json:"stored_status,omitempty"`
	StoredFailureCode         string `json:"stored_failure_code,omitempty"`
	StoredConfirmedTotalUWolo string `json:"stored_confirmed_total_uwolo,omitempty"`
}

type settlementChallengeAuditCheck struct {
	Name        string `json:"name"`
	OK          bool   `json:"ok"`
	FailureCode string `json:"failure_code,omitempty"`
	Detail      string `json:"detail,omitempty"`
	Expected    string `json:"expected,omitempty"`
	Actual      string `json:"actual,omitempty"`
}

type settlementChallengeAuditFunding struct {
	Index           int                               `json:"index"`
	OK              bool                              `json:"ok"`
	FailureCode     string                            `json:"failure_code,omitempty"`
	Detail          string                            `json:"detail,omitempty"`
	FundingTxHash   string                            `json:"funding_tx_hash,omitempty"`
	StoredFunding   *settlementChallengeFundingResult `json:"stored_funding,omitempty"`
	VerifiedFunding *settlementChallengeFundingResult `json:"verified_funding,omitempty"`
}

type settlementChallengeAuditTransfer struct {
	Index         int                       `json:"index"`
	RequestID     string                    `json:"request_id"`
	Bucket        string                    `json:"bucket,omitempty"`
	Reason        string                    `json:"reason,omitempty"`
	Status        string                    `json:"status,omitempty"`
	Outcome       string                    `json:"outcome,omitempty"`
	OK            bool                      `json:"ok"`
	FailureCode   string                    `json:"failure_code,omitempty"`
	Detail        string                    `json:"detail,omitempty"`
	SignerAddress string                    `json:"signer_address,omitempty"`
	ToAddress     string                    `json:"to_address,omitempty"`
	AmountUWolo   string                    `json:"amount_uwolo,omitempty"`
	Memo          string                    `json:"memo,omitempty"`
	TxHash        string                    `json:"tx_hash,omitempty"`
	StatePath     string                    `json:"state_path,omitempty"`
	TxLookup      *settlementLookupResponse `json:"tx_lookup,omitempty"`
}

type settlementChallengeAuditTopUp struct {
	Required    bool                      `json:"required"`
	OK          bool                      `json:"ok"`
	FailureCode string                    `json:"failure_code,omitempty"`
	Detail      string                    `json:"detail,omitempty"`
	RequestID   string                    `json:"request_id,omitempty"`
	FromAddress string                    `json:"from_address,omitempty"`
	ToAddress   string                    `json:"to_address,omitempty"`
	AmountUWolo string                    `json:"amount_uwolo,omitempty"`
	TxHash      string                    `json:"tx_hash,omitempty"`
	StatePath   string                    `json:"state_path,omitempty"`
	TxLookup    *settlementLookupResponse `json:"tx_lookup,omitempty"`
}

func newSettlementChallengeAuditCmd() *cobra.Command {
	var (
		settlementID string
		summaryOnly  bool
	)

	cmd := &cobra.Command{
		Use:   "audit",
		Short: "Reconcile stored challenge settlement state against funding, payout, and top-up tx reality",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.auditSettlementChallenge(cmd.Context(), settlementID)
			if err != nil {
				return err
			}
			if summaryOnly {
				response.Checks = nil
				response.Funding = nil
				response.Transfers = nil
				response.TopUp = nil
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&settlementID, "settlement-id", "", "Stored challenge settlement id to audit")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only the top-level audit summary")
	return cmd
}

func (cfg settlementConfig) auditSettlementChallenge(ctx context.Context, settlementID string) (settlementChallengeAuditResponse, error) {
	settlementID = strings.TrimSpace(settlementID)
	if settlementID == "" {
		return settlementChallengeAuditResponse{}, errors.New("settlement id is required")
	}

	recordPath := cfg.challengeRecordPath(settlementID)
	record, err := readSettlementChallengeStoredResult(recordPath)
	response := settlementChallengeAuditResponse{
		OK:              false,
		SettlementRunID: settlementID,
		ChallengePath:   recordPath,
		CheckedAt:       time.Now().UTC(),
	}
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			response.FailureCode = "CHALLENGE_STATE_NOT_FOUND"
			response.Detail = "stored challenge settlement state was not found"
			response.Checks = append(response.Checks, failedAuditCheck("challenge_state_exists", response.FailureCode, response.Detail, recordPath, "missing"))
			return response, nil
		}
		return settlementChallengeAuditResponse{}, err
	}

	response.Summary = settlementChallengeAuditSummary{
		SourceApp:                 record.Request.SourceApp,
		ChallengeID:               record.Request.ChallengeID,
		SourceEventID:             record.Request.SourceEventID,
		TreasuryAddress:           record.Request.TreasuryAddress,
		FundingCount:              len(record.Request.Funding),
		FundingVerifiedCount:      record.Response.FundingVerifiedCount,
		FundingTotalUWolo:         record.Response.FundingTotalUWolo,
		RequestedTransferCount:    len(record.Request.Transfers),
		RequestedTotalUWolo:       record.Response.RequestedTotalUWolo,
		TopUpRequired:             record.Response.TopUp != nil && record.Response.TopUp.Required,
		StoredStatus:              record.Response.Status,
		StoredFailureCode:         record.Response.FailureCode,
		StoredConfirmedTotalUWolo: record.Response.ConfirmedTotalUWolo,
	}

	checks := settlementChallengeAuditChecks{}
	checks.add("challenge_state_exists", true, "", "stored challenge settlement state exists", recordPath, recordPath)
	expectedFingerprint := hashSettlementChallengeRequest(record.Request)
	checks.addEqual("challenge_state_fingerprint", "CHALLENGE_STATE_FINGERPRINT_MISMATCH", record.Fingerprint, expectedFingerprint)
	checks.addEqual("challenge_response_settlement_id", "CHALLENGE_STATE_MISMATCH", record.Response.SettlementRunID, record.Request.SettlementRunID)
	checks.addEqual("challenge_response_source_app", "CHALLENGE_STATE_MISMATCH", record.Response.SourceApp, record.Request.SourceApp)
	checks.addEqual("challenge_response_challenge_id", "CHALLENGE_STATE_MISMATCH", record.Response.ChallengeID, record.Request.ChallengeID)
	checks.addEqual("challenge_response_source_event_id", "CHALLENGE_STATE_MISMATCH", record.Response.SourceEventID, record.Request.SourceEventID)
	checks.addEqual("challenge_response_funding_count", "FUNDING_COUNT_MISMATCH", strconv.Itoa(len(record.Request.Funding)), strconv.Itoa(len(record.Response.Funding)))
	checks.addEqual("challenge_response_transfer_count", "TRANSFER_STATE_MISMATCH", strconv.Itoa(len(record.Request.Transfers)), strconv.Itoa(len(record.Response.Transfers)))

	verifiedFunding, fundingAudit, fundingChecks, fundingTotals, err := cfg.auditChallengeFunding(ctx, record)
	if err != nil {
		return settlementChallengeAuditResponse{}, err
	}
	checks.items = append(checks.items, fundingChecks...)
	response.Funding = fundingAudit
	response.Summary.FundingVerifiedCount = len(verifiedFunding)
	response.Summary.FundingTotalUWolo = strconv.FormatUint(fundingTotals.total, 10)
	response.Summary.WagerFundedUWolo = strconv.FormatUint(fundingTotals.wager, 10)
	response.Summary.GuaranteeFundedUWolo = strconv.FormatUint(fundingTotals.guarantee, 10)
	checks.addEqual("funding_total", "FUNDING_TOTAL_MISMATCH", record.Response.FundingTotalUWolo, response.Summary.FundingTotalUWolo)

	transferTotals, allocationChecks := auditChallengeBucketAllocation(record, verifiedFunding)
	checks.items = append(checks.items, allocationChecks...)
	response.Summary.RequestedTotalUWolo = strconv.FormatUint(transferTotals.total, 10)
	response.Summary.WagerTransferUWolo = strconv.FormatUint(transferTotals.wager, 10)
	response.Summary.GuaranteeTransferUWolo = strconv.FormatUint(transferTotals.guarantee, 10)
	response.Summary.TreasuryTransferUWolo = strconv.FormatUint(transferTotals.treasury, 10)
	checks.addEqual("requested_total", "REQUESTED_TOTAL_MISMATCH", record.Response.RequestedTotalUWolo, response.Summary.RequestedTotalUWolo)
	checks.addEqual("wager_bucket_total", "BUCKET_TOTAL_MISMATCH", challengeResponseBucketRequested(record.Response, settlementChallengeBucketWager), response.Summary.WagerTransferUWolo)
	checks.addEqual("guarantee_bucket_total", "BUCKET_TOTAL_MISMATCH", challengeResponseBucketRequested(record.Response, settlementChallengeBucketGuarantee), response.Summary.GuaranteeTransferUWolo)

	runRecord, runChecks, err := cfg.auditChallengeRunState(record)
	if err != nil {
		return settlementChallengeAuditResponse{}, err
	}
	checks.items = append(checks.items, runChecks...)
	if runRecord != nil {
		response.RunPath = cfg.runRecordPath(record.Request.SettlementRunID)
	}

	transfers, transferChecks, txChecked, err := cfg.auditChallengeTransfers(ctx, record, runRecord)
	if err != nil {
		return settlementChallengeAuditResponse{}, err
	}
	checks.items = append(checks.items, transferChecks...)
	response.Transfers = transfers
	response.Summary.TransferTxCheckedCount = txChecked

	topUp, topUpChecks, err := cfg.auditChallengeTopUp(ctx, record)
	if err != nil {
		return settlementChallengeAuditResponse{}, err
	}
	checks.items = append(checks.items, topUpChecks...)
	response.TopUp = topUp
	if topUp != nil {
		response.Summary.TopUpAmountUWolo = topUp.AmountUWolo
		response.Summary.TopUpTxChecked = topUp.TxLookup != nil
	}

	response.Checks = checks.items
	response.OK = checks.ok()
	if !response.OK {
		response.FailureCode = checks.firstFailureCode()
		response.Detail = checks.firstFailureDetail()
		return response, nil
	}

	response.Detail = "challenge settlement state reconciles with funding, payout, top-up, and grouped run proofs"
	return response, nil
}

type settlementChallengeAuditChecks struct {
	items []settlementChallengeAuditCheck
}

func (checks *settlementChallengeAuditChecks) add(name string, ok bool, failureCode, detail, expected, actual string) {
	item := settlementChallengeAuditCheck{
		Name:        name,
		OK:          ok,
		FailureCode: strings.TrimSpace(failureCode),
		Detail:      strings.TrimSpace(detail),
		Expected:    strings.TrimSpace(expected),
		Actual:      strings.TrimSpace(actual),
	}
	if item.OK {
		item.FailureCode = ""
	}
	checks.items = append(checks.items, item)
}

func (checks *settlementChallengeAuditChecks) addEqual(name, failureCode, expected, actual string) {
	expected = strings.TrimSpace(expected)
	actual = strings.TrimSpace(actual)
	if expected == actual {
		checks.add(name, true, "", "values match", expected, actual)
		return
	}
	checks.add(name, false, failureCode, fmt.Sprintf("%s expected %q but found %q", name, expected, actual), expected, actual)
}

func (checks settlementChallengeAuditChecks) ok() bool {
	for _, check := range checks.items {
		if !check.OK {
			return false
		}
	}
	return true
}

func (checks settlementChallengeAuditChecks) firstFailureCode() string {
	for _, check := range checks.items {
		if !check.OK && strings.TrimSpace(check.FailureCode) != "" {
			return check.FailureCode
		}
	}
	return "CHALLENGE_AUDIT_FAILED"
}

func (checks settlementChallengeAuditChecks) firstFailureDetail() string {
	for _, check := range checks.items {
		if !check.OK && strings.TrimSpace(check.Detail) != "" {
			return check.Detail
		}
	}
	return "one or more challenge settlement audit checks failed"
}

func failedAuditCheck(name, failureCode, detail, expected, actual string) settlementChallengeAuditCheck {
	return settlementChallengeAuditCheck{
		Name:        name,
		OK:          false,
		FailureCode: failureCode,
		Detail:      detail,
		Expected:    expected,
		Actual:      actual,
	}
}

type challengeAuditFundingTotals struct {
	total     uint64
	wager     uint64
	guarantee uint64
}

func (cfg settlementConfig) auditChallengeFunding(ctx context.Context, record settlementChallengeStoredResult) ([]verifiedSettlementChallengeFunding, []settlementChallengeAuditFunding, []settlementChallengeAuditCheck, challengeAuditFundingTotals, error) {
	checks := settlementChallengeAuditChecks{}
	audits := make([]settlementChallengeAuditFunding, 0, len(record.Request.Funding))
	verified := make([]verifiedSettlementChallengeFunding, 0, len(record.Request.Funding))
	totals := challengeAuditFundingTotals{}

	for index, funding := range record.Request.Funding {
		expected := settlementChallengeFundingExpectation{
			Sender:           funding.DepositorAddress,
			SourceApp:        record.Request.SourceApp,
			SettlementRunID:  funding.SettlementRunID,
			ChallengeID:      record.Request.ChallengeID,
			SourceEventID:    record.Request.SourceEventID,
			ParticipantSide:  funding.ParticipantSide,
			ParticipantID:    funding.ParticipantID,
			TotalFundedUWolo: funding.ExpectedAmountUWolo,
			WagerUWolo:       funding.WagerUWolo,
			GuaranteeUWolo:   funding.GuaranteeUWolo,
		}
		var stored *settlementChallengeFundingResult
		if index < len(record.Response.Funding) {
			storedFunding := record.Response.Funding[index]
			stored = &storedFunding
			expected.Sender = firstNonEmpty(expected.Sender, storedFunding.Sender)
			expected.SettlementRunID = firstNonEmpty(expected.SettlementRunID, storedFunding.SettlementRunID)
			expected.TotalFundedUWolo = firstNonEmpty(expected.TotalFundedUWolo, storedFunding.TotalFundedUWolo)
			expected.WagerUWolo = firstNonEmpty(expected.WagerUWolo, storedFunding.WagerUWolo)
			expected.GuaranteeUWolo = firstNonEmpty(expected.GuaranteeUWolo, storedFunding.GuaranteeUWolo)
		}

		verifyResponse, err := cfg.verifyChallengeFundingDeposit(ctx, funding.FundingTxHash, expected)
		if err != nil {
			return nil, nil, nil, challengeAuditFundingTotals{}, err
		}
		audit := settlementChallengeAuditFunding{
			Index:         index,
			OK:            verifyResponse.OK,
			FundingTxHash: funding.FundingTxHash,
			StoredFunding: stored,
		}
		if verifyResponse.Funding != nil {
			verifiedFunding := *verifyResponse.Funding
			verifiedFunding.Index = index
			audit.VerifiedFunding = &verifiedFunding
		}
		if !verifyResponse.OK || verifyResponse.Funding == nil {
			audit.FailureCode = firstNonEmpty(verifyResponse.FailureCode, "FUNDING_PROOF_MISMATCH")
			audit.Detail = verifyResponse.Detail
			checks.add(fmt.Sprintf("funding_%d_proof", index), false, audit.FailureCode, audit.Detail, funding.FundingTxHash, "unverified")
			audits = append(audits, audit)
			continue
		}

		verified = append(verified, verifiedSettlementChallengeFunding{Result: *audit.VerifiedFunding})
		total, _ := parseOptionalUWoloString(audit.VerifiedFunding.TotalFundedUWolo)
		wager, _ := parseOptionalUWoloString(audit.VerifiedFunding.WagerUWolo)
		guarantee, _ := parseOptionalUWoloString(audit.VerifiedFunding.GuaranteeUWolo)
		totals.total += total
		totals.wager += wager
		totals.guarantee += guarantee
		checks.add(fmt.Sprintf("funding_%d_proof", index), true, "", "funding tx matches challenge memo and escrow expectations", funding.FundingTxHash, funding.FundingTxHash)

		if stored != nil {
			if mismatch := compareStoredChallengeFunding(*stored, *audit.VerifiedFunding); mismatch != "" {
				audit.OK = false
				audit.FailureCode = "FUNDING_STATE_MISMATCH"
				audit.Detail = mismatch
				checks.add(fmt.Sprintf("funding_%d_state", index), false, audit.FailureCode, mismatch, "stored funding", "verified funding")
			} else {
				checks.add(fmt.Sprintf("funding_%d_state", index), true, "", "stored funding state matches verified tx reality", "stored funding", "verified funding")
			}
		}
		audits = append(audits, audit)
	}

	checks.addEqual("funding_verified_count", "FUNDING_COUNT_MISMATCH", strconv.Itoa(record.Response.FundingVerifiedCount), strconv.Itoa(len(verified)))
	return verified, audits, checks.items, totals, nil
}

func compareStoredChallengeFunding(stored, verified settlementChallengeFundingResult) string {
	fields := []struct {
		name   string
		stored string
		actual string
	}{
		{"funding_tx_hash", stored.FundingTxHash, verified.FundingTxHash},
		{"source_app", stored.SourceApp, verified.SourceApp},
		{"settlement_run_id", stored.SettlementRunID, verified.SettlementRunID},
		{"challenge_id", stored.ChallengeID, verified.ChallengeID},
		{"source_event_id", stored.SourceEventID, verified.SourceEventID},
		{"participant_side", stored.ParticipantSide, verified.ParticipantSide},
		{"participant_id", stored.ParticipantID, verified.ParticipantID},
		{"sender", stored.Sender, verified.Sender},
		{"escrow_address", stored.EscrowAddress, verified.EscrowAddress},
		{"total_funded_uwolo", stored.TotalFundedUWolo, verified.TotalFundedUWolo},
		{"wager_uwolo", stored.WagerUWolo, verified.WagerUWolo},
		{"guarantee_uwolo", stored.GuaranteeUWolo, verified.GuaranteeUWolo},
	}
	for _, field := range fields {
		if !strings.EqualFold(strings.TrimSpace(field.stored), strings.TrimSpace(field.actual)) {
			return fmt.Sprintf("%s stored %q does not match verified tx value %q", field.name, field.stored, field.actual)
		}
	}
	return ""
}

type challengeAuditTransferTotals struct {
	total     uint64
	wager     uint64
	guarantee uint64
	treasury  uint64
}

func auditChallengeBucketAllocation(record settlementChallengeStoredResult, funding []verifiedSettlementChallengeFunding) (challengeAuditTransferTotals, []settlementChallengeAuditCheck) {
	checks := settlementChallengeAuditChecks{}
	totals := challengeAuditTransferTotals{}
	allocation := map[string]map[string]uint64{}

	for _, transfer := range record.Request.Transfers {
		amount, err := parseOptionalUWoloString(transfer.AmountUWolo)
		if err != nil {
			checks.add(fmt.Sprintf("transfer_%d_amount", transfer.Index), false, "INVALID_TRANSFER_AMOUNT", err.Error(), transfer.AmountUWolo, "")
			continue
		}
		totals.total += amount
		switch transfer.Bucket {
		case settlementChallengeBucketWager:
			totals.wager += amount
		case settlementChallengeBucketGuarantee:
			totals.guarantee += amount
		}
		if strings.EqualFold(transfer.Reason, "treasury") {
			totals.treasury += amount
			expectedTreasury := strings.TrimSpace(record.Request.TreasuryAddress)
			checks.addEqual(fmt.Sprintf("transfer_%d_treasury_route", transfer.Index), "TREASURY_ROUTE_MISMATCH", expectedTreasury, transfer.ToAddress)
		}

		matchedFunding, matchErr := resolveChallengeFundingParticipant(funding, transfer.ParticipantSide, transfer.ParticipantID)
		if matchErr != "" {
			checks.add(fmt.Sprintf("transfer_%d_funding_identity", transfer.Index), false, "TRANSFER_FUNDING_MISMATCH", matchErr, transfer.ParticipantSide+"|"+transfer.ParticipantID, "")
			continue
		}
		key := challengeFundingIdentityKey(matchedFunding.Result.ParticipantSide, matchedFunding.Result.ParticipantID, matchedFunding.Result.FundingTxHash)
		if allocation[key] == nil {
			allocation[key] = map[string]uint64{}
		}
		allocation[key][transfer.Bucket] += amount
	}

	if bucketErrors := validateChallengeBucketAllocation(funding, allocation); len(bucketErrors) > 0 {
		checks.add("bucket_allocation", false, "BUCKET_ALLOCATION_MISMATCH", strings.Join(bucketErrors, "; "), "funded buckets", "transfer allocation")
	} else {
		checks.add("bucket_allocation", true, "", "wager and guarantee transfer buckets reconcile to verified funding", "funded buckets", "transfer allocation")
	}
	return totals, checks.items
}

func challengeResponseBucketRequested(response settlementChallengeResponse, bucket string) string {
	for _, totals := range response.BucketTotals {
		if strings.EqualFold(totals.Bucket, bucket) {
			return strings.TrimSpace(totals.RequestedUWolo)
		}
	}
	return "0"
}

func (cfg settlementConfig) auditChallengeRunState(record settlementChallengeStoredResult) (*settlementRunStoredResult, []settlementChallengeAuditCheck, error) {
	checks := settlementChallengeAuditChecks{}
	if record.Response.Run == nil {
		if len(record.Response.Transfers) == 0 || strings.EqualFold(record.Response.Status, "failed") {
			checks.add("grouped_run_state", true, "", "no grouped run is expected for this stored failed challenge state", "", "")
			return nil, checks.items, nil
		}
		checks.add("grouped_run_state", false, "RUN_STATE_MISSING", "stored challenge response has transfers but no embedded grouped run", record.Request.SettlementRunID, "missing")
		return nil, checks.items, nil
	}

	runPath := cfg.runRecordPath(record.Request.SettlementRunID)
	runRecord, err := readSettlementRunStoredResult(runPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			checks.add("grouped_run_state", false, "RUN_STATE_MISSING", "stored grouped run state was not found", runPath, "missing")
			return nil, checks.items, nil
		}
		return nil, nil, err
	}

	checks.add("grouped_run_state", true, "", "stored grouped run state exists", runPath, runPath)
	checks.addEqual("grouped_run_fingerprint", "RUN_STATE_FINGERPRINT_MISMATCH", runRecord.Fingerprint, hashSettlementRunRequest(runRecord.Request))
	checks.addEqual("grouped_run_id", "RUN_STATE_MISMATCH", runRecord.Request.SettlementRunID, record.Request.SettlementRunID)
	checks.addEqual("grouped_run_status", "RUN_STATE_MISMATCH", runRecord.Response.Status, record.Response.Run.Status)
	checks.addEqual("grouped_run_requested_total", "RUN_STATE_MISMATCH", runRecord.Response.RequestedTotalUWolo, record.Response.Run.RequestedTotalUWolo)
	checks.addEqual("grouped_run_confirmed_total", "RUN_STATE_MISMATCH", runRecord.Response.ConfirmedTotalUWolo, record.Response.Run.ConfirmedTotalUWolo)

	runPayoutsByID := map[string]normalizedSettlementPayout{}
	for _, payout := range runRecord.Request.Payouts {
		runPayoutsByID[payout.RequestID] = payout
	}
	for _, transfer := range record.Request.Transfers {
		payout, ok := runPayoutsByID[transfer.RequestID]
		if !ok {
			checks.add(fmt.Sprintf("transfer_%d_grouped_run_request", transfer.Index), false, "RUN_STATE_MISMATCH", "challenge transfer request is missing from grouped run state", transfer.RequestID, "missing")
			continue
		}
		checks.addEqual(fmt.Sprintf("transfer_%d_grouped_run_to", transfer.Index), "RUN_STATE_MISMATCH", transfer.ToAddress, payout.ToAddress)
		checks.addEqual(fmt.Sprintf("transfer_%d_grouped_run_amount", transfer.Index), "RUN_STATE_MISMATCH", transfer.AmountUWolo, payout.AmountUWolo)
		checks.addEqual(fmt.Sprintf("transfer_%d_grouped_run_memo", transfer.Index), "RUN_STATE_MISMATCH", transfer.Memo, payout.Memo)
	}

	return &runRecord, checks.items, nil
}

func (cfg settlementConfig) auditChallengeTransfers(ctx context.Context, record settlementChallengeStoredResult, runRecord *settlementRunStoredResult) ([]settlementChallengeAuditTransfer, []settlementChallengeAuditCheck, int, error) {
	checks := settlementChallengeAuditChecks{}
	transfers := make([]settlementChallengeAuditTransfer, 0, len(record.Response.Transfers))
	runPayouts := map[string]settlementRunPayoutResult{}
	if runRecord != nil {
		for _, payout := range runRecord.Response.Payouts {
			runPayouts[payout.RequestID] = payout
		}
	}
	requestsByID := map[string]normalizedSettlementChallengeTransfer{}
	for _, request := range record.Request.Transfers {
		requestsByID[request.RequestID] = request
	}

	txChecked := 0
	for index, transfer := range record.Response.Transfers {
		request, requestFound := requestsByID[transfer.RequestID]
		audit := settlementChallengeAuditTransfer{
			Index:         index,
			RequestID:     transfer.RequestID,
			Bucket:        transfer.Bucket,
			Reason:        transfer.Reason,
			Status:        transfer.Status,
			Outcome:       transfer.Outcome,
			OK:            true,
			SignerAddress: transfer.SignerAddress,
			ToAddress:     transfer.ToAddress,
			AmountUWolo:   transfer.AmountUWolo,
			Memo:          transfer.Memo,
			TxHash:        transfer.TxHash,
			StatePath:     cfg.requestRecordPath(transfer.RequestID),
		}
		if !requestFound {
			audit.OK = false
			audit.FailureCode = "TRANSFER_STATE_MISMATCH"
			audit.Detail = "challenge transfer response has no matching normalized request line"
			checks.add(fmt.Sprintf("transfer_%d_request", index), false, audit.FailureCode, audit.Detail, transfer.RequestID, "missing")
		} else {
			checks.addEqual(fmt.Sprintf("transfer_%d_request_to", index), "TRANSFER_STATE_MISMATCH", request.ToAddress, transfer.ToAddress)
			checks.addEqual(fmt.Sprintf("transfer_%d_request_amount", index), "TRANSFER_STATE_MISMATCH", request.AmountUWolo, transfer.AmountUWolo)
			checks.addEqual(fmt.Sprintf("transfer_%d_request_bucket", index), "TRANSFER_STATE_MISMATCH", request.Bucket, transfer.Bucket)
			checks.addEqual(fmt.Sprintf("transfer_%d_request_reason", index), "TRANSFER_STATE_MISMATCH", request.Reason, transfer.Reason)
		}

		if runPayout, ok := runPayouts[transfer.RequestID]; ok {
			checks.addEqual(fmt.Sprintf("transfer_%d_run_status", index), "RUN_STATE_MISMATCH", runPayout.Status, transfer.Status)
			checks.addEqual(fmt.Sprintf("transfer_%d_run_tx_hash", index), "RUN_STATE_MISMATCH", runPayout.TxHash, transfer.TxHash)
		}

		stored, err := readSettlementStoredResult(audit.StatePath)
		if err != nil {
			if shouldHaveSettlementRequestState(transfer) {
				audit.OK = false
				audit.FailureCode = "TRANSFER_STATE_MISSING"
				audit.Detail = "stored single-transfer state was not found"
				checks.add(fmt.Sprintf("transfer_%d_state", index), false, audit.FailureCode, audit.Detail, audit.StatePath, "missing")
			} else {
				checks.add(fmt.Sprintf("transfer_%d_state", index), true, "", "single-transfer state is not required for this unattempted transfer", "", "")
			}
			transfers = append(transfers, audit)
			continue
		}

		checks.add(fmt.Sprintf("transfer_%d_state", index), true, "", "stored single-transfer state exists", audit.StatePath, audit.StatePath)
		checks.addEqual(fmt.Sprintf("transfer_%d_state_fingerprint", index), "TRANSFER_STATE_FINGERPRINT_MISMATCH", stored.Fingerprint, hashSettlementRequest(stored.Request, stored.Response.SignerAddress))
		checks.addEqual(fmt.Sprintf("transfer_%d_state_to", index), "TRANSFER_STATE_MISMATCH", stored.Request.ToAddress, transfer.ToAddress)
		checks.addEqual(fmt.Sprintf("transfer_%d_state_amount", index), "TRANSFER_STATE_MISMATCH", stored.Request.AmountUWolo, transfer.AmountUWolo)
		checks.addEqual(fmt.Sprintf("transfer_%d_state_memo", index), "TRANSFER_STATE_MISMATCH", stored.Request.Memo, transfer.Memo)
		checks.addEqual(fmt.Sprintf("transfer_%d_state_tx_hash", index), "TRANSFER_STATE_MISMATCH", stored.Response.TxHash, transfer.TxHash)

		if strings.TrimSpace(transfer.TxHash) == "" {
			if strings.EqualFold(transfer.Status, "confirmed") || strings.EqualFold(transfer.Status, "accepted") {
				audit.OK = false
				audit.FailureCode = "TRANSFER_TX_MISSING"
				audit.Detail = "executed transfer has no tx hash"
				checks.add(fmt.Sprintf("transfer_%d_tx", index), false, audit.FailureCode, audit.Detail, "tx hash", "missing")
			}
			transfers = append(transfers, audit)
			continue
		}

		lookup, err := cfg.lookupSettlementTx(ctx, transfer.TxHash, settlementLookupExpectations{
			Sender:      firstNonEmpty(transfer.SignerAddress, stored.Response.SignerAddress),
			Recipient:   transfer.ToAddress,
			AmountUWolo: transfer.AmountUWolo,
		})
		if err != nil {
			return nil, nil, 0, err
		}
		txChecked++
		audit.TxLookup = &lookup
		if mismatch := auditLookupMismatch(lookup, transfer.Status, transfer.Memo); mismatch != "" {
			audit.OK = false
			audit.FailureCode = "TRANSFER_TX_MISMATCH"
			audit.Detail = mismatch
			checks.add(fmt.Sprintf("transfer_%d_tx", index), false, audit.FailureCode, mismatch, transfer.TxHash, lookup.TxHash)
		} else {
			checks.add(fmt.Sprintf("transfer_%d_tx", index), true, "", "transfer tx reconciles with stored state and chain lookup", transfer.TxHash, lookup.TxHash)
		}
		transfers = append(transfers, audit)
	}

	return transfers, checks.items, txChecked, nil
}

func shouldHaveSettlementRequestState(transfer settlementChallengeTransferResult) bool {
	return transfer.Attempted || transfer.TxHash != "" || strings.EqualFold(transfer.Status, "confirmed") || strings.EqualFold(transfer.Status, "accepted")
}

func auditLookupMismatch(lookup settlementLookupResponse, storedStatus, memo string) string {
	if !lookup.OK {
		return firstNonEmpty(lookup.Detail, lookup.FailureCode, "tx lookup failed")
	}
	if !lookup.Found {
		return "tx hash was not found on WoloChain REST"
	}
	if !lookup.MatchedExpected {
		return "tx did not contain the expected sender, recipient, and amount transfer"
	}
	switch strings.TrimSpace(storedStatus) {
	case "confirmed", "accepted":
		if !lookup.TxSuccess {
			return fmt.Sprintf("stored transfer status is %s but tx failed with code %d", storedStatus, lookup.Code)
		}
	case "failed":
		if lookup.TxSuccess {
			return "stored transfer is failed/rejected but tx succeeded on chain"
		}
	}
	if strings.TrimSpace(memo) != "" && strings.TrimSpace(lookup.Memo) != strings.TrimSpace(memo) {
		return fmt.Sprintf("tx memo %q does not match stored memo %q", lookup.Memo, memo)
	}
	return ""
}

func (cfg settlementConfig) auditChallengeTopUp(ctx context.Context, record settlementChallengeStoredResult) (*settlementChallengeAuditTopUp, []settlementChallengeAuditCheck, error) {
	checks := settlementChallengeAuditChecks{}
	if record.Response.TopUp == nil {
		checks.add("top_up_state", true, "", "no top-up was planned for this challenge settlement", "", "")
		return nil, checks.items, nil
	}

	plan := record.Response.TopUp
	audit := &settlementChallengeAuditTopUp{
		Required:    plan.Required,
		OK:          true,
		RequestID:   plan.RequestID,
		FromAddress: plan.FromAddress,
		ToAddress:   plan.ToAddress,
		AmountUWolo: plan.AmountUWolo,
		StatePath:   cfg.requestRecordPath(plan.RequestID),
	}
	checks.add("top_up_state", true, "", "top-up plan is present in challenge state", plan.RequestID, plan.RequestID)
	if !plan.Required {
		return audit, checks.items, nil
	}
	if plan.Response == nil {
		audit.OK = false
		audit.FailureCode = "TOP_UP_STATE_MISSING"
		audit.Detail = "top-up was required but no execution response was stored"
		checks.add("top_up_response", false, audit.FailureCode, audit.Detail, "top-up response", "missing")
		return audit, checks.items, nil
	}

	audit.TxHash = plan.Response.TxHash
	checks.addEqual("top_up_response_amount", "TOP_UP_STATE_MISMATCH", plan.AmountUWolo, plan.Response.AmountUWolo)
	checks.addEqual("top_up_response_to", "TOP_UP_STATE_MISMATCH", plan.ToAddress, plan.Response.ToAddress)

	stored, err := readSettlementStoredResult(audit.StatePath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			audit.OK = false
			audit.FailureCode = "TOP_UP_STATE_MISSING"
			audit.Detail = "stored top-up transfer state was not found"
			checks.add("top_up_transfer_state", false, audit.FailureCode, audit.Detail, audit.StatePath, "missing")
			return audit, checks.items, nil
		}
		return nil, nil, err
	}
	checks.add("top_up_transfer_state", true, "", "stored top-up transfer state exists", audit.StatePath, audit.StatePath)
	checks.addEqual("top_up_state_fingerprint", "TOP_UP_STATE_FINGERPRINT_MISMATCH", stored.Fingerprint, hashSettlementRequest(stored.Request, stored.Response.SignerAddress))
	checks.addEqual("top_up_state_tx_hash", "TOP_UP_STATE_MISMATCH", stored.Response.TxHash, plan.Response.TxHash)

	if strings.TrimSpace(plan.Response.TxHash) == "" {
		audit.OK = false
		audit.FailureCode = "TOP_UP_TX_MISSING"
		audit.Detail = "executed top-up has no tx hash"
		checks.add("top_up_tx", false, audit.FailureCode, audit.Detail, "tx hash", "missing")
		return audit, checks.items, nil
	}

	lookup, err := cfg.lookupSettlementTx(ctx, plan.Response.TxHash, settlementLookupExpectations{
		Sender:      firstNonEmpty(plan.FromAddress, plan.Response.SignerAddress),
		Recipient:   plan.ToAddress,
		AmountUWolo: plan.AmountUWolo,
	})
	if err != nil {
		return nil, nil, err
	}
	audit.TxLookup = &lookup
	topUpMemo := "challenge top-up " + record.Request.SettlementRunID
	if len(topUpMemo) > 180 {
		topUpMemo = topUpMemo[:180]
	}
	if mismatch := auditLookupMismatch(lookup, plan.Response.Status, topUpMemo); mismatch != "" {
		audit.OK = false
		audit.FailureCode = "TOP_UP_TX_MISMATCH"
		audit.Detail = mismatch
		checks.add("top_up_tx", false, audit.FailureCode, mismatch, plan.Response.TxHash, lookup.TxHash)
	} else {
		checks.add("top_up_tx", true, "", "top-up tx reconciles with stored state and chain lookup", plan.Response.TxHash, lookup.TxHash)
	}

	return audit, checks.items, nil
}
