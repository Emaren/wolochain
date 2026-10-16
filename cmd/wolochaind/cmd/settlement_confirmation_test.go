package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	coretypes "github.com/cometbft/cometbft/rpc/core/types"
	cmttypes "github.com/cometbft/cometbft/types"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

const (
	c4TxHash       = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
	c4OtherHash    = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
	c4Signer       = "wolo1payout00000000000000000000000000000000"
	c4EscrowSigner = "wolo1escrow00000000000000000000000000000000"
	c4Recipient    = "wolo1recipient0000000000000000000000000000"
	c4Memo         = "payout:match-c4:user-1"
)

// These fixtures exercise only local HTTP and a synthetic CLI. They never use
// a keyring, production endpoint, or real transaction.
func c4Fixture() map[string]any {
	return map[string]any{
		"tx": map[string]any{"body": map[string]any{
			"memo": c4Memo,
			"messages": []any{map[string]any{
				"@type":        "/cosmos.bank.v1beta1.MsgSend",
				"from_address": c4Signer,
				"to_address":   c4Recipient,
				"amount":       []any{map[string]any{"denom": "uwolo", "amount": "700"}},
			}},
		}},
		"tx_response": map[string]any{
			"txhash": c4TxHash,
			"height": "123",
			"code":   0,
			"events": []any{c4Event(c4Signer, c4Recipient, "700uwolo")},
		},
	}
}

func c4Event(sender, recipient, amount string) map[string]any {
	return map[string]any{"type": "transfer", "attributes": []any{
		map[string]any{"key": "sender", "value": sender},
		map[string]any{"key": "recipient", "value": recipient},
		map[string]any{"key": "amount", "value": amount},
	}}
}

func c4TxResponse(f map[string]any) map[string]any { return f["tx_response"].(map[string]any) }
func c4Body(f map[string]any) map[string]any {
	return f["tx"].(map[string]any)["body"].(map[string]any)
}
func c4Message(f map[string]any) map[string]any {
	return c4Body(f)["messages"].([]any)[0].(map[string]any)
}

func c4Config(t *testing.T, payload string, status int) (settlementConfig, *atomic.Int32) {
	return c4ConfigWithRPC(t, payload, status, nil)
}

func c4ConfigWithRPC(t *testing.T, payload string, status int, rpcPayload []byte) (settlementConfig, *atomic.Int32) {
	t.Helper()
	requests := new(atomic.Int32)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/status" {
			_, _ = w.Write([]byte(`{"result":{"node_info":{"network":"wolo-1"}}}`))
			return
		}
		if r.URL.Path == "/tx" {
			if len(rpcPayload) == 0 {
				http.NotFound(w, r)
				return
			}
			_, _ = w.Write(rpcPayload)
			return
		}
		if !strings.HasPrefix(r.URL.Path, "/cosmos/tx/v1beta1/txs/") {
			t.Errorf("unexpected test-only request: %s", r.URL.Path)
			http.NotFound(w, r)
			return
		}
		requests.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(payload))
	}))
	t.Cleanup(server.Close)
	return settlementConfig{
		RPCHTTP: server.URL, RESTURL: server.URL, ChainID: "wolo-1",
		BaseDenom: "uwolo", AddressPrefix: "wolo", PayoutAddress: c4Signer,
		LookupTimeout: time.Second, ConfirmTimeout: 50 * time.Millisecond,
		ConfirmInterval: time.Millisecond, RequestTimeout: time.Second,
	}, requests
}

func c4JSON(t *testing.T, f map[string]any) string {
	t.Helper()
	b, err := json.Marshal(f)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestSettlementConfirmationRejectsIncompleteEvidence(t *testing.T) {
	tests := []struct {
		name    string
		mutate  func(map[string]any)
		payload string
	}{
		{name: "empty object", payload: `{}`},
		{name: "missing transaction response", mutate: func(f map[string]any) { delete(f, "tx_response") }},
		{name: "null transaction response", mutate: func(f map[string]any) { f["tx_response"] = nil }},
		{name: "empty transaction response", mutate: func(f map[string]any) { f["tx_response"] = map[string]any{} }},
		{name: "missing hash", mutate: func(f map[string]any) { delete(c4TxResponse(f), "txhash") }},
		{name: "empty hash", mutate: func(f map[string]any) { c4TxResponse(f)["txhash"] = "" }},
		{name: "mismatched hash", mutate: func(f map[string]any) { c4TxResponse(f)["txhash"] = c4OtherHash }},
		{name: "nonhex hash", mutate: func(f map[string]any) { c4TxResponse(f)["txhash"] = strings.Repeat("G", 64) }},
		{name: "short hash", mutate: func(f map[string]any) { c4TxResponse(f)["txhash"] = "AA" }},
		{name: "missing height", mutate: func(f map[string]any) { delete(c4TxResponse(f), "height") }},
		{name: "null height", mutate: func(f map[string]any) { c4TxResponse(f)["height"] = nil }},
		{name: "zero height", mutate: func(f map[string]any) { c4TxResponse(f)["height"] = "0" }},
		{name: "negative height", mutate: func(f map[string]any) { c4TxResponse(f)["height"] = "-1" }},
		{name: "invalid height", mutate: func(f map[string]any) { c4TxResponse(f)["height"] = "NaN" }},
		{name: "overflow height", mutate: func(f map[string]any) { c4TxResponse(f)["height"] = "9223372036854775808" }},
		{name: "null code", mutate: func(f map[string]any) { c4TxResponse(f)["code"] = nil }},
		{name: "negative code", mutate: func(f map[string]any) { c4TxResponse(f)["code"] = -1 }},
		{name: "overflow code", mutate: func(f map[string]any) { c4TxResponse(f)["code"] = uint64(4294967296) }},
		{name: "boolean code", mutate: func(f map[string]any) { c4TxResponse(f)["code"] = false }},
		{name: "fractional code", mutate: func(f map[string]any) { c4TxResponse(f)["code"] = 0.5 }},
		{name: "missing transaction", mutate: func(f map[string]any) { delete(f, "tx") }},
		{name: "null transaction", mutate: func(f map[string]any) { f["tx"] = nil }},
		{name: "missing body", mutate: func(f map[string]any) { f["tx"] = map[string]any{} }},
		{name: "null body", mutate: func(f map[string]any) { f["tx"].(map[string]any)["body"] = nil }},
		{name: "string body", mutate: func(f map[string]any) { f["tx"].(map[string]any)["body"] = "forged" }},
		{name: "missing messages", mutate: func(f map[string]any) { delete(c4Body(f), "messages") }},
		{name: "null messages", mutate: func(f map[string]any) { c4Body(f)["messages"] = nil }},
		{name: "empty messages", mutate: func(f map[string]any) { c4Body(f)["messages"] = []any{} }},
		{name: "missing send type", mutate: func(f map[string]any) { delete(c4Message(f), "@type") }},
		{name: "missing send amount", mutate: func(f map[string]any) { delete(c4Message(f), "amount") }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			f := c4Fixture()
			if test.mutate != nil {
				test.mutate(f)
			}
			payload := test.payload
			if payload == "" {
				payload = c4JSON(t, f)
			}
			cfg, _ := c4Config(t, payload, http.StatusOK)
			result, err := cfg.lookupSettlementTx(t.Context(), c4TxHash, settlementLookupExpectations{})
			if err != nil {
				return
			} // A transport/decoding error cannot confirm.
			if result.OK && result.Found && result.TxSuccess {
				t.Fatalf("incomplete evidence was promoted to successful committed payment: %+v", result)
			}
		})
	}
}

func TestSettlementConfirmationAcceptsLegitimateSuccessCodeSerialization(t *testing.T) {
	for _, omitted := range []bool{false, true} {
		name := "explicit zero"
		if omitted {
			name = "omitted proto3 zero"
		}
		t.Run(name, func(t *testing.T) {
			f := c4Fixture()
			if omitted {
				delete(c4TxResponse(f), "code")
			}
			cfg, _ := c4Config(t, c4JSON(t, f), http.StatusOK)
			result, err := cfg.lookupSettlementTx(t.Context(), strings.ToLower(c4TxHash), settlementLookupExpectations{Sender: c4Signer, Recipient: c4Recipient, AmountUWolo: "700"})
			if err != nil || !result.OK || !result.Found || !result.TxSuccess || !result.MatchedExpected {
				t.Fatalf("legitimate successful Cosmos response rejected: result=%+v err=%v", result, err)
			}
		})
	}
}

func TestSettlementConfirmationFailedExecutionCannotConfirm(t *testing.T) {
	f := c4Fixture()
	c4TxResponse(f)["code"] = 5
	c4TxResponse(f)["raw_log"] = "insufficient funds"
	cfg, _ := c4Config(t, c4JSON(t, f), http.StatusOK)
	result, err := cfg.lookupSettlementTx(t.Context(), c4TxHash, settlementLookupExpectations{})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Found || result.TxSuccess || result.Code != 5 {
		t.Fatalf("failed committed transaction lost its distinct failure state: %+v", result)
	}
}

func TestSettlementConfirmationWaitDoesNotPromoteEmptySuccess(t *testing.T) {
	cfg, _ := c4Config(t, `{}`, http.StatusOK)
	result, err := cfg.waitForTxConfirmation(t.Context(), c4TxHash, c4PayoutExpectations())
	if err == nil && result != nil && result.OK && result.Found && result.TxSuccess {
		t.Fatalf("wait loop confirmed empty HTTP-success response: %+v", result)
	}
}

func TestSettlementConfirmationNotFoundPollingIsReadOnly(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/status" {
			_, _ = w.Write([]byte(`{"result":{"node_info":{"network":"wolo-1"}}}`))
			return
		}
		if requests.Add(1) == 2 {
			cancel()
		}
		http.NotFound(w, r)
	}))
	defer server.Close()
	cfg := settlementConfig{RPCHTTP: server.URL, RESTURL: server.URL, ChainID: "wolo-1", BaseDenom: "uwolo",
		LookupTimeout: time.Second, ConfirmTimeout: time.Second, ConfirmInterval: time.Millisecond}
	result, err := cfg.waitForTxConfirmation(ctx, c4TxHash, c4PayoutExpectations())
	if result != nil && result.TxSuccess {
		t.Fatalf("canceled lookup confirmed: %+v", result)
	}
	if ctx.Err() == nil || requests.Load() != 2 {
		t.Fatalf("pending read polling did not stop promptly on cancellation: requests=%d err=%v context=%v", requests.Load(), err, ctx.Err())
	}
}

func TestSettlementConfirmationPayoutAcceptsCanonicalZeroAndEmptyMemo(t *testing.T) {
	for _, test := range []struct {
		name                  string
		stringZero, emptyMemo bool
	}{
		{name: "Cosmos uint32 string zero", stringZero: true},
		{name: "explicitly authorized empty memo", emptyMemo: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			f := c4Fixture()
			expected := c4PayoutExpectations()
			if test.emptyMemo {
				delete(c4Body(f), "memo")
				expected.Memo = ""
			}
			hash, rpc := c4StrictFixture(t, f)
			if test.stringZero {
				c4TxResponse(f)["code"] = "0"
			}
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			result, err := cfg.lookupSettlementTx(t.Context(), hash, expected)
			if err != nil || !result.OK || !result.TxSuccess || result.Status != "confirmed" || !result.MatchedExpected {
				t.Fatalf("canonical successful payout refused: result=%+v err=%v", result, err)
			}
		})
	}
}

func TestSettlementConfirmationPayoutPreservesSDKLogAndFeeRepresentations(t *testing.T) {
	f := c4Fixture()
	hash, rpc := c4StrictFixture(t, f)
	fee := c4Event(c4Signer, "wolo1fee", "25uwolo")
	send := c4Event(c4Signer, c4Recipient, "700uwolo")
	// SDK message logs omit antehandler fee events. The canonical legacy
	// flattened representation uses logs first, so its send ordinal stays zero.
	c4TxResponse(f)["logs"] = []any{map[string]any{"events": []any{send}}}
	c4TxResponse(f)["events"] = []any{fee, send}
	rpc.TxResult.Events = append([]abci.Event{{Type: "transfer", Attributes: []abci.EventAttribute{
		{Key: "sender", Value: c4Signer}, {Key: "recipient", Value: "wolo1fee"}, {Key: "amount", Value: "25uwolo"},
	}}}, rpc.TxResult.Events...)
	cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
	result, err := cfg.lookupSettlementTx(t.Context(), hash, c4PayoutExpectations())
	if err != nil || !result.OK || !result.TxSuccess || !result.MatchedExpected {
		t.Fatalf("legitimate fee plus message log representation rejected: result=%+v err=%v", result, err)
	}
	if len(result.Transfers) != 1 || result.MatchedTransferIndex == nil || *result.MatchedTransferIndex != 0 || result.ReceiptTransferIndex == nil || *result.ReceiptTransferIndex != 0 {
		t.Fatalf("log-first observation or body-effect receipt identity changed: %+v", result)
	}
	// Removing logs changes the observed ordinal to one. Receipt ownership must
	// retain the same bank-message effect index across source representations.
	delete(c4TxResponse(f), "logs")
	cfg2, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
	second, err := cfg2.lookupSettlementTx(t.Context(), hash, c4PayoutExpectations())
	if err != nil || !second.OK || !second.TxSuccess || second.MatchedTransferIndex == nil || *second.MatchedTransferIndex != 1 || second.ReceiptTransferIndex == nil || *second.ReceiptTransferIndex != 0 {
		t.Fatalf("representation-dependent receipt identity permits reuse: result=%+v err=%v", second, err)
	}
}

func TestSettlementConfirmationAmbiguousMatchIsNotAnObligation(t *testing.T) {
	transfer := settlementTransfer{Sender: c4Signer, Recipient: c4Recipient, Amount: "700", Denom: "uwolo"}
	match, ok := matchSettlementTransfer([]settlementTransfer{transfer, transfer}, settlementLookupExpectations{Sender: c4Signer, Recipient: c4Recipient, AmountUWolo: "700"})
	if ok || match != nil {
		t.Fatalf("ambiguous identical effects selected as a unique payout obligation: match=%+v ok=%v", match, ok)
	}
}

func c4PayoutExpectations() settlementLookupExpectations {
	return settlementLookupExpectations{
		Sender: c4Signer, Recipient: c4Recipient, AmountUWolo: "700", Denom: "uwolo",
		Memo: c4Memo, RequireMemo: true, RequirePayout: true,
	}
}

// The RPC bytes are actual protobuf TxRaw/TxBody, with a hash derived from
// those bytes. Synthetic signatures have no chain authority.
func c4StrictFixture(t *testing.T, f map[string]any) (string, coretypes.ResultTx) {
	t.Helper()
	bodyJSON, err := json.Marshal(c4Body(f))
	if err != nil {
		t.Fatal(err)
	}
	var body tx.TxBody
	if err := protojson.Unmarshal(bodyJSON, &body); err != nil {
		t.Fatal(err)
	}
	bodyBytes, err := proto.Marshal(&body)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := proto.Marshal(&tx.TxRaw{BodyBytes: bodyBytes, AuthInfoBytes: []byte("synthetic-auth"), Signatures: [][]byte{[]byte("synthetic-signature")}})
	if err != nil {
		t.Fatal(err)
	}
	transaction := cmttypes.Tx(raw)
	hash := strings.ToUpper(fmt.Sprintf("%X", transaction.Hash()))
	c4TxResponse(f)["txhash"] = hash
	return hash, coretypes.ResultTx{
		Hash: transaction.Hash(), Height: 123, Tx: transaction,
		TxResult: abci.ExecTxResult{Code: 0, Events: []abci.Event{{Type: "transfer", Attributes: []abci.EventAttribute{
			{Key: "sender", Value: c4Signer}, {Key: "recipient", Value: c4Recipient}, {Key: "amount", Value: "700uwolo"},
		}}}},
	}
}

func c4RPCJSON(t *testing.T, result coretypes.ResultTx) []byte {
	t.Helper()
	encoded, err := cmtjson.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	return []byte(`{"jsonrpc":"2.0","id":-1,"result":` + string(encoded) + `}`)
}

func TestSettlementConfirmationRequiresExactPayout(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any, *coretypes.ResultTx, *settlementLookupExpectations)
	}{
		{name: "authorized signer mismatch", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) {
			e.Sender = "wolo1other"
		}},
		{name: "authorized recipient mismatch", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) {
			e.Recipient = "wolo1other"
		}},
		{name: "authorized amount mismatch", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.AmountUWolo = "701" }},
		{name: "authorized denomination mismatch", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.Denom = "uother" }},
		{name: "durable memo mismatch", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) {
			e.Memo = "payout:another-obligation"
		}},
		{name: "empty memo expectation is enforced", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.Memo = "" }},
		{name: "missing signer expectation", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.Sender = "" }},
		{name: "missing recipient expectation", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.Recipient = "" }},
		{name: "missing amount expectation", mutate: func(_ map[string]any, _ *coretypes.ResultTx, e *settlementLookupExpectations) { e.AmountUWolo = "" }},
		{name: "REST forged sender", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["from_address"] = "wolo1other"
		}},
		{name: "REST forged recipient", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["to_address"] = "wolo1other"
		}},
		{name: "REST forged amount", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "uwolo", "amount": "701"}}
		}},
		{name: "foreign denomination", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "uother", "amount": "700"}}
		}},
		{name: "zero amount", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "uwolo", "amount": "0"}}
		}},
		{name: "duplicate coin", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "uwolo", "amount": "700"}, map[string]any{"denom": "uwolo", "amount": "700"}}
		}},
		{name: "additional bank message", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Body(f)["messages"] = append(c4Body(f)["messages"].([]any), c4Message(f))
		}},
		{name: "additional unknown message", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Body(f)["messages"] = append(c4Body(f)["messages"].([]any), map[string]any{"@type": "/unknown.Message"})
		}},
		{name: "memo absent", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			delete(c4Body(f), "memo")
		}},
		{name: "memo differs", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4Body(f)["memo"] = "payout:another-obligation"
		}},
		{name: "event recipient differs", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4TxResponse(f)["events"] = []any{c4Event(c4Signer, "wolo1other", "700uwolo")}
		}},
		{name: "event amount differs", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4TxResponse(f)["events"] = []any{c4Event(c4Signer, c4Recipient, "701uwolo")}
		}},
		{name: "event absent", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			delete(c4TxResponse(f), "events")
		}},
		{name: "logs cannot invent absent RPC effect", mutate: func(f map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4TxResponse(f)["logs"] = []any{map[string]any{"events": []any{c4Event(c4Signer, c4Recipient, "700uwolo")}}}
			delete(c4TxResponse(f), "events")
			rpc.TxResult.Events = nil
		}},
		{name: "same event twice", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4TxResponse(f)["events"] = []any{c4Event(c4Signer, c4Recipient, "700uwolo"), c4Event(c4Signer, c4Recipient, "700uwolo")}
		}},
		{name: "event malformed duplicate attribute", mutate: func(f map[string]any, _ *coretypes.ResultTx, _ *settlementLookupExpectations) {
			c4TxResponse(f)["events"] = []any{map[string]any{"type": "transfer", "attributes": []any{map[string]any{"key": "sender", "value": c4Signer}, map[string]any{"key": "recipient", "value": c4Recipient}, map[string]any{"key": "amount", "value": "700uwolo"}, map[string]any{"key": "amount", "value": "701uwolo"}}}}
		}},
		{name: "RPC hash differs", mutate: func(_ map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) {
			rpc.Hash = []byte(strings.Repeat("B", 32))
		}},
		{name: "RPC bytes differ despite unchanged hash", mutate: func(_ map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) {
			rpc.Tx = append(rpc.Tx, 1)
		}},
		{name: "RPC failed while REST succeeds", mutate: func(_ map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) {
			rpc.TxResult.Code = 7
		}},
		{name: "RPC height differs", mutate: func(_ map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) { rpc.Height++ }},
		{name: "RPC zero height", mutate: func(_ map[string]any, rpc *coretypes.ResultTx, _ *settlementLookupExpectations) { rpc.Height = 0 }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			f := c4Fixture()
			hash, rpc := c4StrictFixture(t, f)
			expected := c4PayoutExpectations()
			test.mutate(f, &rpc, &expected)
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			result, err := cfg.lookupSettlementTx(t.Context(), hash, expected)
			if err == nil && result.OK && result.Found && result.TxSuccess {
				t.Fatalf("mismatched payout evidence confirmed: %+v", result)
			}
		})
	}
}

func TestSettlementConfirmationPayoutRPCSuccessAndDistinctFeeOrdinal(t *testing.T) {
	for _, omittedZero := range []bool{false, true} {
		t.Run(fmt.Sprintf("omittedzero=%t", omittedZero), func(t *testing.T) {
			f := c4Fixture()
			hash, rpc := c4StrictFixture(t, f)
			// A separate fee must retain its ordinal and cannot replace the payout.
			c4TxResponse(f)["events"] = []any{c4Event(c4Signer, "wolo1fee", "25uwolo"), c4Event(c4Signer, c4Recipient, "700uwolo")}
			rpc.TxResult.Events = append([]abci.Event{{Type: "transfer", Attributes: []abci.EventAttribute{{Key: "sender", Value: c4Signer}, {Key: "recipient", Value: "wolo1fee"}, {Key: "amount", Value: "25uwolo"}}}}, rpc.TxResult.Events...)
			if omittedZero {
				delete(c4TxResponse(f), "code")
			}
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			result, err := cfg.lookupSettlementTx(t.Context(), strings.ToLower(hash), c4PayoutExpectations())
			if err != nil || !result.OK || !result.Found || !result.TxSuccess || !result.MatchedExpected {
				t.Fatalf("exact payout rejected: result=%+v err=%v", result, err)
			}
			if result.MatchingTransferCount != 1 || result.MatchedTransferIndex == nil || *result.MatchedTransferIndex != 1 || len(result.Transfers) != 2 {
				t.Fatalf("distinct fee and payout identities collapsed: %+v", result)
			}
			otherObligation := c4PayoutExpectations()
			otherObligation.Memo = "payout:match-c4:user-2"
			reused, err := cfg.lookupSettlementTx(t.Context(), hash, otherObligation)
			if err == nil && reused.OK && reused.Found && reused.TxSuccess {
				t.Fatalf("one effect satisfied another durable request memo: %+v", reused)
			}
		})
	}
}

func TestSettlementConfirmationRejectsIncompleteRPCBytes(t *testing.T) {
	tests := []struct {
		name, raw string
		mutate    func(map[string]any)
	}{
		{name: "empty envelope", raw: `{}`},
		{name: "null envelope", raw: `null`},
		{name: "array envelope", raw: `[]`},
		{name: "missing result", mutate: func(f map[string]any) { delete(f, "result") }},
		{name: "null result", mutate: func(f map[string]any) { f["result"] = nil }},
		{name: "RPC error with forged result", mutate: func(f map[string]any) { f["error"] = map[string]any{"code": -32603, "message": "unavailable"} }},
		{name: "missing protocol version", mutate: func(f map[string]any) { delete(f, "jsonrpc") }},
		{name: "missing execution", mutate: func(f map[string]any) { delete(f["result"].(map[string]any), "tx_result") }},
		{name: "null execution", mutate: func(f map[string]any) { f["result"].(map[string]any)["tx_result"] = nil }},
		{name: "null execution code", mutate: func(f map[string]any) { f["result"].(map[string]any)["tx_result"].(map[string]any)["code"] = nil }},
		{name: "negative execution code", mutate: func(f map[string]any) { f["result"].(map[string]any)["tx_result"].(map[string]any)["code"] = -1 }},
		{name: "missing transaction bytes", mutate: func(f map[string]any) { delete(f["result"].(map[string]any), "tx") }},
		{name: "empty transaction bytes", mutate: func(f map[string]any) { f["result"].(map[string]any)["tx"] = "" }},
		{name: "invalid base64 bytes", mutate: func(f map[string]any) { f["result"].(map[string]any)["tx"] = "!?" }},
		{name: "missing raw hash", mutate: func(f map[string]any) { delete(f["result"].(map[string]any), "hash") }},
		{name: "missing committed height", mutate: func(f map[string]any) { delete(f["result"].(map[string]any), "height") }},
		{name: "trailing forged object", raw: `{"jsonrpc":"2.0","result":{}} {}`},
		{name: "duplicate result keys", raw: `{"jsonrpc":"2.0","result":{},"result":{}}`},
		{name: "oversized JSON", raw: `{"padding":"` + strings.Repeat("x", (1<<20)+1) + `"}`},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			f := c4Fixture()
			hash, rpc := c4StrictFixture(t, f)
			raw := test.raw
			if raw == "" {
				var envelope map[string]any
				if err := json.Unmarshal(c4RPCJSON(t, rpc), &envelope); err != nil {
					t.Fatal(err)
				}
				test.mutate(envelope)
				bytes, err := json.Marshal(envelope)
				if err != nil {
					t.Fatal(err)
				}
				raw = string(bytes)
			}
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, []byte(raw))
			result, err := cfg.lookupSettlementTx(t.Context(), hash, c4PayoutExpectations())
			if err == nil && (result.TxSuccess || result.Status == "confirmed") {
				t.Fatalf("incomplete or forged RPC bytes confirmed payment: %+v", result)
			}
		})
	}
}

func TestSettlementConfirmationBroadcastDoesNotRetryUnverifiablePayment(t *testing.T) {
	f := c4Fixture()
	hash, rpc := c4StrictFixture(t, f)
	failed := c4Fixture()
	_, failedRPC := c4StrictFixture(t, failed)
	c4TxResponse(failed)["code"] = 5
	failedRPC.TxResult.Code = 5
	for _, test := range []struct {
		name, rest, outcome, confirmation string
		status                            int
		rpc                               coretypes.ResultTx
	}{
		{"empty success", `{}`, "accepted", "unverifiable", http.StatusOK, rpc},
		{"not yet indexed", `{"code":5}`, "accepted", "pending", http.StatusNotFound, rpc},
		{"mismatched request memo", strings.Replace(c4JSON(t, f), c4Memo, "another-request", 1), "accepted", "unverifiable", http.StatusOK, rpc},
		{"exact payment", c4JSON(t, f), "confirmed", "confirmed", http.StatusOK, rpc},
		{"committed execution failure", c4JSON(t, failed), "failed", "failed", http.StatusOK, failedRPC},
	} {
		t.Run(test.name, func(t *testing.T) {
			cfg, _ := c4ConfigWithRPC(t, test.rest, test.status, c4RPCJSON(t, test.rpc))
			counterPath := filepath.Join(t.TempDir(), "synthetic-invocations")
			cliPath := filepath.Join(t.TempDir(), "synthetic-broadcast.sh")
			script := "#!/bin/sh\nprintf 'one\\n' >> '" + counterPath + "'\nprintf '%s\\n' '{\"txhash\":\"" + hash + "\",\"code\":0}'\n"
			if err := os.WriteFile(cliPath, []byte(script), 0o700); err != nil {
				t.Fatal(err)
			}
			cfg.ExecutablePath, cfg.ExecutableInterpreter = cliPath, "/bin/sh"
			cfg.PayoutKeyName, cfg.BroadcastMode = "synthetic", "sync"
			cfg.StateDir = t.TempDir()
			result := cfg.broadcastPayout(t.Context(), normalizedSettlementRequest{RequestID: c4Memo, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}, c4Signer)
			if result.Status != test.outcome || result.ConfirmationStatus != test.confirmation || result.Retryable {
				t.Fatalf("broadcast/confirmation state or retry safety is wrong: %+v", result)
			}
			if result.TxHash != hash {
				t.Fatalf("accepted hash lost: %+v", result)
			}
			calls, err := os.ReadFile(counterPath)
			if err != nil || string(calls) != "one\n" {
				t.Fatalf("broadcast executed more than once: %q err=%v", calls, err)
			}
		})
	}
}

func TestSettlementConfirmationBothSignerRolesRemainAcceptedWhenUnverifiable(t *testing.T) {
	for _, role := range []string{"payout", "escrow"} {
		t.Run(role, func(t *testing.T) {
			cfg, _ := c4Config(t, `{}`, http.StatusOK)
			counterPath := filepath.Join(t.TempDir(), "synthetic-invocations")
			cliPath := filepath.Join(t.TempDir(), "synthetic-broadcast.sh")
			script := "#!/bin/sh\nprintf '%s\\n' \"$4\" >> '" + counterPath + "'\nprintf '%s\\n' '{\"txhash\":\"" + c4TxHash + "\",\"code\":0}'\n"
			if err := os.WriteFile(cliPath, []byte(script), 0o700); err != nil {
				t.Fatal(err)
			}
			cfg.ExecutablePath, cfg.ExecutableInterpreter = cliPath, "/bin/sh"
			cfg.PayoutKeyName, cfg.EscrowKeyName = "synthetic-payout", "synthetic-escrow"
			cfg.BroadcastMode = "sync"
			request := normalizedSettlementRequest{RequestID: c4Memo, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo, SignerRole: role}
			var result settlementExecuteResponse
			if role == "escrow" {
				result = cfg.broadcastEscrowTransfer(t.Context(), request, c4EscrowSigner)
			} else {
				result = cfg.broadcastPayout(t.Context(), request, c4Signer)
			}
			if !result.OK || result.Status != "accepted" || result.ConfirmationStatus != "unverifiable" || result.Retryable || result.SignerRole != role {
				t.Fatalf("unverifiable broadcast lost accepted outcome or signer separation: %+v", result)
			}
			calls, err := os.ReadFile(counterPath)
			if err != nil || string(calls) != "synthetic-"+role+"\n" {
				t.Fatalf("wrong signer role or repeated execution: %q err=%v", calls, err)
			}
		})
	}
}

func TestSettlementConfirmationExecuteReplaysStoredAcceptedWithoutBroadcast(t *testing.T) {
	for _, role := range []string{"payout", "escrow"} {
		t.Run(role, func(t *testing.T) {
			balances := map[string]string{c4Signer: "10000000", c4EscrowSigner: "10000000"}
			chain := newMockSettlementChainHandler(balances)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasPrefix(r.URL.Path, "/cosmos/tx/v1beta1/txs/") {
					_, _ = w.Write([]byte(`{}`))
					return
				}
				chain.ServeHTTP(w, r)
			}))
			defer server.Close()
			cfg := newTestSettlementConfig(t, c4Signer, balances)
			cfg.RPCHTTP, cfg.RESTURL = server.URL, server.URL
			cfg.EscrowKeyName, cfg.EscrowAddress = "escrow", c4EscrowSigner
			fakeCLI := writeFakeSettlementExecutableWithTxsAndKeys(t, map[string]string{"payout": c4Signer, "escrow": c4EscrowSigner}, map[string]string{c4Recipient: c4TxHash})
			counterPath := filepath.Join(t.TempDir(), "synthetic-broadcast-count")
			wrapperPath := filepath.Join(t.TempDir(), "synthetic-cli-wrapper.sh")
			script := "#!/bin/sh\nif [ \"$1\" = \"tx\" ]; then printf 'one\\n' >> '" + counterPath + "'; fi\nexec /bin/sh '" + fakeCLI + "' \"$@\"\n"
			if err := os.WriteFile(wrapperPath, []byte(script), 0o700); err != nil {
				t.Fatal(err)
			}
			cfg.ExecutablePath, cfg.ExecutableInterpreter = wrapperPath, "/bin/sh"
			request := settlementExecuteRequest{RequestID: "c4:accepted-replay:" + role, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}
			execute := cfg.executeSettlement
			if role == "escrow" {
				execute = cfg.executeEscrowTransfer
			}
			first, err := execute(t.Context(), request)
			if err != nil || !first.OK || first.Status != "accepted" || first.ConfirmationStatus != "unverifiable" || first.Retryable || first.IdempotentReplay {
				t.Fatalf("first synthetic execution did not persist accepted uncertainty: result=%+v err=%v", first, err)
			}
			second, err := execute(t.Context(), request)
			if err != nil || !second.OK || second.Status != "accepted" || second.ConfirmationStatus != "unverifiable" || !second.IdempotentReplay || second.Retryable || second.TxHash != first.TxHash {
				t.Fatalf("stored accepted uncertainty was not replayed: result=%+v err=%v", second, err)
			}
			calls, err := os.ReadFile(counterPath)
			if err != nil || string(calls) != "one\n" {
				t.Fatalf("accepted replay sent another transaction: %q err=%v", calls, err)
			}
		})
	}
}
