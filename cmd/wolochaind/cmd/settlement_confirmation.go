package cmd

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	sdkmath "cosmossdk.io/math"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	core "github.com/cometbft/cometbft/rpc/core/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/emaren/wolochain/internal/chainevents"
	"github.com/emaren/wolochain/internal/chainjson"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

// This client only reads server-configured chain sources. Its observations are
// trusted-node evidence, not independent consensus authentication or Satchel credit.
var settlementConfirmationClient = &http.Client{
	Timeout: 5 * time.Second,
	Transport: &http.Transport{DisableCompression: true, ResponseHeaderTimeout: 2 * time.Second,
		DialContext:            (&net.Dialer{Timeout: 2 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		TLSHandshakeTimeout:    2 * time.Second,
		MaxResponseHeaderBytes: 16384, MaxConnsPerHost: 4, MaxIdleConns: 8,
		MaxIdleConnsPerHost: 4, IdleConnTimeout: 30 * time.Second},
	CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect refused") },
}

func readSettlementEvidenceJSON(ctx context.Context, target string) ([]byte, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Accept-Encoding", "identity")
	resp, err := settlementConfirmationClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, resp.StatusCode, nil
	}
	if resp.StatusCode != http.StatusOK || (resp.Header.Get("Content-Encoding") != "" && resp.Header.Get("Content-Encoding") != "identity") {
		return nil, resp.StatusCode, errors.New("source unavailable")
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, settlementJSONLimit+1))
	if err != nil || len(data) > settlementJSONLimit || !chainjson.ValidFolded(data) {
		return nil, resp.StatusCode, errors.New("invalid bounded JSON")
	}
	return data, resp.StatusCode, nil
}

func (cfg settlementConfig) fetchSettlementConfirmationChainID(ctx context.Context) (string, error) {
	data, _, err := readSettlementEvidenceJSON(ctx, strings.TrimRight(cfg.RPCHTTP, "/")+"/status")
	if err != nil {
		return "", err
	}
	var status tenderStatusResponse
	if json.Unmarshal(data, &status) != nil || status.Result.NodeInfo.Network == "" {
		return "", errors.New("missing chain identity")
	}
	return status.Result.NodeInfo.Network, nil
}

func (cfg settlementConfig) unverifiableSettlementTx(hash, code string) settlementLookupResponse {
	return settlementLookupResponse{Status: "unverifiable", FailureCode: code,
		Detail: "transaction evidence could not satisfy the settlement proof contract", ChainID: cfg.ChainID,
		CanonicalTxLookup: cfg.txLookupURL(hash), CanonicalTxLookupPreferred: cfg.preferredTxLookupURL(hash),
		CanonicalTxLookupInternal: cfg.txLookupURL(hash), CanonicalTxLookupPublic: cfg.publicTxLookupURL(hash)}
}

func (cfg settlementConfig) readSettlementTx(ctx context.Context, hash string) (restTxLookupResponse, *tx.TxBody, int, string) {
	var payload restTxLookupResponse
	data, status, err := readSettlementEvidenceJSON(ctx, cfg.txLookupURL(hash))
	if err != nil {
		return payload, nil, status, "LOOKUP_FAILED"
	}
	if status == http.StatusNotFound {
		return payload, nil, status, ""
	}
	fields, ok := chainjson.Object(data)
	if !ok {
		return payload, nil, status, "TX_RESPONSE_INVALID"
	}
	result, ok := chainjson.Object(fields["tx_response"])
	if !ok {
		return payload, nil, status, "TX_RESPONSE_INVALID"
	}
	code, ok := chainjson.ExecutionCode(result)
	if !ok {
		return payload, nil, status, "TX_CODE_INVALID"
	}
	// Normalize legitimate uint32 JSON string/omitted-zero forms before decoding.
	result["code"] = json.RawMessage(strconv.FormatUint(uint64(code), 10))
	fields["tx_response"], _ = json.Marshal(result)
	normalized, _ := json.Marshal(fields)
	if json.Unmarshal(normalized, &payload) != nil {
		return payload, nil, status, "TX_RESPONSE_INVALID"
	}
	if !isHexHash(payload.TxResponse.TxHash) || !strings.EqualFold(payload.TxResponse.TxHash, hash) {
		return payload, nil, status, "TX_HASH_MISMATCH"
	}
	height, err := strconv.ParseInt(payload.TxResponse.Height, 10, 64)
	if err != nil || height <= 0 || strconv.FormatInt(height, 10) != payload.TxResponse.Height {
		return payload, nil, status, "TX_HEIGHT_INVALID"
	}
	transaction, ok := chainjson.Object(fields["tx"])
	if !ok {
		return payload, nil, status, "TX_BODY_INVALID"
	}
	if _, ok := chainjson.Object(transaction["body"]); !ok {
		return payload, nil, status, "TX_BODY_INVALID"
	}
	var body tx.TxBody
	if protojson.Unmarshal(transaction["body"], &body) != nil || len(body.Messages) == 0 || len(body.Messages) > settlementMaxRunPayouts {
		return payload, nil, status, "TX_BODY_INVALID"
	}
	for _, message := range body.Messages {
		if message == nil || message.TypeUrl == "" {
			return payload, nil, status, "TX_BODY_INVALID"
		}
		if message.TypeUrl != "/cosmos.bank.v1beta1.MsgSend" {
			continue
		}
		var send bank.MsgSend
		if proto.Unmarshal(message.Value, &send) != nil || send.FromAddress == "" || send.ToAddress == "" || len(send.Amount) == 0 {
			return payload, nil, status, "TX_BODY_INVALID"
		}
		seen := map[string]bool{}
		for _, coin := range send.Amount {
			if coin == nil || len(coin.Amount) == 0 || len(coin.Amount) > 78 || coin.Amount[0] == '0' || (seen[coin.Denom] || sdk.ValidateDenom(coin.Denom) != nil) {
				return payload, nil, status, "TX_BODY_INVALID"
			}
			amount, valid := sdkmath.NewIntFromString(coin.Amount)
			if !valid || !amount.IsPositive() {
				return payload, nil, status, "TX_BODY_INVALID"
			}
			seen[coin.Denom] = true
		}
	}
	if chainevents.Validate(payload.TxResponse.Logs, payload.TxResponse.Events) != nil {
		return payload, nil, status, "TX_EVENTS_INVALID"
	}
	return payload, &body, status, ""
}

// verifySettlementPayout binds the configured node's actual transaction bytes,
// successful committed result and unique bank effect to one normalized request.
// It does not verify validator signatures, a light-client root or event provenance.
func (cfg settlementConfig) verifySettlementPayout(ctx context.Context, hash string, body *tx.TxBody, payload restTxLookupResponse, expected settlementLookupExpectations, response *settlementLookupResponse) string {
	if cfg.ChainID != settlementCanonicalChainID || cfg.BaseDenom != settlementCanonicalBaseDenom ||
		expected.Sender == "" || expected.Recipient == "" || expected.AmountUWolo == "" ||
		firstNonEmpty(expected.Denom, cfg.BaseDenom) != settlementCanonicalBaseDenom || !expected.RequireMemo {
		return "PAYOUT_CONTEXT_REQUIRED"
	}
	if len(body.Messages) != 1 || len(body.ExtensionOptions) != 0 || len(body.NonCriticalExtensionOptions) != 0 || body.Memo != expected.Memo {
		return "TX_PAYOUT_MISMATCH"
	}
	var send bank.MsgSend
	message := body.Messages[0]
	if message.TypeUrl != "/cosmos.bank.v1beta1.MsgSend" || proto.Unmarshal(message.Value, &send) != nil || len(send.ProtoReflect().GetUnknown()) != 0 ||
		send.FromAddress != expected.Sender || send.ToAddress != expected.Recipient || len(send.Amount) != 1 ||
		send.Amount[0].Denom != settlementCanonicalBaseDenom || send.Amount[0].Amount != expected.AmountUWolo {
		return "TX_PAYOUT_MISMATCH"
	}
	observed, failure := cfg.verifySettlementBytes(ctx, hash, body, payload)
	if failure != "" {
		return failure
	}
	if payload.TxResponse.Code != 0 {
		return ""
	} // Failed execution is never evidence of payment.
	wanted := settlementTransfer{Sender: expected.Sender, Recipient: expected.Recipient, Amount: expected.AmountUWolo, Denom: settlementCanonicalBaseDenom}
	if failure := verifySettlementEffect(payload, observed, wanted, response); failure != "" {
		return failure
	}
	receiptIndex := 0
	response.ReceiptTransferIndex = &receiptIndex
	return ""
}

// verifySettlementBytes shares the exact configured-node proof contract between
// payout and escrow. Agreement does not authenticate consensus independently.
func (cfg settlementConfig) verifySettlementBytes(ctx context.Context, hash string, body *tx.TxBody, payload restTxLookupResponse) (*core.ResultTx, string) {
	query := url.Values{"hash": {"0x" + hash}, "prove": {"false"}}
	data, status, err := readSettlementEvidenceJSON(ctx, strings.TrimRight(cfg.RPCHTTP, "/")+"/tx?"+query.Encode())
	if err != nil || status != http.StatusOK {
		return nil, "TX_BYTES_UNAVAILABLE"
	}
	envelope, ok := chainjson.Object(data)
	if !ok || string(envelope["jsonrpc"]) != `"2.0"` {
		return nil, "TX_RPC_INVALID"
	}
	if raw := envelope["error"]; len(raw) > 0 && !bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, "TX_BYTES_UNAVAILABLE"
	}
	result, ok := chainjson.Object(envelope["result"])
	if !ok {
		return nil, "TX_RPC_INVALID"
	}
	execution, ok := chainjson.Object(result["tx_result"])
	if !ok {
		return nil, "TX_RPC_INVALID"
	}
	code, ok := chainjson.ExecutionCode(execution)
	if !ok {
		return nil, "TX_CODE_INVALID"
	}
	execution["code"] = json.RawMessage(strconv.FormatUint(uint64(code), 10))
	result["tx_result"], _ = json.Marshal(execution)
	normalized, _ := json.Marshal(result)
	var observed core.ResultTx
	if cmtjson.Unmarshal(normalized, &observed) != nil {
		return nil, "TX_RPC_INVALID"
	}
	if len(observed.Tx) == 0 || len(observed.Tx) > 65536 || !strings.EqualFold(hex.EncodeToString(observed.Hash), hash) || !bytes.Equal(observed.Tx.Hash(), observed.Hash) {
		return nil, "TX_BYTES_MISMATCH"
	}
	if strconv.FormatInt(observed.Height, 10) != payload.TxResponse.Height || observed.Height <= 0 || code != payload.TxResponse.Code {
		return nil, "TX_RESULT_MISMATCH"
	}
	var raw tx.TxRaw
	var actual tx.TxBody
	if proto.Unmarshal(observed.Tx, &raw) != nil || len(raw.ProtoReflect().GetUnknown()) != 0 || len(raw.AuthInfoBytes) == 0 || len(raw.Signatures) != 1 || len(raw.Signatures[0]) == 0 ||
		proto.Unmarshal(raw.BodyBytes, &actual) != nil || !proto.Equal(&actual, body) {
		return nil, "TX_BYTES_MISMATCH"
	}
	return &observed, ""
}

func verifySettlementEffect(payload restTxLookupResponse, observed *core.ResultTx, wanted settlementTransfer, response *settlementLookupResponse) string {
	index, count := -1, 0
	for i, effect := range response.Transfers {
		if effect == wanted {
			index = i
			count++
		}
	}
	response.MatchingTransferCount = count
	if count != 1 {
		return "TX_TRANSFER_AMBIGUOUS"
	}
	// Logs may omit the fee effect included in top-level events. Preserve the
	// legacy log-first list, require it to be an ordered subsequence, and require
	// exactly one wanted effect in EACH supplied representation.
	fallback := chainevents.Extract(nil, payload.TxResponse.Events)
	if len(fallback) > 0 && len(payload.TxResponse.Logs) > 0 && !settlementEffectSubsequence(response.Transfers, fallback) {
		return "TX_EVENTS_INCONSISTENT"
	}
	if len(fallback) > 0 {
		matches := 0
		for _, effect := range fallback {
			if effect == wanted {
				matches++
			}
		}
		if matches != 1 {
			return "TX_TRANSFER_AMBIGUOUS"
		}
	}

	effects := make([]chainevents.Event, len(observed.TxResult.Events))
	for i, event := range observed.TxResult.Events {
		effects[i].Type = event.Type
		for _, attr := range event.Attributes {
			effects[i].Attributes = append(effects[i].Attributes, chainevents.Attribute{Key: attr.Key, Value: attr.Value})
		}
	}
	if chainevents.Validate(nil, effects) != nil {
		return "TX_EVENTS_INCONSISTENT"
	}
	rpcEffects := chainevents.Extract(nil, effects)
	rpcMatches := 0
	for _, effect := range rpcEffects {
		if effect == wanted {
			rpcMatches++
		}
	}
	if rpcMatches != 1 {
		return "TX_TRANSFER_AMBIGUOUS"
	}
	if !settlementEffectsEqual(rpcEffects, fallback) {
		return "TX_EVENTS_INCONSISTENT"
	}
	response.MatchedExpected = true
	response.MatchedTransfer = &wanted
	response.MatchedTransferIndex = &index
	return ""
}

// Escrow confirmation supports distinct MsgSend messages/coins, but exactly one
// decoded bank send and one committed effect must satisfy the supplied filters.
// A generic lookup or search result alone remains discovery, never funding proof.
func (cfg settlementConfig) verifySettlementEscrow(ctx context.Context, hash string, body *tx.TxBody, payload restTxLookupResponse, expected settlementLookupExpectations, response *settlementLookupResponse) string {
	if cfg.ChainID != settlementCanonicalChainID || cfg.BaseDenom != settlementCanonicalBaseDenom ||
		expected.Recipient != cfg.EscrowAddress || !isWoloAddress(expected.Recipient, cfg.AddressPrefix) {
		return "ESCROW_CONTEXT_REQUIRED"
	}
	if payload.TxResponse.Code != 0 {
		return ""
	} // Preserve the distinct committed failure; it can never prove funding.
	observed, failure := cfg.verifySettlementBytes(ctx, hash, body, payload)
	if failure != "" {
		return failure
	}
	if len(body.ExtensionOptions) != 0 || len(body.NonCriticalExtensionOptions) != 0 {
		return "TX_ESCROW_MISMATCH"
	}
	var wanted settlementTransfer
	response.MatchingTransferCount = 0
	response.MatchedExpected = false
	response.MatchedTransfer = nil
	for _, effect := range response.Transfers {
		if effect.Recipient == expected.Recipient && effect.Denom == cfg.BaseDenom &&
			(expected.Sender == "" || effect.Sender == expected.Sender) &&
			(expected.AmountUWolo == "" || effect.Amount == expected.AmountUWolo) {
			wanted = effect
			response.MatchingTransferCount++
		}
	}
	if response.MatchingTransferCount == 0 {
		return "" // Caller reports the distinct requested-amount/sender mismatch.
	}
	if response.MatchingTransferCount != 1 {
		return "TX_TRANSFER_AMBIGUOUS"
	}
	if !isWoloAddress(wanted.Sender, cfg.AddressPrefix) {
		return "TX_ESCROW_MISMATCH"
	}
	sends := 0
	for _, message := range body.Messages {
		if message.TypeUrl != "/cosmos.bank.v1beta1.MsgSend" {
			continue
		}
		var send bank.MsgSend
		if proto.Unmarshal(message.Value, &send) != nil || len(send.ProtoReflect().GetUnknown()) != 0 {
			return "TX_BODY_INVALID"
		}
		for _, coin := range send.Amount {
			if send.FromAddress == wanted.Sender && send.ToAddress == wanted.Recipient && coin.Denom == wanted.Denom && coin.Amount == wanted.Amount {
				sends++
			}
		}
	}
	if sends != 1 {
		return "TX_ESCROW_MISMATCH"
	}
	return verifySettlementEffect(payload, observed, wanted, response)
}

func payoutConfirmationExpectations(request normalizedSettlementRequest, signer string) settlementLookupExpectations {
	return settlementLookupExpectations{Sender: signer, Recipient: request.ToAddress, AmountUWolo: request.AmountUWolo,
		Denom: settlementCanonicalBaseDenom, Memo: request.Memo, RequireMemo: true, RequirePayout: true}
}

// accepted is the broadcast outcome. ConfirmationStatus separately distinguishes
// unavailable/mismatched evidence from a pending index or a committed failure.
func (cfg settlementConfig) applySettlementConfirmation(ctx context.Context, response *settlementExecuteResponse, request normalizedSettlementRequest, signer string, result *settlementLookupResponse, err error) {
	response.Retryable = false
	response.OK = true
	response.Status = "accepted"
	response.ConfirmationStatus = "pending"
	response.Detail = "broadcast accepted; committed confirmation pending"
	if err != nil || (result != nil && !result.OK) {
		response.ConfirmationStatus = "unverifiable"
		response.FailureCode = "TX_CONFIRMATION_UNVERIFIABLE"
		if result != nil {
			response.FailureCode = firstNonEmpty(result.FailureCode, response.FailureCode)
		}
		response.Detail = "broadcast accepted; confirmation evidence is unverifiable; do not rebroadcast"
		return
	}
	if result == nil {
		return
	}
	response.Code = result.Code
	response.Codespace = result.Codespace
	response.RawLog = result.RawLog
	if !result.TxSuccess {
		response.OK = false
		response.Status = "failed"
		response.ConfirmationStatus = "failed"
		response.FailureCode = classifyRejectedTx(result.RawLog, result.Code)
		response.Detail = "committed transaction execution failed"
		return
	}
	if result.Status != "confirmed" || !result.MatchedExpected || result.MatchedTransferIndex == nil || result.ReceiptTransferIndex == nil {
		response.ConfirmationStatus = "unverifiable"
		response.FailureCode = "TX_CONFIRMATION_UNVERIFIABLE"
		return
	}
	if err := cfg.claimSettlementConfirmation(ctx, request, signer, response.TxHash, *result.ReceiptTransferIndex); err != nil {
		response.ConfirmationStatus = "unverifiable"
		response.FailureCode = "TX_RECEIPT_UNAVAILABLE"
		response.Detail = "broadcast accepted; unique durable receipt ownership could not be established; do not rebroadcast"
		return
	}
	response.Status = "confirmed"
	response.ConfirmationStatus = "confirmed"
	response.Detail = "exact payout confirmed by configured chain sources"
}

func settlementEffectsEqual(left, right []chainevents.Transfer) bool {
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
}
func settlementEffectSubsequence(less, more []chainevents.Transfer) bool {
	next := 0
	for _, effect := range more {
		if next < len(less) && less[next] == effect {
			next++
		}
	}
	return next == len(less)
}
