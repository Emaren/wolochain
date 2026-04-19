package cmd

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

const (
	settlementChallengeFundingMemoPrefix = "wolo.challenge.funding.v1:"
	settlementChallengeBucketWager       = "wager"
	settlementChallengeBucketGuarantee   = "guarantee"
)

var (
	settlementChallengeParticipantSidePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`)
	settlementChallengeReasonPattern          = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,31}$`)
)

type settlementChallengeFundingExpectation struct {
	Sender           string
	SourceApp        string
	ChallengeID      string
	SourceEventID    string
	ParticipantSide  string
	ParticipantID    string
	TotalFundedUWolo string
	WagerUWolo       string
	GuaranteeUWolo   string
}

type settlementChallengeFundingResult struct {
	Index                      int    `json:"index,omitempty"`
	OK                         bool   `json:"ok"`
	FailureCode                string `json:"failure_code,omitempty"`
	Detail                     string `json:"detail,omitempty"`
	DepositFound               bool   `json:"deposit_found"`
	FundingTxHash              string `json:"funding_tx_hash,omitempty"`
	SourceApp                  string `json:"source_app,omitempty"`
	ChallengeID                string `json:"challenge_id,omitempty"`
	SourceEventID              string `json:"source_event_id,omitempty"`
	ParticipantSide            string `json:"participant_side,omitempty"`
	ParticipantID              string `json:"participant_id,omitempty"`
	Sender                     string `json:"sender,omitempty"`
	EscrowAddress              string `json:"escrow_address,omitempty"`
	TotalFundedUWolo           string `json:"total_funded_uwolo,omitempty"`
	TotalFundedWolo            string `json:"total_funded_wolo,omitempty"`
	WagerUWolo                 string `json:"wager_uwolo,omitempty"`
	WagerWolo                  string `json:"wager_wolo,omitempty"`
	GuaranteeUWolo             string `json:"guarantee_uwolo,omitempty"`
	GuaranteeWolo              string `json:"guarantee_wolo,omitempty"`
	Memo                       string `json:"memo,omitempty"`
	CanonicalTxLookup          string `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string `json:"canonical_tx_lookup_public,omitempty"`
}

type settlementChallengeFundingVerifyResponse struct {
	OK          bool                              `json:"ok"`
	FailureCode string                            `json:"failure_code,omitempty"`
	Detail      string                            `json:"detail,omitempty"`
	Funding     *settlementChallengeFundingResult `json:"funding,omitempty"`
	Lookup      *settlementLookupResponse         `json:"lookup,omitempty"`
}

type settlementChallengeFundingRecentFilters struct {
	Limit           int
	Sender          string
	SourceApp       string
	ChallengeID     string
	SourceEventID   string
	ParticipantSide string
	ParticipantID   string
}

type settlementChallengeFundingRecentResponse struct {
	OK              bool                               `json:"ok"`
	FailureCode     string                             `json:"failure_code,omitempty"`
	Detail          string                             `json:"detail,omitempty"`
	Limit           int                                `json:"limit"`
	Count           int                                `json:"count"`
	SenderFilter    string                             `json:"sender_filter,omitempty"`
	SourceApp       string                             `json:"source_app,omitempty"`
	ChallengeID     string                             `json:"challenge_id,omitempty"`
	SourceEventID   string                             `json:"source_event_id,omitempty"`
	ParticipantSide string                             `json:"participant_side,omitempty"`
	ParticipantID   string                             `json:"participant_id,omitempty"`
	Funding         []settlementChallengeFundingResult `json:"funding,omitempty"`
}

type settlementChallengeRequest struct {
	SettlementRunID string                             `json:"settlement_run_id"`
	SourceApp       string                             `json:"source_app"`
	ChallengeID     string                             `json:"challenge_id,omitempty"`
	SourceEventID   string                             `json:"source_event_id,omitempty"`
	TreasuryAddress string                             `json:"treasury_address,omitempty"`
	Note            string                             `json:"note,omitempty"`
	Memo            string                             `json:"memo,omitempty"`
	Funding         []settlementChallengeFundingInput  `json:"funding"`
	Transfers       []settlementChallengeTransferInput `json:"transfers"`
}

type settlementChallengeFundingInput struct {
	FundingTxHash    string `json:"funding_tx_hash"`
	DepositorAddress string `json:"depositor_address,omitempty"`
	ParticipantSide  string `json:"participant_side,omitempty"`
	ParticipantID    string `json:"participant_id,omitempty"`
}

type settlementChallengeTransferInput struct {
	RequestID       string `json:"request_id,omitempty"`
	ParticipantSide string `json:"participant_side,omitempty"`
	ParticipantID   string `json:"participant_id,omitempty"`
	Bucket          string `json:"bucket"`
	Reason          string `json:"reason"`
	ToAddress       string `json:"to_address,omitempty"`
	AmountUWolo     string `json:"amount_uwolo,omitempty"`
	AmountWolo      int64  `json:"amount_wolo,omitempty"`
	Memo            string `json:"memo,omitempty"`
}

type normalizedSettlementChallengeFundingInput struct {
	FundingTxHash    string `json:"funding_tx_hash"`
	DepositorAddress string `json:"depositor_address,omitempty"`
	ParticipantSide  string `json:"participant_side,omitempty"`
	ParticipantID    string `json:"participant_id,omitempty"`
}

type normalizedSettlementChallengeTransfer struct {
	Index           int    `json:"index"`
	RequestID       string `json:"request_id"`
	ParticipantSide string `json:"participant_side,omitempty"`
	ParticipantID   string `json:"participant_id,omitempty"`
	Bucket          string `json:"bucket"`
	Reason          string `json:"reason"`
	ToAddress       string `json:"to_address"`
	AmountUWolo     string `json:"amount_uwolo"`
	Memo            string `json:"memo,omitempty"`
}

type normalizedSettlementChallengeRequest struct {
	SettlementRunID string                                      `json:"settlement_run_id"`
	SourceApp       string                                      `json:"source_app"`
	ChallengeID     string                                      `json:"challenge_id,omitempty"`
	SourceEventID   string                                      `json:"source_event_id,omitempty"`
	TreasuryAddress string                                      `json:"treasury_address,omitempty"`
	Note            string                                      `json:"note,omitempty"`
	Memo            string                                      `json:"memo,omitempty"`
	Funding         []normalizedSettlementChallengeFundingInput `json:"funding"`
	Transfers       []normalizedSettlementChallengeTransfer     `json:"transfers"`
}

type settlementChallengeTransferResult struct {
	Index                      int      `json:"index"`
	RequestID                  string   `json:"request_id"`
	ParticipantSide            string   `json:"participant_side,omitempty"`
	ParticipantID              string   `json:"participant_id,omitempty"`
	Bucket                     string   `json:"bucket,omitempty"`
	Reason                     string   `json:"reason,omitempty"`
	Attempted                  bool     `json:"attempted"`
	OK                         bool     `json:"ok"`
	Status                     string   `json:"status,omitempty"`
	Outcome                    string   `json:"outcome,omitempty"`
	FailureCode                string   `json:"failure_code,omitempty"`
	Retryable                  bool     `json:"retryable"`
	IdempotentReplay           bool     `json:"idempotent_replay"`
	SignerRole                 string   `json:"signer_role,omitempty"`
	SignerAddress              string   `json:"signer_address,omitempty"`
	ToAddress                  string   `json:"to_address,omitempty"`
	AmountUWolo                string   `json:"amount_uwolo,omitempty"`
	AmountWolo                 string   `json:"amount_wolo,omitempty"`
	Memo                       string   `json:"memo,omitempty"`
	TxHash                     string   `json:"tx_hash,omitempty"`
	Detail                     string   `json:"detail,omitempty"`
	CanonicalTxLookup          string   `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string   `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string   `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string   `json:"canonical_tx_lookup_public,omitempty"`
	Warnings                   []string `json:"warnings,omitempty"`
}

type settlementChallengeBucketTotals struct {
	Bucket         string `json:"bucket"`
	RequestedUWolo string `json:"requested_uwolo,omitempty"`
	RequestedWolo  string `json:"requested_wolo,omitempty"`
	ExecutedUWolo  string `json:"executed_uwolo,omitempty"`
	ExecutedWolo   string `json:"executed_wolo,omitempty"`
	ConfirmedUWolo string `json:"confirmed_uwolo,omitempty"`
	ConfirmedWolo  string `json:"confirmed_wolo,omitempty"`
	AcceptedUWolo  string `json:"accepted_uwolo,omitempty"`
	AcceptedWolo   string `json:"accepted_wolo,omitempty"`
	RefusedUWolo   string `json:"refused_uwolo,omitempty"`
	RefusedWolo    string `json:"refused_wolo,omitempty"`
	RejectedUWolo  string `json:"rejected_uwolo,omitempty"`
	RejectedWolo   string `json:"rejected_wolo,omitempty"`
}

type settlementChallengeTopUpResult struct {
	Required                   bool                       `json:"required"`
	Enabled                    bool                       `json:"enabled"`
	Possible                   bool                       `json:"possible"`
	FailureCode                string                     `json:"failure_code,omitempty"`
	Detail                     string                     `json:"detail,omitempty"`
	RequestID                  string                     `json:"request_id,omitempty"`
	SignerRole                 string                     `json:"signer_role,omitempty"`
	FromAddress                string                     `json:"from_address,omitempty"`
	ToAddress                  string                     `json:"to_address,omitempty"`
	AmountUWolo                string                     `json:"amount_uwolo,omitempty"`
	AmountWolo                 string                     `json:"amount_wolo,omitempty"`
	PayoutBalanceBeforeUWolo   string                     `json:"payout_balance_before_uwolo,omitempty"`
	PayoutBalanceBeforeWolo    string                     `json:"payout_balance_before_wolo,omitempty"`
	RequiredPayoutBalanceUWolo string                     `json:"required_payout_balance_uwolo,omitempty"`
	RequiredPayoutBalanceWolo  string                     `json:"required_payout_balance_wolo,omitempty"`
	EscrowBalanceUWolo         string                     `json:"escrow_balance_uwolo,omitempty"`
	EscrowBalanceWolo          string                     `json:"escrow_balance_wolo,omitempty"`
	Response                   *settlementExecuteResponse `json:"response,omitempty"`
}

type settlementChallengeResponse struct {
	OK                     bool                                `json:"ok"`
	DryRun                 bool                                `json:"dry_run"`
	Status                 string                              `json:"status,omitempty"`
	FailureCode            string                              `json:"failure_code,omitempty"`
	Retryable              bool                                `json:"retryable"`
	IdempotentReplay       bool                                `json:"idempotent_replay"`
	SettlementRunID        string                              `json:"settlement_run_id"`
	SourceApp              string                              `json:"source_app,omitempty"`
	ChallengeID            string                              `json:"challenge_id,omitempty"`
	SourceEventID          string                              `json:"source_event_id,omitempty"`
	TreasuryAddress        string                              `json:"treasury_address,omitempty"`
	Note                   string                              `json:"note,omitempty"`
	Memo                   string                              `json:"memo,omitempty"`
	ParticipantCount       int                                 `json:"participant_count"`
	FundingCount           int                                 `json:"funding_count"`
	FundingVerifiedCount   int                                 `json:"funding_verified_count"`
	RequestedTransferCount int                                 `json:"requested_transfer_count"`
	ExecutedTransferCount  int                                 `json:"executed_transfer_count"`
	ConfirmedTransferCount int                                 `json:"confirmed_transfer_count"`
	AcceptedTransferCount  int                                 `json:"accepted_transfer_count"`
	RefusedTransferCount   int                                 `json:"refused_transfer_count"`
	RejectedTransferCount  int                                 `json:"rejected_transfer_count"`
	ReplayTransferCount    int                                 `json:"replay_transfer_count"`
	FundingTotalUWolo      string                              `json:"funding_total_uwolo,omitempty"`
	FundingTotalWolo       string                              `json:"funding_total_wolo,omitempty"`
	RequestedTotalUWolo    string                              `json:"requested_total_uwolo,omitempty"`
	RequestedTotalWolo     string                              `json:"requested_total_wolo,omitempty"`
	ExecutedTotalUWolo     string                              `json:"executed_total_uwolo,omitempty"`
	ExecutedTotalWolo      string                              `json:"executed_total_wolo,omitempty"`
	ConfirmedTotalUWolo    string                              `json:"confirmed_total_uwolo,omitempty"`
	ConfirmedTotalWolo     string                              `json:"confirmed_total_wolo,omitempty"`
	AcceptedTotalUWolo     string                              `json:"accepted_total_uwolo,omitempty"`
	AcceptedTotalWolo      string                              `json:"accepted_total_wolo,omitempty"`
	RefusedTotalUWolo      string                              `json:"refused_total_uwolo,omitempty"`
	RefusedTotalWolo       string                              `json:"refused_total_wolo,omitempty"`
	RejectedTotalUWolo     string                              `json:"rejected_total_uwolo,omitempty"`
	RejectedTotalWolo      string                              `json:"rejected_total_wolo,omitempty"`
	BucketTotals           []settlementChallengeBucketTotals   `json:"bucket_totals,omitempty"`
	TopUp                  *settlementChallengeTopUpResult     `json:"top_up,omitempty"`
	Detail                 string                              `json:"detail,omitempty"`
	Funding                []settlementChallengeFundingResult  `json:"funding,omitempty"`
	Transfers              []settlementChallengeTransferResult `json:"transfers,omitempty"`
	Run                    *settlementRunResponse              `json:"run,omitempty"`
}

type settlementChallengeStoredResult struct {
	Request     normalizedSettlementChallengeRequest `json:"request"`
	Fingerprint string                               `json:"fingerprint"`
	Response    settlementChallengeResponse          `json:"response"`
	UpdatedAt   time.Time                            `json:"updated_at"`
}

type settlementChallengeInspectResponse struct {
	Found           bool                             `json:"found"`
	SettlementRunID string                           `json:"settlement_run_id"`
	ChallengePath   string                           `json:"challenge_path,omitempty"`
	Summary         *settlementChallengeSummary      `json:"summary,omitempty"`
	Record          *settlementChallengeStoredResult `json:"record,omitempty"`
}

type settlementChallengeRecentItem struct {
	SettlementRunID string                          `json:"settlement_run_id"`
	ChallengePath   string                          `json:"challenge_path"`
	UpdatedAt       time.Time                       `json:"updated_at"`
	Summary         settlementChallengeSummary      `json:"summary"`
	Record          settlementChallengeStoredResult `json:"record"`
}

type settlementChallengeRecentResponse struct {
	Count   int                              `json:"count"`
	Summary settlementChallengeRecentSummary `json:"summary"`
	Items   []settlementChallengeRecentItem  `json:"items,omitempty"`
}

type settlementChallengeSummary struct {
	SettlementRunID        string    `json:"settlement_run_id"`
	UpdatedAt              time.Time `json:"updated_at,omitempty"`
	Status                 string    `json:"status,omitempty"`
	FailureCode            string    `json:"failure_code,omitempty"`
	Retryable              bool      `json:"retryable"`
	IdempotentReplay       bool      `json:"idempotent_replay"`
	SourceApp              string    `json:"source_app,omitempty"`
	ChallengeID            string    `json:"challenge_id,omitempty"`
	SourceEventID          string    `json:"source_event_id,omitempty"`
	TreasuryAddress        string    `json:"treasury_address,omitempty"`
	ParticipantCount       int       `json:"participant_count"`
	FundingVerifiedCount   int       `json:"funding_verified_count"`
	RequestedTransferCount int       `json:"requested_transfer_count"`
	ExecutedTransferCount  int       `json:"executed_transfer_count"`
	ConfirmedTransferCount int       `json:"confirmed_transfer_count"`
	AcceptedTransferCount  int       `json:"accepted_transfer_count"`
	RefusedTransferCount   int       `json:"refused_transfer_count"`
	RejectedTransferCount  int       `json:"rejected_transfer_count"`
	ReplayTransferCount    int       `json:"replay_transfer_count"`
	FundingTotalUWolo      string    `json:"funding_total_uwolo,omitempty"`
	RequestedTotalUWolo    string    `json:"requested_total_uwolo,omitempty"`
	TopUpRequired          bool      `json:"top_up_required"`
	TopUpExecuted          bool      `json:"top_up_executed"`
	TopUpTxHash            string    `json:"top_up_tx_hash,omitempty"`
	Detail                 string    `json:"detail,omitempty"`
}

type settlementChallengeRecentSummary struct {
	RequestedLimit    int            `json:"requested_limit"`
	Returned          int            `json:"returned"`
	StatusFilter      string         `json:"status_filter,omitempty"`
	FailureCodeFilter string         `json:"failure_code_filter,omitempty"`
	FailedCount       int            `json:"failed_count"`
	PartialCount      int            `json:"partial_count"`
	ConfirmedCount    int            `json:"confirmed_count"`
	AcceptedCount     int            `json:"accepted_count"`
	ReplayCount       int            `json:"replay_count"`
	RetryableCount    int            `json:"retryable_count"`
	FailureCodes      map[string]int `json:"failure_codes,omitempty"`
}

type verifiedSettlementChallengeFunding struct {
	Result settlementChallengeFundingResult
}

type settlementChallengePlan struct {
	Normalized normalizedSettlementChallengeRequest
	Response   settlementChallengeResponse
	RunRequest settlementRunRequest
}

func newSettlementChallengeCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "challenge",
		Short: "Challenge funding proofs and bucket-aware settlement primitives",
	}

	cmd.AddCommand(
		newSettlementChallengeFundingCmd(),
		newSettlementChallengeValidateCmd(),
		newSettlementChallengeExecuteCmd(),
		newSettlementChallengeInspectCmd(),
		newSettlementChallengeRecentCmd(),
	)

	return cmd
}

func newSettlementChallengeFundingCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "funding",
		Short: "Verify and discover challenge funding deposits in escrow",
	}

	cmd.AddCommand(
		newSettlementChallengeFundingVerifyCmd(),
		newSettlementChallengeFundingRecentCmd(),
	)

	return cmd
}

func newSettlementChallengeFundingVerifyCmd() *cobra.Command {
	var (
		txHash          string
		expectedSender  string
		sourceApp       string
		challengeID     string
		sourceEventID   string
		participantSide string
		participantID   string
		expectedAmount  string
		wagerUWolo      string
		guaranteeUWolo  string
	)

	cmd := &cobra.Command{
		Use:   "verify",
		Short: "Verify a challenge funding deposit against the canonical memo convention",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.verifyChallengeFundingDeposit(cmd.Context(), txHash, settlementChallengeFundingExpectation{
				Sender:           expectedSender,
				SourceApp:        sourceApp,
				ChallengeID:      challengeID,
				SourceEventID:    sourceEventID,
				ParticipantSide:  participantSide,
				ParticipantID:    participantID,
				TotalFundedUWolo: expectedAmount,
				WagerUWolo:       wagerUWolo,
				GuaranteeUWolo:   guaranteeUWolo,
			})
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&txHash, "tx-hash", "", "Funding tx hash to verify")
	cmd.Flags().StringVar(&expectedSender, "expected-sender", "", "Expected depositor address")
	cmd.Flags().StringVar(&sourceApp, "source-app", "", "Expected source app")
	cmd.Flags().StringVar(&challengeID, "challenge-id", "", "Expected challenge id")
	cmd.Flags().StringVar(&sourceEventID, "source-event-id", "", "Expected source event id")
	cmd.Flags().StringVar(&participantSide, "participant-side", "", "Expected participant side, such as left or right")
	cmd.Flags().StringVar(&participantID, "participant-id", "", "Expected participant identity")
	cmd.Flags().StringVar(&expectedAmount, "expected-amount-uwolo", "", "Expected total funded uwolo")
	cmd.Flags().StringVar(&wagerUWolo, "wager-uwolo", "", "Expected wager bucket in uwolo")
	cmd.Flags().StringVar(&guaranteeUWolo, "guarantee-uwolo", "", "Expected guarantee bucket in uwolo")
	return cmd
}

func newSettlementChallengeFundingRecentCmd() *cobra.Command {
	var filters settlementChallengeFundingRecentFilters

	cmd := &cobra.Command{
		Use:   "recent",
		Short: "List recent challenge funding deposits parsed from escrow transfers",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.listRecentChallengeFundingDeposits(cmd.Context(), filters)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().IntVar(&filters.Limit, "limit", 20, "Maximum number of challenge funding deposits to return")
	cmd.Flags().StringVar(&filters.Sender, "sender", "", "Optional depositor address filter")
	cmd.Flags().StringVar(&filters.SourceApp, "source-app", "", "Optional source app filter")
	cmd.Flags().StringVar(&filters.ChallengeID, "challenge-id", "", "Optional challenge id filter")
	cmd.Flags().StringVar(&filters.SourceEventID, "source-event-id", "", "Optional source event id filter")
	cmd.Flags().StringVar(&filters.ParticipantSide, "participant-side", "", "Optional participant side filter")
	cmd.Flags().StringVar(&filters.ParticipantID, "participant-id", "", "Optional participant identity filter")
	return cmd
}

func newSettlementChallengeValidateCmd() *cobra.Command {
	var filePath string

	cmd := &cobra.Command{
		Use:   "validate",
		Short: "Dry-run a bucket-aware challenge settlement without broadcasting transfers",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			request := settlementChallengeRequest{}
			if err := readJSONInput(filePath, &request); err != nil {
				return err
			}

			response, err := cfg.validateSettlementChallenge(cmd.Context(), request)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&filePath, "file", "-", "JSON file path for the challenge settlement payload, or - for stdin")
	return cmd
}

func newSettlementChallengeExecuteCmd() *cobra.Command {
	var filePath string

	cmd := &cobra.Command{
		Use:   "execute",
		Short: "Execute a bucket-aware challenge settlement over the existing payout rail",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			request := settlementChallengeRequest{}
			if err := readJSONInput(filePath, &request); err != nil {
				return err
			}

			response, err := cfg.executeSettlementChallenge(cmd.Context(), request)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&filePath, "file", "-", "JSON file path for the challenge settlement payload, or - for stdin")
	return cmd
}

func newSettlementChallengeInspectCmd() *cobra.Command {
	var (
		settlementID string
		summaryOnly  bool
	)

	cmd := &cobra.Command{
		Use:   "inspect",
		Short: "Inspect stored challenge settlement state by settlement id",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.inspectSettlementChallenge(settlementID)
			if err != nil {
				return err
			}
			if summaryOnly {
				response.Record = nil
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&settlementID, "settlement-id", "", "Stored challenge settlement id")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only concise operator summary fields")
	return cmd
}

func newSettlementChallengeRecentCmd() *cobra.Command {
	var (
		limit       int
		status      string
		failureCode string
		summaryOnly bool
	)

	cmd := &cobra.Command{
		Use:   "recent",
		Short: "List recent challenge settlement records for operator triage",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			status = strings.TrimSpace(strings.ToLower(status))
			switch status {
			case "", "all", "failed", "partial", "confirmed", "accepted":
			default:
				return fmt.Errorf("--status must be one of all, failed, partial, confirmed, accepted")
			}
			failureCode = strings.TrimSpace(strings.ToUpper(failureCode))
			if limit <= 0 {
				return errors.New("--limit must be greater than zero")
			}

			items, err := cfg.listRecentSettlementChallenges(limit, status, failureCode)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), settlementChallengeRecentResponse{
				Count:   len(items),
				Summary: summarizeSettlementChallengeRecentItems(limit, status, failureCode, items),
				Items:   optionalSettlementChallengeRecentItems(summaryOnly, items),
			})
		},
	}

	cmd.Flags().IntVar(&limit, "limit", 20, "Maximum number of stored challenge settlements to return")
	cmd.Flags().StringVar(&status, "status", "all", "Filter by stored challenge status: all, failed, partial, confirmed, accepted")
	cmd.Flags().StringVar(&failureCode, "failure-code", "", "Optional stored failure code filter")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only summary/count data without embedded records")
	return cmd
}

func (cfg settlementConfig) validateSettlementChallenge(ctx context.Context, request settlementChallengeRequest) (settlementChallengeResponse, error) {
	plan, err := cfg.buildSettlementChallengePlan(ctx, request)
	if err != nil {
		return settlementChallengeResponse{}, err
	}

	plan.Response.DryRun = true
	return plan.Response, nil
}

func (cfg settlementConfig) executeSettlementChallenge(ctx context.Context, request settlementChallengeRequest) (settlementChallengeResponse, error) {
	plan, err := cfg.buildSettlementChallengePlan(ctx, request)
	if err != nil {
		return settlementChallengeResponse{}, err
	}

	response := plan.Response
	response.DryRun = false
	settlementID := strings.TrimSpace(response.SettlementRunID)
	if settlementID == "" {
		return response, nil
	}

	recordPath := cfg.challengeRecordPath(settlementID)
	fingerprint := hashSettlementChallengeRequest(plan.Normalized)

	response, err = cfg.withChallengeLock(settlementID, func() (settlementChallengeResponse, error) {
		stored, readErr := readSettlementChallengeStoredResult(recordPath)
		if readErr == nil {
			if stored.Fingerprint != fingerprint {
				return settlementChallengeResponse{
					OK:              false,
					DryRun:          false,
					Status:          "failed",
					FailureCode:     "IDEMPOTENCY_CONFLICT",
					Retryable:       false,
					SettlementRunID: settlementID,
					SourceApp:       response.SourceApp,
					ChallengeID:     response.ChallengeID,
					SourceEventID:   response.SourceEventID,
					TreasuryAddress: response.TreasuryAddress,
					Note:            response.Note,
					Memo:            response.Memo,
					Detail:          "settlement_run_id already exists with different challenge settlement payload",
				}, nil
			}

			if settlementChallengeResponseIsFinal(stored.Response) {
				replayed := stored.Response
				replayed.DryRun = false
				replayed.IdempotentReplay = true
				return replayed, nil
			}
		} else if !errors.Is(readErr, os.ErrNotExist) {
			return settlementChallengeResponse{
				OK:              false,
				DryRun:          false,
				Status:          "failed",
				FailureCode:     "STATE_FILE_INVALID",
				Retryable:       false,
				SettlementRunID: settlementID,
				SourceApp:       response.SourceApp,
				ChallengeID:     response.ChallengeID,
				SourceEventID:   response.SourceEventID,
				TreasuryAddress: response.TreasuryAddress,
				Note:            response.Note,
				Memo:            response.Memo,
				Detail:          fmt.Sprintf("could not read challenge settlement state file: %v", readErr),
			}, nil
		}

		response := plan.Response
		response.DryRun = false
		if !response.OK {
			response.Transfers = markChallengeReadyTransfersFailed(response.Transfers, response.FailureCode, response.Detail, response.Retryable)
			response = finalizeSettlementChallengeResponse(response)
			if err := writeSettlementChallengeStoredResult(recordPath, settlementChallengeStoredResult{
				Request:     plan.Normalized,
				Fingerprint: fingerprint,
				Response:    response,
				UpdatedAt:   time.Now().UTC(),
			}); err != nil {
				return settlementChallengeResponse{}, err
			}
			return response, nil
		}

		if response.TopUp != nil && response.TopUp.Required {
			topUpResult, err := cfg.executeChallengeTopUp(ctx, settlementID, *response.TopUp)
			if err != nil {
				return settlementChallengeResponse{}, err
			}
			response.TopUp = topUpResult
			if topUpResult.Response == nil || !topUpResult.Response.OK {
				response.OK = false
				response.Status = "failed"
				response.FailureCode = firstNonEmpty(topUpResult.FailureCode, "ESCROW_TOP_UP_FAILED")
				response.Retryable = topUpResult.Response != nil && topUpResult.Response.Retryable
				response.Detail = firstNonEmpty(topUpResult.Detail, "escrow top-up failed")
				response.Transfers = markChallengeReadyTransfersFailed(response.Transfers, response.FailureCode, response.Detail, response.Retryable)
				response = finalizeSettlementChallengeResponse(response)
				if err := writeSettlementChallengeStoredResult(recordPath, settlementChallengeStoredResult{
					Request:     plan.Normalized,
					Fingerprint: fingerprint,
					Response:    response,
					UpdatedAt:   time.Now().UTC(),
				}); err != nil {
					return settlementChallengeResponse{}, err
				}
				return response, nil
			}
		}

		runResponse, err := cfg.executeSettlementRun(ctx, plan.RunRequest)
		if err != nil {
			return settlementChallengeResponse{}, err
		}

		response.Run = &runResponse
		response.Transfers = mergeChallengeRunResults(plan.Normalized.Transfers, runResponse)
		response.Status = ""
		response.OK = false
		response.FailureCode = ""
		response.Retryable = runResponse.Retryable
		response.IdempotentReplay = false
		response = finalizeSettlementChallengeResponse(response)
		response.Detail = settlementChallengeExecutionDetail(response)
		if err := writeSettlementChallengeStoredResult(recordPath, settlementChallengeStoredResult{
			Request:     plan.Normalized,
			Fingerprint: fingerprint,
			Response:    response,
			UpdatedAt:   time.Now().UTC(),
		}); err != nil {
			return settlementChallengeResponse{}, err
		}
		return response, nil
	})
	if err != nil {
		return settlementChallengeResponse{}, err
	}

	return response, nil
}

func (cfg settlementConfig) buildSettlementChallengePlan(ctx context.Context, request settlementChallengeRequest) (settlementChallengePlan, error) {
	settlementID := strings.TrimSpace(request.SettlementRunID)
	sourceApp := strings.TrimSpace(request.SourceApp)
	challengeID := strings.TrimSpace(request.ChallengeID)
	sourceEventID := strings.TrimSpace(request.SourceEventID)
	treasuryAddress := strings.TrimSpace(request.TreasuryAddress)
	if treasuryAddress == "" {
		treasuryAddress = strings.TrimSpace(cfg.TreasuryAddress)
	}
	note := strings.TrimSpace(request.Note)
	memo := strings.TrimSpace(request.Memo)
	if len(note) > 280 {
		note = note[:280]
	}
	if len(memo) > 180 {
		memo = memo[:180]
	}

	response := settlementChallengeResponse{
		OK:              false,
		DryRun:          true,
		Status:          "failed",
		SettlementRunID: settlementID,
		SourceApp:       sourceApp,
		ChallengeID:     challengeID,
		SourceEventID:   sourceEventID,
		TreasuryAddress: treasuryAddress,
		Note:            note,
		Memo:            memo,
		FundingCount:    len(request.Funding),
	}
	normalized := normalizedSettlementChallengeRequest{
		SettlementRunID: settlementID,
		SourceApp:       sourceApp,
		ChallengeID:     challengeID,
		SourceEventID:   sourceEventID,
		TreasuryAddress: treasuryAddress,
		Note:            note,
		Memo:            memo,
		Funding:         make([]normalizedSettlementChallengeFundingInput, 0, len(request.Funding)),
		Transfers:       make([]normalizedSettlementChallengeTransfer, 0, len(request.Transfers)),
	}

	validationErrors := make([]string, 0)
	if err := validateSettlementRunID(settlementID); err != nil {
		validationErrors = append(validationErrors, err.Error())
	}
	if normalizedSourceApp, err := normalizeSettlementRunMetadataID("source_app", sourceApp, 64, settlementRequestIDPattern); err != nil || normalizedSourceApp == "" {
		if err != nil {
			validationErrors = append(validationErrors, err.Error())
		} else {
			validationErrors = append(validationErrors, "source_app is required")
		}
	} else {
		sourceApp = normalizedSourceApp
	}
	if normalizedChallengeID, err := normalizeSettlementRunMetadataID("challenge_id", challengeID, 128, settlementSourceEventPattern); err != nil {
		validationErrors = append(validationErrors, err.Error())
	} else {
		challengeID = normalizedChallengeID
	}
	if normalizedSourceEventID, err := normalizeSettlementRunMetadataID("source_event_id", sourceEventID, 128, settlementSourceEventPattern); err != nil {
		validationErrors = append(validationErrors, err.Error())
	} else {
		sourceEventID = normalizedSourceEventID
	}
	if challengeID == "" && sourceEventID == "" {
		validationErrors = append(validationErrors, "challenge_id or source_event_id is required")
	}
	if treasuryAddress != "" && !isWoloAddress(treasuryAddress, cfg.AddressPrefix) {
		validationErrors = append(validationErrors, "treasury_address must be a valid WOLO address")
	}
	if len(request.Funding) == 0 {
		validationErrors = append(validationErrors, "funding must contain at least one verified escrow deposit")
	}
	if len(request.Transfers) == 0 {
		validationErrors = append(validationErrors, "transfers must contain at least one bucket movement")
	}
	response.SourceApp = sourceApp
	response.ChallengeID = challengeID
	response.SourceEventID = sourceEventID
	response.TreasuryAddress = treasuryAddress
	normalized.SourceApp = sourceApp
	normalized.ChallengeID = challengeID
	normalized.SourceEventID = sourceEventID
	normalized.TreasuryAddress = treasuryAddress
	if len(validationErrors) > 0 {
		response.FailureCode = "INVALID_CHALLENGE"
		response.Detail = strings.Join(validationErrors, "; ")
		return settlementChallengePlan{Normalized: normalized, Response: response}, nil
	}

	response.Funding = make([]settlementChallengeFundingResult, len(request.Funding))
	verifiedFunding := make([]verifiedSettlementChallengeFunding, 0, len(request.Funding))
	var fundedTotal uint64
	for index, fundingInput := range request.Funding {
		normalizedFunding := normalizedSettlementChallengeFundingInput{
			FundingTxHash:    normalizeTxHash(fundingInput.FundingTxHash),
			DepositorAddress: strings.TrimSpace(fundingInput.DepositorAddress),
			ParticipantSide:  strings.TrimSpace(fundingInput.ParticipantSide),
			ParticipantID:    strings.TrimSpace(fundingInput.ParticipantID),
		}
		normalized.Funding = append(normalized.Funding, normalizedFunding)
		verifyResponse, err := cfg.verifyChallengeFundingDeposit(ctx, normalizedFunding.FundingTxHash, settlementChallengeFundingExpectation{
			Sender:          normalizedFunding.DepositorAddress,
			SourceApp:       sourceApp,
			ChallengeID:     challengeID,
			SourceEventID:   sourceEventID,
			ParticipantSide: normalizedFunding.ParticipantSide,
			ParticipantID:   normalizedFunding.ParticipantID,
		})
		if err != nil {
			return settlementChallengePlan{}, err
		}
		if verifyResponse.Funding != nil {
			verifyResponse.Funding.Index = index
			response.Funding[index] = *verifyResponse.Funding
		} else {
			response.Funding[index] = settlementChallengeFundingResult{
				Index:         index,
				OK:            false,
				FundingTxHash: normalizedFunding.FundingTxHash,
				FailureCode:   firstNonEmpty(verifyResponse.FailureCode, "INVALID_CHALLENGE"),
				Detail:        verifyResponse.Detail,
			}
		}
		if !verifyResponse.OK || verifyResponse.Funding == nil {
			continue
		}

		amount, err := parseOptionalUWoloString(verifyResponse.Funding.TotalFundedUWolo)
		if err == nil {
			fundedTotal += amount
		}
		verifiedFunding = append(verifiedFunding, verifiedSettlementChallengeFunding{Result: *verifyResponse.Funding})
		response.FundingVerifiedCount++
	}
	response.FundingCount = len(response.Funding)
	response.FundingTotalUWolo = strconv.FormatUint(fundedTotal, 10)
	response.FundingTotalWolo = formatDisplayAmount(response.FundingTotalUWolo)
	if response.FundingVerifiedCount != len(request.Funding) {
		response.FailureCode = "INVALID_CHALLENGE"
		if response.Detail == "" {
			response.Detail = "one or more funding deposits could not be verified against the challenge funding memo convention"
		}
		return settlementChallengePlan{Normalized: normalized, Response: finalizeSettlementChallengeResponse(response)}, nil
	}

	participantErrors := validateVerifiedChallengeFundingParticipants(verifiedFunding)
	if len(participantErrors) > 0 {
		response.FailureCode = "INVALID_CHALLENGE"
		response.Detail = strings.Join(participantErrors, "; ")
		return settlementChallengePlan{Normalized: normalized, Response: finalizeSettlementChallengeResponse(response)}, nil
	}
	response.ParticipantCount = len(verifiedFunding)

	response.Transfers = make([]settlementChallengeTransferResult, len(request.Transfers))
	runRequest := settlementRunRequest{
		SettlementRunID: settlementID,
		SourceApp:       sourceApp,
		SourceEventID:   firstNonEmpty(sourceEventID, challengeID),
		Note:            note,
		Memo:            memo,
		Payouts:         make([]settlementRunPayoutInput, 0, len(request.Transfers)),
	}

	allocation := map[string]map[string]uint64{}
	seenRequestIDs := map[string]struct{}{}
	var requestedTotal uint64
	for index, transfer := range request.Transfers {
		normalizedTransfer, transferResult, validatedAmount := normalizeSettlementChallengeTransfer(transfer, settlementID, index, memo, treasuryAddress, cfg.AddressPrefix)
		response.Transfers[index] = transferResult
		normalized.Transfers = append(normalized.Transfers, normalizedTransfer)
		if transferResult.FailureCode != "" {
			continue
		}

		funding, matchErr := resolveChallengeFundingParticipant(verifiedFunding, normalizedTransfer.ParticipantSide, normalizedTransfer.ParticipantID)
		if matchErr != "" {
			response.Transfers[index].FailureCode = "INVALID_TRANSFER_PARTICIPANT"
			response.Transfers[index].Detail = matchErr
			response.Transfers[index].Status = "failed"
			response.Transfers[index].Outcome = "invalid"
			continue
		}

		if strings.EqualFold(normalizedTransfer.Reason, "treasury") && treasuryAddress != "" && !strings.EqualFold(normalizedTransfer.ToAddress, treasuryAddress) {
			response.Transfers[index].FailureCode = "INVALID_TREASURY_ROUTE"
			response.Transfers[index].Detail = "treasury transfer must route to the configured treasury_address"
			response.Transfers[index].Status = "failed"
			response.Transfers[index].Outcome = "invalid"
			continue
		}

		key := challengeFundingIdentityKey(funding.Result.ParticipantSide, funding.Result.ParticipantID, funding.Result.FundingTxHash)
		if _, ok := allocation[key]; !ok {
			allocation[key] = map[string]uint64{}
		}
		allocation[key][normalizedTransfer.Bucket] += validatedAmount
		response.Transfers[index].OK = true
		response.Transfers[index].Status = "validated"
		response.Transfers[index].Outcome = "ready"
		response.Transfers[index].ParticipantSide = funding.Result.ParticipantSide
		response.Transfers[index].ParticipantID = funding.Result.ParticipantID
		response.Transfers[index].AmountUWolo = normalizedTransfer.AmountUWolo
		response.Transfers[index].AmountWolo = formatDisplayAmount(normalizedTransfer.AmountUWolo)
		if _, exists := seenRequestIDs[normalizedTransfer.RequestID]; exists {
			response.Transfers[index].OK = false
			response.Transfers[index].Status = "failed"
			response.Transfers[index].Outcome = "invalid"
			response.Transfers[index].FailureCode = "DUPLICATE_REQUEST_ID"
			response.Transfers[index].Detail = fmt.Sprintf("request_id %q appears more than once in this challenge settlement", normalizedTransfer.RequestID)
			continue
		}
		seenRequestIDs[normalizedTransfer.RequestID] = struct{}{}

		requestedTotal += validatedAmount
		runRequest.Payouts = append(runRequest.Payouts, settlementRunPayoutInput{
			RequestID:   normalizedTransfer.RequestID,
			ToAddress:   normalizedTransfer.ToAddress,
			AmountUWolo: normalizedTransfer.AmountUWolo,
			Memo:        normalizedTransfer.Memo,
		})
	}

	response.RequestedTransferCount = len(response.Transfers)
	response.RequestedTotalUWolo = strconv.FormatUint(requestedTotal, 10)
	response.RequestedTotalWolo = formatDisplayAmount(response.RequestedTotalUWolo)

	bucketErrors := validateChallengeBucketAllocation(verifiedFunding, allocation)
	if len(bucketErrors) > 0 {
		response.FailureCode = "INVALID_CHALLENGE"
		if response.Detail != "" {
			response.Detail += "; "
		}
		response.Detail += strings.Join(bucketErrors, "; ")
		return settlementChallengePlan{Normalized: normalized, Response: finalizeSettlementChallengeResponse(response)}, nil
	}
	if hasInvalidChallengeTransfers(response.Transfers) {
		response.FailureCode = "INVALID_CHALLENGE"
		if response.Detail == "" {
			response.Detail = "one or more challenge transfer lines are invalid"
		}
		return settlementChallengePlan{Normalized: normalized, Response: finalizeSettlementChallengeResponse(response)}, nil
	}

	runValidation, err := cfg.validateSettlementRun(ctx, runRequest)
	if err != nil {
		return settlementChallengePlan{}, err
	}
	response.Run = &runValidation

	topUp, err := cfg.buildChallengeTopUpPlan(ctx, settlementID, runValidation)
	if err != nil {
		return settlementChallengePlan{}, err
	}
	if topUp != nil {
		response.TopUp = topUp
	}

	switch {
	case response.TopUp != nil && response.TopUp.Required && !response.TopUp.Enabled:
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "PAYOUT_TOP_UP_REQUIRED"
		response.Retryable = true
		response.Detail = firstNonEmpty(response.TopUp.Detail, "escrow top-up is required before executing this challenge settlement")
	case response.TopUp != nil && response.TopUp.Required && !response.TopUp.Possible:
		response.OK = false
		response.Status = "failed"
		response.FailureCode = firstNonEmpty(response.TopUp.FailureCode, "ESCROW_TOP_UP_UNAVAILABLE")
		response.Retryable = strings.HasSuffix(response.FailureCode, "_LOOKUP_FAILED") || strings.HasSuffix(response.FailureCode, "_TOO_LOW")
		response.Detail = response.TopUp.Detail
	case response.TopUp != nil && response.TopUp.Required && response.TopUp.Enabled && response.TopUp.Possible:
		response.OK = true
		response.Status = "validated"
		response.Detail = "challenge settlement validated; escrow top-up will fund the payout signer before execution"
	case runValidation.OK:
		response.OK = true
		response.Status = "validated"
		if response.TopUp != nil && response.TopUp.Required {
			response.Detail = "challenge settlement validated; escrow top-up will fund the payout signer before execution"
		} else {
			response.Detail = "challenge settlement validated"
		}
	default:
		response.OK = false
		response.Status = "failed"
		response.FailureCode = runValidation.FailureCode
		response.Retryable = runValidation.Retryable
		response.Detail = runValidation.Detail
	}

	return settlementChallengePlan{
		Normalized: normalized,
		Response:   finalizeSettlementChallengeResponse(response),
		RunRequest: runRequest,
	}, nil
}

func normalizeSettlementChallengeTransfer(transfer settlementChallengeTransferInput, settlementID string, index int, defaultMemo string, treasuryAddress string, addressPrefix string) (normalizedSettlementChallengeTransfer, settlementChallengeTransferResult, uint64) {
	requestID := strings.TrimSpace(transfer.RequestID)
	if requestID == "" {
		requestID = deriveSettlementChallengeTransferRequestID(settlementID, index)
	}
	participantSide := strings.TrimSpace(transfer.ParticipantSide)
	participantID := strings.TrimSpace(transfer.ParticipantID)
	bucket := strings.TrimSpace(strings.ToLower(transfer.Bucket))
	reason := strings.TrimSpace(strings.ToLower(transfer.Reason))
	toAddress := strings.TrimSpace(transfer.ToAddress)
	if toAddress == "" && reason == "treasury" {
		toAddress = treasuryAddress
	}
	memo := strings.TrimSpace(transfer.Memo)
	if memo == "" {
		memo = defaultMemo
	}
	if len(memo) > 180 {
		memo = memo[:180]
	}

	result := settlementChallengeTransferResult{
		Index:           index,
		RequestID:       requestID,
		ParticipantSide: participantSide,
		ParticipantID:   participantID,
		Bucket:          bucket,
		Reason:          reason,
		Attempted:       false,
		OK:              false,
		Status:          "failed",
		Outcome:         "invalid",
		Memo:            memo,
	}
	normalized := normalizedSettlementChallengeTransfer{
		Index:           index,
		RequestID:       requestID,
		ParticipantSide: participantSide,
		ParticipantID:   participantID,
		Bucket:          bucket,
		Reason:          reason,
		ToAddress:       toAddress,
		Memo:            memo,
	}

	validationErrors := make([]string, 0)
	if !settlementRequestIDPattern.MatchString(requestID) {
		validationErrors = append(validationErrors, "request_id must be 3-128 chars using letters, numbers, dot, underscore, colon, or dash")
	}
	if participantSide == "" && participantID == "" {
		validationErrors = append(validationErrors, "participant_side or participant_id is required on each challenge transfer")
	}
	if participantSide != "" && !settlementChallengeParticipantSidePattern.MatchString(participantSide) {
		validationErrors = append(validationErrors, "participant_side uses unsupported characters")
	}
	if participantID != "" {
		normalizedParticipantID, err := normalizeSettlementRunMetadataID("participant_id", participantID, 128, settlementSourceEventPattern)
		if err != nil {
			validationErrors = append(validationErrors, err.Error())
		} else {
			participantID = normalizedParticipantID
			normalized.ParticipantID = participantID
			result.ParticipantID = participantID
		}
	}
	switch bucket {
	case settlementChallengeBucketWager, settlementChallengeBucketGuarantee:
	default:
		validationErrors = append(validationErrors, "bucket must be wager or guarantee")
	}
	if reason == "" || !settlementChallengeReasonPattern.MatchString(reason) {
		validationErrors = append(validationErrors, "reason must be a lowercase token such as refund, return, payout, or treasury")
	}
	if toAddress == "" {
		validationErrors = append(validationErrors, "to_address is required for each challenge transfer")
	} else if !isWoloAddress(toAddress, addressPrefix) {
		validationErrors = append(validationErrors, "to_address must be a valid WOLO address")
	}
	amountUWolo, err := normalizeAmountUWolo(transfer.AmountUWolo, transfer.AmountWolo)
	if err != nil {
		validationErrors = append(validationErrors, err.Error())
	} else {
		normalized.AmountUWolo = amountUWolo
		result.AmountUWolo = amountUWolo
		result.AmountWolo = formatDisplayAmount(amountUWolo)
	}
	if len(validationErrors) > 0 {
		result.FailureCode = "INVALID_TRANSFER"
		result.Detail = strings.Join(validationErrors, "; ")
		return normalized, result, 0
	}

	amount, _ := strconv.ParseUint(amountUWolo, 10, 64)
	result.OK = true
	result.Status = "validated"
	result.Outcome = "ready"
	result.ToAddress = toAddress
	return normalized, result, amount
}

func validateVerifiedChallengeFundingParticipants(funding []verifiedSettlementChallengeFunding) []string {
	errorsOut := make([]string, 0)
	seenSides := map[string]string{}
	seenIDs := map[string]string{}
	for _, item := range funding {
		side := strings.TrimSpace(item.Result.ParticipantSide)
		id := strings.TrimSpace(item.Result.ParticipantID)
		label := challengeFundingLabel(item.Result.ParticipantSide, item.Result.ParticipantID, item.Result.FundingTxHash)
		if side != "" {
			lower := strings.ToLower(side)
			if existing, ok := seenSides[lower]; ok {
				errorsOut = append(errorsOut, fmt.Sprintf("participant_side %q appears in multiple funding deposits (%s and %s)", side, existing, label))
			} else {
				seenSides[lower] = label
			}
		}
		if id != "" {
			lower := strings.ToLower(id)
			if existing, ok := seenIDs[lower]; ok {
				errorsOut = append(errorsOut, fmt.Sprintf("participant_id %q appears in multiple funding deposits (%s and %s)", id, existing, label))
			} else {
				seenIDs[lower] = label
			}
		}
	}
	return errorsOut
}

func resolveChallengeFundingParticipant(funding []verifiedSettlementChallengeFunding, participantSide, participantID string) (verifiedSettlementChallengeFunding, string) {
	participantSide = strings.TrimSpace(participantSide)
	participantID = strings.TrimSpace(participantID)
	matches := make([]verifiedSettlementChallengeFunding, 0, len(funding))
	for _, item := range funding {
		if participantSide != "" && !strings.EqualFold(strings.TrimSpace(item.Result.ParticipantSide), participantSide) {
			continue
		}
		if participantID != "" && !strings.EqualFold(strings.TrimSpace(item.Result.ParticipantID), participantID) {
			continue
		}
		if participantSide == "" && participantID == "" {
			continue
		}
		matches = append(matches, item)
	}
	if len(matches) == 1 {
		return matches[0], ""
	}
	if len(matches) > 1 {
		return verifiedSettlementChallengeFunding{}, "participant reference is ambiguous across verified funding deposits"
	}
	return verifiedSettlementChallengeFunding{}, fmt.Sprintf("no verified funding deposit matches participant_side=%q participant_id=%q", participantSide, participantID)
}

func validateChallengeBucketAllocation(funding []verifiedSettlementChallengeFunding, allocation map[string]map[string]uint64) []string {
	errorsOut := make([]string, 0)
	for _, item := range funding {
		key := challengeFundingIdentityKey(item.Result.ParticipantSide, item.Result.ParticipantID, item.Result.FundingTxHash)
		buckets := allocation[key]
		wagerAllocated := buckets[settlementChallengeBucketWager]
		guaranteeAllocated := buckets[settlementChallengeBucketGuarantee]
		wagerFunded, _ := strconv.ParseUint(item.Result.WagerUWolo, 10, 64)
		guaranteeFunded, _ := strconv.ParseUint(item.Result.GuaranteeUWolo, 10, 64)
		label := challengeFundingLabel(item.Result.ParticipantSide, item.Result.ParticipantID, item.Result.FundingTxHash)
		if wagerAllocated != wagerFunded {
			errorsOut = append(errorsOut, fmt.Sprintf("%s wager bucket allocates %d uwolo but funding proves %d uwolo", label, wagerAllocated, wagerFunded))
		}
		if guaranteeAllocated != guaranteeFunded {
			errorsOut = append(errorsOut, fmt.Sprintf("%s guarantee bucket allocates %d uwolo but funding proves %d uwolo", label, guaranteeAllocated, guaranteeFunded))
		}
	}
	return errorsOut
}

func hasInvalidChallengeTransfers(transfers []settlementChallengeTransferResult) bool {
	for _, transfer := range transfers {
		if transfer.Outcome == "invalid" {
			return true
		}
	}
	return false
}

func (cfg settlementConfig) buildChallengeTopUpPlan(ctx context.Context, settlementID string, run settlementRunResponse) (*settlementChallengeTopUpResult, error) {
	payoutBalanceBefore, err := parseOptionalUWoloString(run.PayoutBalanceBeforeUWolo)
	if err != nil || run.PayoutBalanceBeforeUWolo == "" {
		return nil, nil
	}
	requestedTotal, err := parseOptionalUWoloString(run.RequestedTotalUWolo)
	if err != nil {
		return nil, nil
	}
	requiredPayoutBalance := requestedTotal
	if cfg.MinPayoutBalanceUWolo > requiredPayoutBalance-requestedTotal {
		requiredPayoutBalance = requestedTotal + cfg.MinPayoutBalanceUWolo
	}
	if cfg.FeeHeadroomUWolo > requiredPayoutBalance-requestedTotal {
		requiredPayoutBalance = requestedTotal + cfg.FeeHeadroomUWolo
	}
	if feeTotal, err := parseOptionalUWoloString(run.EstimatedFeeTotalUWolo); err == nil {
		requiredPayoutBalance += feeTotal
	}
	shortfall := uint64(0)
	if payoutBalanceBefore < requiredPayoutBalance {
		shortfall = requiredPayoutBalance - payoutBalanceBefore
	}

	plan := &settlementChallengeTopUpResult{
		Required:                   shortfall > 0,
		Enabled:                    cfg.EscrowAutoTopUp,
		Possible:                   shortfall == 0,
		RequestID:                  deriveSettlementChallengeTopUpRequestID(settlementID),
		SignerRole:                 "escrow",
		ToAddress:                  strings.TrimSpace(cfg.PayoutAddress),
		AmountUWolo:                strconv.FormatUint(shortfall, 10),
		AmountWolo:                 formatDisplayAmount(strconv.FormatUint(shortfall, 10)),
		PayoutBalanceBeforeUWolo:   run.PayoutBalanceBeforeUWolo,
		PayoutBalanceBeforeWolo:    run.PayoutBalanceBeforeWolo,
		RequiredPayoutBalanceUWolo: strconv.FormatUint(requiredPayoutBalance, 10),
		RequiredPayoutBalanceWolo:  formatDisplayAmount(strconv.FormatUint(requiredPayoutBalance, 10)),
	}
	if !plan.Required {
		return plan, nil
	}

	if strings.TrimSpace(cfg.PayoutAddress) == "" {
		plan.FailureCode = "PAYOUT_SIGNER_UNAVAILABLE"
		plan.Detail = "payout signer address is unavailable for challenge top-up planning"
		return plan, nil
	}
	if strings.TrimSpace(cfg.EscrowKeyName) == "" || strings.TrimSpace(cfg.EscrowAddress) == "" {
		plan.FailureCode = "ESCROW_TOP_UP_UNCONFIGURED"
		plan.Detail = "WOLO_SETTLEMENT_ESCROW_KEY_NAME and WOLO_SETTLEMENT_ESCROW_ADDRESS are required for escrow auto top-up"
		return plan, nil
	}

	escrowAddress, err := cfg.resolveEscrowAddress(ctx)
	if err != nil {
		plan.FailureCode = "ESCROW_TOP_UP_UNCONFIGURED"
		plan.Detail = err.Error()
		return plan, nil
	}
	plan.FromAddress = escrowAddress
	escrowBalance, err := cfg.fetchAccountBalanceUWolo(ctx, escrowAddress)
	if err != nil {
		plan.FailureCode = "ESCROW_BALANCE_LOOKUP_FAILED"
		plan.Detail = err.Error()
		return plan, nil
	}
	plan.EscrowBalanceUWolo = strconv.FormatUint(escrowBalance, 10)
	plan.EscrowBalanceWolo = formatDisplayAmount(plan.EscrowBalanceUWolo)
	if escrowBalance < shortfall {
		plan.FailureCode = "ESCROW_BALANCE_TOO_LOW"
		plan.Detail = fmt.Sprintf(
			"escrow balance %s uwolo (%s wolo) is below the required payout top-up %s uwolo (%s wolo)",
			plan.EscrowBalanceUWolo,
			plan.EscrowBalanceWolo,
			plan.AmountUWolo,
			plan.AmountWolo,
		)
		return plan, nil
	}

	plan.Possible = true
	if cfg.EscrowAutoTopUp {
		plan.Detail = fmt.Sprintf(
			"escrow top-up of %s uwolo (%s wolo) will raise the payout signer to %s uwolo (%s wolo) before challenge execution",
			plan.AmountUWolo,
			plan.AmountWolo,
			plan.RequiredPayoutBalanceUWolo,
			plan.RequiredPayoutBalanceWolo,
		)
	} else {
		plan.Detail = fmt.Sprintf(
			"escrow holds enough WOLO to top up the payout signer by %s uwolo (%s wolo), but WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED is off",
			plan.AmountUWolo,
			plan.AmountWolo,
		)
	}
	return plan, nil
}

func (cfg settlementConfig) executeChallengeTopUp(ctx context.Context, settlementID string, plan settlementChallengeTopUpResult) (*settlementChallengeTopUpResult, error) {
	if !plan.Required {
		return &plan, nil
	}

	memo := fmt.Sprintf("challenge top-up %s", settlementID)
	if len(memo) > 180 {
		memo = memo[:180]
	}
	response, err := cfg.executeEscrowTransfer(ctx, settlementExecuteRequest{
		RequestID:   plan.RequestID,
		ToAddress:   plan.ToAddress,
		AmountUWolo: plan.AmountUWolo,
		Memo:        memo,
	})
	if err != nil {
		return nil, err
	}

	plan.Response = &response
	plan.FailureCode = response.FailureCode
	plan.Detail = response.Detail
	plan.SignerRole = response.SignerRole
	plan.FromAddress = response.SignerAddress
	plan.ToAddress = response.ToAddress
	if response.OK && response.Status == "accepted" {
		balance, balanceErr := cfg.fetchAccountBalanceUWolo(ctx, plan.ToAddress)
		if balanceErr == nil {
			target, _ := strconv.ParseUint(plan.RequiredPayoutBalanceUWolo, 10, 64)
			if balance >= target {
				return &plan, nil
			}
		}
		plan.Response.OK = false
		plan.Response.Status = "failed"
		plan.Response.FailureCode = "ESCROW_TOP_UP_PENDING_CONFIRMATION"
		plan.Response.Retryable = true
		plan.Response.Detail = "escrow top-up broadcast was accepted but the payout balance has not reached the required level yet"
		plan.FailureCode = plan.Response.FailureCode
		plan.Detail = plan.Response.Detail
	}

	return &plan, nil
}

func (cfg settlementConfig) verifyChallengeFundingDeposit(ctx context.Context, txHash string, expectation settlementChallengeFundingExpectation) (settlementChallengeFundingVerifyResponse, error) {
	result := settlementChallengeFundingResult{
		OK:            false,
		FundingTxHash: normalizeTxHash(txHash),
		EscrowAddress: strings.TrimSpace(cfg.EscrowAddress),
	}
	response := settlementChallengeFundingVerifyResponse{
		OK:      false,
		Funding: &result,
	}

	if strings.TrimSpace(cfg.EscrowAddress) == "" {
		response.FailureCode = "ESCROW_UNCONFIGURED"
		response.Detail = "WOLO_SETTLEMENT_ESCROW_ADDRESS must be set before challenge funding verification can be used"
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}

	if err := validateChallengeFundingExpectation(expectation, cfg.AddressPrefix); err != nil {
		response.FailureCode = "INVALID_CHALLENGE"
		response.Detail = err.Error()
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}

	lookup, err := cfg.lookupSettlementTx(ctx, txHash, settlementLookupExpectations{
		Sender:      strings.TrimSpace(expectation.Sender),
		Recipient:   cfg.EscrowAddress,
		AmountUWolo: strings.TrimSpace(expectation.TotalFundedUWolo),
	})
	if err != nil {
		return settlementChallengeFundingVerifyResponse{}, err
	}
	response.Lookup = &lookup
	if !lookup.OK {
		response.FailureCode = firstNonEmpty(lookup.FailureCode, "LOOKUP_FAILED")
		response.Detail = lookup.Detail
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}
	if !lookup.Found {
		response.FailureCode = "TX_NOT_FOUND"
		response.Detail = "tx hash not found on WoloChain REST"
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}
	if lookup.Kind != "escrow_deposit" {
		response.FailureCode = "NOT_ESCROW_DEPOSIT"
		response.Detail = "tx did not deliver a WOLO transfer into the configured escrow address"
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}
	if lookup.MatchedTransfer == nil {
		response.FailureCode = "CHALLENGE_FUNDING_MISMATCH"
		response.Detail = "tx reached escrow but no matching WOLO transfer was found for the expected challenge funding amount"
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		response.Funding.DepositFound = true
		return response, nil
	}

	parsedFunding, err := parseChallengeFundingResult(*lookup.MatchedTransfer, lookup, cfg.EscrowAddress)
	if err != nil {
		response.FailureCode = "INVALID_CHALLENGE_FUNDING_MEMO"
		response.Detail = err.Error()
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		response.Funding.DepositFound = true
		response.Funding.CanonicalTxLookup = lookup.CanonicalTxLookup
		response.Funding.CanonicalTxLookupPreferred = lookup.CanonicalTxLookupPreferred
		response.Funding.CanonicalTxLookupInternal = lookup.CanonicalTxLookupInternal
		response.Funding.CanonicalTxLookupPublic = lookup.CanonicalTxLookupPublic
		return response, nil
	}

	response.Funding = &parsedFunding
	if mismatch := compareChallengeFundingExpectation(parsedFunding, expectation); mismatch != "" {
		response.FailureCode = "CHALLENGE_FUNDING_MISMATCH"
		response.Detail = mismatch
		response.Funding.OK = false
		response.Funding.FailureCode = response.FailureCode
		response.Funding.Detail = response.Detail
		return response, nil
	}

	response.OK = true
	response.Detail = "challenge funding deposit verified"
	response.Funding.OK = true
	response.Funding.Detail = response.Detail
	return response, nil
}

func validateChallengeFundingExpectation(expectation settlementChallengeFundingExpectation, addressPrefix string) error {
	if sender := strings.TrimSpace(expectation.Sender); sender != "" && !isWoloAddress(sender, addressPrefix) {
		return errors.New("expected_sender must be a valid WOLO address")
	}
	if sourceApp := strings.TrimSpace(expectation.SourceApp); sourceApp != "" {
		if _, err := normalizeSettlementRunMetadataID("source_app", sourceApp, 64, settlementRequestIDPattern); err != nil {
			return err
		}
	}
	if challengeID := strings.TrimSpace(expectation.ChallengeID); challengeID != "" {
		if _, err := normalizeSettlementRunMetadataID("challenge_id", challengeID, 128, settlementSourceEventPattern); err != nil {
			return err
		}
	}
	if sourceEventID := strings.TrimSpace(expectation.SourceEventID); sourceEventID != "" {
		if _, err := normalizeSettlementRunMetadataID("source_event_id", sourceEventID, 128, settlementSourceEventPattern); err != nil {
			return err
		}
	}
	if participantSide := strings.TrimSpace(expectation.ParticipantSide); participantSide != "" && !settlementChallengeParticipantSidePattern.MatchString(participantSide) {
		return errors.New("participant_side uses unsupported characters")
	}
	if participantID := strings.TrimSpace(expectation.ParticipantID); participantID != "" {
		if _, err := normalizeSettlementRunMetadataID("participant_id", participantID, 128, settlementSourceEventPattern); err != nil {
			return err
		}
	}
	for field, value := range map[string]string{
		"expected_amount_uwolo": strings.TrimSpace(expectation.TotalFundedUWolo),
		"wager_uwolo":           strings.TrimSpace(expectation.WagerUWolo),
		"guarantee_uwolo":       strings.TrimSpace(expectation.GuaranteeUWolo),
	} {
		if value == "" {
			continue
		}
		if _, err := strconv.ParseUint(value, 10, 64); err != nil {
			return fmt.Errorf("%s must be a positive integer", field)
		}
	}
	return nil
}

func parseChallengeFundingResult(transfer settlementTransfer, lookup settlementLookupResponse, escrowAddress string) (settlementChallengeFundingResult, error) {
	memo := strings.TrimSpace(lookup.Memo)
	if !strings.HasPrefix(memo, settlementChallengeFundingMemoPrefix) {
		return settlementChallengeFundingResult{}, errors.New("memo does not use the wolo.challenge.funding.v1 convention")
	}

	values, err := url.ParseQuery(strings.TrimPrefix(memo, settlementChallengeFundingMemoPrefix))
	if err != nil {
		return settlementChallengeFundingResult{}, fmt.Errorf("memo query string is invalid: %w", err)
	}

	getValue := func(keys ...string) string {
		for _, key := range keys {
			if value := strings.TrimSpace(values.Get(key)); value != "" {
				return value
			}
		}
		return ""
	}

	sourceApp := getValue("source_app", "app")
	if sourceApp == "" {
		return settlementChallengeFundingResult{}, errors.New("memo is missing source_app")
	}
	if normalizedSourceApp, err := normalizeSettlementRunMetadataID("source_app", sourceApp, 64, settlementRequestIDPattern); err != nil {
		return settlementChallengeFundingResult{}, err
	} else {
		sourceApp = normalizedSourceApp
	}

	challengeID := getValue("challenge_id", "cid")
	if challengeID != "" {
		if normalizedChallengeID, err := normalizeSettlementRunMetadataID("challenge_id", challengeID, 128, settlementSourceEventPattern); err != nil {
			return settlementChallengeFundingResult{}, err
		} else {
			challengeID = normalizedChallengeID
		}
	}
	sourceEventID := getValue("source_event_id", "event_id", "eid")
	if sourceEventID != "" {
		if normalizedSourceEventID, err := normalizeSettlementRunMetadataID("source_event_id", sourceEventID, 128, settlementSourceEventPattern); err != nil {
			return settlementChallengeFundingResult{}, err
		} else {
			sourceEventID = normalizedSourceEventID
		}
	}
	if challengeID == "" && sourceEventID == "" {
		return settlementChallengeFundingResult{}, errors.New("memo is missing challenge_id or source_event_id")
	}

	participantSide := getValue("participant_side", "side")
	if participantSide != "" && !settlementChallengeParticipantSidePattern.MatchString(participantSide) {
		return settlementChallengeFundingResult{}, errors.New("memo participant_side uses unsupported characters")
	}
	participantID := getValue("participant_id", "pid")
	if participantID != "" {
		if normalizedParticipantID, err := normalizeSettlementRunMetadataID("participant_id", participantID, 128, settlementSourceEventPattern); err != nil {
			return settlementChallengeFundingResult{}, err
		} else {
			participantID = normalizedParticipantID
		}
	}
	if participantSide == "" && participantID == "" {
		return settlementChallengeFundingResult{}, errors.New("memo is missing participant_side or participant_id")
	}

	wagerUWolo, err := parseChallengeMemoAmount("wager_uwolo", getValue("wager_uwolo", "w"))
	if err != nil {
		return settlementChallengeFundingResult{}, err
	}
	guaranteeUWolo, err := parseChallengeMemoAmount("guarantee_uwolo", getValue("guarantee_uwolo", "g"))
	if err != nil {
		return settlementChallengeFundingResult{}, err
	}
	totalFundedUWolo := strings.TrimSpace(transfer.Amount)
	totalFunded, err := strconv.ParseUint(totalFundedUWolo, 10, 64)
	if err != nil || totalFunded == 0 {
		return settlementChallengeFundingResult{}, errors.New("escrow transfer amount is not a positive uwolo integer")
	}
	if declaredTotal := strings.TrimSpace(getValue("total_funded_uwolo", "total_uwolo", "total", "t")); declaredTotal != "" && declaredTotal != totalFundedUWolo {
		return settlementChallengeFundingResult{}, fmt.Errorf("memo total_funded_uwolo=%s does not match the escrow transfer amount %s", declaredTotal, totalFundedUWolo)
	}
	if wagerUWolo+guaranteeUWolo != totalFunded {
		return settlementChallengeFundingResult{}, fmt.Errorf(
			"memo bucket totals %d do not match the escrow transfer amount %d",
			wagerUWolo+guaranteeUWolo,
			totalFunded,
		)
	}

	return settlementChallengeFundingResult{
		OK:                         true,
		DepositFound:               true,
		FundingTxHash:              lookup.TxHash,
		SourceApp:                  sourceApp,
		ChallengeID:                challengeID,
		SourceEventID:              sourceEventID,
		ParticipantSide:            participantSide,
		ParticipantID:              participantID,
		Sender:                     transfer.Sender,
		EscrowAddress:              escrowAddress,
		TotalFundedUWolo:           totalFundedUWolo,
		TotalFundedWolo:            formatDisplayAmount(totalFundedUWolo),
		WagerUWolo:                 strconv.FormatUint(wagerUWolo, 10),
		WagerWolo:                  formatDisplayAmount(strconv.FormatUint(wagerUWolo, 10)),
		GuaranteeUWolo:             strconv.FormatUint(guaranteeUWolo, 10),
		GuaranteeWolo:              formatDisplayAmount(strconv.FormatUint(guaranteeUWolo, 10)),
		Memo:                       memo,
		CanonicalTxLookup:          lookup.CanonicalTxLookup,
		CanonicalTxLookupPreferred: lookup.CanonicalTxLookupPreferred,
		CanonicalTxLookupInternal:  lookup.CanonicalTxLookupInternal,
		CanonicalTxLookupPublic:    lookup.CanonicalTxLookupPublic,
	}, nil
}

func parseChallengeMemoAmount(fieldName, raw string) (uint64, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 0, fmt.Errorf("memo is missing %s", fieldName)
	}
	value, err := strconv.ParseUint(raw, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be a positive integer", fieldName)
	}
	return value, nil
}

func compareChallengeFundingExpectation(funding settlementChallengeFundingResult, expectation settlementChallengeFundingExpectation) string {
	checks := []struct {
		name     string
		expected string
		actual   string
	}{
		{"source_app", expectation.SourceApp, funding.SourceApp},
		{"challenge_id", expectation.ChallengeID, funding.ChallengeID},
		{"source_event_id", expectation.SourceEventID, funding.SourceEventID},
		{"participant_side", expectation.ParticipantSide, funding.ParticipantSide},
		{"participant_id", expectation.ParticipantID, funding.ParticipantID},
		{"expected_sender", expectation.Sender, funding.Sender},
		{"expected_amount_uwolo", expectation.TotalFundedUWolo, funding.TotalFundedUWolo},
		{"wager_uwolo", expectation.WagerUWolo, funding.WagerUWolo},
		{"guarantee_uwolo", expectation.GuaranteeUWolo, funding.GuaranteeUWolo},
	}
	for _, check := range checks {
		expected := strings.TrimSpace(check.expected)
		if expected == "" {
			continue
		}
		if !strings.EqualFold(expected, strings.TrimSpace(check.actual)) {
			return fmt.Sprintf("%s=%q does not match the verified challenge funding value %q", check.name, expected, check.actual)
		}
	}
	return ""
}

func (cfg settlementConfig) listRecentChallengeFundingDeposits(ctx context.Context, filters settlementChallengeFundingRecentFilters) (settlementChallengeFundingRecentResponse, error) {
	response := settlementChallengeFundingRecentResponse{
		OK:              false,
		Limit:           filters.Limit,
		SenderFilter:    strings.TrimSpace(filters.Sender),
		SourceApp:       strings.TrimSpace(filters.SourceApp),
		ChallengeID:     strings.TrimSpace(filters.ChallengeID),
		SourceEventID:   strings.TrimSpace(filters.SourceEventID),
		ParticipantSide: strings.TrimSpace(filters.ParticipantSide),
		ParticipantID:   strings.TrimSpace(filters.ParticipantID),
	}
	if response.Limit <= 0 {
		response.FailureCode = "INVALID_LIMIT"
		response.Detail = "limit must be greater than zero"
		return response, nil
	}
	if err := validateChallengeFundingExpectation(settlementChallengeFundingExpectation{
		Sender:          response.SenderFilter,
		SourceApp:       response.SourceApp,
		ChallengeID:     response.ChallengeID,
		SourceEventID:   response.SourceEventID,
		ParticipantSide: response.ParticipantSide,
		ParticipantID:   response.ParticipantID,
	}, cfg.AddressPrefix); err != nil {
		response.FailureCode = "INVALID_CHALLENGE"
		response.Detail = err.Error()
		return response, nil
	}

	searchLimit := response.Limit * 5
	if searchLimit < response.Limit {
		searchLimit = response.Limit
	}
	if searchLimit > 100 {
		searchLimit = 100
	}
	escrowRecent, err := cfg.listRecentEscrowDeposits(ctx, searchLimit, response.SenderFilter)
	if err != nil {
		return settlementChallengeFundingRecentResponse{}, err
	}
	if !escrowRecent.OK {
		response.FailureCode = escrowRecent.FailureCode
		response.Detail = escrowRecent.Detail
		return response, nil
	}

	items := make([]settlementChallengeFundingResult, 0, response.Limit)
	for _, deposit := range escrowRecent.Deposits {
		lookup := settlementLookupResponse{
			OK:                         deposit.TxSuccess,
			Found:                      true,
			ChainID:                    cfg.ChainID,
			TxHash:                     deposit.TxHash,
			TxSuccess:                  deposit.TxSuccess,
			Kind:                       "escrow_deposit",
			Height:                     deposit.Height,
			Memo:                       deposit.Memo,
			Timestamp:                  deposit.Timestamp,
			CanonicalTxLookup:          deposit.CanonicalTxLookup,
			CanonicalTxLookupPreferred: deposit.CanonicalTxLookupPreferred,
			CanonicalTxLookupInternal:  deposit.CanonicalTxLookupInternal,
			CanonicalTxLookupPublic:    deposit.CanonicalTxLookupPublic,
			MatchedTransfer: &settlementTransfer{
				Sender:    deposit.Sender,
				Recipient: deposit.Recipient,
				Amount:    deposit.AmountUWolo,
				Denom:     cfg.BaseDenom,
			},
		}
		funding, err := parseChallengeFundingResult(*lookup.MatchedTransfer, lookup, cfg.EscrowAddress)
		if err != nil {
			continue
		}
		if mismatch := compareChallengeFundingExpectation(funding, settlementChallengeFundingExpectation{
			Sender:          response.SenderFilter,
			SourceApp:       response.SourceApp,
			ChallengeID:     response.ChallengeID,
			SourceEventID:   response.SourceEventID,
			ParticipantSide: response.ParticipantSide,
			ParticipantID:   response.ParticipantID,
		}); mismatch != "" {
			continue
		}
		funding.Index = len(items)
		items = append(items, funding)
		if len(items) >= response.Limit {
			break
		}
	}

	response.OK = true
	response.Count = len(items)
	response.Funding = items
	return response, nil
}

func (cfg settlementConfig) resolveEscrowAddress(ctx context.Context) (string, error) {
	if cfg.EscrowKeyName == "" {
		return "", errors.New("WOLO_SETTLEMENT_ESCROW_KEY_NAME is not set")
	}

	args := []string{
		"keys", "show", cfg.EscrowKeyName,
		"--address",
		"--home", cfg.HomeDir,
		"--keyring-backend", cfg.KeyringBackend,
	}
	if cfg.KeyringDir != "" {
		args = append(args, "--keyring-dir", cfg.KeyringDir)
	}

	cmd := exec.CommandContext(ctx, cfg.ExecutablePath, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	output, err := cmd.Output()
	if err != nil {
		detail := strings.TrimSpace(stderr.String())
		if detail == "" {
			detail = strings.TrimSpace(string(output))
		}
		return "", fmt.Errorf("could not resolve escrow signer %q: %s", cfg.EscrowKeyName, detail)
	}

	address := strings.TrimSpace(string(output))
	if !isWoloAddress(address, cfg.AddressPrefix) {
		return "", fmt.Errorf("resolved escrow signer %q to non-wolo address %q", cfg.EscrowKeyName, address)
	}
	if cfg.EscrowAddress != "" && !strings.EqualFold(address, cfg.EscrowAddress) {
		return "", fmt.Errorf("escrow signer resolved to %s, expected %s", address, cfg.EscrowAddress)
	}
	return address, nil
}

func (cfg settlementConfig) executeEscrowTransfer(ctx context.Context, request settlementExecuteRequest) (settlementExecuteResponse, error) {
	normalized, err := normalizeSettlementRequest(request)
	if err != nil {
		return settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: "INVALID_REQUEST",
			Detail:      err.Error(),
			RequestID:   strings.TrimSpace(request.RequestID),
			ChainID:     cfg.ChainID,
			SignerRole:  "escrow",
		}, nil
	}

	recordPath := cfg.requestRecordPath(normalized.RequestID)
	return cfg.withRequestLock(normalized.RequestID, func() (settlementExecuteResponse, error) {
		stored, readErr := readSettlementStoredResult(recordPath)
		if readErr == nil {
			if !sameSettlementRequest(stored.Request, normalized) {
				return settlementExecuteResponse{
					OK:            false,
					Status:        "failed",
					FailureCode:   "IDEMPOTENCY_CONFLICT",
					Retryable:     false,
					RequestID:     normalized.RequestID,
					ChainID:       cfg.ChainID,
					SignerRole:    "escrow",
					SignerAddress: stored.Response.SignerAddress,
					ToAddress:     normalized.ToAddress,
					AmountUWolo:   normalized.AmountUWolo,
					AmountWolo:    formatDisplayAmount(normalized.AmountUWolo),
					Detail:        "request id already exists with different settlement payload",
				}, nil
			}

			if stored.Response.OK || stored.Response.TxHash != "" || !stored.Response.Retryable {
				replayed := stored.Response
				replayed.IdempotentReplay = true
				return replayed, nil
			}
		} else if !errors.Is(readErr, os.ErrNotExist) {
			return settlementExecuteResponse{
				OK:          false,
				Status:      "failed",
				FailureCode: "STATE_FILE_INVALID",
				Retryable:   false,
				RequestID:   normalized.RequestID,
				ChainID:     cfg.ChainID,
				SignerRole:  "escrow",
				ToAddress:   normalized.ToAddress,
				AmountUWolo: normalized.AmountUWolo,
				AmountWolo:  formatDisplayAmount(normalized.AmountUWolo),
				Detail:      fmt.Sprintf("could not read settlement state file: %v", readErr),
			}, nil
		}

		signerAddress, failure := cfg.preflightEscrowTransfer(ctx, normalized.AmountUWolo)
		if failure != nil {
			failure.RequestID = normalized.RequestID
			failure.ToAddress = normalized.ToAddress
			failure.AmountUWolo = normalized.AmountUWolo
			failure.AmountWolo = formatDisplayAmount(normalized.AmountUWolo)
			signerForRecord := signerAddress
			if signerForRecord == "" {
				signerForRecord = failure.SignerAddress
			}
			if err := cfg.writeSettlementRecord(recordPath, normalized, signerForRecord, *failure); err != nil {
				return settlementExecuteResponse{}, err
			}
			return *failure, nil
		}

		result := cfg.broadcastEscrowTransfer(ctx, normalized, signerAddress)
		if err := cfg.writeSettlementRecord(recordPath, normalized, signerAddress, result); err != nil {
			return settlementExecuteResponse{}, err
		}
		return result, nil
	})
}

func (cfg settlementConfig) preflightEscrowTransfer(ctx context.Context, requestAmountUWolo string) (string, *settlementExecuteResponse) {
	health := cfg.buildHealthReport(ctx)
	if !health.OK {
		return "", &settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: health.FailureCode,
			Retryable:   health.FailureCode == "RPC_UNREACHABLE",
			ChainID:     cfg.ChainID,
			SignerRole:  "escrow",
			Detail:      health.Detail,
		}
	}
	if cfg.EscrowKeyName == "" {
		return "", &settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: "ESCROW_SIGNER_UNCONFIGURED",
			Retryable:   false,
			ChainID:     cfg.ChainID,
			SignerRole:  "escrow",
			Detail:      "WOLO_SETTLEMENT_ESCROW_KEY_NAME is required for escrow transfers",
		}
	}

	signerAddress, err := cfg.resolveEscrowAddress(ctx)
	if err != nil {
		failureCode := "ESCROW_SIGNER_UNAVAILABLE"
		if strings.Contains(strings.ToLower(err.Error()), "expected") {
			failureCode = "ESCROW_ADDRESS_MISMATCH"
		}
		return "", &settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: failureCode,
			Retryable:   false,
			ChainID:     cfg.ChainID,
			SignerRole:  "escrow",
			Detail:      err.Error(),
		}
	}
	requestAmount, err := strconv.ParseUint(strings.TrimSpace(requestAmountUWolo), 10, 64)
	if err != nil {
		return signerAddress, &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   "INVALID_REQUEST",
			Retryable:     false,
			ChainID:       cfg.ChainID,
			SignerRole:    "escrow",
			SignerAddress: signerAddress,
			Detail:        "amount_uwolo must be a positive integer",
		}
	}
	balanceAmount, err := cfg.fetchAccountBalanceUWolo(ctx, signerAddress)
	if err != nil {
		return signerAddress, &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   "ESCROW_BALANCE_LOOKUP_FAILED",
			Retryable:     true,
			ChainID:       cfg.ChainID,
			SignerRole:    "escrow",
			SignerAddress: signerAddress,
			Detail:        err.Error(),
		}
	}
	if balanceAmount < requestAmount {
		return signerAddress, &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   "ESCROW_BALANCE_TOO_LOW",
			Retryable:     true,
			ChainID:       cfg.ChainID,
			SignerRole:    "escrow",
			SignerAddress: signerAddress,
			Detail: fmt.Sprintf(
				"escrow signer balance %s uwolo (%s wolo) is below requested transfer %s uwolo (%s wolo)",
				strconv.FormatUint(balanceAmount, 10),
				formatDisplayAmount(strconv.FormatUint(balanceAmount, 10)),
				strconv.FormatUint(requestAmount, 10),
				formatDisplayAmount(strconv.FormatUint(requestAmount, 10)),
			),
		}
	}

	return signerAddress, nil
}

func (cfg settlementConfig) broadcastEscrowTransfer(ctx context.Context, request normalizedSettlementRequest, signerAddress string) settlementExecuteResponse {
	ctx, cancel := context.WithTimeout(ctx, cfg.RequestTimeout)
	defer cancel()

	amountArg := request.AmountUWolo + cfg.BaseDenom
	args := []string{
		"tx", "bank", "send",
		cfg.EscrowKeyName,
		request.ToAddress,
		amountArg,
		"--yes",
		"--output", "json",
		"--broadcast-mode", cfg.BroadcastMode,
		"--chain-id", cfg.ChainID,
		"--home", cfg.HomeDir,
		"--keyring-backend", cfg.KeyringBackend,
		"--node", cfg.NodeAddr,
		"--gas", cfg.Gas,
	}
	if cfg.KeyringDir != "" {
		args = append(args, "--keyring-dir", cfg.KeyringDir)
	}
	if cfg.GasAdjustment != "" {
		args = append(args, "--gas-adjustment", cfg.GasAdjustment)
	}
	if cfg.Fees != "" {
		args = append(args, "--fees", cfg.Fees)
	} else if cfg.GasPrices != "" {
		args = append(args, "--gas-prices", cfg.GasPrices)
	}
	if request.Memo != "" {
		args = append(args, "--note", request.Memo)
	}

	cmd := exec.CommandContext(ctx, cfg.ExecutablePath, args...)
	output, err := cmd.CombinedOutput()

	response := settlementExecuteResponse{
		OK:                         false,
		Status:                     "failed",
		RequestID:                  request.RequestID,
		ChainID:                    cfg.ChainID,
		SignerRole:                 "escrow",
		SignerAddress:              signerAddress,
		ToAddress:                  request.ToAddress,
		AmountUWolo:                request.AmountUWolo,
		AmountWolo:                 formatDisplayAmount(request.AmountUWolo),
		BroadcastMode:              cfg.BroadcastMode,
		CanonicalTxLookup:          cfg.txLookupURL(""),
		CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(""),
		CanonicalTxLookupInternal:  cfg.txLookupURL(""),
		CanonicalTxLookupPublic:    cfg.publicTxLookupURL(""),
	}

	var broadcast bankSendBroadcastResponse
	if jsonPayload := extractJSONPayload(output); len(jsonPayload) > 0 {
		if jsonErr := json.Unmarshal(jsonPayload, &broadcast); jsonErr == nil && broadcast.TxHash != "" {
			response.TxHash = broadcast.TxHash
			response.Code = broadcast.Code
			response.Codespace = broadcast.Codespace
			response.RawLog = broadcast.RawLog
			response.CanonicalTxLookup = cfg.txLookupURL(broadcast.TxHash)
			response.CanonicalTxLookupPreferred = cfg.preferredTxLookupURL(broadcast.TxHash)
			response.CanonicalTxLookupInternal = cfg.txLookupURL(broadcast.TxHash)
			response.CanonicalTxLookupPublic = cfg.publicTxLookupURL(broadcast.TxHash)
			if broadcast.Code == 0 {
				confirmed, confirmErr := cfg.waitForTxConfirmation(ctx, broadcast.TxHash)
				if confirmErr == nil && confirmed != nil {
					response.Code = confirmed.Code
					response.Codespace = confirmed.Codespace
					response.RawLog = confirmed.RawLog
					if confirmed.TxSuccess {
						response.OK = true
						response.Status = "confirmed"
						response.Detail = "escrow transfer confirmed on WoloChain"
						return response
					}

					response.FailureCode = classifyRejectedTx(confirmed.RawLog, confirmed.Code)
					response.Detail = fmt.Sprintf("tx failed with code %d", confirmed.Code)
					response.Retryable = false
					return response
				}

				response.OK = true
				response.Status = "accepted"
				if confirmErr != nil {
					response.Detail = "escrow transfer broadcast accepted; final confirmation check failed"
				} else {
					response.Detail = "escrow transfer broadcast accepted; final confirmation pending"
				}
				return response
			}

			response.FailureCode = classifyRejectedTx(broadcast.RawLog, broadcast.Code)
			response.Detail = fmt.Sprintf("tx rejected with code %d", broadcast.Code)
			response.Retryable = false
			return response
		}
	}

	failureCode, retryable := classifySettlementExecError(string(output))
	response.FailureCode = failureCode
	response.Retryable = retryable
	response.Detail = strings.TrimSpace(string(output))
	if response.Detail == "" && err != nil {
		response.Detail = err.Error()
	}
	return response
}

func mergeChallengeRunResults(transfers []normalizedSettlementChallengeTransfer, run settlementRunResponse) []settlementChallengeTransferResult {
	resultsByRequestID := map[string]settlementRunPayoutResult{}
	for _, payout := range run.Payouts {
		resultsByRequestID[payout.RequestID] = payout
	}

	out := make([]settlementChallengeTransferResult, 0, len(transfers))
	for _, transfer := range transfers {
		result := settlementChallengeTransferResult{
			Index:           transfer.Index,
			RequestID:       transfer.RequestID,
			ParticipantSide: transfer.ParticipantSide,
			ParticipantID:   transfer.ParticipantID,
			Bucket:          transfer.Bucket,
			Reason:          transfer.Reason,
			Attempted:       false,
			OK:              false,
			Status:          "failed",
			Outcome:         "invalid",
			ToAddress:       transfer.ToAddress,
			AmountUWolo:     transfer.AmountUWolo,
			AmountWolo:      formatDisplayAmount(transfer.AmountUWolo),
			Memo:            transfer.Memo,
		}
		if payout, ok := resultsByRequestID[transfer.RequestID]; ok {
			result.Attempted = payout.Attempted
			result.OK = payout.OK
			result.Status = payout.Status
			result.Outcome = payout.Outcome
			result.FailureCode = payout.FailureCode
			result.Retryable = payout.Retryable
			result.IdempotentReplay = payout.IdempotentReplay
			result.SignerRole = payout.SignerRole
			result.SignerAddress = payout.SignerAddress
			result.TxHash = payout.TxHash
			result.Detail = payout.Detail
			result.CanonicalTxLookup = payout.CanonicalTxLookup
			result.CanonicalTxLookupPreferred = payout.CanonicalTxLookupPreferred
			result.CanonicalTxLookupInternal = payout.CanonicalTxLookupInternal
			result.CanonicalTxLookupPublic = payout.CanonicalTxLookupPublic
			result.Warnings = payout.Warnings
		}
		out = append(out, result)
	}
	return out
}

func finalizeSettlementChallengeResponse(response settlementChallengeResponse) settlementChallengeResponse {
	var (
		requestedTotal uint64
		executedTotal  uint64
		confirmedTotal uint64
		acceptedTotal  uint64
		refusedTotal   uint64
		rejectedTotal  uint64
	)

	bucketTotals := map[string]*settlementChallengeBucketTotals{}
	getBucketTotals := func(bucket string) *settlementChallengeBucketTotals {
		if bucketTotals[bucket] == nil {
			bucketTotals[bucket] = &settlementChallengeBucketTotals{Bucket: bucket}
		}
		return bucketTotals[bucket]
	}

	if response.RequestedTransferCount == 0 {
		response.RequestedTransferCount = len(response.Transfers)
	}
	for _, transfer := range response.Transfers {
		amount, err := parseOptionalUWoloString(transfer.AmountUWolo)
		if err != nil {
			continue
		}
		requestedTotal += amount
		bucket := getBucketTotals(transfer.Bucket)
		bucketRequested, _ := parseOptionalUWoloString(bucket.RequestedUWolo)
		bucket.RequestedUWolo = strconv.FormatUint(bucketRequested+amount, 10)
		bucket.RequestedWolo = formatDisplayAmount(bucket.RequestedUWolo)
		switch transfer.Status {
		case "confirmed":
			response.ConfirmedTransferCount++
			response.ExecutedTransferCount++
			executedTotal += amount
			confirmedTotal += amount
			bucketExecuted, _ := parseOptionalUWoloString(bucket.ExecutedUWolo)
			bucketConfirmed, _ := parseOptionalUWoloString(bucket.ConfirmedUWolo)
			bucket.ExecutedUWolo = strconv.FormatUint(bucketExecuted+amount, 10)
			bucket.ExecutedWolo = formatDisplayAmount(bucket.ExecutedUWolo)
			bucket.ConfirmedUWolo = strconv.FormatUint(bucketConfirmed+amount, 10)
			bucket.ConfirmedWolo = formatDisplayAmount(bucket.ConfirmedUWolo)
		case "accepted":
			response.AcceptedTransferCount++
			response.ExecutedTransferCount++
			executedTotal += amount
			acceptedTotal += amount
			bucketExecuted, _ := parseOptionalUWoloString(bucket.ExecutedUWolo)
			bucketAccepted, _ := parseOptionalUWoloString(bucket.AcceptedUWolo)
			bucket.ExecutedUWolo = strconv.FormatUint(bucketExecuted+amount, 10)
			bucket.ExecutedWolo = formatDisplayAmount(bucket.ExecutedUWolo)
			bucket.AcceptedUWolo = strconv.FormatUint(bucketAccepted+amount, 10)
			bucket.AcceptedWolo = formatDisplayAmount(bucket.AcceptedUWolo)
		}
		switch transfer.Outcome {
		case "refused", "invalid":
			response.RefusedTransferCount++
			refusedTotal += amount
			bucketRefused, _ := parseOptionalUWoloString(bucket.RefusedUWolo)
			bucket.RefusedUWolo = strconv.FormatUint(bucketRefused+amount, 10)
			bucket.RefusedWolo = formatDisplayAmount(bucket.RefusedUWolo)
		case "rejected":
			response.RejectedTransferCount++
			rejectedTotal += amount
			bucketRejected, _ := parseOptionalUWoloString(bucket.RejectedUWolo)
			bucket.RejectedUWolo = strconv.FormatUint(bucketRejected+amount, 10)
			bucket.RejectedWolo = formatDisplayAmount(bucket.RejectedUWolo)
		}
		if transfer.IdempotentReplay {
			response.ReplayTransferCount++
		}
		if transfer.Retryable {
			response.Retryable = true
		}
	}

	response.RequestedTotalUWolo = firstNonEmpty(response.RequestedTotalUWolo, formatOptionalRunAmount(requestedTotal))
	response.RequestedTotalWolo = firstNonEmpty(response.RequestedTotalWolo, formatOptionalRunDisplayAmount(requestedTotal))
	response.ExecutedTotalUWolo = formatOptionalRunAmount(executedTotal)
	response.ExecutedTotalWolo = formatOptionalRunDisplayAmount(executedTotal)
	response.ConfirmedTotalUWolo = formatOptionalRunAmount(confirmedTotal)
	response.ConfirmedTotalWolo = formatOptionalRunDisplayAmount(confirmedTotal)
	response.AcceptedTotalUWolo = formatOptionalRunAmount(acceptedTotal)
	response.AcceptedTotalWolo = formatOptionalRunDisplayAmount(acceptedTotal)
	response.RefusedTotalUWolo = formatOptionalRunAmount(refusedTotal)
	response.RefusedTotalWolo = formatOptionalRunDisplayAmount(refusedTotal)
	response.RejectedTotalUWolo = formatOptionalRunAmount(rejectedTotal)
	response.RejectedTotalWolo = formatOptionalRunDisplayAmount(rejectedTotal)

	response.BucketTotals = make([]settlementChallengeBucketTotals, 0, len(bucketTotals))
	for _, bucket := range []string{settlementChallengeBucketWager, settlementChallengeBucketGuarantee} {
		if totals := bucketTotals[bucket]; totals != nil {
			response.BucketTotals = append(response.BucketTotals, *totals)
		}
	}

	if response.Status == "" {
		response.Status, response.OK, response.FailureCode = deriveSettlementChallengeStatus(response)
	}
	if response.Run != nil {
		response.Retryable = response.Retryable || response.Run.Retryable
	}
	return response
}

func deriveSettlementChallengeStatus(response settlementChallengeResponse) (string, bool, string) {
	if response.FailureCode == "INVALID_CHALLENGE" {
		return "failed", false, response.FailureCode
	}
	if response.ConfirmedTransferCount == response.RequestedTransferCount && response.RequestedTransferCount > 0 {
		return "confirmed", true, ""
	}
	if response.ExecutedTransferCount == response.RequestedTransferCount && response.RequestedTransferCount > 0 {
		return "accepted", true, ""
	}
	if response.ExecutedTransferCount > 0 && (response.RefusedTransferCount > 0 || response.RejectedTransferCount > 0) {
		return "partial", false, firstNonEmpty(response.FailureCode, firstChallengeTransferFailureCode(response.Transfers), "CHALLENGE_PARTIAL_FAILURE")
	}
	if response.ExecutedTransferCount == 0 && (response.RefusedTransferCount > 0 || response.RejectedTransferCount > 0) {
		return "failed", false, firstNonEmpty(response.FailureCode, firstChallengeTransferFailureCode(response.Transfers), "CHALLENGE_FAILED")
	}
	return strings.TrimSpace(response.Status), response.OK, response.FailureCode
}

func firstChallengeTransferFailureCode(transfers []settlementChallengeTransferResult) string {
	for _, transfer := range transfers {
		if strings.TrimSpace(transfer.FailureCode) != "" {
			return transfer.FailureCode
		}
	}
	return ""
}

func settlementChallengeExecutionDetail(response settlementChallengeResponse) string {
	switch strings.TrimSpace(response.Status) {
	case "confirmed":
		return fmt.Sprintf("all %d challenge transfers confirmed on WoloChain", response.ConfirmedTransferCount)
	case "accepted":
		return fmt.Sprintf("all %d challenge transfers were broadcast accepted; final confirmation is still pending for at least one transfer", response.ExecutedTransferCount)
	case "partial":
		return fmt.Sprintf("%d of %d challenge transfers executed; inspect per-bucket results for the remaining failures", response.ExecutedTransferCount, response.RequestedTransferCount)
	case "failed":
		if detail := firstChallengeTransferFailureDetail(response.Transfers); detail != "" {
			return detail
		}
		return strings.TrimSpace(response.Detail)
	default:
		return strings.TrimSpace(response.Detail)
	}
}

func firstChallengeTransferFailureDetail(transfers []settlementChallengeTransferResult) string {
	for _, transfer := range transfers {
		if strings.TrimSpace(transfer.Detail) != "" && strings.TrimSpace(transfer.FailureCode) != "" {
			return transfer.Detail
		}
	}
	return ""
}

func markChallengeReadyTransfersFailed(transfers []settlementChallengeTransferResult, failureCode, detail string, retryable bool) []settlementChallengeTransferResult {
	out := make([]settlementChallengeTransferResult, len(transfers))
	copy(out, transfers)
	for index, transfer := range out {
		if transfer.Outcome != "ready" {
			continue
		}
		transfer.OK = false
		transfer.Status = "failed"
		transfer.Outcome = "refused"
		transfer.FailureCode = failureCode
		transfer.Retryable = retryable
		transfer.Detail = detail
		out[index] = transfer
	}
	return out
}

func settlementChallengeResponseIsFinal(response settlementChallengeResponse) bool {
	if response.Retryable {
		return false
	}
	return response.OK || strings.EqualFold(strings.TrimSpace(response.Status), "failed") || strings.EqualFold(strings.TrimSpace(response.Status), "partial")
}

func hashSettlementChallengeRequest(request normalizedSettlementChallengeRequest) string {
	data, _ := json.Marshal(request)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func (cfg settlementConfig) challengeRecordPath(settlementID string) string {
	return filepath.Join(cfg.StateDir, "challenge-settlements", settlementID+".json")
}

func (cfg settlementConfig) challengeLockPath(settlementID string) string {
	return filepath.Join(cfg.StateDir, "challenge-locks", settlementID+".lock")
}

func (cfg settlementConfig) withChallengeLock(settlementID string, fn func() (settlementChallengeResponse, error)) (settlementChallengeResponse, error) {
	lockPath := cfg.challengeLockPath(settlementID)
	if err := os.MkdirAll(filepath.Dir(lockPath), 0o755); err != nil {
		return settlementChallengeResponse{}, err
	}

	lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			info, statErr := os.Stat(lockPath)
			if statErr == nil && time.Since(info.ModTime()) > cfg.RequestLockTTL {
				_ = os.Remove(lockPath)
				return cfg.withChallengeLock(settlementID, fn)
			}
			return settlementChallengeResponse{
				OK:              false,
				DryRun:          false,
				Status:          "failed",
				FailureCode:     "CHALLENGE_IN_PROGRESS",
				Retryable:       true,
				SettlementRunID: settlementID,
				Detail:          "another challenge settlement attempt with this settlement_run_id is already running",
			}, nil
		}
		return settlementChallengeResponse{}, err
	}

	_, _ = lockFile.WriteString(time.Now().UTC().Format(time.RFC3339Nano))
	_ = lockFile.Close()
	defer os.Remove(lockPath)

	return fn()
}

func readSettlementChallengeStoredResult(path string) (settlementChallengeStoredResult, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return settlementChallengeStoredResult{}, err
	}
	result := settlementChallengeStoredResult{}
	if err := json.Unmarshal(data, &result); err != nil {
		return settlementChallengeStoredResult{}, err
	}
	return result, nil
}

func writeSettlementChallengeStoredResult(path string, result settlementChallengeStoredResult) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	tmpPath := path + ".tmp"
	if err := os.WriteFile(tmpPath, append(payload, '\n'), 0o600); err != nil {
		return err
	}
	return os.Rename(tmpPath, path)
}

func (cfg settlementConfig) inspectSettlementChallenge(settlementID string) (settlementChallengeInspectResponse, error) {
	settlementID = strings.TrimSpace(settlementID)
	if settlementID == "" {
		return settlementChallengeInspectResponse{}, errors.New("settlement id is required")
	}
	recordPath := cfg.challengeRecordPath(settlementID)
	record, err := readSettlementChallengeStoredResult(recordPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return settlementChallengeInspectResponse{
				Found:           false,
				SettlementRunID: settlementID,
			}, nil
		}
		return settlementChallengeInspectResponse{}, err
	}
	summary := summarizeSettlementChallengeStoredResult(record)
	return settlementChallengeInspectResponse{
		Found:           true,
		SettlementRunID: settlementID,
		ChallengePath:   recordPath,
		Summary:         &summary,
		Record:          &record,
	}, nil
}

func (cfg settlementConfig) listRecentSettlementChallenges(limit int, statusFilter, failureCodeFilter string) ([]settlementChallengeRecentItem, error) {
	recordsDir := filepath.Join(cfg.StateDir, "challenge-settlements")
	entries, err := os.ReadDir(recordsDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return []settlementChallengeRecentItem{}, nil
		}
		return nil, err
	}

	items := make([]settlementChallengeRecentItem, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		recordPath := filepath.Join(recordsDir, entry.Name())
		record, err := readSettlementChallengeStoredResult(recordPath)
		if err != nil {
			return nil, fmt.Errorf("read challenge settlement record %s: %w", recordPath, err)
		}
		if statusFilter != "" && statusFilter != "all" && !strings.EqualFold(record.Response.Status, statusFilter) {
			continue
		}
		if failureCodeFilter != "" && !strings.EqualFold(strings.TrimSpace(record.Response.FailureCode), failureCodeFilter) {
			continue
		}

		summary := summarizeSettlementChallengeStoredResult(record)
		items = append(items, settlementChallengeRecentItem{
			SettlementRunID: record.Request.SettlementRunID,
			ChallengePath:   recordPath,
			UpdatedAt:       record.UpdatedAt,
			Summary:         summary,
			Record:          record,
		})
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func summarizeSettlementChallengeStoredResult(record settlementChallengeStoredResult) settlementChallengeSummary {
	summary := settlementChallengeSummary{
		SettlementRunID:        record.Request.SettlementRunID,
		UpdatedAt:              record.UpdatedAt,
		Status:                 record.Response.Status,
		FailureCode:            record.Response.FailureCode,
		Retryable:              record.Response.Retryable,
		IdempotentReplay:       record.Response.IdempotentReplay,
		SourceApp:              record.Request.SourceApp,
		ChallengeID:            record.Request.ChallengeID,
		SourceEventID:          record.Request.SourceEventID,
		TreasuryAddress:        record.Request.TreasuryAddress,
		ParticipantCount:       record.Response.ParticipantCount,
		FundingVerifiedCount:   record.Response.FundingVerifiedCount,
		RequestedTransferCount: record.Response.RequestedTransferCount,
		ExecutedTransferCount:  record.Response.ExecutedTransferCount,
		ConfirmedTransferCount: record.Response.ConfirmedTransferCount,
		AcceptedTransferCount:  record.Response.AcceptedTransferCount,
		RefusedTransferCount:   record.Response.RefusedTransferCount,
		RejectedTransferCount:  record.Response.RejectedTransferCount,
		ReplayTransferCount:    record.Response.ReplayTransferCount,
		FundingTotalUWolo:      record.Response.FundingTotalUWolo,
		RequestedTotalUWolo:    record.Response.RequestedTotalUWolo,
		TopUpRequired:          record.Response.TopUp != nil && record.Response.TopUp.Required,
		TopUpExecuted:          record.Response.TopUp != nil && record.Response.TopUp.Response != nil && record.Response.TopUp.Response.OK,
		Detail:                 record.Response.Detail,
	}
	if record.Response.TopUp != nil && record.Response.TopUp.Response != nil {
		summary.TopUpTxHash = record.Response.TopUp.Response.TxHash
	}
	return summary
}

func summarizeSettlementChallengeRecentItems(limit int, statusFilter, failureCodeFilter string, items []settlementChallengeRecentItem) settlementChallengeRecentSummary {
	summary := settlementChallengeRecentSummary{
		RequestedLimit:    limit,
		Returned:          len(items),
		StatusFilter:      statusFilter,
		FailureCodeFilter: failureCodeFilter,
		FailureCodes:      map[string]int{},
	}
	for _, item := range items {
		switch item.Summary.Status {
		case "failed":
			summary.FailedCount++
		case "partial":
			summary.PartialCount++
		case "confirmed":
			summary.ConfirmedCount++
		case "accepted":
			summary.AcceptedCount++
		}
		if item.Summary.IdempotentReplay {
			summary.ReplayCount++
		}
		if item.Summary.Retryable {
			summary.RetryableCount++
		}
		if item.Summary.FailureCode != "" {
			summary.FailureCodes[item.Summary.FailureCode]++
		}
	}
	if len(summary.FailureCodes) == 0 {
		summary.FailureCodes = nil
	}
	return summary
}

func optionalSettlementChallengeRecentItems(summaryOnly bool, items []settlementChallengeRecentItem) []settlementChallengeRecentItem {
	if summaryOnly {
		return nil
	}
	return items
}

func challengeFundingIdentityKey(participantSide, participantID, fundingTxHash string) string {
	return strings.ToLower(strings.TrimSpace(participantSide)) + "|" + strings.ToLower(strings.TrimSpace(participantID)) + "|" + strings.ToUpper(strings.TrimSpace(fundingTxHash))
}

func challengeFundingLabel(participantSide, participantID, fundingTxHash string) string {
	switch {
	case strings.TrimSpace(participantSide) != "" && strings.TrimSpace(participantID) != "":
		return fmt.Sprintf("participant_side=%s participant_id=%s (tx %s)", participantSide, participantID, fundingTxHash)
	case strings.TrimSpace(participantSide) != "":
		return fmt.Sprintf("participant_side=%s (tx %s)", participantSide, fundingTxHash)
	case strings.TrimSpace(participantID) != "":
		return fmt.Sprintf("participant_id=%s (tx %s)", participantID, fundingTxHash)
	default:
		return fmt.Sprintf("funding tx %s", fundingTxHash)
	}
}

func deriveSettlementChallengeTransferRequestID(settlementID string, index int) string {
	return fmt.Sprintf("%s:challenge-%03d", settlementID, index+1)
}

func deriveSettlementChallengeTopUpRequestID(settlementID string) string {
	return settlementID + ":topup"
}

func parseBoolEnv(key string) bool {
	value := strings.TrimSpace(strings.ToLower(os.Getenv(key)))
	switch value {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}
