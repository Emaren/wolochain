package satchelservice

// This binds original-review-stage principal evidence into the existing dual
// reserve review. It does not discharge a liability or authorize a payment;
// custody still needs its separate post-attempt revalidation and durable fence.
import (
	"context"
	"math"
	"time"
)

type ReviewerPrincipalPartitionReader interface {
	ReadWagerPrincipalPartition(context.Context, WagerReservation) (VerifiedReviewerPrincipalPartition, error)
}

type ReviewerPrincipalSpendBinding struct {
	Protocol             int    `json:"protocol"`
	Kind                 string `json:"kind"`
	ChainID              string `json:"chain_id"`
	Denom                string `json:"denom"`
	Vault                string `json:"vault"`
	OperationID          string `json:"operation_id"`
	OwnerID              string `json:"owner_id"`
	PrincipalUWolo       string `json:"principal_uwolo"`
	ProposedFingerprint  string `json:"proposed_fingerprint"`
	ReservationDigest    string `json:"reservation_digest"`
	LedgerRevision       string `json:"ledger_revision"`
	ConsentDigest        string `json:"consent_digest"`
	LedgerVersion        string `json:"ledger_version"`
	PartitionSHA256      string `json:"partition_sha256"`
	OwnerLedgerSHA256    string `json:"owner_ledger_sha256"`
	CustodyJournalSHA256 string `json:"custody_journal_sha256"`
}

// Independently operated reviewers can prepare the exact canonical body value
// after reading their real source. No amount, caller JSON or bare digest can
// substitute for an opaque fresh verified partition here. Timestamps stay out
// of this value so repeated reads of an unchanged partition have the same hash;
// source freshness and the existing signed reserve review bound its lifetime.
func PrepareReviewerPrincipalSpendBinding(partition VerifiedReviewerPrincipalPartition, proposed WagerReservation, completed time.Time) (ReviewerPrincipalSpendBinding, error) {
	if !partition.FreshAt(completed) || !validReviewerFeeProposal(proposed, proposed.Vault) || partition.operation != proposed.OperationID || partition.owner != proposed.OwnerID ||
		partition.principal != proposed.AmountUWolo || partition.proposedFingerprint != reviewerFingerprint(proposed) ||
		!validReserveDigest(partition.partitionDigest) || !validReserveDigest(partition.ownerLedgerDigest) || !validReserveDigest(partition.custodyJournalDigest) ||
		!reviewerUnsignedDecimal(partition.ledgerVersion, true, math.MaxInt64) {
		return ReviewerPrincipalSpendBinding{}, ErrReviewerHeld
	}
	return ReviewerPrincipalSpendBinding{Protocol: 1, Kind: "owner_principal_spend_binding", ChainID: "wolo-1", Denom: "uwolo", Vault: proposed.Vault, OperationID: proposed.OperationID, OwnerID: proposed.OwnerID,
		PrincipalUWolo: partition.principal, ProposedFingerprint: partition.proposedFingerprint, ReservationDigest: proposed.ReservationDigest, LedgerRevision: proposed.LedgerRevision, ConsentDigest: proposed.ConsentDigest,
		LedgerVersion: partition.ledgerVersion, PartitionSHA256: partition.partitionDigest, OwnerLedgerSHA256: partition.ownerLedgerDigest, CustodyJournalSHA256: partition.custodyJournalDigest}, nil
}

func (ReviewerPrincipalSpendBinding) SpendingAuthorized() bool { return false }

func (s *ReviewerReserveCensusSource) verifyPrincipalSpendBinding(body ReviewerReserveCensusBody, proposed WagerReservation, ownerLedger, custodyJournal string, now time.Time, partitions ...VerifiedReviewerPrincipalPartition) error {
	if s.config.PrincipalPartitions == nil {
		if body.PrincipalSpend != nil || len(partitions) != 0 {
			return ReviewerCensusCoverageInvalid
		}
		return nil
	}
	if body.PrincipalSpend == nil || len(partitions) != 1 {
		return ReviewerCensusCoverageInvalid
	}
	expected, err := PrepareReviewerPrincipalSpendBinding(partitions[0], proposed, now)
	if err != nil || expected.OwnerLedgerSHA256 != ownerLedger || expected.CustodyJournalSHA256 != custodyJournal || *body.PrincipalSpend != expected {
		return ReviewerCensusSourceInvalid
	}
	return nil
}

func (s *ReviewerReserveCensusSource) readPrincipalPartition(ctx context.Context, proposed WagerReservation) ([]VerifiedReviewerPrincipalPartition, error) {
	if s.config.PrincipalPartitions == nil {
		return nil, nil
	}
	partition, err := s.config.PrincipalPartitions.ReadWagerPrincipalPartition(ctx, proposed)
	if err != nil || ctx.Err() != nil {
		return nil, ReviewerCensusSourceInvalid
	}
	return []VerifiedReviewerPrincipalPartition{partition}, nil
}

var _ ReviewerPrincipalPartitionReader = (*ReviewerPrincipalPartitionSource)(nil)
