package satchelservice

// All keys, source enrollment and chain authority below are isolated fixtures.
// They do not establish a production operator, financial GO or user consent.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

type escrowServiceFixture struct {
	*escrowRuntimeFixture
	service    *EnrolledEscrowExecutor
	permit     EscrowReturnOperationPermit
	permitPath string
}

func newEscrowServiceFixture(t *testing.T) *escrowServiceFixture {
	t.Helper()
	f := &escrowServiceFixture{}
	f.escrowRuntimeFixture = newEscrowRuntimeFixtureWithConfig(t, func(c *Config) {
		dir := filepath.Join(filepath.Dir(c.StatePath), "enrolled-escrow-keyring")
		key := &sdksecp.PrivKey{Key: bytes.Repeat([]byte{9}, 32)}
		pass := nativeProductKeyring(t, dir, "protected-escrow-only", key)
		f.permitPath = filepath.Join(filepath.Dir(c.StatePath), "owner-escrow-operation.json")
		enrollment := EscrowSignerEnrollment{Version: 1, Scope: escrowSignerEnrollmentScope, SourceCommit: strings.Repeat("1", 40), PublicKeyHex: hex.EncodeToString(key.PubKey().Bytes()), KeyringDir: dir, KeyName: "protected-escrow-only", PassphraseFile: pass, OperationPermitFile: f.permitPath}
		c.EscrowSignerEnrollmentFile = filepath.Join(filepath.Dir(c.StatePath), "signer-enrollment.json")
		c.EscrowSignerEnrollmentSHA256 = custodySHA(custodyWrite(t, c.EscrowSignerEnrollmentFile, enrollment))
	})
	c := f.custody
	_, err := c.engine.PrepareReturnRun(t.Context(), f.approval)
	require.NoError(t, err)
	f.refresh(t) // fresh signed reserve against the actual post-prepare journal
	f.service, err = newEnrolledEscrowExecutor(c.issuer, func() (string, error) { return strings.Repeat("1", 40), nil })
	require.NoError(t, err)
	t.Cleanup(f.service.Close)
	f.service.native.signer = &custodyObservedSDKSigner{inner: f.service.native.signer, fixture: c}
	raw, err := os.ReadFile(f.reviewPath)
	require.NoError(t, err)
	f.permit = EscrowReturnOperationPermit{Version: 1, Scope: escrowOperationPermitScope, ChainID: "wolo-1", Denom: "uwolo", SourceCommit: strings.Repeat("1", 40),
		BinarySHA256: c.issuer.binaryDigest, ConfigSHA256: c.issuer.configDigest, EnrollmentSHA256: c.config.EscrowSignerEnrollmentSHA256,
		Vault: c.config.Vault, Escrow: c.config.BettingEscrow, ClaimID: f.approval.ClaimID, ApprovalSHA256: hashJSON(f.approval), ReserveReviewSHA256: custodySHA(raw), AmountUWolo: f.approval.AmountUWolo, FeeUWolo: c.config.FeesUWolo,
		Nonce: strings.Repeat("a", 64), IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Unix() + 60}
	f.writePermit(t)
	return f
}

func (f *escrowServiceFixture) writePermit(t *testing.T) {
	t.Helper()
	key := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, 32))
	f.permit.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(key, EscrowReturnOperationPermitMessage(f.permit)))
	custodyWrite(t, f.permitPath, f.permit)
}

type escrowServiceHTTP struct {
	*Engine
	executor *EnrolledEscrowExecutor
}

func (s *escrowServiceHTTP) ExecuteEnrolledClaimReturn(ctx context.Context, a ReturnApproval) (EscrowReturnSpendResult, error) {
	return s.executor.Execute(ctx, a)
}

func TestEscrowServiceActualSDKHTTPExecutionAndNativeReconciliation(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	h, err := NewHTTPHandler(&escrowServiceHTTP{Engine: c.engine, executor: f.service}, HTTPConfig{Token: testHTTPToken, Accepting: true,
		Authorize: func(context.Context) bool {
			return VerifyPermit(c.config, c.issuer.configDigest, c.issuer.binaryDigest)
		},
		Health: HTTPHealth{Accepting: true, VaultAddress: c.config.Vault, EscrowAddress: c.config.BettingEscrow, ExclusiveAuthorityVerified: true, BuildSHA256: c.issuer.binaryDigest, KeyFingerprint: custodySHA([]byte(c.config.PublicKeyHex))}})
	require.NoError(t, err)
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	raw, err := json.Marshal(f.approval)
	require.NoError(t, err)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/execute", string(raw)))
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var result EscrowReturnSpendResult
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &result))
	require.Equal(t, "UNKNOWN", result.Status)
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.Equal(t, before+1, c.chain.broadcasts)
	require.Equal(t, signs+1, c.SDKSigns.Load())
	receipt, err := c.engine.ReconcileReturn(t.Context(), f.approval, result.TxHash, c.reader)
	require.NoError(t, err)
	require.Equal(t, result.TxHash, receipt.TxHash)
	require.False(t, receipt.CreditAuthorized)
	// Replay remains an observation even after the exact owner permit is gone.
	require.NoError(t, os.Remove(f.permitPath))
	again, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, result, again)
	require.Equal(t, before+1, c.chain.broadcasts)
	require.Equal(t, signs+1, c.SDKSigns.Load())
	inspection := httptest.NewRecorder()
	h.ServeHTTP(inspection, testHTTPRequest(http.MethodGet, "/satchel/v1/returns/execution/101", ""))
	require.Equal(t, http.StatusOK, inspection.Code)
	var inspected EscrowReturnSpendResult
	require.NoError(t, json.Unmarshal(inspection.Body.Bytes(), &inspected))
	require.Equal(t, result, inspected)
	missing := httptest.NewRecorder()
	h.ServeHTTP(missing, testHTTPRequest(http.MethodGet, "/satchel/v1/returns/execution/102", ""))
	require.Equal(t, http.StatusNotFound, missing.Code, "absence remainsUNKNOWN; never permissiontoPOSTagain")
	changed := f.approval
	changed.AmountUWolo = "4000000"
	_, err = f.service.Execute(t.Context(), changed)
	require.Error(t, err)
}

func TestEscrowServiceSignedPermissionRefusalsDoNotSign(t *testing.T) {
	for _, mode := range []string{"missing", "forged", "expired", "owner", "source", "review", "fee", "nonce", "enrollment", "global_permit"} {
		t.Run(mode, func(t *testing.T) {
			f := newEscrowServiceFixture(t)
			c := f.custody
			switch mode {
			case "missing":
				require.NoError(t, os.Remove(f.permitPath))
			case "forged":
				f.permit.Signature = "invalid"
				custodyWrite(t, f.permitPath, f.permit)
			case "expired":
				f.permit.IssuedAt = time.Now().Unix() - 60
				f.permit.ExpiresAt = time.Now().Unix() - 1
				f.writePermit(t)
			case "owner":
				f.permit.ApprovalSHA256 = strings.Repeat("b", 64)
				f.writePermit(t)
			case "source":
				f.permit.SourceCommit = strings.Repeat("2", 40)
				f.writePermit(t)
			case "review":
				f.permit.ReserveReviewSHA256 = strings.Repeat("b", 64)
				f.writePermit(t)
			case "fee":
				f.permit.FeeUWolo = "0"
				f.writePermit(t)
			case "nonce":
				f.permit.Nonce = strings.Repeat("0", 64)
				f.writePermit(t)
			case "enrollment":
				require.NoError(t, os.WriteFile(c.config.EscrowSignerEnrollmentFile, []byte(`{}`), 0600))
			case "global_permit":
				require.NoError(t, os.Remove(c.config.PermitFile))
			}
			before, signs := c.chain.broadcasts, c.SDKSigns.Load()
			_, err := f.service.Execute(t.Context(), f.approval)
			require.Error(t, err)
			require.Equal(t, before, c.chain.broadcasts)
			require.Equal(t, signs, c.SDKSigns.Load())
		})
	}
}

func TestEscrowServiceSignedRevocationAfterSDKSigningPreservesUnknown(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	c.afterSign = func() { f.permit.Nonce = strings.Repeat("b", 64); f.writePermit(t) }
	result, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "signed_permit_revoked_unknown", result.Reason)
	require.NoError(t, c.engine.db.View(func(tx *bolt.Tx) error {
		var stored escrowReturnSpendRecord
		require.NoError(t, json.Unmarshal(tx.Bucket(escrowReturnSpendBucket).Get([]byte(f.approval.ClaimID)), &stored))
		require.Equal(t, stored.OperationPermitSHA256, custodySHA(stored.OperationPermitRaw))
		var original EscrowReturnOperationPermit
		require.NoError(t, json.Unmarshal(stored.OperationPermitRaw, &original))
		require.Equal(t, strings.Repeat("a", 64), original.Nonce)
		var reserve EscrowReturnExecutionBundle
		require.NoError(t, json.Unmarshal(stored.ReserveReviewRaw, &reserve))
		require.Equal(t, stored.ProofHash, hashJSON(reserve))
		return nil
	}))
	require.NotEmpty(t, result.TxHash)
	require.Equal(t, before, c.chain.broadcasts)
	require.Equal(t, signs+1, c.SDKSigns.Load())
	again, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, result, again)
	require.Equal(t, signs+1, c.SDKSigns.Load())
}

func TestEscrowServiceGlobalRevocationDuringFinalBankIOCannotSign(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	var once sync.Once
	errors := make(chan error, 1)
	hook := func() {
		if f.service.native.mu.TryLock() {
			f.service.native.mu.Unlock()
			return
		}
		// Only the SDK's last authorization callback owns this actual mutex.
		once.Do(func() { errors <- os.Remove(c.config.PermitFile) })
	}
	c.bankHook.Store(&hook)
	result, err := f.service.Execute(t.Context(), f.approval)
	c.bankHook.Store(nil)
	require.NoError(t, err)
	select {
	case err := <-errors:
		require.NoError(t, err)
	default:
		t.Fatal("final SDK bank-read revocation hook was not reached")
	}
	require.Equal(t, "UNKNOWN", result.Status)
	require.Equal(t, "signing_uncertain", result.Reason)
	require.Equal(t, signs, c.SDKSigns.Load(), "expired/revoked final bank read entered SDK signer")
	require.Equal(t, before, c.chain.broadcasts)
}

func (f *escrowServiceFixture) prepareSecondLeg(t *testing.T, uncertainFirst bool) ReturnApproval {
	t.Helper()
	writeReview := func() ReturnApproval {
		a, bank, proof, journal, bundle := f.reserve.bundle(t, "102")
		if uncertainFirst {
			bundle.Review.GasReserveUWolo = "1002500"
			for i := range bundle.Body.Producers {
				if bundle.Body.Producers[i].ProducerID == "all_signer_pending_uncertain_and_unmaterialized_fees" {
					bundle.Body.Producers[i].PendingFees = []ReviewerPendingFee{{OperationID: escrowReturnClaimKey("101"), Stage: "uncertain", FeeUWolo: "1000000"}}
				}
			}
		}
		raw := f.reserve.sign(t, &bundle)
		qualified, err := f.reserve.verifier.Verify(t.Context(), a, bank, proof, journal, raw)
		require.NoError(t, err, "second leg must have genuine current sufficient reserve qualification")
		require.True(t, qualified.CurrentFor(t.Context(), a))
		require.NoError(t, os.WriteFile(f.reviewPath, raw, 0600))
		return a
	}
	a := writeReview()
	_, err := f.custody.engine.PrepareReturnRun(t.Context(), a)
	require.NoError(t, err)
	a = writeReview() // original preparation changes the actual committed journal
	raw, err := os.ReadFile(f.reviewPath)
	require.NoError(t, err)
	f.permit.ClaimID, f.permit.ApprovalSHA256, f.permit.AmountUWolo = a.ClaimID, hashJSON(a), a.AmountUWolo
	f.permit.ReserveReviewSHA256 = custodySHA(raw)
	f.writePermit(t)
	return a
}

func TestEscrowServiceUnknownSequenceFencesOtherFundedLeg(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	c.afterSign = func() { require.NoError(t, os.Remove(f.permitPath)) }
	first, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "signed_permit_revoked_unknown", first.Reason)
	c.afterSign = nil
	f.permit.Nonce = strings.Repeat("b", 64)
	second := f.prepareSecondLeg(t, true)
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	_, err = f.service.Execute(t.Context(), second)
	require.Error(t, err)
	require.Equal(t, before, c.chain.broadcasts)
	require.Equal(t, signs, c.SDKSigns.Load())
	require.NoError(t, c.engine.db.View(func(tx *bolt.Tx) error {
		require.Nil(t, tx.Bucket(escrowReturnSpendBucket).Get([]byte("102")))
		return nil
	}))
}

func TestEscrowServiceConsumedNonceAndActualTwoLegConservation(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	first, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	_, err = c.engine.ReconcileReturn(t.Context(), f.approval, first.TxHash, c.reader)
	require.NoError(t, err)
	second := f.prepareSecondLeg(t, false)
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	_, err = f.service.Execute(t.Context(), second)
	require.Error(t, err, "even a paid claim permanently consumes its owner nonce")
	require.Equal(t, before, c.chain.broadcasts)
	require.Equal(t, signs, c.SDKSigns.Load())
	f.permit.Nonce = strings.Repeat("b", 64)
	f.writePermit(t)
	result, err := f.service.Execute(t.Context(), second)
	require.NoError(t, err)
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.Equal(t, before+1, c.chain.broadcasts)
	require.Equal(t, signs+1, c.SDKSigns.Load())
	receipt, err := c.engine.ReconcileReturn(t.Context(), second, result.TxHash, c.reader)
	require.NoError(t, err)
	require.False(t, receipt.CreditAuthorized)
	bank, _, err := c.reader.ReadCurrentBankProof(t.Context(), c.config.BettingEscrow)
	require.NoError(t, err)
	require.Equal(t, "1995000", bank.BalanceUWolo(), "9-WOLO escrow minus5+2-WOLO returns and both2500-uwolo native fees")
	journal := readTestCustodyJournal(t, c.engine)
	require.Equal(t, uint64(2), journal.ConfirmedReturnReceiptCount)
	require.Equal(t, "7000000", journal.ConfirmedReturnUWolo)
}

type interruptedEscrowSDKSigner struct{ inner backendSigner }

func (s interruptedEscrowSDKSigner) Sign(name string, data []byte, mode signing.SignMode) ([]byte, cryptotypes.PubKey, error) {
	// A real SDK signature was produced, but its acknowledgement is lost.
	_, _, err := s.inner.Sign(name, data, mode)
	if err != nil {
		return nil, nil, err
	}
	return nil, nil, ErrBackend
}

func TestEscrowServiceInterruptedSDKSigningRemainsHeldAcrossRestart(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	f.service.native.signer = interruptedEscrowSDKSigner{inner: f.service.native.signer}
	before, signs := c.chain.broadcasts, c.SDKSigns.Load()
	result, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "signing_uncertain", result.Reason)
	require.Empty(t, result.TxHash)
	require.Equal(t, signs+1, c.SDKSigns.Load())
	require.Equal(t, before, c.chain.broadcasts)
	f.service.Close()
	require.NoError(t, c.engine.Close())
	reopened, err := Open(c.config.StatePath, c.engine.policy, c.native)
	require.NoError(t, err)
	t.Cleanup(func() { _ = reopened.Close() })
	issuer, err := NewCustodyAuthority(reopened, c.native, c.reader, c.path, c.issuer.configDigest, c.issuer.binaryDigest)
	require.NoError(t, err)
	require.NoError(t, reopened.RequireCustodyAuthority(issuer))
	restarted, err := newEnrolledEscrowExecutor(issuer, func() (string, error) { return strings.Repeat("1", 40), nil })
	require.NoError(t, err)
	t.Cleanup(restarted.Close)
	restarted.native.signer = &custodyObservedSDKSigner{inner: restarted.native.signer, fixture: c}
	require.NoError(t, os.Remove(f.permitPath))
	again, err := restarted.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, result, again)
	require.Equal(t, signs+1, c.SDKSigns.Load(), "restart must never re-enter the SDK signer")
	require.Equal(t, before, c.chain.broadcasts)
}

func TestEscrowServiceJournalBudgetRefusesBeforeSigningAndPreservesHistory(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	require.NoError(t, c.engine.db.Update(func(tx *bolt.Tx) error {
		b, err := tx.CreateBucket([]byte("preserved-financial-evidence"))
		if err != nil {
			return err
		}
		return b.Put([]byte("bounded-original"), bytes.Repeat([]byte{1}, custodyJournalMaxBytes-(96<<10)))
	}))
	f.refresh(t)
	raw, err := os.ReadFile(f.reviewPath)
	require.NoError(t, err)
	f.permit.ReserveReviewSHA256 = custodySHA(raw)
	f.writePermit(t)
	before := readTestCustodyJournal(t, c.engine)
	broadcasts, signs := c.chain.broadcasts, c.SDKSigns.Load()
	_, err = f.service.Execute(t.Context(), f.approval)
	require.Error(t, err)
	require.Equal(t, before, readTestCustodyJournal(t, c.engine))
	require.Equal(t, broadcasts, c.chain.broadcasts)
	require.Equal(t, signs, c.SDKSigns.Load())
	_, err = c.engine.ReadEscrowReturnSpend(f.approval.ClaimID)
	require.Error(t, err)
}

func TestEscrowServiceCorruptRecoveryIdentityNeverEmitsCandidateOrResigns(t *testing.T) {
	f := newEscrowServiceFixture(t)
	c := f.custody
	_, err := f.service.Execute(t.Context(), f.approval)
	require.NoError(t, err)
	var original []byte
	require.NoError(t, c.engine.db.View(func(tx *bolt.Tx) error {
		original = append([]byte(nil), tx.Bucket(escrowReturnSpendBucket).Get([]byte(f.approval.ClaimID))...)
		return nil
	}))
	for _, mode := range []string{"version", "request", "result_hash", "signed_bytes", "nonce", "permit_bytes", "review_bytes"} {
		t.Run(mode, func(t *testing.T) {
			var state escrowReturnSpendRecord
			require.NoError(t, json.Unmarshal(original, &state))
			switch mode {
			case "version":
				state.Version = 0
			case "request":
				state.Request.OperationID = "satchel:claim-return:102"
			case "result_hash":
				state.Result.TxHash = strings.Repeat("A", 64)
			case "signed_bytes":
				state.Signed.Bytes[0] ^= 1
			case "nonce":
				state.OperationNonce = strings.Repeat("c", 64)
			case "permit_bytes":
				state.OperationPermitRaw[0] ^= 1
			case "review_bytes":
				state.ReserveReviewRaw[0] ^= 1
			}
			require.NoError(t, c.engine.db.Update(func(tx *bolt.Tx) error {
				return writeEscrowSpend(tx.Bucket(escrowReturnSpendBucket), []byte(f.approval.ClaimID), state)
			}))
			before, signs := c.chain.broadcasts, c.SDKSigns.Load()
			_, err := c.engine.ReadEscrowReturnSpend(f.approval.ClaimID)
			require.Error(t, err)
			_, err = f.service.Execute(t.Context(), f.approval)
			require.Error(t, err)
			require.Equal(t, before, c.chain.broadcasts)
			require.Equal(t, signs, c.SDKSigns.Load())
		})
	}
}
