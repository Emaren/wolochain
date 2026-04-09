package cmd

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
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

	"github.com/emaren/wolochain/app"
)

const (
	settlementCanonicalChainID      = "wolo-testnet"
	settlementCanonicalBaseDenom    = "uwolo"
	settlementCanonicalDisplayDenom = "wolo"
	settlementCanonicalPrefix       = "wolo"
	settlementDefaultGasPrices      = "0.025uwolo"
	settlementDefaultRPC            = "http://127.0.0.1:26657"
	settlementDefaultNode           = "tcp://127.0.0.1:26657"
	settlementDefaultREST           = "http://127.0.0.1:1317"
	settlementDefaultListenAddr     = "127.0.0.1:8091"
	settlementSignerRole            = "payout"
	settlementMaxRunPayouts         = 250
)

var settlementRequestIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$`)
var settlementSourceEventPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$`)

type settlementConfig struct {
	ExecutablePath        string
	HomeDir               string
	KeyringBackend        string
	KeyringDir            string
	NodeAddr              string
	RPCHTTP               string
	RESTURL               string
	PublicRESTURL         string
	ChainID               string
	BaseDenom             string
	DisplayDenom          string
	AddressPrefix         string
	PayoutKeyName         string
	PayoutAddress         string
	EscrowAddress         string
	BroadcastMode         string
	Gas                   string
	GasAdjustment         string
	GasPrices             string
	Fees                  string
	MinPayoutBalanceUWolo uint64
	FeeHeadroomUWolo      uint64
	StateDir              string
	ListenAddr            string
	AuthToken             string
	RequestLockTTL        time.Duration
	RequestTimeout        time.Duration
	LookupTimeout         time.Duration
	HealthTimeout         time.Duration
	ConfirmTimeout        time.Duration
	ConfirmInterval       time.Duration
}

type settlementHealthResponse struct {
	OK                    bool     `json:"ok"`
	FailureCode           string   `json:"failure_code,omitempty"`
	Detail                string   `json:"detail,omitempty"`
	ChainID               string   `json:"chain_id"`
	RuntimeChainID        string   `json:"runtime_chain_id,omitempty"`
	RPCURL                string   `json:"rpc_url"`
	RESTURL               string   `json:"rest_url"`
	PublicRESTURL         string   `json:"public_rest_url,omitempty"`
	HomeDir               string   `json:"home_dir"`
	KeyringBackend        string   `json:"keyring_backend"`
	PayoutKeyName         string   `json:"payout_key_name,omitempty"`
	PayoutAddress         string   `json:"payout_address,omitempty"`
	EscrowAddress         string   `json:"escrow_address,omitempty"`
	PayoutBalanceUWolo    string   `json:"payout_balance_uwolo,omitempty"`
	PayoutBalanceWolo     string   `json:"payout_balance_wolo,omitempty"`
	MinPayoutBalanceUWolo string   `json:"min_payout_balance_uwolo,omitempty"`
	MinPayoutBalanceWolo  string   `json:"min_payout_balance_wolo,omitempty"`
	FeeHeadroomUWolo      string   `json:"fee_headroom_uwolo,omitempty"`
	FeeHeadroomWolo       string   `json:"fee_headroom_wolo,omitempty"`
	Warnings              []string `json:"warnings,omitempty"`
	LoopbackOnly          bool     `json:"loopback_only"`
	AuthTokenSet          bool     `json:"auth_token_set"`
}

type settlementExecuteRequest struct {
	RequestID   string `json:"request_id"`
	ToAddress   string `json:"to_address"`
	AmountUWolo string `json:"amount_uwolo,omitempty"`
	AmountWolo  int64  `json:"amount_wolo,omitempty"`
	Memo        string `json:"memo,omitempty"`
}

type normalizedSettlementRequest struct {
	RequestID   string `json:"request_id"`
	ToAddress   string `json:"to_address"`
	AmountUWolo string `json:"amount_uwolo"`
	Memo        string `json:"memo,omitempty"`
}

type settlementExecuteResponse struct {
	OK                         bool   `json:"ok"`
	Status                     string `json:"status"`
	FailureCode                string `json:"failure_code,omitempty"`
	Retryable                  bool   `json:"retryable"`
	IdempotentReplay           bool   `json:"idempotent_replay"`
	RequestID                  string `json:"request_id"`
	ChainID                    string `json:"chain_id"`
	SignerRole                 string `json:"signer_role"`
	SignerAddress              string `json:"signer_address,omitempty"`
	ToAddress                  string `json:"to_address,omitempty"`
	AmountUWolo                string `json:"amount_uwolo,omitempty"`
	AmountWolo                 string `json:"amount_wolo,omitempty"`
	BroadcastMode              string `json:"broadcast_mode,omitempty"`
	TxHash                     string `json:"tx_hash,omitempty"`
	Code                       uint32 `json:"code,omitempty"`
	Codespace                  string `json:"codespace,omitempty"`
	RawLog                     string `json:"raw_log,omitempty"`
	Detail                     string `json:"detail,omitempty"`
	CanonicalTxLookup          string `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string `json:"canonical_tx_lookup_public,omitempty"`
}

type settlementRunRequest struct {
	SettlementRunID string                     `json:"settlement_run_id"`
	SourceApp       string                     `json:"source_app,omitempty"`
	SourceEventID   string                     `json:"source_event_id,omitempty"`
	Note            string                     `json:"note,omitempty"`
	Memo            string                     `json:"memo,omitempty"`
	Payouts         []settlementRunPayoutInput `json:"payouts"`
}

type settlementRunPayoutInput struct {
	RequestID   string `json:"request_id,omitempty"`
	ToAddress   string `json:"to_address"`
	AmountUWolo string `json:"amount_uwolo,omitempty"`
	AmountWolo  int64  `json:"amount_wolo,omitempty"`
	Memo        string `json:"memo,omitempty"`
}

type normalizedSettlementRunRequest struct {
	SettlementRunID string                       `json:"settlement_run_id"`
	SourceApp       string                       `json:"source_app,omitempty"`
	SourceEventID   string                       `json:"source_event_id,omitempty"`
	Note            string                       `json:"note,omitempty"`
	Memo            string                       `json:"memo,omitempty"`
	Payouts         []normalizedSettlementPayout `json:"payouts"`
}

type normalizedSettlementPayout struct {
	Index       int    `json:"index"`
	RequestID   string `json:"request_id"`
	ToAddress   string `json:"to_address"`
	AmountUWolo string `json:"amount_uwolo"`
	Memo        string `json:"memo,omitempty"`
}

type settlementRunPayoutResult struct {
	Index                      int      `json:"index"`
	RequestID                  string   `json:"request_id"`
	Attempted                  bool     `json:"attempted"`
	OK                         bool     `json:"ok"`
	Status                     string   `json:"status"`
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

type settlementRunResponse struct {
	OK                       bool                        `json:"ok"`
	DryRun                   bool                        `json:"dry_run"`
	Status                   string                      `json:"status"`
	FailureCode              string                      `json:"failure_code,omitempty"`
	Retryable                bool                        `json:"retryable"`
	IdempotentReplay         bool                        `json:"idempotent_replay"`
	SettlementRunID          string                      `json:"settlement_run_id"`
	SourceApp                string                      `json:"source_app,omitempty"`
	SourceEventID            string                      `json:"source_event_id,omitempty"`
	Note                     string                      `json:"note,omitempty"`
	Memo                     string                      `json:"memo,omitempty"`
	RequestedPayoutCount     int                         `json:"requested_payout_count"`
	ExecutedPayoutCount      int                         `json:"executed_payout_count"`
	ConfirmedPayoutCount     int                         `json:"confirmed_payout_count"`
	AcceptedPayoutCount      int                         `json:"accepted_payout_count"`
	RefusedPayoutCount       int                         `json:"refused_payout_count"`
	RejectedPayoutCount      int                         `json:"rejected_payout_count"`
	ReplayPayoutCount        int                         `json:"replay_payout_count"`
	RequestedTotalUWolo      string                      `json:"requested_total_uwolo,omitempty"`
	RequestedTotalWolo       string                      `json:"requested_total_wolo,omitempty"`
	ExecutedTotalUWolo       string                      `json:"executed_total_uwolo,omitempty"`
	ExecutedTotalWolo        string                      `json:"executed_total_wolo,omitempty"`
	ConfirmedTotalUWolo      string                      `json:"confirmed_total_uwolo,omitempty"`
	ConfirmedTotalWolo       string                      `json:"confirmed_total_wolo,omitempty"`
	AcceptedTotalUWolo       string                      `json:"accepted_total_uwolo,omitempty"`
	AcceptedTotalWolo        string                      `json:"accepted_total_wolo,omitempty"`
	RefusedTotalUWolo        string                      `json:"refused_total_uwolo,omitempty"`
	RefusedTotalWolo         string                      `json:"refused_total_wolo,omitempty"`
	RejectedTotalUWolo       string                      `json:"rejected_total_uwolo,omitempty"`
	RejectedTotalWolo        string                      `json:"rejected_total_wolo,omitempty"`
	PayoutBalanceBeforeUWolo string                      `json:"payout_balance_before_uwolo,omitempty"`
	PayoutBalanceBeforeWolo  string                      `json:"payout_balance_before_wolo,omitempty"`
	ProjectedRemainingUWolo  string                      `json:"projected_remaining_uwolo,omitempty"`
	ProjectedRemainingWolo   string                      `json:"projected_remaining_wolo,omitempty"`
	EstimatedFeeTotalUWolo   string                      `json:"estimated_fee_total_uwolo,omitempty"`
	EstimatedFeeTotalWolo    string                      `json:"estimated_fee_total_wolo,omitempty"`
	MinPayoutBalanceUWolo    string                      `json:"min_payout_balance_uwolo,omitempty"`
	MinPayoutBalanceWolo     string                      `json:"min_payout_balance_wolo,omitempty"`
	FeeHeadroomUWolo         string                      `json:"fee_headroom_uwolo,omitempty"`
	FeeHeadroomWolo          string                      `json:"fee_headroom_wolo,omitempty"`
	Warnings                 []string                    `json:"warnings,omitempty"`
	Detail                   string                      `json:"detail,omitempty"`
	Payouts                  []settlementRunPayoutResult `json:"payouts,omitempty"`
}

type settlementStoredResult struct {
	Request     normalizedSettlementRequest `json:"request"`
	Fingerprint string                      `json:"fingerprint"`
	Response    settlementExecuteResponse   `json:"response"`
	UpdatedAt   time.Time                   `json:"updated_at"`
}

type settlementRunStoredResult struct {
	Request     normalizedSettlementRunRequest `json:"request"`
	Fingerprint string                         `json:"fingerprint"`
	Response    settlementRunResponse          `json:"response"`
	UpdatedAt   time.Time                      `json:"updated_at"`
}

type settlementLookupResponse struct {
	OK                         bool                 `json:"ok"`
	FailureCode                string               `json:"failure_code,omitempty"`
	Detail                     string               `json:"detail,omitempty"`
	Found                      bool                 `json:"found"`
	ChainID                    string               `json:"chain_id,omitempty"`
	TxHash                     string               `json:"tx_hash,omitempty"`
	TxSuccess                  bool                 `json:"tx_success"`
	Kind                       string               `json:"kind,omitempty"`
	Height                     string               `json:"height,omitempty"`
	Code                       uint32               `json:"code,omitempty"`
	Codespace                  string               `json:"codespace,omitempty"`
	Memo                       string               `json:"memo,omitempty"`
	RawLog                     string               `json:"raw_log,omitempty"`
	Timestamp                  string               `json:"timestamp,omitempty"`
	CanonicalTxLookup          string               `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string               `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string               `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string               `json:"canonical_tx_lookup_public,omitempty"`
	Transfers                  []settlementTransfer `json:"transfers,omitempty"`
	MatchedExpected            bool                 `json:"matched_expected"`
	MatchedTransfer            *settlementTransfer  `json:"matched_transfer,omitempty"`
}

type settlementEscrowVerifyResponse struct {
	OK                  bool                      `json:"ok"`
	FailureCode         string                    `json:"failure_code,omitempty"`
	Detail              string                    `json:"detail,omitempty"`
	EscrowAddress       string                    `json:"escrow_address,omitempty"`
	ExpectedSender      string                    `json:"expected_sender,omitempty"`
	ExpectedAmountUWolo string                    `json:"expected_amount_uwolo,omitempty"`
	DepositFound        bool                      `json:"deposit_found"`
	Lookup              *settlementLookupResponse `json:"lookup,omitempty"`
}

type settlementEscrowRecentResponse struct {
	OK            bool                          `json:"ok"`
	FailureCode   string                        `json:"failure_code,omitempty"`
	Detail        string                        `json:"detail,omitempty"`
	EscrowAddress string                        `json:"escrow_address,omitempty"`
	SenderFilter  string                        `json:"sender_filter,omitempty"`
	Limit         int                           `json:"limit"`
	Count         int                           `json:"count"`
	Deposits      []settlementEscrowDepositItem `json:"deposits,omitempty"`
}

type settlementEscrowDepositItem struct {
	TransferIndex              int    `json:"transfer_index"`
	TxHash                     string `json:"tx_hash"`
	Height                     string `json:"height,omitempty"`
	Timestamp                  string `json:"timestamp,omitempty"`
	TxSuccess                  bool   `json:"tx_success"`
	Sender                     string `json:"sender,omitempty"`
	Recipient                  string `json:"recipient,omitempty"`
	AmountUWolo                string `json:"amount_uwolo,omitempty"`
	AmountWolo                 string `json:"amount_wolo,omitempty"`
	Memo                       string `json:"memo,omitempty"`
	CanonicalTxLookup          string `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string `json:"canonical_tx_lookup_public,omitempty"`
}

type settlementTransfer struct {
	Sender    string `json:"sender"`
	Recipient string `json:"recipient"`
	Amount    string `json:"amount"`
	Denom     string `json:"denom"`
}

type settlementInspectResponse struct {
	Found       bool                     `json:"found"`
	RequestID   string                   `json:"request_id"`
	RequestPath string                   `json:"request_path,omitempty"`
	Summary     *settlementRecordSummary `json:"summary,omitempty"`
	Record      *settlementStoredResult  `json:"record,omitempty"`
}

type settlementRecentResponse struct {
	Count   int                     `json:"count"`
	Summary settlementRecentSummary `json:"summary"`
	Items   []settlementRecentItem  `json:"items,omitempty"`
}

type settlementRecentItem struct {
	RequestID   string                  `json:"request_id"`
	RequestPath string                  `json:"request_path"`
	UpdatedAt   time.Time               `json:"updated_at"`
	Summary     settlementRecordSummary `json:"summary"`
	Record      settlementStoredResult  `json:"record"`
}

type settlementRecordSummary struct {
	RequestID                  string    `json:"request_id"`
	UpdatedAt                  time.Time `json:"updated_at,omitempty"`
	Outcome                    string    `json:"outcome"`
	Status                     string    `json:"status,omitempty"`
	FailureCode                string    `json:"failure_code,omitempty"`
	Retryable                  bool      `json:"retryable"`
	IdempotentReplay           bool      `json:"idempotent_replay"`
	SignerRole                 string    `json:"signer_role,omitempty"`
	SignerAddress              string    `json:"signer_address,omitempty"`
	ToAddress                  string    `json:"to_address,omitempty"`
	AmountUWolo                string    `json:"amount_uwolo,omitempty"`
	AmountWolo                 string    `json:"amount_wolo,omitempty"`
	TxHash                     string    `json:"tx_hash,omitempty"`
	Detail                     string    `json:"detail,omitempty"`
	CanonicalTxLookup          string    `json:"canonical_tx_lookup,omitempty"`
	CanonicalTxLookupPreferred string    `json:"canonical_tx_lookup_preferred,omitempty"`
	CanonicalTxLookupInternal  string    `json:"canonical_tx_lookup_internal,omitempty"`
	CanonicalTxLookupPublic    string    `json:"canonical_tx_lookup_public,omitempty"`
}

type settlementRecentSummary struct {
	RequestedLimit    int            `json:"requested_limit"`
	Returned          int            `json:"returned"`
	StatusFilter      string         `json:"status_filter,omitempty"`
	FailureCodeFilter string         `json:"failure_code_filter,omitempty"`
	FailedCount       int            `json:"failed_count"`
	RefusedCount      int            `json:"refused_count"`
	RejectedCount     int            `json:"rejected_count"`
	AcceptedCount     int            `json:"accepted_count"`
	ConfirmedCount    int            `json:"confirmed_count"`
	ReplayCount       int            `json:"replay_count"`
	RetryableCount    int            `json:"retryable_count"`
	FailureCodes      map[string]int `json:"failure_codes,omitempty"`
}

type settlementRunInspectResponse struct {
	Found           bool                       `json:"found"`
	SettlementRunID string                     `json:"settlement_run_id"`
	RunPath         string                     `json:"run_path,omitempty"`
	Summary         *settlementRunSummary      `json:"summary,omitempty"`
	Record          *settlementRunStoredResult `json:"record,omitempty"`
}

type settlementRunRecentResponse struct {
	Count   int                        `json:"count"`
	Summary settlementRunRecentSummary `json:"summary"`
	Items   []settlementRunRecentItem  `json:"items,omitempty"`
}

type settlementRunRecentItem struct {
	SettlementRunID string                    `json:"settlement_run_id"`
	RunPath         string                    `json:"run_path"`
	UpdatedAt       time.Time                 `json:"updated_at"`
	Summary         settlementRunSummary      `json:"summary"`
	Record          settlementRunStoredResult `json:"record"`
}

type settlementRunSummary struct {
	SettlementRunID      string    `json:"settlement_run_id"`
	UpdatedAt            time.Time `json:"updated_at,omitempty"`
	Status               string    `json:"status,omitempty"`
	FailureCode          string    `json:"failure_code,omitempty"`
	Retryable            bool      `json:"retryable"`
	IdempotentReplay     bool      `json:"idempotent_replay"`
	SourceApp            string    `json:"source_app,omitempty"`
	SourceEventID        string    `json:"source_event_id,omitempty"`
	Note                 string    `json:"note,omitempty"`
	Memo                 string    `json:"memo,omitempty"`
	SignerRole           string    `json:"signer_role,omitempty"`
	SignerAddress        string    `json:"signer_address,omitempty"`
	RequestedPayoutCount int       `json:"requested_payout_count"`
	ExecutedPayoutCount  int       `json:"executed_payout_count"`
	ConfirmedPayoutCount int       `json:"confirmed_payout_count"`
	AcceptedPayoutCount  int       `json:"accepted_payout_count"`
	RefusedPayoutCount   int       `json:"refused_payout_count"`
	RejectedPayoutCount  int       `json:"rejected_payout_count"`
	ReplayPayoutCount    int       `json:"replay_payout_count"`
	RequestedTotalUWolo  string    `json:"requested_total_uwolo,omitempty"`
	RequestedTotalWolo   string    `json:"requested_total_wolo,omitempty"`
	ExecutedTotalUWolo   string    `json:"executed_total_uwolo,omitempty"`
	ExecutedTotalWolo    string    `json:"executed_total_wolo,omitempty"`
	ConfirmedTotalUWolo  string    `json:"confirmed_total_uwolo,omitempty"`
	ConfirmedTotalWolo   string    `json:"confirmed_total_wolo,omitempty"`
	AcceptedTotalUWolo   string    `json:"accepted_total_uwolo,omitempty"`
	AcceptedTotalWolo    string    `json:"accepted_total_wolo,omitempty"`
	RefusedTotalUWolo    string    `json:"refused_total_uwolo,omitempty"`
	RefusedTotalWolo     string    `json:"refused_total_wolo,omitempty"`
	RejectedTotalUWolo   string    `json:"rejected_total_uwolo,omitempty"`
	RejectedTotalWolo    string    `json:"rejected_total_wolo,omitempty"`
	Detail               string    `json:"detail,omitempty"`
}

type settlementRunRecentSummary struct {
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

type settlementLookupExpectations struct {
	Sender      string
	Recipient   string
	AmountUWolo string
}

type tenderStatusResponse struct {
	Result struct {
		NodeInfo struct {
			Network string `json:"network"`
		} `json:"node_info"`
	} `json:"result"`
}

type restNodeInfoResponse struct {
	DefaultNodeInfo struct {
		Network string `json:"network"`
	} `json:"default_node_info"`
}

type restDenomMetadataResponse struct {
	Metadata struct {
		Base    string `json:"base"`
		Display string `json:"display"`
	} `json:"metadata"`
}

type restStakingParamsResponse struct {
	Params struct {
		BondDenom string `json:"bond_denom"`
	} `json:"params"`
}

type restMintParamsResponse struct {
	Params struct {
		MintDenom string `json:"mint_denom"`
	} `json:"params"`
}

type restBalancesResponse struct {
	Balances []struct {
		Denom  string `json:"denom"`
		Amount string `json:"amount"`
	} `json:"balances"`
}

type restTxLookupResponse struct {
	Tx struct {
		Body struct {
			Memo string `json:"memo"`
		} `json:"body"`
	} `json:"tx"`
	TxResponse struct {
		Height    string          `json:"height"`
		TxHash    string          `json:"txhash"`
		Code      uint32          `json:"code"`
		Codespace string          `json:"codespace"`
		RawLog    string          `json:"raw_log"`
		Timestamp string          `json:"timestamp"`
		Logs      []restTxLogItem `json:"logs"`
		Events    []restTxEvent   `json:"events"`
	} `json:"tx_response"`
}

type restTxSearchResponse struct {
	Txs []struct {
		Body struct {
			Memo string `json:"memo"`
		} `json:"body"`
	} `json:"txs"`
	TxResponses []struct {
		Height    string          `json:"height"`
		TxHash    string          `json:"txhash"`
		Code      uint32          `json:"code"`
		Codespace string          `json:"codespace"`
		RawLog    string          `json:"raw_log"`
		Timestamp string          `json:"timestamp"`
		Logs      []restTxLogItem `json:"logs"`
		Events    []restTxEvent   `json:"events"`
	} `json:"tx_responses"`
	Pagination struct {
		NextKey string `json:"next_key"`
		Total   string `json:"total"`
	} `json:"pagination"`
	Total string `json:"total"`
}

type restTxLogItem struct {
	Events []restTxEvent `json:"events"`
}

type restTxEvent struct {
	Type       string                 `json:"type"`
	Attributes []restTxEventAttribute `json:"attributes"`
}

type restTxEventAttribute struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type bankSendBroadcastResponse struct {
	Height    string `json:"height"`
	TxHash    string `json:"txhash"`
	Code      uint32 `json:"code"`
	Codespace string `json:"codespace"`
	RawLog    string `json:"raw_log"`
}

func settlementCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "settlement",
		Short: "Settlement execution and proof surfaces owned by WoloChain",
	}

	cmd.AddCommand(
		newSettlementDoctorCmd(),
		newSettlementExecuteCmd(),
		newSettlementEscrowCmd(),
		newSettlementLookupCmd(),
		newSettlementInspectCmd(),
		newSettlementRecentCmd(),
		newSettlementRunCmd(),
		newSettlementServeCmd(),
	)

	return cmd
}

func newSettlementEscrowCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "escrow",
		Short: "Read-only escrow deposit verification and discovery helpers",
	}

	cmd.AddCommand(
		newSettlementEscrowVerifyCmd(),
		newSettlementEscrowRecentCmd(),
	)

	return cmd
}

func newSettlementEscrowVerifyCmd() *cobra.Command {
	var (
		txHash       string
		expectedFrom string
		expectedAmt  string
	)

	cmd := &cobra.Command{
		Use:   "verify",
		Short: "Verify that a tx delivered a WOLO transfer into the configured escrow address",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.verifyEscrowDeposit(cmd.Context(), txHash, expectedFrom, expectedAmt)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&txHash, "tx-hash", "", "Transaction hash to verify against the configured escrow address")
	cmd.Flags().StringVar(&expectedFrom, "expected-sender", "", "Expected WOLO sender for escrow deposit matching")
	cmd.Flags().StringVar(&expectedAmt, "expected-amount-uwolo", "", "Expected WOLO amount for escrow deposit matching")
	return cmd
}

func newSettlementEscrowRecentCmd() *cobra.Command {
	var (
		limit  int
		sender string
	)

	cmd := &cobra.Command{
		Use:   "recent",
		Short: "List recent WOLO transfers into the configured escrow address",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.listRecentEscrowDeposits(cmd.Context(), limit, sender)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().IntVar(&limit, "limit", 20, "Maximum number of recent escrow transfers to return")
	cmd.Flags().StringVar(&sender, "sender", "", "Optional WOLO sender address filter")
	return cmd
}

func newSettlementDoctorCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Check settlement runtime config and chain invariants",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			report := cfg.buildHealthReport(cmd.Context())
			return writeJSON(cmd.OutOrStdout(), report)
		},
	}
}

func newSettlementExecuteCmd() *cobra.Command {
	var request settlementExecuteRequest

	cmd := &cobra.Command{
		Use:   "execute",
		Short: "Execute an idempotent WOLO payout transfer",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.executeSettlement(cmd.Context(), request)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&request.RequestID, "request-id", "", "Stable payout request id")
	cmd.Flags().StringVar(&request.ToAddress, "to", "", "WOLO recipient address")
	cmd.Flags().StringVar(&request.AmountUWolo, "amount-uwolo", "", "Amount in canonical base denom")
	cmd.Flags().Int64Var(&request.AmountWolo, "amount-wolo", 0, "Whole WOLO amount when amount-uwolo is omitted")
	cmd.Flags().StringVar(&request.Memo, "memo", "", "Memo/note for the payout tx")

	return cmd
}

func newSettlementLookupCmd() *cobra.Command {
	var (
		txHash       string
		expectedFrom string
		expectedTo   string
		expectedAmt  string
	)

	cmd := &cobra.Command{
		Use:   "lookup",
		Short: "Lookup and normalize a WOLO tx proof by hash",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			response, err := cfg.lookupSettlementTx(cmd.Context(), txHash, settlementLookupExpectations{
				Sender:      expectedFrom,
				Recipient:   expectedTo,
				AmountUWolo: expectedAmt,
			})
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&txHash, "tx-hash", "", "Transaction hash")
	cmd.Flags().StringVar(&expectedFrom, "expected-sender", "", "Expected sender for proof matching")
	cmd.Flags().StringVar(&expectedTo, "expected-recipient", "", "Expected recipient for proof matching")
	cmd.Flags().StringVar(&expectedAmt, "expected-amount-uwolo", "", "Expected amount for proof matching")

	return cmd
}

func newSettlementInspectCmd() *cobra.Command {
	var (
		requestID   string
		summaryOnly bool
	)

	cmd := &cobra.Command{
		Use:   "inspect",
		Short: "Inspect stored settlement request state by request id",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			requestID = strings.TrimSpace(requestID)
			if requestID == "" {
				return errors.New("--request-id is required")
			}

			recordPath := cfg.requestRecordPath(requestID)
			record, err := readSettlementStoredResult(recordPath)
			if err != nil {
				if errors.Is(err, os.ErrNotExist) {
					return writeJSON(cmd.OutOrStdout(), settlementInspectResponse{
						Found:     false,
						RequestID: requestID,
					})
				}
				return err
			}

			summary := summarizeSettlementStoredResult(record)
			return writeJSON(cmd.OutOrStdout(), settlementInspectResponse{
				Found:       true,
				RequestID:   requestID,
				RequestPath: recordPath,
				Summary:     &summary,
				Record:      optionalSettlementRecord(summaryOnly, &record),
			})
		},
	}

	cmd.Flags().StringVar(&requestID, "request-id", "", "Stored settlement request id")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only concise operator summary fields")
	return cmd
}

func newSettlementRecentCmd() *cobra.Command {
	var (
		limit       int
		status      string
		failureCode string
		summaryOnly bool
	)

	cmd := &cobra.Command{
		Use:   "recent",
		Short: "List recent stored settlement requests for inspection and retry triage",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			status = strings.TrimSpace(strings.ToLower(status))
			switch status {
			case "", "all", "failed", "refused", "rejected", "confirmed", "accepted":
			default:
				return fmt.Errorf("--status must be one of all, failed, refused, rejected, confirmed, accepted")
			}
			failureCode = strings.TrimSpace(strings.ToUpper(failureCode))
			if limit <= 0 {
				return errors.New("--limit must be greater than zero")
			}

			items, err := cfg.listRecentSettlementRecords(limit, status, failureCode)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), settlementRecentResponse{
				Count:   len(items),
				Summary: summarizeSettlementRecentItems(limit, status, failureCode, items),
				Items:   optionalSettlementRecentItems(summaryOnly, items),
			})
		},
	}

	cmd.Flags().IntVar(&limit, "limit", 20, "Maximum number of stored requests to return")
	cmd.Flags().StringVar(&status, "status", "all", "Filter by stored outcome: all, failed, refused, rejected, confirmed, accepted")
	cmd.Flags().StringVar(&failureCode, "failure-code", "", "Optional stored failure code filter")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only summary/count data without embedded records")
	return cmd
}

func newSettlementRunCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "run",
		Short: "Validate, execute, and inspect grouped settlement runs",
	}

	cmd.AddCommand(
		newSettlementRunValidateCmd(),
		newSettlementRunExecuteCmd(),
		newSettlementRunInspectCmd(),
		newSettlementRunRecentCmd(),
	)

	return cmd
}

func newSettlementRunValidateCmd() *cobra.Command {
	var filePath string

	cmd := &cobra.Command{
		Use:   "validate",
		Short: "Dry-run a grouped settlement run without broadcasting payouts",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			request := settlementRunRequest{}
			if err := readJSONInput(filePath, &request); err != nil {
				return err
			}

			response, err := cfg.validateSettlementRun(cmd.Context(), request)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&filePath, "file", "-", "JSON file path for the settlement run payload, or - for stdin")
	return cmd
}

func newSettlementRunExecuteCmd() *cobra.Command {
	var filePath string

	cmd := &cobra.Command{
		Use:   "execute",
		Short: "Execute a grouped settlement run over the single-payout settlement rail",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			request := settlementRunRequest{}
			if err := readJSONInput(filePath, &request); err != nil {
				return err
			}

			response, err := cfg.executeSettlementRun(cmd.Context(), request)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), response)
		},
	}

	cmd.Flags().StringVar(&filePath, "file", "-", "JSON file path for the settlement run payload, or - for stdin")
	return cmd
}

func newSettlementRunInspectCmd() *cobra.Command {
	var (
		runID       string
		summaryOnly bool
	)

	cmd := &cobra.Command{
		Use:   "inspect",
		Short: "Inspect stored settlement run state by run id",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			runID = strings.TrimSpace(runID)
			if runID == "" {
				return errors.New("--run-id is required")
			}

			recordPath := cfg.runRecordPath(runID)
			record, err := readSettlementRunStoredResult(recordPath)
			if err != nil {
				if errors.Is(err, os.ErrNotExist) {
					return writeJSON(cmd.OutOrStdout(), settlementRunInspectResponse{
						Found:           false,
						SettlementRunID: runID,
					})
				}
				return err
			}

			summary := summarizeSettlementRunStoredResult(record)
			return writeJSON(cmd.OutOrStdout(), settlementRunInspectResponse{
				Found:           true,
				SettlementRunID: runID,
				RunPath:         recordPath,
				Summary:         &summary,
				Record:          optionalSettlementRunRecord(summaryOnly, &record),
			})
		},
	}

	cmd.Flags().StringVar(&runID, "run-id", "", "Stored settlement run id")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only concise operator summary fields")
	return cmd
}

func newSettlementRunRecentCmd() *cobra.Command {
	var (
		limit       int
		status      string
		failureCode string
		summaryOnly bool
	)

	cmd := &cobra.Command{
		Use:   "recent",
		Short: "List recent grouped settlement runs for operator triage",
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

			items, err := cfg.listRecentSettlementRuns(limit, status, failureCode)
			if err != nil {
				return err
			}

			return writeJSON(cmd.OutOrStdout(), settlementRunRecentResponse{
				Count:   len(items),
				Summary: summarizeSettlementRunRecentItems(limit, status, failureCode, items),
				Items:   optionalSettlementRunRecentItems(summaryOnly, items),
			})
		},
	}

	cmd.Flags().IntVar(&limit, "limit", 20, "Maximum number of stored runs to return")
	cmd.Flags().StringVar(&status, "status", "all", "Filter by stored run status: all, failed, partial, confirmed, accepted")
	cmd.Flags().StringVar(&failureCode, "failure-code", "", "Optional stored run failure code filter")
	cmd.Flags().BoolVar(&summaryOnly, "summary-only", false, "Return only summary/count data without embedded records")
	return cmd
}

func newSettlementServeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "serve",
		Short: "Serve localhost settlement execution and proof endpoints",
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := loadSettlementConfig()
			if err != nil {
				return err
			}

			if err := cfg.validateServeSafety(); err != nil {
				return err
			}

			server := &http.Server{
				Addr:              cfg.ListenAddr,
				Handler:           cfg.newSettlementHTTPHandler(),
				ReadHeaderTimeout: 5 * time.Second,
			}

			cmd.Printf("settlement server listening on http://%s\n", cfg.ListenAddr)
			return server.ListenAndServe()
		},
	}
}

func (cfg settlementConfig) newSettlementHTTPHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/settlement/v1/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}

		statusCode := http.StatusOK
		report := cfg.buildHealthReport(r.Context())
		if !report.OK {
			statusCode = http.StatusServiceUnavailable
		}
		writeJSONResponse(w, statusCode, report)
	})

	mux.HandleFunc("/settlement/v1/payouts", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if err := cfg.checkAuth(r); err != nil {
			writeJSONResponse(w, http.StatusUnauthorized, map[string]string{"detail": err.Error()})
			return
		}

		var request settlementExecuteRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, settlementExecuteResponse{
				OK:          false,
				Status:      "failed",
				FailureCode: "INVALID_REQUEST",
				Detail:      "request body must be valid JSON",
				ChainID:     cfg.ChainID,
				SignerRole:  settlementSignerRole,
			})
			return
		}

		response, err := cfg.executeSettlement(r.Context(), request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusConflict
			if response.FailureCode == "INVALID_REQUEST" || response.FailureCode == "INVALID_ADDRESS" {
				statusCode = http.StatusBadRequest
			}
		}

		writeJSONResponse(w, statusCode, response)
	})

	mux.HandleFunc("/settlement/v1/runs/validate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if err := cfg.checkAuth(r); err != nil {
			writeJSONResponse(w, http.StatusUnauthorized, map[string]string{"detail": err.Error()})
			return
		}

		var request settlementRunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, settlementRunResponse{
				OK:          false,
				DryRun:      true,
				Status:      "failed",
				FailureCode: "INVALID_RUN",
				Detail:      "request body must be valid JSON",
			})
			return
		}

		response, err := cfg.validateSettlementRun(r.Context(), request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusConflict
			if response.FailureCode == "INVALID_RUN" {
				statusCode = http.StatusBadRequest
			}
		}

		writeJSONResponse(w, statusCode, response)
	})

	mux.HandleFunc("/settlement/v1/runs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if err := cfg.checkAuth(r); err != nil {
			writeJSONResponse(w, http.StatusUnauthorized, map[string]string{"detail": err.Error()})
			return
		}

		var request settlementRunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, settlementRunResponse{
				OK:          false,
				DryRun:      false,
				Status:      "failed",
				FailureCode: "INVALID_RUN",
				Detail:      "request body must be valid JSON",
			})
			return
		}

		response, err := cfg.executeSettlementRun(r.Context(), request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusConflict
			if response.FailureCode == "INVALID_RUN" {
				statusCode = http.StatusBadRequest
			}
		}

		writeJSONResponse(w, statusCode, response)
	})

	mux.HandleFunc("/settlement/v1/escrow/txs/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}

		txHash := strings.TrimPrefix(r.URL.Path, "/settlement/v1/escrow/txs/")
		response, err := cfg.verifyEscrowDeposit(r.Context(), txHash, r.URL.Query().Get("expected_sender"), r.URL.Query().Get("expected_amount_uwolo"))
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusConflict
			switch response.FailureCode {
			case "ESCROW_UNCONFIGURED", "INVALID_ADDRESS", "INVALID_AMOUNT":
				statusCode = http.StatusBadRequest
			case "INVALID_TX_HASH":
				statusCode = http.StatusBadRequest
			case "TX_NOT_FOUND", "NOT_ESCROW_DEPOSIT":
				statusCode = http.StatusNotFound
			case "LOOKUP_FAILED", "RPC_UNREACHABLE", "CHAIN_ID_MISMATCH":
				statusCode = http.StatusServiceUnavailable
			}
		}

		writeJSONResponse(w, statusCode, response)
	})

	mux.HandleFunc("/settlement/v1/escrow/deposits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}

		limit := 20
		if rawLimit := strings.TrimSpace(r.URL.Query().Get("limit")); rawLimit != "" {
			parsedLimit, err := strconv.Atoi(rawLimit)
			if err != nil {
				writeJSONResponse(w, http.StatusBadRequest, settlementEscrowRecentResponse{
					OK:          false,
					FailureCode: "INVALID_LIMIT",
					Detail:      "limit must be a positive integer",
				})
				return
			}
			limit = parsedLimit
		}

		response, err := cfg.listRecentEscrowDeposits(r.Context(), limit, r.URL.Query().Get("sender"))
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusConflict
			switch response.FailureCode {
			case "ESCROW_UNCONFIGURED", "INVALID_ADDRESS", "INVALID_LIMIT":
				statusCode = http.StatusBadRequest
			case "LOOKUP_FAILED", "RPC_UNREACHABLE", "CHAIN_ID_MISMATCH":
				statusCode = http.StatusServiceUnavailable
			}
		}

		writeJSONResponse(w, statusCode, response)
	})

	mux.HandleFunc("/settlement/v1/txs/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}

		txHash := strings.TrimPrefix(r.URL.Path, "/settlement/v1/txs/")
		response, err := cfg.lookupSettlementTx(r.Context(), txHash, settlementLookupExpectations{
			Sender:      r.URL.Query().Get("expected_sender"),
			Recipient:   r.URL.Query().Get("expected_recipient"),
			AmountUWolo: r.URL.Query().Get("expected_amount_uwolo"),
		})
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}

		statusCode := http.StatusOK
		if !response.OK {
			statusCode = http.StatusNotFound
			if response.FailureCode == "INVALID_TX_HASH" {
				statusCode = http.StatusBadRequest
			}
		}
		writeJSONResponse(w, statusCode, response)
	})

	return mux
}

func loadSettlementConfig() (settlementConfig, error) {
	executablePath, err := os.Executable()
	if err != nil {
		return settlementConfig{}, err
	}

	homeDir := getenvFirst("WOLO_SETTLEMENT_HOME", "WOLO_HOME")
	if homeDir == "" {
		homeDir = app.DefaultNodeHome
	}
	homeDir = expandHome(homeDir)

	rpcHTTP := normalizeHTTPURL(getenvFirst("WOLO_SETTLEMENT_RPC_HTTP", "WOLO_SETTLEMENT_RPC_URL", "WOLO_RPC_URL"), settlementDefaultRPC)
	restURL := normalizeHTTPURL(getenvFirst("WOLO_SETTLEMENT_REST_URL", "WOLO_REST_URL"), settlementDefaultREST)
	publicRESTURL := strings.TrimSpace(getenvFirst("WOLO_SETTLEMENT_PUBLIC_REST_URL", "WOLO_PUBLIC_REST_URL"))
	if publicRESTURL != "" {
		publicRESTURL = normalizeHTTPURL(publicRESTURL, "")
	}
	minPayoutBalanceUWolo, err := parseOptionalUWoloEnv("WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO")
	if err != nil {
		return settlementConfig{}, err
	}
	feeHeadroomUWolo, err := parseOptionalUWoloEnv("WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO")
	if err != nil {
		return settlementConfig{}, err
	}

	cfg := settlementConfig{
		ExecutablePath:        executablePath,
		HomeDir:               homeDir,
		KeyringBackend:        getenvDefault("WOLO_SETTLEMENT_KEYRING_BACKEND", "os"),
		KeyringDir:            expandHome(os.Getenv("WOLO_SETTLEMENT_KEYRING_DIR")),
		NodeAddr:              getenvDefault("WOLO_SETTLEMENT_NODE", settlementDefaultNode),
		RPCHTTP:               rpcHTTP,
		RESTURL:               restURL,
		PublicRESTURL:         publicRESTURL,
		ChainID:               getenvDefault("WOLO_SETTLEMENT_CHAIN_ID", settlementCanonicalChainID),
		BaseDenom:             getenvDefault("WOLO_SETTLEMENT_BASE_DENOM", settlementCanonicalBaseDenom),
		DisplayDenom:          getenvDefault("WOLO_SETTLEMENT_DISPLAY_DENOM", settlementCanonicalDisplayDenom),
		AddressPrefix:         getenvDefault("WOLO_SETTLEMENT_ADDRESS_PREFIX", settlementCanonicalPrefix),
		PayoutKeyName:         strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_PAYOUT_KEY_NAME")),
		PayoutAddress:         strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_PAYOUT_ADDRESS")),
		EscrowAddress:         strings.TrimSpace(getenvFirst("WOLO_SETTLEMENT_ESCROW_ADDRESS", "WOLO_BET_ESCROW_ADDRESS")),
		BroadcastMode:         getenvDefault("WOLO_SETTLEMENT_BROADCAST_MODE", "sync"),
		Gas:                   getenvDefault("WOLO_SETTLEMENT_GAS", "auto"),
		GasAdjustment:         getenvDefault("WOLO_SETTLEMENT_GAS_ADJUSTMENT", "1.5"),
		GasPrices:             getenvDefault("WOLO_SETTLEMENT_GAS_PRICES", settlementDefaultGasPrices),
		Fees:                  strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_FEES")),
		MinPayoutBalanceUWolo: minPayoutBalanceUWolo,
		FeeHeadroomUWolo:      feeHeadroomUWolo,
		ListenAddr:            getenvDefault("WOLO_SETTLEMENT_LISTEN_ADDR", settlementDefaultListenAddr),
		AuthToken:             strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_AUTH_TOKEN")),
		RequestLockTTL:        2 * time.Minute,
		RequestTimeout:        30 * time.Second,
		LookupTimeout:         10 * time.Second,
		HealthTimeout:         5 * time.Second,
		ConfirmTimeout:        12 * time.Second,
		ConfirmInterval:       250 * time.Millisecond,
	}

	cfg.StateDir = expandHome(getenvDefault("WOLO_SETTLEMENT_STATE_DIR", filepath.Join(cfg.HomeDir, "settlement")))

	if cfg.BaseDenom != settlementCanonicalBaseDenom ||
		cfg.DisplayDenom != settlementCanonicalDisplayDenom ||
		cfg.AddressPrefix != settlementCanonicalPrefix ||
		cfg.ChainID != settlementCanonicalChainID {
		return settlementConfig{}, fmt.Errorf("settlement config drift detected: chain=%s denom=%s/%s prefix=%s", cfg.ChainID, cfg.BaseDenom, cfg.DisplayDenom, cfg.AddressPrefix)
	}

	return cfg, nil
}

func (cfg settlementConfig) buildHealthReport(ctx context.Context) settlementHealthResponse {
	report := settlementHealthResponse{
		OK:                    true,
		ChainID:               cfg.ChainID,
		RPCURL:                cfg.RPCHTTP,
		RESTURL:               cfg.RESTURL,
		PublicRESTURL:         cfg.PublicRESTURL,
		HomeDir:               cfg.HomeDir,
		KeyringBackend:        cfg.KeyringBackend,
		PayoutKeyName:         cfg.PayoutKeyName,
		EscrowAddress:         cfg.EscrowAddress,
		MinPayoutBalanceUWolo: formatOptionalUWolo(cfg.MinPayoutBalanceUWolo),
		MinPayoutBalanceWolo:  formatOptionalDisplayAmount(cfg.MinPayoutBalanceUWolo),
		FeeHeadroomUWolo:      formatOptionalUWolo(cfg.FeeHeadroomUWolo),
		FeeHeadroomWolo:       formatOptionalDisplayAmount(cfg.FeeHeadroomUWolo),
		LoopbackOnly:          cfg.listenAddrIsLoopback(),
		AuthTokenSet:          cfg.AuthToken != "",
	}

	ctx, cancel := context.WithTimeout(ctx, cfg.HealthTimeout)
	defer cancel()

	runtimeChainID, err := cfg.fetchRuntimeChainID(ctx)
	if err != nil {
		report.OK = false
		report.FailureCode = "RPC_UNREACHABLE"
		report.Detail = err.Error()
		return report
	}
	report.RuntimeChainID = runtimeChainID

	if runtimeChainID != cfg.ChainID {
		report.OK = false
		report.FailureCode = "CHAIN_ID_MISMATCH"
		report.Detail = fmt.Sprintf("rpc reported %s, expected %s", runtimeChainID, cfg.ChainID)
		return report
	}

	if err := cfg.validateRESTInvariants(ctx); err != nil {
		report.OK = false
		report.FailureCode = "REST_DRIFT"
		report.Detail = err.Error()
		return report
	}

	if cfg.PayoutKeyName == "" {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_PAYOUT_KEY_NAME is not set; payout execution is disabled")
	}
	if strings.EqualFold(cfg.PayoutKeyName, "faucetgrowth") {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_PAYOUT_KEY_NAME still points at temporary faucetgrowth; move settlement to a dedicated payout signer")
	}

	if cfg.KeyringBackend == "test" {
		report.Warnings = append(report.Warnings, "test keyring backend is enabled; use only for local/dev or explicitly accepted ops")
	}

	if cfg.AuthToken == "" {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_AUTH_TOKEN is empty; payout POST access relies on loopback-only binding")
	}
	if cfg.PublicRESTURL == "" {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_PUBLIC_REST_URL is empty; preferred proof links will stay internal-only")
	}
	if cfg.MinPayoutBalanceUWolo == 0 {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO is zero; reserve-floor refusal is disabled")
	}
	if cfg.FeeHeadroomUWolo == 0 {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO is zero; fee-headroom refusal is disabled")
	}
	if cfg.EscrowAddress == "" {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_ESCROW_ADDRESS is empty; escrow proof/discovery helpers are disabled")
	}

	payoutAddress, err := cfg.resolvePayoutAddress(ctx)
	if err == nil && payoutAddress != "" {
		report.PayoutAddress = payoutAddress
	}
	if err != nil && cfg.PayoutKeyName != "" {
		if strings.Contains(err.Error(), "payout signer resolved to") {
			report.OK = false
			report.FailureCode = "PAYOUT_ADDRESS_MISMATCH"
			report.Detail = err.Error()
			return report
		}
		report.Warnings = append(report.Warnings, err.Error())
	}
	if payoutAddress != "" {
		balanceUWolo, balanceErr := cfg.fetchAccountBalanceUWolo(ctx, payoutAddress)
		if balanceErr != nil {
			report.OK = false
			report.FailureCode = "PAYOUT_BALANCE_LOOKUP_FAILED"
			report.Detail = balanceErr.Error()
			return report
		}
		report.PayoutBalanceUWolo = strconv.FormatUint(balanceUWolo, 10)
		report.PayoutBalanceWolo = formatDisplayAmount(report.PayoutBalanceUWolo)

		if code, detail, failed := cfg.checkReserveHealth(balanceUWolo); failed {
			report.OK = false
			report.FailureCode = code
			report.Detail = detail
			return report
		}
	}

	if payoutAddress != "" &&
		cfg.EscrowAddress != "" &&
		strings.EqualFold(payoutAddress, cfg.EscrowAddress) {
		report.Warnings = append(report.Warnings, "payout and escrow currently point at the same address; split roles before mainnet")
	}

	if cfg.EscrowAddress != "" && !isWoloAddress(cfg.EscrowAddress, cfg.AddressPrefix) {
		report.OK = false
		report.FailureCode = "INVALID_ESCROW_ADDRESS"
		report.Detail = "WOLO_SETTLEMENT_ESCROW_ADDRESS does not match the wolo prefix"
	}

	return report
}

func (cfg settlementConfig) validateServeSafety() error {
	if cfg.AuthToken != "" {
		return nil
	}

	if cfg.listenAddrIsLoopback() {
		return nil
	}

	return errors.New("WOLO_SETTLEMENT_AUTH_TOKEN is required when binding settlement serve beyond localhost")
}

func (cfg settlementConfig) listenAddrIsLoopback() bool {
	host, _, err := net.SplitHostPort(cfg.ListenAddr)
	if err != nil {
		return false
	}

	if host == "localhost" {
		return true
	}

	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func (cfg settlementConfig) checkAuth(r *http.Request) error {
	if cfg.AuthToken == "" {
		return nil
	}

	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	expected := "Bearer " + cfg.AuthToken
	if authHeader != expected {
		return errors.New("missing or invalid bearer token")
	}

	return nil
}

func (cfg settlementConfig) executeSettlement(ctx context.Context, request settlementExecuteRequest) (settlementExecuteResponse, error) {
	normalized, err := normalizeSettlementRequest(request)
	if err != nil {
		return settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: "INVALID_REQUEST",
			Detail:      err.Error(),
			RequestID:   strings.TrimSpace(request.RequestID),
			ChainID:     cfg.ChainID,
			SignerRole:  settlementSignerRole,
		}, nil
	}

	recordPath := cfg.requestRecordPath(normalized.RequestID)

	response, err := cfg.withRequestLock(normalized.RequestID, func() (settlementExecuteResponse, error) {
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
					SignerRole:    settlementSignerRole,
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
				SignerRole:  settlementSignerRole,
				ToAddress:   normalized.ToAddress,
				AmountUWolo: normalized.AmountUWolo,
				AmountWolo:  formatDisplayAmount(normalized.AmountUWolo),
				Detail:      fmt.Sprintf("could not read settlement state file: %v", readErr),
			}, nil
		}

		signerAddress, failure := cfg.preflightExecution(ctx, normalized.AmountUWolo)
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

		result := cfg.broadcastPayout(ctx, normalized, signerAddress)
		if err := cfg.writeSettlementRecord(recordPath, normalized, signerAddress, result); err != nil {
			return settlementExecuteResponse{}, err
		}
		return result, nil
	})
	if err != nil {
		return settlementExecuteResponse{}, err
	}

	return response, nil
}

func (cfg settlementConfig) writeSettlementRecord(recordPath string, request normalizedSettlementRequest, signerAddress string, response settlementExecuteResponse) error {
	return writeSettlementStoredResult(recordPath, settlementStoredResult{
		Request:     request,
		Fingerprint: hashSettlementRequest(request, signerAddress),
		Response:    response,
		UpdatedAt:   time.Now().UTC(),
	})
}

func (cfg settlementConfig) validateSettlementRun(ctx context.Context, request settlementRunRequest) (settlementRunResponse, error) {
	_, response, err := cfg.buildSettlementRunPlan(ctx, request)
	if err != nil {
		return settlementRunResponse{}, err
	}

	response.DryRun = true
	return response, nil
}

func (cfg settlementConfig) executeSettlementRun(ctx context.Context, request settlementRunRequest) (settlementRunResponse, error) {
	normalized, validation, err := cfg.buildSettlementRunPlan(ctx, request)
	if err != nil {
		return settlementRunResponse{}, err
	}

	validation.DryRun = false
	runID := strings.TrimSpace(validation.SettlementRunID)
	if runID == "" {
		return validation, nil
	}

	recordPath := cfg.runRecordPath(runID)
	fingerprint := hashSettlementRunRequest(normalized)

	response, err := cfg.withRunLock(runID, func() (settlementRunResponse, error) {
		stored, readErr := readSettlementRunStoredResult(recordPath)
		if readErr == nil {
			if stored.Fingerprint != fingerprint {
				return settlementRunResponse{
					OK:              false,
					DryRun:          false,
					Status:          "failed",
					FailureCode:     "IDEMPOTENCY_CONFLICT",
					Retryable:       false,
					SettlementRunID: runID,
					SourceApp:       validation.SourceApp,
					SourceEventID:   validation.SourceEventID,
					Note:            validation.Note,
					Memo:            validation.Memo,
					Detail:          "settlement_run_id already exists with different payout payload",
				}, nil
			}

			if settlementRunResponseIsFinal(stored.Response) {
				replayed := stored.Response
				replayed.DryRun = false
				replayed.IdempotentReplay = true
				return replayed, nil
			}
		} else if !errors.Is(readErr, os.ErrNotExist) {
			return settlementRunResponse{
				OK:              false,
				DryRun:          false,
				Status:          "failed",
				FailureCode:     "STATE_FILE_INVALID",
				Retryable:       false,
				SettlementRunID: runID,
				SourceApp:       validation.SourceApp,
				SourceEventID:   validation.SourceEventID,
				Note:            validation.Note,
				Memo:            validation.Memo,
				Detail:          fmt.Sprintf("could not read settlement run state file: %v", readErr),
			}, nil
		}

		response := validation
		response.DryRun = false
		if !validation.OK {
			if err := writeSettlementRunStoredResult(recordPath, settlementRunStoredResult{
				Request:     normalized,
				Fingerprint: fingerprint,
				Response:    response,
				UpdatedAt:   time.Now().UTC(),
			}); err != nil {
				return settlementRunResponse{}, err
			}
			return response, nil
		}

		itemResults := make([]settlementRunPayoutResult, 0, len(normalized.Payouts))
		for _, payout := range normalized.Payouts {
			itemResponse, err := cfg.executeSettlement(ctx, settlementExecuteRequest{
				RequestID:   payout.RequestID,
				ToAddress:   payout.ToAddress,
				AmountUWolo: payout.AmountUWolo,
				Memo:        payout.Memo,
			})
			if err != nil {
				return settlementRunResponse{}, err
			}
			itemResults = append(itemResults, settlementRunPayoutResultFromExecuteResponse(payout, itemResponse))
		}

		response.Payouts = itemResults
		response.OK = false
		response.Status = ""
		response.FailureCode = ""
		response.Retryable = false
		response.IdempotentReplay = false
		response.ExecutedPayoutCount = 0
		response.ConfirmedPayoutCount = 0
		response.AcceptedPayoutCount = 0
		response.RefusedPayoutCount = 0
		response.RejectedPayoutCount = 0
		response.ReplayPayoutCount = 0
		response.ExecutedTotalUWolo = ""
		response.ExecutedTotalWolo = ""
		response.ConfirmedTotalUWolo = ""
		response.ConfirmedTotalWolo = ""
		response.AcceptedTotalUWolo = ""
		response.AcceptedTotalWolo = ""
		response.RefusedTotalUWolo = ""
		response.RefusedTotalWolo = ""
		response.RejectedTotalUWolo = ""
		response.RejectedTotalWolo = ""
		response.Detail = ""
		response = finalizeSettlementRunResponse(response)
		response.Detail = settlementRunExecutionDetail(response)
		if err := writeSettlementRunStoredResult(recordPath, settlementRunStoredResult{
			Request:     normalized,
			Fingerprint: fingerprint,
			Response:    response,
			UpdatedAt:   time.Now().UTC(),
		}); err != nil {
			return settlementRunResponse{}, err
		}
		return response, nil
	})
	if err != nil {
		return settlementRunResponse{}, err
	}

	return response, nil
}

func (cfg settlementConfig) buildSettlementRunPlan(ctx context.Context, request settlementRunRequest) (normalizedSettlementRunRequest, settlementRunResponse, error) {
	normalized, response := prepareSettlementRunRequest(request)
	response.DryRun = true
	response.MinPayoutBalanceUWolo = formatOptionalUWolo(cfg.MinPayoutBalanceUWolo)
	response.MinPayoutBalanceWolo = formatOptionalDisplayAmount(cfg.MinPayoutBalanceUWolo)
	response.FeeHeadroomUWolo = formatOptionalUWolo(cfg.FeeHeadroomUWolo)
	response.FeeHeadroomWolo = formatOptionalDisplayAmount(cfg.FeeHeadroomUWolo)
	if !runResponseHasReadyPayouts(response) {
		return normalized, finalizeSettlementRunResponse(response), nil
	}

	health := cfg.buildHealthReport(ctx)
	response.PayoutBalanceBeforeUWolo = health.PayoutBalanceUWolo
	response.PayoutBalanceBeforeWolo = health.PayoutBalanceWolo
	if estimatedFeeUWolo, feeWarning := cfg.estimateSettlementRunFee(len(normalized.Payouts)); estimatedFeeUWolo != "" {
		response.EstimatedFeeTotalUWolo = estimatedFeeUWolo
		response.EstimatedFeeTotalWolo = formatDisplayAmount(estimatedFeeUWolo)
	} else if feeWarning != "" {
		response.Warnings = append(response.Warnings, feeWarning)
	}

	if !health.OK {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = health.FailureCode
		response.Retryable = health.FailureCode == "RPC_UNREACHABLE"
		response.Detail = health.Detail
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, health.FailureCode, health.Detail, response.Retryable)
		return normalized, finalizeSettlementRunResponse(response), nil
	}

	totalRequested, err := parseOptionalUWoloString(response.RequestedTotalUWolo)
	if err != nil {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "INVALID_RUN"
		response.Detail = "requested_total_uwolo could not be parsed"
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, response.FailureCode, response.Detail, false)
		return normalized, finalizeSettlementRunResponse(response), nil
	}
	balanceBefore, err := parseOptionalUWoloString(health.PayoutBalanceUWolo)
	if err != nil {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "PAYOUT_BALANCE_LOOKUP_FAILED"
		response.Retryable = true
		response.Detail = "payout signer balance could not be parsed"
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, response.FailureCode, response.Detail, true)
		return normalized, finalizeSettlementRunResponse(response), nil
	}

	if totalRequested > balanceBefore {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "PAYOUT_BALANCE_TOO_LOW"
		response.Retryable = true
		response.Detail = fmt.Sprintf(
			"run requests %s uwolo (%s wolo) but payout signer balance is %s uwolo (%s wolo)",
			response.RequestedTotalUWolo,
			response.RequestedTotalWolo,
			health.PayoutBalanceUWolo,
			health.PayoutBalanceWolo,
		)
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, response.FailureCode, response.Detail, true)
		return normalized, finalizeSettlementRunResponse(response), nil
	}

	projectedRemaining := balanceBefore - totalRequested
	response.ProjectedRemainingUWolo = strconv.FormatUint(projectedRemaining, 10)
	response.ProjectedRemainingWolo = formatDisplayAmount(response.ProjectedRemainingUWolo)
	if cfg.FeeHeadroomUWolo > 0 && projectedRemaining < cfg.FeeHeadroomUWolo {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "PAYOUT_FEE_HEADROOM_TOO_LOW"
		response.Retryable = true
		response.Detail = fmt.Sprintf(
			"run would leave %s uwolo (%s wolo), below configured fee headroom %s uwolo (%s wolo)",
			response.ProjectedRemainingUWolo,
			response.ProjectedRemainingWolo,
			response.FeeHeadroomUWolo,
			response.FeeHeadroomWolo,
		)
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, response.FailureCode, response.Detail, true)
		return normalized, finalizeSettlementRunResponse(response), nil
	}
	if cfg.MinPayoutBalanceUWolo > 0 && projectedRemaining < cfg.MinPayoutBalanceUWolo {
		response.OK = false
		response.Status = "failed"
		response.FailureCode = "PAYOUT_RESERVE_FLOOR_HIT"
		response.Retryable = true
		response.Detail = fmt.Sprintf(
			"run would leave %s uwolo (%s wolo), below configured reserve floor %s uwolo (%s wolo)",
			response.ProjectedRemainingUWolo,
			response.ProjectedRemainingWolo,
			response.MinPayoutBalanceUWolo,
			response.MinPayoutBalanceWolo,
		)
		response.Payouts = markRunReadyPayoutsRefused(response.Payouts, response.FailureCode, response.Detail, true)
		return normalized, finalizeSettlementRunResponse(response), nil
	}

	if response.EstimatedFeeTotalUWolo != "" {
		estimatedFee, err := parseOptionalUWoloString(response.EstimatedFeeTotalUWolo)
		if err == nil && projectedRemaining < estimatedFee {
			response.Warnings = append(response.Warnings, fmt.Sprintf(
				"projected remaining balance %s uwolo is below estimated configured fees %s uwolo; fixed-fee runs may still fail during execution",
				response.ProjectedRemainingUWolo,
				response.EstimatedFeeTotalUWolo,
			))
		}
	}

	response.OK = true
	response.Status = "validated"
	response.Detail = "settlement run validated"
	return normalized, finalizeSettlementRunResponse(response), nil
}

func (cfg settlementConfig) preflightExecution(ctx context.Context, requestAmountUWolo string) (string, *settlementExecuteResponse) {
	health := cfg.buildHealthReport(ctx)
	if !health.OK {
		return "", &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   health.FailureCode,
			Retryable:     health.FailureCode == "RPC_UNREACHABLE",
			ChainID:       cfg.ChainID,
			SignerRole:    settlementSignerRole,
			SignerAddress: health.PayoutAddress,
			Detail:        health.Detail,
		}
	}

	if cfg.PayoutKeyName == "" {
		return "", &settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: "PAYOUT_SIGNER_UNCONFIGURED",
			Retryable:   false,
			ChainID:     cfg.ChainID,
			SignerRole:  settlementSignerRole,
			Detail:      "WOLO_SETTLEMENT_PAYOUT_KEY_NAME is required for payout execution",
		}
	}

	if health.PayoutAddress == "" {
		return "", &settlementExecuteResponse{
			OK:          false,
			Status:      "failed",
			FailureCode: "PAYOUT_SIGNER_UNAVAILABLE",
			Retryable:   false,
			ChainID:     cfg.ChainID,
			SignerRole:  settlementSignerRole,
			Detail:      "payout signer could not be resolved from the configured keyring",
		}
	}

	requestAmount, err := strconv.ParseUint(strings.TrimSpace(requestAmountUWolo), 10, 64)
	if err != nil {
		return "", &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   "INVALID_REQUEST",
			Retryable:     false,
			ChainID:       cfg.ChainID,
			SignerRole:    settlementSignerRole,
			SignerAddress: health.PayoutAddress,
			Detail:        "amount_uwolo must be a positive integer",
		}
	}
	balanceAmount, err := strconv.ParseUint(strings.TrimSpace(health.PayoutBalanceUWolo), 10, 64)
	if err != nil {
		return "", &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   "PAYOUT_BALANCE_LOOKUP_FAILED",
			Retryable:     true,
			ChainID:       cfg.ChainID,
			SignerRole:    settlementSignerRole,
			SignerAddress: health.PayoutAddress,
			Detail:        "payout signer balance could not be parsed",
		}
	}
	if code, detail, failed := cfg.checkPayoutCapacity(balanceAmount, requestAmount); failed {
		return "", &settlementExecuteResponse{
			OK:            false,
			Status:        "failed",
			FailureCode:   code,
			Retryable:     true,
			ChainID:       cfg.ChainID,
			SignerRole:    settlementSignerRole,
			SignerAddress: health.PayoutAddress,
			Detail:        detail,
		}
	}

	return health.PayoutAddress, nil
}

func (cfg settlementConfig) broadcastPayout(ctx context.Context, request normalizedSettlementRequest, signerAddress string) settlementExecuteResponse {
	ctx, cancel := context.WithTimeout(ctx, cfg.RequestTimeout)
	defer cancel()

	amountArg := request.AmountUWolo + cfg.BaseDenom
	args := []string{
		"tx", "bank", "send",
		cfg.PayoutKeyName,
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
		SignerRole:                 settlementSignerRole,
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
						response.Detail = "payout confirmed on WoloChain"
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
					response.Detail = "payout broadcast accepted; final confirmation check failed"
				} else {
					response.Detail = "payout broadcast accepted; final confirmation pending"
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

func extractJSONPayload(output []byte) []byte {
	start := bytes.IndexByte(output, '{')
	end := bytes.LastIndexByte(output, '}')
	if start == -1 || end == -1 || end < start {
		return nil
	}

	return bytes.TrimSpace(output[start : end+1])
}

func (cfg settlementConfig) waitForTxConfirmation(parent context.Context, txHash string) (*settlementLookupResponse, error) {
	deadline := time.Now().Add(cfg.ConfirmTimeout)
	for time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(parent, cfg.LookupTimeout)
		result, err := cfg.lookupSettlementTx(ctx, txHash, settlementLookupExpectations{})
		cancel()
		if err != nil {
			return nil, err
		}
		if result.OK && result.Found {
			return &result, nil
		}
		if result.FailureCode != "TX_NOT_FOUND" {
			return &result, nil
		}

		select {
		case <-parent.Done():
			return nil, parent.Err()
		case <-time.After(cfg.ConfirmInterval):
		}
	}

	return nil, nil
}

func (cfg settlementConfig) lookupSettlementTx(ctx context.Context, txHash string, expectations settlementLookupExpectations) (settlementLookupResponse, error) {
	normalizedHash := normalizeTxHash(txHash)
	if normalizedHash == "" {
		return settlementLookupResponse{
			OK:          false,
			FailureCode: "INVALID_TX_HASH",
			Detail:      "tx hash is required",
		}, nil
	}

	if !isHexHash(normalizedHash) {
		return settlementLookupResponse{
			OK:          false,
			FailureCode: "INVALID_TX_HASH",
			Detail:      "tx hash must be uppercase/lowercase hex",
		}, nil
	}

	ctx, cancel := context.WithTimeout(ctx, cfg.LookupTimeout)
	defer cancel()

	runtimeChainID, err := cfg.fetchRuntimeChainID(ctx)
	if err != nil {
		return settlementLookupResponse{
			OK:          false,
			FailureCode: "RPC_UNREACHABLE",
			Detail:      err.Error(),
		}, nil
	}

	if runtimeChainID != cfg.ChainID {
		return settlementLookupResponse{
			OK:          false,
			FailureCode: "CHAIN_ID_MISMATCH",
			Detail:      fmt.Sprintf("rpc reported %s, expected %s", runtimeChainID, cfg.ChainID),
		}, nil
	}

	payload := restTxLookupResponse{}
	statusCode, err := getJSON(ctx, cfg.txLookupURL(normalizedHash), &payload)
	if err != nil {
		return settlementLookupResponse{
			OK:                         false,
			FailureCode:                "LOOKUP_FAILED",
			Detail:                     err.Error(),
			CanonicalTxLookup:          cfg.txLookupURL(normalizedHash),
			CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(normalizedHash),
			CanonicalTxLookupInternal:  cfg.txLookupURL(normalizedHash),
			CanonicalTxLookupPublic:    cfg.publicTxLookupURL(normalizedHash),
		}, nil
	}
	if statusCode == http.StatusNotFound {
		return settlementLookupResponse{
			OK:                         false,
			FailureCode:                "TX_NOT_FOUND",
			Detail:                     "tx hash not found on WoloChain REST",
			CanonicalTxLookup:          cfg.txLookupURL(normalizedHash),
			CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(normalizedHash),
			CanonicalTxLookupInternal:  cfg.txLookupURL(normalizedHash),
			CanonicalTxLookupPublic:    cfg.publicTxLookupURL(normalizedHash),
		}, nil
	}

	transfers := extractSettlementTransfers(payload)
	matchedTransfer, matchedExpected := matchSettlementTransfer(transfers, expectations)
	kind := cfg.classifyTransferKind(transfers)
	if kind == "transfer" && cfg.PayoutAddress == "" && cfg.PayoutKeyName != "" {
		if payoutAddress, addrErr := cfg.resolvePayoutAddress(ctx); addrErr == nil && payoutAddress != "" {
			derived := cfg
			derived.PayoutAddress = payoutAddress
			kind = derived.classifyTransferKind(transfers)
		}
	}

	response := settlementLookupResponse{
		OK:                         true,
		Found:                      true,
		ChainID:                    cfg.ChainID,
		TxHash:                     payload.TxResponse.TxHash,
		TxSuccess:                  payload.TxResponse.Code == 0,
		Kind:                       kind,
		Height:                     payload.TxResponse.Height,
		Code:                       payload.TxResponse.Code,
		Codespace:                  payload.TxResponse.Codespace,
		Memo:                       payload.Tx.Body.Memo,
		RawLog:                     payload.TxResponse.RawLog,
		Timestamp:                  payload.TxResponse.Timestamp,
		CanonicalTxLookup:          cfg.txLookupURL(normalizedHash),
		CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(normalizedHash),
		CanonicalTxLookupInternal:  cfg.txLookupURL(normalizedHash),
		CanonicalTxLookupPublic:    cfg.publicTxLookupURL(normalizedHash),
		Transfers:                  transfers,
		MatchedExpected:            matchedExpected,
		MatchedTransfer:            matchedTransfer,
	}

	return response, nil
}

func (cfg settlementConfig) verifyEscrowDeposit(ctx context.Context, txHash, expectedSender, expectedAmountUWolo string) (settlementEscrowVerifyResponse, error) {
	response := settlementEscrowVerifyResponse{
		OK:                  false,
		EscrowAddress:       cfg.EscrowAddress,
		ExpectedSender:      strings.TrimSpace(expectedSender),
		ExpectedAmountUWolo: strings.TrimSpace(expectedAmountUWolo),
	}

	if strings.TrimSpace(cfg.EscrowAddress) == "" {
		response.FailureCode = "ESCROW_UNCONFIGURED"
		response.Detail = "WOLO_SETTLEMENT_ESCROW_ADDRESS must be set before escrow verification can be used"
		return response, nil
	}

	expectedSender = strings.TrimSpace(expectedSender)
	if expectedSender != "" && !isWoloAddress(expectedSender, cfg.AddressPrefix) {
		response.FailureCode = "INVALID_ADDRESS"
		response.Detail = "expected_sender must be a valid WOLO address"
		return response, nil
	}

	expectedAmountUWolo = strings.TrimSpace(expectedAmountUWolo)
	if expectedAmountUWolo != "" {
		if _, err := strconv.ParseUint(expectedAmountUWolo, 10, 64); err != nil {
			response.FailureCode = "INVALID_AMOUNT"
			response.Detail = "expected_amount_uwolo must be a positive integer"
			return response, nil
		}
	}

	lookup, err := cfg.lookupSettlementTx(ctx, txHash, settlementLookupExpectations{
		Sender:      expectedSender,
		Recipient:   cfg.EscrowAddress,
		AmountUWolo: expectedAmountUWolo,
	})
	if err != nil {
		return settlementEscrowVerifyResponse{}, err
	}

	response.Lookup = &lookup
	if !lookup.OK {
		response.FailureCode = firstNonEmpty(lookup.FailureCode, "LOOKUP_FAILED")
		response.Detail = lookup.Detail
		return response, nil
	}
	if !lookup.Found {
		response.FailureCode = "TX_NOT_FOUND"
		response.Detail = "tx hash not found on WoloChain REST"
		return response, nil
	}
	if lookup.Kind != "escrow_deposit" {
		response.FailureCode = "NOT_ESCROW_DEPOSIT"
		response.Detail = "tx did not deliver a WOLO transfer into the configured escrow address"
		return response, nil
	}

	response.DepositFound = true
	if lookup.MatchedExpected {
		response.OK = true
		response.Detail = "tx delivered a WOLO transfer into the configured escrow address"
		return response, nil
	}

	response.FailureCode = "ESCROW_DEPOSIT_MISMATCH"
	response.Detail = "tx reached the configured escrow address but did not match the expected sender and/or amount"
	return response, nil
}

func (cfg settlementConfig) listRecentEscrowDeposits(ctx context.Context, limit int, sender string) (settlementEscrowRecentResponse, error) {
	response := settlementEscrowRecentResponse{
		OK:            false,
		EscrowAddress: strings.TrimSpace(cfg.EscrowAddress),
		SenderFilter:  strings.TrimSpace(sender),
		Limit:         limit,
	}

	if response.EscrowAddress == "" {
		response.FailureCode = "ESCROW_UNCONFIGURED"
		response.Detail = "WOLO_SETTLEMENT_ESCROW_ADDRESS must be set before escrow discovery can be used"
		return response, nil
	}
	if limit <= 0 {
		response.FailureCode = "INVALID_LIMIT"
		response.Detail = "limit must be greater than zero"
		return response, nil
	}
	if limit > 100 {
		limit = 100
		response.Limit = limit
	}

	sender = strings.TrimSpace(sender)
	if sender != "" && !isWoloAddress(sender, cfg.AddressPrefix) {
		response.FailureCode = "INVALID_ADDRESS"
		response.Detail = "sender must be a valid WOLO address"
		return response, nil
	}

	ctx, cancel := context.WithTimeout(ctx, cfg.LookupTimeout)
	defer cancel()

	runtimeChainID, err := cfg.fetchRuntimeChainID(ctx)
	if err != nil {
		response.FailureCode = "RPC_UNREACHABLE"
		response.Detail = err.Error()
		return response, nil
	}
	if runtimeChainID != cfg.ChainID {
		response.FailureCode = "CHAIN_ID_MISMATCH"
		response.Detail = fmt.Sprintf("rpc reported %s, expected %s", runtimeChainID, cfg.ChainID)
		return response, nil
	}

	searchURL := cfg.escrowSearchURL(limit, sender)
	payload := restTxSearchResponse{}
	if _, err := getJSON(ctx, searchURL, &payload); err != nil {
		response.FailureCode = "LOOKUP_FAILED"
		response.Detail = err.Error()
		return response, nil
	}

	deposits := make([]settlementEscrowDepositItem, 0)
	for index, txResponse := range payload.TxResponses {
		if txResponse.Code != 0 {
			continue
		}

		memo := ""
		if index < len(payload.Txs) {
			memo = strings.TrimSpace(payload.Txs[index].Body.Memo)
		}
		transfers := extractSettlementTransfersFromLogsAndEvents(txResponse.Logs, txResponse.Events)
		for transferIndex, transfer := range transfers {
			if !strings.EqualFold(transfer.Recipient, cfg.EscrowAddress) || transfer.Denom != cfg.BaseDenom {
				continue
			}
			if sender != "" && !strings.EqualFold(transfer.Sender, sender) {
				continue
			}

			deposits = append(deposits, settlementEscrowDepositItem{
				TransferIndex:              transferIndex,
				TxHash:                     txResponse.TxHash,
				Height:                     txResponse.Height,
				Timestamp:                  txResponse.Timestamp,
				TxSuccess:                  txResponse.Code == 0,
				Sender:                     transfer.Sender,
				Recipient:                  transfer.Recipient,
				AmountUWolo:                transfer.Amount,
				AmountWolo:                 formatDisplayAmount(transfer.Amount),
				Memo:                       memo,
				CanonicalTxLookup:          cfg.txLookupURL(txResponse.TxHash),
				CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(txResponse.TxHash),
				CanonicalTxLookupInternal:  cfg.txLookupURL(txResponse.TxHash),
				CanonicalTxLookupPublic:    cfg.publicTxLookupURL(txResponse.TxHash),
			})
			if len(deposits) >= limit {
				break
			}
		}
		if len(deposits) >= limit {
			break
		}
	}

	response.OK = true
	response.Count = len(deposits)
	response.Deposits = deposits
	return response, nil
}

func (cfg settlementConfig) escrowSearchURL(limit int, sender string) string {
	query := fmt.Sprintf("transfer.recipient='%s'", strings.TrimSpace(cfg.EscrowAddress))
	if trimmedSender := strings.TrimSpace(sender); trimmedSender != "" {
		query += fmt.Sprintf(" AND transfer.sender='%s'", trimmedSender)
	}

	values := url.Values{}
	values.Set("query", query)
	values.Set("pagination.limit", strconv.Itoa(limit))
	values.Set("order_by", "ORDER_BY_DESC")

	return strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/tx/v1beta1/txs?" + values.Encode()
}

func (cfg settlementConfig) classifyTransferKind(transfers []settlementTransfer) string {
	for _, transfer := range transfers {
		if cfg.EscrowAddress != "" &&
			strings.EqualFold(transfer.Recipient, cfg.EscrowAddress) &&
			transfer.Denom == cfg.BaseDenom {
			return "escrow_deposit"
		}
		if cfg.PayoutAddress != "" &&
			strings.EqualFold(transfer.Sender, cfg.PayoutAddress) &&
			transfer.Denom == cfg.BaseDenom {
			return "payout"
		}
	}

	if len(transfers) > 0 {
		return "transfer"
	}

	return "unknown"
}

func (cfg settlementConfig) resolvePayoutAddress(ctx context.Context) (string, error) {
	if cfg.PayoutKeyName == "" {
		return "", nil
	}

	args := []string{
		"keys", "show", cfg.PayoutKeyName,
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
		return "", fmt.Errorf("could not resolve payout signer %q: %s", cfg.PayoutKeyName, detail)
	}

	address := strings.TrimSpace(string(output))
	if !isWoloAddress(address, cfg.AddressPrefix) {
		return "", fmt.Errorf("resolved payout signer %q to non-wolo address %q", cfg.PayoutKeyName, address)
	}

	if cfg.PayoutAddress != "" && !strings.EqualFold(address, cfg.PayoutAddress) {
		return "", fmt.Errorf("payout signer resolved to %s, expected %s", address, cfg.PayoutAddress)
	}

	return address, nil
}

func (cfg settlementConfig) fetchRuntimeChainID(ctx context.Context) (string, error) {
	payload := tenderStatusResponse{}
	if _, err := getJSON(ctx, strings.TrimRight(cfg.RPCHTTP, "/")+"/status", &payload); err != nil {
		return "", err
	}

	chainID := strings.TrimSpace(payload.Result.NodeInfo.Network)
	if chainID == "" {
		return "", errors.New("rpc status returned no chain id")
	}

	return chainID, nil
}

func (cfg settlementConfig) validateRESTInvariants(ctx context.Context) error {
	nodeInfo := restNodeInfoResponse{}
	if _, err := getJSON(ctx, strings.TrimRight(cfg.RESTURL, "/")+"/cosmos/base/tendermint/v1beta1/node_info", &nodeInfo); err != nil {
		return fmt.Errorf("rest node_info failed: %w", err)
	}
	if strings.TrimSpace(nodeInfo.DefaultNodeInfo.Network) != cfg.ChainID {
		return fmt.Errorf("rest node_info reported %s, expected %s", nodeInfo.DefaultNodeInfo.Network, cfg.ChainID)
	}

	denom := restDenomMetadataResponse{}
	if _, err := getJSON(ctx, strings.TrimRight(cfg.RESTURL, "/")+"/cosmos/bank/v1beta1/denoms_metadata/"+cfg.BaseDenom, &denom); err != nil {
		return fmt.Errorf("rest denom metadata failed: %w", err)
	}
	if denom.Metadata.Base != cfg.BaseDenom || denom.Metadata.Display != cfg.DisplayDenom {
		return fmt.Errorf("rest denom metadata drift: base=%s display=%s", denom.Metadata.Base, denom.Metadata.Display)
	}

	staking := restStakingParamsResponse{}
	if _, err := getJSON(ctx, strings.TrimRight(cfg.RESTURL, "/")+"/cosmos/staking/v1beta1/params", &staking); err != nil {
		return fmt.Errorf("rest staking params failed: %w", err)
	}
	if staking.Params.BondDenom != cfg.BaseDenom {
		return fmt.Errorf("staking bond denom drift: %s", staking.Params.BondDenom)
	}

	mint := restMintParamsResponse{}
	if _, err := getJSON(ctx, strings.TrimRight(cfg.RESTURL, "/")+"/cosmos/mint/v1beta1/params", &mint); err != nil {
		return fmt.Errorf("rest mint params failed: %w", err)
	}
	if mint.Params.MintDenom != cfg.BaseDenom {
		return fmt.Errorf("mint denom drift: %s", mint.Params.MintDenom)
	}

	return nil
}

func (cfg settlementConfig) fetchAccountBalanceUWolo(ctx context.Context, address string) (uint64, error) {
	payload := restBalancesResponse{}
	target := strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/bank/v1beta1/balances/" + url.PathEscape(address)
	if _, err := getJSON(ctx, target, &payload); err != nil {
		return 0, fmt.Errorf("rest balance lookup failed for %s: %w", address, err)
	}

	for _, balance := range payload.Balances {
		if balance.Denom != cfg.BaseDenom {
			continue
		}
		amount, err := strconv.ParseUint(strings.TrimSpace(balance.Amount), 10, 64)
		if err != nil {
			return 0, fmt.Errorf("rest balance lookup returned invalid %s amount %q", cfg.BaseDenom, balance.Amount)
		}
		return amount, nil
	}

	return 0, nil
}

func (cfg settlementConfig) checkReserveHealth(balanceUWolo uint64) (string, string, bool) {
	if cfg.FeeHeadroomUWolo > 0 && balanceUWolo < cfg.FeeHeadroomUWolo {
		return "PAYOUT_FEE_HEADROOM_TOO_LOW",
			fmt.Sprintf(
				"payout signer balance %s uwolo (%s wolo) is below configured fee headroom %s uwolo (%s wolo)",
				strconv.FormatUint(balanceUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(balanceUWolo, 10)),
				strconv.FormatUint(cfg.FeeHeadroomUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(cfg.FeeHeadroomUWolo, 10)),
			),
			true
	}
	if cfg.MinPayoutBalanceUWolo > 0 && balanceUWolo < cfg.MinPayoutBalanceUWolo {
		return "PAYOUT_RESERVE_FLOOR_HIT",
			fmt.Sprintf(
				"payout signer balance %s uwolo (%s wolo) is below configured reserve floor %s uwolo (%s wolo)",
				strconv.FormatUint(balanceUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(balanceUWolo, 10)),
				strconv.FormatUint(cfg.MinPayoutBalanceUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(cfg.MinPayoutBalanceUWolo, 10)),
			),
			true
	}

	return "", "", false
}

func (cfg settlementConfig) checkPayoutCapacity(balanceUWolo, requestUWolo uint64) (string, string, bool) {
	if balanceUWolo < requestUWolo {
		return "PAYOUT_BALANCE_TOO_LOW",
			fmt.Sprintf(
				"payout signer balance %s uwolo (%s wolo) is below requested payout %s uwolo (%s wolo)",
				strconv.FormatUint(balanceUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(balanceUWolo, 10)),
				strconv.FormatUint(requestUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(requestUWolo, 10)),
			),
			true
	}

	remaining := balanceUWolo - requestUWolo
	if cfg.FeeHeadroomUWolo > 0 && remaining < cfg.FeeHeadroomUWolo {
		return "PAYOUT_FEE_HEADROOM_TOO_LOW",
			fmt.Sprintf(
				"payout would leave %s uwolo (%s wolo), below configured fee headroom %s uwolo (%s wolo)",
				strconv.FormatUint(remaining, 10),
				formatDisplayAmount(strconv.FormatUint(remaining, 10)),
				strconv.FormatUint(cfg.FeeHeadroomUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(cfg.FeeHeadroomUWolo, 10)),
			),
			true
	}
	if cfg.MinPayoutBalanceUWolo > 0 && remaining < cfg.MinPayoutBalanceUWolo {
		return "PAYOUT_RESERVE_FLOOR_HIT",
			fmt.Sprintf(
				"payout would leave %s uwolo (%s wolo), below configured reserve floor %s uwolo (%s wolo)",
				strconv.FormatUint(remaining, 10),
				formatDisplayAmount(strconv.FormatUint(remaining, 10)),
				strconv.FormatUint(cfg.MinPayoutBalanceUWolo, 10),
				formatDisplayAmount(strconv.FormatUint(cfg.MinPayoutBalanceUWolo, 10)),
			),
			true
	}

	return "", "", false
}

func (cfg settlementConfig) withRequestLock(requestID string, fn func() (settlementExecuteResponse, error)) (settlementExecuteResponse, error) {
	lockPath := cfg.requestLockPath(requestID)
	if err := os.MkdirAll(filepath.Dir(lockPath), 0o755); err != nil {
		return settlementExecuteResponse{}, err
	}

	lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			info, statErr := os.Stat(lockPath)
			if statErr == nil && time.Since(info.ModTime()) > cfg.RequestLockTTL {
				_ = os.Remove(lockPath)
				return cfg.withRequestLock(requestID, fn)
			}
			return settlementExecuteResponse{
				OK:          false,
				Status:      "failed",
				FailureCode: "REQUEST_IN_PROGRESS",
				Retryable:   true,
				RequestID:   requestID,
				ChainID:     cfg.ChainID,
				SignerRole:  settlementSignerRole,
				Detail:      "another settlement attempt with this request id is already running",
			}, nil
		}
		return settlementExecuteResponse{}, err
	}

	_, _ = lockFile.WriteString(time.Now().UTC().Format(time.RFC3339Nano))
	_ = lockFile.Close()
	defer os.Remove(lockPath)

	return fn()
}

func (cfg settlementConfig) withRunLock(runID string, fn func() (settlementRunResponse, error)) (settlementRunResponse, error) {
	lockPath := cfg.runLockPath(runID)
	if err := os.MkdirAll(filepath.Dir(lockPath), 0o755); err != nil {
		return settlementRunResponse{}, err
	}

	lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			info, statErr := os.Stat(lockPath)
			if statErr == nil && time.Since(info.ModTime()) > cfg.RequestLockTTL {
				_ = os.Remove(lockPath)
				return cfg.withRunLock(runID, fn)
			}
			return settlementRunResponse{
				OK:              false,
				DryRun:          false,
				Status:          "failed",
				FailureCode:     "RUN_IN_PROGRESS",
				Retryable:       true,
				SettlementRunID: runID,
				Detail:          "another settlement run attempt with this settlement_run_id is already running",
			}, nil
		}
		return settlementRunResponse{}, err
	}

	_, _ = lockFile.WriteString(time.Now().UTC().Format(time.RFC3339Nano))
	_ = lockFile.Close()
	defer os.Remove(lockPath)

	return fn()
}

func (cfg settlementConfig) requestRecordPath(requestID string) string {
	return filepath.Join(cfg.StateDir, "requests", requestID+".json")
}

func (cfg settlementConfig) requestLockPath(requestID string) string {
	return filepath.Join(cfg.StateDir, "locks", requestID+".lock")
}

func (cfg settlementConfig) runRecordPath(runID string) string {
	return filepath.Join(cfg.StateDir, "runs", runID+".json")
}

func (cfg settlementConfig) runLockPath(runID string) string {
	return filepath.Join(cfg.StateDir, "run-locks", runID+".lock")
}

func (cfg settlementConfig) listRecentSettlementRecords(limit int, statusFilter, failureCodeFilter string) ([]settlementRecentItem, error) {
	requestsDir := filepath.Join(cfg.StateDir, "requests")
	entries, err := os.ReadDir(requestsDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return []settlementRecentItem{}, nil
		}
		return nil, err
	}

	items := make([]settlementRecentItem, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}

		recordPath := filepath.Join(requestsDir, entry.Name())
		record, err := readSettlementStoredResult(recordPath)
		if err != nil {
			return nil, fmt.Errorf("read settlement record %s: %w", recordPath, err)
		}

		if !matchesSettlementStatusFilter(record.Response, statusFilter) {
			continue
		}
		if failureCodeFilter != "" && !strings.EqualFold(strings.TrimSpace(record.Response.FailureCode), failureCodeFilter) {
			continue
		}

		summary := summarizeSettlementStoredResult(record)
		items = append(items, settlementRecentItem{
			RequestID:   record.Request.RequestID,
			RequestPath: recordPath,
			UpdatedAt:   record.UpdatedAt,
			Summary:     summary,
			Record:      record,
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

func (cfg settlementConfig) listRecentSettlementRuns(limit int, statusFilter, failureCodeFilter string) ([]settlementRunRecentItem, error) {
	runsDir := filepath.Join(cfg.StateDir, "runs")
	entries, err := os.ReadDir(runsDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return []settlementRunRecentItem{}, nil
		}
		return nil, err
	}

	items := make([]settlementRunRecentItem, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}

		recordPath := filepath.Join(runsDir, entry.Name())
		record, err := readSettlementRunStoredResult(recordPath)
		if err != nil {
			return nil, fmt.Errorf("read settlement run record %s: %w", recordPath, err)
		}

		if statusFilter != "" && statusFilter != "all" && !strings.EqualFold(record.Response.Status, statusFilter) {
			continue
		}
		if failureCodeFilter != "" && !strings.EqualFold(strings.TrimSpace(record.Response.FailureCode), failureCodeFilter) {
			continue
		}

		summary := summarizeSettlementRunStoredResult(record)
		items = append(items, settlementRunRecentItem{
			SettlementRunID: record.Request.SettlementRunID,
			RunPath:         recordPath,
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

func (cfg settlementConfig) txLookupURL(txHash string) string {
	if txHash == "" {
		return strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/tx/v1beta1/txs/{tx_hash}"
	}

	return strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/tx/v1beta1/txs/" + url.PathEscape(txHash)
}

func (cfg settlementConfig) preferredTxLookupURL(txHash string) string {
	publicURL := cfg.publicTxLookupURL(txHash)
	if publicURL != "" {
		return publicURL
	}

	return cfg.txLookupURL(txHash)
}

func (cfg settlementConfig) publicTxLookupURL(txHash string) string {
	if strings.TrimSpace(cfg.PublicRESTURL) == "" {
		return ""
	}
	if txHash == "" {
		return strings.TrimRight(cfg.PublicRESTURL, "/") + "/cosmos/tx/v1beta1/txs/{tx_hash}"
	}

	return strings.TrimRight(cfg.PublicRESTURL, "/") + "/cosmos/tx/v1beta1/txs/" + url.PathEscape(txHash)
}

func normalizeSettlementRequest(request settlementExecuteRequest) (normalizedSettlementRequest, error) {
	requestID := strings.TrimSpace(request.RequestID)
	if !settlementRequestIDPattern.MatchString(requestID) {
		return normalizedSettlementRequest{}, errors.New("request_id must be 3-128 chars using letters, numbers, dot, underscore, colon, or dash")
	}

	toAddress := strings.TrimSpace(request.ToAddress)
	if !isWoloAddress(toAddress, settlementCanonicalPrefix) {
		return normalizedSettlementRequest{}, errors.New("to_address must be a valid wolo address")
	}

	amountUWolo, err := normalizeAmountUWolo(request.AmountUWolo, request.AmountWolo)
	if err != nil {
		return normalizedSettlementRequest{}, err
	}

	memo := strings.TrimSpace(request.Memo)
	if len(memo) > 180 {
		memo = memo[:180]
	}

	return normalizedSettlementRequest{
		RequestID:   requestID,
		ToAddress:   toAddress,
		AmountUWolo: amountUWolo,
		Memo:        memo,
	}, nil
}

func normalizeAmountUWolo(amountUWolo string, amountWolo int64) (string, error) {
	trimmed := strings.TrimSpace(amountUWolo)
	if trimmed != "" && amountWolo > 0 {
		return "", errors.New("provide either amount_uwolo or amount_wolo, not both")
	}
	if trimmed == "" && amountWolo <= 0 {
		return "", errors.New("amount_uwolo or amount_wolo is required")
	}

	if trimmed != "" {
		if _, err := strconv.ParseUint(trimmed, 10, 64); err != nil {
			return "", errors.New("amount_uwolo must be a positive integer")
		}
		if trimmed == "0" {
			return "", errors.New("amount_uwolo must be greater than zero")
		}
		return trimmed, nil
	}

	if amountWolo <= 0 {
		return "", errors.New("amount_wolo must be greater than zero")
	}

	return strconv.FormatInt(amountWolo*1_000_000, 10), nil
}

func formatDisplayAmount(amountUWolo string) string {
	if amountUWolo == "" {
		return ""
	}

	parsed, err := strconv.ParseInt(amountUWolo, 10, 64)
	if err != nil {
		return ""
	}

	whole := parsed / 1_000_000
	frac := parsed % 1_000_000
	return fmt.Sprintf("%d.%06d", whole, frac)
}

func hashSettlementRequest(request normalizedSettlementRequest, signerAddress string) string {
	blob := struct {
		Request normalizedSettlementRequest `json:"request"`
		Signer  string                      `json:"signer"`
	}{
		Request: request,
		Signer:  signerAddress,
	}

	data, _ := json.Marshal(blob)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func hashSettlementRunRequest(request normalizedSettlementRunRequest) string {
	data, _ := json.Marshal(request)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func prepareSettlementRunRequest(request settlementRunRequest) (normalizedSettlementRunRequest, settlementRunResponse) {
	runID := strings.TrimSpace(request.SettlementRunID)
	sourceApp := strings.TrimSpace(request.SourceApp)
	sourceEventID := strings.TrimSpace(request.SourceEventID)
	note := strings.TrimSpace(request.Note)
	memo := strings.TrimSpace(request.Memo)

	response := settlementRunResponse{
		OK:              false,
		DryRun:          true,
		Status:          "failed",
		SettlementRunID: runID,
		SourceApp:       sourceApp,
		SourceEventID:   sourceEventID,
		Note:            note,
		Memo:            memo,
	}

	validationErrors := make([]string, 0)
	if err := validateSettlementRunID(runID); err != nil {
		validationErrors = append(validationErrors, err.Error())
	}
	if normalizedSourceApp, err := normalizeSettlementRunMetadataID("source_app", sourceApp, 64, settlementRequestIDPattern); err != nil {
		validationErrors = append(validationErrors, err.Error())
	} else {
		sourceApp = normalizedSourceApp
	}
	if normalizedSourceEventID, err := normalizeSettlementRunMetadataID("source_event_id", sourceEventID, 128, settlementSourceEventPattern); err != nil {
		validationErrors = append(validationErrors, err.Error())
	} else {
		sourceEventID = normalizedSourceEventID
	}
	if len(note) > 280 {
		note = note[:280]
	}
	if len(memo) > 180 {
		memo = memo[:180]
	}

	response.SourceApp = sourceApp
	response.SourceEventID = sourceEventID
	response.Note = note
	response.Memo = memo

	if len(request.Payouts) == 0 {
		validationErrors = append(validationErrors, "payouts must contain at least one payout")
	}
	if len(request.Payouts) > settlementMaxRunPayouts {
		validationErrors = append(validationErrors, fmt.Sprintf("payouts may contain at most %d line items", settlementMaxRunPayouts))
	}
	if len(validationErrors) > 0 {
		response.FailureCode = "INVALID_RUN"
		response.Detail = strings.Join(validationErrors, "; ")
		return normalizedSettlementRunRequest{}, response
	}

	normalized := normalizedSettlementRunRequest{
		SettlementRunID: runID,
		SourceApp:       sourceApp,
		SourceEventID:   sourceEventID,
		Note:            note,
		Memo:            memo,
		Payouts:         make([]normalizedSettlementPayout, 0, len(request.Payouts)),
	}

	response.Payouts = make([]settlementRunPayoutResult, len(request.Payouts))
	response.RequestedPayoutCount = len(request.Payouts)

	seenRequestIDs := map[string]struct{}{}
	seenPayoutKeys := map[string][]int{}
	var invalid bool
	var totalRequested uint64

	for index, payout := range request.Payouts {
		requestID := strings.TrimSpace(payout.RequestID)
		if requestID == "" {
			requestID = deriveSettlementRunRequestID(runID, index)
		}
		itemMemo := strings.TrimSpace(payout.Memo)
		if itemMemo == "" {
			itemMemo = memo
		}

		itemResult := settlementRunPayoutResult{
			Index:      index,
			RequestID:  requestID,
			Attempted:  false,
			Status:     "failed",
			Outcome:    "invalid",
			SignerRole: settlementSignerRole,
			Memo:       itemMemo,
		}

		normalizedPayout, err := normalizeSettlementRequest(settlementExecuteRequest{
			RequestID:   requestID,
			ToAddress:   payout.ToAddress,
			AmountUWolo: payout.AmountUWolo,
			AmountWolo:  payout.AmountWolo,
			Memo:        itemMemo,
		})
		if err != nil {
			itemResult.FailureCode = "INVALID_PAYOUT"
			itemResult.Detail = err.Error()
			response.Payouts[index] = itemResult
			invalid = true
			continue
		}
		if _, exists := seenRequestIDs[normalizedPayout.RequestID]; exists {
			itemResult.ToAddress = normalizedPayout.ToAddress
			itemResult.AmountUWolo = normalizedPayout.AmountUWolo
			itemResult.AmountWolo = formatDisplayAmount(normalizedPayout.AmountUWolo)
			itemResult.FailureCode = "DUPLICATE_REQUEST_ID"
			itemResult.Detail = fmt.Sprintf("request_id %q appears more than once in this settlement run", normalizedPayout.RequestID)
			response.Payouts[index] = itemResult
			invalid = true
			continue
		}

		seenRequestIDs[normalizedPayout.RequestID] = struct{}{}
		normalizedRunPayout := normalizedSettlementPayout{
			Index:       index,
			RequestID:   normalizedPayout.RequestID,
			ToAddress:   normalizedPayout.ToAddress,
			AmountUWolo: normalizedPayout.AmountUWolo,
			Memo:        normalizedPayout.Memo,
		}
		normalized.Payouts = append(normalized.Payouts, normalizedRunPayout)

		amountUWolo, err := parseOptionalUWoloString(normalizedPayout.AmountUWolo)
		if err == nil {
			totalRequested += amountUWolo
		}
		itemResult.OK = true
		itemResult.Status = "validated"
		itemResult.Outcome = "ready"
		itemResult.ToAddress = normalizedPayout.ToAddress
		itemResult.AmountUWolo = normalizedPayout.AmountUWolo
		itemResult.AmountWolo = formatDisplayAmount(normalizedPayout.AmountUWolo)
		itemResult.Memo = normalizedPayout.Memo
		response.Payouts[index] = itemResult

		payoutKey := normalizedPayout.ToAddress + "|" + normalizedPayout.AmountUWolo + "|" + normalizedPayout.Memo
		seenPayoutKeys[payoutKey] = append(seenPayoutKeys[payoutKey], index)
	}

	response.RequestedTotalUWolo = strconv.FormatUint(totalRequested, 10)
	response.RequestedTotalWolo = formatDisplayAmount(response.RequestedTotalUWolo)

	for payoutKey, indexes := range seenPayoutKeys {
		if len(indexes) < 2 {
			continue
		}
		parts := strings.SplitN(payoutKey, "|", 3)
		warning := fmt.Sprintf("duplicate payout line items detected for %s %s uwolo (%d entries)", parts[0], parts[1], len(indexes))
		response.Warnings = append(response.Warnings, warning)
		for _, index := range indexes {
			response.Payouts[index].Warnings = append(response.Payouts[index].Warnings, warning)
		}
	}

	if invalid {
		response.FailureCode = "INVALID_RUN"
		response.Detail = "one or more payout lines are invalid"
	}

	return normalized, response
}

func sameSettlementRequest(left, right normalizedSettlementRequest) bool {
	return left.RequestID == right.RequestID &&
		left.ToAddress == right.ToAddress &&
		left.AmountUWolo == right.AmountUWolo &&
		left.Memo == right.Memo
}

func settlementRunPayoutResultFromExecuteResponse(payout normalizedSettlementPayout, response settlementExecuteResponse) settlementRunPayoutResult {
	return settlementRunPayoutResult{
		Index:                      payout.Index,
		RequestID:                  response.RequestID,
		Attempted:                  true,
		OK:                         response.OK,
		Status:                     response.Status,
		Outcome:                    deriveSettlementOutcome(response),
		FailureCode:                response.FailureCode,
		Retryable:                  response.Retryable,
		IdempotentReplay:           response.IdempotentReplay,
		SignerRole:                 response.SignerRole,
		SignerAddress:              response.SignerAddress,
		ToAddress:                  response.ToAddress,
		AmountUWolo:                response.AmountUWolo,
		AmountWolo:                 response.AmountWolo,
		Memo:                       payout.Memo,
		TxHash:                     response.TxHash,
		Detail:                     response.Detail,
		CanonicalTxLookup:          response.CanonicalTxLookup,
		CanonicalTxLookupPreferred: response.CanonicalTxLookupPreferred,
		CanonicalTxLookupInternal:  response.CanonicalTxLookupInternal,
		CanonicalTxLookupPublic:    response.CanonicalTxLookupPublic,
	}
}

func finalizeSettlementRunResponse(response settlementRunResponse) settlementRunResponse {
	var (
		requestedTotal uint64
		executedTotal  uint64
		confirmedTotal uint64
		acceptedTotal  uint64
		refusedTotal   uint64
		rejectedTotal  uint64
	)

	if response.RequestedPayoutCount == 0 {
		response.RequestedPayoutCount = len(response.Payouts)
	}
	if response.RequestedTotalUWolo == "" {
		for _, payout := range response.Payouts {
			if amount, err := parseOptionalUWoloString(payout.AmountUWolo); err == nil {
				requestedTotal += amount
			}
		}
		response.RequestedTotalUWolo = strconv.FormatUint(requestedTotal, 10)
		response.RequestedTotalWolo = formatDisplayAmount(response.RequestedTotalUWolo)
	}

	for _, payout := range response.Payouts {
		amount, err := parseOptionalUWoloString(payout.AmountUWolo)
		if err != nil {
			continue
		}
		switch payout.Status {
		case "confirmed":
			response.ConfirmedPayoutCount++
			response.ExecutedPayoutCount++
			executedTotal += amount
			confirmedTotal += amount
		case "accepted":
			response.AcceptedPayoutCount++
			response.ExecutedPayoutCount++
			executedTotal += amount
			acceptedTotal += amount
		}

		switch payout.Outcome {
		case "refused", "invalid":
			response.RefusedPayoutCount++
			refusedTotal += amount
		case "rejected":
			response.RejectedPayoutCount++
			rejectedTotal += amount
		}
		if payout.IdempotentReplay {
			response.ReplayPayoutCount++
		}
		if payout.Retryable {
			response.Retryable = true
		}
	}

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
	if response.Status == "" {
		response.Status, response.OK, response.FailureCode = deriveSettlementRunStatus(response)
	}

	return response
}

func deriveSettlementRunStatus(response settlementRunResponse) (string, bool, string) {
	if response.FailureCode == "INVALID_RUN" {
		return "failed", false, response.FailureCode
	}
	if response.ConfirmedPayoutCount == response.RequestedPayoutCount && response.RequestedPayoutCount > 0 {
		return "confirmed", true, ""
	}
	if response.ExecutedPayoutCount == response.RequestedPayoutCount && response.RequestedPayoutCount > 0 {
		return "accepted", true, ""
	}
	if response.ExecutedPayoutCount > 0 && (response.RefusedPayoutCount > 0 || response.RejectedPayoutCount > 0) {
		return "partial", false, firstNonEmpty(response.FailureCode, firstSettlementRunFailureCode(response.Payouts), "RUN_PARTIAL_FAILURE")
	}
	if response.ExecutedPayoutCount == 0 && (response.RefusedPayoutCount > 0 || response.RejectedPayoutCount > 0) {
		return "failed", false, firstNonEmpty(response.FailureCode, firstSettlementRunFailureCode(response.Payouts), "RUN_FAILED")
	}

	return strings.TrimSpace(response.Status), response.OK, response.FailureCode
}

func firstSettlementRunFailureCode(payouts []settlementRunPayoutResult) string {
	for _, payout := range payouts {
		if strings.TrimSpace(payout.FailureCode) != "" {
			return payout.FailureCode
		}
	}

	return ""
}

func settlementRunExecutionDetail(response settlementRunResponse) string {
	switch strings.TrimSpace(response.Status) {
	case "confirmed":
		return fmt.Sprintf("all %d payouts confirmed on WoloChain", response.ConfirmedPayoutCount)
	case "accepted":
		return fmt.Sprintf("all %d payouts broadcast accepted; final confirmation is still pending for at least one payout", response.ExecutedPayoutCount)
	case "partial":
		return fmt.Sprintf("%d of %d payouts executed; inspect per-recipient results for the remaining failures", response.ExecutedPayoutCount, response.RequestedPayoutCount)
	case "failed":
		if detail := firstSettlementRunFailureDetail(response.Payouts); detail != "" {
			return detail
		}
		return "no payouts executed successfully"
	default:
		return strings.TrimSpace(response.Detail)
	}
}

func firstSettlementRunFailureDetail(payouts []settlementRunPayoutResult) string {
	for _, payout := range payouts {
		if strings.TrimSpace(payout.Detail) != "" && strings.TrimSpace(payout.FailureCode) != "" {
			return payout.Detail
		}
	}

	return ""
}

func runResponseHasReadyPayouts(response settlementRunResponse) bool {
	for _, payout := range response.Payouts {
		if payout.Outcome == "ready" {
			return true
		}
	}

	return false
}

func runResponseHasRetryablePayouts(response settlementRunResponse) bool {
	for _, payout := range response.Payouts {
		if payout.Retryable {
			return true
		}
	}

	return false
}

func settlementRunResponseIsFinal(response settlementRunResponse) bool {
	if runResponseHasRetryablePayouts(response) {
		return false
	}

	return response.OK || strings.EqualFold(strings.TrimSpace(response.Status), "failed") || strings.EqualFold(strings.TrimSpace(response.Status), "partial")
}

func markRunReadyPayoutsRefused(payouts []settlementRunPayoutResult, failureCode, detail string, retryable bool) []settlementRunPayoutResult {
	out := make([]settlementRunPayoutResult, len(payouts))
	copy(out, payouts)
	for index, payout := range out {
		if payout.Outcome != "ready" {
			continue
		}
		payout.OK = false
		payout.Status = "failed"
		payout.Outcome = "refused"
		payout.FailureCode = failureCode
		payout.Retryable = retryable
		payout.Detail = detail
		out[index] = payout
	}

	return out
}

func validateSettlementRunID(runID string) error {
	if !settlementRequestIDPattern.MatchString(runID) {
		return errors.New("settlement_run_id must be 3-128 chars using letters, numbers, dot, underscore, colon, or dash")
	}
	if len(runID) > 96 {
		return errors.New("settlement_run_id must be 96 chars or fewer so derived payout request ids remain stable")
	}

	return nil
}

func normalizeSettlementRunMetadataID(fieldName, value string, maxLen int, pattern *regexp.Regexp) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", nil
	}
	if len(value) > maxLen {
		return "", fmt.Errorf("%s must be %d chars or fewer", fieldName, maxLen)
	}
	if !pattern.MatchString(value) {
		return "", fmt.Errorf("%s uses unsupported characters", fieldName)
	}

	return value, nil
}

func deriveSettlementRunRequestID(runID string, index int) string {
	return fmt.Sprintf("%s:item-%03d", runID, index+1)
}

func parseOptionalUWoloString(value string) (uint64, error) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return 0, nil
	}

	return strconv.ParseUint(trimmed, 10, 64)
}

func formatOptionalRunAmount(amount uint64) string {
	if amount == 0 {
		return ""
	}

	return strconv.FormatUint(amount, 10)
}

func formatOptionalRunDisplayAmount(amount uint64) string {
	if amount == 0 {
		return ""
	}

	return formatDisplayAmount(strconv.FormatUint(amount, 10))
}

func summarizeSettlementStoredResult(record settlementStoredResult) settlementRecordSummary {
	response := record.Response
	canonicalInternal := firstNonEmpty(response.CanonicalTxLookupInternal, response.CanonicalTxLookup)
	canonicalPreferred := firstNonEmpty(response.CanonicalTxLookupPreferred, response.CanonicalTxLookupPublic, canonicalInternal)

	return settlementRecordSummary{
		RequestID:                  firstNonEmpty(record.Request.RequestID, response.RequestID),
		UpdatedAt:                  record.UpdatedAt,
		Outcome:                    deriveSettlementOutcome(response),
		Status:                     response.Status,
		FailureCode:                response.FailureCode,
		Retryable:                  response.Retryable,
		IdempotentReplay:           response.IdempotentReplay,
		SignerRole:                 response.SignerRole,
		SignerAddress:              response.SignerAddress,
		ToAddress:                  firstNonEmpty(response.ToAddress, record.Request.ToAddress),
		AmountUWolo:                firstNonEmpty(response.AmountUWolo, record.Request.AmountUWolo),
		AmountWolo:                 firstNonEmpty(response.AmountWolo, formatDisplayAmount(record.Request.AmountUWolo)),
		TxHash:                     response.TxHash,
		Detail:                     response.Detail,
		CanonicalTxLookup:          response.CanonicalTxLookup,
		CanonicalTxLookupPreferred: canonicalPreferred,
		CanonicalTxLookupInternal:  canonicalInternal,
		CanonicalTxLookupPublic:    response.CanonicalTxLookupPublic,
	}
}

func summarizeSettlementRecentItems(limit int, statusFilter, failureCodeFilter string, items []settlementRecentItem) settlementRecentSummary {
	summary := settlementRecentSummary{
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
		case "accepted":
			summary.AcceptedCount++
		case "confirmed":
			summary.ConfirmedCount++
		}
		switch item.Summary.Outcome {
		case "refused":
			summary.RefusedCount++
		case "rejected":
			summary.RejectedCount++
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

func summarizeSettlementRunStoredResult(record settlementRunStoredResult) settlementRunSummary {
	response := record.Response
	signerRole, signerAddress := summarizeSettlementRunSigner(response.Payouts)
	return settlementRunSummary{
		SettlementRunID:      record.Request.SettlementRunID,
		UpdatedAt:            record.UpdatedAt,
		Status:               response.Status,
		FailureCode:          response.FailureCode,
		Retryable:            response.Retryable,
		IdempotentReplay:     response.IdempotentReplay,
		SourceApp:            record.Request.SourceApp,
		SourceEventID:        record.Request.SourceEventID,
		Note:                 record.Request.Note,
		Memo:                 record.Request.Memo,
		SignerRole:           signerRole,
		SignerAddress:        signerAddress,
		RequestedPayoutCount: response.RequestedPayoutCount,
		ExecutedPayoutCount:  response.ExecutedPayoutCount,
		ConfirmedPayoutCount: response.ConfirmedPayoutCount,
		AcceptedPayoutCount:  response.AcceptedPayoutCount,
		RefusedPayoutCount:   response.RefusedPayoutCount,
		RejectedPayoutCount:  response.RejectedPayoutCount,
		ReplayPayoutCount:    response.ReplayPayoutCount,
		RequestedTotalUWolo:  response.RequestedTotalUWolo,
		RequestedTotalWolo:   response.RequestedTotalWolo,
		ExecutedTotalUWolo:   response.ExecutedTotalUWolo,
		ExecutedTotalWolo:    response.ExecutedTotalWolo,
		ConfirmedTotalUWolo:  response.ConfirmedTotalUWolo,
		ConfirmedTotalWolo:   response.ConfirmedTotalWolo,
		AcceptedTotalUWolo:   response.AcceptedTotalUWolo,
		AcceptedTotalWolo:    response.AcceptedTotalWolo,
		RefusedTotalUWolo:    response.RefusedTotalUWolo,
		RefusedTotalWolo:     response.RefusedTotalWolo,
		RejectedTotalUWolo:   response.RejectedTotalUWolo,
		RejectedTotalWolo:    response.RejectedTotalWolo,
		Detail:               response.Detail,
	}
}

func summarizeSettlementRunSigner(payouts []settlementRunPayoutResult) (string, string) {
	signerRole := settlementSignerRole
	signerAddress := ""
	for _, payout := range payouts {
		if signerAddress == "" && strings.TrimSpace(payout.SignerAddress) != "" {
			signerAddress = payout.SignerAddress
		}
		if strings.TrimSpace(payout.SignerRole) != "" {
			signerRole = payout.SignerRole
		}
	}

	if signerRole == settlementSignerRole && signerAddress == "" && len(payouts) == 0 {
		return "", ""
	}

	return signerRole, signerAddress
}

func summarizeSettlementRunRecentItems(limit int, statusFilter, failureCodeFilter string, items []settlementRunRecentItem) settlementRunRecentSummary {
	summary := settlementRunRecentSummary{
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

func matchesSettlementStatusFilter(response settlementExecuteResponse, statusFilter string) bool {
	switch statusFilter {
	case "", "all":
		return true
	case "failed", "confirmed", "accepted":
		return strings.EqualFold(strings.TrimSpace(response.Status), statusFilter)
	case "refused":
		return strings.EqualFold(strings.TrimSpace(response.Status), "failed") && strings.TrimSpace(response.TxHash) == ""
	case "rejected":
		return strings.EqualFold(strings.TrimSpace(response.Status), "failed") && strings.TrimSpace(response.TxHash) != ""
	default:
		return false
	}
}

func deriveSettlementOutcome(response settlementExecuteResponse) string {
	switch {
	case response.IdempotentReplay:
		return "idempotent_replay"
	case strings.EqualFold(strings.TrimSpace(response.Status), "confirmed") && response.OK:
		return "confirmed"
	case strings.EqualFold(strings.TrimSpace(response.Status), "accepted") && response.OK:
		return "accepted"
	case strings.EqualFold(strings.TrimSpace(response.Status), "failed") && strings.TrimSpace(response.TxHash) == "":
		return "refused"
	case strings.EqualFold(strings.TrimSpace(response.Status), "failed") && strings.TrimSpace(response.TxHash) != "":
		return "rejected"
	case strings.TrimSpace(response.Status) != "":
		return strings.TrimSpace(response.Status)
	default:
		return "unknown"
	}
}

func classifySettlementExecError(raw string) (string, bool) {
	text := strings.ToLower(strings.TrimSpace(raw))
	switch {
	case strings.Contains(text, "insufficient funds"):
		return "INSUFFICIENT_FUNDS", false
	case strings.Contains(text, "account sequence mismatch"), strings.Contains(text, "incorrect account sequence"):
		return "SEQUENCE_MISMATCH", true
	case strings.Contains(text, "connection refused"), strings.Contains(text, "no such host"), strings.Contains(text, "deadline exceeded"), strings.Contains(text, "timed out"), strings.Contains(text, "rpc error"):
		return "RPC_UNREACHABLE", true
	default:
		return "BROADCAST_FAILED", true
	}
}

func classifyRejectedTx(rawLog string, code uint32) string {
	text := strings.ToLower(rawLog)
	switch {
	case strings.Contains(text, "out of gas"):
		return "OUT_OF_GAS"
	case strings.Contains(text, "insufficient funds"):
		return "INSUFFICIENT_FUNDS"
	default:
		_ = code
		return "TX_REJECTED"
	}
}

func extractSettlementTransfers(payload restTxLookupResponse) []settlementTransfer {
	return extractSettlementTransfersFromLogsAndEvents(payload.TxResponse.Logs, payload.TxResponse.Events)
}

func extractSettlementTransfersFromLogsAndEvents(logItems []restTxLogItem, fallbackEvents []restTxEvent) []settlementTransfer {
	transfers := make([]settlementTransfer, 0)

	appendFromEvents := func(events []restTxEvent) {
		for _, event := range events {
			if event.Type != "transfer" {
				continue
			}

			sender := ""
			recipient := ""
			amount := ""
			for _, attr := range event.Attributes {
				switch attr.Key {
				case "sender":
					sender = strings.TrimSpace(attr.Value)
				case "recipient":
					recipient = strings.TrimSpace(attr.Value)
				case "amount":
					amount = strings.TrimSpace(attr.Value)
				}
			}

			if sender == "" || recipient == "" || amount == "" {
				continue
			}

			for _, coin := range splitCoinAmounts(amount) {
				transfers = append(transfers, settlementTransfer{
					Sender:    sender,
					Recipient: recipient,
					Amount:    coin.Amount,
					Denom:     coin.Denom,
				})
			}
		}
	}

	for _, logItem := range logItems {
		appendFromEvents(logItem.Events)
	}

	if len(transfers) == 0 {
		appendFromEvents(fallbackEvents)
	}

	return transfers
}

type coinAmount struct {
	Amount string
	Denom  string
}

func splitCoinAmounts(raw string) []coinAmount {
	parts := strings.Split(raw, ",")
	out := make([]coinAmount, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		splitAt := 0
		for splitAt < len(part) && part[splitAt] >= '0' && part[splitAt] <= '9' {
			splitAt++
		}
		if splitAt == 0 || splitAt >= len(part) {
			continue
		}

		out = append(out, coinAmount{
			Amount: part[:splitAt],
			Denom:  part[splitAt:],
		})
	}
	return out
}

func matchSettlementTransfer(transfers []settlementTransfer, expectations settlementLookupExpectations) (*settlementTransfer, bool) {
	expectedSender := strings.TrimSpace(expectations.Sender)
	expectedRecipient := strings.TrimSpace(expectations.Recipient)
	expectedAmount := strings.TrimSpace(expectations.AmountUWolo)
	if expectedSender == "" && expectedRecipient == "" && expectedAmount == "" {
		return nil, false
	}

	for _, transfer := range transfers {
		if expectedSender != "" && !strings.EqualFold(transfer.Sender, expectedSender) {
			continue
		}
		if expectedRecipient != "" && !strings.EqualFold(transfer.Recipient, expectedRecipient) {
			continue
		}
		if expectedAmount != "" && transfer.Amount != expectedAmount {
			continue
		}

		match := transfer
		return &match, true
	}

	return nil, false
}

func readSettlementStoredResult(path string) (settlementStoredResult, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return settlementStoredResult{}, err
	}

	result := settlementStoredResult{}
	if err := json.Unmarshal(data, &result); err != nil {
		return settlementStoredResult{}, err
	}
	return result, nil
}

func readSettlementRunStoredResult(path string) (settlementRunStoredResult, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return settlementRunStoredResult{}, err
	}

	result := settlementRunStoredResult{}
	if err := json.Unmarshal(data, &result); err != nil {
		return settlementRunStoredResult{}, err
	}
	return result, nil
}

func writeSettlementStoredResult(path string, result settlementStoredResult) error {
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

func writeSettlementRunStoredResult(path string, result settlementRunStoredResult) error {
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

func normalizeTxHash(txHash string) string {
	return strings.ToUpper(strings.TrimSpace(txHash))
}

func isHexHash(txHash string) bool {
	if len(txHash) == 0 || len(txHash)%2 != 0 {
		return false
	}
	_, err := hex.DecodeString(txHash)
	return err == nil
}

func isWoloAddress(address, prefix string) bool {
	address = strings.TrimSpace(address)
	return address != "" && strings.HasPrefix(strings.ToLower(address), strings.ToLower(prefix)+"1")
}

func getJSON(ctx context.Context, target string, dst any) (int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return resp.StatusCode, err
	}

	if resp.StatusCode == http.StatusNotFound {
		return resp.StatusCode, nil
	}
	if resp.StatusCode >= 400 {
		return resp.StatusCode, fmt.Errorf("upstream returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	decoder := json.NewDecoder(bytes.NewReader(body))
	if err := decoder.Decode(dst); err != nil {
		return resp.StatusCode, err
	}

	return resp.StatusCode, nil
}

func writeJSON(writer io.Writer, value any) error {
	encoder := json.NewEncoder(writer)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}

func writeJSONResponse(w http.ResponseWriter, statusCode int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_ = writeJSON(w, value)
}

func optionalSettlementRecord(summaryOnly bool, record *settlementStoredResult) *settlementStoredResult {
	if summaryOnly {
		return nil
	}

	return record
}

func optionalSettlementRecentItems(summaryOnly bool, items []settlementRecentItem) []settlementRecentItem {
	if summaryOnly {
		return nil
	}

	return items
}

func optionalSettlementRunRecord(summaryOnly bool, record *settlementRunStoredResult) *settlementRunStoredResult {
	if summaryOnly {
		return nil
	}

	return record
}

func optionalSettlementRunRecentItems(summaryOnly bool, items []settlementRunRecentItem) []settlementRunRecentItem {
	if summaryOnly {
		return nil
	}

	return items
}

func readJSONInput(path string, dst any) error {
	var (
		reader io.Reader
		file   *os.File
		err    error
	)

	if strings.TrimSpace(path) == "" || strings.TrimSpace(path) == "-" {
		reader = os.Stdin
	} else {
		file, err = os.Open(path)
		if err != nil {
			return err
		}
		defer file.Close()
		reader = file
	}

	decoder := json.NewDecoder(reader)
	return decoder.Decode(dst)
}

func parseOptionalUWoloEnv(key string) (uint64, error) {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return 0, nil
	}

	amount, err := strconv.ParseUint(value, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be a positive integer uwolo amount", key)
	}

	return amount, nil
}

func formatOptionalUWolo(amount uint64) string {
	if amount == 0 {
		return ""
	}

	return strconv.FormatUint(amount, 10)
}

func formatOptionalDisplayAmount(amount uint64) string {
	if amount == 0 {
		return ""
	}

	return formatDisplayAmount(strconv.FormatUint(amount, 10))
}

func (cfg settlementConfig) estimateSettlementRunFee(payoutCount int) (string, string) {
	if payoutCount <= 0 {
		return "", ""
	}
	if strings.TrimSpace(cfg.Fees) == "" {
		return "", fmt.Sprintf("fee estimate unavailable for grouped runs unless WOLO_SETTLEMENT_FEES is set explicitly in %s", cfg.BaseDenom)
	}

	perPayoutFee, err := parseBaseDenomFeeAmount(cfg.Fees, cfg.BaseDenom)
	if err != nil {
		return "", fmt.Sprintf("fee estimate unavailable: %v", err)
	}
	if perPayoutFee == 0 {
		return "", fmt.Sprintf("fee estimate unavailable: WOLO_SETTLEMENT_FEES does not include %s", cfg.BaseDenom)
	}

	return strconv.FormatUint(perPayoutFee*uint64(payoutCount), 10), ""
}

func parseBaseDenomFeeAmount(raw, baseDenom string) (uint64, error) {
	var total uint64
	for _, coin := range splitCoinAmounts(raw) {
		if coin.Denom != baseDenom {
			continue
		}
		amount, err := strconv.ParseUint(strings.TrimSpace(coin.Amount), 10, 64)
		if err != nil {
			return 0, fmt.Errorf("invalid %s fee amount %q", baseDenom, coin.Amount)
		}
		total += amount
	}

	return total, nil
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			return trimmed
		}
	}

	return ""
}

func getenvDefault(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func getenvFirst(keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}
	return ""
}

func normalizeHTTPURL(raw, fallback string) string {
	value := strings.TrimSpace(raw)
	if value == "" {
		value = fallback
	}
	value = strings.TrimRight(value, "/")
	if strings.HasPrefix(value, "tcp://") {
		value = "http://" + strings.TrimPrefix(value, "tcp://")
	}
	if !strings.HasPrefix(value, "http://") && !strings.HasPrefix(value, "https://") {
		value = "http://" + value
	}
	return value
}

func expandHome(path string) string {
	path = strings.TrimSpace(path)
	if path == "" || path[0] != '~' {
		return path
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return path
	}

	if path == "~" {
		return home
	}

	return filepath.Join(home, strings.TrimPrefix(path, "~/"))
}
