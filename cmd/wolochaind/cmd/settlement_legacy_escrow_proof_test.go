package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	abci "github.com/cometbft/cometbft/abci/types"
	coretypes "github.com/cometbft/cometbft/rpc/core/types"
	"github.com/cosmos/btcutil/bech32"
)

// Addresses and protobuf transaction bytes are deterministic test data. These
// cases only contact httptest servers and never invoke a signer or keyring.
func legacyProofAddress(t *testing.T, seed byte) string {
	t.Helper()
	address, err := bech32.EncodeFromBase256("wolo", bytes.Repeat([]byte{seed}, 20))
	if err != nil {
		t.Fatal(err)
	}
	return address
}

func legacyEscrowProofFixture(t *testing.T) (map[string]any, string, coretypes.ResultTx, string, string) {
	t.Helper()
	sender, escrow := legacyProofAddress(t, 81), legacyProofAddress(t, 82)
	f := c4Fixture()
	c4Message(f)["from_address"] = sender
	c4Message(f)["to_address"] = escrow
	c4TxResponse(f)["events"] = []any{c4Event(sender, escrow, "700uwolo")}
	hash, rpc := c4StrictFixture(t, f)
	rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo")}
	return f, hash, rpc, sender, escrow
}

func legacyProofRPCEvent(sender, recipient, amount string) abci.Event {
	return abci.Event{Type: "transfer", Attributes: []abci.EventAttribute{
		{Key: "sender", Value: sender}, {Key: "recipient", Value: recipient}, {Key: "amount", Value: amount},
	}}
}

func TestLegacyEscrowRequiresExactCommittedEconomicProof(t *testing.T) {
	tests := []struct {
		name       string
		mutate     func(*testing.T, map[string]any, *coretypes.ResultTx)
		payload    string
		status     int
		missingRPC bool
		rehashBody bool
	}{
		{name: "empty HTTP success", payload: `{}`},
		{name: "null HTTP success", payload: `null`},
		{name: "missing transaction response", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) { delete(f, "tx_response") }},
		{name: "wrong returned transaction hash", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) { c4TxResponse(f)["txhash"] = c4OtherHash }},
		{name: "missing committed height", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) { delete(c4TxResponse(f), "height") }},
		{name: "zero committed height", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) { c4TxResponse(f)["height"] = "0" }},
		{name: "invalid execution code", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) { c4TxResponse(f)["code"] = false }},
		{name: "failed execution with matching event", mutate: func(_ *testing.T, f map[string]any, rpc *coretypes.ResultTx) {
			c4TxResponse(f)["code"] = 5
			rpc.TxResult.Code = 5
		}},
		{name: "malformed transaction body", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			f["tx"] = map[string]any{"body": "forged"}
		}},
		{name: "forged event sender", rehashBody: true, mutate: func(t *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4Message(f)["from_address"] = legacyProofAddress(t, 83)
		}},
		{name: "forged event recipient", rehashBody: true, mutate: func(t *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4Message(f)["to_address"] = legacyProofAddress(t, 83)
		}},
		{name: "forged event amount", rehashBody: true, mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "uwolo", "amount": "701"}}
		}},
		{name: "forged event denomination", rehashBody: true, mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4Message(f)["amount"] = []any{map[string]any{"denom": "ufake", "amount": "700"}}
		}},
		{name: "REST body disagrees with hashed transaction memo", mutate: func(_ *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4Body(f)["memo"] = "not the memo committed in these bytes"
		}},
		{name: "duplicate matching effects", mutate: func(_ *testing.T, f map[string]any, rpc *coretypes.ResultTx) {
			events := c4TxResponse(f)["events"].([]any)
			c4TxResponse(f)["events"] = append(events, events[0])
			rpc.TxResult.Events = append(rpc.TxResult.Events, rpc.TxResult.Events[0])
		}},
		{name: "conflicting log and top-level effects", mutate: func(t *testing.T, f map[string]any, _ *coretypes.ResultTx) {
			c4TxResponse(f)["logs"] = []any{map[string]any{"events": c4TxResponse(f)["events"]}}
			c4TxResponse(f)["events"] = []any{c4Event(c4Message(f)["from_address"].(string), legacyProofAddress(t, 83), "700uwolo")}
		}},
		{name: "committed result height disagreement", mutate: func(_ *testing.T, _ map[string]any, rpc *coretypes.ResultTx) { rpc.Height++ }},
		{name: "RPC bytes mismatch", mutate: func(_ *testing.T, _ map[string]any, rpc *coretypes.ResultTx) { rpc.Tx = append(rpc.Tx, byte(0)) }},
		{name: "unavailable transaction bytes", missingRPC: true},
		{name: "unconfirmed transaction", status: http.StatusNotFound},
		{name: "unavailable REST source", status: http.StatusServiceUnavailable},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			f, hash, rpc, sender, escrow := legacyEscrowProofFixture(t)
			if test.mutate != nil {
				test.mutate(t, f, &rpc)
			}
			if test.rehashBody {
				// REST and RPC agree on actual transaction bytes, but the events
				// falsely describe a different economic transfer. Byte agreement
				// alone must never establish the authorized bank-send effect.
				hash, rpc = c4StrictFixture(t, f)
				rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo")}
			}
			payload := test.payload
			if payload == "" {
				payload = c4JSON(t, f)
			}
			status := test.status
			if status == 0 {
				status = http.StatusOK
			}
			var rpcPayload []byte
			if !test.missingRPC {
				rpcPayload = c4RPCJSON(t, rpc)
			}
			cfg, _ := c4ConfigWithRPC(t, payload, status, rpcPayload)
			cfg.EscrowAddress = escrow
			result, err := cfg.verifyEscrowDeposit(t.Context(), hash, sender, "700")
			if err == nil && result.OK {
				t.Fatalf("inconsistent or unavailable economic evidence certified escrow funding: %+v lookup=%+v", result, result.Lookup)
			}
		})
	}
}

func TestLegacyEscrowPreservesCanonicalZeroAndDistinctTransfers(t *testing.T) {
	for _, zero := range []string{"explicit", "omitted", "string"} {
		t.Run(zero, func(t *testing.T) {
			f, _, _, sender, escrow := legacyEscrowProofFixture(t)
			// One unrelated bank send must remain distinct from the exact uwolo
			// obligation. A foreign-denom coin with the same amount is no proof.
			other := legacyProofAddress(t, 84)
			messages := c4Body(f)["messages"].([]any)
			c4Body(f)["messages"] = append(messages, map[string]any{
				"@type": "/cosmos.bank.v1beta1.MsgSend", "from_address": sender, "to_address": other,
				"amount": []any{map[string]any{"denom": "ufake", "amount": "700"}},
			})
			c4TxResponse(f)["events"] = []any{c4Event(sender, escrow, "700uwolo"), c4Event(sender, other, "700ufake")}
			hash, rpc := c4StrictFixture(t, f)
			rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo"), legacyProofRPCEvent(sender, other, "700ufake")}
			switch zero {
			case "omitted":
				delete(c4TxResponse(f), "code")
			case "string":
				c4TxResponse(f)["code"] = "0"
			}
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			cfg.EscrowAddress = escrow
			result, err := cfg.verifyEscrowDeposit(t.Context(), strings.ToLower(hash), sender, "700")
			if err != nil || !result.OK || !result.DepositFound || result.Lookup == nil || result.Lookup.MatchedTransfer == nil || result.Lookup.MatchedTransfer.Denom != "uwolo" || result.Lookup.MatchingTransferCount != 1 {
				t.Fatalf("complete unique WOLO effect rejected: %+v lookup=%+v err=%v", result, result.Lookup, err)
			}
		})
	}
}

func TestLegacyEscrowRejectsNoncanonicalExpectedAmounts(t *testing.T) {
	for _, amount := range []string{"0", "00", "0700", "+700", "-700", "700.0", "18446744073709551616"} {
		t.Run(amount, func(t *testing.T) {
			f, hash, rpc, sender, escrow := legacyEscrowProofFixture(t)
			cfg, requests := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			cfg.EscrowAddress = escrow
			result, err := cfg.verifyEscrowDeposit(t.Context(), hash, sender, amount)
			if err != nil || result.OK || result.FailureCode != "INVALID_AMOUNT" || requests.Load() != 0 {
				t.Fatalf("invalid expected amount reached chain evidence instead of failing closed: result=%+v requests=%d err=%v", result, requests.Load(), err)
			}
		})
	}
}

func TestLegacyChallengeFundingBindsCommittedMemoAndBankSend(t *testing.T) {
	for _, attack := range []string{"none", "forged memo", "forged bank send"} {
		t.Run(attack, func(t *testing.T) {
			f, _, _, sender, escrow := legacyEscrowProofFixture(t)
			memo := canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "500", "200")
			c4Body(f)["memo"] = memo
			if attack == "forged memo" {
				c4Body(f)["memo"] = canonicalAoE2HDBetsChallengeFundingMemo("42", "right", "500", "200")
			}
			if attack == "forged bank send" {
				c4Message(f)["to_address"] = legacyProofAddress(t, 85)
			}
			hash, rpc := c4StrictFixture(t, f)
			rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo")}
			// The REST response now claims the authorized challenge memo and
			// recipient, even when the exact hashed transaction committed another.
			c4Body(f)["memo"] = memo
			c4Message(f)["to_address"] = escrow
			cfg, _ := c4ConfigWithRPC(t, c4JSON(t, f), http.StatusOK, c4RPCJSON(t, rpc))
			cfg.EscrowAddress = escrow
			result, err := cfg.verifyChallengeFundingDeposit(t.Context(), hash, settlementChallengeFundingExpectation{
				Sender: sender, SourceApp: settlementAoE2HDBetsSourceApp,
				SettlementRunID: "aoe2hdbets:challenge-42:v1", ChallengeID: "42", ParticipantSide: "left",
				TotalFundedUWolo: "700", WagerUWolo: "500", GuaranteeUWolo: "200",
			})
			if attack == "none" {
				if err != nil || !result.OK || result.Funding == nil || !result.Funding.OK {
					t.Fatalf("complete canonical challenge funding rejected: %+v err=%v", result, err)
				}
			} else if err == nil && result.OK {
				t.Fatalf("forged REST challenge proof accepted over different committed bytes: %+v lookup=%+v", result, result.Lookup)
			}
		})
	}
}

func TestLegacyChallengeDiscoveryCannotPromoteUnverifiedSearchRows(t *testing.T) {
	for _, attack := range []string{"missing transaction", "empty exact response", "forged canonical memo", "valid duplicate search rows"} {
		t.Run(attack, func(t *testing.T) {
			f, _, _, sender, escrow := legacyEscrowProofFixture(t)
			memo := canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "500", "200")
			c4Body(f)["memo"] = memo
			if attack == "forged canonical memo" {
				c4Body(f)["memo"] = canonicalAoE2HDBetsChallengeFundingMemo("42", "right", "500", "200")
			}
			hash, rpc := c4StrictFixture(t, f)
			rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo")}
			exactPayload := c4JSON(t, f)
			// Search results assert the desired memo independently of the exact
			// committed transaction. They are candidates, never funding proof.
			c4Body(f)["memo"] = memo
			rows := []any{f["tx_response"]}
			transactions := []any{f["tx"]}
			if attack == "valid duplicate search rows" {
				rows = append(rows, rows[0])
				transactions = append(transactions, transactions[0])
			}
			searchPayload := map[string]any{"txs": transactions, "tx_responses": rows}
			var exactReads atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.URL.Path {
				case "/status":
					_, _ = w.Write([]byte(`{"result":{"node_info":{"network":"wolo-1"}}}`))
				case "/cosmos/tx/v1beta1/txs":
					_ = json.NewEncoder(w).Encode(searchPayload)
				case "/cosmos/tx/v1beta1/txs/" + hash:
					exactReads.Add(1)
					if attack == "missing transaction" {
						http.NotFound(w, r)
					} else if attack == "empty exact response" {
						_, _ = w.Write([]byte(`{}`))
					} else {
						_, _ = w.Write([]byte(exactPayload))
					}
				case "/tx":
					_, _ = w.Write(c4RPCJSON(t, rpc))
				default:
					t.Errorf("unexpected test request: %s", r.URL.Path)
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			cfg := settlementConfig{RPCHTTP: server.URL, RESTURL: server.URL, ChainID: "wolo-1", BaseDenom: "uwolo", AddressPrefix: "wolo", EscrowAddress: escrow, LookupTimeout: time.Second}
			result, err := cfg.listRecentChallengeFundingDeposits(t.Context(), settlementChallengeFundingRecentFilters{
				Limit: 5, Sender: sender, SourceApp: settlementAoE2HDBetsSourceApp,
				SettlementRunID: "aoe2hdbets:challenge-42:v1", ChallengeID: "42", ParticipantSide: "left",
			})
			if err != nil || !result.OK {
				t.Fatalf("read-only discovery failed: %+v err=%v", result, err)
			}
			if attack == "valid duplicate search rows" {
				if result.Count != 1 || len(result.Funding) != 1 || !result.Funding[0].OK || result.Funding[0].FundingTxHash != hash || result.Funding[0].Index != 0 || exactReads.Load() != 1 {
					t.Fatalf("one unique committed funding proof required despite repeated search rows: %+v exact_reads=%d", result, exactReads.Load())
				}
			} else if result.Count != 0 || len(result.Funding) != 0 || exactReads.Load() != 1 {
				t.Fatalf("unverified search events promoted to successful challenge funding: %+v exact_reads=%d", result, exactReads.Load())
			}
		})
	}
}

func TestLegacyChallengeDiscoveryCancellationCannotReportCompleteResults(t *testing.T) {
	for _, verifiedPrefix := range []bool{false, true} {
		name := "empty result"
		if verifiedPrefix {
			name = "partial result"
		}
		t.Run(name, func(t *testing.T) {
			f, _, _, sender, escrow := legacyEscrowProofFixture(t)
			c4Body(f)["memo"] = canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "500", "200")
			hash, rpc := c4StrictFixture(t, f)
			rpc.TxResult.Events = []abci.Event{legacyProofRPCEvent(sender, escrow, "700uwolo")}
			exactPayload, rpcPayload := c4JSON(t, f), c4RPCJSON(t, rpc)
			blockedHash := strings.Repeat("E", 64)
			blocked := map[string]any{"txhash": blockedHash, "height": "123", "code": 0, "events": c4TxResponse(f)["events"]}
			rows, transactions := []any{blocked}, []any{f["tx"]}
			if verifiedPrefix {
				rows = append([]any{f["tx_response"]}, rows...)
				transactions = append([]any{f["tx"]}, transactions...)
			}
			started := make(chan struct{}, 1)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.URL.Path {
				case "/status":
					_, _ = w.Write([]byte(`{"result":{"node_info":{"network":"wolo-1"}}}`))
				case "/cosmos/tx/v1beta1/txs":
					_ = json.NewEncoder(w).Encode(map[string]any{"txs": transactions, "tx_responses": rows})
				case "/cosmos/tx/v1beta1/txs/" + hash:
					_, _ = w.Write([]byte(exactPayload))
				case "/cosmos/tx/v1beta1/txs/" + blockedHash:
					started <- struct{}{}
					<-r.Context().Done()
				case "/tx":
					_, _ = w.Write(rpcPayload)
				default:
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			cfg := settlementConfig{RPCHTTP: server.URL, RESTURL: server.URL, ChainID: "wolo-1", BaseDenom: "uwolo", AddressPrefix: "wolo", EscrowAddress: escrow, LookupTimeout: 5 * time.Second}
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			type outcome struct {
				response settlementChallengeFundingRecentResponse
				err      error
			}
			finished := make(chan outcome, 1)
			go func() {
				response, err := cfg.listRecentChallengeFundingDeposits(ctx, settlementChallengeFundingRecentFilters{Limit: 5, Sender: sender, SourceApp: settlementAoE2HDBetsSourceApp, ChallengeID: "42", ParticipantSide: "left"})
				finished <- outcome{response, err}
			}()
			select {
			case <-started:
				cancel()
			case <-time.After(2 * time.Second):
				t.Fatal("exact transaction read did not start")
			}
			select {
			case result := <-finished:
				if result.err != nil || result.response.OK || result.response.FailureCode != "LOOKUP_FAILED" || result.response.Count != 0 || len(result.response.Funding) != 0 {
					t.Fatalf("canceled evidence collection claimed a complete empty or partial result: %+v err=%v", result.response, result.err)
				}
			case <-time.After(2 * time.Second):
				t.Fatal("exact transaction read did not honor cancellation")
			}
		})
	}
}
