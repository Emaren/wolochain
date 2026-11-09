package satchelservice

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/stretchr/testify/require"
)

func TestPortableReserveReviewNativeProof(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	_, proof, err := f.reader.ReadCurrentBankProof(t.Context(), f.config.Vault)
	require.NoError(t, err)
	pins := PortableReserveReviewAuthority{
		Version: 1, TrustAnchor: f.config.TrustAnchor, Vault: f.config.Vault,
		AccountingReviewerKeyHex:  f.config.AccountingReviewerKeyHex,
		CustodyReviewerKeyHex:     f.config.CustodyReviewerKeyHex,
		ActivationAuthorityKeyHex: f.config.ActivationAuthorityKeyHex,
		WagerApprovalKeyHex:       f.config.WagerApprovalKeyHex,
		WithdrawalApprovalKeyHex:  f.config.WithdrawalApprovalKeyHex,
		BuildSHA256:               f.review.BuildSHA256, ConfigSHA256: f.review.ConfigSHA256, PermitSHA256: f.review.PermitSHA256,
		LiabilityInventorySHA256: f.review.LiabilityInventorySHA256,
		JournalSnapshotSHA256:    f.review.JournalSnapshotSHA256,
		NonOverlapWitnessSHA256:  f.review.NonOverlapWitnessSHA256,
	}
	encode := func(t *testing.T, v any) []byte {
		t.Helper()
		out, err := json.Marshal(v)
		require.NoError(t, err)
		return out
	}
	authority, review, transcript := encode(t, pins), encode(t, f.review), encode(t, proof)
	receipt, err := VerifyPortableReserveReview(t.Context(), authority, review, transcript)
	require.NoError(t, err)
	require.Equal(t, "VERIFIED_RESERVE_REVIEW_NONAUTHORIZING", receipt.Status)
	require.Equal(t, custodySHA(authority), receipt.AuthoritySHA256)
	require.Equal(t, custodySHA(review), receipt.ReviewSHA256)
	require.Equal(t, custodySHA(transcript), receipt.BankProofSHA256)
	require.Equal(t, f.review.StateHeight, receipt.StateHeight)
	require.Equal(t, f.review.StateHeight+1, receipt.CommitHeight)
	require.True(t, strings.EqualFold(f.review.CommitBlockHash, receipt.CommitBlockHash))
	require.Equal(t, f.review.ExpiresAt, receipt.ExpiresAt.Unix())
	require.False(t, receipt.CreditAuthorized || receipt.SpendingAuthorized || receipt.SolvencyAuthorized)
	require.Zero(t, f.SDKSigns.Load())

	for name, mutate := range map[string]func(*PortableReserveReviewAuthority, *SignedReserveReview, *satchel.BankProof){
		"independent liability pin": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.LiabilityInventorySHA256 = strings.Repeat("a", 64)
		},
		"independent journal pin": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.JournalSnapshotSHA256 = strings.Repeat("b", 64)
		},
		"independent overlap pin": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.NonOverlapWitnessSHA256 = strings.Repeat("c", 64)
		},
		"changed permit pin": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.PermitSHA256 = strings.Repeat("d", 64)
		},
		"invalid trusted anchor": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.TrustAnchor.Hash = strings.Repeat("e", 64)
		},
		"duplicate reviewer authority": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.CustodyReviewerKeyHex = p.AccountingReviewerKeyHex
		},
		"invalid encoded key suffix": func(p *PortableReserveReviewAuthority, _ *SignedReserveReview, _ *satchel.BankProof) {
			p.CustodyReviewerKeyHex += "zz"
		},
		"wrong authenticated height": func(_ *PortableReserveReviewAuthority, r *SignedReserveReview, _ *satchel.BankProof) {
			r.StateHeight++
			signReview(r, f.accounting, f.custody)
		},
		"insufficient coverage with valid signatures": func(_ *PortableReserveReviewAuthority, r *SignedReserveReview, _ *satchel.BankProof) {
			r.ConfirmedLiabilitiesUWolo = r.ObservedBankUWolo
			signReview(r, f.accounting, f.custody)
		},
		"expired review with valid signatures": func(_ *PortableReserveReviewAuthority, r *SignedReserveReview, _ *satchel.BankProof) {
			r.IssuedAt, r.ExpiresAt = time.Now().Unix()-30, time.Now().Unix()-1
			signReview(r, f.accounting, f.custody)
		},
		"forged review": func(_ *PortableReserveReviewAuthority, r *SignedReserveReview, _ *satchel.BankProof) {
			r.CustodyReviewerSignature = r.AccountingReviewerSignature
		},
		"duplicate bank proof response": func(_ *PortableReserveReviewAuthority, _ *SignedReserveReview, b *satchel.BankProof) {
			b.Responses = append(b.Responses, b.Responses[0])
		},
	} {
		t.Run(name, func(t *testing.T) {
			p, r, b := pins, f.review, proof
			mutate(&p, &r, &b)
			receipt, err := VerifyPortableReserveReview(t.Context(), encode(t, p), encode(t, r), encode(t, b))
			require.Error(t, err)
			require.Zero(t, receipt)
		})
	}

	t.Run("duplicate review field", func(t *testing.T) {
		duplicate := append([]byte(`{"Version":1,`), review[1:]...)
		receipt, err := VerifyPortableReserveReview(t.Context(), authority, duplicate, transcript)
		require.Error(t, err)
		require.Zero(t, receipt)
	})
}
