package satchelservice

// Offline arithmetic prerequisite for the independently operated Mecha
// wager reviewer. This code deliberately CANNOT sign an approval, authenticate
// the bank, certify a complete producer census or authorize an execution.
// A bank balance or "complete" bit supplied by HD is not trustworthy evidence.
import (
	"errors"
	"math"
	"regexp"
	"strconv"
)

const reviewerMaxPendingOperations = 10000
const reviewerMaxOperationFeeUWolo = 1000000

var reviewerOperationID = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,128}$`)

type ReviewerPendingFee struct {
	OperationID string
	Stage       string // prepared or uncertain; UNKNOWN must never free gas
	FeeUWolo    string
}

type ReviewerFeeCensus struct {
	ChainID                       string
	Denom                         string
	OperationID                   string
	BankBalanceUWolo              string
	AllOwnerLiabilitiesUWolo      string
	PendingOperations             []ReviewerPendingFee
	NewOperationFeeUWolo          string
	MinimumUnencumberedGasUWolo   string
	PendingOperationsComplete     bool // An ASSERTION; caller must prove this independently.
}

type ReviewerFeeBudget struct {
	Status                    string
	PendingFeeUWolo           string
	RequiredUWolo             string
	RemainingUWolo            string
	SpendingAuthorized        bool // Always false; a positive result is only arithmetic.
	BankAuthenticated        bool // Always false; independent Comet proof still required.
	OwnerLedgerAuthenticated bool // Always false; separate DB attestation still required.
}

var reviewerInteger = regexp.MustCompile(`^(0|[1-9][0-9]{0,18})$`)

func reviewerAmount(value string, max uint64, positive bool) (uint64, error) {
	if !reviewerInteger.MatchString(value) {
		return 0, errors.New("reviewer_fee_noncanonical_integer")
	}
	n, err := strconv.ParseUint(value, 10, 64)
	if err != nil || n > max || (positive && n == 0) {
		return 0, errors.New("reviewer_fee_out_of_range")
	}
	return n, nil
}

func reviewerAdd(a, b uint64) (uint64, error) {
	if b > uint64(math.MaxInt64)-a {
		return 0, errors.New("reviewer_fee_aggregate_overflow")
	}
	return a + b, nil
}

// AssessReviewerFeeBudget binds the prospective fee to the exact ticket
// operation. It does not validate a Keplr mandate, an owner balance debit,
// Watcher identity, chain state, signing key or old escrow liabilities.
// Only a separately authenticated reviewer can use its numbers as one input.
func AssessReviewerFeeBudget(c ReviewerFeeCensus, proposed WagerReservation) (ReviewerFeeBudget, error) {
	none := ReviewerFeeBudget{Status: "CENSUS_INCOMPLETE"}
	if c.ChainID != "wolo-1" || c.Denom != "uwolo" ||
		c.OperationID != proposed.OperationID ||
		!wagerIDs.MatchString(proposed.OperationID) {
		return none, errors.New("reviewer_fee_wrong_chain_or_operation")
	}
	bank, err := reviewerAmount(c.BankBalanceUWolo, uint64(math.MaxInt64), false)
	if err != nil {
		return none, err
	}
	liabilities, err := reviewerAmount(c.AllOwnerLiabilitiesUWolo, uint64(math.MaxInt64), false)
	if err != nil {
		return none, err
	}
	newFee, err := reviewerAmount(c.NewOperationFeeUWolo, reviewerMaxOperationFeeUWolo, true)
	if err != nil {
		return none, err
	}
	if proposed.FeeUWolo != c.NewOperationFeeUWolo {
		return none, errors.New("reviewer_fee_does_not_match_original_wager")
	}
	cushion, err := reviewerAmount(c.MinimumUnencumberedGasUWolo, uint64(math.MaxInt64), false)
	if err != nil {
		return none, err
	}
	if len(c.PendingOperations) > reviewerMaxPendingOperations {
		return none, errors.New("reviewer_fee_inventory_unbounded")
	}
	seen := make(map[string]struct{}, len(c.PendingOperations))
	var pending uint64
	for _, p := range c.PendingOperations {
		if !reviewerOperationID.MatchString(p.OperationID) ||
			p.OperationID == proposed.OperationID ||
			(p.Stage != "prepared" && p.Stage != "uncertain") {
			return none, errors.New("reviewer_fee_pending_operation_invalid")
		}
		if _, exists := seen[p.OperationID]; exists {
			return none, errors.New("reviewer_fee_pending_operation_duplicate")
		}
		seen[p.OperationID] = struct{}{}
		fee, parseErr := reviewerAmount(p.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
		if parseErr != nil {
			return none, parseErr
		}
		pending, err = reviewerAdd(pending, fee)
		if err != nil {
			return none, err
		}
	}
	// No quantity returned below can establish that the inventory was
	// independently assembled. False/unavailable remains a hard HOLD.
	none.PendingFeeUWolo = strconv.FormatUint(pending, 10)
	if !c.PendingOperationsComplete {
		return none, nil
	}
	required := liabilities
	for _, v := range []uint64{pending, newFee, cushion} {
		required, err = reviewerAdd(required, v)
		if err != nil {
			return none, err
		}
	}
	if bank < required {
		return ReviewerFeeBudget{Status: "INSUFFICIENT_HEADROOM",
			PendingFeeUWolo: strconv.FormatUint(pending, 10),
			RequiredUWolo:   strconv.FormatUint(required, 10)}, nil
	}
	return ReviewerFeeBudget{Status: "BUDGET_SUFFICIENT_NONAUTHORIZING",
		PendingFeeUWolo: strconv.FormatUint(pending, 10),
		RequiredUWolo:   strconv.FormatUint(required, 10),
		RemainingUWolo:  strconv.FormatUint(bank-required, 10)}, nil
}
