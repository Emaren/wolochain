package satchelservice

import (
	"encoding/json"
	"strings"
	"testing"

	bolt "go.etcd.io/bbolt"
)

func attackClonePlan(t *testing.T, p ReturnAllocation) ReturnAllocation {
	t.Helper()
	data, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	var result ReturnAllocation
	if err = json.Unmarshal(data, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func attackRevisionPlans(t *testing.T, p Policy, plan ReturnAllocation) (ReturnAllocation, ReturnAllocation) {
	t.Helper()
	first := attackClonePlan(t, plan)
	first.Legs[0].Entitlements = nil
	first.Legs[1].Entitlements = []ReturnEntitlement{
		{EntitlementID: "winner-a", ClaimID: "201", ClaimKind: "bet_payout", PrincipalUWolo: "500000", AmountUWolo: "1000000"},
		{EntitlementID: "winner-b", ClaimID: "202", ClaimKind: "bet_payout", PrincipalUWolo: "500000", AmountUWolo: "1000000"},
	}
	testSignAllocation(&first, p)
	later := attackClonePlan(t, first)
	later.Revision = 3 // The intermediate signed plan need never be delivered.
	later.Legs[0].Entitlements = []ReturnEntitlement{{EntitlementID: "desync-refund", ClaimID: "203", ClaimKind: "bet_refund", PrincipalUWolo: "1000000", AmountUWolo: "1000000"}}
	testSignAllocation(&later, p)
	return first, later
}

func TestAllocationOlderUndeliveredClaimSurvivesSkippedAppendOnlyRevision(t *testing.T) {
	for _, initialLatest := range []bool{false, true} {
		name := "older-plan-seeded"
		if initialLatest {
			name = "latest-plan-arrives-first"
		}
		t.Run(name, func(t *testing.T) {
			e, _, p, b, plan := multiLegFixture(t)
			first, later := attackRevisionPlans(t, p, plan)
			var order []ReturnApproval
			if initialLatest {
				order = []ReturnApproval{multiLegApproval(t, later, "203", p), multiLegApproval(t, first, "201", p), multiLegApproval(t, first, "202", p)}
			} else {
				order = []ReturnApproval{multiLegApproval(t, first, "201", p), multiLegApproval(t, later, "203", p), multiLegApproval(t, first, "202", p)}
			}
			for _, a := range order {
				if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
					t.Fatalf("leg %s at revision %d refused out of order: %v", a.ClaimID, a.Allocation.Revision, err)
				}
			}
			var stored allocationState
			if err := e.db.View(func(tx *bolt.Tx) error {
				return json.Unmarshal(tx.Bucket(allocationBucket).Get([]byte(plan.OperationID)), &stored)
			}); err != nil {
				t.Fatal(err)
			}
			if stored.Plan.Revision != 3 || stored.Digest != AllocationDigest(later, p) || stored.Reserved != 3000000 {
				t.Fatalf("old claim rolled back authority or budget: %+v", stored)
			}
			reserved, global := multiLegReserved(t, e, plan.OperationID)
			if reserved != 3000000 || global != 3000000 {
				t.Fatalf("out-of-order deliveries changed obligations: %d/%d", reserved, global)
			}
			for _, a := range order {
				if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
					t.Fatalf("exact duplicate failed: %v", err)
				}
			}
			reserved, global = multiLegReserved(t, e, plan.OperationID)
			if reserved != 3000000 || global != 3000000 || b.signs.Load() != 1 || b.broadcasts.Load() != 1 {
				t.Fatal("replayed old manifests reserved or transmitted again")
			}
		})
	}
}

func TestAllocationOlderManifestCannotInjectAnotherEntitlement(t *testing.T) {
	e, _, p, _, plan := multiLegFixture(t)
	first, later := attackRevisionPlans(t, p, plan)
	if _, err := e.PrepareReturnRun(t.Context(), multiLegApproval(t, later, "203", p)); err != nil {
		t.Fatal(err)
	}
	// A newly signed older revision is not allowed to retroactively introduce
	// an entitlement absent from the latest approved journal plan.
	first.Legs[1].Entitlements[1].ClaimID = "204"
	first.Legs[1].Entitlements[1].EntitlementID = "winner-c"
	testSignAllocation(&first, p)
	if _, err := e.PrepareReturnRun(t.Context(), multiLegApproval(t, first, "204", p)); err == nil {
		t.Fatal("older re-signed manifest introduced a new entitlement")
	}
	reserved, global := multiLegReserved(t, e, plan.OperationID)
	if reserved != 1000000 || global != 1000000 {
		t.Fatal("refused older allocation altered budget")
	}
}

func TestAllocationReSignedBankSnapshotCannotResetSharedFundsBudget(t *testing.T) {
	for name, mutate := range map[string]func(*ReturnAllocation){
		"budget namespace": func(a *ReturnAllocation) { a.FundsBudgetID = "bank-review-new" },
		"larger balance":   func(a *ReturnAllocation) { a.FundsAvailableUWolo = "50000000001" },
		"smaller balance":  func(a *ReturnAllocation) { a.FundsAvailableUWolo = "49999999999" },
		"evidence digest":  func(a *ReturnAllocation) { a.BankEvidenceDigest = strings.Repeat("F", 64) },
		"height":           func(a *ReturnAllocation) { a.BankHeight++ },
		"block":            func(a *ReturnAllocation) { a.BankBlockHash = strings.Repeat("C", 64) },
	} {
		t.Run(name, func(t *testing.T) {
			e, _, p, b, plan := multiLegFixture(t)
			if _, err := e.PrepareReturnRun(t.Context(), multiLegApproval(t, plan, "102", p)); err != nil {
				t.Fatal(err)
			}
			request := engineTestWager(t, "2")
			request.OwnerID = "owner-1"
			if _, err := e.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Reconcile(t.Context(), request.OperationID); err != nil {
				t.Fatal(err)
			}
			second := attackClonePlan(t, plan)
			second.OperationID = request.OperationID
			second.TicketID = "2"
			second.AllocationID = "allocation:ticket:2"
			second.FundingTxHash = engineTestSigned(request).Hash
			second.Legs = []ReturnLeg{{LegID: "winner", MarketID: "503", StakeUWolo: "1000000", Entitlements: []ReturnEntitlement{{EntitlementID: "ticket-two-refund", ClaimID: "211", ClaimKind: "bet_refund", PrincipalUWolo: "1000000", AmountUWolo: "1000000"}}}}
			mutate(&second)
			testSignAllocation(&second, p)
			if _, err := e.PrepareReturnRun(t.Context(), multiLegApproval(t, second, "211", p)); err == nil {
				t.Fatal("new signed bank metadata reset existing shared capacity")
			}
			_, global := multiLegReserved(t, e, plan.OperationID)
			if global != 1000000 || b.signs.Load() != 2 || b.broadcasts.Load() != 2 {
				t.Fatal("refused new budget changed reserved funds or sent a return")
			}
		})
	}
}

func TestAllocationOldExpiryCannotCreateNewObligation(t *testing.T) {
	e, _, p, _, plan := multiLegFixture(t)
	if _, err := e.PrepareReturnRun(t.Context(), multiLegApproval(t, plan, "101", p)); err != nil {
		t.Fatal(err)
	}
	// A fresh claim signature cannot refresh its expired allocation authority.
	plan.IssuedAt = 1799999699
	plan.ExpiresAt = 1799999999
	testSignAllocation(&plan, p)
	a := multiLegApproval(t, plan, "102", p)
	a.IssuedAt = 1799999990
	a.ExpiresAt = 1800000100
	testSignReturnApproval(&a, p)
	if _, err := e.PrepareReturnRun(t.Context(), a); err == nil {
		t.Fatal("fresh claim revived expired allocation")
	}
	reserved, global := multiLegReserved(t, e, plan.OperationID)
	if reserved != 2000000 || global != 2000000 {
		t.Fatal("expired allocation created an obligation")
	}
}
