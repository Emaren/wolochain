package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"strings"
	"testing"
	"time"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	bolt "go.etcd.io/bbolt"
)

func distinctWithdrawalUsingHold(t *testing.T, request TransferRequest, upper bool) TransferRequest {
	t.Helper()
	request.OperationID = "satchel:withdrawal:12345678-1234-4123-8123-123456789abe"
	request.Approval.WithdrawalID = "12345678-1234-4123-8123-123456789abe"
	request.Approval.ChallengeID = "12345678-1234-4123-8123-123456789abf"
	request.Memo = "aoe2war/satchel/withdraw/v1/" + request.Approval.WithdrawalID
	request.Approval.Memo = request.Memo
	request.OwnerMandate.Challenge.ID = request.Approval.ChallengeID
	if upper {
		request.Approval.ReservationDigest = strings.ToUpper(request.Approval.ReservationDigest)
	} else {
		request.Approval.ReservationDigest = strings.ToLower(request.Approval.ReservationDigest)
	}
	message, err := WithdrawalOwnerSignBytes(request.OwnerMandate.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	signature, err := sdksecp.GenPrivKeyFromSecret([]byte("isolated-test-owner-consent-not-a-production-key")).Sign(message)
	if err != nil {
		t.Fatal(err)
	}
	request.OwnerMandate.Signature = base64.StdEncoding.EncodeToString(signature)
	request.Approval.HoldDigest = WithdrawalHoldDigest(request.Approval.ReservationDigest, *request.OwnerMandate)
	engineTestSignApproval(request.Approval, request.Sender)
	return request
}

func seedHistoricalAuthorityRecord(t *testing.T, e *Engine, req TransferRequest) []byte {
	t.Helper()
	signed := engineTestSigned(req)
	r := record{Request: req, Fingerprint: fingerprint(req), Signed: signed,
		Result:       Result{OperationID: req.OperationID, Status: "CONFIRMED", TxHash: signed.Hash, DurableFenced: true},
		Confirmation: Confirmation{Status: "CONFIRMED", ReceiptID: "wolo-1:" + signed.Hash + ":0", Height: 123, BlockHash: strings.Repeat("B", 64)}}
	var out []byte
	if err := e.db.Update(func(tx *bolt.Tx) error {
		if err := save(tx, r); err != nil {
			return err
		}
		if err := tx.Bucket(effects).Put([]byte("wolo-1:"+signed.Hash), []byte(req.OperationID)); err != nil {
			return err
		}
		out = append([]byte(nil), tx.Bucket(operations).Get([]byte(req.OperationID))...)
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	return out
}

func assertHistoricalAuthorityUnchanged(t *testing.T, e *Engine, id string, original []byte) {
	t.Helper()
	if err := e.db.View(func(tx *bolt.Tx) error {
		if !bytes.Equal(original, tx.Bucket(operations).Get([]byte(id))) {
			return errors.New("historical operation bytes changed")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestEngineHistoricalReservationBackfillPreservesRecoveryAndConsumption(t *testing.T) {
	e, path, p := engineTestOpen(t, &engineTestBackend{})
	old := engineTestWithdrawal(t)
	original := seedHistoricalAuthorityRecord(t, e, old)
	if err := e.Close(); err != nil {
		t.Fatal(err)
	}
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	reopened, err := Open(path, p, backend)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Unix(1800000000, 0) }
	if result, err := reopened.Reconcile(t.Context(), old.OperationID); err != nil || result.Status != "CONFIRMED" {
		t.Fatal("historical recovery refused")
	}
	// First legitimate execution backfills authority metadata, never old ops.
	wager := engineTestWager(t, "1")
	if _, err := reopened.Submit(t.Context(), wager); err != nil {
		t.Fatal(err)
	}
	if _, err := reopened.Reconcile(t.Context(), wager.OperationID); err != nil {
		t.Fatal(err)
	}
	if _, err := reopened.Submit(t.Context(), distinctWithdrawalUsingHold(t, engineTestWithdrawal(t), false)); err == nil || err.Error() != "execution_reservation_already_consumed" {
		t.Fatalf("old hold was reusable after backfill: %v", err)
	}
	assertHistoricalAuthorityUnchanged(t, reopened, old.OperationID, original)
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatal("historical recovery or duplicate reservation transmitted")
	}
}

func TestEngineHistoricalReservationCollisionsOrMissingAuthorityHoldNewExecutionOnly(t *testing.T) {
	for _, kind := range []string{"collision", "missing"} {
		t.Run(kind, func(t *testing.T) {
			e, path, p := engineTestOpen(t, &engineTestBackend{})
			first := engineTestWithdrawal(t)
			if kind == "missing" {
				first.Approval.ReservationDigest = ""
				first.OwnerMandate = nil
			}
			original := seedHistoricalAuthorityRecord(t, e, first)
			if kind == "collision" {
				seedHistoricalAuthorityRecord(t, e, distinctWithdrawalUsingHold(t, engineTestWithdrawal(t), false))
			}
			if err := e.Close(); err != nil {
				t.Fatal(err)
			}
			backend := &engineTestBackend{}
			reopened, err := Open(path, p, backend)
			if err != nil {
				t.Fatalf("historical hold destroyed read-only journal access: %v", err)
			}
			defer reopened.Close()
			reopened.now = func() time.Time { return time.Unix(1800000000, 0) }
			if r, err := reopened.Lookup(first.OperationID); err != nil || r.Status != "CONFIRMED" {
				t.Fatal("historical lookup refused")
			}
			if r, err := reopened.Reconcile(t.Context(), first.OperationID); err != nil || r.Status != "CONFIRMED" {
				t.Fatal("historical read-only reconciliation refused")
			}
			_, err = reopened.Submit(t.Context(), engineTestWager(t, "1"))
			want := "historical_reservation_collision_hold"
			if kind == "missing" {
				want = "historical_reservation_review_required"
			}
			if err == nil || err.Error() != want {
				t.Fatalf("unreviewed historic hold allowed execution: %v", err)
			}
			assertHistoricalAuthorityUnchanged(t, reopened, first.OperationID, original)
			if backend.signs.Load() != 0 || backend.broadcasts.Load() != 0 {
				t.Fatal("historical hold reached signing")
			}
		})
	}
}

func TestEngineReservationCannotCrossWagerAndWithdrawalKinds(t *testing.T) {
	for _, order := range []string{"wager-first", "withdrawal-first"} {
		t.Run(order, func(t *testing.T) {
			backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
			e, _, p := engineTestOpen(t, backend)
			wager := engineTestWager(t, "1")
			withdrawal := engineTestWithdrawal(t)
			wager.Reservation.ReservationDigest = strings.ToLower(withdrawal.Approval.ReservationDigest)
			wager.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(*wager.Reservation)))
			if p.verifyWager(wager, e.now()) != nil {
				t.Fatal("invalid approved fixture")
			}
			first, second := wager, withdrawal
			if order == "withdrawal-first" {
				first, second = withdrawal, wager
			}
			if _, err := e.Submit(t.Context(), first); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Reconcile(t.Context(), first.OperationID); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Submit(t.Context(), second); err == nil || err.Error() != "execution_reservation_already_consumed" {
				t.Fatalf("one hold crossed execution kinds: %v", err)
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
				t.Fatal("same reservation spent twice")
			}
		})
	}
}

func TestEngineOwnsAcceptedApprovalPointersBeforeBackendExecution(t *testing.T) {
	backend := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, backend)
	req := engineTestWager(t, "1")
	digest := req.Reservation.ReservationDigest
	backend.beforeSign = func(TransferRequest) { req.Reservation.ReservationDigest = strings.Repeat("f", 64) }
	r, err := e.Submit(t.Context(), req)
	if err != nil || r.Status != "ACCEPTED" {
		t.Fatalf("caller mutation changed accepted authority: %+v %v", r, err)
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		stored, err := load(tx, req.OperationID)
		if err != nil {
			return err
		}
		if stored.Request.Reservation.ReservationDigest != digest {
			return errors.New("accepted reservation pointer was mutable")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestEngineMissingIndexedReservationBucketCannotResetConsumedHolds(t *testing.T) {
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	e, _, _ := engineTestOpen(t, backend)
	first := engineTestWithdrawal(t)
	if _, err := e.Submit(t.Context(), first); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Reconcile(t.Context(), first.OperationID); err != nil {
		t.Fatal(err)
	}
	if err := e.db.Update(func(tx *bolt.Tx) error { return tx.DeleteBucket(reservationAuthorities) }); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Submit(t.Context(), distinctWithdrawalUsingHold(t, engineTestWithdrawal(t), false)); err == nil || err.Error() != "reservation_authority_index_corrupt" {
		t.Fatalf("missing index silently reset previously consumed reservations: %v", err)
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatal("corrupt reservation index allowed another withdrawal")
	}
}

func TestEngineDeletedReservationEntryCannotRestoreConsumedAuthority(t *testing.T) {
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	e, _, _ := engineTestOpen(t, backend)
	first := engineTestWithdrawal(t)
	if _, err := e.Submit(t.Context(), first); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Reconcile(t.Context(), first.OperationID); err != nil {
		t.Fatal(err)
	}
	var original []byte
	if err := e.db.Update(func(tx *bolt.Tx) error {
		original = append([]byte(nil), tx.Bucket(operations).Get([]byte(first.OperationID))...)
		return tx.Bucket(reservationAuthorities).Delete([]byte(strings.ToLower(first.Approval.ReservationDigest)))
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Submit(t.Context(), distinctWithdrawalUsingHold(t, engineTestWithdrawal(t), false)); err == nil || err.Error() != "reservation_authority_index_corrupt" {
		t.Fatalf("deleted index entry restored consumed withdrawal authority: %v", err)
	}
	assertHistoricalAuthorityUnchanged(t, e, first.OperationID, original)
	if result, err := e.Reconcile(t.Context(), first.OperationID); err != nil || result.Status != "CONFIRMED" {
		t.Fatal("corrupt index prevented historical read-only recovery")
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatal("deleted reservation fence allowed another withdrawal")
	}
}

func TestEngineOneReservationCannotFundDistinctApprovedWithdrawals(t *testing.T) {
	for _, upper := range []bool{false, true} {
		t.Run(map[bool]string{false: "lowercase-alias", true: "same-digest"}[upper], func(t *testing.T) {
			backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
			e, _, _ := engineTestOpen(t, backend)
			first := engineTestWithdrawal(t)
			if _, err := e.Submit(t.Context(), first); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Reconcile(t.Context(), first.OperationID); err != nil {
				t.Fatal(err)
			}
			second := distinctWithdrawalUsingHold(t, engineTestWithdrawal(t), upper)
			if _, err := e.Submit(t.Context(), second); err == nil {
				t.Fatal("one durable owner reservation authorized a second separately approved withdrawal")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
				t.Fatal("reused reservation reached financial execution")
			}
		})
	}
}
