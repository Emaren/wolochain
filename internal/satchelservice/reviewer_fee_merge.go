package satchelservice

// This is arithmetic preparation from already authenticated source checkpoints.
// It authenticates no bank, certifies no global coverage, signs no approval and
// releases no durable hold. Protected source readers and reserve reviewers must
// establish those separate facts before any issuer uses the returned fees.
import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"sort"
	"strings"
	"time"
)

const reviewerFeeCheckpointMaxAge = 2 * time.Second

// ReviewerFeeMergeAuthority comes from protected configuration, never a wager
// request or either checkpoint. The custody and issuer policies may differ.
type ReviewerFeeMergeAuthority struct {
	Vault               string
	CustodyPolicyDigest string
	IssuerPolicyDigest  string
	WagerApprovalKey    ed25519.PublicKey
}

// MergeReviewerPendingFees includes every unresolved custody fee and every
// outstanding issuer fee, deduplicating only exact verified original identities.
// The proposed fee is counted separately by AssessReviewerFeeBudget; it can be
// excluded here only when its original identity and actual fee are consistent.
func MergeReviewerPendingFees(proposed WagerReservation, issued ReviewerIssuedFeeCheckpoint, custody ReviewerCustodyFeeCheckpoint, authority ReviewerFeeMergeAuthority, completed time.Time) ([]ReviewerPendingFee, error) {
	if !validAddress(authority.Vault) || !validReserveDigest(authority.CustodyPolicyDigest) || !validReserveDigest(authority.IssuerPolicyDigest) ||
		len(authority.WagerApprovalKey) != ed25519.PublicKeySize || bytesAllZero(authority.WagerApprovalKey) || completed.IsZero() || completed.UnixMilli() <= 0 {
		return nil, ErrReviewerHeld
	}
	publicHash := sha256.Sum256(authority.WagerApprovalKey)
	publicFingerprint := hex.EncodeToString(publicHash[:])
	if issued.Protocol != 1 || issued.Kind != reviewerIssuedFeeCheckpointKind || issued.ChainID != "wolo-1" || issued.Denom != "uwolo" || issued.Vault != authority.Vault ||
		issued.PolicyDigest != authority.IssuerPolicyDigest || issued.ApprovalKeyFingerprint != publicFingerprint || !validReserveDigest(issued.JournalDigest) ||
		custody.Protocol != 1 || custody.Kind != "custody_fee_checkpoint" || custody.ChainID != "wolo-1" || custody.Denom != "uwolo" || custody.Vault != authority.Vault ||
		custody.PolicyDigest != authority.CustodyPolicyDigest || custody.WagerApprovalKeyFingerprint != publicFingerprint || !validReserveDigest(custody.JournalDigest) ||
		!reviewerFeeCheckpointFresh(issued.ObservedAtMS, completed) || !reviewerFeeCheckpointFresh(custody.ObservedAtMS, completed) ||
		issued.PendingFees == nil || issued.EntryFingerprints == nil || custody.UnresolvedFees == nil || custody.AccountedOperations == nil || custody.AccountedFingerprints == nil {
		return nil, ErrReviewerHeld
	}
	if !validReviewerFeeProposal(proposed, authority.Vault) {
		return nil, ErrReviewerHeld
	}
	originalFingerprint := reviewerFingerprint(proposed)
	issuerFees, err := reviewerFeeList(issued.PendingFees, true)
	if err != nil || len(issued.EntryFingerprints) != len(issuerFees) {
		return nil, ErrReviewerHeld
	}
	requested := map[string]bool{proposed.OperationID: true}
	for id := range issuerFees {
		if !validReserveDigest(issued.EntryFingerprints[id]) {
			return nil, ErrReviewerHeld
		}
		requested[id] = true
	}
	actualFees, err := reviewerFeeList(custody.UnresolvedFees, false)
	if err != nil || len(custody.AccountedOperations) != len(requested) || len(custody.AccountedFingerprints) != len(requested) {
		return nil, ErrReviewerHeld
	}
	for id := range requested {
		status, present := custody.AccountedOperations[id]
		fingerprint, hasFingerprint := custody.AccountedFingerprints[id]
		if !present || !hasFingerprint || (fingerprint != "" && !validReserveDigest(fingerprint)) {
			return nil, ErrReviewerHeld
		}
		_, unresolved := actualFees[id]
		switch status {
		case "NOT_RECORDED":
			if fingerprint != "" || unresolved {
				return nil, ErrReviewerHeld
			}
		case "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING":
			if !unresolved {
				return nil, ErrReviewerHeld
			}
		case "CONFIRMED", "FAILED", "REFUSED":
			if unresolved {
				return nil, ErrReviewerHeld
			}
		default:
			return nil, ErrReviewerHeld
		}
	}
	// Preserve all actual unresolved custody operations, including withdrawals
	// and legacy operations whose original approval identity is unavailable.
	merged := make(map[string]ReviewerPendingFee, len(actualFees)+len(issuerFees))
	for id, fee := range actualFees {
		merged[id] = fee
	}
	for id, fee := range issuerFees {
		if id == proposed.OperationID && issued.EntryFingerprints[id] != originalFingerprint {
			return nil, ErrReviewerHeld
		}
		status, fingerprint := custody.AccountedOperations[id], custody.AccountedFingerprints[id]
		if status == "NOT_RECORDED" {
			// A legacy crash PENDING for the current operation cannot be treated
			// as an unattempted fresh operation or reissued after restart.
			if id == proposed.OperationID && fee.Stage == "uncertain" {
				return nil, ErrReviewerHeld
			}
			merged[id] = fee
			continue
		}
		if fingerprint == "" || fingerprint != issued.EntryFingerprints[id] {
			return nil, ErrReviewerHeld
		}
		if actual, unresolved := actualFees[id]; unresolved {
			// SIGNED must agree with the exact actual fee. The legacy PENDING
			// maximum can be superseded only by this proven matching identity.
			if fee.Stage != "uncertain" && fee.FeeUWolo != actual.FeeUWolo {
				return nil, ErrReviewerHeld
			}
		}
		// A verified terminal original has already accounted for its fee in
		// bank state. Its matching issuer entry adds no second pending debit.
	}
	if fee, exists := issuerFees[proposed.OperationID]; exists && fee.Stage == "prepared" && fee.FeeUWolo != proposed.FeeUWolo {
		return nil, ErrReviewerHeld
	}
	if custody.AccountedOperations[proposed.OperationID] != "NOT_RECORDED" {
		if custody.AccountedFingerprints[proposed.OperationID] != originalFingerprint {
			return nil, ErrReviewerHeld
		}
		if actual, unresolved := actualFees[proposed.OperationID]; unresolved && actual.FeeUWolo != proposed.FeeUWolo {
			return nil, ErrReviewerHeld
		}
	}
	delete(merged, proposed.OperationID)
	if len(merged) > reviewerMaxPendingOperations {
		return nil, ErrReviewerHeld
	}
	ids := make([]string, 0, len(merged))
	for id := range merged {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	out := make([]ReviewerPendingFee, 0, len(ids))
	for _, id := range ids {
		out = append(out, merged[id])
	}
	return out, nil
}

func reviewerFeeCheckpointFresh(observedMS int64, completed time.Time) bool {
	now := completed.UnixMilli()
	return observedMS > 0 && observedMS <= now && now-observedMS <= reviewerFeeCheckpointMaxAge.Milliseconds()
}

func validReviewerFeeProposal(p WagerReservation, vault string) bool {
	amountUWolo, amountErr := reviewerAmount(p.AmountUWolo, ProductMaxWagerUWolo, true)
	_, feeErr := reviewerAmount(p.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
	return p.Version == 1 && wagerIDs.MatchString(p.OperationID) && ownerUIDPattern.MatchString(p.OwnerID) && p.Vault == vault &&
		validAddress(p.Recipient) && p.Recipient != vault && ticketMemo.MatchString(p.Memo) && amountErr == nil && amountUWolo%1000000 == 0 && feeErr == nil &&
		validReserveDigest(p.ReservationDigest) && validReserveDigest(p.LedgerRevision) && validReserveDigest(p.ConsentDigest) &&
		p.IssuedAt == 0 && p.ExpiresAt == 0 && p.Signature == ""
}

func reviewerFeeList(fees []ReviewerPendingFee, issuer bool) (map[string]ReviewerPendingFee, error) {
	if len(fees) > reviewerMaxPendingOperations {
		return nil, ErrReviewerHeld
	}
	out := make(map[string]ReviewerPendingFee, len(fees))
	previous := ""
	for _, fee := range fees {
		withdrawalID := strings.TrimPrefix(fee.OperationID, "satchel:withdrawal:")
		validID := wagerIDs.MatchString(fee.OperationID) || (!issuer && withdrawalID != fee.OperationID && uuid.MatchString(withdrawalID))
		_, err := reviewerAmount(fee.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
		if !validID || fee.OperationID <= previous || err != nil || (fee.Stage != "prepared" && fee.Stage != "uncertain") ||
			(issuer && fee.Stage == "uncertain" && fee.FeeUWolo != "1000000") {
			return nil, ErrReviewerHeld
		}
		previous = fee.OperationID
		out[fee.OperationID] = fee
	}
	return out, nil
}

func bytesAllZero(value []byte) bool {
	for _, b := range value {
		if b != 0 {
			return false
		}
	}
	return true
}
