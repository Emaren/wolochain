package satchelservice

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
)

const reviewerReserveCensusScope = "aoe2war/satchel/reviewer-fee-census/v1"
const reviewerReserveCensusMaxBytes = 2 << 20
const reviewerOwnerLedgerProducer = "hd-current-vault-ledger"
const reviewerPendingFeesProducer = "satchel-pending-fees"

type ReviewerReserveCoverageReader interface {
	ReadReviewerReserveCoverage(context.Context) ([]byte, error)
}
type ReviewerCustodyFeeReader interface {
	ReadReviewerCustodyFees(context.Context, []string) (ReviewerCustodyFeeCheckpoint, error)
}

type ReviewerReserveObligation struct {
	EconomicKey string `json:"economic_key"`
	Kind        string `json:"kind"`
	AmountUWolo string `json:"amount_uwolo"`
}
type ReviewerReserveProducer struct {
	ProducerID       string                      `json:"producer_id"`
	CheckpointSHA256 string                      `json:"checkpoint_sha256"`
	Obligations      []ReviewerReserveObligation `json:"obligations"`
	PendingFees      []ReviewerPendingFee        `json:"pending_fees"`
}
type ReviewerReserveNonOverlap struct {
	EconomicKey string `json:"economic_key"`
	ProducerID  string `json:"producer_id"`
}

type ReviewerReserveCensusBody struct {
	Protocol             int                            `json:"protocol"`
	Scope                string                         `json:"scope"`
	Vault                string                         `json:"vault"`
	OperationID          string                         `json:"operation_id"`
	ProposedFingerprint  string                         `json:"proposed_fingerprint"`
	BookedPrincipalUWolo string                         `json:"booked_principal_uwolo"`
	OwnerLedgerSHA256    string                         `json:"owner_ledger_sha256"`
	CustodyJournalSHA256 string                         `json:"custody_journal_sha256"`
	IssuerJournalSHA256  string                         `json:"issuer_journal_sha256"`
	Producers            []ReviewerReserveProducer      `json:"producers"`
	NonOverlap           []ReviewerReserveNonOverlap    `json:"nonoverlap"`
	PrincipalSpend       *ReviewerPrincipalSpendBinding `json:"principal_spend,omitempty"`
}
type ReviewerReserveCensusBundle struct {
	Version int                       `json:"version"`
	Review  SignedReserveReview       `json:"review"`
	Body    ReviewerReserveCensusBody `json:"body"`
}

type ReviewerReserveCensusConfig struct {
	Authority                ReserveReviewAuthority
	FeeSources               ReviewerFeeMergeAuthority
	RequiredProducerIDs      []string
	FeeUWolo                 string
	MinimumGasReserveUWolo   string
	MinimumUnencumberedUWolo string
	PrincipalPartitions      ReviewerPrincipalPartitionReader
}

type ReviewerReserveCensusSource struct {
	*ReviewerFinanceSource
	custody  ReviewerCustodyFeeReader
	coverage ReviewerReserveCoverageReader
	config   ReviewerReserveCensusConfig
	required []string
	now      func() time.Time
}

// Every known historical/external scope must be represented, even where a
// separately reviewed statement proves no exposure to this particular vault.
// An empty current Satchel ledger cannot erase these required source identities.
var reviewerRequiredReserveProducers = []string{
	"all_signer_pending_uncertain_and_unmaterialized_fees",
	"de_and_external_obligations_and_overlaps",
	"hd-current-vault-ledger",
	"hd_manual_and_founder_obligations",
	"satchel-pending-fees",
	"staking_and_treasury_encumbrances",
}

type ReviewerCensusFailure string

const (
	ReviewerCensusUnconfigured    ReviewerCensusFailure = "reviewer_census_unconfigured"
	ReviewerCensusCoverageInvalid ReviewerCensusFailure = "reviewer_census_coverage_untrusted"
	ReviewerCensusSourceInvalid   ReviewerCensusFailure = "reviewer_census_source_identity_invalid"
	ReviewerCensusSnapshotChanged ReviewerCensusFailure = "reviewer_census_snapshot_changed"
	ReviewerCensusBankInvalid     ReviewerCensusFailure = "reviewer_census_native_bank_invalid"
)

func (e ReviewerCensusFailure) Error() string        { return string(e) }
func (e ReviewerCensusFailure) Is(target error) bool { return target == ErrReviewerHeld }

// This explicit composition replaces only the previously unavailable census.
// It never accepts request-supplied roots, role keys or a complete=true switch.
// Enrolled reviewers still attest source completeness; signatures cannot prove
// physical operator independence or discover an omitted external producer.
func NewReviewerReserveCensusSource(base *ReviewerFinanceSource, custody ReviewerCustodyFeeReader, coverage ReviewerReserveCoverageReader, cfg ReviewerReserveCensusConfig) (*ReviewerReserveCensusSource, error) {
	if base == nil || base.ReviewerEvidenceSource == nil || base.pg == nil || base.pg.db == nil || base.bank == nil || custody == nil || coverage == nil ||
		!validReviewAuthority(cfg.Authority) || !validAddress(cfg.Authority.ExpectedVault) || cfg.Authority.ExpectedVault != base.pg.vault ||
		cfg.FeeSources.Vault != base.pg.vault || !bytes.Equal(cfg.FeeSources.WagerApprovalKey, cfg.Authority.WagerApprovalKey) ||
		!validReserveDigest(cfg.FeeSources.CustodyPolicyDigest) || !validReserveDigest(cfg.FeeSources.IssuerPolicyDigest) || cfg.FeeUWolo != base.pg.fee {
		return nil, ReviewerCensusUnconfigured
	}
	for _, key := range []ed25519.PublicKey{cfg.Authority.AccountingReviewerKey, cfg.Authority.CustodyReviewerKey, cfg.Authority.ExecutionAuthorityKey, cfg.Authority.WagerApprovalKey, cfg.Authority.WithdrawalApprovalKey} {
		if bytesAllZero(key) {
			return nil, ReviewerCensusUnconfigured
		}
	}
	if _, err := reviewerAmount(cfg.FeeUWolo, reviewerMaxOperationFeeUWolo, true); err != nil {
		return nil, ReviewerCensusUnconfigured
	}
	for _, n := range []string{cfg.MinimumGasReserveUWolo, cfg.MinimumUnencumberedUWolo} {
		if _, err := reviewerAmount(n, math.MaxInt64, true); err != nil {
			return nil, ReviewerCensusUnconfigured
		}
	}
	required := append([]string{}, reviewerRequiredReserveProducers...)
	required = append(required, cfg.RequiredProducerIDs...)
	sort.Strings(required)
	unique := make([]string, 0, len(required))
	for _, id := range required {
		if !reviewerReserveSourceID(id) {
			return nil, ReviewerCensusUnconfigured
		}
		if len(unique) == 0 || unique[len(unique)-1] != id {
			unique = append(unique, id)
		}
	}
	if len(unique) > 64 {
		return nil, ReviewerCensusUnconfigured
	}
	// Keep the trusted identities immutable if the caller reuses its config slices.
	cfg.Authority.AccountingReviewerKey = append(ed25519.PublicKey{}, cfg.Authority.AccountingReviewerKey...)
	cfg.Authority.CustodyReviewerKey = append(ed25519.PublicKey{}, cfg.Authority.CustodyReviewerKey...)
	cfg.Authority.ExecutionAuthorityKey = append(ed25519.PublicKey{}, cfg.Authority.ExecutionAuthorityKey...)
	cfg.Authority.WagerApprovalKey = append(ed25519.PublicKey{}, cfg.Authority.WagerApprovalKey...)
	cfg.Authority.WithdrawalApprovalKey = append(ed25519.PublicKey{}, cfg.Authority.WithdrawalApprovalKey...)
	cfg.FeeSources.WagerApprovalKey = append(ed25519.PublicKey{}, cfg.FeeSources.WagerApprovalKey...)
	cfg.RequiredProducerIDs = append([]string{}, cfg.RequiredProducerIDs...)
	return &ReviewerReserveCensusSource{base, custody, coverage, cfg, unique, time.Now}, nil
}

func reviewerReserveSourceID(s string) bool {
	if len(s) < 1 || len(s) > 128 {
		return false
	}
	for _, c := range s {
		if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.') {
			return false
		}
	}
	return true
}
func reviewerReserveEconomicKey(s string) bool {
	return len(s) > 0 && len(s) <= 160 && reviewerOperationID.MatchString(s)
}

// These domain-separated canonical digests are reproducible review inputs,
// never proof of source completeness or permission to sign/broadcast.
func ReviewerReserveCensusBodyDigest(body ReviewerReserveCensusBody) string {
	return hashJSON([]any{reviewerReserveCensusScope, body})
}
func ReviewerReserveNonOverlapDigest(items []ReviewerReserveNonOverlap) string {
	return hashJSON([]any{"aoe2war/satchel/reviewer-fee-nonoverlap/v1", items})
}
func ReviewerOwnerLedgerCheckpointDigest(o ReviewerFinanceObservation) (string, error) {
	if _, err := o.ledger.total(); err != nil {
		return "", err
	}
	r := o.ledger
	return hashJSON([]any{"aoe2war/satchel/reconciled-vault-ledger-total/v1", r.owners, r.available, r.reserved, r.committed, r.withdrawing, r.revisions, r.entries}), nil
}
func ReviewerPendingFeeCheckpointDigest(issued ReviewerIssuedFeeCheckpoint, custody ReviewerCustodyFeeCheckpoint, fees []ReviewerPendingFee) string {
	return hashJSON([]any{"aoe2war/satchel/pending-fee-sources/v1", custody.JournalDigest, custody.PolicyDigest, custody.WagerApprovalKeyFingerprint,
		issued.JournalDigest, issued.PolicyDigest, issued.ApprovalKeyFingerprint, fees})
}

// Lookup batches are bounded by the existing private API. Every batch must
// describe precisely the same journal, policy and unresolved fee inventory.
func (s *ReviewerReserveCensusSource) readCustody(ctx context.Context, issued ReviewerIssuedFeeCheckpoint, proposed string) (ReviewerCustodyFeeCheckpoint, error) {
	ids := make([]string, 0, len(issued.PendingFees)+1)
	seen := map[string]bool{proposed: true}
	ids = append(ids, proposed)
	for _, fee := range issued.PendingFees {
		if !seen[fee.OperationID] {
			ids = append(ids, fee.OperationID)
			seen[fee.OperationID] = true
		}
	}
	if len(ids) > reviewerMaxPendingOperations+1 {
		return ReviewerCustodyFeeCheckpoint{}, ReviewerCensusSourceInvalid
	}
	sort.Strings(ids)
	var out ReviewerCustodyFeeCheckpoint
	baseline := ""
	for start := 0; start < len(ids); start += custodyFeeCheckpointMaxIDs {
		end := start + custodyFeeCheckpointMaxIDs
		if end > len(ids) {
			end = len(ids)
		}
		cp, err := s.custody.ReadReviewerCustodyFees(ctx, ids[start:end])
		if err != nil || ctx.Err() != nil {
			return ReviewerCustodyFeeCheckpoint{}, ReviewerCensusSourceInvalid
		}
		if len(cp.AccountedOperations) != end-start || len(cp.AccountedFingerprints) != end-start {
			return ReviewerCustodyFeeCheckpoint{}, ReviewerCensusSourceInvalid
		}
		current := hashJSON([]any{cp.Protocol, cp.Kind, cp.ChainID, cp.Denom, cp.Vault, cp.JournalDigest, cp.PolicyDigest, cp.WagerApprovalKeyFingerprint, cp.UnresolvedFees})
		if baseline == "" {
			baseline = current
			out = cp
			out.AccountedOperations = map[string]string{}
			out.AccountedFingerprints = map[string]string{}
		} else if baseline != current {
			return ReviewerCustodyFeeCheckpoint{}, ReviewerCensusSnapshotChanged
		}
		if cp.ObservedAtMS < out.ObservedAtMS {
			out.ObservedAtMS = cp.ObservedAtMS
		}
		for _, id := range ids[start:end] {
			status, ok := cp.AccountedOperations[id]
			fp, has := cp.AccountedFingerprints[id]
			if !ok || !has {
				return ReviewerCustodyFeeCheckpoint{}, ReviewerCensusSourceInvalid
			}
			out.AccountedOperations[id], out.AccountedFingerprints[id] = status, fp
		}
	}
	return out, nil
}

func decodeReviewerReserveBundle(raw []byte) (ReviewerReserveCensusBundle, error) {
	var bundle ReviewerReserveCensusBundle
	if len(raw) == 0 || len(raw) > reviewerReserveCensusMaxBytes || !utf8.Valid(raw) || !chainjson.ValidFolded(raw) || strictHTTPJSON(raw, &bundle) != nil || bundle.Version != 1 {
		return bundle, ReviewerCensusCoverageInvalid
	}
	return bundle, nil
}

func (s *ReviewerReserveCensusSource) AuthenticatedFeeCensus(ctx context.Context, proposed WagerReservation) (ReviewerFeeCensus, error) {
	none := ReviewerFeeCensus{}
	if s == nil || s.ReviewerFinanceSource == nil || s.pg == nil || s.pg.db == nil || s.bank == nil || s.ReviewerEvidenceSource == nil || s.custody == nil || s.coverage == nil || s.now == nil || ctx == nil || ctx.Err() != nil {
		return none, ReviewerCensusUnconfigured
	}
	started, initial := time.Now(), s.now()
	completed := func() time.Time {
		now := s.now()
		if floor := initial.Add(time.Since(started)); floor.After(now) {
			now = floor
		}
		return now
	}
	issued, err := reviewerIssuedFeesFromContext(ctx)
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	if !validReviewerFeeProposal(proposed, s.config.Authority.ExpectedVault) || proposed.FeeUWolo != s.config.FeeUWolo {
		return none, ReviewerCensusCoverageInvalid
	}
	raw, err := s.coverage.ReadReviewerReserveCoverage(ctx)
	if err != nil {
		return none, ReviewerCensusCoverageInvalid
	}
	bundle, err := decodeReviewerReserveBundle(raw)
	if err != nil {
		return none, err
	}
	custody, err := s.readCustody(ctx, issued, proposed.OperationID)
	if err != nil {
		return none, err
	}
	observation, err := s.ObserveFinance(ctx, bundle.Review.StateHeight)
	if err != nil {
		return none, ReviewerCensusBankInvalid
	}
	fees, err := MergeReviewerPendingFees(proposed, issued, custody, s.config.FeeSources, completed())
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	principalPartitions, err := s.readPrincipalPartition(ctx, proposed)
	if err != nil {
		return none, err
	}
	census, err := s.verifyCoverage(bundle, proposed, observation, issued, custody, fees, completed(), principalPartitions...)
	if err != nil {
		return none, err
	}
	// Re-read independent mutable evidence after verification. Approval remains
	// unavailable if the ledger, custody journal or protected review changed.
	again, err := s.readCustody(ctx, issued, proposed.OperationID)
	if err != nil {
		return none, err
	}
	if hashJSON(custody.UnresolvedFees) != hashJSON(again.UnresolvedFees) || custody.JournalDigest != again.JournalDigest || custody.PolicyDigest != again.PolicyDigest ||
		hashJSON(custody.AccountedOperations) != hashJSON(again.AccountedOperations) || hashJSON(custody.AccountedFingerprints) != hashJSON(again.AccountedFingerprints) ||
		custody.WagerApprovalKeyFingerprint != again.WagerApprovalKeyFingerprint {
		return none, ReviewerCensusSnapshotChanged
	}
	row, err := s.pg.readOwnerLedger(ctx)
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	freshObservation := observation
	freshObservation.ledger = row
	oldLedger, _ := ReviewerOwnerLedgerCheckpointDigest(observation)
	newLedger, _ := ReviewerOwnerLedgerCheckpointDigest(freshObservation)
	reread, err := s.coverage.ReadReviewerReserveCoverage(ctx)
	if err != nil || !bytes.Equal(raw, reread) || oldLedger != newLedger || ctx.Err() != nil || !freshObservation.FreshAt(completed()) || !freshObservation.bank.CurrentAt(completed()) {
		return none, ReviewerCensusSnapshotChanged
	}
	finalPartitions, err := s.readPrincipalPartition(ctx, proposed)
	if err != nil {
		return none, err
	}
	if err = s.verifyPrincipalSpendBinding(bundle.Body, proposed, newLedger, again.JournalDigest, completed(), finalPartitions...); err != nil {
		return none, err
	}
	if !freshObservation.FreshAt(completed()) || !freshObservation.bank.CurrentAt(completed()) || ctx.Err() != nil {
		return none, ReviewerCensusSnapshotChanged
	}
	finalFees, err := MergeReviewerPendingFees(proposed, issued, again, s.config.FeeSources, completed())
	if err != nil || hashJSON(finalFees) != hashJSON(fees) {
		return none, ReviewerCensusSourceInvalid
	}
	if _, err := EvaluateProofBoundReserveReview(completed(), freshObservation.bank, bundle.Review, s.config.Authority); err != nil {
		return none, ReviewerCensusBankInvalid
	}
	return census, nil
}

func (s *ReviewerReserveCensusSource) verifyCoverage(bundle ReviewerReserveCensusBundle, proposed WagerReservation, observed ReviewerFinanceObservation, issued ReviewerIssuedFeeCheckpoint, custody ReviewerCustodyFeeCheckpoint, fees []ReviewerPendingFee, now time.Time, principalPartitions ...VerifiedReviewerPrincipalPartition) (ReviewerFeeCensus, error) {
	none := ReviewerFeeCensus{}
	body := bundle.Body
	review := bundle.Review
	owner, err := observed.KnownOwnerLiabilitiesUWolo()
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	ownerHash, err := ReviewerOwnerLedgerCheckpointDigest(observed)
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	if err = s.verifyPrincipalSpendBinding(body, proposed, ownerHash, custody.JournalDigest, now, principalPartitions...); err != nil {
		return none, err
	}
	ownerAmount, err := reviewerAmount(owner, math.MaxInt64, false)
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	principal, err := reviewerAmount(proposed.AmountUWolo, math.MaxInt64, true)
	if err != nil || ownerAmount < principal {
		return none, ReviewerCensusCoverageInvalid
	}
	if body.Protocol != 1 || body.Scope != reviewerReserveCensusScope || body.Vault != s.config.Authority.ExpectedVault || body.OperationID != proposed.OperationID ||
		body.ProposedFingerprint != reviewerFingerprint(proposed) || body.BookedPrincipalUWolo != proposed.AmountUWolo || body.OwnerLedgerSHA256 != ownerHash ||
		body.CustodyJournalSHA256 != custody.JournalDigest || body.IssuerJournalSHA256 != issued.JournalDigest || review.JournalSnapshotSHA256 != custody.JournalDigest ||
		review.LiabilityInventorySHA256 != ReviewerReserveCensusBodyDigest(body) || review.NonOverlapWitnessSHA256 != ReviewerReserveNonOverlapDigest(body.NonOverlap) ||
		len(body.Producers) != len(s.required) || body.Producers == nil || body.NonOverlap == nil {
		return none, ReviewerCensusCoverageInvalid
	}
	assignments := map[string]string{}
	var confirmed, unknown, pending uint64
	allFees := make([]ReviewerPendingFee, 0)
	expectedFees := hashJSON(fees)
	pendingSource := ReviewerPendingFeeCheckpointDigest(issued, custody, fees)
	for i, producer := range body.Producers {
		if producer.ProducerID != s.required[i] || !validReserveDigest(producer.CheckpointSHA256) || producer.Obligations == nil || producer.PendingFees == nil {
			return none, ReviewerCensusCoverageInvalid
		}
		previous := ""
		for _, obligation := range producer.Obligations {
			if !reviewerReserveEconomicKey(obligation.EconomicKey) || strings.HasPrefix(obligation.EconomicKey, "fee:") || obligation.EconomicKey <= previous || assignments[obligation.EconomicKey] != "" {
				return none, ReviewerCensusCoverageInvalid
			}
			previous = obligation.EconomicKey
			assignments[obligation.EconomicKey] = producer.ProducerID
			amount, err := reviewerAmount(obligation.AmountUWolo, math.MaxInt64, false)
			if err != nil {
				return none, ReviewerCensusCoverageInvalid
			}
			switch obligation.Kind {
			case "confirmed":
				confirmed, err = reviewerAdd(confirmed, amount)
			case "unknown":
				unknown, err = reviewerAdd(unknown, amount)
			default:
				return none, ReviewerCensusCoverageInvalid
			}
			if err != nil {
				return none, ReviewerCensusCoverageInvalid
			}
		}
		parsed, err := reviewerFeeList(producer.PendingFees, false)
		if err != nil {
			return none, ReviewerCensusCoverageInvalid
		}
		for id, fee := range parsed {
			key := "fee:" + id
			if assignments[key] != "" || id == proposed.OperationID {
				return none, ReviewerCensusCoverageInvalid
			}
			assignments[key] = producer.ProducerID
			if len(allFees) >= reviewerMaxPendingOperations {
				return none, ReviewerCensusCoverageInvalid
			}
			allFees = append(allFees, fee)
			amount, _ := reviewerAmount(fee.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
			pending, err = reviewerAdd(pending, amount)
			if err != nil {
				return none, ReviewerCensusCoverageInvalid
			}
		}
		switch producer.ProducerID {
		case reviewerOwnerLedgerProducer:
			if producer.CheckpointSHA256 != ownerHash || len(producer.Obligations) != 1 || len(producer.PendingFees) != 0 || producer.Obligations[0] != (ReviewerReserveObligation{"vault-owner-liabilities", "confirmed", owner}) {
				return none, ReviewerCensusCoverageInvalid
			}
		case reviewerPendingFeesProducer:
			if producer.CheckpointSHA256 != pendingSource || len(producer.Obligations) != 0 || hashJSON(producer.PendingFees) != expectedFees {
				return none, ReviewerCensusCoverageInvalid
			}
		}
	}
	if len(body.NonOverlap) != len(assignments) {
		return none, ReviewerCensusCoverageInvalid
	}
	previous := ""
	for _, item := range body.NonOverlap {
		producer, exists := assignments[item.EconomicKey]
		if !exists || item.EconomicKey <= previous || producer != item.ProducerID {
			return none, ReviewerCensusCoverageInvalid
		}
		previous = item.EconomicKey
	}
	if review.ConfirmedLiabilitiesUWolo != strconv.FormatUint(confirmed, 10) || review.UncertainMaxLiabilitiesUWolo != strconv.FormatUint(unknown, 10) || unknown == 0 {
		return none, ReviewerCensusCoverageInvalid
	}
	gas, err := reviewerAmount(review.GasReserveUWolo, math.MaxInt64, true)
	if err != nil {
		return none, ReviewerCensusCoverageInvalid
	}
	minimumGas, _ := reviewerAmount(s.config.MinimumGasReserveUWolo, math.MaxInt64, true)
	floor, err := reviewerAmount(review.UnencumberedMinimumUWolo, math.MaxInt64, true)
	if err != nil {
		return none, ReviewerCensusCoverageInvalid
	}
	minimumFloor, _ := reviewerAmount(s.config.MinimumUnencumberedUWolo, math.MaxInt64, true)
	fee, _ := reviewerAmount(proposed.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
	requiredGas, err := reviewerAdd(pending, fee)
	if err != nil || gas < requiredGas || gas < minimumGas || floor < minimumFloor {
		return none, ReviewerCensusCoverageInvalid
	}
	liabilities, err := reviewerAdd(confirmed, unknown)
	if err != nil {
		return none, ReviewerCensusCoverageInvalid
	}
	cushion, err := reviewerAdd(gas-requiredGas, floor)
	if err != nil {
		return none, ReviewerCensusCoverageInvalid
	}
	qualified, err := EvaluateProofBoundReserveReview(now, observed.bank, review, s.config.Authority)
	if err != nil || !qualified.Sufficient {
		return none, ReviewerCensusBankInvalid
	}
	sort.Slice(allFees, func(i, j int) bool { return allFees[i].OperationID < allFees[j].OperationID })
	result := ReviewerFeeCensus{ChainID: "wolo-1", Denom: "uwolo", OperationID: proposed.OperationID, BankBalanceUWolo: observed.bank.BalanceUWolo(), AllOwnerLiabilitiesUWolo: strconv.FormatUint(liabilities, 10),
		PendingOperations: allFees, NewOperationFeeUWolo: proposed.FeeUWolo, MinimumUnencumberedGasUWolo: strconv.FormatUint(cushion, 10), PendingOperationsComplete: true}
	budget, err := AssessReviewerFeeBudget(result, proposed)
	if err != nil || budget.Status != "BUDGET_SUFFICIENT_NONAUTHORIZING" {
		return none, ReviewerCensusCoverageInvalid
	}
	return result, nil
}

var _ ReviewerEvidenceSource = (*ReviewerReserveCensusSource)(nil)
