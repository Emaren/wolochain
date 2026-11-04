package satchelservice

// This is an isolated SDK transaction-building fixture. The injected reviewer
// and key are test-only; no fixture provisions production escrow authority.
import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
	"google.golang.org/protobuf/proto"
)

type backendReturnFixture struct {
	base    *backendFixture
	backend *KeyringBackend
	request TransferRequest
	policy  Policy
}

func newBackendReturnFixture(t *testing.T) *backendReturnFixture {
	t.Helper()
	f := &backendReturnFixture{base: newBackendFixture(t)}
	sender, recipient := f.base.request.Sender, f.base.request.Recipient
	f.policy = Policy{Vault: recipient, BettingEscrow: sender, MaxAmountUWolo: 1000000000,
		WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
	at := time.Now().Unix()
	plan := ReturnAllocation{Version: 2, AllocationID: "allocation:backend-return:7", Revision: 1, OperationID: "satchel:ticket:7", OwnerID: "owner-1", TicketID: "7",
		FundingTxHash: strings.Repeat("A", 64), ReturnCapUWolo: "7000000", FundsBudgetID: "backend-return-budget", FundsAvailableUWolo: "9000000",
		BankEvidenceDigest: strings.Repeat("B", 64), BankHeight: 99, BankBlockHash: strings.Repeat("C", 64), IssuedAt: at - 1, ExpiresAt: at + 120,
		Legs: []ReturnLeg{{LegID: "refund", MarketID: "501", StakeUWolo: "7000000", Entitlements: []ReturnEntitlement{{EntitlementID: "refund:101", ClaimID: "101", ClaimKind: "bet_refund", PrincipalUWolo: "7000000", AmountUWolo: "7000000"}}}}}
	testSignAllocation(&plan, f.policy)
	a := ReturnApproval{Version: 2, TicketID: "7", MarketID: "501", LegID: "refund", EntitlementID: "refund:101", Allocation: &plan,
		OperationID: "satchel:ticket:7", ClaimID: "101", OwnerID: "owner-1", ClaimKind: "bet_refund", AmountUWolo: "7000000",
		AllocationDigest: AllocationDigest(plan, f.policy), IssuedAt: at - 1, ExpiresAt: at + 120}
	testSignReturnApproval(&a, f.policy)
	f.request = TransferRequest{OperationID: "satchel:claim-return:101", Kind: "claim_return", ChainID: "wolo-1", Denom: "uwolo", Sender: sender,
		Recipient: recipient, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/101", OwnerID: a.OwnerID, ReturnApproval: &a}
	original := hashJSON(a)
	cfg := f.base.b.cfg
	cfg.ReturnDestination = recipient
	cfg.ReturnVerifier = func(r TransferRequest) error {
		if r.ReturnApproval == nil || hashJSON(*r.ReturnApproval) != original ||
			!verifyReview(f.policy.WithdrawalApprovalKey, ReturnApprovalMessage(*r.ReturnApproval, f.policy), r.ReturnApproval.Signature) ||
			!verifyReview(f.policy.WithdrawalApprovalKey, AllocationMessage(*r.ReturnApproval.Allocation, f.policy), r.ReturnApproval.Allocation.Signature) {
			return ErrBackend
		}
		return nil
	}
	cfg.AuthorizeSign = func(context.Context, TransferRequest) bool { return true }
	cfg.AuthorizeBroadcast = func(context.Context, SignedTransaction) bool { return true }
	var err error
	f.backend, err = newBackend(cfg)
	require.NoError(t, err)
	f.backend.signer = f.base.signer
	t.Cleanup(f.backend.Close)
	return f
}

func copyBackendReturnRequest(t *testing.T, r TransferRequest) TransferRequest {
	t.Helper()
	b, err := json.Marshal(r)
	require.NoError(t, err)
	var copy TransferRequest
	require.NoError(t, json.Unmarshal(b, &copy))
	return copy
}

func TestBackendClaimReturnSDKSigningAndExplicitRoleOnly(t *testing.T) {
	f := newBackendReturnFixture(t)
	_, err := f.base.b.Sign(t.Context(), f.request)
	require.ErrorIs(t, err, ErrPreSignRefused, "ordinary vault backend must reject return requests")
	_, err = f.backend.Sign(t.Context(), f.base.request)
	require.ErrorIs(t, err, ErrPreSignRefused, "escrow return role must not sign wagers")
	require.Zero(t, f.base.signer.calls.Load())
	signed, err := f.backend.Sign(t.Context(), f.request)
	require.NoError(t, err)
	require.EqualValues(t, 1, f.base.signer.calls.Load())
	require.Zero(t, f.base.broadcasts.Load(), "signing must not broadcast")
	require.NoError(t, f.backend.ValidateSigned(f.request, signed))
	var raw txapi.TxRaw
	var body txapi.TxBody
	var send bank.MsgSend
	require.NoError(t, proto.Unmarshal(signed.Bytes, &raw))
	require.NoError(t, proto.Unmarshal(raw.BodyBytes, &body))
	require.Len(t, body.Messages, 1)
	require.NoError(t, proto.Unmarshal(body.Messages[0].Value, &send))
	require.Equal(t, f.request.Sender, send.FromAddress)
	require.Equal(t, f.request.Recipient, send.ToAddress)
	require.Len(t, send.Amount, 1)
	require.Equal(t, f.request.AmountUWolo, send.Amount[0].Amount)
	require.Equal(t, "uwolo", send.Amount[0].Denom)
	require.Equal(t, f.request.Memo, body.Memo)
	result, err := f.backend.Broadcast(t.Context(), signed)
	require.NoError(t, err)
	require.Equal(t, "ACCEPTED", result.Status)
	require.EqualValues(t, 1, f.base.broadcasts.Load())
}

func TestBackendClaimReturnRejectsChangedIdentityAndConflictingAuthority(t *testing.T) {
	f := newBackendReturnFixture(t)
	cases := map[string]func(*TransferRequest){
		"owner":                      func(r *TransferRequest) { r.OwnerID = "owner-2" },
		"amount":                     func(r *TransferRequest) { r.AmountUWolo = "6000000" },
		"destination":                func(r *TransferRequest) { r.Recipient = engineTestPolicy(t).Vault },
		"sender":                     func(r *TransferRequest) { r.Sender = r.Recipient },
		"claim operation":            func(r *TransferRequest) { r.OperationID = "satchel:claim-return:102" },
		"memo":                       func(r *TransferRequest) { r.Memo = "aoe2war/satchel/claim-return/v1/102" },
		"allocation":                 func(r *TransferRequest) { r.ReturnApproval.Allocation.Legs[0].StakeUWolo = "6000000" },
		"allocation digest":          func(r *TransferRequest) { r.ReturnApproval.AllocationDigest = strings.Repeat("d", 64) },
		"allocation owner":           func(r *TransferRequest) { r.ReturnApproval.Allocation.OwnerID = "owner-2" },
		"entitlement":                func(r *TransferRequest) { r.ReturnApproval.EntitlementID = "other" },
		"approval signature":         func(r *TransferRequest) { r.ReturnApproval.Signature = "invalid" },
		"allocation signature":       func(r *TransferRequest) { r.ReturnApproval.Allocation.Signature = "invalid" },
		"expired approval":           func(r *TransferRequest) { r.ReturnApproval.ExpiresAt = time.Now().Unix() - 1 },
		"expired allocation":         func(r *TransferRequest) { r.ReturnApproval.Allocation.ExpiresAt = time.Now().Unix() - 1 },
		"future approval":            func(r *TransferRequest) { r.ReturnApproval.IssuedAt = time.Now().Unix() + 1 },
		"missing approval":           func(r *TransferRequest) { r.ReturnApproval = nil },
		"wager reservation":          func(r *TransferRequest) { r.Reservation = f.base.request.Reservation },
		"withdrawal approval":        func(r *TransferRequest) { r.Approval = &WithdrawalApproval{} },
		"owner withdrawal mandate":   func(r *TransferRequest) { r.OwnerMandate = &OwnerWithdrawalMandate{} },
		"protected historical claim": func(r *TransferRequest) { r.ReturnApproval.ClaimID = "889" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			r := copyBackendReturnRequest(t, f.request)
			mutate(&r)
			_, err := f.backend.Sign(t.Context(), r)
			require.ErrorIs(t, err, ErrPreSignRefused)
		})
	}
	require.Zero(t, f.base.signer.calls.Load())
	require.Zero(t, f.base.broadcasts.Load())
}

func TestBackendClaimReturnRequiresCompleteProtectedComposition(t *testing.T) {
	f := newBackendReturnFixture(t)
	for name, mutate := range map[string]func(*BackendConfig){
		"destination missing":   func(c *BackendConfig) { c.ReturnDestination = "" },
		"destination conflicts": func(c *BackendConfig) { c.ReturnDestination = c.Vault },
		"multiple destinations": func(c *BackendConfig) {
			c.ApprovedDestinations = append([]string{c.ReturnDestination}, engineTestPolicy(t).Vault)
		},
		"verifier missing":            func(c *BackendConfig) { c.ReturnVerifier = nil },
		"pre-sign guard missing":      func(c *BackendConfig) { c.AuthorizeSign = nil },
		"pre-broadcast guard missing": func(c *BackendConfig) { c.AuthorizeBroadcast = nil },
	} {
		t.Run(name, func(t *testing.T) {
			cfg := f.backend.cfg
			mutate(&cfg)
			b, err := newBackend(cfg)
			if b != nil {
				b.Close()
			}
			require.ErrorIs(t, err, ErrBackend)
		})
	}
}

func TestBackendClaimReturnValidatesExactDurableNativeBytes(t *testing.T) {
	f := newBackendReturnFixture(t)
	signed, err := f.backend.Sign(t.Context(), f.request)
	require.NoError(t, err)
	for name, mutate := range map[string]func(*TransferRequest){
		"amount":    func(r *TransferRequest) { r.AmountUWolo = "6000000" },
		"recipient": func(r *TransferRequest) { r.Recipient = engineTestPolicy(t).Vault },
		"owner":     func(r *TransferRequest) { r.OwnerID = "owner-2" },
		"memo":      func(r *TransferRequest) { r.Memo += "-changed" },
		"partition": func(r *TransferRequest) { r.ReturnApproval.Allocation.Legs[0].StakeUWolo = "6000000" },
	} {
		t.Run(name, func(t *testing.T) {
			r := copyBackendReturnRequest(t, f.request)
			mutate(&r)
			require.Error(t, f.backend.ValidateSigned(r, signed))
		})
	}
	require.EqualValues(t, 1, f.base.signer.calls.Load())
	require.Zero(t, f.base.broadcasts.Load())
}

func TestBackendClaimReturnRevocationPreservesSignedRecoveryWithoutResigning(t *testing.T) {
	f := newBackendReturnFixture(t)
	signed, err := f.backend.Sign(t.Context(), f.request)
	require.NoError(t, err)
	f.backend.cfg.ReturnVerifier = func(TransferRequest) error { return errors.New("revoked isolated review") }
	require.NoError(t, f.backend.ValidateSigned(f.request, signed), "revocation must preserve inspection of already fenced bytes")
	_, err = f.backend.Sign(t.Context(), f.request)
	require.ErrorIs(t, err, ErrPreSignRefused)
	f.backend.cfg.AuthorizeBroadcast = func(context.Context, SignedTransaction) bool { return false }
	result, err := f.backend.Broadcast(t.Context(), signed)
	require.ErrorIs(t, err, ErrBackend)
	require.Equal(t, "UNKNOWN", result.Status)
	require.EqualValues(t, 1, f.base.signer.calls.Load())
	require.Zero(t, f.base.broadcasts.Load())
}

func TestBackendClaimReturnMetadataCannotEnterVaultIntentJournal(t *testing.T) {
	b := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, b)
	r := engineTestWager(t, "1")
	r.ReturnApproval = &ReturnApproval{Version: 2, ClaimID: "101"}
	_, err := e.Submit(t.Context(), r)
	require.Error(t, err)
	require.NoError(t, e.db.View(func(tx *bolt.Tx) error {
		require.Nil(t, tx.Bucket(operations).Get([]byte(r.OperationID)))
		require.Empty(t, tx.Bucket(meta).Get([]byte("active")))
		return nil
	}))
	require.Zero(t, b.signs.Load())
	require.Zero(t, b.broadcasts.Load())
	// Fault injection must not make this unbound metadata valid merely by using
	// the old operation fingerprint and an unsigned UNKNOWN record.
	require.NoError(t, e.db.Update(func(tx *bolt.Tx) error {
		return save(tx, record{Request: r, Fingerprint: fingerprint(r), Result: Result{OperationID: r.OperationID, Status: "UNKNOWN", DurableFenced: true}})
	}))
	_, err = e.CustodyJournal()
	require.Error(t, err)
}
