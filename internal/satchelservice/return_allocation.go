package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strconv"
	"strings"

	bolt "go.etcd.io/bbolt"
)

// ReturnAllocation is a reviewed ticket partition and a bounded escrow return
// budget. Its signature authenticates the independent allocation reviewer, not
// bank state. BankEvidenceDigest must refer to that review's complete bank and
// liability reconciliation. This service prepares requests only; the separately
// controlled escrow executor must still check real funds before transmission.
type ReturnAllocation struct {
	Version             int         `json:"version"`
	AllocationID        string      `json:"allocation_id"`
	Revision            uint64      `json:"revision"`
	OperationID         string      `json:"operation_id"`
	OwnerID             string      `json:"owner_id"`
	TicketID            string      `json:"ticket_id"`
	FundingTxHash       string      `json:"funding_tx_hash"`
	ReturnCapUWolo      string      `json:"return_cap_uwolo"`
	FundsBudgetID       string      `json:"funds_budget_id"`
	FundsAvailableUWolo string      `json:"funds_available_uwolo"`
	BankEvidenceDigest  string      `json:"bank_evidence_digest"`
	BankHeight          int64       `json:"bank_height"`
	BankBlockHash       string      `json:"bank_block_hash"`
	Legs                []ReturnLeg `json:"legs"`
	IssuedAt            int64       `json:"issued_at"`
	ExpiresAt           int64       `json:"expires_at"`
	Signature           string      `json:"signature"`
}
type ReturnLeg struct {
	LegID        string              `json:"leg_id"`
	MarketID     string              `json:"market_id"`
	StakeUWolo   string              `json:"stake_uwolo"`
	Entitlements []ReturnEntitlement `json:"entitlements"`
}
type ReturnEntitlement struct {
	EntitlementID  string `json:"entitlement_id"`
	ClaimID        string `json:"claim_id"`
	ClaimKind      string `json:"claim_kind"`
	PrincipalUWolo string `json:"principal_uwolo"`
	AmountUWolo    string `json:"amount_uwolo"`
}
type allocationState struct {
	Plan     ReturnAllocation
	Digest   string
	Reserved uint64
}
type returnFundsState struct {
	Identity            string
	Available, Reserved uint64
}

var allocationBucket = []byte("return-allocations-v2")
var fundsKey = []byte("return-funds-budget-v2")

func allocationFields(a ReturnAllocation, p Policy) []any {
	legs := make([]any, 0, len(a.Legs))
	for _, leg := range a.Legs {
		entries := make([]any, 0, len(leg.Entitlements))
		for _, entry := range leg.Entitlements {
			entries = append(entries, []string{entry.EntitlementID, entry.ClaimID, entry.ClaimKind, entry.PrincipalUWolo, entry.AmountUWolo})
		}
		legs = append(legs, []any{leg.LegID, leg.MarketID, leg.StakeUWolo, entries})
	}
	return []any{"aoe2war/satchel/return-allocation/v2", "wolo-1", "uwolo", p.BettingEscrow, p.Vault, a.Version, a.AllocationID, a.Revision, a.OperationID, a.OwnerID, a.TicketID, a.FundingTxHash, a.ReturnCapUWolo, a.FundsBudgetID, a.FundsAvailableUWolo, a.BankEvidenceDigest, a.BankHeight, a.BankBlockHash, legs}
}

// AllocationDigest excludes approval time/signature so the same immutable plan
// can be freshly authorized without changing a claim's economic identity.
func AllocationDigest(a ReturnAllocation, p Policy) string { return hashJSON(allocationFields(a, p)) }
func AllocationMessage(a ReturnAllocation, p Policy) []byte {
	v := append(allocationFields(a, p), a.IssuedAt, a.ExpiresAt)
	b, _ := json.Marshal(v)
	return b
}
func allocationRoot(a ReturnAllocation, p Policy) string {
	a.Revision = 0
	a.Legs = nil
	return hashJSON(allocationFields(a, p))
}
func fundsIdentity(a ReturnAllocation, p Policy) string {
	return hashJSON([]any{"return-funds-v2", p.BettingEscrow, p.Vault, a.FundsBudgetID, a.FundsAvailableUWolo, a.BankEvidenceDigest, a.BankHeight, a.BankBlockHash})
}
func positive(v string, max uint64) (uint64, bool) {
	if !amount(v, max) {
		return 0, false
	}
	n, err := strconv.ParseUint(v, 10, 64)
	return n, err == nil
}
func validReviewTime(issued, expires, now int64, fresh bool) bool {
	return issued >= 0 && expires > issued && uint64(expires)-uint64(issued) <= 300 && issued <= now && (!fresh || expires > now)
}
func verifyReview(key []byte, message []byte, signature string) bool {
	if len(signature) != 88 {
		return false
	}
	s, err := base64.StdEncoding.Strict().DecodeString(signature)
	return err == nil && len(key) == ed25519.PublicKeySize && len(s) == ed25519.SignatureSize && base64.StdEncoding.EncodeToString(s) == signature && ed25519.Verify(key, message, s)
}

func (e *Engine) validateAllocation(tx *bolt.Tx, a ReturnApproval, fresh bool) (ReturnEntitlement, error) {
	refuse := func() (ReturnEntitlement, error) { return ReturnEntitlement{}, errors.New("return_allocation_invalid") }
	p := a.Allocation
	if !boundedAllocation(p) {
		return refuse()
	}
	if a.Version != 2 || p == nil || p.Version != 2 || !ids.MatchString(p.AllocationID) || p.Revision == 0 || p.Revision > 100000 || p.OperationID != a.OperationID || p.OwnerID != a.OwnerID || p.TicketID != a.TicketID || !claimIDs.MatchString(p.TicketID) || !nonzeroDigest(p.FundingTxHash) || p.FundingTxHash != strings.ToUpper(p.FundingTxHash) || !ids.MatchString(p.FundsBudgetID) || !nonzeroDigest(p.BankEvidenceDigest) || p.BankHeight <= 0 || !nonzeroDigest(p.BankBlockHash) || len(p.Legs) == 0 || len(p.Legs) > 16 || !validReviewTime(p.IssuedAt, p.ExpiresAt, e.now().Unix(), fresh) || !verifyReview(e.policy.WithdrawalApprovalKey, AllocationMessage(*p, e.policy), p.Signature) || a.AllocationDigest != AllocationDigest(*p, e.policy) {
		return refuse()
	}
	cap, ok := positive(p.ReturnCapUWolo, 100000000000000)
	if !ok {
		return refuse()
	}
	funds, ok := positive(p.FundsAvailableUWolo, 100000000000000)
	if !ok || cap > funds {
		return refuse()
	}
	r, err := load(tx, a.OperationID)
	if err != nil {
		return ReturnEntitlement{}, err
	}
	if r.Result.Status != "CONFIRMED" || p.BankHeight < r.Confirmation.Height || r.Request.Kind != "wager" || r.Request.Recipient != e.policy.BettingEscrow || r.Result.TxHash != p.FundingTxHash || r.Request.Memo != "AoE2HDBets bet ticket v1 · ticket "+p.TicketID || e.backend.ValidateSigned(r.Request, r.Signed) != nil || (r.Request.OwnerID != "" && r.Request.OwnerID != a.OwnerID) {
		return refuse()
	}
	funded, ok := positive(r.Request.AmountUWolo, 1000000000)
	if !ok {
		return refuse()
	}
	return validateAllocationEconomics(a, funded)
}

// The offline financial bridge reuses this exact accounting contract. Its
// funded amount must come from HD's already authenticated durable ticket;
// neither the exported proof nor a signed reviewer claim supplies new capital.
func validateAllocationEconomics(a ReturnApproval, funded uint64) (ReturnEntitlement, error) {
	refuse := func() (ReturnEntitlement, error) { return ReturnEntitlement{}, errors.New("return_allocation_invalid") }
	p := a.Allocation
	if !boundedAllocation(p) || funded == 0 || funded > 1000000000 || p == nil || len(p.Legs) == 0 || len(p.Legs) > 16 {
		return refuse()
	}
	cap, ok := positive(p.ReturnCapUWolo, 100000000000000)
	if !ok {
		return refuse()
	}
	funds, ok := positive(p.FundsAvailableUWolo, 100000000000000)
	if !ok || cap > funds {
		return refuse()
	}
	seenClaims := map[string]bool{}
	seenEntitlements := map[string]bool{}
	seenMarkets := map[string]bool{}
	var totalStake, totalReturn uint64
	var found ReturnEntitlement
	previousLeg := ""
	count := 0
	for _, leg := range p.Legs {
		if !ids.MatchString(leg.LegID) || leg.LegID <= previousLeg || !claimIDs.MatchString(leg.MarketID) || seenMarkets[leg.MarketID] || len(leg.Entitlements) > 64 {
			return refuse()
		}
		previousLeg = leg.LegID
		seenMarkets[leg.MarketID] = true
		stake, ok := positive(leg.StakeUWolo, funded)
		if !ok || stake > funded-totalStake {
			return refuse()
		}
		totalStake += stake
		var principal uint64
		previousEntry := ""
		for _, entry := range leg.Entitlements {
			count++
			if count > 128 || !ids.MatchString(entry.EntitlementID) || entry.EntitlementID <= previousEntry || seenEntitlements[entry.EntitlementID] || !claimIDs.MatchString(entry.ClaimID) || entry.ClaimID == "889" || seenClaims[entry.ClaimID] || (entry.ClaimKind != "bet_refund" && entry.ClaimKind != "bet_payout") {
				return refuse()
			}
			previousEntry = entry.EntitlementID
			seenClaims[entry.ClaimID] = true
			seenEntitlements[entry.EntitlementID] = true
			n, ok := positive(entry.PrincipalUWolo, stake)
			if !ok || n > stake-principal {
				return refuse()
			}
			principal += n
			due, ok := positive(entry.AmountUWolo, 50000000000)
			if !ok || due > cap-totalReturn || (entry.ClaimKind == "bet_refund" && due != n) {
				return refuse()
			}
			totalReturn += due
			if entry.ClaimID == a.ClaimID {
				if leg.LegID != a.LegID || leg.MarketID != a.MarketID || entry.EntitlementID != a.EntitlementID || entry.ClaimKind != a.ClaimKind || entry.AmountUWolo != a.AmountUWolo {
					return refuse()
				}
				found = entry
			}
		}
	}
	if totalStake != funded || found.ClaimID == "" {
		return refuse()
	}
	return found, nil
}

func allocationsExtend(old, next ReturnAllocation, p Policy) bool {
	if allocationRoot(old, p) != allocationRoot(next, p) || len(old.Legs) != len(next.Legs) {
		return false
	}
	for i, leg := range old.Legs {
		n := next.Legs[i]
		if leg.LegID != n.LegID || leg.MarketID != n.MarketID || leg.StakeUWolo != n.StakeUWolo {
			return false
		}
		entries := map[string]ReturnEntitlement{}
		for _, entry := range n.Entitlements {
			entries[entry.EntitlementID] = entry
		}
		for _, entry := range leg.Entitlements {
			if entries[entry.EntitlementID] != entry {
				return false
			}
		}
	}
	return true
}

// reserveAllocation runs in the SAME Bolt transaction as the immutable claim
// record. Pending, uncertain and confirmed claims all consume their full amount;
// no timeout, cancellation or missing proof releases an entitlement or budget.
func (e *Engine) reserveAllocation(tx *bolt.Tx, a ReturnApproval, newClaim bool) error {
	p := *a.Allocation
	b, err := tx.CreateBucketIfNotExists(allocationBucket)
	if err != nil {
		return err
	}
	// There is no silent v1 migration. Its one-return marker and all old records
	// remain untouched; an independent liabilities review is needed first.
	if tx.Bucket(meta).Get([]byte("return-schema-v2")) == nil {
		cursor := tx.Bucket(meta).Cursor()
		if key, _ := cursor.Seek([]byte("return-operation:")); bytes.HasPrefix(key, []byte("return-operation:")) {
			return errors.New("legacy_return_review_required")
		}
		if old := tx.Bucket(returns); old != nil {
			count := 0
			if err := old.ForEach(func(_, data []byte) error {
				count++
				if count > 100000 {
					return errors.New("return_capacity_hold")
				}
				var r returnRecord
				if json.Unmarshal(data, &r) != nil {
					return errors.New("return_state_corrupt")
				}
				if r.Approval.Version != 2 {
					return errors.New("legacy_return_review_required")
				}
				return nil
			}); err != nil {
				return err
			}
		}
		if err := tx.Bucket(meta).Put([]byte("return-schema-v2"), []byte("2")); err != nil {
			return err
		}
	}
	if newClaim && tx.Bucket(returns).Stats().KeyN >= 100000 {
		return errors.New("return_capacity_hold")
	}
	if tx.Bucket(meta).Get([]byte("return-operation:"+a.OperationID)) != nil {
		return errors.New("legacy_return_review_required")
	}
	var state allocationState
	data := b.Get([]byte(a.OperationID))
	digest := AllocationDigest(p, e.policy)
	if data == nil {
		state = allocationState{Plan: p, Digest: digest}
	} else {
		if json.Unmarshal(data, &state) != nil || state.Digest != AllocationDigest(state.Plan, e.policy) {
			return errors.New("allocation_state_corrupt")
		}
		if p.Revision == state.Plan.Revision {
			if state.Digest != digest {
				return errors.New("allocation_revision_conflict")
			}
		} else if p.Revision > state.Plan.Revision && allocationsExtend(state.Plan, p, e.policy) {
			state.Plan = p
			state.Digest = digest
		} else if p.Revision < state.Plan.Revision && allocationsExtend(p, state.Plan, e.policy) {
			// A previously issued claim may arrive after a newer append-only plan.
			// Its exact entitlement must already exist in the latest durable plan.
		} else {
			return errors.New("allocation_revision_conflict")
		}
	}
	var funds returnFundsState
	m := tx.Bucket(meta)
	fundData := m.Get(fundsKey)
	identity := fundsIdentity(p, e.policy)
	available, _ := positive(p.FundsAvailableUWolo, 100000000000000)
	if fundData == nil {
		funds = returnFundsState{Identity: identity, Available: available}
	} else if json.Unmarshal(fundData, &funds) != nil || funds.Identity != identity || funds.Available != available || funds.Reserved > funds.Available {
		return errors.New("funds_budget_conflict")
	}
	cap, _ := positive(p.ReturnCapUWolo, 100000000000000)
	if state.Reserved > cap {
		return errors.New("allocation_state_corrupt")
	}
	if newClaim {
		due, _ := positive(a.AmountUWolo, 50000000000)
		if due > cap-state.Reserved || due > funds.Available-funds.Reserved {
			return errors.New("return_budget_exhausted")
		}
		state.Reserved += due
		funds.Reserved += due
	}
	data, _ = json.Marshal(state)
	if err = b.Put([]byte(a.OperationID), data); err != nil {
		return err
	}
	data, _ = json.Marshal(funds)
	return m.Put(fundsKey, data)
}

// Bound every variable-sized field before constructing signature preimages.
func boundedAllocation(p *ReturnAllocation) bool {
	if p == nil || len(p.Legs) == 0 || len(p.Legs) > 16 || len(p.Signature) != 88 || !ids.MatchString(p.OperationID) || !ids.MatchString(p.OwnerID) || len(p.AllocationID) > 128 || len(p.TicketID) > 12 || len(p.FundingTxHash) != 64 || len(p.ReturnCapUWolo) > 15 || len(p.FundsBudgetID) > 128 || len(p.FundsAvailableUWolo) > 15 || len(p.BankEvidenceDigest) != 64 || len(p.BankBlockHash) != 64 {
		return false
	}
	count := 0
	for _, leg := range p.Legs {
		if len(leg.LegID) > 128 || len(leg.MarketID) > 12 || len(leg.StakeUWolo) > 15 || len(leg.Entitlements) > 64 {
			return false
		}
		count += len(leg.Entitlements)
		if count > 128 {
			return false
		}
		for _, entry := range leg.Entitlements {
			if len(entry.EntitlementID) > 128 || len(entry.ClaimID) > 12 || len(entry.ClaimKind) > 16 || len(entry.PrincipalUWolo) > 15 || len(entry.AmountUWolo) > 15 {
				return false
			}
		}
	}
	return true
}
