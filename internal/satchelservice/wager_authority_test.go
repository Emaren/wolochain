package satchelservice

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestWagerReservationExactCrossLanguageFixture(t *testing.T) {
	r := engineTestWager(t, "1")
	f := map[string]any{"fixture_only": true, "mainnet_authority": false,
		"approval_public_key_hex": hex.EncodeToString(engineTestPolicy(t).WithdrawalApprovalKey),
		"reservation":             r.Reservation, "reservation_sign_bytes": string(WagerReservationMessage(*r.Reservation))}
	want, _ := json.Marshal(f)
	actual, err := os.ReadFile("testdata/wager-reservation-v1.json")
	if err != nil {
		t.Fatalf("FIXTURE_BEGIN\n%s\nFIXTURE_END", want)
	}
	var decoded any
	if json.Unmarshal(actual, &decoded) != nil {
		t.Fatal("invalid fixture")
	}
	canonical, _ := json.Marshal(decoded)
	var expected any
	if json.Unmarshal(want, &expected) != nil {
		t.Fatal("invalid source fixture")
	}
	want, _ = json.Marshal(expected)
	if string(canonical) != string(want) {
		t.Fatal("wager reservation signing fixture drift")
	}
}

// This test also compiles against the PR38 base: a bearer-selected operation
// and valid ticket memo alone must never authorize a new customer debit.
func TestEngineWagerServiceTokenCannotSpendUnreservedCustody(t *testing.T) {
	b := &engineTestBackend{}
	e, _, p := engineTestOpen(t, b)
	r := TransferRequest{OperationID: "satchel:ticket:717", ChainID: "wolo-1", Denom: "uwolo", Sender: p.Vault, Recipient: p.BettingEscrow, AmountUWolo: "1000000", Memo: "AoE2HDBets bet ticket v1 · ticket 717", Kind: "wager", OwnerID: "owner-1"}
	if _, err := e.Submit(t.Context(), r); err == nil {
		t.Fatal("bearer-only request spent unreserved custody")
	}
	if b.signs.Load() != 0 || b.broadcasts.Load() != 0 {
		t.Fatal("unapproved custody reached signer")
	}
	if _, err := e.Lookup(r.OperationID); err == nil {
		t.Fatal("missing authority created a financial intent")
	}
}

func TestWagerReservationBindsExactOwnerHoldConsentEconomicsAndFee(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*TransferRequest)
	}{
		{"missing", func(r *TransferRequest) { r.Reservation = nil }},
		{"owner", func(r *TransferRequest) { r.OwnerID = "another-owner" }},
		{"operation", func(r *TransferRequest) { r.OperationID = "satchel:ticket:2" }},
		{"amount", func(r *TransferRequest) { r.AmountUWolo = "1000001" }},
		{"recipient", func(r *TransferRequest) { r.Recipient = r.Sender }},
		{"memo", func(r *TransferRequest) { r.Memo = "AoE2HDBets bet ticket v1 · ticket 2" }},
		{"expired", func(r *TransferRequest) { r.Reservation.ExpiresAt = 1800000000 }},
		{"future", func(r *TransferRequest) { r.Reservation.IssuedAt = 1800000001 }},
		{"overlong", func(r *TransferRequest) { r.Reservation.ExpiresAt = r.Reservation.IssuedAt + 301 }},
		{"zerohold", func(r *TransferRequest) { r.Reservation.ReservationDigest = strings.Repeat("0", 64) }},
		{"missingledger", func(r *TransferRequest) { r.Reservation.LedgerRevision = "" }},
		{"missingconsent", func(r *TransferRequest) { r.Reservation.ConsentDigest = "" }},
		{"unapprovedfee", func(r *TransferRequest) { r.Reservation.FeeUWolo = "6000" }},
		{"forged", func(r *TransferRequest) {
			r.Reservation.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64))
		}},
		{"noncanonical", func(r *TransferRequest) { r.Reservation.Signature += "\n" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			b := &engineTestBackend{}
			e, _, _ := engineTestOpen(t, b)
			r := engineTestWager(t, "1")
			test.mutate(&r)
			if _, err := e.Submit(t.Context(), r); err == nil {
				t.Fatal("mismatched or forged reservation accepted")
			}
			if b.signs.Load() != 0 || b.broadcasts.Load() != 0 {
				t.Fatal("invalid reservation reached signing")
			}
		})
	}
}

func TestWagerReservationExpiryDuringSigningKeepsUnknownFence(t *testing.T) {
	b := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, b)
	r := engineTestWager(t, "10")
	b.beforeSign = func(TransferRequest) { e.now = func() time.Time { return time.Unix(r.Reservation.ExpiresAt, 0) } }
	out, err := e.Submit(t.Context(), r)
	if err != nil || out.Status != "UNKNOWN" || out.TxHash == "" || !out.DurableFenced {
		t.Fatalf("expired signed debit lost fence: %+v %v", out, err)
	}
	for n := 0; n < 3; n++ {
		again, err := e.Submit(t.Context(), r)
		if err != nil || again != out {
			t.Fatal("replay altered uncertain debit")
		}
	}
	if b.signs.Load() != 1 || b.broadcasts.Load() != 0 {
		t.Fatal("expired authority signed again or broadcast")
	}
}

func TestWagerReservationCannotFundAnotherOperationAfterConfirmation(t *testing.T) {
	b := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	e, _, p := engineTestOpen(t, b)
	r := engineTestWager(t, "1")
	if _, err := e.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
		t.Fatal(err)
	}
	other := engineTestWager(t, "2")
	other.Reservation.ReservationDigest = r.Reservation.ReservationDigest
	other.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestApprovalKey(), WagerReservationMessage(*other.Reservation)))
	if err := p.verifyWager(other, e.now()); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Submit(t.Context(), other); err == nil {
		t.Fatal("one ledger hold funded two wagers")
	}
	if b.signs.Load() != 1 || b.broadcasts.Load() != 1 {
		t.Fatal("reservation replay caused duplicate payment")
	}
}

func TestReservedWagerV2WireRejectsUnknownMixedAndAliasedFields(t *testing.T) {
	r := engineTestWager(t, "1")
	wire := map[string]any{"protocol": 2, "request_id": r.OperationID, "chain_id": r.ChainID, "signer_role": httpCustodyRole, "from_address": r.Sender, "to_address": r.Recipient, "amount": httpCoin{Denom: r.Denom, Amount: r.AmountUWolo}, "memo": r.Memo, "owner_id": r.OwnerID, "reservation": r.Reservation}
	b, _ := json.Marshal(wire)
	decoded, err := decodeReservedWagerHTTP(b)
	if err != nil || decoded.OwnerID != r.OwnerID || decoded.Reservation.ReservationDigest != r.Reservation.ReservationDigest {
		t.Fatal("valid v2 reservation wire rejected")
	}
	for _, key := range []string{"Owner_ID", "requestId", "rpc_url", "availableUwolo"} {
		wire[key] = "attacker"
		b, _ = json.Marshal(wire)
		if _, err := decodeReservedWagerHTTP(b); err == nil {
			t.Fatalf("accepted unknown/aliased field %s", key)
		}
		delete(wire, key)
	}
}

func TestReservedWagerHTTPAckDoesNotPretendCommittedPayment(t *testing.T) {
	r := engineTestWager(t, "1")
	body, _ := json.Marshal(map[string]any{"protocol": 2, "request_id": r.OperationID, "chain_id": r.ChainID, "signer_role": httpCustodyRole, "from_address": r.Sender, "to_address": r.Recipient, "amount": httpCoin{Denom: r.Denom, Amount: r.AmountUWolo}, "memo": r.Memo, "owner_id": r.OwnerID, "reservation": r.Reservation})
	b := &httpTestBackend{}
	h := testHTTPHandler(t, b, testHTTPConfig(t))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v2/one-shot", string(body)))
	response := testHTTPRead(t, w)
	if w.Code != 200 || response["status"] != "ACCEPTED" || response["kind"] != "broadcast_accepted" || response["confirmed"] != false || response["credit_authorized"] != false {
		t.Fatalf("acceptance falsely confirmed payment: %v", response)
	}
	if b.submissions.Load() != 1 {
		t.Fatal("v2 did not submit once")
	}
}

type journalHTTPBackend struct{ *Engine }

func TestCustodyJournalHTTPStaysReadOnlyAfterPermitExpiry(t *testing.T) {
	b := &engineTestBackend{}
	e, _, p := engineTestOpen(t, b)
	cfg := testHTTPConfig(t)
	cfg.Health.VaultAddress = p.Vault
	cfg.Authorize = func(_ context.Context) bool { return false }
	h := testHTTPHandler(t, &journalHTTPBackend{e}, cfg)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/custody/journal", ""))
	response := testHTTPRead(t, w)
	if w.Code != 200 || response["custody_capability"] != "UNAVAILABLE" || response["credit_authorized"] != false || response["bank_balance_authenticated"] != false || response["solvency_authorized"] != false {
		t.Fatalf("journal became unavailable or invented authority: %v", response)
	}
	if b.signs.Load() != 0 || b.broadcasts.Load() != 0 || b.confirmations.Load() != 0 {
		t.Fatal("checkpoint invoked financial execution")
	}
}
