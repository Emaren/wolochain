package satchelservice

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func testReturnApproval(t *testing.T, operationID, claimID string) ReturnApproval {
	ticket := strings.TrimPrefix(operationID, "satchel:ticket:")
	request := engineTestWager(t, ticket)
	// Preserve the public historical financial fixture; this is not a request
	// submitted through the current execution authority.
	request.OwnerID = ""
	request.Reservation = nil
	plan := ReturnAllocation{Version: 2, AllocationID: "allocation:" + ticket, Revision: 1, OperationID: operationID, OwnerID: "owner-1", TicketID: ticket,
		FundingTxHash: engineTestSigned(request).Hash, ReturnCapUWolo: "50000000000", FundsBudgetID: "bank-review-1", FundsAvailableUWolo: "50000000000", BankEvidenceDigest: strings.Repeat("E", 64), BankHeight: 200, BankBlockHash: strings.Repeat("B", 64),
		Legs: []ReturnLeg{{LegID: "winner", MarketID: "501", StakeUWolo: "1000000", Entitlements: []ReturnEntitlement{{EntitlementID: "entitlement:" + claimID, ClaimID: claimID, ClaimKind: "bet_refund", PrincipalUWolo: "1000000", AmountUWolo: "1000000"}}}}, IssuedAt: 1799999990, ExpiresAt: 1800000100}
	testSignAllocation(&plan, engineTestPolicy(t))
	a := ReturnApproval{Version: 2, TicketID: ticket, MarketID: "501", LegID: "winner", EntitlementID: "entitlement:" + claimID, Allocation: &plan, OperationID: operationID, ClaimID: claimID, OwnerID: "owner-1", ClaimKind: "bet_refund", AmountUWolo: "1000000", AllocationDigest: AllocationDigest(plan, engineTestPolicy(t)), IssuedAt: 1799999990, ExpiresAt: 1800000100}
	testSignReturnApproval(&a, engineTestPolicy(t))
	return a
}
func testSignAllocation(a *ReturnAllocation, p Policy) {
	a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWithdrawalApprovalKey(), AllocationMessage(*a, p)))
}
func testSignReturnApproval(a *ReturnApproval, p Policy) {
	a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWithdrawalApprovalKey(), ReturnApprovalMessage(*a, p)))
}
func testReturnEngine(t *testing.T) (*Engine, string, Policy, *engineTestBackend, TransferRequest) {
	t.Helper()
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	engine, path, policy := engineTestOpen(t, backend)
	request := engineTestWager(t, "1")
	// Explicit historical-state injection, never admission of a new ownerless
	// wager. Production paths cannot construct a confirmed record this way.
	request.OwnerID = ""
	request.Reservation = nil
	signed := engineTestSigned(request)
	r := record{Request: request, Fingerprint: fingerprint(request), Signed: signed,
		Result:       Result{OperationID: request.OperationID, Status: "CONFIRMED", TxHash: signed.Hash, DurableFenced: true},
		Confirmation: Confirmation{Status: "CONFIRMED", ReceiptID: "wolo-1:" + signed.Hash + ":0", Height: 123, BlockHash: strings.Repeat("B", 64)}}
	if err := engine.db.Update(func(tx *bolt.Tx) error {
		if err := save(tx, r); err != nil {
			return err
		}
		return tx.Bucket(effects).Put([]byte("wolo-1:"+signed.Hash), []byte(request.OperationID))
	}); err != nil {
		t.Fatal(err)
	}
	return engine, path, policy, backend, request
}
func testStoredReturn(t *testing.T, e *Engine, claimID string) returnRecord {
	t.Helper()
	var out returnRecord
	if err := e.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b == nil {
			return errors.New("return_bucket_missing")
		}
		data := b.Get([]byte(claimID))
		if data == nil {
			return errors.New("return_record_missing")
		}
		return json.Unmarshal(data, &out)
	}); err != nil {
		t.Fatal(err)
	}
	return out
}

func testOwnedReturnApproval(t *testing.T, operationID, claimID string) ReturnApproval {
	t.Helper()
	a := testReturnApproval(t, operationID, claimID)
	r := engineTestWager(t, strings.TrimPrefix(operationID, "satchel:ticket:"))
	r.OwnerID = a.OwnerID
	a.Allocation.FundingTxHash = engineTestSigned(r).Hash
	testSignAllocation(a.Allocation, engineTestPolicy(t))
	a.AllocationDigest = AllocationDigest(*a.Allocation, engineTestPolicy(t))
	testSignReturnApproval(&a, engineTestPolicy(t))
	return a
}
func testOwnedReturnEngine(t *testing.T) (*Engine, string, Policy, *engineTestBackend, TransferRequest) {
	t.Helper()
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	engine, path, policy := engineTestOpen(t, backend)
	request := engineTestWager(t, "1")
	request.OwnerID = "owner-1"
	if _, err := engine.Submit(t.Context(), request); err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Reconcile(t.Context(), request.OperationID); err != nil {
		t.Fatal(err)
	}
	return engine, path, policy, backend, request
}

func TestReturnPreparationUsesEscrowRunAndFullUnmatchedStake(t *testing.T) {
	engine, _, policy, backend, request := testOwnedReturnEngine(t)
	approval := testOwnedReturnApproval(t, request.OperationID, "101")
	run, err := engine.PrepareReturnRun(t.Context(), approval)
	if err != nil {
		t.Fatal(err)
	}
	if run.SettlementRunID != "satchel:claim-return:101" || run.SourceApp != "aoe2hdbets" || run.SourceEventID != request.OperationID || run.SignerRole != "escrow" || len(run.Payouts) != 1 {
		t.Fatalf("not canonical existing escrow run: %+v", run)
	}
	payout := run.Payouts[0]
	if payout.RequestID != run.SettlementRunID || payout.ToAddress != policy.Vault || payout.AmountUWolo != request.AmountUWolo || payout.Memo != "aoe2war/satchel/claim-return/v1/101" {
		t.Fatalf("unmatched refund deducted a fee or changed destination: %+v", payout)
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatal("return preparation transmitted tokens")
	}
	stored := testStoredReturn(t, engine, approval.ClaimID)
	if stored.Approval.OwnerID != approval.OwnerID || stored.Fingerprint != returnFingerprint(approval) || stored.Receipt != nil {
		t.Fatalf("owner allocation not durably fenced independently of payment: %+v", stored)
	}
}

func TestReturnApprovalRejectsInvalidOwnershipFinancialAndSignatureEvidence(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*ReturnApproval)
		resign bool
	}{
		{"98 percent refund forbidden", func(a *ReturnApproval) { a.AmountUWolo = "980000" }, true},
		{"partial refund forbidden", func(a *ReturnApproval) { a.AmountUWolo = "500000" }, true},
		{"excessive refund forbidden", func(a *ReturnApproval) { a.AmountUWolo = "1000001" }, true},
		{"zero refund", func(a *ReturnApproval) { a.AmountUWolo = "0" }, true},
		{"claim identity", func(a *ReturnApproval) { a.ClaimID = "0" }, true},
		{"unknown claim kind", func(a *ReturnApproval) { a.ClaimKind = "founder" }, true},
		{"missing owner", func(a *ReturnApproval) { a.OwnerID = "" }, true},
		{"missing allocation evidence", func(a *ReturnApproval) { a.AllocationDigest = strings.Repeat("0", 64) }, true},
		{"wrong signed amount", func(a *ReturnApproval) { a.ClaimKind = "bet_payout"; a.AmountUWolo = "2000000" }, false},
		{"retargeted owner", func(a *ReturnApproval) { a.OwnerID = "owner-2" }, false},
		{"expired approval", func(a *ReturnApproval) { a.ExpiresAt = 1800000000 }, true},
		{"future approval", func(a *ReturnApproval) { a.IssuedAt = 1800000001 }, true},
		{"overlong approval", func(a *ReturnApproval) { a.ExpiresAt = a.IssuedAt + 301 }, true},
		{"overflowed approval", func(a *ReturnApproval) { a.IssuedAt = -1 << 63; a.ExpiresAt = (1 << 63) - 1 }, true},
		{"wrong signature", func(a *ReturnApproval) { a.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64)) }, false},
		{"noncanonical signature", func(a *ReturnApproval) { a.Signature += "\n" }, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			engine, _, policy, backend, request := testOwnedReturnEngine(t)
			approval := testOwnedReturnApproval(t, request.OperationID, "101")
			test.mutate(&approval)
			if test.resign {
				testSignReturnApproval(&approval, policy)
			}
			if _, err := engine.PrepareReturnRun(t.Context(), approval); err == nil {
				t.Fatal("invalid return allocation reached escrow run preparation")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
				t.Fatal("invalid return allocation transmitted")
			}
		})
	}
}

func TestReturnApprovalCannotCrossWithdrawalSignatureDomain(t *testing.T) {
	engine, _, _, _, request := testOwnedReturnEngine(t)
	a := testOwnedReturnApproval(t, request.OperationID, "101")
	w := engineTestWithdrawal(t)
	a.Signature = w.Approval.Signature
	if _, err := engine.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("withdrawal approval authorized an escrow claim return")
	}
}

func TestReturnRequiresConfirmedOriginalWagerAndOwner(t *testing.T) {
	for _, test := range []struct{ name, status, owner string }{
		{"accepted broadcast not confirmed", "ACCEPTED", "owner-1"},
		{"untrusted observation not confirmed", "OBSERVED_NONCREDITING", "owner-1"},
		{"confirmed belongs to different owner", "CONFIRMED", "another-owner"},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{confirmationStatus: test.status}
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			request.OwnerID = test.owner
			request.Reservation = testWagerReservation(t, request, engineTestPolicy(t), time.Unix(1800000000, 0))
			if _, err := engine.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			if test.status != "ACCEPTED" {
				if _, err := engine.Reconcile(t.Context(), request.OperationID); err != nil {
					t.Fatal(err)
				}
			}
			a := testOwnedReturnApproval(t, request.OperationID, "101")
			if _, err := engine.PrepareReturnRun(t.Context(), a); err == nil {
				t.Fatal("unconfirmed or foreign-owner wager generated claim return")
			}
		})
	}
}

func TestReturnClaimAndOperationAllocationCannotBeReassigned(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*ReturnApproval)
	}{
		{"different owner same claim", func(a *ReturnApproval) { a.OwnerID = "owner-2" }},
		{"undeclared claim same operation", func(a *ReturnApproval) { a.ClaimID = "102" }},
		{"different amount same claim", func(a *ReturnApproval) { a.ClaimKind = "bet_payout"; a.AmountUWolo = "2000000" }},
		{"different kind same claim", func(a *ReturnApproval) { a.ClaimKind = "bet_payout" }},
		{"different allocation same claim", func(a *ReturnApproval) { a.AllocationDigest = strings.Repeat("E", 64) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			engine, _, policy, _, request := testOwnedReturnEngine(t)
			a := testOwnedReturnApproval(t, request.OperationID, "101")
			if _, err := engine.PrepareReturnRun(t.Context(), a); err != nil {
				t.Fatal(err)
			}
			test.mutate(&a)
			testSignReturnApproval(&a, policy)
			if _, err := engine.PrepareReturnRun(t.Context(), a); err == nil {
				t.Fatal("durable owner/operation allocation changed")
			}
		})
	}
}

func TestReturnCancellationCannotCreateNewAllocation(t *testing.T) {
	engine, _, _, _, request := testOwnedReturnEngine(t)
	a := testOwnedReturnApproval(t, request.OperationID, "101")
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := engine.PrepareReturnRun(ctx, a); err == nil {
		t.Fatal("canceled request created return allocation")
	}
	if err := engine.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b != nil && b.Get([]byte(a.ClaimID)) != nil {
			return errors.New("canceled_allocation_persisted")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestReturnMissingTrustedProofNeverInfersPayment(t *testing.T) {
	engine, _, _, backend, request := testOwnedReturnEngine(t)
	a := testOwnedReturnApproval(t, request.OperationID, "101")
	if _, err := engine.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatal(err)
	}
	if _, err := engine.ReconcileReturn(t.Context(), a, testHTTPHash, nil); err == nil {
		t.Fatal("missing authenticated chain reader proved receipt")
	}
	if testStoredReturn(t, engine, a.ClaimID).Receipt != nil || backend.broadcasts.Load() != 1 {
		t.Fatal("missing proof created payment or retransmission")
	}
}

func testFaultInjectedReturnReceipt(a ReturnApproval, hash string, index int) ReturnReceipt {
	return ReturnReceipt{Version: 2, TicketID: a.TicketID, MarketID: a.MarketID, LegID: a.LegID, EntitlementID: a.EntitlementID, AllocationID: a.Allocation.AllocationID, OperationID: a.OperationID, ClaimID: a.ClaimID, OwnerID: a.OwnerID, ClaimKind: a.ClaimKind, AmountUWolo: a.AmountUWolo, TxHash: hash, ReceiptID: "wolo-1:" + hash + ":" + string(rune('0'+index)), Height: 123, BlockHash: strings.Repeat("B", 64)}
}

func TestReturnDuplicatePhysicalEffectsCannotBecomeOwnerCredits(t *testing.T) {
	for _, index := range []int{0, 1} {
		t.Run("alternate_observed_ordinal="+string(rune('0'+index)), func(t *testing.T) {
			engine, _, policy, _, request := testOwnedReturnEngine(t)
			first := testOwnedReturnApproval(t, request.OperationID, "101")
			if _, err := engine.PrepareReturnRun(t.Context(), first); err != nil {
				t.Fatal(err)
			}
			original := testStoredReturn(t, engine, first.ClaimID)
			// Explicit DB fault injection tests the independent physical-hash guard;
			// no trusted proof constructor is mocked or exported to application code.
			if err := engine.recordReturn(original, testFaultInjectedReturnReceipt(first, testHTTPHash, 0)); err != nil {
				t.Fatal(err)
			}
			secondRequest := engineTestWager(t, "2")
			secondRequest.OwnerID = "owner-2"
			secondRequest.Reservation = testWagerReservation(t, secondRequest, policy, time.Unix(1800000000, 0))
			if _, err := engine.Submit(t.Context(), secondRequest); err != nil {
				t.Fatal(err)
			}
			if _, err := engine.Reconcile(t.Context(), secondRequest.OperationID); err != nil {
				t.Fatal(err)
			}
			second := testOwnedReturnApproval(t, secondRequest.OperationID, "102")
			second.OwnerID = "owner-2"
			second.Allocation.OwnerID = second.OwnerID
			second.Allocation.FundingTxHash = engineTestSigned(secondRequest).Hash
			testSignAllocation(second.Allocation, policy)
			second.AllocationDigest = AllocationDigest(*second.Allocation, policy)
			testSignReturnApproval(&second, policy)
			if _, err := engine.PrepareReturnRun(t.Context(), second); err != nil {
				t.Fatal(err)
			}
			if err := engine.recordReturn(testStoredReturn(t, engine, second.ClaimID), testFaultInjectedReturnReceipt(second, testHTTPHash, index)); err == nil {
				t.Fatal("same return transaction allocated to another owner")
			}
			if testStoredReturn(t, engine, second.ClaimID).Receipt != nil {
				t.Fatal("duplicate transaction receipt became owner credit")
			}
		})
	}
}

func TestReturnReceiptReplayRemainsOwnerBoundAcrossRestart(t *testing.T) {
	engine, path, policy, _, request := testOwnedReturnEngine(t)
	a := testOwnedReturnApproval(t, request.OperationID, "101")
	if _, err := engine.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatal(err)
	}
	if err := engine.recordReturn(testStoredReturn(t, engine, a.ClaimID), testFaultInjectedReturnReceipt(a, testHTTPHash, 0)); err != nil {
		t.Fatal(err)
	}
	if err := engine.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(path, policy, &engineTestBackend{})
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Unix(1800000000, 0) }
	if _, err := reopened.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatalf("same already-proven receipt could not replay after restart: %v", err)
	}
	a.OwnerID = "another-owner"
	testSignReturnApproval(&a, policy)
	if _, err := reopened.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("restart reassigned a paid receipt to another owner")
	}
}

func TestReturnPoisonedReceiptCannotBeReplayed(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*ReturnReceipt)
	}{
		{"owner", func(r *ReturnReceipt) { r.OwnerID = "another-owner" }},
		{"amount", func(r *ReturnReceipt) { r.AmountUWolo = "2000000" }},
		{"height", func(r *ReturnReceipt) { r.Height = 0 }},
		{"hash identity", func(r *ReturnReceipt) { r.ReceiptID = "wolo-1:" + strings.Repeat("C", 64) + ":0" }},
		{"invented ledger credit", func(r *ReturnReceipt) { r.CreditAuthorized = true }},
	} {
		t.Run(test.name, func(t *testing.T) {
			engine, _, _, _, request := testOwnedReturnEngine(t)
			a := testOwnedReturnApproval(t, request.OperationID, "101")
			if _, err := engine.PrepareReturnRun(t.Context(), a); err != nil {
				t.Fatal(err)
			}
			record := testStoredReturn(t, engine, a.ClaimID)
			receipt := testFaultInjectedReturnReceipt(a, testHTTPHash, 0)
			test.mutate(&receipt)
			record.Receipt = &receipt
			if err := engine.db.Update(func(tx *bolt.Tx) error {
				raw, _ := json.Marshal(record)
				return tx.Bucket(returns).Put([]byte(a.ClaimID), raw)
			}); err != nil {
				t.Fatal(err)
			}
			if _, err := engine.PrepareReturnRun(t.Context(), a); err == nil {
				t.Fatal("poisoned receipt became an owner payment")
			}
		})
	}
}
