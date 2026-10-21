package satchelservice

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"

	"cosmossdk.io/collections"
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/internal/satchel"
)

type bankHTTPFixture struct {
	httpTestBackend
	calls int
	vault string
}

func (b *bankHTTPFixture) BankProof(context.Context) (satchel.BankProof, error) {
	b.calls++
	addr, _ := sdk.GetFromBech32(b.vault, "wolo")
	key, _ := collections.EncodeKeyWithPrefix(banktypes.BalancesPrefix, collections.PairKeyCodec(sdk.AccAddressKey, collections.StringKey), collections.Join(sdk.AccAddress(addr), "uwolo"))
	q := url.Values{"path": {strconv.Quote("/store/bank/key")}, "data": {"0x" + strings.ToUpper(hex.EncodeToString(key))}, "height": {"100"}, "prove": {"true"}}
	// Deliberately UNTRUSTED transcript: the route transports evidence; only
	// the separately pinned offline Comet/ICS23 verifier can authenticate it.
	return satchel.BankProof{Version: 1, ChainID: "wolo-1", Denom: "uwolo", Address: b.vault, Height: 100, Responses: []satchel.ProofResponse{{Source: "primary", Path: "/abci_query", Query: q.Encode(), Body: json.RawMessage(`{}`)}}}, nil
}
func TestBankProofHTTPIsReadOnlyAndCannotSelectVaultOrHeight(t *testing.T) {
	cfg := testHTTPConfig(t)
	cfg.Authorize = func(context.Context) bool { return false }
	b := &bankHTTPFixture{vault: cfg.Health.VaultAddress}
	h := testHTTPHandler(t, b, cfg)
	for _, body := range []string{`{}`, `{"protocol":2}`, `{"protocol":1,"vault":"other"}`, `{"protocol":1,"height":100}`, `{"protocol":1,"protocol":1}`} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, testHTTPRequest("POST", "/satchel/v1/proofs/bank", body))
		if w.Code != 400 || b.calls != 0 {
			t.Fatalf("caller bank authority accepted: %d %d", w.Code, b.calls)
		}
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest("POST", "/satchel/v1/proofs/bank", `{"protocol":1}`))
	if w.Code != 200 || b.calls != 1 || b.submissions.Load() != 0 || b.reconciliations.Load() != 0 || b.lookups.Load() != 0 {
		t.Fatalf("read entered financial execution: %d %s", w.Code, w.Body.String())
	}
	var proof satchel.BankProof
	if json.Unmarshal(w.Body.Bytes(), &proof) != nil || proof.Address != b.vault {
		t.Fatal("wrong bank transcript")
	}
	w = httptest.NewRecorder()
	request := testHTTPRequest("POST", "/satchel/v1/proofs/bank", `{"protocol":1}`)
	request.Header.Del("Authorization")
	h.ServeHTTP(w, request)
	if w.Code != 401 || b.calls != 1 {
		t.Fatal("unauthenticated bank read reached source")
	}
}
