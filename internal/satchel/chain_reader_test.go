package satchel

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	base "cosmossdk.io/api/cosmos/base/v1beta1"
	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/version"
	coretypes "github.com/cometbft/cometbft/rpc/core/types"
	cmttypes "github.com/cometbft/cometbft/types"
	cmtversion "github.com/cometbft/cometbft/version"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

// Every fixture is synthetic. Real Comet proof/commitment encodings exercise
// consistency verification; these fake signatures establish NO chain trust.
type readerFixture struct {
	intent      Intent
	observation Observation
	now         time.Time
	status      coretypes.ResultStatus
	tx          coretypes.ResultTx
	results     coretypes.ResultBlockResults
	commits     map[int64]*coretypes.ResultCommit
	rest        map[string]any
	overrides   map[string][]byte
}

func newReaderFixture(t *testing.T) *readerFixture {
	t.Helper()
	i, o, now := depositFixture(t)
	effect := abci.Event{Type: "transfer", Attributes: []abci.EventAttribute{
		{Key: "sender", Value: i.Sender}, {Key: "recipient", Value: i.Vault}, {Key: "amount", Value: i.AmountUWolo + Denom},
	}}
	result := abci.ExecTxResult{Code: 0, GasWanted: 10000, GasUsed: 5000, Events: []abci.Event{effect}}
	txs := cmttypes.Txs{cmttypes.Tx(o.TxBytes)}
	f := &readerFixture{intent: i, observation: o, now: now,
		tx:      coretypes.ResultTx{Hash: txs[0].Hash(), Height: o.Height, Index: 0, TxResult: result, Tx: txs[0], Proof: txs.Proof(0)},
		results: coretypes.ResultBlockResults{Height: o.Height, TxsResults: []*abci.ExecTxResult{&result}},
		commits: map[int64]*coretypes.ResultCommit{}, overrides: map[string][]byte{},
	}
	for height := int64(100); height <= 102; height++ {
		header := &cmttypes.Header{Version: cmtproto.Consensus{Block: cmtversion.BlockProtocol}, ChainID: ChainID, Height: height,
			Time:           now.Add(time.Duration(height-103) * 3 * time.Second),
			ValidatorsHash: bytes.Repeat([]byte{1}, 32), NextValidatorsHash: bytes.Repeat([]byte{1}, 32),
			ConsensusHash: bytes.Repeat([]byte{2}, 32), AppHash: bytes.Repeat([]byte{3}, 32),
			ProposerAddress: bytes.Repeat([]byte{4}, 20),
		}
		if height == 100 {
			header.DataHash = txs.Hash()
		}
		commit := &cmttypes.Commit{Height: height, Signatures: []cmttypes.CommitSig{{BlockIDFlag: cmttypes.BlockIDFlagCommit,
			ValidatorAddress: bytes.Repeat([]byte{4}, 20), Timestamp: header.Time, Signature: bytes.Repeat([]byte{5}, 64)}}}
		f.commits[height] = coretypes.NewResultCommit(header, commit, true)
	}
	f.status.NodeInfo.Network = ChainID
	f.status.SyncInfo.LatestBlockHeight = 102
	f.status.SyncInfo.LatestBlockTime = f.commits[102].Time
	f.reseal()
	var raw tx.TxRaw
	var body tx.TxBody
	if err := proto.Unmarshal(o.TxBytes, &raw); err != nil {
		t.Fatal(err)
	}
	if err := proto.Unmarshal(raw.BodyBytes, &body); err != nil {
		t.Fatal(err)
	}
	bodyJSON, err := protojson.Marshal(&body)
	if err != nil {
		t.Fatal(err)
	}
	var bodyObject map[string]any
	if err := json.Unmarshal(bodyJSON, &bodyObject); err != nil {
		t.Fatal(err)
	}
	f.rest = map[string]any{"tx": map[string]any{"body": bodyObject}, "tx_response": map[string]any{
		"height": "100", "txhash": strings.ToUpper(o.TxHash), "code": 0, "raw_log": "", "logs": []any{},
		"gas_wanted": "10000", "gas_used": "5000", "timestamp": f.commits[100].Time.Format(time.RFC3339Nano),
		"events": []any{map[string]any{"type": "transfer", "attributes": []any{
			map[string]any{"key": "sender", "value": i.Sender}, map[string]any{"key": "recipient", "value": i.Vault},
			map[string]any{"key": "amount", "value": i.AmountUWolo + Denom},
		}}},
	}}
	return f
}

func (f *readerFixture) reseal() {
	f.commits[101].Header.LastResultsHash = cmttypes.NewResults(f.results.TxsResults).Hash()
	// Commit.Hash caches its result. Rebuilding avoids retaining a stale cached
	// hash when a test intentionally changes a synthetic header and reseals it.
	for _, c := range f.commits {
		c.Commit = &cmttypes.Commit{Height: c.Commit.Height, Round: c.Commit.Round, Signatures: c.Commit.Signatures}
	}
	for height := int64(100); height <= 102; height++ {
		c := f.commits[height]
		if height > 100 {
			c.Header.LastBlockID = f.commits[height-1].Commit.BlockID
			c.Header.LastCommitHash = f.commits[height-1].Commit.Hash()
		}
		c.Commit.BlockID = cmttypes.BlockID{Hash: c.Header.Hash(), PartSetHeader: cmttypes.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
	}
	f.status.SyncInfo.LatestBlockHash = f.commits[102].Header.Hash()
}

func (f *readerFixture) response(t *testing.T, req *http.Request) []byte {
	t.Helper()
	key := req.URL.Path
	if req.URL.RawQuery != "" {
		key += "?" + req.URL.RawQuery
	}
	if b, ok := f.overrides[key]; ok {
		return b
	}
	if req.URL.Path == "/cosmos/tx/v1beta1/txs/"+strings.ToUpper(f.observation.TxHash) {
		b, err := json.Marshal(f.rest)
		if err != nil {
			t.Error(err)
		}
		return b
	}
	var result any
	switch req.URL.Path {
	case "/status":
		result = f.status
	case "/tx":
		if req.URL.Query().Get("hash") != "0x"+strings.ToUpper(f.observation.TxHash) || req.URL.Query().Get("prove") != "true" {
			t.Errorf("noncanonical transaction query: %s", req.URL.RawQuery)
		}
		result = f.tx
	case "/block_results":
		if req.URL.Query().Get("height") != "100" {
			t.Errorf("unexpected results height")
		}
		result = f.results
	case "/commit":
		h, _ := strconv.ParseInt(req.URL.Query().Get("height"), 10, 64)
		result = f.commits[h]
		if result == nil {
			t.Errorf("unpinned commit request: %s", req.URL.RawQuery)
		}
	default:
		t.Errorf("unexpected request: %s", key)
	}
	b, err := cmtjson.Marshal(result)
	if err != nil {
		t.Error(err)
	}
	return []byte(`{"jsonrpc":"2.0","id":-1,"result":` + string(b) + `}`)
}

func (f *readerFixture) server(t *testing.T) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.Header.Get("Accept-Encoding") != "identity" {
			t.Errorf("unbounded request shape: %s %s", r.Method, r.Header.Get("Accept-Encoding"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(f.response(t, r))
	}))
	t.Cleanup(s.Close)
	return s
}

func fixtureReader(t *testing.T, f *readerFixture, witness *readerFixture) *ChainReader {
	t.Helper()
	s := f.server(t)
	cfg := SourceConfig{RPC: s.URL, REST: s.URL}
	if witness != nil {
		cfg.WitnessRPC = witness.server(t).URL
	}
	r, err := NewChainReader(cfg)
	if err != nil {
		t.Fatal(err)
	}
	r.now = func() time.Time { return f.now }
	t.Cleanup(r.Close)
	return r
}

func requireEvidenceFailure(t *testing.T, err error, allowed ...FailureCode) {
	t.Helper()
	var ee *EvidenceError
	if !errors.As(err, &ee) {
		t.Fatalf("expected typed evidence error, got %v", err)
	}
	for _, c := range allowed {
		if ee.Code == c {
			return
		}
	}
	t.Fatalf("failure %s, want one of %v", ee.Code, allowed)
}

func TestChainReaderFetchedEvidenceRemainsNoncrediting(t *testing.T) {
	for _, withWitness := range []bool{false, true} {
		t.Run(fmt.Sprint("witness=", withWitness), func(t *testing.T) {
			f := newReaderFixture(t)
			var witness *readerFixture
			if withWitness {
				witness = newReaderFixture(t)
			}
			r := fixtureReader(t, f, witness)
			e, err := r.ReadDeposit(context.Background(), f.intent, strings.ToLower(f.observation.TxHash))
			if err != nil {
				t.Fatal(err)
			}
			if e.Status() != "NONCREDITING" || e.CreditAuthorized() || e.ConsensusAuthenticated() || e.WitnessCompared != withWitness {
				t.Fatalf("unsafe evidence authority: %+v", e)
			}
			if e.Receipt.ID() != ChainID+":"+strings.ToUpper(f.observation.TxHash)+":0" {
				t.Fatalf("incorrect receipt: %+v", e.Receipt)
			}
			if !bytes.Equal(e.Observation.TxBytes, f.observation.TxBytes) || e.Observation.Height != 100 || e.Observation.BlockHash != f.commits[100].Header.Hash().String() {
				t.Fatal("fetched evidence missing canonical bytes or block binding")
			}
			blockers := e.Blockers()
			if len(blockers) != 2 || blockers[0] != UntrustedConsensus || blockers[1] != IndependentTrustUnavailable {
				t.Fatalf("missing explicit trust blockers: %v", blockers)
			}
			blockers[0] = "fake"
			if e.Blockers()[0] != UntrustedConsensus || CurrentCapability().Available() || CurrentCapability().CreditAuthorized() {
				t.Fatal("observation mutated custody authority")
			}
			if !withWitness && e.Observation.IndependentHead.Height != 0 {
				t.Fatal("fabricated independent head")
			}
			if withWitness {
				if e.WitnessHead.Height != 102 || e.WitnessHead.BlockHash != witness.status.SyncInfo.LatestBlockHash.String() || !e.WitnessHead.BlockTime.Equal(witness.status.SyncInfo.LatestBlockTime) || !e.WitnessHead.ObservedAt.Equal(f.now) || e.WitnessHead.CatchingUp == nil || *e.WitnessHead.CatchingUp {
					t.Fatal("actual witness status was not retained")
				}
			} else if e.WitnessHead != (Head{}) {
				t.Fatal("fabricated actual witness status")
			}
		})
	}
}

func TestChainReaderConfigurationRejectsRequestControlledSources(t *testing.T) {
	for _, bad := range []string{"", "http://example.com", "http://localhost:26657", "ftp://127.0.0.1", "https://user:secret@example.com", "https://example.com?q=1", "https://example.com#fragment", "https://example.com/%2fsecret", "//example.com", "http://192.168.1.1", "file:///tmp/rpc"} {
		t.Run(bad, func(t *testing.T) {
			for n, cfg := range []SourceConfig{{RPC: bad, REST: "https://example.com"}, {RPC: "https://example.com", REST: bad}, {RPC: "https://example.com", REST: "https://example.com", WitnessRPC: bad}} {
				if n == 2 && bad == "" {
					continue
				}
				_, err := NewChainReader(cfg)
				requireEvidenceFailure(t, err, InvalidConfiguration)
			}
		})
	}
	for _, good := range []string{"https://example.com", "https://example.com/rpc/", "http://127.0.0.1:26657", "http://[::1]:26657"} {
		r, err := NewChainReader(SourceConfig{RPC: good, REST: good})
		if err != nil {
			t.Fatalf("valid server source %s: %v", good, err)
		}
		r.Close()
	}
}

func TestChainReaderBindsFetchedRawMessageToImmutableIntent(t *testing.T) {
	for _, name := range []string{"memo", "sender", "recipient", "amount", "denomination", "extra coin", "extra message", "multi send", "unknown body field"} {
		t.Run(name, func(t *testing.T) {
			f := newReaderFixture(t)
			switch name {
			case "memo":
				rewriteBody(t, &f.observation, func(b *tx.TxBody) { b.Memo = "forged" })
			case "extra message":
				rewriteBody(t, &f.observation, func(b *tx.TxBody) { b.Messages = append(b.Messages, b.Messages[0]) })
			case "multi send":
				rewriteBody(t, &f.observation, func(b *tx.TxBody) { b.Messages[0].TypeUrl = "/cosmos.bank.v1beta1.MsgMultiSend" })
			case "unknown body field":
				rewriteBody(t, &f.observation, func(b *tx.TxBody) { b.ProtoReflect().SetUnknown([]byte{0x80, 0x01, 0x01}) })
			default:
				rewriteSend(t, &f.observation, func(s *bank.MsgSend) {
					switch name {
					case "sender":
						s.FromAddress = fixtureAddress(t, 8)
					case "recipient":
						s.ToAddress = fixtureAddress(t, 8)
					case "amount":
						s.Amount[0].Amount = "2"
					case "denomination":
						s.Amount[0].Denom = "other"
					case "extra coin":
						s.Amount = append(s.Amount, &base.Coin{Denom: "other", Amount: "1"})
					}
				})
			}
			// Hash, proof, headers and request agree with the malicious raw bytes.
			// The immutable owner intent must still reject their decoded message.
			txs := cmttypes.Txs{cmttypes.Tx(f.observation.TxBytes)}
			f.tx.Hash, f.tx.Tx, f.tx.Proof = txs[0].Hash(), txs[0], txs.Proof(0)
			f.commits[100].Header.DataHash = txs.Hash()
			f.reseal()
			f.rest["tx_response"].(map[string]any)["txhash"] = strings.ToUpper(f.observation.TxHash)
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, TransactionMismatch)
		})
	}
}

func TestChainReaderRejectsMaliciousEvidence(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*readerFixture)
		code   []FailureCode
	}{
		{"wrong status chain", func(f *readerFixture) { f.status.NodeInfo.Network = "other" }, []FailureCode{WrongChain}},
		{"stale head", func(f *readerFixture) { f.status.SyncInfo.LatestBlockTime = f.now.Add(-time.Minute) }, []FailureCode{StaleHead}},
		{"future head", func(f *readerFixture) { f.status.SyncInfo.LatestBlockTime = f.now.Add(time.Minute) }, []FailureCode{StaleHead}},
		{"catching up", func(f *readerFixture) { f.status.SyncInfo.CatchingUp = true }, []FailureCode{StaleHead}},
		{"status hash differs from commit", func(f *readerFixture) { f.status.SyncInfo.LatestBlockHash = bytes.Repeat([]byte{9}, 32) }, []FailureCode{InconsistentObservations}},
		{"transaction bytes differ", func(f *readerFixture) { f.tx.Tx = append(f.tx.Tx, 0) }, []FailureCode{TransactionMismatch}},
		{"rpc transaction hash differs", func(f *readerFixture) { f.tx.Hash = bytes.Repeat([]byte{9}, 32) }, []FailureCode{TransactionMismatch}},
		{"failed execution", func(f *readerFixture) { f.tx.TxResult.Code = 7 }, []FailureCode{ExecutionFailed}},
		{"forged proof root", func(f *readerFixture) { f.tx.Proof.RootHash = bytes.Repeat([]byte{9}, 32) }, []FailureCode{InvalidInclusion}},
		{"forged proof data", func(f *readerFixture) { f.tx.Proof.Data = []byte("forged") }, []FailureCode{InvalidInclusion}},
		{"forged proof ordinal", func(f *readerFixture) { f.tx.Index = 1 }, []FailureCode{InvalidInclusion, InvalidResultCommitment}},
		{"wrong results height", func(f *readerFixture) { f.results.Height = 99 }, []FailureCode{InvalidResultCommitment}},
		{"missing result commitment", func(f *readerFixture) {
			f.commits[101].Header.LastResultsHash = nil
			f.commits[101].Commit.BlockID.Hash = f.commits[101].Header.Hash()
		}, []FailureCode{InvalidResultCommitment}},
		{"results replaced", func(f *readerFixture) { f.results.TxsResults[0].GasUsed++ }, []FailureCode{InvalidResultCommitment, InconsistentObservations}},
		{"result deterministic data differs", func(f *readerFixture) { f.tx.TxResult.Data = []byte("forged-result") }, []FailureCode{InvalidResultCommitment, InconsistentObservations}},
		{"broken height linkage", func(f *readerFixture) {
			f.commits[101].Header.LastBlockID.Hash = bytes.Repeat([]byte{9}, 32)
			f.commits[101].Commit.BlockID.Hash = f.commits[101].Header.Hash()
		}, []FailureCode{InvalidInclusion, InconsistentObservations}},
		{"invalid commit signature shape", func(f *readerFixture) { f.commits[100].Commit.Signatures = nil }, []FailureCode{UntrustedConsensus, InvalidResponse}},
		{"noncanonical commit", func(f *readerFixture) { f.commits[100].CanonicalCommit = false }, []FailureCode{UntrustedConsensus, InvalidResponse}},
		{"rest hash mismatch", func(f *readerFixture) { f.rest["tx_response"].(map[string]any)["txhash"] = strings.Repeat("F", 64) }, []FailureCode{TransactionMismatch}},
		{"rest height mismatch", func(f *readerFixture) { f.rest["tx_response"].(map[string]any)["height"] = "99" }, []FailureCode{TransactionMismatch}},
		{"rest failed execution", func(f *readerFixture) { f.rest["tx_response"].(map[string]any)["code"] = 8 }, []FailureCode{ExecutionFailed, InconsistentObservations}},
		{"rest wrong timestamp", func(f *readerFixture) {
			f.rest["tx_response"].(map[string]any)["timestamp"] = f.now.Format(time.RFC3339Nano)
		}, []FailureCode{TransactionMismatch, InconsistentObservations}},
		{"rest memo forged", func(f *readerFixture) { f.rest["tx"].(map[string]any)["body"].(map[string]any)["memo"] = "forged" }, []FailureCode{TransactionMismatch}},
		{"rest unknown protobuf field", func(f *readerFixture) { f.rest["tx"].(map[string]any)["body"].(map[string]any)["forged"] = "field" }, []FailureCode{InvalidResponse, TransactionMismatch}},
		{"rest effect missing", func(f *readerFixture) { f.rest["tx_response"].(map[string]any)["events"] = []any{} }, []FailureCode{AmbiguousTransfers, TransactionMismatch, InconsistentObservations}},
		{"rest extra transfer", func(f *readerFixture) {
			r := f.rest["tx_response"].(map[string]any)
			e := r["events"].([]any)
			r["events"] = append(e, e[0])
		}, []FailureCode{AmbiguousTransfers, InconsistentObservations}},
		{"extra execution transfer", func(f *readerFixture) { f.tx.TxResult.Events = append(f.tx.TxResult.Events, f.tx.TxResult.Events[0]) }, []FailureCode{AmbiguousTransfers, InconsistentObservations}},
		{"malformed transfer attribute", func(f *readerFixture) {
			f.tx.TxResult.Events[0].Attributes = append(f.tx.TxResult.Events[0].Attributes, abci.EventAttribute{Key: "amount", Value: "1uwolo"})
		}, []FailureCode{AmbiguousTransfers, InconsistentObservations}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f := newReaderFixture(t)
			tt.mutate(f)
			r := fixtureReader(t, f, nil)
			e, err := r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, tt.code...)
			if e.Receipt != (ReceiptCandidate{}) {
				t.Fatal("failure retained usable receipt")
			}
		})
	}
}

func TestChainReaderWitnessDisagreementNeverAuthenticates(t *testing.T) {
	for _, point := range []string{"status chain", "stale witness", "inclusion commit", "result commit", "head commit"} {
		t.Run(point, func(t *testing.T) {
			f, w := newReaderFixture(t), newReaderFixture(t)
			switch point {
			case "status chain":
				w.status.NodeInfo.Network = "forged-chain"
			case "stale witness":
				w.status.SyncInfo.LatestBlockTime = w.now.Add(-time.Minute)
			case "inclusion commit":
				w.commits[100].Header.AppHash = bytes.Repeat([]byte{7}, 32)
				w.reseal()
			case "result commit":
				w.commits[101].Header.AppHash = bytes.Repeat([]byte{7}, 32)
				w.reseal()
			case "head commit":
				w.commits[102].Header.AppHash = bytes.Repeat([]byte{7}, 32)
				w.reseal()
			}
			r := fixtureReader(t, f, w)
			_, err := r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, InconsistentObservations, WrongChain, StaleHead)
		})
	}
}

func TestChainReaderWitnessStatusMustMatchItsOwnCommit(t *testing.T) {
	for _, field := range []string{"block hash", "block time"} {
		t.Run(field, func(t *testing.T) {
			f, w := newReaderFixture(t), newReaderFixture(t)
			if field == "block hash" {
				w.status.SyncInfo.LatestBlockHash = bytes.Repeat([]byte{9}, 32)
			} else {
				w.status.SyncInfo.LatestBlockTime = w.status.SyncInfo.LatestBlockTime.Add(time.Second)
			}
			_, err := fixtureReader(t, f, w).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, InconsistentObservations)
			var ee *EvidenceError
			if !errors.As(err, &ee) || ee.Source != "witness" || ee.Operation != "status_commit" {
				t.Fatalf("did not identify witness status/commit disagreement: %v", err)
			}
		})
	}
}

func advanceReaderFixtureWitness(f *readerFixture, stamp time.Time) {
	header := *f.commits[102].Header
	header.Height, header.Time = 103, stamp
	header.LastBlockID, header.LastCommitHash = f.commits[102].Commit.BlockID, f.commits[102].Commit.Hash()
	commit := &cmttypes.Commit{Height: 103,
		BlockID:    cmttypes.BlockID{Hash: header.Hash(), PartSetHeader: cmttypes.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}},
		Signatures: []cmttypes.CommitSig{{BlockIDFlag: cmttypes.BlockIDFlagCommit, ValidatorAddress: bytes.Repeat([]byte{4}, 20), Timestamp: stamp, Signature: bytes.Repeat([]byte{5}, 64)}},
	}
	f.commits[103] = coretypes.NewResultCommit(&header, commit, true)
	f.status.SyncInfo.LatestBlockHeight, f.status.SyncInfo.LatestBlockTime, f.status.SyncInfo.LatestBlockHash = 103, stamp, header.Hash()
}

func TestChainReaderRetainsAndBindsAheadWitnessHead(t *testing.T) {
	f, w := newReaderFixture(t), newReaderFixture(t)
	advanceReaderFixtureWitness(w, w.now.Add(-time.Second))
	primary := f.server(t)
	var mu sync.Mutex
	counts := map[string]int{}
	witness := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		mu.Lock()
		counts[req.URL.Path+"?"+req.URL.RawQuery]++
		mu.Unlock()
		_, _ = rw.Write(w.response(t, req))
	}))
	defer witness.Close()
	r, err := NewChainReader(SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	r.now = func() time.Time { return f.now }
	e, err := r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	if err != nil {
		t.Fatal(err)
	}
	if e.WitnessHead.Height != 103 || e.WitnessHead.BlockHash != w.commits[103].Header.Hash().String() || !e.WitnessHead.BlockTime.Equal(w.commits[103].Time) || !e.WitnessHead.ObservedAt.Equal(f.now) || e.Observation.IndependentHead.Height != 102 || e.Observation.IndependentHead.BlockHash != f.commits[102].Header.Hash().String() || !e.WitnessCompared || e.ConsensusAuthenticated() || e.CreditAuthorized() {
		t.Fatalf("actual and compared witness heads were confused: %+v", e)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(counts) != 5 {
		t.Fatalf("unexpected witness request set: %v", counts)
	}
	for path, count := range counts {
		if count != 1 {
			t.Fatalf("repeated witness request %s: %d", path, count)
		}
	}
	for _, height := range []string{"100", "101", "102", "103"} {
		if counts["/commit?height="+height] != 1 {
			t.Fatalf("witness height %s not fetched exactly once", height)
		}
	}
}

func TestChainReaderWitnessAheadTimeCannotPrecedeComparedHead(t *testing.T) {
	f, w := newReaderFixture(t), newReaderFixture(t)
	// This adversarial source reports an ahead-height header with an older but
	// initially fresh timestamp. Its own status and commit agree, but its time
	// contradicts the already compared lower-height header and must be refused.
	advanceReaderFixtureWitness(w, w.now.Add(-29*time.Second))
	primary := f.server(t)
	var advanced atomic.Bool
	witness := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/commit" && req.URL.Query().Get("height") == "103" {
			advanced.Store(true)
		}
		_, _ = rw.Write(w.response(t, req))
	}))
	defer witness.Close()
	r, err := NewChainReader(SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	r.now = func() time.Time {
		if advanced.Load() {
			return f.now.Add(2 * time.Second)
		}
		return f.now
	}
	_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	requireEvidenceFailure(t, err, InconsistentObservations)
	var ee *EvidenceError
	if !errors.As(err, &ee) || ee.Source != "witness" || ee.Operation != "header_time" {
		t.Fatalf("contradictory witness time lost its deterministic reason: %v", err)
	}
}

func TestChainReaderLatestSeenCommitRemainsNoncrediting(t *testing.T) {
	for _, witness := range []bool{false, true} {
		t.Run(fmt.Sprint(witness), func(t *testing.T) {
			f := newReaderFixture(t)
			f.commits[102].CanonicalCommit = false
			var w *readerFixture
			if witness {
				w = newReaderFixture(t)
				w.commits[102].CanonicalCommit = false
			}
			e, err := fixtureReader(t, f, w).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			if err != nil {
				t.Fatal(err)
			}
			if e.Status() != "NONCREDITING" || e.TrustStatus() != "UNTRUSTED_CONSENSUS_ANCHOR" || e.ConsensusAuthenticated() || e.CreditAuthorized() {
				t.Fatal("seen commit granted financial authority")
			}
		})
	}
}

func TestChainReaderMissingOrNullCommitMetadataRefused(t *testing.T) {
	for _, raw := range []string{"missing", "null"} {
		t.Run(raw, func(t *testing.T) {
			f := newReaderFixture(t)
			b, _ := cmtjson.Marshal(f.commits[102])
			var fields map[string]json.RawMessage
			if err := json.Unmarshal(b, &fields); err != nil {
				t.Fatal(err)
			}
			if raw == "missing" {
				delete(fields, "canonical")
			} else {
				fields["canonical"] = json.RawMessage("null")
			}
			b, _ = json.Marshal(fields)
			f.overrides["/commit?height=102"] = []byte(`{"jsonrpc":"2.0","id":-1,"result":` + string(b) + `}`)
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, InvalidResponse)
		})
	}
}

func TestChainReaderRefusesSelfConsistentExtraBankEffects(t *testing.T) {
	for _, kind := range []string{"duplicated exact transfer", "unrelated fee transfer", "split coin transfer"} {
		t.Run(kind, func(t *testing.T) {
			f := newReaderFixture(t)
			event := f.tx.TxResult.Events[0]
			if kind == "unrelated fee transfer" {
				event.Attributes = []abci.EventAttribute{{Key: "sender", Value: f.intent.Sender}, {Key: "recipient", Value: fixtureAddress(t, 9)}, {Key: "amount", Value: "1uwolo"}}
			}
			if kind == "split coin transfer" {
				event.Attributes = []abci.EventAttribute{{Key: "sender", Value: f.intent.Sender}, {Key: "recipient", Value: f.intent.Vault}, {Key: "amount", Value: "1uwolo,1other"}}
			}
			f.tx.TxResult.Events = append(f.tx.TxResult.Events, event)
			f.results.TxsResults[0].Events = f.tx.TxResult.Events
			f.reseal()
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, AmbiguousTransfers)
		})
	}
}

func TestChainReaderRESTTimestampUsesCosmosSerialization(t *testing.T) {
	for _, format := range []string{"exact nanos", "SDK whole seconds", "wrong second"} {
		t.Run(format, func(t *testing.T) {
			f := newReaderFixture(t)
			f.commits[100].Header.Time = f.commits[100].Header.Time.Add(123456789 * time.Nanosecond)
			f.reseal()
			stamp := f.commits[100].Header.Time.Format(time.RFC3339Nano)
			if format == "SDK whole seconds" {
				stamp = f.commits[100].Header.Time.Format(time.RFC3339)
			}
			if format == "wrong second" {
				stamp = f.commits[100].Header.Time.Add(time.Second).Format(time.RFC3339)
			}
			f.rest["tx_response"].(map[string]any)["timestamp"] = stamp
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			if format == "wrong second" {
				requireEvidenceFailure(t, err, TransactionMismatch)
			} else if err != nil {
				t.Fatalf("legitimate Cosmos timestamp refused: %v", err)
			}
		})
	}
}

func TestChainReaderZeroCodeAndMalformedExecutionSerialization(t *testing.T) {
	for _, value := range []string{"omitted", "0", `"0"`, "null", `""`, "0.0", "0e0", "-1", "4294967296", `"00"`, "false"} {
		t.Run(value, func(t *testing.T) {
			f := newReaderFixture(t)
			raw, err := cmtjson.Marshal(f.tx)
			if err != nil {
				t.Fatal(err)
			}
			var v map[string]any
			if err = json.Unmarshal(raw, &v); err != nil {
				t.Fatal(err)
			}
			result := v["tx_result"].(map[string]any)
			delete(result, "code")
			if value != "omitted" {
				result["code"] = json.RawMessage(value)
			}
			b, err := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": -1, "result": v})
			if err != nil {
				t.Fatal(err)
			}
			q := url.Values{"hash": {"0x" + strings.ToUpper(f.observation.TxHash)}, "prove": {"true"}}
			f.overrides["/tx?"+q.Encode()] = b
			r := fixtureReader(t, f, nil)
			_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			if value == "omitted" || value == "0" || value == `"0"` {
				if err != nil {
					t.Fatalf("legitimate zero code refused: %v", err)
				}
			} else {
				requireEvidenceFailure(t, err, InvalidResponse)
			}
		})
	}
	for _, missing := range []bool{true, false} {
		t.Run(fmt.Sprint("missing-result=", missing), func(t *testing.T) {
			f := newReaderFixture(t)
			b, _ := cmtjson.Marshal(f.tx)
			var v map[string]any
			_ = json.Unmarshal(b, &v)
			if missing {
				delete(v, "tx_result")
			} else {
				v["tx_result"] = nil
			}
			b, _ = json.Marshal(map[string]any{"jsonrpc": "2.0", "id": -1, "result": v})
			q := url.Values{"hash": {"0x" + strings.ToUpper(f.observation.TxHash)}, "prove": {"true"}}
			f.overrides["/tx?"+q.Encode()] = b
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, InvalidResponse)
		})
	}
}

func TestChainReaderRejectsRPCEnvelopesAndResourceAttacks(t *testing.T) {
	for name, payload := range map[string]string{
		"rpc remote error":   `{"jsonrpc":"2.0","id":-1,"error":{"code":-32603,"message":"secret-remote-body"}}`,
		"null result":        `{"jsonrpc":"2.0","id":-1,"result":null}`,
		"duplicate result":   `{"jsonrpc":"2.0","id":-1,"result":{},"result":{}}`,
		"trailing json":      `{} {}`,
		"deep nesting":       strings.Repeat("[", 1000) + strings.Repeat("]", 1000),
		"oversized response": `{"padding":"` + strings.Repeat("x", maxResponseBytes) + `"}`,
	} {
		t.Run(name, func(t *testing.T) {
			f := newReaderFixture(t)
			f.overrides["/status"] = []byte(payload)
			_, err := fixtureReader(t, f, nil).ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, InvalidResponse, ResponseTooLarge, SourceUnavailable)
			if strings.Contains(err.Error(), "secret-remote-body") {
				t.Fatal("remote content leaked into deterministic error")
			}
		})
	}
	for _, mode := range []string{"http error", "gzip", "redirect", "chunked oversized"} {
		t.Run(mode, func(t *testing.T) {
			f := newReaderFixture(t)
			var redirected atomic.Int64
			dest := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { redirected.Add(1); _, _ = w.Write([]byte("{}")) }))
			defer dest.Close()
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch mode {
				case "http error":
					http.Error(w, "secret-remote-body", http.StatusServiceUnavailable)
				case "gzip":
					w.Header().Set("Content-Encoding", "gzip")
					_, _ = w.Write([]byte("{}"))
				case "redirect":
					http.Redirect(w, r, dest.URL, http.StatusTemporaryRedirect)
				case "chunked oversized":
					w.(http.Flusher).Flush()
					_, _ = w.Write(bytes.Repeat([]byte(" "), maxResponseBytes+1))
				}
			}))
			defer s.Close()
			r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
			if err != nil {
				t.Fatal(err)
			}
			defer r.Close()
			r.now = func() time.Time { return f.now }
			_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, SourceUnavailable, InvalidResponse, ResponseTooLarge)
			if redirected.Load() != 0 {
				t.Fatal("followed redirect to unconfigured source")
			}
		})
	}
}

func TestChainReaderCumulativeResponseBudget(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(append([]byte(`{}`), bytes.Repeat([]byte(" "), 900000)...))
	}))
	defer s.Close()
	r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	session := readSession{reader: r, remaining: maxEvidenceBytes}
	for n := 0; n < 6; n++ {
		if _, err = session.get(context.Background(), r.rpc, "rpc", "test", "/status", nil); err != nil {
			t.Fatal(err)
		}
	}
	_, err = session.get(context.Background(), r.rpc, "rpc", "test", "/status", nil)
	requireEvidenceFailure(t, err, ResponseTooLarge)
}

func TestChainReaderRejectsHeadThatBecomesStaleDuringRead(t *testing.T) {
	f := newReaderFixture(t)
	var elapsed atomic.Bool
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(f.response(t, r))
		if strings.HasPrefix(r.URL.Path, "/cosmos/tx/") {
			elapsed.Store(true)
		}
	}))
	defer s.Close()
	r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	r.now = func() time.Time {
		if elapsed.Load() {
			return f.now.Add(31 * time.Second)
		}
		return f.now
	}
	_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	requireEvidenceFailure(t, err, StaleHead)
}

func TestChainReaderOwnedRequestTimeoutWithoutCallerDeadline(t *testing.T) {
	for _, bodyStall := range []bool{false, true} {
		t.Run(fmt.Sprint("body_stall=", bodyStall), func(t *testing.T) {
			f := newReaderFixture(t)
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if bodyStall {
					_, _ = w.Write([]byte("{"))
					w.(http.Flusher).Flush()
				}
				<-r.Context().Done()
			}))
			defer s.Close()
			r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
			if err != nil {
				t.Fatal(err)
			}
			defer r.Close()
			r.now = func() time.Time { return f.now }
			started := time.Now()
			_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, TimedOut)
			if time.Since(started) > maxReadDuration {
				t.Fatal("unresponsive source exceeded reader total deadline")
			}
		})
	}
}

func TestChainReaderCancellationDeadlineAndRetry(t *testing.T) {
	f := newReaderFixture(t)
	for _, deadline := range []bool{false, true} {
		t.Run(fmt.Sprint("deadline=", deadline), func(t *testing.T) {
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
			defer s.Close()
			r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
			if err != nil {
				t.Fatal(err)
			}
			defer r.Close()
			r.now = func() time.Time { return f.now }
			ctx, cancel := context.WithCancel(context.Background())
			want := Canceled
			if deadline {
				cancel()
				ctx, cancel = context.WithTimeout(context.Background(), 30*time.Millisecond)
				want = TimedOut
			} else {
				cancel()
			}
			defer cancel()
			_, err = r.ReadDeposit(ctx, f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, want)
		})
	}
	var statusCalls atomic.Int64
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/status" && statusCalls.Add(1) == 1 {
			http.Error(w, "retry later", http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write(f.response(t, r))
	}))
	defer s.Close()
	r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	r.now = func() time.Time { return f.now }
	_, err = r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	requireEvidenceFailure(t, err, SourceUnavailable)
	first, err := r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	if err != nil {
		t.Fatal(err)
	}
	second, err := r.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
	if err != nil {
		t.Fatal(err)
	}
	if first.Receipt != second.Receipt || statusCalls.Load() != 3 {
		t.Fatal("read retry changed receipt identity or performed hidden retries")
	}
}

func TestChainReaderBoundsConcurrentReadsAndCancelsQueuedWork(t *testing.T) {
	f := newReaderFixture(t)
	entered := make(chan struct{}, 8)
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { entered <- struct{}{}; <-r.Context().Done() }))
	defer s.Close()
	r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	r.now = func() time.Time { return f.now }
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var wg sync.WaitGroup
	for n := 0; n < 4; n++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := r.ReadDeposit(ctx, f.intent, f.observation.TxHash)
			requireEvidenceFailure(t, err, Canceled)
		}()
	}
	for n := 0; n < 4; n++ {
		select {
		case <-entered:
		case <-time.After(time.Second):
			t.Fatal("bounded read did not begin")
		}
	}
	queued, stop := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer stop()
	_, err = r.ReadDeposit(queued, f.intent, f.observation.TxHash)
	requireEvidenceFailure(t, err, TimedOut)
	select {
	case <-entered:
		t.Fatal("fifth read bypassed concurrency limit")
	default:
	}
	cancel()
	wg.Wait()
}

func TestChainReaderInvalidIntentAndHashNeverReachSource(t *testing.T) {
	for _, mode := range []string{"expired", "known role vault", "bad hash", "url hash", "bad owner"} {
		t.Run(mode, func(t *testing.T) {
			f := newReaderFixture(t)
			hash := f.observation.TxHash
			switch mode {
			case "expired":
				f.intent.ExpiresAt = f.now
			case "known role vault":
				f.intent.Vault = "wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p"
			case "bad hash":
				hash = "not-a-hash"
			case "url hash":
				hash = "https://evil.example/"
			case "bad owner":
				f.intent.OwnerID = ""
			}
			var calls atomic.Int64
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls.Add(1); _, _ = w.Write([]byte("{}")) }))
			defer s.Close()
			r, err := NewChainReader(SourceConfig{RPC: s.URL, REST: s.URL})
			if err != nil {
				t.Fatal(err)
			}
			defer r.Close()
			r.now = func() time.Time { return f.now }
			_, err = r.ReadDeposit(context.Background(), f.intent, hash)
			requireEvidenceFailure(t, err, InvalidIntent, TransactionMismatch)
			if calls.Load() != 0 {
				t.Fatal("invalid immutable request reached source")
			}
		})
	}
}

// Keep base64 parity visible: Comet Tx JSON must contain fetched bytes, never a
// request-provided decoded transfer substituted for those bytes.
func TestChainReaderFixtureContainsActualRawTransaction(t *testing.T) {
	f := newReaderFixture(t)
	b, err := cmtjson.Marshal(f.tx)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(b, []byte(base64.StdEncoding.EncodeToString(f.observation.TxBytes))) {
		t.Fatal("fixture omitted raw transaction bytes")
	}
	for _, c := range f.commits {
		if err := c.SignedHeader.ValidateBasic(ChainID); err != nil {
			t.Fatalf("synthetic commit is not structurally valid: %v", err)
		}
	}
}
