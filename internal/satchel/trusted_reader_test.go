package satchel

import (
	"bytes"
	"context"
	bankbase "cosmossdk.io/api/cosmos/base/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"encoding/hex"
	"fmt"
	gproto "google.golang.org/protobuf/proto"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	proto "github.com/cometbft/cometbft/proto/tendermint/types"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
)

// These are genuine signatures over a synthetic chain. No real checkpoint,
// validator key, wallet, custody certification or live transaction is used.
func signedReaderFixture(t *testing.T) (*readerFixture, *cmt.ValidatorSet) {
	f := newReaderFixture(t)
	var raw txapi.TxRaw
	_ = gproto.Unmarshal(f.tx.Tx, &raw)
	raw.AuthInfoBytes, _ = gproto.Marshal(&txapi.AuthInfo{Fee: &txapi.Fee{Amount: []*bankbase.Coin{{Denom: Denom, Amount: "1"}}, GasLimit: 10000}})
	data, _ := gproto.Marshal(&raw)
	f.tx.Tx = cmt.Tx(data)
	f.tx.Hash = f.tx.Tx.Hash()
	f.tx.Proof = cmt.Txs{f.tx.Tx}.Proof(0)
	f.observation.TxHash = hex.EncodeToString(f.tx.Hash)
	f.observation.TxBytes = data
	f.rest["tx_response"].(map[string]any)["txhash"] = strings.ToUpper(f.observation.TxHash)
	f.commits[100].Header.DataHash = cmt.Txs{f.tx.Tx}.Hash()
	key := cmted.GenPrivKeyFromSecret([]byte("synthetic-light-client-fixture"))
	vals := cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(key.PubKey(), 10)})
	for height := int64(100); height <= 102; height++ {
		h := f.commits[height].Header
		h.ValidatorsHash = vals.Hash()
		h.NextValidatorsHash = vals.Hash()
		h.ProposerAddress = key.PubKey().Address()
		if height > 100 {
			h.LastBlockID = f.commits[height-1].Commit.BlockID
			h.LastCommitHash = f.commits[height-1].Commit.Hash()
		}
		id := cmt.BlockID{Hash: h.Hash(), PartSetHeader: cmt.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
		vote := proto.Vote{Type: proto.PrecommitType, Height: height, Round: 0, BlockID: id.ToProto(), Timestamp: h.Time, ValidatorAddress: key.PubKey().Address(), ValidatorIndex: 0}
		signature, err := key.Sign(cmt.VoteSignBytes(ChainID, &vote))
		if err != nil {
			t.Fatal(err)
		}
		f.commits[height].Commit = &cmt.Commit{Height: height, Round: 0, BlockID: id, Signatures: []cmt.CommitSig{{BlockIDFlag: cmt.BlockIDFlagCommit, ValidatorAddress: key.PubKey().Address(), Timestamp: h.Time, Signature: signature}}}
	}
	f.status.SyncInfo.LatestBlockHash = f.commits[102].Header.Hash()
	return f, vals
}
func trustedFixtureServer(t *testing.T, f *readerFixture, vals *cmt.ValidatorSet) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			t.Error("write attempted")
		}
		if r.URL.Path == "/validators" {
			height, _ := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
			if r.URL.Query().Get("page") != "1" || r.URL.Query().Get("per_page") != "100" {
				t.Error("unbounded validator pagination")
			}
			b, _ := cmtjson.Marshal(&core.ResultValidators{BlockHeight: height, Validators: vals.Validators, Count: len(vals.Validators), Total: len(vals.Validators)})
			fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, b)
			return
		}
		w.Write(f.response(t, r))
	}))
	t.Cleanup(s.Close)
	return s
}
func trustedFixture(t *testing.T, f *readerFixture, vals *cmt.ValidatorSet, a TrustAnchor) *TrustedReader {
	s := trustedFixtureServer(t, f, vals)
	w := trustedFixtureServer(t, f, vals)
	r, err := NewTrustedReader(SourceConfig{RPC: s.URL, REST: s.URL, WitnessRPC: w.URL}, a)
	if err != nil {
		t.Fatal(err)
	}
	r.reader.now = func() time.Time { return f.now }
	t.Cleanup(r.Close)
	return r
}
func fixtureAnchor(f *readerFixture) TrustAnchor {
	return TrustAnchor{100, hex.EncodeToString(f.commits[100].Header.Hash()), 3600, "synthetic-independent-checkpoint"}
}
func TestTrustedReaderAuthenticatesRealCommitSignatures(t *testing.T) {
	f, v := signedReaderFixture(t)
	r := trustedFixture(t, f, v, fixtureAnchor(f))
	e, err := r.ReadTransfer(context.Background(), TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}, f.observation.TxHash)
	if err != nil {
		t.Fatal(err)
	}
	if !e.ConsensusAuthenticated() || e.CreditAuthorized() || e.Receipt().ID() != ChainID+":"+strings.ToUpper(f.observation.TxHash)+":0" {
		t.Fatalf("bad trust scope %+v", e)
	}
	if CurrentCapability().Available() {
		t.Fatal("chain authentication unlocked custody")
	}
}
func TestTrustedReaderRejectsForgedCommitAndPin(t *testing.T) {
	for _, mode := range []string{"pin", "signature", "validators", "expired"} {
		t.Run(mode, func(t *testing.T) {
			f, v := signedReaderFixture(t)
			a := fixtureAnchor(f)
			switch mode {
			case "pin":
				a.Hash = fmt.Sprintf("%064x", 42)
			case "signature":
				f.commits[101].Commit.Signatures[0].Signature = bytes.Repeat([]byte{9}, 64)
			case "validators":
				v = cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(cmted.GenPrivKeyFromSecret([]byte("attacker")).PubKey(), 10)})
			case "expired":
				a.PeriodSeconds = 60
				f.now = f.now.Add(2 * time.Minute)
				for h := range f.commits {
					_ = h
				}
			}
			r := trustedFixture(t, f, v, a)
			_, err := r.ReadTransfer(context.Background(), TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}, f.observation.TxHash)
			if err == nil {
				t.Fatal("forged or stale trust accepted")
			}
		})
	}
}
func TestTrustedReaderConfigurationFailsClosed(t *testing.T) {
	for _, a := range []TrustAnchor{{}, {Height: 1, Hash: fmt.Sprintf("%064x", 1), PeriodSeconds: 3600}, {Height: 1, Hash: fmt.Sprintf("%064x", 1), PeriodSeconds: 86401, EvidenceReference: "unreviewed"}} {
		if _, err := NewTrustedReader(SourceConfig{RPC: "https://same.example", REST: "https://rest.example", WitnessRPC: "https://same.example"}, a); err == nil {
			t.Fatal("missing trust accepted")
		}
	}
}
