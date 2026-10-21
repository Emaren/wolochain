package satchelservice

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func TestReturnOwnerlessConfirmedFundingCannotBeAssigned(t *testing.T) {
	e, _, p, backend, request := testReturnEngine(t)
	if request.OwnerID != "" {
		t.Fatal("regression fixture must retain the historical ownerless request")
	}
	var before []byte
	if err := e.db.View(func(tx *bolt.Tx) error {
		before = append([]byte(nil), tx.Bucket(operations).Get([]byte(request.OperationID))...)
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	a := testReturnApproval(t, request.OperationID, "101")
	// Even an authentic new reviewer signature cannot retroactively establish
	// the owner of the already confirmed, ownerless custody debit.
	testSignAllocation(a.Allocation, p)
	testSignReturnApproval(&a, p)
	if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("a signed allocation adopted an ownerless confirmed funding operation")
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		if !bytes.Equal(before, tx.Bucket(operations).Get([]byte(request.OperationID))) {
			t.Fatal("historical funding request was rewritten")
		}
		if b := tx.Bucket(returns); b != nil && b.Get([]byte(a.ClaimID)) != nil {
			t.Fatal("refused ownerless funding created a new claim obligation")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if backend.signs.Load() != 0 || backend.broadcasts.Load() != 0 {
		t.Fatal("ownerless return review transmitted a payment")
	}
}

func TestReturnOwnerUIDMatchesExistingProofContract(t *testing.T) {
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	e, _, p := engineTestOpen(t, backend)
	r := engineTestWager(t, "1")
	r.OwnerID = "owner.with.dot"
	r.Reservation = testWagerReservation(t, r, p, time.Unix(1800000000, 0))
	if _, err := e.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
		t.Fatal(err)
	}
	a := testReturnApproval(t, r.OperationID, "101")
	a.OwnerID = r.OwnerID
	a.Allocation.OwnerID = r.OwnerID
	a.Allocation.FundingTxHash = engineTestSigned(r).Hash
	testSignAllocation(a.Allocation, p)
	a.AllocationDigest = AllocationDigest(*a.Allocation, p)
	testSignReturnApproval(&a, p)
	if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatalf("existing owner UID contract failed on its return path: %v", err)
	}
	c := FinancialProofContext{Protocol: 1, Kind: "claim_return", OwnerID: a.OwnerID, OperationID: a.OperationID,
		Sender: p.BettingEscrow, Recipient: p.Vault, AmountUWolo: a.AmountUWolo,
		Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID, TxHash: testHTTPHash,
		FundedAmountUWolo: r.AmountUWolo, ReturnApproval: &a}
	if err := verifyReturnContext(c, p); err != nil {
		t.Fatalf("existing owner UID contract failed on offline return verification: %v", err)
	}
}

func TestReturnAllZeroPhysicalIdentityCannotBecomeReceipt(t *testing.T) {
	e, _, _, _, request := testOwnedReturnEngine(t)
	a := testOwnedReturnApproval(t, request.OperationID, "101")
	if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatal(err)
	}
	r := testStoredReturn(t, e, a.ClaimID)
	p := testFaultInjectedReturnReceipt(a, strings.Repeat("0", 64), 0)
	if err := e.recordReturn(r, p); err == nil {
		t.Fatal("all-zero physical transaction identity was stored as payment evidence")
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		var stored returnRecord
		if err := json.Unmarshal(tx.Bucket(returns).Get([]byte(a.ClaimID)), &stored); err != nil {
			return err
		}
		if stored.Receipt != nil {
			t.Fatal("invalid receipt changed durable payment state")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
