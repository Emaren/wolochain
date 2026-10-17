package satchel

import (
	"context"
	"encoding/hex"
	"strings"
	"testing"

	abci "github.com/cometbft/cometbft/abci/types"
	cmt "github.com/cometbft/cometbft/types"
	"github.com/cosmos/btcutil/bech32"
	sdkaddress "github.com/cosmos/cosmos-sdk/types/address"
	"github.com/emaren/wolochain/internal/chainevents"
)

func feeFixture(t *testing.T, mode string) (*readerFixture, *cmt.ValidatorSet) {
	f, v := signedReaderFixture(t)
	words, _ := bech32.ConvertBits(sdkaddress.Module("fee_collector"), 8, 5, true)
	collector, _ := bech32.Encode("wolo", words)
	fee := abci.Event{Type: "transfer", Attributes: []abci.EventAttribute{{Key: "sender", Value: f.intent.Sender}, {Key: "recipient", Value: collector}, {Key: "amount", Value: "1uwolo"}}}
	send := f.tx.TxResult.Events[0]
	events := []abci.Event{fee, send}
	if mode == "extra" {
		events = append(events, send)
	}
	if mode == "wrong_fee" {
		events[0].Attributes = append([]abci.EventAttribute(nil), fee.Attributes...)
		events[0].Attributes[2].Value = "2uwolo"
	}
	f.tx.TxResult.Events = events
	f.results.TxsResults[0].Events = events
	response := f.rest["tx_response"].(map[string]any)
	response["events"] = transferEvents(events)
	if mode == "logs_without_fee" {
		response["logs"] = []chainevents.LogItem{{Events: transferEvents([]abci.Event{send})}}
	}
	if mode == "reordered_logs" {
		response["logs"] = []chainevents.LogItem{{Events: transferEvents([]abci.Event{send, fee})}}
	}
	f.commits[101].Header.LastResultsHash = cmt.NewResults(f.results.TxsResults).Hash()
	for height := int64(100); height <= 102; height++ {
		h := f.commits[height].Header
		if height > 100 {
			h.LastBlockID = f.commits[height-1].Commit.BlockID
			h.LastCommitHash = f.commits[height-1].Commit.Hash()
		}
		f.commits[height] = adversarialCommit(t, h)
	}
	f.status.SyncInfo.LatestBlockHash = f.commits[102].Header.Hash()
	return f, v
}
func TestOutgoingProofPermitsOnlyExactEncodedFeeAndPreservesOrdinal(t *testing.T) {
	for _, mode := range []string{"fee_before_send", "logs_without_fee", "wrong_fee", "extra", "reordered_logs"} {
		t.Run(mode, func(t *testing.T) {
			f, v := feeFixture(t, mode)
			r := trustedFixture(t, f, v, fixtureAnchor(f))
			proof, err := readTrustedFixture(r, f)
			if mode == "wrong_fee" || mode == "extra" || mode == "reordered_logs" {
				if err == nil {
					t.Fatal("ambiguous extra effects accepted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			want := uint32(1)
			if mode == "logs_without_fee" {
				want = 0
			}
			if proof.Receipt().TransferIndex != want || !proof.ConsensusAuthenticated() {
				t.Fatal("ordinal filtered or renumbered")
			}
			if !strings.EqualFold(proof.Receipt().TxHash, hex.EncodeToString(f.tx.Hash)) {
				t.Fatal("tx identity lost")
			}
			_, err = r.reader.ReadDeposit(context.Background(), f.intent, f.observation.TxHash)
			if err == nil {
				t.Fatal("outgoing fee exception weakened C2 deposits")
			}
		})
	}
}
func TestTrustedReaderChecksRealTrustBeforeOpeningSigner(t *testing.T) {
	f, v := signedReaderFixture(t)
	r := trustedFixture(t, f, v, fixtureAnchor(f))
	if err := r.CheckTrust(context.Background()); err != nil {
		t.Fatal(err)
	}
	f.commits[102].Commit.Signatures[0].Signature = make([]byte, 64)
	if err := r.CheckTrust(context.Background()); err == nil {
		t.Fatal("forged live signing gate accepted")
	}
}
