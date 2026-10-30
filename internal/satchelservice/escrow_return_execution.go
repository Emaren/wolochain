package satchelservice

// This verifier qualifies a current escrow reserve review. It neither signs a
// Cosmos transaction nor grants the legacy executor permission to spend. That
// executor must separately enforce its permit and the exact prepared return.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

const EscrowReturnExecutionScope = "aoe2war/satchel/escrow-return-execution/v1"
const escrowReturnExecutionMaxBytes = 2 << 20

var ErrEscrowReturnExecution = errors.New("escrow_return_execution_reserve_untrusted")

// Protected enrollment pins identify reviewed producers. Neither a source hash
// nor reviewer signatures independently discover omitted external liabilities
// or prove physical independence; external coverage remains their attestation.
type EscrowReturnProducerPin struct {
	ProducerID   string
	SourceSHA256 string
}

type EscrowReturnExecutionConfig struct {
	Authority                   ReserveReviewAuthority // ExpectedVault is the ESCROW role.
	TrustAnchor                 satchel.TrustAnchor
	PaidReturnProofReader       EscrowReturnPaidProofReader
	ExpectedCustodyPolicySHA256 string
	Producers                   []EscrowReturnProducerPin
	FeeUWolo                    string // Protected fee for this new return, never caller-selected.
	MaximumFeeUWolo             string // Existing conservative UNKNOWN ceiling: 1,000,000.
	MinimumGasReserveUWolo      string
	MinimumUnencumberedUWolo    string
}

// The configured native reader supplies transcripts, never authority. Every
// discharge is reverified against this verifier's protected anchor as well.
// *satchel.TrustedReader implements this read-only interface directly.
type EscrowReturnPaidProofReader interface {
	ReadTransferProof(context.Context, satchel.TransferIntent, string) (satchel.AuthenticatedEvidence, satchel.PortableProof, error)
}

type EscrowReturnExecutionProducer struct {
	ProducerID       string                      `json:"producer_id"`
	SourceSHA256     string                      `json:"source_sha256"`
	CheckpointSHA256 string                      `json:"checkpoint_sha256"`
	Obligations      []ReviewerReserveObligation `json:"obligations"`
	PendingFees      []ReviewerPendingFee        `json:"pending_fees"`
}

// Field order is the canonical Go JSON contract hashed below. Original bank
// evidence is allocation audit metadata; current bank identity is separately
// bound by SignedReserveReview and MUST NOT replace the original allocation.
type EscrowReturnExecutionBody struct {
	Protocol                   int                             `json:"protocol"`
	Scope                      string                          `json:"scope"`
	Escrow                     string                          `json:"escrow"`
	Vault                      string                          `json:"vault"`
	OperationID                string                          `json:"operation_id"`
	ClaimID                    string                          `json:"claim_id"`
	OwnerID                    string                          `json:"owner_id"`
	TicketID                   string                          `json:"ticket_id"`
	MarketID                   string                          `json:"market_id"`
	LegID                      string                          `json:"leg_id"`
	EntitlementID              string                          `json:"entitlement_id"`
	ClaimKind                  string                          `json:"claim_kind"`
	AmountUWolo                string                          `json:"amount_uwolo"`
	AllocationDigest           string                          `json:"allocation_digest"`
	OriginalBankEvidenceDigest string                          `json:"original_bank_evidence_digest"`
	FundsBudgetID              string                          `json:"funds_budget_id"`
	JournalSHA256              string                          `json:"journal_sha256"`
	PolicySHA256               string                          `json:"policy_sha256"`
	Producers                  []EscrowReturnExecutionProducer `json:"producers"`
	NonOverlap                 []ReviewerReserveNonOverlap     `json:"nonoverlap"`
}

type EscrowReturnExecutionBundle struct {
	Version int                       `json:"version"`
	Review  SignedReserveReview       `json:"review"`
	Body    EscrowReturnExecutionBody `json:"body"`
}

func EscrowReturnExecutionBodyDigest(body EscrowReturnExecutionBody) string {
	return hashJSON([]any{EscrowReturnExecutionScope, body})
}
func EscrowReturnExecutionNonOverlapDigest(items []ReviewerReserveNonOverlap) string {
	return hashJSON([]any{"aoe2war/satchel/escrow-return-nonoverlap/v1", items})
}

type EscrowReturnExecutionVerifier struct {
	engine *Engine
	config EscrowReturnExecutionConfig
	proof  *satchel.ProofVerifier
	now    func() time.Time
}

// All fields are private: JSON, an expired statement or a zero value cannot
// mint this result. It is a reserve qualification, not custody spend authority.
type VerifiedEscrowReturnExecution struct {
	engine                        *Engine
	claimFingerprint, journalHash string
	policyHash, bundleHash        string
	allocationDigest              string
	bank                          satchel.AuthenticatedBankEvidence
	expires                       time.Time
	now                           func() time.Time
}

func (v VerifiedEscrowReturnExecution) ExpiresAt() time.Time { return v.expires }

func NewEscrowReturnExecutionVerifier(e *Engine, cfg EscrowReturnExecutionConfig) (*EscrowReturnExecutionVerifier, error) {
	if e == nil || !validReviewAuthority(cfg.Authority) || cfg.Authority.ExpectedVault != e.policy.BettingEscrow ||
		!validAddress(cfg.Authority.ExpectedVault) || !validReserveDigest(cfg.ExpectedCustodyPolicySHA256) || cfg.ExpectedCustodyPolicySHA256 != hashJSON(e.policy) ||
		!bytes.Equal(cfg.Authority.WagerApprovalKey, e.policy.WagerApprovalKey) || !bytes.Equal(cfg.Authority.WithdrawalApprovalKey, e.policy.WithdrawalApprovalKey) ||
		cfg.MaximumFeeUWolo != strconv.Itoa(reviewerMaxOperationFeeUWolo) || len(cfg.Producers) < len(reviewerRequiredReserveProducers) || len(cfg.Producers) > 64 {
		return nil, ErrEscrowReturnExecution
	}
	for _, key := range []ed25519.PublicKey{cfg.Authority.AccountingReviewerKey, cfg.Authority.CustodyReviewerKey, cfg.Authority.ExecutionAuthorityKey, cfg.Authority.WagerApprovalKey, cfg.Authority.WithdrawalApprovalKey} {
		if bytesAllZero(key) {
			return nil, ErrEscrowReturnExecution
		}
	}
	if _, err := reviewerAmount(cfg.FeeUWolo, reviewerMaxOperationFeeUWolo, true); err != nil {
		return nil, ErrEscrowReturnExecution
	}
	for _, amount := range []string{cfg.MinimumGasReserveUWolo, cfg.MinimumUnencumberedUWolo} {
		if _, err := reviewerAmount(amount, math.MaxInt64, true); err != nil {
			return nil, ErrEscrowReturnExecution
		}
	}
	cfg.Producers = append([]EscrowReturnProducerPin{}, cfg.Producers...)
	sort.Slice(cfg.Producers, func(i, j int) bool { return cfg.Producers[i].ProducerID < cfg.Producers[j].ProducerID })
	enrolled := map[string]bool{}
	for _, pin := range cfg.Producers {
		if !reviewerReserveSourceID(pin.ProducerID) || !validReserveDigest(pin.SourceSHA256) || enrolled[pin.ProducerID] {
			return nil, ErrEscrowReturnExecution
		}
		enrolled[pin.ProducerID] = true
	}
	for _, required := range reviewerRequiredReserveProducers {
		if !enrolled[required] {
			return nil, ErrEscrowReturnExecution
		}
	}
	cfg.Authority.AccountingReviewerKey = append(ed25519.PublicKey{}, cfg.Authority.AccountingReviewerKey...)
	cfg.Authority.CustodyReviewerKey = append(ed25519.PublicKey{}, cfg.Authority.CustodyReviewerKey...)
	cfg.Authority.ExecutionAuthorityKey = append(ed25519.PublicKey{}, cfg.Authority.ExecutionAuthorityKey...)
	cfg.Authority.WagerApprovalKey = append(ed25519.PublicKey{}, cfg.Authority.WagerApprovalKey...)
	cfg.Authority.WithdrawalApprovalKey = append(ed25519.PublicKey{}, cfg.Authority.WithdrawalApprovalKey...)
	proof, err := satchel.NewProofVerifier(cfg.TrustAnchor)
	if err != nil {
		return nil, ErrEscrowReturnExecution
	}
	return &EscrowReturnExecutionVerifier{engine: e, config: cfg, proof: proof, now: time.Now}, nil
}

// Verify reauthenticates the transcript against the protected anchor, not a root
// supplied in the bundle. It validates the actual current journal and durable
// allocations/receipts. No signing, broadcast, reservation or DB write occurs.
func (v *EscrowReturnExecutionVerifier) Verify(ctx context.Context, a ReturnApproval, bank satchel.AuthenticatedBankEvidence, proof satchel.BankProof, journal CustodyJournal, raw []byte) (VerifiedEscrowReturnExecution, error) {
	if v == nil || v.engine == nil {
		return VerifiedEscrowReturnExecution{}, ErrEscrowReturnExecution
	}
	v.engine.mu.Lock()
	defer v.engine.mu.Unlock()
	return v.verifyLocked(ctx, a, bank, proof, journal, raw)
}

// Caller owns the same engine mutex through its subsequent prepare write. The
// future executor must enforce the exact prepared identity and its own permit.
func (v *EscrowReturnExecutionVerifier) verifyLocked(ctx context.Context, a ReturnApproval, bank satchel.AuthenticatedBankEvidence, proof satchel.BankProof, expectedJournal CustodyJournal, raw []byte) (VerifiedEscrowReturnExecution, error) {
	none := VerifiedEscrowReturnExecution{}
	if v == nil || v.engine == nil || v.engine.db == nil || v.proof == nil || v.now == nil || ctx == nil || ctx.Err() != nil || len(raw) == 0 || len(raw) > escrowReturnExecutionMaxBytes || !utf8.Valid(raw) || !chainjson.ValidFolded(raw) {
		return none, ErrEscrowReturnExecution
	}
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	var bundle EscrowReturnExecutionBundle
	if strictHTTPJSON(raw, &bundle) != nil || bundle.Version != 1 {
		return none, ErrEscrowReturnExecution
	}
	current, err := v.proof.VerifyBankProof(ctx, v.config.Authority.ExpectedVault, bank.Height(), proof)
	if err != nil || !bank.CurrentAt(v.now()) || !current.CurrentAt(v.now()) || bank.VaultAddress() != current.VaultAddress() || bank.BalanceUWolo() != current.BalanceUWolo() ||
		bank.Height() != current.Height() || bank.BlockHash() != current.BlockHash() || bank.AppHash() != current.AppHash() || current.HeadTime().After(v.now()) || ctx.Err() != nil {
		return none, ErrEscrowReturnExecution
	}
	e := v.engine
	var actual CustodyJournal
	var obligations map[string]ReviewerReserveObligation
	var pending map[string]ReviewerPendingFee
	err = e.db.View(func(tx *bolt.Tx) error {
		var err error
		actual, err = e.custodyJournalTx(tx)
		if err != nil || hashJSON(actual) != hashJSON(expectedJournal) || actual.PolicyDigest != v.config.ExpectedCustodyPolicySHA256 || e.validateReturnAt(tx, a, true) != nil {
			return ErrEscrowReturnExecution
		}
		obligations, pending, err = v.obligationsTx(ctx, tx, a, current)
		return err
	})
	if err != nil || ctx.Err() != nil {
		return none, ErrEscrowReturnExecution
	}
	if err := v.verifyInventory(bundle, a, actual, obligations, pending, current, v.now()); err != nil {
		return none, ErrEscrowReturnExecution
	}
	// No retained statement survives a journal change or elapsed native/review
	// deadline during signature verification. Compare a new actual Bolt view.
	completed := v.now()
	if ctx.Err() != nil || !bank.CurrentAt(completed) || !current.CurrentAt(completed) || completed.Unix() < bundle.Review.IssuedAt || completed.Unix() >= bundle.Review.ExpiresAt {
		return none, ErrEscrowReturnExecution
	}
	if err := e.db.View(func(tx *bolt.Tx) error {
		again, err := e.custodyJournalTx(tx)
		if err != nil || hashJSON(again) != hashJSON(actual) || e.validateReturnAt(tx, a, true) != nil {
			return ErrEscrowReturnExecution
		}
		return nil
	}); err != nil || ctx.Err() != nil {
		return none, ErrEscrowReturnExecution
	}
	expires := time.Unix(bundle.Review.ExpiresAt, 0)
	for _, until := range []time.Time{current.ExpiresAt(), time.Unix(a.ExpiresAt, 0), time.Unix(a.Allocation.ExpiresAt, 0)} {
		if until.Before(expires) {
			expires = until
		}
	}
	if !v.now().Before(expires) || ctx.Err() != nil {
		return none, ErrEscrowReturnExecution
	}
	return VerifiedEscrowReturnExecution{engine: e, claimFingerprint: returnFingerprint(a), journalHash: actual.JournalDigest,
		policyHash: actual.PolicyDigest, bundleHash: hashJSON(bundle), allocationDigest: a.AllocationDigest, bank: current, expires: expires, now: v.now}, nil
}

func escrowReturnClaimKey(id string) string { return "satchel:claim-return:" + id }

// Independent local lower bound. The inventory may add externally reviewed
// liabilities; it may not omit or rewrite any durable unpaid entitlement.
func (v *EscrowReturnExecutionVerifier) obligationsTx(ctx context.Context, tx *bolt.Tx, selected ReturnApproval, bank satchel.AuthenticatedBankEvidence) (map[string]ReviewerReserveObligation, map[string]ReviewerPendingFee, error) {
	e := v.engine
	plans := map[string]ReturnAllocation{}
	if b := tx.Bucket(allocationBucket); b != nil {
		if err := b.ForEach(func(id, raw []byte) error {
			var state allocationState
			if raw == nil || len(plans) >= reviewerMaxPendingOperations || json.Unmarshal(raw, &state) != nil || state.Plan.OperationID != string(id) || state.Digest != AllocationDigest(state.Plan, e.policy) {
				return ErrEscrowReturnExecution
			}
			plans[string(id)] = state.Plan
			return nil
		}); err != nil {
			return nil, nil, err
		}
	}
	proposed := *selected.Allocation // validateReturnAt already authenticated and bounded it.
	if raw := tx.Bucket(meta).Get(fundsKey); raw != nil {
		var funds returnFundsState
		if json.Unmarshal(raw, &funds) != nil || funds.Identity != fundsIdentity(proposed, e.policy) {
			return nil, nil, ErrEscrowReturnExecution
		}
	}
	if old, exists := plans[selected.OperationID]; exists {
		switch {
		case proposed.Revision == old.Revision:
			if AllocationDigest(proposed, e.policy) != AllocationDigest(old, e.policy) {
				return nil, nil, ErrEscrowReturnExecution
			}
		case proposed.Revision > old.Revision:
			if !allocationsExtend(old, proposed, e.policy) {
				return nil, nil, ErrEscrowReturnExecution
			}
			plans[selected.OperationID] = proposed
		default:
			if !allocationsExtend(proposed, old, e.policy) {
				return nil, nil, ErrEscrowReturnExecution
			}
		}
	} else {
		plans[selected.OperationID] = proposed
	}
	obligations := map[string]ReviewerReserveObligation{}
	pending := map[string]ReviewerPendingFee{}
	seenClaims := map[string]bool{}
	for _, plan := range plans {
		if ctx.Err() != nil {
			return nil, nil, ErrEscrowReturnExecution
		}
		for _, leg := range plan.Legs {
			for _, entry := range leg.Entitlements {
				if seenClaims[entry.ClaimID] || len(seenClaims) >= reviewerMaxPendingOperations {
					return nil, nil, ErrEscrowReturnExecution
				}
				seenClaims[entry.ClaimID] = true
				expected := ReturnApproval{Version: 2, TicketID: plan.TicketID, MarketID: leg.MarketID, LegID: leg.LegID, EntitlementID: entry.EntitlementID,
					Allocation: &plan, OperationID: plan.OperationID, ClaimID: entry.ClaimID, OwnerID: plan.OwnerID, ClaimKind: entry.ClaimKind, AmountUWolo: entry.AmountUWolo}
				key := escrowReturnClaimKey(entry.ClaimID)
				var record returnRecord
				if b := tx.Bucket(returns); b != nil {
					if raw := b.Get([]byte(entry.ClaimID)); raw != nil {
						if json.Unmarshal(raw, &record) != nil || record.Fingerprint != returnFingerprint(expected) || record.Fingerprint != returnFingerprint(record.Approval) {
							return nil, nil, ErrEscrowReturnExecution
						}
						if record.Receipt != nil {
							if entry.ClaimID == selected.ClaimID || !validReturnReceipt(record, *record.Receipt) || record.Receipt.Height > bank.Height() ||
								string(tx.Bucket(effects).Get([]byte("wolo-1:"+record.Receipt.TxHash))) != "return:"+entry.ClaimID {
								return nil, nil, ErrEscrowReturnExecution
							}
							if !v.authenticatedPaidReturn(ctx, record, bank) {
								return nil, nil, ErrEscrowReturnExecution
							}
							continue // Only durable native-reconciled, globally consumed payment discharges this claim.
						}
						if entry.ClaimID != selected.ClaimID {
							pending[key] = ReviewerPendingFee{OperationID: key, Stage: "uncertain", FeeUWolo: v.config.MaximumFeeUWolo}
						}
					}
				}
				obligations[key] = ReviewerReserveObligation{EconomicKey: key, Kind: "confirmed", AmountUWolo: entry.AmountUWolo}
			}
		}
	}
	// Conservatively retain all actual unresolved custody fees too. Expiry is
	// not evidence that a signed or issued transaction cannot still consume gas.
	if err := tx.Bucket(operations).ForEach(func(id, _ []byte) error {
		r, err := load(tx, string(id))
		if err != nil {
			return ErrEscrowReturnExecution
		}
		switch r.Result.Status {
		case "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING":
			if len(pending) >= reviewerMaxPendingOperations {
				return ErrEscrowReturnExecution
			}
			fee, err := e.custodyUnresolvedFee(r)
			if err != nil {
				return err
			}
			stage := "prepared"
			if len(r.Signed.Bytes) > 0 {
				stage = "uncertain"
			}
			if _, exists := pending[string(id)]; exists {
				return ErrEscrowReturnExecution
			}
			pending[string(id)] = ReviewerPendingFee{OperationID: string(id), Stage: stage, FeeUWolo: fee}
		}
		return nil
	}); err != nil {
		return nil, nil, err
	}
	return obligations, pending, nil
}

func (v *EscrowReturnExecutionVerifier) authenticatedPaidReturn(ctx context.Context, record returnRecord, bank satchel.AuthenticatedBankEvidence) bool {
	if v.config.PaidReturnProofReader == nil || record.Receipt == nil || ctx.Err() != nil {
		return false
	}
	r := *record.Receipt
	intent := satchel.TransferIntent{Sender: v.engine.policy.BettingEscrow, Recipient: v.engine.policy.Vault, AmountUWolo: r.AmountUWolo,
		Memo: "aoe2war/satchel/claim-return/v1/" + r.ClaimID}
	_, proof, err := v.config.PaidReturnProofReader.ReadTransferProof(ctx, intent, r.TxHash)
	if err != nil || ctx.Err() != nil {
		return false
	}
	evidence, err := v.proof.VerifyTransferProof(ctx, intent, r.TxHash, proof)
	if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || ctx.Err() != nil {
		return false
	}
	o := evidence.Observation()
	return o.Height == r.Height && o.Height <= bank.Height() && o.BlockHash == r.BlockHash && evidence.Receipt().ID() == r.ReceiptID &&
		o.Head.Height == bank.CommitHeight() && o.IndependentHead.Height == bank.CommitHeight() &&
		strings.EqualFold(o.Head.BlockHash, bank.BlockHash()) && strings.EqualFold(o.IndependentHead.BlockHash, bank.BlockHash())
}

func (v *EscrowReturnExecutionVerifier) verifyInventory(bundle EscrowReturnExecutionBundle, a ReturnApproval, journal CustodyJournal, known map[string]ReviewerReserveObligation, knownFees map[string]ReviewerPendingFee, bank satchel.AuthenticatedBankEvidence, now time.Time) error {
	b, review := bundle.Body, bundle.Review
	if b.Protocol != 1 || b.Scope != EscrowReturnExecutionScope || b.Escrow != v.config.Authority.ExpectedVault || b.Vault != v.engine.policy.Vault ||
		b.OperationID != a.OperationID || b.ClaimID != a.ClaimID || b.OwnerID != a.OwnerID || b.TicketID != a.TicketID || b.MarketID != a.MarketID || b.LegID != a.LegID || b.EntitlementID != a.EntitlementID || b.ClaimKind != a.ClaimKind ||
		b.AmountUWolo != a.AmountUWolo || b.AllocationDigest != a.AllocationDigest || b.OriginalBankEvidenceDigest != a.Allocation.BankEvidenceDigest || b.FundsBudgetID != a.Allocation.FundsBudgetID ||
		b.JournalSHA256 != journal.JournalDigest || b.PolicySHA256 != journal.PolicyDigest || review.JournalSnapshotSHA256 != journal.JournalDigest ||
		review.LiabilityInventorySHA256 != EscrowReturnExecutionBodyDigest(b) || review.NonOverlapWitnessSHA256 != EscrowReturnExecutionNonOverlapDigest(b.NonOverlap) ||
		len(b.Producers) != len(v.config.Producers) || b.NonOverlap == nil || len(b.NonOverlap) > reviewerMaxPendingOperations*2 || review.IssuedAt > now.Unix() {
		return ErrEscrowReturnExecution
	}
	assignments := map[string]string{}
	allObligations := map[string]ReviewerReserveObligation{}
	allFees := map[string]ReviewerPendingFee{}
	var confirmed, unknown, pending uint64
	for i, p := range b.Producers {
		pin := v.config.Producers[i]
		if p.ProducerID != pin.ProducerID || p.SourceSHA256 != pin.SourceSHA256 || !validReserveDigest(p.CheckpointSHA256) || p.Obligations == nil || p.PendingFees == nil || len(p.Obligations) > reviewerMaxPendingOperations || len(p.PendingFees) > reviewerMaxPendingOperations {
			return ErrEscrowReturnExecution
		}
		previous := ""
		for _, obligation := range p.Obligations {
			if !reviewerReserveEconomicKey(obligation.EconomicKey) || strings.HasPrefix(obligation.EconomicKey, "fee:") || obligation.EconomicKey <= previous || assignments[obligation.EconomicKey] != "" || len(allObligations) >= reviewerMaxPendingOperations {
				return ErrEscrowReturnExecution
			}
			previous = obligation.EconomicKey
			amount, err := reviewerAmount(obligation.AmountUWolo, math.MaxInt64, false)
			if err != nil {
				return ErrEscrowReturnExecution
			}
			switch obligation.Kind {
			case "confirmed":
				confirmed, err = reviewerAdd(confirmed, amount)
			case "unknown":
				unknown, err = reviewerAdd(unknown, amount)
			default:
				return ErrEscrowReturnExecution
			}
			if err != nil {
				return ErrEscrowReturnExecution
			}
			assignments[obligation.EconomicKey], allObligations[obligation.EconomicKey] = p.ProducerID, obligation
		}
		parsed, err := escrowReturnPendingFees(p.PendingFees)
		if err != nil {
			return ErrEscrowReturnExecution
		}
		for id, fee := range parsed {
			key := "fee:" + id
			if id == escrowReturnClaimKey(a.ClaimID) || assignments[key] != "" || len(allFees) >= reviewerMaxPendingOperations {
				return ErrEscrowReturnExecution
			}
			amount, err := reviewerAmount(fee.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
			if err != nil {
				return ErrEscrowReturnExecution
			}
			pending, err = reviewerAdd(pending, amount)
			if err != nil {
				return ErrEscrowReturnExecution
			}
			assignments[key], allFees[id] = p.ProducerID, fee
		}
	}
	for key, obligation := range known {
		if allObligations[key] != obligation {
			return ErrEscrowReturnExecution
		}
	}
	if _, found := known[escrowReturnClaimKey(a.ClaimID)]; !found {
		return ErrEscrowReturnExecution
	}
	for id, fee := range knownFees {
		actual, found := allFees[id]
		need, _ := reviewerAmount(fee.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
		got, err := reviewerAmount(actual.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
		if !found || err != nil || actual.Stage != fee.Stage || got < need {
			return ErrEscrowReturnExecution
		}
	}
	if len(b.NonOverlap) != len(assignments) {
		return ErrEscrowReturnExecution
	}
	previous := ""
	for _, item := range b.NonOverlap {
		producer, exists := assignments[item.EconomicKey]
		if !exists || item.EconomicKey <= previous || producer != item.ProducerID {
			return ErrEscrowReturnExecution
		}
		previous = item.EconomicKey
	}
	if unknown == 0 || review.ConfirmedLiabilitiesUWolo != strconv.FormatUint(confirmed, 10) || review.UncertainMaxLiabilitiesUWolo != strconv.FormatUint(unknown, 10) {
		return ErrEscrowReturnExecution
	}
	gas, err := reviewerAmount(review.GasReserveUWolo, math.MaxInt64, true)
	if err != nil {
		return ErrEscrowReturnExecution
	}
	floor, err := reviewerAmount(review.UnencumberedMinimumUWolo, math.MaxInt64, true)
	if err != nil {
		return ErrEscrowReturnExecution
	}
	newFee, _ := reviewerAmount(v.config.FeeUWolo, reviewerMaxOperationFeeUWolo, true)
	requiredGas, err := reviewerAdd(pending, newFee)
	minGas, _ := reviewerAmount(v.config.MinimumGasReserveUWolo, math.MaxInt64, true)
	minFloor, _ := reviewerAmount(v.config.MinimumUnencumberedUWolo, math.MaxInt64, true)
	if err != nil || gas < requiredGas || gas < minGas || floor < minFloor {
		return ErrEscrowReturnExecution
	}
	qualified, err := EvaluateProofBoundReserveReview(now, bank, review, v.config.Authority)
	if err != nil || !qualified.Sufficient {
		return ErrEscrowReturnExecution
	}
	// The selected payout already appears once in confirmed liabilities. No
	// extra payout-principal/equity requirement is added to the bank equation.
	return nil
}

// The wager reviewer's fee parser intentionally accepts only wager/withdrawal
// IDs. Escrow execution additionally has claim-return and enrolled external
// producers. These are inventory identities, never executable instructions.
func escrowReturnPendingFees(fees []ReviewerPendingFee) (map[string]ReviewerPendingFee, error) {
	if len(fees) > reviewerMaxPendingOperations {
		return nil, ErrEscrowReturnExecution
	}
	out := make(map[string]ReviewerPendingFee, len(fees))
	previous := ""
	for _, fee := range fees {
		if !reviewerOperationID.MatchString(fee.OperationID) || fee.OperationID <= previous || (fee.Stage != "prepared" && fee.Stage != "uncertain") {
			return nil, ErrEscrowReturnExecution
		}
		if strings.HasPrefix(fee.OperationID, "satchel:claim-return:") && !claimIDs.MatchString(strings.TrimPrefix(fee.OperationID, "satchel:claim-return:")) {
			return nil, ErrEscrowReturnExecution
		}
		if _, err := reviewerAmount(fee.FeeUWolo, reviewerMaxOperationFeeUWolo, true); err != nil {
			return nil, ErrEscrowReturnExecution
		}
		out[fee.OperationID] = fee
		previous = fee.OperationID
	}
	return out, nil
}

// CurrentFor is a read-only completion check. The caller must still atomically
// enforce its exact prepared return and independent execution permit. This is
// deliberately unsuitable for constructing authority from a serialized DTO.
func (g VerifiedEscrowReturnExecution) CurrentFor(ctx context.Context, a ReturnApproval) bool {
	if g.engine == nil || g.now == nil || ctx == nil || ctx.Err() != nil {
		return false
	}
	now := g.now()
	if now.IsZero() || !now.Before(g.expires) || !g.bank.CurrentAt(now) || g.claimFingerprint != returnFingerprint(a) || g.allocationDigest != a.AllocationDigest || !validReserveDigest(g.bundleHash) {
		return false
	}
	e := g.engine
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.db != nil && e.db.View(func(tx *bolt.Tx) error {
		journal, err := e.custodyJournalTx(tx)
		if err != nil || journal.JournalDigest != g.journalHash || journal.PolicyDigest != g.policyHash || e.validateReturnAt(tx, a, true) != nil || ctx.Err() != nil {
			return ErrEscrowReturnExecution
		}
		return nil
	}) == nil
}
