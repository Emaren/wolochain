package satchelservice

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func (s *escrowServiceHTTP) CheckEnrolledClaimReturn(ctx context.Context, a ReturnApproval) (EscrowReturnExecutionCheck, error) {
	return s.executor.CheckExecution(ctx, a)
}

func TestEscrowCheckNativeReadOnlyAndExecutionRevalidatesPermission(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	before := readTestCustodyJournal(t, c.engine)
	signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
	checked, err := f.service.CheckExecution(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "escrow_return_execution_check", checked.Kind)
	require.Equal(t, f.approval, checked.Approval)
	require.Equal(t, f.bundle.Review.StateHeight, checked.StateHeight)
	require.Equal(t, checked.StateHeight+1, checked.CommitHeight)
	require.Equal(t, f.bundle.Review.CommitBlockHash, checked.CommitBlockHash)
	require.Equal(t, f.permit.ReserveReviewSHA256, checked.ReserveReviewSHA256)
	require.Greater(t, checked.ExpiresAt, time.Now().Unix())
	require.False(t, checked.ExecutionAuthorized)
	require.False(t, checked.CreditAuthorized)
	require.Equal(t, before, readTestCustodyJournal(t, c.engine))
	require.Equal(t, signs, c.SDKSigns.Load())
	require.Equal(t, broadcasts, c.chain.broadcasts)
	_, err = c.engine.ReadEscrowReturnSpend(f.approval.ClaimID)
	require.ErrorIs(t, err, ErrEscrowReturnSpend)
	// A successful observation cannot survive revocation or become execution
	// permission. The actual signer reopens and verifies the protected files.
	require.NoError(t, os.Remove(f.permitPath))
	_, err = f.service.Execute(t.Context(), f.approval)
	require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
	require.Equal(t, before, readTestCustodyJournal(t, c.engine))
	require.Equal(t, signs, c.SDKSigns.Load())
	f.writePermit(t)
	result, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.Equal(t, broadcasts+1, c.chain.broadcasts)
	_, err = f.service.CheckExecution(t.Context(), f.approval)
	require.ErrorIs(t, err, ErrEscrowRuntimeHeld, "consumed claims are read-only recovery, never new admission")
}

func TestEscrowCheckNativeRejectsInvalidReviewPermissionAndFinalRevocation(t *testing.T) {
	for _, mode := range []string{"expired_permission", "forged_review_root", "review_outlives_bank", "final_io_revocation"} {
		t.Run(mode, func(t *testing.T) {
			f := newEscrowServiceFixture(t)
			c := f.custody
			switch mode {
			case "expired_permission":
				f.permit.IssuedAt, f.permit.ExpiresAt = time.Now().Unix()-60, time.Now().Unix()-1
				f.writePermit(t)
			case "forged_review_root", "review_outlives_bank":
				if mode == "forged_review_root" {
					f.bundle.Review.CommitBlockHash = strings.Repeat("F", 64)
				} else {
					bank, _, err := c.reader.ReadCurrentBankProof(t.Context(), c.config.BettingEscrow)
					require.NoError(t, err)
					f.bundle.Review.ExpiresAt = bank.ExpiresAt().Unix() + 1
				}
				raw := f.reserve.sign(t, &f.bundle)
				require.NoError(t, os.WriteFile(f.reviewPath, raw, 0600))
				f.permit.ReserveReviewSHA256 = custodySHA(raw)
				f.writePermit(t)
			case "final_io_revocation":
				hook := func() { c.bankHook.Store(nil); _ = os.Remove(f.permitPath) }
				c.bankHook.Store(&hook)
			}
			before := readTestCustodyJournal(t, c.engine)
			signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
			_, err := f.service.CheckExecution(t.Context(), f.approval)
			c.bankHook.Store(nil)
			require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
			require.Equal(t, before, readTestCustodyJournal(t, c.engine))
			require.Equal(t, signs, c.SDKSigns.Load())
			require.Equal(t, broadcasts, c.chain.broadcasts)
		})
	}
}

func TestEscrowCheckRetainsGlobalUnknownFenceAndConsumedNonce(t *testing.T) {
	for _, paid := range []bool{false, true} {
		t.Run(map[bool]string{false: "unknown", true: "paid_nonce"}[paid], func(t *testing.T) {
			f := newEscrowServiceFixture(t)
			c := f.custody
			if !paid {
				c.afterSign = func() { _ = os.Remove(f.permitPath) }
			}
			result, err := f.service.Execute(t.Context(), f.approval)
			require.NoError(t, err)
			c.afterSign = nil
			if paid {
				_, err = c.engine.ReconcileReturn(t.Context(), f.approval, result.TxHash, c.reader)
				require.NoError(t, err)
			}
			second := f.prepareSecondLeg(t, !paid)
			signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
			_, err = f.service.CheckExecution(t.Context(), second)
			require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
			require.Equal(t, signs, c.SDKSigns.Load())
			require.Equal(t, broadcasts, c.chain.broadcasts)
		})
	}
}

func TestEscrowCheckProtectedHTTPHasNoIntentOrExecutionEffect(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	h, err := NewHTTPHandler(&escrowServiceHTTP{Engine: c.engine, executor: f.service}, HTTPConfig{Token: testHTTPToken, Accepting: true,
		Authorize: func(context.Context) bool {
			return VerifyPermit(c.config, c.issuer.configDigest, c.issuer.binaryDigest)
		},
		Health: HTTPHealth{Accepting: true, VaultAddress: c.config.Vault, EscrowAddress: c.config.BettingEscrow, ExclusiveAuthorityVerified: true, BuildSHA256: c.issuer.binaryDigest, KeyFingerprint: custodySHA([]byte(c.config.PublicKeyHex))}})
	require.NoError(t, err)
	raw, err := json.Marshal(f.approval)
	require.NoError(t, err)
	before := readTestCustodyJournal(t, c.engine)
	signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/check-execution", string(raw)))
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var checked EscrowReturnExecutionCheck
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &checked))
	require.Equal(t, f.approval, checked.Approval)
	require.False(t, checked.ExecutionAuthorized)
	require.False(t, checked.CreditAuthorized)
	require.Equal(t, before, readTestCustodyJournal(t, c.engine))
	require.Equal(t, signs, c.SDKSigns.Load())
	require.Equal(t, broadcasts, c.chain.broadcasts)
}
