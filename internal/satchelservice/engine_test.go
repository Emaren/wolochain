package satchelservice

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	bolt "go.etcd.io/bbolt"
)

// This backend tests journal state transitions only. Its deterministic synthetic
// bytes are not signed Cosmos transactions and can never leave this test.
// backend_test.go separately checks actual Cosmos transaction construction.
type engineTestBackend struct {
	signs, broadcasts, confirmations               atomic.Int32
	signErr, validateErr, broadcastErr, confirmErr error
	broadcastStatus                                string
	broadcastCode                                  uint32
	confirmationStatus                             string
	receiptIndex                                   int
	corruptSigned                                  bool
	fixedBytes                                     bool
	beforeSign                                     func(TransferRequest)
	beforeBroadcast                                func(SignedTransaction)
}

func engineTestSigned(r TransferRequest) SignedTransaction {
	b, _ := json.Marshal(r)
	hash := sha256.Sum256(b)
	return SignedTransaction{Bytes: b, Hash: strings.ToUpper(hex.EncodeToString(hash[:])), AccountNumber: 1, Sequence: 7}
}
func (b *engineTestBackend) Sign(_ context.Context, r TransferRequest) (SignedTransaction, error) {
	b.signs.Add(1)
	if b.beforeSign != nil {
		b.beforeSign(r)
	}
	if b.signErr != nil {
		return SignedTransaction{}, b.signErr
	}
	if b.fixedBytes {
		r = TransferRequest{OperationID: "synthetic-colliding-backend"}
	}
	signed := engineTestSigned(r)
	if b.corruptSigned {
		signed.Hash = strings.Repeat("F", 64)
	}
	return signed, nil
}
func (b *engineTestBackend) ValidateSigned(r TransferRequest, s SignedTransaction) error {
	if b.validateErr != nil {
		return b.validateErr
	}
	if b.fixedBytes {
		r = TransferRequest{OperationID: "synthetic-colliding-backend"}
	}
	expected := engineTestSigned(r)
	if !bytes.Equal(expected.Bytes, s.Bytes) || !strings.EqualFold(expected.Hash, s.Hash) {
		return errors.New("synthetic_payload_mismatch")
	}
	return nil
}
func (b *engineTestBackend) Broadcast(_ context.Context, s SignedTransaction) (BroadcastResult, error) {
	b.broadcasts.Add(1)
	if b.beforeBroadcast != nil {
		b.beforeBroadcast(s)
	}
	status := b.broadcastStatus
	if status == "" {
		status = "ACCEPTED"
	}
	return BroadcastResult{Status: status, Code: b.broadcastCode}, b.broadcastErr
}
func (b *engineTestBackend) Confirm(_ context.Context, _ TransferRequest, s SignedTransaction) (Confirmation, error) {
	b.confirmations.Add(1)
	status := b.confirmationStatus
	if status == "" {
		status = "OBSERVED_NONCREDITING"
	}
	return Confirmation{Status: status, ReceiptID: "wolo-1:" + s.Hash + ":" + strconv.Itoa(b.receiptIndex), Height: 123, BlockHash: strings.Repeat("B", 64)}, b.confirmErr
}

func engineTestPolicy(t *testing.T) Policy {
	return Policy{Vault: testHTTPAddress(t, 110), BettingEscrow: testHTTPAddress(t, 111), ProtectedAddresses: []string{testHTTPAddress(t, 111), testHTTPAddress(t, 112)},
		MaxAmountUWolo: 1000000000, WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
}
func engineTestApprovalKey() ed25519.PrivateKey {
	return ed25519.NewKeyFromSeed(bytes.Repeat([]byte{77}, ed25519.SeedSize))
}
func engineTestWagerApprovalKey() ed25519.PrivateKey {
	return ed25519.NewKeyFromSeed(bytes.Repeat([]byte{78}, ed25519.SeedSize))
}
func engineTestOpen(t *testing.T, b Backend) (*Engine, string, Policy) {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "operations.db")
	policy := engineTestPolicy(t)
	engine, err := Open(path, policy, b)
	if err != nil {
		t.Fatal(err)
	}
	engine.now = func() time.Time { return time.Unix(1800000000, 0) }
	t.Cleanup(func() { _ = engine.Close() })
	return engine, path, policy
}
func engineTestWager(t *testing.T, n string) TransferRequest {
	p := engineTestPolicy(t)
	r := TransferRequest{OperationID: "satchel:ticket:" + n, ChainID: "wolo-1", Denom: "uwolo", Sender: p.Vault, Recipient: p.BettingEscrow, AmountUWolo: "1000000", Memo: "AoE2HDBets bet ticket v1 · ticket " + n, Kind: "wager", OwnerID: "owner-1"}
	r.Reservation = testWagerReservation(t, r, p, time.Unix(1800000000, 0))
	return r
}

func testWagerReservation(t *testing.T, r TransferRequest, p Policy, now time.Time) *WagerReservation {
	t.Helper()
	digest := sha256.Sum256([]byte("test-only-ledger-reservation:" + r.OperationID))
	a := &WagerReservation{Version: 1, OperationID: r.OperationID, OwnerID: r.OwnerID,
		Vault: p.Vault, Recipient: p.BettingEscrow, AmountUWolo: r.AmountUWolo, Memo: r.Memo,
		ReservationDigest: hex.EncodeToString(digest[:]), LedgerRevision: strings.Repeat("a", 64),
		ConsentDigest: strings.Repeat("b", 64), FeeUWolo: "5000", IssuedAt: now.Unix() - 1, ExpiresAt: now.Unix() + 120}
	a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(*a)))
	return a
}
func engineTestWithdrawal(t *testing.T) TransferRequest {
	p := engineTestPolicy(t)
	id := "12345678-1234-4123-8123-123456789abc"
	a := WithdrawalApproval{WithdrawalID: id, ChallengeID: "12345678-1234-4123-8123-123456789abd", OwnerID: "owner-1", AmountUWolo: "1000000", Memo: "aoe2war/satchel/withdraw/v1/" + id, ReservationDigest: strings.Repeat("C", 64), IssuedAt: 1799999990, ExpiresAt: 1800000100}
	owner := sdksecp.GenPrivKeyFromSecret([]byte("isolated-test-owner-consent-not-a-production-key"))
	a.Recipient, _ = bech32.EncodeFromBase256("wolo", owner.PubKey().Address())
	m := &OwnerWithdrawalMandate{Challenge: OwnerWithdrawalChallenge{ID: a.ChallengeID, OwnerUID: a.OwnerID, WalletAddress: a.Recipient, AmountUWolo: a.AmountUWolo, IssuedAtUTC: time.Unix(a.IssuedAt, 0).UTC().Format("2006-01-02T15:04:05.000Z"), ExpiresAtUTC: time.Unix(a.ExpiresAt, 0).UTC().Format("2006-01-02T15:04:05.000Z")}, PubKey: OwnerWithdrawalPublicKey{Type: "tendermint/PubKeySecp256k1", Value: base64.StdEncoding.EncodeToString(owner.PubKey().Bytes())}}
	message, err := WithdrawalOwnerSignBytes(m.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	sig, err := owner.Sign(message)
	if err != nil {
		t.Fatal(err)
	}
	m.Signature = base64.StdEncoding.EncodeToString(sig)
	a.HoldDigest = WithdrawalHoldDigest(a.ReservationDigest, *m)
	engineTestSignApproval(&a, p.Vault)
	return TransferRequest{OperationID: "satchel:withdrawal:" + id, ChainID: "wolo-1", Denom: "uwolo", Sender: p.Vault, Recipient: a.Recipient, AmountUWolo: a.AmountUWolo, Memo: a.Memo, Kind: "withdrawal", OwnerID: a.OwnerID, Approval: &a, OwnerMandate: m}
}
func engineTestSignApproval(a *WithdrawalApproval, vault string) {
	a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestApprovalKey(), ApprovalMessage(*a, vault)))
}

func TestEnginePersistsIntentAndSignedBytesBeforeNetworkBoundary(t *testing.T) {
	backend := &engineTestBackend{}
	engine, _, _ := engineTestOpen(t, backend)
	request := engineTestWager(t, "1")
	backend.beforeSign = func(input TransferRequest) {
		if err := engine.db.View(func(tx *bolt.Tx) error {
			r, err := load(tx, input.OperationID)
			if err != nil {
				return err
			}
			if !r.Result.DurableFenced || r.Result.Status != "UNKNOWN" || r.Result.Reason != "signing_started" || string(tx.Bucket(meta).Get([]byte("active"))) != input.OperationID {
				return errors.New("intent_not_durable_before_sign")
			}
			return nil
		}); err != nil {
			t.Error(err)
		}
	}
	backend.beforeBroadcast = func(s SignedTransaction) {
		if err := engine.db.View(func(tx *bolt.Tx) error {
			r, err := load(tx, request.OperationID)
			if err != nil {
				return err
			}
			if !bytes.Equal(r.Signed.Bytes, s.Bytes) || r.Result.TxHash != s.Hash || r.Result.Reason != "broadcast_started" {
				return errors.New("signed_bytes_not_durable_before_broadcast")
			}
			return nil
		}); err != nil {
			t.Error(err)
		}
	}
	result, err := engine.Submit(t.Context(), request)
	if err != nil || result.Status != "ACCEPTED" || !result.DurableFenced || result.TxHash == "" {
		t.Fatalf("accepted outcome missing durable identity: result=%+v err=%v", result, err)
	}
}

func TestEngineConcurrentIdenticalSubmissionsSignAndBroadcastOnce(t *testing.T) {
	backend := &engineTestBackend{}
	engine, _, _ := engineTestOpen(t, backend)
	request := engineTestWager(t, "1")
	var wg sync.WaitGroup
	failures := make(chan error, 64)
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			result, err := engine.Submit(t.Context(), request)
			if err != nil {
				failures <- err
			} else if result.Status != "ACCEPTED" || result.OperationID != request.OperationID || !result.DurableFenced {
				failures <- errors.New("inconsistent_replay")
			}
		}()
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatalf("concurrent replay transmitted again: sign=%d broadcast=%d", backend.signs.Load(), backend.broadcasts.Load())
	}
}

func TestEngineOperationIDBindsEveryEconomicField(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*TransferRequest)
	}{
		{"chain", func(r *TransferRequest) { r.ChainID = "other" }},
		{"denom", func(r *TransferRequest) { r.Denom = "uother" }},
		{"sender", func(r *TransferRequest) { r.Sender = testHTTPAddress(t, 115) }},
		{"recipient", func(r *TransferRequest) { r.Recipient = testHTTPAddress(t, 115) }},
		{"amount", func(r *TransferRequest) { r.AmountUWolo = "2000000" }},
		{"memo", func(r *TransferRequest) { r.Memo += " changed" }},
		{"kind", func(r *TransferRequest) { r.Kind = "withdrawal" }},
		{"owner", func(r *TransferRequest) { r.OwnerID = "other-owner" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{}
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			if _, err := engine.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			test.mutate(&request)
			if _, err := engine.Submit(t.Context(), request); err == nil {
				t.Fatal("changed economics reused operation identity")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
				t.Fatal("conflicting request transmitted")
			}
		})
	}
}

func TestEngineRestartNeverSignsOrBroadcastsRecordedOperation(t *testing.T) {
	first := &engineTestBackend{}
	engine, path, policy := engineTestOpen(t, first)
	request := engineTestWager(t, "1")
	original, err := engine.Submit(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if err := engine.Close(); err != nil {
		t.Fatal(err)
	}
	second := &engineTestBackend{}
	reopened, err := Open(path, policy, second)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	result, err := reopened.Submit(t.Context(), request)
	if err != nil || result != original || second.signs.Load() != 0 || second.broadcasts.Load() != 0 {
		t.Fatalf("restart replay changed or retransmitted operation: result=%+v err=%v", result, err)
	}
	if _, err := reopened.Submit(t.Context(), engineTestWager(t, "2")); err == nil {
		t.Fatal("restart lost unresolved signer sequence fence")
	}
}

func TestEngineUncertaintyAndSigningFailureHoldEntireSigner(t *testing.T) {
	for _, test := range []struct {
		name       string
		backend    *engineTestBackend
		broadcasts int32
	}{
		{"signing error", &engineTestBackend{signErr: errors.New("uncertain_signer")}, 0},
		{"poisoned signed hash", &engineTestBackend{corruptSigned: true}, 0},
		{"wrong signed economic payload", &engineTestBackend{validateErr: errors.New("payload_mismatch")}, 0},
		{"broadcast transport uncertainty", &engineTestBackend{broadcastErr: errors.New("lost_ack")}, 1},
		{"broadcast rejection remains held", &engineTestBackend{broadcastStatus: "FAILED", broadcastCode: 5}, 1},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := test.backend
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			first, err := engine.Submit(t.Context(), request)
			if err != nil || first.Status != "UNKNOWN" || !first.DurableFenced {
				t.Fatalf("uncertainty not held: %+v %v", first, err)
			}
			second, err := engine.Submit(t.Context(), request)
			if err != nil || second != first {
				t.Fatal("uncertain replay changed outcome")
			}
			if _, err := engine.Submit(t.Context(), engineTestWager(t, "2")); err == nil {
				t.Fatal("new operation bypassed unresolved signer hold")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != test.broadcasts {
				t.Fatalf("uncertainty retried: sign=%d broadcast=%d", backend.signs.Load(), backend.broadcasts.Load())
			}
		})
	}
}

func TestEngineRejectsInvalidAuthorityBeforeDurableSigningFence(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*TransferRequest)
	}{
		{"wrong chain", func(r *TransferRequest) { r.ChainID = "wolo-2" }},
		{"wrong denom", func(r *TransferRequest) { r.Denom = "stake" }},
		{"wrong signer", func(r *TransferRequest) { r.Sender = testHTTPAddress(t, 115) }},
		{"unapproved destination", func(r *TransferRequest) { r.Recipient = testHTTPAddress(t, 115) }},
		{"zero amount", func(r *TransferRequest) { r.AmountUWolo = "0" }},
		{"padded amount", func(r *TransferRequest) { r.AmountUWolo = "01000000" }},
		{"overflow amount", func(r *TransferRequest) { r.AmountUWolo = "18446744073709551616" }},
		{"fractional WOLO wager", func(r *TransferRequest) { r.AmountUWolo = "1" }},
		{"wrong memo", func(r *TransferRequest) { r.Memo = "payment" }},
		{"unknown kind", func(r *TransferRequest) { r.Kind = "treasury" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{}
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			test.mutate(&request)
			if _, err := engine.Submit(t.Context(), request); err == nil {
				t.Fatal("invalid request reached durable custody execution")
			}
			if backend.signs.Load() != 0 || backend.broadcasts.Load() != 0 {
				t.Fatal("invalid request reached signer")
			}
			if result, err := engine.Submit(t.Context(), engineTestWager(t, "2")); err != nil || result.Status != "ACCEPTED" {
				t.Fatalf("rejected input poisoned global signer availability: result=%+v err=%v", result, err)
			}
		})
	}
}

func TestEngineUntrustedObservationsCannotReleaseFinancialHold(t *testing.T) {
	for _, status := range []string{"OBSERVED_NONCREDITING", "UNKNOWN", "ACCEPTED", ""} {
		t.Run("status="+status, func(t *testing.T) {
			backend := &engineTestBackend{confirmationStatus: status}
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			if _, err := engine.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			result, err := engine.Reconcile(t.Context(), request.OperationID)
			if err != nil || result.Status == "CONFIRMED" || result.Status == "FAILED" {
				t.Fatalf("untrusted observation became terminal: result=%+v err=%v", result, err)
			}
			if _, err := engine.Submit(t.Context(), engineTestWager(t, "2")); err == nil {
				t.Fatal("untrusted evidence released signer sequence authority")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
				t.Fatal("reconciliation transmitted")
			}
		})
	}
}

func TestEngineTicketMemoCannotBeReassignedAfterAuthenticatedCompletion(t *testing.T) {
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	engine, _, _ := engineTestOpen(t, backend)
	first := engineTestWager(t, "1")
	if _, err := engine.Submit(t.Context(), first); err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Reconcile(t.Context(), first.OperationID); err != nil {
		t.Fatal(err)
	}
	second := engineTestWager(t, "2")
	second.Memo = first.Memo
	if _, err := engine.Submit(t.Context(), second); err == nil {
		t.Fatal("same ticket memo funded another operation")
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatal("reused ticket transmitted")
	}
}

func TestEnginePoisonedPersistedRecordsFailClosed(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*record)
	}{
		{"economic payload", func(r *record) { r.Request.Recipient = testHTTPAddress(t, 115) }},
		{"fingerprint", func(r *record) { r.Fingerprint = strings.Repeat("0", 64) }},
		{"result identity", func(r *record) { r.Result.OperationID = "satchel:ticket:2" }},
		{"missing fence", func(r *record) { r.Result.DurableFenced = false }},
		{"invented terminal confirmation", func(r *record) { r.Result.Status = "CONFIRMED" }},
		{"unknown status", func(r *record) { r.Result.Status = "fake_paid" }},
		{"signed bytes", func(r *record) { r.Signed.Bytes = append(r.Signed.Bytes, 0) }},
		{"returned hash", func(r *record) { r.Result.TxHash = strings.Repeat("E", 64) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{}
			engine, _, _ := engineTestOpen(t, backend)
			request := engineTestWager(t, "1")
			if _, err := engine.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			if err := engine.db.Update(func(tx *bolt.Tx) error {
				r, err := load(tx, request.OperationID)
				if err != nil {
					return err
				}
				test.mutate(&r)
				return save(tx, r)
			}); err != nil {
				t.Fatal(err)
			}
			if _, err := engine.Lookup(request.OperationID); err == nil {
				t.Fatal("poisoned record yielded payment status")
			}
			if _, err := engine.Submit(t.Context(), request); err == nil {
				t.Fatal("poisoned record replayed trusted state")
			}
			if _, err := engine.Reconcile(t.Context(), request.OperationID); err == nil {
				t.Fatal("poisoned record reconciled as payment")
			}
			if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 || backend.confirmations.Load() != 0 {
				t.Fatal("poisoned persisted state reached execution or confirmation")
			}
		})
	}
}

func TestEngineWithdrawalRequiresFreshExactIndependentApproval(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*TransferRequest)
		resign bool
	}{
		{"missing approval", func(r *TransferRequest) { r.Approval = nil }, false},
		{"invalid signature", func(r *TransferRequest) { r.Approval.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64)) }, false},
		{"noncanonical base64", func(r *TransferRequest) { r.Approval.Signature += "\n" }, false},
		{"retargeted owner", func(r *TransferRequest) { r.OwnerID = "other-owner" }, false},
		{"retargeted recipient", func(r *TransferRequest) { r.Recipient = testHTTPAddress(t, 115) }, false},
		{"changed amount", func(r *TransferRequest) { r.AmountUWolo = "2000000" }, false},
		{"changed memo", func(r *TransferRequest) { r.Memo += "bad" }, false},
		{"expired approval", func(r *TransferRequest) { r.Approval.ExpiresAt = 1800000000 }, true},
		{"future approval", func(r *TransferRequest) { r.Approval.IssuedAt = 1800000010 }, true},
		{"overlong validity", func(r *TransferRequest) { r.Approval.ExpiresAt = r.Approval.IssuedAt + 301 }, true},
		{"overflowed validity", func(r *TransferRequest) { r.Approval.IssuedAt = -1 << 63; r.Approval.ExpiresAt = (1 << 63) - 1 }, true},
		{"missing hold evidence", func(r *TransferRequest) { r.Approval.HoldDigest = "" }, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{}
			engine, _, policy := engineTestOpen(t, backend)
			request := engineTestWithdrawal(t)
			test.mutate(&request)
			if test.resign {
				engineTestSignApproval(request.Approval, policy.Vault)
			}
			if _, err := engine.Submit(t.Context(), request); err == nil {
				t.Fatal("invalid independent withdrawal authorization accepted")
			}
			if backend.signs.Load() != 0 || backend.broadcasts.Load() != 0 {
				t.Fatal("invalid approval reached signer")
			}
		})
	}
}

func TestEngineWithdrawalChallengeAndOwnerBindingSurviveRestart(t *testing.T) {
	backend := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	engine, path, policy := engineTestOpen(t, backend)
	request := engineTestWithdrawal(t)
	original, err := engine.Submit(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Reconcile(t.Context(), request.OperationID); err != nil {
		t.Fatal(err)
	}
	if err := engine.Close(); err != nil {
		t.Fatal(err)
	}
	secondBackend := &engineTestBackend{}
	reopened, err := Open(path, policy, secondBackend)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Unix(1800000200, 0) }
	replayed, err := reopened.Submit(t.Context(), request)
	if err != nil || replayed.TxHash != original.TxHash || replayed.Status != "CONFIRMED" {
		t.Fatalf("expired approval blocked safe existing receipt replay: result=%+v err=%v", replayed, err)
	}
	second := engineTestWithdrawal(t)
	second.Approval.WithdrawalID = "12345678-1234-4123-8123-123456789abe"
	second.OperationID = "satchel:withdrawal:" + second.Approval.WithdrawalID
	second.Approval.Memo = "aoe2war/satchel/withdraw/v1/" + second.Approval.WithdrawalID
	second.Memo = second.Approval.Memo
	second.Approval.IssuedAt = 1800000190
	second.Approval.ExpiresAt = 1800000300
	engineTestSignApproval(second.Approval, policy.Vault)
	if _, err := reopened.Submit(t.Context(), second); err == nil {
		t.Fatal("consumed owner challenge authorized another withdrawal")
	}
	request.OwnerID = "another-owner"
	if _, err := reopened.Submit(t.Context(), request); err == nil {
		t.Fatal("withdrawal receipt reassigned after restart")
	}
	if secondBackend.signs.Load() != 0 || secondBackend.broadcasts.Load() != 0 {
		t.Fatal("restart withdrawal replay transmitted")
	}
}

func TestEngineDuplicateAuthenticatedEffectsCannotSettleTwoOperations(t *testing.T) {
	// Deliberately faulty test backend returns one identical transaction for two
	// operations. Production ValidateSigned forbids that; the journal independently
	// refuses consuming the same chain effect twice even under this faulty stub.
	for _, secondIndex := range []int{0, 1} {
		t.Run("second_observed_ordinal="+strconv.Itoa(secondIndex), func(t *testing.T) {
			backend := &engineTestBackend{confirmationStatus: "CONFIRMED", fixedBytes: true}
			engine, _, _ := engineTestOpen(t, backend)
			first := engineTestWager(t, "1")
			if _, err := engine.Submit(t.Context(), first); err != nil {
				t.Fatal(err)
			}
			if _, err := engine.Reconcile(t.Context(), first.OperationID); err != nil {
				t.Fatal(err)
			}
			second := engineTestWager(t, "2")
			backend.receiptIndex = secondIndex
			if _, err := engine.Submit(t.Context(), second); err != nil {
				t.Fatal(err)
			}
			if _, err := engine.Reconcile(t.Context(), second.OperationID); err == nil {
				t.Fatal("one bank-send effect confirmed two obligations")
			}
			result, err := engine.Lookup(second.OperationID)
			if err != nil || result.Status == "CONFIRMED" {
				t.Fatalf("duplicate effect persisted as payment: result=%+v err=%v", result, err)
			}
		})
	}
}

func TestEngineWithdrawalSupportsAppMaximumWithoutRaisingWagerCap(t *testing.T) {
	backend := &engineTestBackend{}
	policy := engineTestPolicy(t)
	policy.MaxAmountUWolo = 50000000000
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	engine, err := Open(filepath.Join(dir, "operations.db"), policy, backend)
	if err != nil {
		t.Fatal(err)
	}
	defer engine.Close()
	engine.now = func() time.Time { return time.Unix(1800000000, 0) }
	wager := engineTestWager(t, "1")
	wager.AmountUWolo = "10001000000"
	wager.Reservation = testWagerReservation(t, wager, policy, time.Unix(1800000000, 0))
	if _, err := engine.Submit(t.Context(), wager); err == nil {
		t.Fatal("withdrawal maximum raised automated wager cap")
	}
	withdrawal := engineTestWithdrawal(t)
	withdrawal.AmountUWolo = "50000000000"
	withdrawal.Approval.AmountUWolo = withdrawal.AmountUWolo
	withdrawal.OwnerMandate.Challenge.AmountUWolo = withdrawal.AmountUWolo
	ownerMessage, err := WithdrawalOwnerSignBytes(withdrawal.OwnerMandate.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	ownerSignature, err := sdksecp.GenPrivKeyFromSecret([]byte("isolated-test-owner-consent-not-a-production-key")).Sign(ownerMessage)
	if err != nil {
		t.Fatal(err)
	}
	withdrawal.OwnerMandate.Signature = base64.StdEncoding.EncodeToString(ownerSignature)
	withdrawal.Approval.HoldDigest = WithdrawalHoldDigest(withdrawal.Approval.ReservationDigest, *withdrawal.OwnerMandate)
	engineTestSignApproval(withdrawal.Approval, policy.Vault)
	result, err := engine.Submit(t.Context(), withdrawal)
	if err != nil || result.Status != "ACCEPTED" || backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatalf("app-authorized 50000 WOLO withdrawal contract unsupported: result=%+v err=%v", result, err)
	}
}

func TestEnginePrivateStateAndPolicyCannotBeChangedAtRestart(t *testing.T) {
	backend := &engineTestBackend{}
	engine, path, policy := engineTestOpen(t, backend)
	if err := engine.Close(); err != nil {
		t.Fatal(err)
	}
	changed := policy
	changed.MaxAmountUWolo--
	if opened, err := Open(path, changed, backend); err == nil {
		opened.Close()
		t.Fatal("existing history accepted changed custody policy")
	}
	if err := os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	if opened, err := Open(path, policy, backend); err == nil {
		opened.Close()
		t.Fatal("publicly readable journal accepted")
	}
}
