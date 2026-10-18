package satchelservice

import (
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func multiLegFixture(t *testing.T) (*Engine, string, Policy, *engineTestBackend, ReturnAllocation) {
	t.Helper()
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	engine, path, policy := engineTestOpen(t, backend)
	r := engineTestWager(t, "1")
	r.AmountUWolo = "2000000"
	r.OwnerID = "owner-1"
	r.Reservation = testWagerReservation(t, r, policy, time.Unix(1800000000, 0))
	if _, err := engine.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Reconcile(t.Context(), r.OperationID); err != nil {
		t.Fatal(err)
	}
	plan := ReturnAllocation{Version: 2, AllocationID: "allocation:ticket:1", Revision: 1, OperationID: r.OperationID, OwnerID: r.OwnerID, TicketID: "1", FundingTxHash: engineTestSigned(r).Hash,
		ReturnCapUWolo: "3000000", FundsBudgetID: "bank-review-1", FundsAvailableUWolo: "50000000000", BankEvidenceDigest: strings.Repeat("E", 64), BankHeight: 200, BankBlockHash: strings.Repeat("B", 64), IssuedAt: 1799999990, ExpiresAt: 1800000100,
		Legs: []ReturnLeg{
			{LegID: "desync", MarketID: "502", StakeUWolo: "1000000", Entitlements: []ReturnEntitlement{{EntitlementID: "desync-refund", ClaimID: "102", ClaimKind: "bet_refund", PrincipalUWolo: "1000000", AmountUWolo: "1000000"}}},
			{LegID: "winner", MarketID: "501", StakeUWolo: "1000000", Entitlements: []ReturnEntitlement{{EntitlementID: "winner-payout", ClaimID: "101", ClaimKind: "bet_payout", PrincipalUWolo: "1000000", AmountUWolo: "2000000"}}},
		}}
	testSignAllocation(&plan, policy)
	return engine, path, policy, backend, plan
}
func multiLegApproval(t *testing.T, plan ReturnAllocation, claim string, p Policy) ReturnApproval {
	t.Helper()
	raw, _ := json.Marshal(plan)
	var copy ReturnAllocation
	if err := json.Unmarshal(raw, &copy); err != nil {
		t.Fatal(err)
	}
	for _, leg := range copy.Legs {
		for _, entry := range leg.Entitlements {
			if entry.ClaimID == claim {
				a := ReturnApproval{Version: 2, TicketID: copy.TicketID, MarketID: leg.MarketID, LegID: leg.LegID, EntitlementID: entry.EntitlementID, Allocation: &copy, OperationID: copy.OperationID, ClaimID: entry.ClaimID, OwnerID: copy.OwnerID, ClaimKind: entry.ClaimKind, AmountUWolo: entry.AmountUWolo, AllocationDigest: AllocationDigest(copy, p), IssuedAt: copy.IssuedAt, ExpiresAt: copy.ExpiresAt}
				testSignReturnApproval(&a, p)
				return a
			}
		}
	}
	t.Fatalf("missing test entitlement %s", claim)
	return ReturnApproval{}
}
func multiLegReserved(t *testing.T, e *Engine, id string) (uint64, uint64) {
	t.Helper()
	var plan allocationState
	var funds returnFundsState
	if err := e.db.View(func(tx *bolt.Tx) error {
		if err := json.Unmarshal(tx.Bucket(allocationBucket).Get([]byte(id)), &plan); err != nil {
			return err
		}
		return json.Unmarshal(tx.Bucket(meta).Get(fundsKey), &funds)
	}); err != nil {
		t.Fatal(err)
	}
	return plan.Reserved, funds.Reserved
}

func TestMultiLegWinnerAndDesyncClaimsSettleInEitherOrder(t *testing.T) {
	for _, order := range [][]string{{"101", "102"}, {"102", "101"}} {
		t.Run(strings.Join(order, "then"), func(t *testing.T) {
			e, _, p, b, plan := multiLegFixture(t)
			for _, claim := range order {
				a := multiLegApproval(t, plan, claim, p)
				run, err := e.PrepareReturnRun(t.Context(), a)
				if err != nil {
					t.Fatalf("independent leg claim %s refused: %v", claim, err)
				}
				if len(run.Payouts) != 1 || run.Payouts[0].AmountUWolo != a.AmountUWolo || run.Payouts[0].ToAddress != p.Vault || run.SignerRole != "escrow" {
					t.Fatalf("leg payout/refund not exact: %+v", run)
				}
			}
			reserved, global := multiLegReserved(t, e, plan.OperationID)
			if reserved != 3000000 || global != 3000000 {
				t.Fatalf("aggregate obligation not reserved exactly: %d/%d", reserved, global)
			}
			if b.signs.Load() != 1 || b.broadcasts.Load() != 1 {
				t.Fatal("return preparation sent tokens")
			}
		})
	}
}

func TestMultiLegPartialUnmatchedPrincipalRefundsAllWithoutFee(t *testing.T) {
	e, _, p, _, plan := multiLegFixture(t)
	// Only 0.4 WOLO of the desync leg is unmatched. Its full principal returns;
	// the rest can be resolved later in an append-only allocation revision.
	entry := &plan.Legs[0].Entitlements[0]
	entry.PrincipalUWolo = "400000"
	entry.AmountUWolo = "400000"
	testSignAllocation(&plan, p)
	a := multiLegApproval(t, plan, "102", p)
	run, err := e.PrepareReturnRun(t.Context(), a)
	if err != nil || len(run.Payouts) != 1 || run.Payouts[0].AmountUWolo != "400000" {
		t.Fatalf("partial leg lost full unmatched principal: %+v %v", run, err)
	}
	reserved, _ := multiLegReserved(t, e, plan.OperationID)
	if reserved != 400000 {
		t.Fatal("partial principal reservation changed")
	}
}

func TestMultiLegUnmatchedPrincipalCompletesAcrossRevisionsAndRestart(t *testing.T) {
	e, path, p, backend, plan := multiLegFixture(t)
	plan.ReturnCapUWolo = "2000000"
	plan.Legs[0].Entitlements[0].PrincipalUWolo = "400000"
	plan.Legs[0].Entitlements[0].AmountUWolo = "400000"
	plan.Legs[1].Entitlements = nil
	testSignAllocation(&plan, p)
	first := multiLegApproval(t, plan, "102", p)
	if _, err := e.PrepareReturnRun(t.Context(), first); err != nil {
		t.Fatal(err)
	}
	// These explicit test-only receipts exercise durable consumption, not chain
	// authentication; production reconciliation still requires TrustedReader.
	if err := e.recordReturn(testStoredReturn(t, e, first.ClaimID), testFaultInjectedReturnReceipt(first, strings.Repeat("2", 64), 0)); err != nil {
		t.Fatal(err)
	}
	if err := e.Close(); err != nil {
		t.Fatal(err)
	}
	afterRestart := &engineTestBackend{}
	reopened, err := Open(path, p, afterRestart)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Unix(1800000000, 0) }
	plan.Revision++
	plan.Legs[0].Entitlements = append(plan.Legs[0].Entitlements, ReturnEntitlement{EntitlementID: "desync-refund-b", ClaimID: "103", ClaimKind: "bet_refund", PrincipalUWolo: "600000", AmountUWolo: "600000"})
	plan.Legs[1].Entitlements = []ReturnEntitlement{{EntitlementID: "winner-refund", ClaimID: "101", ClaimKind: "bet_refund", PrincipalUWolo: "1000000", AmountUWolo: "1000000"}}
	testSignAllocation(&plan, p)
	for _, claim := range []string{"101", "103"} {
		a := multiLegApproval(t, plan, claim, p)
		run, err := reopened.PrepareReturnRun(t.Context(), a)
		if err != nil || len(run.Payouts) != 1 || run.Payouts[0].AmountUWolo != a.AmountUWolo {
			t.Fatalf("complete unmatched principal changed: %+v %v", run, err)
		}
		hash := strings.Repeat("1", 64)
		if claim == "103" {
			hash = strings.Repeat("3", 64)
		}
		if err := reopened.recordReturn(testStoredReturn(t, reopened, claim), testFaultInjectedReturnReceipt(a, hash, 0)); err != nil {
			t.Fatal(err)
		}
	}
	// The old partial claim can be delivered again after the newer complete
	// plan. It must retain its original effect and consume no further capital.
	for _, a := range []ReturnApproval{first, multiLegApproval(t, plan, "101", p), multiLegApproval(t, plan, "103", p)} {
		if _, err := reopened.PrepareReturnRun(t.Context(), a); err != nil {
			t.Fatal(err)
		}
	}
	reserved, global := multiLegReserved(t, reopened, plan.OperationID)
	if reserved != 2000000 || global != 2000000 {
		t.Fatalf("all unmatched principal must return once without deduction: %d/%d", reserved, global)
	}
	if err := reopened.db.View(func(tx *bolt.Tx) error {
		if tx.Bucket(returns).Stats().KeyN != 3 {
			return errors.New("duplicate_unmatched_refund_receipt")
		}
		var refunded uint64
		for _, claim := range []string{"101", "102", "103"} {
			var r returnRecord
			if err := json.Unmarshal(tx.Bucket(returns).Get([]byte(claim)), &r); err != nil {
				return err
			}
			if r.Receipt == nil || !validReturnReceipt(r, *r.Receipt) || r.Receipt.OwnerID != plan.OwnerID {
				return errors.New("missing_owned_unmatched_refund")
			}
			n, _ := positive(r.Receipt.AmountUWolo, 2000000)
			refunded += n
		}
		if refunded != 2000000 {
			return errors.New("unmatched_principal_not_conserved")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 || afterRestart.signs.Load() != 0 || afterRestart.broadcasts.Load() != 0 {
		t.Fatal("refund preparation or reconciliation retried a financial send")
	}
}

func TestMultiLegConcurrentDuplicateDeliveryChargesEntitlementOnce(t *testing.T) {
	e, _, p, _, plan := multiLegFixture(t)
	a := multiLegApproval(t, plan, "101", p)
	var wg sync.WaitGroup
	failures := make(chan error, 32)
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			run, err := e.PrepareReturnRun(t.Context(), a)
			if err != nil {
				failures <- err
			} else if run.SettlementRunID != "satchel:claim-return:101" {
				failures <- errors.New("replay_identity_changed")
			}
		}()
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	reserved, global := multiLegReserved(t, e, plan.OperationID)
	if reserved != 2000000 || global != 2000000 {
		t.Fatalf("duplicate delivery charged twice: %d/%d", reserved, global)
	}
}

func TestMultiLegCrossIdentityAndForgedClaimsFailClosed(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*ReturnApproval)
		resign bool
	}{
		{"owner impersonation", func(a *ReturnApproval) { a.OwnerID = "owner-2" }, true},
		{"ticket impersonation", func(a *ReturnApproval) { a.TicketID = "2" }, true},
		{"market impersonation", func(a *ReturnApproval) { a.MarketID = "502" }, true},
		{"leg impersonation", func(a *ReturnApproval) { a.LegID = "desync" }, true},
		{"entitlement impersonation", func(a *ReturnApproval) { a.EntitlementID = "desync-refund" }, true},
		{"claim impersonation", func(a *ReturnApproval) { a.ClaimID = "103" }, true},
		{"changed payout amount", func(a *ReturnApproval) { a.AmountUWolo = "2000001" }, true},
		{"expired claim", func(a *ReturnApproval) { a.ExpiresAt = 1800000000 }, true},
		{"forged plan", func(a *ReturnApproval) { a.Allocation.FundsAvailableUWolo = "99999999999" }, true},
		{"forged claim signature", func(a *ReturnApproval) { a.Signature = "invalid" }, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			e, _, p, _, plan := multiLegFixture(t)
			a := multiLegApproval(t, plan, "101", p)
			test.mutate(&a)
			if test.resign {
				testSignReturnApproval(&a, p)
			}
			if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
				t.Fatal("mismatched leg/owner entitlement generated transfer request")
			}
		})
	}
}

func TestMultiLegPlanCannotAllocateMoreThanStakeOrReviewedBudget(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*ReturnAllocation)
	}{
		{"return cap below entitlements", func(p *ReturnAllocation) { p.ReturnCapUWolo = "2999999" }},
		{"available funds below cap", func(p *ReturnAllocation) { p.FundsAvailableUWolo = "2999999" }},
		{"leg principal over stake", func(p *ReturnAllocation) {
			p.Legs[0].Entitlements[0].PrincipalUWolo = "1000001"
			p.Legs[0].Entitlements[0].AmountUWolo = "1000001"
		}},
		{"98 percent unmatched refund", func(p *ReturnAllocation) { p.Legs[0].Entitlements[0].AmountUWolo = "980000" }},
		{"leg partition exceeds funding", func(p *ReturnAllocation) { p.Legs[0].StakeUWolo = "1000001" }},
		{"duplicate entitlement", func(p *ReturnAllocation) {
			p.Legs[1].Entitlements[0].EntitlementID = p.Legs[0].Entitlements[0].EntitlementID
		}},
		{"duplicate claim", func(p *ReturnAllocation) { p.Legs[1].Entitlements[0].ClaimID = "102" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			e, _, p, _, plan := multiLegFixture(t)
			test.mutate(&plan)
			testSignAllocation(&plan, p)
			a := multiLegApproval(t, plan, "102", p)
			if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
				t.Fatal("overallocated or fee-reduced plan accepted")
			}
		})
	}
}

func TestMultiLegRestartAndExpiredReplayNeverReleaseReservation(t *testing.T) {
	e, path, p, _, plan := multiLegFixture(t)
	a := multiLegApproval(t, plan, "101", p)
	if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatal(err)
	}
	if err := e.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(path, p, &engineTestBackend{})
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Unix(1800000200, 0) }
	if _, err := reopened.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("expired authority prepared new execution")
	}
	reserved, global := multiLegReserved(t, reopened, plan.OperationID)
	if reserved != 2000000 || global != 2000000 {
		t.Fatal("expiry released uncertain financial obligation")
	}
	a.IssuedAt = 1800000190
	a.ExpiresAt = 1800000300
	a.Allocation.IssuedAt = a.IssuedAt
	a.Allocation.ExpiresAt = a.ExpiresAt
	testSignAllocation(a.Allocation, p)
	testSignReturnApproval(&a, p)
	if _, err := reopened.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatalf("fresh identical economic replay failed after restart: %v", err)
	}
	reserved, global = multiLegReserved(t, reopened, plan.OperationID)
	if reserved != 2000000 || global != 2000000 {
		t.Fatal("restart replay double reserved funds")
	}
}

func TestMultiLegReviewedGlobalFundsCannotBeSpentByTwoTickets(t *testing.T) {
	e, _, p, _, first := multiLegFixture(t)
	first.FundsAvailableUWolo = "3000000"
	testSignAllocation(&first, p)
	r := engineTestWager(t, "2")
	r.AmountUWolo = "2000000"
	r.OwnerID = "owner-1"
	r.Reservation = testWagerReservation(t, r, p, time.Unix(1800000000, 0))
	if _, err := e.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(first)
	var second ReturnAllocation
	_ = json.Unmarshal(raw, &second)
	second.AllocationID = "allocation:ticket:2"
	second.OperationID = r.OperationID
	second.TicketID = "2"
	second.FundingTxHash = engineTestSigned(r).Hash
	second.Legs[0].Entitlements[0].ClaimID = "202"
	second.Legs[1].Entitlements[0].ClaimID = "201"
	testSignAllocation(&second, p)
	claims := []ReturnApproval{multiLegApproval(t, first, "101", p), multiLegApproval(t, second, "201", p)}
	var success atomic.Int32
	var wg sync.WaitGroup
	for _, a := range claims {
		a := a
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
				success.Add(1)
			}
		}()
	}
	wg.Wait()
	if success.Load() != 1 {
		t.Fatalf("shared reviewed funds permitted negative balance: accepted=%d", success.Load())
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		var f returnFundsState
		if err := json.Unmarshal(tx.Bucket(meta).Get(fundsKey), &f); err != nil {
			return err
		}
		if f.Reserved != 2000000 || f.Reserved > f.Available {
			return errors.New("negative_reviewed_budget")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestMultiLegLegacyRecordsRemainHeldAndBytePreserved(t *testing.T) {
	e, _, _, _, plan := multiLegFixture(t)
	legacy := ReturnApproval{OperationID: plan.OperationID, ClaimID: "77", OwnerID: "historical-owner", ClaimKind: "bet_refund", AmountUWolo: "2000000", AllocationDigest: strings.Repeat("D", 64)}
	record := returnRecord{Approval: legacy, Fingerprint: returnFingerprint(legacy)}
	raw, _ := json.Marshal(record)
	if err := e.db.Update(func(tx *bolt.Tx) error {
		b, err := tx.CreateBucketIfNotExists(returns)
		if err != nil {
			return err
		}
		return b.Put([]byte("77"), raw)
	}); err != nil {
		t.Fatal(err)
	}
	a := multiLegApproval(t, plan, "101", e.policy)
	if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("legacy liabilities silently migrated into new allocations")
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		if string(tx.Bucket(returns).Get([]byte("77"))) != string(raw) {
			return errors.New("historical_record_changed")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
