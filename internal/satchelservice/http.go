package satchelservice

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net"
	"net/http"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/cosmos/btcutil/bech32"
	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
)

const (
	HTTPMaxBodyBytes = 16 << 10
	httpCustodyRole  = "exclusive-war-satchel-v1"
)

var (
	httpTokenPattern     = regexp.MustCompile(`^[A-Za-z0-9_-]{48,512}$`)
	httpDigestPattern    = regexp.MustCompile(`^[a-f0-9]{64}$`)
	httpHashPattern      = regexp.MustCompile(`^[A-Fa-f0-9]{64}$`)
	httpOperationPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$`)
	httpReasonPattern    = regexp.MustCompile(`^[A-Za-z0-9_:-]{1,96}$`)
)

// HTTPBackend is the durable engine boundary. Only Submit may initiate a
// transfer. Reconcile and Lookup must never sign or rebroadcast an operation.
type HTTPBackend interface {
	Submit(context.Context, TransferRequest) (Result, error)
	Reconcile(context.Context, string) (Result, error)
	Lookup(string) (Result, error)
}

// HTTPReturnBackend prepares a request for the separately controlled escrow
// lane and reads actual return evidence. Neither method may transmit tokens.
type HTTPReturnBackend interface {
	PrepareReturnRun(context.Context, ReturnApproval) (ReturnRun, error)
	ReconcileClaimReturn(context.Context, ReturnApproval, string) (ReturnReceipt, error)
}

// HTTPFinancialProofBackend exports evidence only. It cannot credit, sign,
// broadcast or reserve an operation, including when the permit has expired.
type HTTPFinancialProofBackend interface {
	DepositProof(context.Context, DepositProofRequest) (FinancialProof, error)
	OperationProof(context.Context, string) (FinancialProof, error)
	ReturnProof(context.Context, string) (FinancialProof, error)
}

type HTTPCustodyJournalBackend interface {
	CustodyJournal() (CustodyJournal, error)
}

type HTTPCustodyFeeCheckpointBackend interface {
	ReviewerFeeCheckpoint([]string) (ReviewerCustodyFeeCheckpoint, error)
}

// HTTPHealth describes the already-verified service identity. This self-report
// does not certify vault ownership, bank reserves, recovery or chain consensus.
// Construct it only after the engine verifies its operator-owned authority.
type HTTPHealth struct {
	Accepting                  bool
	VaultAddress               string
	EscrowAddress              string
	KeyFingerprint             string
	BuildSHA256                string
	ExclusiveAuthorityVerified bool
}

type HTTPConfig struct {
	Token string
	// Accepting is set only by the CLI after verifying the independent signed
	// activation permit. Its zero value keeps every execution route closed.
	Accepting bool
	// Authorize re-verifies the independent activation permit at each health
	// check and submission. Read-only recovery stays available after expiry.
	Authorize         func(context.Context) bool
	CustodyCapability func(context.Context) RuntimeCustodyCapability
	Health            HTTPHealth
	RequestTimeout    time.Duration
	MaxConcurrent     int
}

type privateHTTPHandler struct {
	backend           HTTPBackend
	identity          HTTPHealth
	tokenDigest       [32]byte
	timeout           time.Duration
	slots             chan struct{}
	authorize         func(context.Context) bool
	custodyCapability func(context.Context) RuntimeCustodyCapability
}

// NewHTTPHandler implements the two pinned HD client wire forms. It exposes no
// arbitrary node, key, destination policy or subprocess options. The service is
// restricted to authenticated literal loopback peers; proxy headers confer no
// authority. An independently controlled withdrawal approval remains mandatory.
func NewHTTPHandler(backend HTTPBackend, cfg HTTPConfig) (http.Handler, error) {
	if backend == nil || !httpTokenPattern.MatchString(cfg.Token) {
		return nil, errors.New("invalid_private_http_configuration")
	}
	if !cfg.Accepting {
		cfg.Health.Accepting = false
		cfg.Health.ExclusiveAuthorityVerified = false
	}
	if cfg.Accepting && cfg.Authorize == nil {
		return nil, errors.New("independent_activation_verifier_required")
	}
	if cfg.RequestTimeout == 0 {
		cfg.RequestTimeout = 7 * time.Second
	}
	if cfg.MaxConcurrent == 0 {
		cfg.MaxConcurrent = 4
	}
	if cfg.RequestTimeout <= 0 || cfg.RequestTimeout > 8*time.Second || cfg.MaxConcurrent < 1 || cfg.MaxConcurrent > 16 {
		return nil, errors.New("invalid_private_http_limits")
	}
	if cfg.Health.Accepting && (!cfg.Health.ExclusiveAuthorityVerified || !httpVaultAddress(cfg.Health.VaultAddress) ||
		!httpDigestPattern.MatchString(cfg.Health.KeyFingerprint) || !httpDigestPattern.MatchString(cfg.Health.BuildSHA256)) {
		return nil, errors.New("unverified_private_http_identity")
	}
	return &privateHTTPHandler{backend: backend, identity: cfg.Health, tokenDigest: sha256.Sum256([]byte(cfg.Token)),
		timeout: cfg.RequestTimeout, slots: make(chan struct{}, cfg.MaxConcurrent), authorize: cfg.Authorize, custodyCapability: cfg.CustodyCapability}, nil
}

func httpVaultAddress(address string) bool {
	prefix, payload, err := bech32.DecodeToBase256(address)
	return err == nil && prefix == "wolo" && len(payload) == 20 && !satchel.IsKnownRoleAddress(address)
}

// NewPrivateHTTPServer supplies transport-level resource bounds. Operators must
// run this listener in the dedicated service account and network namespace;
// loopback is not a replacement for OS separation or protected secret files.
func NewPrivateHTTPServer(address string, handler http.Handler) (*http.Server, error) {
	host, port, err := net.SplitHostPort(address)
	ip := net.ParseIP(host)
	portNumber, portErr := strconv.Atoi(port)
	if err != nil || ip == nil || !ip.IsLoopback() || portErr != nil || portNumber < 0 || portNumber > 65535 || handler == nil {
		return nil, errors.New("private_listener_requires_literal_loopback")
	}
	return &http.Server{Addr: address, Handler: handler, ReadHeaderTimeout: 2 * time.Second,
		ReadTimeout: 3 * time.Second, WriteTimeout: 9 * time.Second, IdleTimeout: 15 * time.Second,
		MaxHeaderBytes: 8192}, nil
}

func (h *privateHTTPHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	if !h.authorized(r) {
		httpFailure(w, http.StatusUnauthorized, "private_authentication_required")
		return
	}
	if r.URL.RawQuery != "" || r.URL.RawPath != "" {
		httpFailure(w, http.StatusBadRequest, "invalid_private_route")
		return
	}
	select {
	case h.slots <- struct{}{}:
		defer func() { <-h.slots }()
	default:
		httpFailure(w, http.StatusServiceUnavailable, "private_service_busy")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), h.timeout)
	defer cancel()
	r = r.WithContext(ctx)
	if r.URL.Path == "/satchel/v1/health" {
		if r.Method != http.MethodGet {
			httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
			return
		}
		h.health(ctx, w)
		return
	}
	if r.URL.Path == "/satchel/v1/custody/journal" {
		if r.Method != http.MethodGet {
			httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
			return
		}
		backend, ok := h.backend.(HTTPCustodyJournalBackend)
		if !ok || ctx.Err() != nil {
			httpFailure(w, http.StatusServiceUnavailable, "custody_journal_unavailable")
			return
		}
		snapshot, err := backend.CustodyJournal()
		if err != nil || ctx.Err() != nil || snapshot.Protocol != 1 || snapshot.ChainID != "wolo-1" || snapshot.Denom != "uwolo" ||
			snapshot.CreditAuthorized || snapshot.SolvencyAuthorized || snapshot.BankBalanceAuthenticated || snapshot.CustodyCapability != "UNAVAILABLE" {
			httpFailure(w, http.StatusConflict, "custody_journal_unverifiable")
			return
		}
		httpWrite(w, http.StatusOK, snapshot)
		return
	}
	if r.URL.Path == "/satchel/v1/custody/fee-checkpoint" {
		h.custodyFeeCheckpoint(ctx, w, r)
		return
	}
	if r.URL.Path == "/satchel/v1/custody/principal-checkpoint" {
		h.custodyPrincipalCheckpoint(ctx, w, r)
		return
	}
	if strings.HasPrefix(r.URL.Path, "/satchel/v1/operations/") {
		if r.Method != http.MethodGet {
			httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/satchel/v1/operations/")
		if !httpOperationPattern.MatchString(id) {
			httpFailure(w, http.StatusBadRequest, "invalid_operation_id")
			return
		}
		result, err := h.backend.Lookup(id)
		h.result(w, id, result, err, false)
		return
	}
	if r.URL.Path != "/satchel/v1/one-shot" && r.URL.Path != "/satchel/v2/one-shot" && r.URL.Path != "/v1/satchel/withdrawals" && r.URL.Path != "/satchel/v1/reconcile" &&
		r.URL.Path != "/satchel/v1/returns/prepare" && r.URL.Path != "/satchel/v1/returns/reconcile" &&
		r.URL.Path != "/satchel/v1/proofs/deposit" && r.URL.Path != "/satchel/v1/proofs/operation" && r.URL.Path != "/satchel/v1/proofs/return" && r.URL.Path != "/satchel/v1/proofs/bank" && r.URL.Path != "/satchel/v1/proofs/escrow-bank" {
		httpFailure(w, http.StatusNotFound, "private_route_not_found")
		return
	}
	if r.Method != http.MethodPost {
		httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}
	if ctx.Err() != nil {
		httpFailure(w, http.StatusRequestTimeout, "request_canceled")
		return
	}
	readOnly := r.URL.Path == "/satchel/v1/reconcile" || r.URL.Path == "/satchel/v1/returns/reconcile" || strings.HasPrefix(r.URL.Path, "/satchel/v1/proofs/")
	if !readOnly && !h.accepting(ctx) {
		httpFailure(w, http.StatusServiceUnavailable, "custody_service_unavailable")
		return
	}
	data, status := readPrivateJSON(w, r)
	if status != 0 {
		httpFailure(w, status, "invalid_bounded_request")
		return
	}
	if ctx.Err() != nil {
		httpFailure(w, http.StatusRequestTimeout, "request_canceled")
		return
	}
	if strings.HasPrefix(r.URL.Path, "/satchel/v1/proofs/") {
		h.financialProof(ctx, w, r.URL.Path, data)
		return
	}
	if strings.HasPrefix(r.URL.Path, "/satchel/v1/returns/") {
		h.claimReturn(ctx, w, r.URL.Path, data)
		return
	}
	if r.URL.Path == "/satchel/v1/reconcile" {
		_ = h.accepting(ctx) // Check permit without preventing read-only recovery.
		var input struct {
			OperationID string `json:"operation_id"`
		}
		if strictHTTPJSON(data, &input) != nil || !httpOperationPattern.MatchString(input.OperationID) {
			httpFailure(w, http.StatusBadRequest, "invalid_reconciliation_request")
			return
		}
		result, err := h.backend.Reconcile(ctx, input.OperationID)
		h.result(w, input.OperationID, result, err, false)
		return
	}
	var input TransferRequest
	var err error
	if r.URL.Path == "/v1/satchel/withdrawals" {
		input, err = decodeWithdrawalHTTP(data)
	} else if r.URL.Path == "/satchel/v2/one-shot" {
		input, err = decodeReservedWagerHTTP(data)
	} else {
		input, err = decodeWagerHTTP(data)
	}
	if err != nil {
		httpFailure(w, http.StatusBadRequest, "invalid_transfer_request")
		return
	}
	// A slow body or validation interval must not outlive the independently
	// approved activation window before the durable engine receives intent.
	if !h.accepting(ctx) {
		httpFailure(w, http.StatusServiceUnavailable, "custody_service_unavailable")
		return
	}
	result, err := h.backend.Submit(ctx, input)
	if r.URL.Path == "/satchel/v2/one-shot" {
		h.result(w, input.OperationID, result, err, false, true)
	} else {
		h.result(w, input.OperationID, result, err, true)
	}
}

func (h *privateHTTPHandler) claimReturn(ctx context.Context, w http.ResponseWriter, path string, data []byte) {
	backend, ok := h.backend.(HTTPReturnBackend)
	if !ok {
		httpFailure(w, http.StatusServiceUnavailable, "return_adapter_unavailable")
		return
	}
	if path == "/satchel/v1/returns/prepare" {
		var approval ReturnApproval
		if strictHTTPJSON(data, &approval) != nil || !httpReturnV2(approval) {
			httpFailure(w, http.StatusBadRequest, "invalid_return_approval")
			return
		}
		if !h.accepting(ctx) {
			httpFailure(w, http.StatusServiceUnavailable, "custody_service_unavailable")
			return
		}
		run, err := backend.PrepareReturnRun(ctx, approval)
		if err != nil {
			httpFailure(w, http.StatusConflict, "return_preparation_refused")
			return
		}
		id := "satchel:claim-return:" + approval.ClaimID
		if run.SettlementRunID != id || run.SourceApp != "aoe2hdbets" || run.SourceEventID != approval.OperationID || run.SignerRole != "escrow" || len(run.Payouts) != 1 ||
			run.Payouts[0].RequestID != id || run.Payouts[0].ToAddress != h.identity.VaultAddress || run.Payouts[0].AmountUWolo != approval.AmountUWolo || run.Payouts[0].Memo != "aoe2war/satchel/claim-return/v1/"+approval.ClaimID {
			httpFailure(w, http.StatusServiceUnavailable, "return_run_identity_unverifiable")
			return
		}
		httpWrite(w, http.StatusOK, map[string]any{"kind": "escrow_run_prepared", "execution_authorized": false, "credit_authorized": false, "run": run})
		return
	}
	_ = h.accepting(ctx) // Expired activation must not prevent proof reconciliation.
	var input struct {
		Approval *ReturnApproval `json:"approval"`
		TxHash   string          `json:"tx_hash"`
	}
	if strictHTTPJSON(data, &input) != nil || input.Approval == nil || !httpReturnV2(*input.Approval) || !httpHashPattern.MatchString(input.TxHash) {
		httpFailure(w, http.StatusBadRequest, "invalid_return_reconciliation")
		return
	}
	receipt, err := backend.ReconcileClaimReturn(ctx, *input.Approval, strings.ToUpper(input.TxHash))
	if err != nil {
		httpFailure(w, http.StatusConflict, "return_proof_unavailable")
		return
	}
	a := input.Approval
	if receipt.Version != 2 || receipt.TicketID != a.TicketID || receipt.MarketID != a.MarketID || receipt.LegID != a.LegID || receipt.EntitlementID != a.EntitlementID || receipt.AllocationID != a.Allocation.AllocationID || receipt.OperationID != a.OperationID || receipt.ClaimID != a.ClaimID || receipt.OwnerID != a.OwnerID || receipt.ClaimKind != a.ClaimKind || receipt.AmountUWolo != a.AmountUWolo ||
		receipt.TxHash != strings.ToUpper(input.TxHash) || receipt.Height <= 0 || !httpHashPattern.MatchString(receipt.BlockHash) || receipt.CreditAuthorized ||
		(receipt.ReceiptID != "wolo-1:"+receipt.TxHash+":0" && receipt.ReceiptID != "wolo-1:"+receipt.TxHash+":1") {
		httpFailure(w, http.StatusServiceUnavailable, "return_receipt_identity_unverifiable")
		return
	}
	httpWrite(w, http.StatusOK, receipt)
}

func httpReturnV2(a ReturnApproval) bool {
	return a.Version == 2 && httpOperationPattern.MatchString(a.OperationID) && a.ClaimID != "" && a.OwnerID != "" && a.TicketID != "" && a.MarketID != "" && a.LegID != "" && a.EntitlementID != "" && a.Allocation != nil && a.Allocation.Version == 2 && a.Allocation.AllocationID != ""
}

func (h *privateHTTPHandler) authorized(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	ip := net.ParseIP(host)
	if err != nil || ip == nil || !ip.IsLoopback() || len(r.Header.Values("Origin")) != 0 || len(r.Header.Values("Authorization")) != 1 {
		return false
	}
	header := r.Header.Get("Authorization")
	if !strings.HasPrefix(header, "Bearer ") || len(header) > 519 {
		return false
	}
	digest := sha256.Sum256([]byte(strings.TrimPrefix(header, "Bearer ")))
	return subtle.ConstantTimeCompare(digest[:], h.tokenDigest[:]) == 1
}

func (h *privateHTTPHandler) accepting(ctx context.Context) bool {
	ok, _ := h.availability(ctx)
	return ok
}
func (h *privateHTTPHandler) availability(ctx context.Context) (bool, RuntimeCustodyCapability) {
	if !h.identity.Accepting || h.authorize == nil || ctx.Err() != nil || !h.authorize(ctx) {
		return false, RuntimeCustodyCapability{}
	}
	if h.custodyCapability == nil {
		return true, RuntimeCustodyCapability{}
	}
	c := h.custodyCapability(ctx)
	return c.Available(ctx), c
}

func (h *privateHTTPHandler) health(ctx context.Context, w http.ResponseWriter) {
	i := h.identity
	var capability RuntimeCustodyCapability
	i.Accepting, capability = h.availability(ctx)
	response := map[string]any{
		"ok": i.Accepting, "protocol": 1, "chainId": "wolo-1", "custodyRole": httpCustodyRole,
		"vaultAddress": i.VaultAddress, "keyFingerprint": i.KeyFingerprint, "exclusiveSignOnly": i.Accepting,
		"accepting": i.Accepting, "chain_id": "wolo-1", "signer_role": httpCustodyRole,
		"vault_address": i.VaultAddress, "build_sha256": i.BuildSHA256,
		"durable_one_shot": true, "replay_after_restart_forbidden": true, "refunds_require_chain_proof": true,
		"execution_protocol": 2, "owner_bound_wager_reservation_required": true, "custody_capability": "UNAVAILABLE",
	}
	if i.Accepting && capability.grant != nil {
		response["custody_capability"] = "AVAILABLE"
		response["custody_capability_version"] = "war-satchel-runtime-custody-v1"
		response["custody_capability_expires_at"] = capability.ExpiresAt().UTC().Format(time.RFC3339Nano)
	}
	if i.Accepting && i.ExclusiveAuthorityVerified {
		response["custody_mnemonic_shared_with_other_roles"] = false
	}
	httpWrite(w, http.StatusOK, response)
}

func (h *privateHTTPHandler) result(w http.ResponseWriter, id string, result Result, err error, allowAccepted bool, reservedACK ...bool) {
	if err != nil {
		httpFailure(w, http.StatusConflict, "operation_refused_or_unknown")
		return
	}
	if result.OperationID != id {
		httpFailure(w, http.StatusServiceUnavailable, "operation_identity_unverifiable")
		return
	}
	switch result.Status {
	case "ACCEPTED", "UNKNOWN", "FAILED", "OBSERVED_NONCREDITING", "CONFIRMED", "REFUSED":
	default:
		httpFailure(w, http.StatusServiceUnavailable, "operation_status_unverifiable")
		return
	}
	if (result.Status == "ACCEPTED" || result.Status == "CONFIRMED") && (!result.DurableFenced || !httpHashPattern.MatchString(result.TxHash)) {
		httpFailure(w, http.StatusServiceUnavailable, "operation_evidence_unverifiable")
		return
	}
	reason := result.Reason
	if !httpReasonPattern.MatchString(reason) {
		reason = "execution_status_unavailable"
	}
	response := map[string]any{"operation_id": id, "request_id": id, "chain_id": "wolo-1", "signer_role": httpCustodyRole,
		"status": result.Status, "durable_request_fenced": result.DurableFenced,
		"kind": "unknown", "reason": reason,
	}
	if result.Status == "REFUSED" {
		response["kind"] = "refused"
	}
	if httpHashPattern.MatchString(result.TxHash) {
		response["tx_hash"] = strings.ToUpper(result.TxHash)
	}
	// The HD v1 name means an accepted one-shot broadcast. It does not mean
	// committed execution or authenticated finality; ticket commit separately
	// verifies chain evidence. Read-only reconciliation never creates this ACK.
	if allowAccepted && (result.Status == "ACCEPTED" || result.Status == "CONFIRMED") && result.DurableFenced && httpHashPattern.MatchString(result.TxHash) {
		response["kind"] = "broadcast_confirmed"
		response["txHash"] = strings.ToUpper(result.TxHash)
		response["broadcast_status"] = "accepted_once"
	}
	if len(reservedACK) == 1 && reservedACK[0] && result.Status == "ACCEPTED" {
		response["kind"] = "broadcast_accepted"
		response["confirmed"] = false
	}
	response["credit_authorized"] = false
	httpWrite(w, http.StatusOK, response)
}

func httpFailure(w http.ResponseWriter, status int, reason string) {
	httpWrite(w, status, map[string]any{"kind": "unknown", "reason": reason})
}
func httpWrite(w http.ResponseWriter, status int, response any) {
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(response)
}

func readPrivateJSON(w http.ResponseWriter, r *http.Request) ([]byte, int) {
	media, params, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" || (params["charset"] != "" && !strings.EqualFold(params["charset"], "utf-8")) || r.Header.Get("Content-Encoding") != "" {
		return nil, http.StatusUnsupportedMediaType
	}
	if r.ContentLength > HTTPMaxBodyBytes {
		return nil, http.StatusRequestEntityTooLarge
	}
	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, HTTPMaxBodyBytes))
	if err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			return nil, http.StatusRequestEntityTooLarge
		}
		return nil, http.StatusBadRequest
	}
	if !utf8.Valid(data) || !chainjson.Valid(data) {
		return nil, http.StatusBadRequest
	}
	if _, ok := chainjson.Object(data); !ok {
		return nil, http.StatusBadRequest
	}
	return data, 0
}

func strictHTTPJSON(data []byte, out any) error {
	if !exactHTTPFields(data, reflect.TypeOf(out).Elem()) {
		return errors.New("unknown_or_aliased_json_field")
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(out); err != nil {
		return err
	}
	if d.Decode(new(any)) != io.EOF {
		return errors.New("trailing_json")
	}
	return nil
}

// encoding/json otherwise accepts case-insensitive aliases such as RequestId
// alongside requestId. Require the exact published spelling at every struct.
func exactHTTPFields(data []byte, shape reflect.Type) bool {
	if shape == reflect.TypeOf(json.RawMessage{}) {
		return chainjson.Valid(data)
	}
	if shape.Kind() == reflect.Pointer {
		if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
			return true
		}
		return exactHTTPFields(data, shape.Elem())
	}
	if shape.Kind() == reflect.Slice || shape.Kind() == reflect.Array {
		if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
			return true
		}
		var entries []json.RawMessage
		if json.Unmarshal(data, &entries) != nil {
			return false
		}
		for _, entry := range entries {
			if !exactHTTPFields(entry, shape.Elem()) {
				return false
			}
		}
		return true
	}
	if shape.Kind() != reflect.Struct {
		return true
	}
	fields, ok := chainjson.Object(data)
	if !ok {
		return false
	}
	allowed := map[string]reflect.Type{}
	for i := 0; i < shape.NumField(); i++ {
		field := shape.Field(i)
		name := strings.Split(field.Tag.Get("json"), ",")[0]
		if name == "-" {
			continue
		}
		if name == "" {
			name = field.Name
		}
		allowed[name] = field.Type
	}
	for key, raw := range fields {
		field, exists := allowed[key]
		if !exists || !exactHTTPFields(raw, field) {
			return false
		}
	}
	return true
}

type httpCoin struct {
	Denom  string `json:"denom"`
	Amount string `json:"amount"`
}
type httpCamelWager struct {
	Protocol    int    `json:"protocol"`
	RequestID   string `json:"requestId"`
	ChainID     string `json:"chainId"`
	Sender      string `json:"senderAddress"`
	Recipient   string `json:"recipientAddress"`
	Denom       string `json:"denom"`
	AmountUWolo string `json:"amountUwolo"`
	Memo        string `json:"memo"`
	OwnerID     string `json:"ownerId,omitempty"`
}
type httpSnakeWager struct {
	RequestID string   `json:"request_id"`
	ChainID   string   `json:"chain_id"`
	Role      string   `json:"signer_role"`
	Sender    string   `json:"from_address"`
	Recipient string   `json:"to_address"`
	Amount    httpCoin `json:"amount"`
	Memo      string   `json:"memo"`
	OwnerID   string   `json:"owner_id,omitempty"`
}

func decodeWagerHTTP(data []byte) (TransferRequest, error) {
	fields, _ := chainjson.Object(data)
	var request TransferRequest
	if _, camel := fields["protocol"]; camel {
		var input httpCamelWager
		if err := strictHTTPJSON(data, &input); err != nil || input.Protocol != 1 {
			return request, errors.New("invalid_wager_protocol")
		}
		request = TransferRequest{OperationID: input.RequestID, ChainID: input.ChainID, Sender: input.Sender, Recipient: input.Recipient, Denom: input.Denom, AmountUWolo: input.AmountUWolo, Memo: input.Memo, Kind: "wager", OwnerID: input.OwnerID}
	} else {
		var input httpSnakeWager
		if err := strictHTTPJSON(data, &input); err != nil || input.Role != httpCustodyRole {
			return request, errors.New("invalid_wager_role")
		}
		request = TransferRequest{OperationID: input.RequestID, ChainID: input.ChainID, Sender: input.Sender, Recipient: input.Recipient, Denom: input.Amount.Denom, AmountUWolo: input.Amount.Amount, Memo: input.Memo, Kind: "wager", OwnerID: input.OwnerID}
	}
	if !httpOperationPattern.MatchString(request.OperationID) || request.ChainID != "wolo-1" || request.Denom != "uwolo" || request.Sender == "" || request.Recipient == "" || request.AmountUWolo == "" || request.Memo == "" {
		return TransferRequest{}, errors.New("invalid_wager_identity")
	}
	return request, nil
}

func decodeReservedWagerHTTP(data []byte) (TransferRequest, error) {
	var input struct {
		Protocol    int               `json:"protocol"`
		RequestID   string            `json:"request_id"`
		ChainID     string            `json:"chain_id"`
		Role        string            `json:"signer_role"`
		Sender      string            `json:"from_address"`
		Recipient   string            `json:"to_address"`
		Amount      httpCoin          `json:"amount"`
		Memo        string            `json:"memo"`
		OwnerID     string            `json:"owner_id"`
		Reservation *WagerReservation `json:"reservation"`
	}
	if strictHTTPJSON(data, &input) != nil || input.Protocol != 2 || input.Role != httpCustodyRole ||
		!httpOperationPattern.MatchString(input.RequestID) || input.ChainID != "wolo-1" || input.Amount.Denom != "uwolo" ||
		!ownerUIDPattern.MatchString(input.OwnerID) || input.Reservation == nil {
		return TransferRequest{}, errors.New("invalid_reserved_wager_contract")
	}
	return TransferRequest{OperationID: input.RequestID, ChainID: input.ChainID, Sender: input.Sender, Recipient: input.Recipient,
		Denom: input.Amount.Denom, AmountUWolo: input.Amount.Amount, Memo: input.Memo, Kind: "wager", OwnerID: input.OwnerID,
		Reservation: input.Reservation}, nil
}

type httpWithdrawal struct {
	Protocol     int                     `json:"protocol"`
	OperationID  string                  `json:"operation_id"`
	ChainID      string                  `json:"chain_id"`
	Sender       string                  `json:"from_address"`
	Recipient    string                  `json:"to_address"`
	Amount       httpCoin                `json:"amount"`
	Memo         string                  `json:"memo"`
	OwnerID      string                  `json:"owner_id"`
	Approval     *WithdrawalApproval     `json:"approval"`
	OwnerMandate *OwnerWithdrawalMandate `json:"owner_mandate"`
}

func decodeWithdrawalHTTP(data []byte) (TransferRequest, error) {
	var input httpWithdrawal
	if strictHTTPJSON(data, &input) != nil || input.Protocol != 1 || !httpOperationPattern.MatchString(input.OperationID) || input.ChainID != "wolo-1" || input.Amount.Denom != "uwolo" || input.OwnerID == "" || input.Approval == nil || input.OwnerMandate == nil {
		return TransferRequest{}, errors.New("invalid_withdrawal_contract")
	}
	return TransferRequest{OperationID: input.OperationID, ChainID: input.ChainID, Sender: input.Sender, Recipient: input.Recipient,
		Denom: input.Amount.Denom, AmountUWolo: input.Amount.Amount, Memo: input.Memo, OwnerID: input.OwnerID,
		Approval: input.Approval, OwnerMandate: input.OwnerMandate, Kind: "withdrawal"}, nil
}
