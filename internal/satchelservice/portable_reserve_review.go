package satchelservice

import (
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"errors"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
)

// PortableReserveReviewAuthority contains public pins provisioned independently
// of a review or proof. The operator must authenticate the trust anchor and
// audited evidence before retaining this record on the verification host.
type PortableReserveReviewAuthority struct {
	Version                   int                 `json:"version"`
	TrustAnchor               satchel.TrustAnchor `json:"trust_anchor"`
	Vault                     string              `json:"vault"`
	AccountingReviewerKeyHex  string              `json:"accounting_reviewer_key_hex"`
	CustodyReviewerKeyHex     string              `json:"custody_reviewer_key_hex"`
	ActivationAuthorityKeyHex string              `json:"activation_authority_key_hex"`
	WagerApprovalKeyHex       string              `json:"wager_approval_key_hex"`
	WithdrawalApprovalKeyHex  string              `json:"withdrawal_approval_key_hex"`
	BuildSHA256               string              `json:"build_sha256"`
	ConfigSHA256              string              `json:"config_sha256"`
	PermitSHA256              string              `json:"permit_sha256"`
	LiabilityInventorySHA256  string              `json:"liability_inventory_sha256"`
	JournalSnapshotSHA256     string              `json:"journal_snapshot_sha256"`
	NonOverlapWitnessSHA256   string              `json:"nonoverlap_witness_sha256"`
}

// PortableReserveReviewReceipt is a read-only attestation of the supplied
// signed review and captured bank proof. It never contains customer records,
// collateral authorization, or any power to activate a financial operation.
type PortableReserveReviewReceipt struct {
	Version            int       `json:"version"`
	Status             string    `json:"status"`
	AuthoritySHA256    string    `json:"authority_sha256"`
	ReviewSHA256       string    `json:"review_sha256"`
	BankProofSHA256    string    `json:"bank_proof_sha256"`
	StateHeight        int64     `json:"state_height"`
	CommitHeight       int64     `json:"commit_height"`
	CommitBlockHash    string    `json:"commit_block_hash"`
	ExpiresAt          time.Time `json:"expires_at"`
	CreditAuthorized   bool      `json:"credit_authorized"`
	SpendingAuthorized bool      `json:"spending_authorized"`
	SolvencyAuthorized bool      `json:"solvency_authorized"`
}

// VerifyPortableReserveReview replays an untrusted native bank transcript
// against the protected authority's anchor and verifies both signatures,
// arithmetic, freshness, and independently retained evidence pins. It cannot
// establish whether those audited liabilities are complete or funds pledged.
func VerifyPortableReserveReview(ctx context.Context, authorityBytes, reviewBytes, bankProofBytes []byte) (PortableReserveReviewReceipt, error) {
	refuse := func() (PortableReserveReviewReceipt, error) {
		return PortableReserveReviewReceipt{}, errors.New("portable_reserve_review_unverifiable")
	}
	var pins PortableReserveReviewAuthority
	var review SignedReserveReview
	if ctx == nil || ctx.Err() != nil || len(authorityBytes) > 16<<10 || len(reviewBytes) > 16<<10 ||
		!chainjson.ValidFolded(authorityBytes) || strictHTTPJSON(authorityBytes, &pins) != nil ||
		!chainjson.ValidFolded(reviewBytes) || strictHTTPJSON(reviewBytes, &review) != nil {
		return refuse()
	}

	decodePublicKey := func(encoded string) ed25519.PublicKey {
		key, err := hex.DecodeString(encoded)
		if err != nil {
			return nil
		}
		return ed25519.PublicKey(key)
	}
	authority := ReserveReviewAuthority{
		AccountingReviewerKey: decodePublicKey(pins.AccountingReviewerKeyHex),
		CustodyReviewerKey:    decodePublicKey(pins.CustodyReviewerKeyHex),
		ExecutionAuthorityKey: decodePublicKey(pins.ActivationAuthorityKeyHex),
		WagerApprovalKey:      decodePublicKey(pins.WagerApprovalKeyHex),
		WithdrawalApprovalKey: decodePublicKey(pins.WithdrawalApprovalKeyHex),
		ExpectedVault:         pins.Vault,
		ExpectedBuildSHA256:   pins.BuildSHA256,
		ExpectedConfigSHA256:  pins.ConfigSHA256,
		ExpectedPermitSHA256:  pins.PermitSHA256,
	}
	if pins.Version != 1 || !validAddress(pins.Vault) || satchel.IsKnownRoleAddress(pins.Vault) ||
		!validReviewAuthority(authority) ||
		pins.LiabilityInventorySHA256 != review.LiabilityInventorySHA256 ||
		pins.JournalSnapshotSHA256 != review.JournalSnapshotSHA256 ||
		pins.NonOverlapWitnessSHA256 != review.NonOverlapWitnessSHA256 {
		return refuse()
	}
	proof, err := satchel.DecodeBankProof(bankProofBytes)
	if err != nil {
		return refuse()
	}
	verifier, err := satchel.NewProofVerifier(pins.TrustAnchor)
	if err != nil {
		return refuse()
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	bank, err := verifier.VerifyBankProof(ctx, pins.Vault, review.StateHeight, proof)
	if err != nil {
		return refuse()
	}
	qualified, err := EvaluateProofBoundReserveReview(time.Now(), bank, review, authority)
	if err != nil || !qualified.Sufficient || ctx.Err() != nil {
		return refuse()
	}
	return PortableReserveReviewReceipt{
		Version: 1, Status: "VERIFIED_RESERVE_REVIEW_NONAUTHORIZING",
		AuthoritySHA256: custodySHA(authorityBytes), ReviewSHA256: custodySHA(reviewBytes),
		BankProofSHA256: custodySHA(bankProofBytes), StateHeight: bank.Height(),
		CommitHeight: bank.CommitHeight(), CommitBlockHash: bank.BlockHash(),
		ExpiresAt: qualified.ExpiresAt.UTC(),
	}, nil
}
