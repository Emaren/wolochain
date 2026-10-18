package satchel

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtsecp "github.com/cometbft/cometbft/crypto/secp256k1"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
)

// Every endpoint and signature is a local synthetic fixture. This file never
// obtains a live checkpoint, opens a keyring or broadcasts a transaction.
func adversarialTrustedServer(t *testing.T, f *readerFixture, vals *cmt.ValidatorSet, intercept func(http.ResponseWriter, *http.Request) bool) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("trust reader attempted %s", r.Method)
		}
		if intercept != nil && intercept(w, r) {
			return
		}
		if r.URL.Path == "/validators" {
			height, _ := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
			data, err := cmtjson.Marshal(&core.ResultValidators{BlockHeight: height, Validators: vals.Validators, Count: len(vals.Validators), Total: len(vals.Validators)})
			if err != nil {
				t.Errorf("fixture validators: %v", err)
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, data)
			return
		}
		_, _ = w.Write(f.response(t, r))
	}))
	t.Cleanup(s.Close)
	return s
}

func adversarialTrustedReader(t *testing.T, f *readerFixture, primary, witness *httptest.Server, anchor TrustAnchor) *TrustedReader {
	t.Helper()
	r, err := NewTrustedReader(SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL}, anchor)
	if err != nil {
		t.Fatal(err)
	}
	r.reader.now = func() time.Time { return f.now }
	t.Cleanup(r.Close)
	return r
}

func readTrustedFixture(r *TrustedReader, f *readerFixture) (AuthenticatedEvidence, error) {
	return r.ReadTransfer(context.Background(), TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}, f.observation.TxHash)
}

func assertTrustedRefusal(t *testing.T, r *TrustedReader, f *readerFixture) *EvidenceError {
	t.Helper()
	defer func() {
		if recovered := recover(); recovered != nil {
			t.Fatalf("malformed remote evidence panicked instead of refusing: %v", recovered)
		}
	}()
	evidence, err := readTrustedFixture(r, f)
	if err == nil || evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
		t.Fatalf("hostile evidence was authenticated: err=%v", err)
	}
	var typed *EvidenceError
	if !errors.As(err, &typed) {
		t.Fatalf("untyped trust failure: %v", err)
	}
	return typed
}

func TestTrustedReaderAdversarialValidatorsNeverPanic(t *testing.T) {
	for _, mode := range []string{"duplicate", "empty_ed25519", "short_ed25519", "short_secp256k1", "unsupported_wire_key"} {
		t.Run(mode, func(t *testing.T) {
			f, vals := signedReaderFixture(t)
			anchor := fixtureAnchor(f)
			var intercept func(http.ResponseWriter, *http.Request) bool
			switch mode {
			case "duplicate":
				vals.Validators = append(vals.Validators, vals.Validators[0].Copy())
			case "empty_ed25519":
				vals.Validators[0].PubKey = cmted.PubKey(nil)
			case "short_ed25519":
				vals.Validators[0].PubKey = cmted.PubKey{1}
			case "short_secp256k1":
				vals.Validators[0].PubKey = cmtsecp.PubKey{2}
			case "unsupported_wire_key":
				intercept = func(w http.ResponseWriter, request *http.Request) bool {
					if request.URL.Path != "/validators" {
						return false
					}
					height, _ := strconv.ParseInt(request.URL.Query().Get("height"), 10, 64)
					data, _ := cmtjson.Marshal(&core.ResultValidators{BlockHeight: height, Validators: vals.Validators, Count: 1, Total: 1})
					var body map[string]any
					if json.Unmarshal(data, &body) != nil {
						t.Error("invalid fixture")
					}
					body["validators"].([]any)[0].(map[string]any)["pub_key"].(map[string]any)["type"] = "attacker/UnsupportedKey"
					encoded, _ := json.Marshal(body)
					fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, encoded)
					return true
				}
			}
			primary := adversarialTrustedServer(t, f, vals, intercept)
			witness := trustedFixtureServer(t, f, vals)
			r := adversarialTrustedReader(t, f, primary, witness, anchor)
			assertTrustedRefusal(t, r, f)
		})
	}
}

func TestTrustedReaderAuthenticatedObservationIsImmutable(t *testing.T) {
	f, vals := signedReaderFixture(t)
	r := trustedFixture(t, f, vals, fixtureAnchor(f))
	evidence, err := readTrustedFixture(r, f)
	if err != nil {
		t.Fatal(err)
	}
	original := evidence.Observation()
	changed := evidence.Observation()
	changed.TxBytes[0] ^= 0xff
	changed.Transfers[0].Amount = "999"
	*changed.Code = 9
	*changed.TransferIndex = 99
	*changed.Head.CatchingUp = true
	*changed.IndependentHead.CatchingUp = true
	if !reflect.DeepEqual(evidence.Observation(), original) || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
		t.Fatal("public observation changed authenticated evidence")
	}
	receipt := evidence.Receipt()
	receipt.TxHash = strings.Repeat("F", 64)
	if evidence.Receipt().TxHash == receipt.TxHash {
		t.Fatal("public receipt changed authenticated evidence")
	}
}

func adversarialCommit(t *testing.T, header *cmt.Header) *core.ResultCommit {
	t.Helper()
	key := cmted.GenPrivKeyFromSecret([]byte("synthetic-light-client-fixture"))
	id := cmt.BlockID{Hash: header.Hash(), PartSetHeader: cmt.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
	vote := cmtproto.Vote{Type: cmtproto.PrecommitType, Height: header.Height, BlockID: id.ToProto(), Timestamp: header.Time, ValidatorAddress: key.PubKey().Address()}
	signature, err := key.Sign(cmt.VoteSignBytes(ChainID, &vote))
	if err != nil {
		t.Fatal(err)
	}
	commit := &cmt.Commit{Height: header.Height, BlockID: id, Signatures: []cmt.CommitSig{{BlockIDFlag: cmt.BlockIDFlagCommit, ValidatorAddress: key.PubKey().Address(), Timestamp: header.Time, Signature: signature}}}
	return core.NewResultCommit(header, commit, true)
}

func TestTrustedReaderRejectsSignedFollowingHeaderSubstitution(t *testing.T) {
	f, vals := signedReaderFixture(t)
	copy := *f.commits[101].Header
	copy.LastResultsHash = bytes.Repeat([]byte{42}, 32)
	alternate := adversarialCommit(t, &copy)
	makeServer := func() *httptest.Server {
		var requests atomic.Int32
		return adversarialTrustedServer(t, f, vals, func(w http.ResponseWriter, request *http.Request) bool {
			if request.URL.Path != "/commit" || request.URL.Query().Get("height") != "101" || requests.Add(1) == 1 {
				return false
			}
			encoded, _ := cmtjson.Marshal(alternate)
			fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, encoded)
			return true
		})
	}
	r := adversarialTrustedReader(t, f, makeServer(), makeServer(), fixtureAnchor(f))
	typed := assertTrustedRefusal(t, r, f)
	if typed.Code != InconsistentObservations || typed.Operation != "result_header" {
		t.Fatalf("did not bind authenticated H+1 to the collected result root: %v", typed)
	}
}

func TestTrustedReaderAnchorCannotExpireDuringVerification(t *testing.T) {
	f, vals := signedReaderFixture(t)
	f.commits[100].Header.Time = f.now.Add(-59 * time.Second)
	for height := int64(100); height <= 102; height++ {
		if height > 100 {
			f.commits[height].Header.LastBlockID = f.commits[height-1].Commit.BlockID
			f.commits[height].Header.LastCommitHash = f.commits[height-1].Commit.Hash()
		}
		f.commits[height] = adversarialCommit(t, f.commits[height].Header)
	}
	f.status.SyncInfo.LatestBlockHash = f.commits[102].Header.Hash()
	f.rest["tx_response"].(map[string]any)["timestamp"] = f.commits[100].Time.Format(time.RFC3339Nano)
	anchor := fixtureAnchor(f)
	anchor.PeriodSeconds = 60
	var advanced atomic.Bool
	primary := adversarialTrustedServer(t, f, vals, func(_ http.ResponseWriter, request *http.Request) bool {
		if request.URL.Path == "/validators" && request.URL.Query().Get("height") == "101" {
			advanced.Store(true)
		}
		return false
	})
	witness := trustedFixtureServer(t, f, vals)
	r := adversarialTrustedReader(t, f, primary, witness, anchor)
	r.reader.now = func() time.Time {
		if advanced.Load() {
			return f.now.Add(2 * time.Second)
		}
		return f.now
	}
	typed := assertTrustedRefusal(t, r, f)
	if !advanced.Load() || typed.Code != UntrustedConsensus {
		t.Fatalf("did not refuse anchor expiration during the verification: %v", typed)
	}
}

func TestTrustedReaderMissingOrUnavailableWitnessCannotAuthenticate(t *testing.T) {
	f, vals := signedReaderFixture(t)
	primary := trustedFixtureServer(t, f, vals)
	for _, witness := range []string{"", primary.URL, primary.URL + "/"} {
		r, err := NewTrustedReader(SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness}, fixtureAnchor(f))
		if err == nil {
			r.Close()
			t.Errorf("missing or normalized-identical witness accepted: %q", witness)
		}
	}
	witness := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusServiceUnavailable) }))
	t.Cleanup(witness.Close)
	r := adversarialTrustedReader(t, f, primary, witness, fixtureAnchor(f))
	assertTrustedRefusal(t, r, f)
}

func TestTrustedReaderLatestProviderReservesAllThreeRequests(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(server.Close)
	r, err := NewChainReader(SourceConfig{RPC: server.URL, REST: server.URL})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(r.Close)
	budget := &lightBudget{remaining: 1024, calls: 2}
	p := &boundedProvider{reader: r, base: r.rpc, label: "primary", budget: budget}
	_, err = p.LightBlock(context.Background(), 0)
	if err == nil || requests.Load() != 0 || budget.calls != 2 {
		t.Fatalf("latest lookup exceeded its three-call reservation: requests=%d calls=%d err=%v", requests.Load(), budget.calls, err)
	}
}

func TestTrustedReaderZeroEvidenceCannotClaimAuthentication(t *testing.T) {
	var evidence AuthenticatedEvidence
	if evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || CurrentCapability().Available() {
		t.Fatal("empty evidence granted chain or custody authority")
	}
}
