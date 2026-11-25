package satchelservice

// These are isolated SDK authorities. No fixture establishes production
// reviewer independence, enrolls a real signer, or grants escrow execution.
import (
	"context"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"cosmossdk.io/collections"
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

type escrowRuntimeFixture struct {
	custody    *custodyAuthorityFixture
	reserve    *escrowExecutionFixture
	approval   ReturnApproval
	bundle     EscrowReturnExecutionBundle
	reviewPath string
}

func newEscrowRuntimeFixture(t *testing.T) *escrowRuntimeFixture {
	t.Helper()
	return newEscrowRuntimeFixtureWithConfig(t, nil)
}

func newEscrowRuntimeFixtureWithConfig(t *testing.T, provision func(*Config)) *escrowRuntimeFixture {
	t.Helper()
	f := &escrowRuntimeFixture{}
	var enrollment escrowReturnRuntimeEnrollment
	f.custody = newCustodyAuthorityFixtureWithConfig(t, func(c *Config) {
		dir := filepath.Dir(c.StatePath)
		f.reviewPath = filepath.Join(dir, "escrow-review.json")
		enrollment = escrowReturnRuntimeEnrollment{Version: 1, Scope: escrowReturnEnrollmentScope, ReviewFile: f.reviewPath,
			FeeUWolo: c.FeesUWolo, MaximumFeeUWolo: "1000000", MinimumGasReserveUWolo: "2500", MinimumUnencumberedUWolo: "1000"}
		for _, id := range reviewerRequiredReserveProducers {
			enrollment.Producers = append(enrollment.Producers, escrowReturnRuntimeProducer{ProducerID: id, SourceSHA256: hashJSON([]string{"isolated-runtime-producer", id})})
		}
		c.EscrowReturnExecutionFile = filepath.Join(dir, "escrow-enrollment.json")
		c.EscrowReturnExecutionSHA256 = custodySHA(custodyWrite(t, c.EscrowReturnExecutionFile, enrollment))
		if provision != nil {
			provision(c)
		}
	})
	c := f.custody
	c.chain.release()
	result, err := c.engine.Submit(t.Context(), c.request)
	require.NoError(t, err)
	require.Equal(t, "ACCEPTED", result.Status)
	result, err = c.engine.Reconcile(t.Context(), c.request.OperationID)
	require.NoError(t, err)
	require.Equal(t, "CONFIRMED", result.Status)
	// Actual additional SDK assets leave gas headroom above seven booked WOLO.
	escrowExecutionSDKSend(t, c.chain, c.fundingKey, c.config.BettingEscrow, "2000000", "isolated-runtime-headroom")
	escrow, err := sdk.GetFromBech32(c.config.BettingEscrow, "wolo")
	require.NoError(t, err)
	c.chain.bankKey, err = collections.EncodeKeyWithPrefix(banktypes.BalancesPrefix, collections.PairKeyCodec(sdk.AccAddressKey, collections.StringKey), collections.Join(sdk.AccAddress(escrow), "uwolo"))
	require.NoError(t, err)
	bank, _, err := c.reader.ReadCurrentBankProof(t.Context(), c.config.BettingEscrow)
	require.NoError(t, err)
	require.Equal(t, "9000000", bank.BalanceUWolo())
	at := time.Now().Unix()
	p := c.engine.policy
	plan := ReturnAllocation{Version: 2, AllocationID: "allocation:ticket:7", Revision: 1, OperationID: c.request.OperationID, OwnerID: c.request.OwnerID, TicketID: "7", FundingTxHash: result.TxHash,
		ReturnCapUWolo: "7000000", FundsBudgetID: "isolated-runtime-budget", FundsAvailableUWolo: "9000000", BankEvidenceDigest: strings.Repeat("E", 64), BankHeight: bank.Height(), BankBlockHash: bank.BlockHash(), IssuedAt: at - 1, ExpiresAt: at + 120,
		Legs: []ReturnLeg{
			{LegID: "desync", MarketID: "502", StakeUWolo: "2000000", Entitlements: []ReturnEntitlement{{EntitlementID: "desync-refund", ClaimID: "900000000102", ClaimKind: "bet_refund", PrincipalUWolo: "2000000", AmountUWolo: "2000000"}}},
			{LegID: "winner", MarketID: "501", StakeUWolo: "5000000", Entitlements: []ReturnEntitlement{{EntitlementID: "winner-payout", ClaimID: "900000000101", ClaimKind: "bet_payout", PrincipalUWolo: "5000000", AmountUWolo: "5000000"}}},
		}}
	testSignAllocation(&plan, p)
	accounting, _ := hex.DecodeString(c.config.AccountingReviewerKeyHex)
	custody, _ := hex.DecodeString(c.config.CustodyReviewerKeyHex)
	execution, _ := hex.DecodeString(c.config.ActivationAuthorityKeyHex)
	permit, err := os.ReadFile(c.config.PermitFile)
	require.NoError(t, err)
	cfg := EscrowReturnExecutionConfig{Authority: ReserveReviewAuthority{AccountingReviewerKey: accounting, CustodyReviewerKey: custody, ExecutionAuthorityKey: execution,
		WagerApprovalKey: p.WagerApprovalKey, WithdrawalApprovalKey: p.WithdrawalApprovalKey, ExpectedVault: p.BettingEscrow,
		ExpectedBuildSHA256: c.issuer.binaryDigest, ExpectedConfigSHA256: c.issuer.configDigest, ExpectedPermitSHA256: custodySHA(permit)},
		TrustAnchor: c.config.TrustAnchor, PaidReturnProofReader: c.reader, ExpectedCustodyPolicySHA256: hashJSON(p), FeeUWolo: c.config.FeesUWolo,
		MaximumFeeUWolo: enrollment.MaximumFeeUWolo, MinimumGasReserveUWolo: enrollment.MinimumGasReserveUWolo, MinimumUnencumberedUWolo: enrollment.MinimumUnencumberedUWolo}
	for _, pin := range enrollment.Producers {
		cfg.Producers = append(cfg.Producers, EscrowReturnProducerPin{ProducerID: pin.ProducerID, SourceSHA256: pin.SourceSHA256})
	}
	verifier, err := NewEscrowReturnExecutionVerifier(c.engine, cfg)
	require.NoError(t, err)
	f.reserve = &escrowExecutionFixture{engine: c.engine, chain: c.chain, reader: c.reader, accounting: c.accounting, custody: c.custody, config: cfg, verifier: verifier, plan: plan}
	f.refresh(t)
	return f
}

func (f *escrowRuntimeFixture) refresh(t *testing.T) {
	t.Helper()
	a, _, _, _, bundle := f.reserve.bundle(t, "900000000101")
	f.approval, f.bundle = a, bundle
	require.NoError(t, os.WriteFile(f.reviewPath, f.reserve.sign(t, &f.bundle), 0600))
}

func TestEscrowReturnRuntimeProtectedSDKPreparationAndStaleJournal(t *testing.T) {
	f := newEscrowRuntimeFixture(t)
	c := f.custody
	before := readTestCustodyJournal(t, c.engine)
	signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
	run, err := c.engine.PrepareReturnRun(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, "satchel:claim-return:900000000101", run.SettlementRunID)
	require.Equal(t, "5000000", run.Payouts[0].AmountUWolo)
	require.Equal(t, c.config.Vault, run.Payouts[0].ToAddress)
	prepared := readTestCustodyJournal(t, c.engine)
	require.NotEqual(t, before.JournalDigest, prepared.JournalDigest)
	// Preparation changed the real journal. Its old independent review cannot
	// authorize a second preparation or later execution, despite identical input.
	_, err = c.engine.PrepareReturnRun(t.Context(), f.approval)
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
	require.Equal(t, prepared, readTestCustodyJournal(t, c.engine))
	f.refresh(t)
	again, err := c.engine.PrepareReturnRun(t.Context(), f.approval)
	require.NoError(t, err)
	require.Equal(t, run, again)
	require.Equal(t, prepared, readTestCustodyJournal(t, c.engine))
	require.Equal(t, signs, c.SDKSigns.Load())
	require.Equal(t, broadcasts, c.chain.broadcasts)
}

func TestEscrowReturnRuntimeRefusesRevocationAndChangedEvidenceBeforeWrite(t *testing.T) {
	for _, mode := range []string{"permit", "enrollment", "review_permissions", "root", "expired_review", "forged_review", "journal", "allocation", "cancelled"} {
		t.Run(mode, func(t *testing.T) {
			f := newEscrowRuntimeFixture(t)
			c := f.custody
			ctx := t.Context()
			switch mode {
			case "permit":
				require.NoError(t, os.Remove(c.config.PermitFile))
			case "enrollment":
				require.NoError(t, os.WriteFile(c.config.EscrowReturnExecutionFile, []byte(`{}`), 0600))
			case "review_permissions":
				require.NoError(t, os.Chmod(f.reviewPath, 0644))
			case "root":
				f.bundle.Review.CommitBlockHash = strings.Repeat("A", 64)
				require.NoError(t, os.WriteFile(f.reviewPath, f.reserve.sign(t, &f.bundle), 0600))
			case "expired_review":
				f.bundle.Review.ExpiresAt = time.Now().Unix() - 1
				require.NoError(t, os.WriteFile(f.reviewPath, f.reserve.sign(t, &f.bundle), 0600))
			case "forged_review":
				f.bundle.Review.AccountingReviewerSignature = "invalid"
				custodyWrite(t, f.reviewPath, f.bundle)
			case "journal":
				require.NoError(t, c.engine.db.Update(func(tx *bolt.Tx) error { _, err := tx.CreateBucket([]byte("changed-after-review")); return err }))
			case "allocation":
				f.approval.AmountUWolo = "4000000"
			case "cancelled":
				var cancel context.CancelFunc
				ctx, cancel = context.WithCancel(ctx)
				cancel()
			}
			before := readTestCustodyJournal(t, c.engine)
			signs, broadcasts := c.SDKSigns.Load(), c.chain.broadcasts
			_, err := c.engine.PrepareReturnRun(ctx, f.approval)
			require.Error(t, err)
			require.Equal(t, before, readTestCustodyJournal(t, c.engine))
			require.Equal(t, signs, c.SDKSigns.Load())
			require.Equal(t, broadcasts, c.chain.broadcasts)
		})
	}
}
