package satchelservice

// These exercise an actual disposable Cosmos SDK keyring and authenticated
// native chain, not a real funded wallet or production escrow enrollment.
import (
	"bytes"
	"context"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/stretchr/testify/require"
)

func enrolledSDKFixture(t *testing.T) (*escrowRuntimeFixture, *KeyringBackend) {
	t.Helper()
	f := newEscrowRuntimeFixture(t)
	c := f.custody
	c.chain.release()
	// 8094's original permitted preparation uses the current signed journal.
	_, err := c.engine.PrepareReturnRun(t.Context(), f.approval)
	require.NoError(t, err)
	// Original preparation changed its journal, so a genuinely NEW independent
	// two-reviewer snapshot is mandatory for execution.
	f.refresh(t)
	key := &sdksecp.PrivKey{Key: bytes.Repeat([]byte{9}, 32)}
	address, err := backendPubAddress(key.PubKey())
	require.NoError(t, err)
	require.Equal(t, c.config.BettingEscrow, address)
	dir := filepath.Join(filepath.Dir(c.path), "separate-escrow-keyring")
	pass := nativeProductKeyring(t, dir, "native-escrow-only", key)
	approvalHash := hashJSON(f.approval)
	cfg := BackendConfig{
		RPC: c.config.RPC, REST: c.config.REST, WitnessRPC: c.config.WitnessRPC,
		Vault:        c.config.BettingEscrow,
		PublicKeyHex: hex.EncodeToString(key.PubKey().Bytes()),
		KeyringDir:   dir, KeyName: "native-escrow-only", PassphraseFile: pass,
		FeesUWolo: c.config.FeesUWolo, MaxAmountUWolo: "1000000000",
		GasLimit: c.config.GasLimit, TimeoutBlocks: c.config.TimeoutBlocks,
		ApprovedDestinations: []string{c.config.Vault},
		ProtectedAddresses:   []string{c.config.Vault},
		ReturnDestination:    c.config.Vault,
		ReturnVerifier: func(req TransferRequest) error {
			if req.ReturnApproval == nil || hashJSON(*req.ReturnApproval) != approvalHash ||
				!verifyReview(c.engine.policy.WithdrawalApprovalKey,
					ReturnApprovalMessage(*req.ReturnApproval, c.engine.policy),
					req.ReturnApproval.Signature) {
				return ErrBackend
			}
			return nil
		},
		AuthorizeSign:      func(context.Context, TransferRequest) bool { return true },   // fixture-only
		AuthorizeBroadcast: func(context.Context, SignedTransaction) bool { return true }, // fixture-only
		ConfirmTransaction: func(ctx context.Context, req TransferRequest, signed SignedTransaction) (Confirmation, error) {
			evidence, err := c.reader.ReadTransfer(ctx, satchel.TransferIntent{
				Sender: req.Sender, Recipient: req.Recipient,
				AmountUWolo: req.AmountUWolo, Memo: req.Memo}, signed.Hash)
			if err != nil || !evidence.ConsensusAuthenticated() ||
				!bytes.Equal(evidence.Observation().TxBytes, signed.Bytes) {
				return Confirmation{Status: "UNKNOWN"}, ErrBackend
			}
			return Confirmation{Status: "CONFIRMED", ReceiptID: evidence.Receipt().ID(),
				Height: evidence.Observation().Height, BlockHash: evidence.Observation().BlockHash}, nil
		},
	}
	escrow, err := NewKeyringBackend(cfg)
	require.NoError(t, err)
	t.Cleanup(escrow.Close)
	return f, escrow
}

func TestEnrolledEscrowNativeSDKExecutesOnlyOneActualEscrowMsgSend(t *testing.T) {
	f, escrow := enrolledSDKFixture(t)
	c := f.custody
	guards := EscrowReturnSpendGuard{
		Permit:       func(context.Context, TransferRequest) bool { return true },                    // fixture permit
		PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true }, // fixture permit
	}
	before := c.chain.broadcasts
	result, err := c.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, escrow, guards)
	require.NoError(t, err)
	require.Equal(t, "UNKNOWN", result.Status, "native broadcast alone must never grant customer credit")
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.NotEmpty(t, result.TxHash)
	require.Equal(t, before+1, c.chain.broadcasts, "exactly one real SDK escrow MsgSend")
	stored, err := c.engine.ReadEscrowReturnSpend(f.approval.ClaimID)
	require.NoError(t, err)
	require.Equal(t, result, stored)
	_, err = c.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, escrow, guards)
	require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
	require.Equal(t, before+1, c.chain.broadcasts, "no native second send on replay")
	// Independent consensus proof and payment reconciliation are a distinct
	// acceptance operation; execution cannot mark a return receipt paid.
	require.Error(t, errInaccessibleReturnCredit(t, c.engine, f.approval))
}

func TestEnrolledEscrowRejectsWrongRoleRevocationAndMissingIndependentPermit(t *testing.T) {
	t.Run("wrong vault signer role", func(t *testing.T) {
		f, _ := enrolledSDKFixture(t)
		c := f.custody
		before := c.chain.broadcasts
		_, err := c.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, c.native,
			EscrowReturnSpendGuard{Permit: func(context.Context, TransferRequest) bool { return true },
				PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true }})
		require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
		require.Equal(t, before, c.chain.broadcasts)
	})
	t.Run("permit absent", func(t *testing.T) {
		f, escrow := enrolledSDKFixture(t)
		c := f.custody
		before := c.chain.broadcasts
		_, err := c.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, escrow,
			EscrowReturnSpendGuard{})
		require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
		require.Equal(t, before, c.chain.broadcasts)
	})
	t.Run("review changed after preparation", func(t *testing.T) {
		f, escrow := enrolledSDKFixture(t)
		before := f.custody.chain.broadcasts
		require.NoError(t, os.WriteFile(f.reviewPath, []byte(strings.Repeat("x", 20)), 0600))
		_, err := f.custody.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, escrow,
			EscrowReturnSpendGuard{Permit: func(context.Context, TransferRequest) bool { return true },
				PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true }})
		require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
		require.Equal(t, before, f.custody.chain.broadcasts)
	})
	t.Run("owner financial permit revoked", func(t *testing.T) {
		f, escrow := enrolledSDKFixture(t)
		before := f.custody.chain.broadcasts
		require.NoError(t, os.Remove(f.custody.config.PermitFile))
		_, err := f.custody.engine.ExecuteEnrolledEscrowReturn(t.Context(), f.approval, escrow,
			EscrowReturnSpendGuard{Permit: func(context.Context, TransferRequest) bool { return true },
				PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true }})
		require.ErrorIs(t, err, ErrEscrowRuntimeHeld)
		require.Equal(t, before, f.custody.chain.broadcasts)
	})
}
