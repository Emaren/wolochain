package satchelservice

// Runtime loading for the existing return preparer. Enrollment bytes are pinned
// by the exact custody configuration and permit; only the separately signed
// operation-specific reserve review may change between preparations.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"path/filepath"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
)

const escrowReturnEnrollmentScope = "aoe2war/satchel/escrow-return-enrollment/v1"

type escrowReturnRuntimeProducer struct {
	ProducerID   string `json:"producer_id"`
	SourceSHA256 string `json:"source_sha256"`
}

type escrowReturnRuntimeEnrollment struct {
	Version                  int                           `json:"version"`
	Scope                    string                        `json:"scope"`
	ReviewFile               string                        `json:"review_file"`
	Producers                []escrowReturnRuntimeProducer `json:"producers"`
	FeeUWolo                 string                        `json:"fee_uwolo"`
	MaximumFeeUWolo          string                        `json:"maximum_fee_uwolo"`
	MinimumGasReserveUWolo   string                        `json:"minimum_gas_reserve_uwolo"`
	MinimumUnencumberedUWolo string                        `json:"minimum_unencumbered_uwolo"`
}

// Caller holds the existing engine mutex until its preparation transaction.
// Missing provisioning refuses preparation, without affecting read-only return
// reconciliation or enabling the independently governed escrow executor.
func (a *CustodyAuthority) qualifyEscrowReturnLocked(ctx context.Context, approval ReturnApproval) (VerifiedEscrowReturnExecution, error) {
	none := VerifiedEscrowReturnExecution{}
	if a == nil || a.engine == nil || a.engine.custodyAuthority != a || a.reader == nil || ctx == nil || ctx.Err() != nil ||
		a.config.EscrowReturnExecutionFile == "" || !validReserveDigest(a.config.EscrowReturnExecutionSHA256) || !a.nativeLeaseHeld() {
		return none, ErrEscrowReturnExecution
	}
	permitDigest, permitExpiry, err := a.currentFiles(ctx)
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	enrollmentRaw, err := ReadPrivateFile(a.config.EscrowReturnExecutionFile, 64<<10)
	if err != nil || custodySHA(enrollmentRaw) != a.config.EscrowReturnExecutionSHA256 || !utf8.Valid(enrollmentRaw) || !chainjson.ValidFolded(enrollmentRaw) {
		return none, ErrEscrowReturnExecution
	}
	var enrollment escrowReturnRuntimeEnrollment
	if strictHTTPJSON(enrollmentRaw, &enrollment) != nil || enrollment.Version != 1 || enrollment.Scope != escrowReturnEnrollmentScope ||
		!filepath.IsAbs(enrollment.ReviewFile) || filepath.Clean(enrollment.ReviewFile) != enrollment.ReviewFile ||
		enrollment.ReviewFile == a.config.ReserveReviewFile || enrollment.ReviewFile == a.config.EscrowReturnExecutionFile {
		return none, ErrEscrowReturnExecution
	}
	public := func(encoded string) ed25519.PublicKey {
		decoded, _ := hex.DecodeString(encoded)
		return ed25519.PublicKey(decoded)
	}
	producers := make([]EscrowReturnProducerPin, len(enrollment.Producers))
	for i, pin := range enrollment.Producers {
		producers[i] = EscrowReturnProducerPin{ProducerID: pin.ProducerID, SourceSHA256: pin.SourceSHA256}
	}
	verifier, err := NewEscrowReturnExecutionVerifier(a.engine, EscrowReturnExecutionConfig{
		Authority: ReserveReviewAuthority{
			AccountingReviewerKey: public(a.config.AccountingReviewerKeyHex), CustodyReviewerKey: public(a.config.CustodyReviewerKeyHex),
			ExecutionAuthorityKey: public(a.config.ActivationAuthorityKeyHex), WagerApprovalKey: public(a.config.WagerApprovalKeyHex), WithdrawalApprovalKey: public(a.config.WithdrawalApprovalKeyHex),
			ExpectedVault: a.config.BettingEscrow, ExpectedBuildSHA256: a.binaryDigest, ExpectedConfigSHA256: a.configDigest, ExpectedPermitSHA256: permitDigest,
		}, TrustAnchor: a.config.TrustAnchor, ExpectedCustodyPolicySHA256: hashJSON(a.engine.policy), Producers: producers,
		FeeUWolo: enrollment.FeeUWolo, MaximumFeeUWolo: enrollment.MaximumFeeUWolo,
		MinimumGasReserveUWolo: enrollment.MinimumGasReserveUWolo, MinimumUnencumberedUWolo: enrollment.MinimumUnencumberedUWolo,
		PaidReturnProofReader: a.reader,
	})
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	review, err := readPrivateFileBounded(enrollment.ReviewFile, escrowReturnExecutionMaxBytes, escrowReturnExecutionMaxBytes)
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	bank, proof, err := a.reader.ReadCurrentBankProof(ctx, a.config.BettingEscrow)
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	journal, err := a.engine.custodyJournalLocked()
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	qualified, err := verifier.verifyLocked(ctx, approval, bank, proof, journal, review)
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	lateBank, lateProof, err := a.reader.ReadCurrentBankProof(ctx, a.config.BettingEscrow)
	if err != nil {
		return none, ErrEscrowReturnExecution
	}
	lateBank, err = verifier.proof.VerifyBankProof(ctx, a.config.BettingEscrow, lateBank.Height(), lateProof)
	if err != nil || lateBank.Height() != bank.Height() || lateBank.CommitHeight() != bank.CommitHeight() ||
		lateBank.BlockHash() != bank.BlockHash() || lateBank.AppHash() != bank.AppHash() || lateBank.BalanceUWolo() != bank.BalanceUWolo() {
		return none, ErrEscrowReturnExecution
	}
	// Revoke or replace any source during bank/proof I/O and this admission is
	// discarded. The engine mutex preserves the checked journal through prepare.
	finalPermit, finalExpiry, err := a.currentFiles(ctx)
	if err != nil || finalPermit != permitDigest || !finalExpiry.Equal(permitExpiry) {
		return none, ErrEscrowReturnExecution
	}
	again, err := ReadPrivateFile(a.config.EscrowReturnExecutionFile, 64<<10)
	if err != nil || !bytes.Equal(enrollmentRaw, again) {
		return none, ErrEscrowReturnExecution
	}
	again, err = readPrivateFileBounded(enrollment.ReviewFile, escrowReturnExecutionMaxBytes, escrowReturnExecutionMaxBytes)
	// Lease inspection can wait on the native signing mutex. Sample completion
	// only after it returns so that lock delay cannot preserve expired evidence.
	leaseHeld := a.nativeLeaseHeld()
	completed := time.Now()
	if err != nil || !bytes.Equal(review, again) || ctx.Err() != nil || !completed.Before(permitExpiry) || !completed.Before(qualified.expires) ||
		!qualified.bank.CurrentAt(completed) || !lateBank.CurrentAt(completed) || qualified.claimFingerprint != returnFingerprint(approval) ||
		qualified.allocationDigest != approval.AllocationDigest || !leaseHeld {
		return none, ErrEscrowReturnExecution
	}
	return qualified, nil
}
