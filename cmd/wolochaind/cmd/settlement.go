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
)

var settlementRequestIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$`)

type settlementConfig struct {
	ExecutablePath  string
	HomeDir         string
	KeyringBackend  string
	KeyringDir      string
	NodeAddr        string
	RPCHTTP         string
	RESTURL         string
	ChainID         string
	BaseDenom       string
	DisplayDenom    string
	AddressPrefix   string
	PayoutKeyName   string
	PayoutAddress   string
	EscrowAddress   string
	BroadcastMode   string
	Gas             string
	GasAdjustment   string
	GasPrices       string
	Fees            string
	StateDir        string
	ListenAddr      string
	AuthToken       string
	RequestLockTTL  time.Duration
	RequestTimeout  time.Duration
	LookupTimeout   time.Duration
	HealthTimeout   time.Duration
	ConfirmTimeout  time.Duration
	ConfirmInterval time.Duration
}

type settlementHealthResponse struct {
	OK             bool     `json:"ok"`
	FailureCode    string   `json:"failure_code,omitempty"`
	Detail         string   `json:"detail,omitempty"`
	ChainID        string   `json:"chain_id"`
	RuntimeChainID string   `json:"runtime_chain_id,omitempty"`
	RPCURL         string   `json:"rpc_url"`
	RESTURL        string   `json:"rest_url"`
	HomeDir        string   `json:"home_dir"`
	KeyringBackend string   `json:"keyring_backend"`
	PayoutKeyName  string   `json:"payout_key_name,omitempty"`
	PayoutAddress  string   `json:"payout_address,omitempty"`
	EscrowAddress  string   `json:"escrow_address,omitempty"`
	Warnings       []string `json:"warnings,omitempty"`
	LoopbackOnly   bool     `json:"loopback_only"`
	AuthTokenSet   bool     `json:"auth_token_set"`
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
	OK                bool   `json:"ok"`
	Status            string `json:"status"`
	FailureCode       string `json:"failure_code,omitempty"`
	Retryable         bool   `json:"retryable"`
	IdempotentReplay  bool   `json:"idempotent_replay"`
	RequestID         string `json:"request_id"`
	ChainID           string `json:"chain_id"`
	SignerRole        string `json:"signer_role"`
	SignerAddress     string `json:"signer_address,omitempty"`
	ToAddress         string `json:"to_address,omitempty"`
	AmountUWolo       string `json:"amount_uwolo,omitempty"`
	AmountWolo        string `json:"amount_wolo,omitempty"`
	BroadcastMode     string `json:"broadcast_mode,omitempty"`
	TxHash            string `json:"tx_hash,omitempty"`
	Code              uint32 `json:"code,omitempty"`
	Codespace         string `json:"codespace,omitempty"`
	RawLog            string `json:"raw_log,omitempty"`
	Detail            string `json:"detail,omitempty"`
	CanonicalTxLookup string `json:"canonical_tx_lookup,omitempty"`
}

type settlementStoredResult struct {
	Request     normalizedSettlementRequest `json:"request"`
	Fingerprint string                      `json:"fingerprint"`
	Response    settlementExecuteResponse   `json:"response"`
	UpdatedAt   time.Time                   `json:"updated_at"`
}

type settlementLookupResponse struct {
	OK                bool                 `json:"ok"`
	FailureCode       string               `json:"failure_code,omitempty"`
	Detail            string               `json:"detail,omitempty"`
	Found             bool                 `json:"found"`
	ChainID           string               `json:"chain_id,omitempty"`
	TxHash            string               `json:"tx_hash,omitempty"`
	TxSuccess         bool                 `json:"tx_success"`
	Kind              string               `json:"kind,omitempty"`
	Height            string               `json:"height,omitempty"`
	Code              uint32               `json:"code,omitempty"`
	Codespace         string               `json:"codespace,omitempty"`
	Memo              string               `json:"memo,omitempty"`
	RawLog            string               `json:"raw_log,omitempty"`
	Timestamp         string               `json:"timestamp,omitempty"`
	CanonicalTxLookup string               `json:"canonical_tx_lookup,omitempty"`
	Transfers         []settlementTransfer `json:"transfers,omitempty"`
	MatchedExpected   bool                 `json:"matched_expected"`
	MatchedTransfer   *settlementTransfer  `json:"matched_transfer,omitempty"`
}

type settlementTransfer struct {
	Sender    string `json:"sender"`
	Recipient string `json:"recipient"`
	Amount    string `json:"amount"`
	Denom     string `json:"denom"`
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
		newSettlementLookupCmd(),
		newSettlementServeCmd(),
	)

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

			server := &http.Server{
				Addr:              cfg.ListenAddr,
				Handler:           mux,
				ReadHeaderTimeout: 5 * time.Second,
			}

			cmd.Printf("settlement server listening on http://%s\n", cfg.ListenAddr)
			return server.ListenAndServe()
		},
	}
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

	cfg := settlementConfig{
		ExecutablePath:  executablePath,
		HomeDir:         homeDir,
		KeyringBackend:  getenvDefault("WOLO_SETTLEMENT_KEYRING_BACKEND", "os"),
		KeyringDir:      expandHome(os.Getenv("WOLO_SETTLEMENT_KEYRING_DIR")),
		NodeAddr:        getenvDefault("WOLO_SETTLEMENT_NODE", settlementDefaultNode),
		RPCHTTP:         rpcHTTP,
		RESTURL:         restURL,
		ChainID:         getenvDefault("WOLO_SETTLEMENT_CHAIN_ID", settlementCanonicalChainID),
		BaseDenom:       getenvDefault("WOLO_SETTLEMENT_BASE_DENOM", settlementCanonicalBaseDenom),
		DisplayDenom:    getenvDefault("WOLO_SETTLEMENT_DISPLAY_DENOM", settlementCanonicalDisplayDenom),
		AddressPrefix:   getenvDefault("WOLO_SETTLEMENT_ADDRESS_PREFIX", settlementCanonicalPrefix),
		PayoutKeyName:   strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_PAYOUT_KEY_NAME")),
		PayoutAddress:   strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_PAYOUT_ADDRESS")),
		EscrowAddress:   strings.TrimSpace(getenvFirst("WOLO_SETTLEMENT_ESCROW_ADDRESS", "WOLO_BET_ESCROW_ADDRESS")),
		BroadcastMode:   getenvDefault("WOLO_SETTLEMENT_BROADCAST_MODE", "sync"),
		Gas:             getenvDefault("WOLO_SETTLEMENT_GAS", "auto"),
		GasAdjustment:   getenvDefault("WOLO_SETTLEMENT_GAS_ADJUSTMENT", "1.5"),
		GasPrices:       getenvDefault("WOLO_SETTLEMENT_GAS_PRICES", settlementDefaultGasPrices),
		Fees:            strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_FEES")),
		ListenAddr:      getenvDefault("WOLO_SETTLEMENT_LISTEN_ADDR", settlementDefaultListenAddr),
		AuthToken:       strings.TrimSpace(os.Getenv("WOLO_SETTLEMENT_AUTH_TOKEN")),
		RequestLockTTL:  2 * time.Minute,
		RequestTimeout:  30 * time.Second,
		LookupTimeout:   10 * time.Second,
		HealthTimeout:   5 * time.Second,
		ConfirmTimeout:  12 * time.Second,
		ConfirmInterval: 250 * time.Millisecond,
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
		OK:             true,
		ChainID:        cfg.ChainID,
		RPCURL:         cfg.RPCHTTP,
		RESTURL:        cfg.RESTURL,
		HomeDir:        cfg.HomeDir,
		KeyringBackend: cfg.KeyringBackend,
		PayoutKeyName:  cfg.PayoutKeyName,
		EscrowAddress:  cfg.EscrowAddress,
		LoopbackOnly:   cfg.listenAddrIsLoopback(),
		AuthTokenSet:   cfg.AuthToken != "",
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

	if cfg.KeyringBackend == "test" {
		report.Warnings = append(report.Warnings, "test keyring backend is enabled; use only for local/dev or explicitly accepted ops")
	}

	if cfg.AuthToken == "" {
		report.Warnings = append(report.Warnings, "WOLO_SETTLEMENT_AUTH_TOKEN is empty; payout POST access relies on loopback-only binding")
	}

	payoutAddress, err := cfg.resolvePayoutAddress(ctx)
	if err == nil && payoutAddress != "" {
		report.PayoutAddress = payoutAddress
	}
	if err != nil && cfg.PayoutKeyName != "" {
		report.Warnings = append(report.Warnings, err.Error())
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

	signerAddress, failure := cfg.preflightExecution(ctx)
	if failure != nil {
		failure.RequestID = normalized.RequestID
		failure.ToAddress = normalized.ToAddress
		failure.AmountUWolo = normalized.AmountUWolo
		failure.AmountWolo = formatDisplayAmount(normalized.AmountUWolo)
		return *failure, nil
	}

	recordPath := cfg.requestRecordPath(normalized.RequestID)
	fingerprint := hashSettlementRequest(normalized, signerAddress)

	response, err := cfg.withRequestLock(normalized.RequestID, func() (settlementExecuteResponse, error) {
		stored, readErr := readSettlementStoredResult(recordPath)
		if readErr == nil {
			if stored.Fingerprint != fingerprint {
				return settlementExecuteResponse{
					OK:            false,
					Status:        "failed",
					FailureCode:   "IDEMPOTENCY_CONFLICT",
					Retryable:     false,
					RequestID:     normalized.RequestID,
					ChainID:       cfg.ChainID,
					SignerRole:    settlementSignerRole,
					SignerAddress: signerAddress,
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
				OK:            false,
				Status:        "failed",
				FailureCode:   "STATE_FILE_INVALID",
				Retryable:     false,
				RequestID:     normalized.RequestID,
				ChainID:       cfg.ChainID,
				SignerRole:    settlementSignerRole,
				SignerAddress: signerAddress,
				ToAddress:     normalized.ToAddress,
				AmountUWolo:   normalized.AmountUWolo,
				AmountWolo:    formatDisplayAmount(normalized.AmountUWolo),
				Detail:        fmt.Sprintf("could not read settlement state file: %v", readErr),
			}, nil
		}

		result := cfg.broadcastPayout(ctx, normalized, signerAddress)
		if err := writeSettlementStoredResult(recordPath, settlementStoredResult{
			Request:     normalized,
			Fingerprint: fingerprint,
			Response:    result,
			UpdatedAt:   time.Now().UTC(),
		}); err != nil {
			return settlementExecuteResponse{}, err
		}
		return result, nil
	})
	if err != nil {
		return settlementExecuteResponse{}, err
	}

	return response, nil
}

func (cfg settlementConfig) preflightExecution(ctx context.Context) (string, *settlementExecuteResponse) {
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
		OK:                false,
		Status:            "failed",
		RequestID:         request.RequestID,
		ChainID:           cfg.ChainID,
		SignerRole:        settlementSignerRole,
		SignerAddress:     signerAddress,
		ToAddress:         request.ToAddress,
		AmountUWolo:       request.AmountUWolo,
		AmountWolo:        formatDisplayAmount(request.AmountUWolo),
		BroadcastMode:     cfg.BroadcastMode,
		CanonicalTxLookup: cfg.txLookupURL(""),
	}

	var broadcast bankSendBroadcastResponse
	if jsonPayload := extractJSONPayload(output); len(jsonPayload) > 0 {
		if jsonErr := json.Unmarshal(jsonPayload, &broadcast); jsonErr == nil && broadcast.TxHash != "" {
			response.TxHash = broadcast.TxHash
			response.Code = broadcast.Code
			response.Codespace = broadcast.Codespace
			response.RawLog = broadcast.RawLog
			response.CanonicalTxLookup = cfg.txLookupURL(broadcast.TxHash)
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
			OK:                false,
			FailureCode:       "LOOKUP_FAILED",
			Detail:            err.Error(),
			CanonicalTxLookup: cfg.txLookupURL(normalizedHash),
		}, nil
	}
	if statusCode == http.StatusNotFound {
		return settlementLookupResponse{
			OK:                false,
			FailureCode:       "TX_NOT_FOUND",
			Detail:            "tx hash not found on WoloChain REST",
			CanonicalTxLookup: cfg.txLookupURL(normalizedHash),
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
		OK:                true,
		Found:             true,
		ChainID:           cfg.ChainID,
		TxHash:            payload.TxResponse.TxHash,
		TxSuccess:         payload.TxResponse.Code == 0,
		Kind:              kind,
		Height:            payload.TxResponse.Height,
		Code:              payload.TxResponse.Code,
		Codespace:         payload.TxResponse.Codespace,
		Memo:              payload.Tx.Body.Memo,
		RawLog:            payload.TxResponse.RawLog,
		Timestamp:         payload.TxResponse.Timestamp,
		CanonicalTxLookup: cfg.txLookupURL(normalizedHash),
		Transfers:         transfers,
		MatchedExpected:   matchedExpected,
		MatchedTransfer:   matchedTransfer,
	}

	return response, nil
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

func (cfg settlementConfig) requestRecordPath(requestID string) string {
	return filepath.Join(cfg.StateDir, "requests", requestID+".json")
}

func (cfg settlementConfig) requestLockPath(requestID string) string {
	return filepath.Join(cfg.StateDir, "locks", requestID+".lock")
}

func (cfg settlementConfig) txLookupURL(txHash string) string {
	if txHash == "" {
		return strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/tx/v1beta1/txs/{tx_hash}"
	}

	return strings.TrimRight(cfg.RESTURL, "/") + "/cosmos/tx/v1beta1/txs/" + url.PathEscape(txHash)
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

	for _, logItem := range payload.TxResponse.Logs {
		appendFromEvents(logItem.Events)
	}

	if len(transfers) == 0 {
		appendFromEvents(payload.TxResponse.Events)
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
