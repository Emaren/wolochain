package satchelservice

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"

	"errors"
	bolt "go.etcd.io/bbolt"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

// Transaction bytes here are a controlled local stub. Real SDK/MsgSend signing
// and reserve bank-proof authenticity remain covered by the existing dedicated
// backend_return_test and escrow_return_execution_test suites.
type durableEscrowFake struct {
	signs, broadcasts int
	refuseSign        bool
	unknownBroadcast  bool
}

func (b *durableEscrowFake) Sign(_ context.Context, r TransferRequest) (SignedTransaction, error) {
	b.signs++
	if b.refuseSign {
		return SignedTransaction{}, errors.New("signer_timeout_unknown")
	}
	raw := []byte("test-only-signed-native-return:" + r.OperationID + ":" + r.Sender + ":" + r.Recipient + ":" + r.AmountUWolo)
	sum := sha256.Sum256(raw)
	return SignedTransaction{Bytes: raw, Hash: strings.ToUpper(hex.EncodeToString(sum[:]))}, nil
}
func (b *durableEscrowFake) ValidateSigned(r TransferRequest, s SignedTransaction) error {
	if r.Kind != "claim_return" || !strings.HasPrefix(string(s.Bytes), "test-only-signed-native-return:") {
		return ErrBackend
	}
	return nil
}
func (b *durableEscrowFake) Broadcast(context.Context, SignedTransaction) (BroadcastResult, error) {
	b.broadcasts++
	if b.unknownBroadcast {
		return BroadcastResult{Status: "UNKNOWN"}, errors.New("network_disconnect")
	}
	return BroadcastResult{Status: "ACCEPTED", Code: 0}, nil
}
func (b *durableEscrowFake) Confirm(context.Context, TransferRequest, SignedTransaction) (Confirmation, error) {
	return Confirmation{Status: "UNKNOWN"}, ErrBackend
}

func newQualifiedPreparedEscrow(t *testing.T) (*escrowExecutionFixture, ReturnApproval, VerifiedEscrowReturnExecution) {
	t.Helper()
	f := newEscrowExecutionFixture(t)
	a, _, _, _, _ := f.bundle(t, "101")
	// Source runtime owns its original owner claim preparation before review.
	_, err := f.engine.PrepareReturnRun(t.Context(), a)
	require.NoError(t, err)
	a, bank, proof, journal, bundle := f.bundle(t, "101")
	verified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &bundle))
	require.NoError(t, err)
	require.True(t, verified.CurrentFor(t.Context(), a))
	return f, a, verified
}

func TestDurableEscrowReturnSignsAndBroadcastsOnceWithoutCredit(t *testing.T) {
	f, a, proof := newQualifiedPreparedEscrow(t)
	backend := &durableEscrowFake{}
	guards := EscrowReturnSpendGuard{
		Permit:       func(context.Context, TransferRequest) bool { return true },
		PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true },
	}
	before := readTestCustodyJournal(t, f.engine)
	result, err := f.engine.ExecuteQualifiedEscrowReturn(t.Context(), a, proof, backend, guards)
	require.NoError(t, err)
	require.Equal(t, "UNKNOWN", result.Status)
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.True(t, result.DurableFenced)
	require.NotEmpty(t, result.TxHash)
	require.Equal(t, 1, backend.signs)
	require.Equal(t, 1, backend.broadcasts)
	stored, err := f.engine.ReadEscrowReturnSpend(a.ClaimID)
	require.NoError(t, err)
	require.Equal(t, result, stored)
	// Reserve/custody snapshot must retain a new operation, not pretend this
	// spending attempt is a paid return receipt.
	after := readTestCustodyJournal(t, f.engine)
	require.NotEqual(t, before.JournalDigest, after.JournalDigest)
	require.Error(t, errInaccessibleReturnCredit(t, f.engine, a))
	_, err = f.engine.ExecuteQualifiedEscrowReturn(t.Context(), a, proof, backend, guards)
	require.ErrorIs(t, err, ErrEscrowReturnSpend)
	require.Equal(t, 1, backend.signs)
	require.Equal(t, 1, backend.broadcasts)
}
func errInaccessibleReturnCredit(t *testing.T, e *Engine, a ReturnApproval) error {
	t.Helper()
	return e.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b == nil {
			return errors.New("missing original returns")
		}
		var state returnRecord
		if json.Unmarshal(b.Get([]byte(a.ClaimID)), &state) != nil {
			return errors.New("invalid return")
		}
		if state.Receipt == nil {
			return errors.New("still unpaid, correct")
		}
		return nil
	})
}
func TestDurableEscrowReturnRefusesUnsignedOrRevokedAndRetainsUnknown(t *testing.T) {
	t.Run("missing permit never signs or writes", func(t *testing.T) {
		f, a, proof := newQualifiedPreparedEscrow(t)
		backend := &durableEscrowFake{}
		_, err := f.engine.ExecuteQualifiedEscrowReturn(t.Context(), a, proof, backend, EscrowReturnSpendGuard{})
		require.ErrorIs(t, err, ErrEscrowReturnSpend)
		require.Zero(t, backend.signs)
		_, err = f.engine.ReadEscrowReturnSpend(a.ClaimID)
		require.ErrorIs(t, err, ErrEscrowReturnSpend)
	})
	t.Run("pre-broadcast revoke leaves signed bytes without broadcasting", func(t *testing.T) {
		f, a, proof := newQualifiedPreparedEscrow(t)
		backend := &durableEscrowFake{}
		guards := EscrowReturnSpendGuard{Permit: func(context.Context, TransferRequest) bool { return true },
			PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return false }}
		result, err := f.engine.ExecuteQualifiedEscrowReturn(t.Context(), a, proof, backend, guards)
		require.NoError(t, err)
		require.Equal(t, "signed_permit_revoked_unknown", result.Reason)
		require.Equal(t, 1, backend.signs)
		require.Zero(t, backend.broadcasts)
		stored, err := f.engine.ReadEscrowReturnSpend(a.ClaimID)
		require.NoError(t, err)
		require.Equal(t, result, stored)
	})
	t.Run("sign failure remains durable unknown", func(t *testing.T) {
		f, a, proof := newQualifiedPreparedEscrow(t)
		backend := &durableEscrowFake{refuseSign: true}
		guards := EscrowReturnSpendGuard{Permit: func(context.Context, TransferRequest) bool { return true },
			PreBroadcast: func(context.Context, TransferRequest, SignedTransaction) bool { return true }}
		result, err := f.engine.ExecuteQualifiedEscrowReturn(t.Context(), a, proof, backend, guards)
		require.NoError(t, err)
		require.Equal(t, "signing_uncertain", result.Reason)
		require.Equal(t, 1, backend.signs)
		require.Zero(t, backend.broadcasts)
		_, err = f.engine.ReadEscrowReturnSpend(a.ClaimID)
		require.NoError(t, err)
	})
}
