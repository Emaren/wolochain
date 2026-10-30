package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	base "cosmossdk.io/api/cosmos/base/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	bolt "go.etcd.io/bbolt"
	"google.golang.org/protobuf/proto"
)

func custodyFeeStoreUnsigned(t *testing.T, e *Engine, r TransferRequest) {
	t.Helper()
	rec := record{Request: r, Fingerprint: fingerprint(r), Result: Result{OperationID: r.OperationID, Status: "UNKNOWN", DurableFenced: true}}
	if err := e.db.Update(func(tx *bolt.Tx) error { return save(tx, rec) }); err != nil {
		t.Fatal(err)
	}
}

func TestCustodyFeeCheckpointIncludesAllUnresolvedAndExactRequestedStatuses(t *testing.T) {
	b := &engineTestBackend{signErr: errors.New("isolated signing uncertainty")}
	e, _, _ := engineTestOpen(t, b)
	first, second := engineTestWager(t, "1"), engineTestWager(t, "2")
	if _, err := e.Submit(t.Context(), first); err != nil {
		t.Fatal(err)
	}
	// A historical unresolved operation without a provable canonical fee must
	// retain the conservative maximum; no request list may hide it.
	second.Reservation = nil
	custodyFeeStoreUnsigned(t, e, second)
	before := readTestCustodyJournal(t, e)
	e.now = func() time.Time { return time.Unix(1800003600, 0) } // expiry never frees a durable fee
	got, err := e.ReviewerFeeCheckpoint([]string{first.OperationID, "satchel:ticket:99"})
	if err != nil {
		t.Fatal(err)
	}
	want := []ReviewerPendingFee{{OperationID: first.OperationID, Stage: "prepared", FeeUWolo: "5000"}, {OperationID: second.OperationID, Stage: "prepared", FeeUWolo: "1000000"}}
	keyDigest := sha256.Sum256(e.policy.WagerApprovalKey)
	if !reflect.DeepEqual(got.UnresolvedFees, want) || got.AccountedOperations[first.OperationID] != "UNKNOWN" || got.AccountedOperations["satchel:ticket:99"] != "NOT_RECORDED" ||
		got.AccountedFingerprints[first.OperationID] != e.custodyWagerFingerprint(first) || got.AccountedFingerprints[first.OperationID] == "" || got.AccountedFingerprints["satchel:ticket:99"] != "" ||
		got.WagerApprovalKeyFingerprint != hex.EncodeToString(keyDigest[:]) ||
		got.JournalDigest != before.JournalDigest || got.PolicyDigest != before.PolicyDigest || got.Vault != e.policy.Vault || got.ObservedAtMS != e.now().UnixMilli() {
		t.Fatalf("checkpoint lost actual unresolved fees: %+v", got)
	}
	empty, err := e.ReviewerFeeCheckpoint(nil)
	if err != nil || !reflect.DeepEqual(empty.UnresolvedFees, want) || len(empty.AccountedOperations) != 0 || len(empty.AccountedFingerprints) != 0 {
		t.Fatal("caller filtered unresolved obligations", empty, err)
	}
	if after := readTestCustodyJournal(t, e); !reflect.DeepEqual(before, after) || b.signs.Load() != 1 || b.broadcasts.Load() != 0 || b.confirmations.Load() != 0 {
		t.Fatal("fee read mutated or executed the journal")
	}
}

func TestCustodyFeeCheckpointBindsOriginalIssuerIdentityBeforeNormalizing(t *testing.T) {
	for _, mutation := range []string{"unchanged", "owner", "fee", "reservation"} {
		t.Run(mutation, func(t *testing.T) {
			e, _, _ := engineTestOpen(t, &engineTestBackend{})
			original := engineTestWager(t, "1")
			issuerOriginal := *original.Reservation
			issuerOriginal.IssuedAt, issuerOriginal.ExpiresAt, issuerOriginal.Signature = 0, 0, ""
			issuerFingerprint := reviewerFingerprint(issuerOriginal)
			stored := original
			a := *original.Reservation
			stored.Reservation = &a
			switch mutation {
			case "owner":
				stored.OwnerID, a.OwnerID = "owner-2", "owner-2"
			case "fee":
				a.FeeUWolo = "6000"
			case "reservation":
				a.ReservationDigest = strings.Repeat("d", 64)
			}
			a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(a)))
			custodyFeeStoreUnsigned(t, e, stored)
			// A terminal record with a reused operation ID still cannot account
			// for a different issuer approval's original financial identity.
			if err := e.db.Update(func(tx *bolt.Tx) error {
				rec, err := load(tx, stored.OperationID)
				if err != nil {
					return err
				}
				rec.Result.Status = "REFUSED"
				return save(tx, rec)
			}); err != nil {
				t.Fatal(err)
			}
			e.now = func() time.Time { return time.Unix(a.ExpiresAt+3600, 0) }
			before := readTestCustodyJournal(t, e)
			got, err := e.ReviewerFeeCheckpoint([]string{stored.OperationID})
			if err != nil || got.AccountedOperations[stored.OperationID] != "REFUSED" || got.AccountedFingerprints[stored.OperationID] == "" || len(got.UnresolvedFees) != 0 {
				t.Fatal("authenticated original identity missing", got, err)
			}
			matches := got.AccountedFingerprints[stored.OperationID] == issuerFingerprint
			if matches != (mutation == "unchanged") {
				t.Fatal("operation ID confused different owner/fee/reservation identities", mutation, got)
			}
			if !reflect.DeepEqual(before, readTestCustodyJournal(t, e)) || stored.Reservation.IssuedAt == 0 || stored.Reservation.Signature == "" {
				t.Fatal("identity normalization changed durable approval")
			}
		})
	}
}

func TestCustodyFeeCheckpointUnverifiableUnsignedFeeRetainsMaximumWithoutIdentity(t *testing.T) {
	for _, mutation := range []string{"missing", "ownerless", "forged", "fee", "noncanonical-amount", "conflicting-approval", "zero-issued"} {
		t.Run(mutation, func(t *testing.T) {
			e, _, _ := engineTestOpen(t, &engineTestBackend{})
			r := engineTestWager(t, "1")
			switch mutation {
			case "missing":
				r.Reservation = nil
			case "ownerless":
				r.OwnerID, r.Reservation = "", nil
			case "forged":
				r.Reservation.Signature = base64.StdEncoding.EncodeToString(make([]byte, ed25519.SignatureSize))
			case "fee":
				r.Reservation.FeeUWolo = "1" // Caller mutation is not reviewer authority.
			case "noncanonical-amount":
				r.AmountUWolo, r.Reservation.AmountUWolo = "1000001", "1000001"
				r.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(*r.Reservation)))
			case "conflicting-approval":
				r.Approval = &WithdrawalApproval{}
			case "zero-issued":
				r.Reservation.IssuedAt, r.Reservation.ExpiresAt = 0, 120
				r.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(*r.Reservation)))
			}
			custodyFeeStoreUnsigned(t, e, r)
			got, err := e.ReviewerFeeCheckpoint([]string{r.OperationID})
			if err != nil || len(got.UnresolvedFees) != 1 || got.UnresolvedFees[0].FeeUWolo != "1000000" || got.AccountedFingerprints[r.OperationID] != "" || got.AccountedOperations[r.OperationID] != "UNKNOWN" {
				t.Fatal("unverifiable original understated fees or acquired issuer identity", mutation, got, err)
			}
		})
	}
}

func TestCustodyFeeCheckpointParsesActualValidatedCosmosSignedFee(t *testing.T) {
	f := newBackendFixture(t)
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	p := Policy{Vault: f.request.Sender, BettingEscrow: f.request.Recipient, MaxAmountUWolo: 1000000000,
		ProtectedAddresses:    []string{f.request.Recipient},
		WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
	e, err := Open(filepath.Join(dir, "native-fee.db"), p, f.b)
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	signed, err := f.b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	if err = f.b.ValidateSigned(f.request, signed); err != nil {
		t.Fatal(err)
	}
	r := record{Request: f.request, Fingerprint: fingerprint(f.request), Signed: signed,
		Result: Result{OperationID: f.request.OperationID, Status: "UNKNOWN", TxHash: signed.Hash, DurableFenced: true}}
	if err = e.db.Update(func(tx *bolt.Tx) error { return save(tx, r) }); err != nil {
		t.Fatal(err)
	}
	before := readTestCustodyJournal(t, e)
	got, err := e.ReviewerFeeCheckpoint([]string{f.request.OperationID})
	keyDigest := sha256.Sum256(p.WagerApprovalKey)
	if err != nil || len(got.UnresolvedFees) != 1 || got.UnresolvedFees[0].Stage != "uncertain" || got.UnresolvedFees[0].FeeUWolo != "2500" || got.WagerApprovalKeyFingerprint != hex.EncodeToString(keyDigest[:]) {
		t.Fatalf("actual Cosmos fee was not read: %+v %v", got, err)
	}
	if !reflect.DeepEqual(before, readTestCustodyJournal(t, e)) || f.signer.calls.Load() != 1 || f.broadcasts.Load() != 0 {
		t.Fatal("fee checkpoint signed or broadcast")
	}
	// The real backend independently rejects byte corruption; recomputing the
	// journal's unkeyed fingerprint cannot manufacture a valid native signature.
	if err = e.db.Update(func(tx *bolt.Tx) error {
		v := tx.Bucket(operations).Get([]byte(f.request.OperationID))
		var stored record
		if json.Unmarshal(v, &stored) != nil {
			return errors.New("fixture")
		}
		stored.Signed.Bytes[0] ^= 1
		return save(tx, stored)
	}); err != nil {
		t.Fatal(err)
	}
	if got, err = e.ReviewerFeeCheckpoint([]string{}); err == nil || !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) {
		t.Fatal("corrupt native record returned partial fees")
	}
}

func TestCustodyFeeCheckpointLegacyPolicyDoesNotInventApprovalKey(t *testing.T) {
	for _, key := range []ed25519.PublicKey{nil, make(ed25519.PublicKey, ed25519.PublicKeySize-1), make(ed25519.PublicKey, ed25519.PublicKeySize)} {
		dir, err := filepath.EvalSymlinks(t.TempDir())
		if err != nil {
			t.Fatal(err)
		}
		policy := engineTestPolicy(t)
		policy.WagerApprovalKey = key
		e, err := Open(filepath.Join(dir, "legacy.db"), policy, &engineTestBackend{})
		if err != nil {
			t.Fatal(err)
		}
		got, err := e.ReviewerFeeCheckpoint([]string{})
		_ = e.Close()
		if err != nil || got.WagerApprovalKeyFingerprint != "" || got.PolicyDigest != hashJSON(policy) {
			t.Fatal("read invented approval authority for an unconfigured policy", got, err)
		}
	}
}

func TestCustodyFeeCheckpointTerminalStatusesAndInputBounds(t *testing.T) {
	for _, terminal := range []string{"CONFIRMED", "FAILED", "REFUSED"} {
		t.Run(terminal, func(t *testing.T) {
			b := &engineTestBackend{confirmationStatus: terminal}
			if terminal == "REFUSED" {
				b.signErr = ErrPreSignRefused
			}
			e, _, _ := engineTestOpen(t, b)
			r := engineTestWager(t, "1")
			if _, err := e.Submit(t.Context(), r); err != nil {
				t.Fatal(err)
			}
			if terminal != "REFUSED" {
				if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
					t.Fatal(err)
				}
			}
			j := readTestCustodyJournal(t, e)
			got, err := e.ReviewerFeeCheckpoint([]string{r.OperationID})
			if err != nil || len(got.UnresolvedFees) != 0 || got.AccountedOperations[r.OperationID] != terminal || got.JournalDigest != j.JournalDigest {
				t.Fatal("terminal status changed into bank headroom", got, err)
			}
		})
	}
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	tooMany := make([]string, custodyFeeCheckpointMaxIDs+1)
	for i := range tooMany {
		tooMany[i] = "satchel:ticket:" + strconv.Itoa(i+1)
	}
	if err := validateCustodyFeeIDs(tooMany[:custodyFeeCheckpointMaxIDs]); err != nil {
		t.Fatal("bounded canonical ID list rejected", err)
	}
	for _, ids := range [][]string{{"satchel:ticket:1", "satchel:ticket:1"}, {"satchel:ticket:01"}, {"satchel:withdrawal:1"}, {"../outside"}, tooMany} {
		if got, err := e.ReviewerFeeCheckpoint(ids); err == nil || !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) {
			t.Fatal("invalid request accepted", ids)
		}
	}
	if got, err := (*Engine)(nil).ReviewerFeeCheckpoint([]string{}); err == nil || !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) {
		t.Fatal("nil engine accepted")
	}
	if err := e.db.Update(func(tx *bolt.Tx) error { return tx.Bucket(meta).Put([]byte("policy"), []byte("corrupt")) }); err != nil {
		t.Fatal(err)
	}
	if got, err := e.ReviewerFeeCheckpoint([]string{}); err == nil || !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) {
		t.Fatal("corrupt policy returned partial checkpoint")
	}
}

func TestCustodyFeeCheckpointSharesJournalResourceBoundsWithoutPartialOutput(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	if err := e.db.Update(func(tx *bolt.Tx) error {
		bucket, err := tx.CreateBucket([]byte("extra"))
		if err != nil {
			return err
		}
		return bucket.Put([]byte("huge"), make([]byte, custodyJournalMaxBytes))
	}); err != nil {
		t.Fatal(err)
	}
	if got, err := e.ReviewerFeeCheckpoint([]string{}); err == nil || !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) {
		t.Fatal("checkpoint bypassed the bounded journal or returned partial inventory", got, err)
	}
}

func TestCustodyFeeCheckpointFeeParserCannotReturnZeroOrUnderstateAboveCap(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	for _, amount := range []string{"0", "1", "1000000", "1000001", "01"} {
		auth, _ := proto.Marshal(&txapi.AuthInfo{Fee: &txapi.Fee{Amount: []*base.Coin{{Denom: "uwolo", Amount: amount}}}})
		raw, _ := proto.Marshal(&txapi.TxRaw{AuthInfoBytes: auth, Signatures: [][]byte{{1}}})
		fee, err := e.custodyUnresolvedFee(record{Signed: SignedTransaction{Bytes: raw}})
		if amount == "1000001" || amount == "01" {
			if err == nil {
				t.Fatal("unbounded/noncanonical actual fee accepted", amount, fee)
			}
			continue
		}
		want := amount
		if want == "0" {
			want = "1000000"
		}
		if err != nil || fee != want {
			t.Fatal(amount, fee, err)
		}
	}
}

func TestCustodyFeeCheckpointHTTPStrictPrivateReadOnlyRoute(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{signErr: errors.New("isolated signing uncertainty")})
	request := engineTestWager(t, "1")
	if _, err := e.Submit(t.Context(), request); err != nil {
		t.Fatal(err)
	}
	cfg := testHTTPConfig(t)
	cfg.Accepting = false
	cfg.Health.VaultAddress = e.policy.Vault
	h := testHTTPHandler(t, e, cfg)
	call := func(method, body, peer, token string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, "http://localhost/satchel/v1/custody/fee-checkpoint", strings.NewReader(body))
		r.RemoteAddr = peer
		r.Header.Set("Authorization", "Bearer "+token)
		r.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w
	}
	before := readTestCustodyJournal(t, e)
	w := call(http.MethodPost, `{"protocol":1,"operation_ids":["satchel:ticket:99","satchel:ticket:1"]}`, "127.0.0.1:1234", testHTTPToken)
	var got ReviewerCustodyFeeCheckpoint
	if w.Code != http.StatusOK || json.Unmarshal(w.Body.Bytes(), &got) != nil || got.AccountedOperations["satchel:ticket:99"] != "NOT_RECORDED" ||
		got.AccountedFingerprints["satchel:ticket:99"] != "" || got.AccountedOperations[request.OperationID] != "UNKNOWN" ||
		got.AccountedFingerprints[request.OperationID] != e.custodyWagerFingerprint(request) || len(got.UnresolvedFees) != 1 || got.UnresolvedFees[0].FeeUWolo != "5000" {
		t.Fatal(w.Code, w.Body.String())
	}
	// Even without an execution permit this authenticated read is available;
	// the optional interface is never synthesized from legacy Lookup results.
	withoutCheckpoint := testHTTPHandler(t, &httpTestBackend{}, cfg)
	absent := httptest.NewRequest(http.MethodPost, "http://localhost/satchel/v1/custody/fee-checkpoint", strings.NewReader(`{"protocol":1,"operation_ids":[]}`))
	absent.RemoteAddr = "127.0.0.1:1234"
	absent.Header.Set("Authorization", "Bearer "+testHTTPToken)
	absent.Header.Set("Content-Type", "application/json")
	unavailable := httptest.NewRecorder()
	withoutCheckpoint.ServeHTTP(unavailable, absent)
	if unavailable.Code != http.StatusServiceUnavailable {
		t.Fatal("legacy backend invented a fee checkpoint", unavailable.Code)
	}
	for _, body := range []string{`{"protocol":2,"operation_ids":[]}`, `{"protocol":1}`, `{"protocol":1,"operation_ids":null}`, `{"protocol":1,"operation_ids":[],"fee_uwolo":"1"}`, `{"protocol":1,"operation_ids":[],"Protocol":1}`, `{"protocol":1,"operation_ids":["satchel:ticket:1","satchel:ticket:1"]}`, `{"protocol":1,"operation_ids":[],"protocol":1}`} {
		if w := call(http.MethodPost, body, "127.0.0.1:1234", testHTTPToken); w.Code != http.StatusBadRequest {
			t.Fatal("invalid body accepted", body, w.Code)
		}
	}
	if w := call(http.MethodPost, strings.Repeat(" ", custodyFeeCheckpointMaxBody+1), "127.0.0.1:1234", testHTTPToken); w.Code != http.StatusRequestEntityTooLarge {
		t.Fatal("unbounded body accepted", w.Code)
	}
	if w := call(http.MethodGet, "", "127.0.0.1:1234", testHTTPToken); w.Code != http.StatusMethodNotAllowed {
		t.Fatal("GET accepted", w.Code)
	}
	if w := call(http.MethodPost, `{"protocol":1,"operation_ids":[]}`, "203.0.113.1:1234", testHTTPToken); w.Code != http.StatusUnauthorized {
		t.Fatal("remote peer accepted", w.Code)
	}
	if w := call(http.MethodPost, `{"protocol":1,"operation_ids":[]}`, "127.0.0.1:1234", "wrong"); w.Code != http.StatusUnauthorized {
		t.Fatal("wrong bearer accepted", w.Code)
	}
	if !reflect.DeepEqual(before, readTestCustodyJournal(t, e)) {
		t.Fatal("HTTP checkpoint mutated journal")
	}
	// The existing GET journal endpoint retains its exact output contract.
	r := httptest.NewRequest(http.MethodGet, "http://localhost/satchel/v1/custody/journal", nil)
	r.RemoteAddr = "127.0.0.1:1234"
	r.Header.Set("Authorization", "Bearer "+testHTTPToken)
	w = httptest.NewRecorder()
	h.ServeHTTP(w, r)
	wire, _ := json.Marshal(before)
	if w.Code != http.StatusOK || !bytes.Equal(bytes.TrimSpace(w.Body.Bytes()), wire) {
		t.Fatal("legacy journal wire changed", w.Code, w.Body.String())
	}
}
