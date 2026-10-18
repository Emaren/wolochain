package satchelservice

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

func TestWithdrawalRequiresOwnerConsentEvenWithValidIndependentApproval(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*TransferRequest)
	}{
		{"missing mandate", func(r *TransferRequest) { r.OwnerMandate = nil }},
		{"missing reservation", func(r *TransferRequest) { r.Approval.ReservationDigest = "" }},
		{"unbound owner proof", func(r *TransferRequest) { r.Approval.HoldDigest = strings.Repeat("A", 64) }},
		{"changed owner", func(r *TransferRequest) { r.OwnerMandate.Challenge.OwnerUID = "owner-2" }},
		{"changed receiving wallet", func(r *TransferRequest) { r.OwnerMandate.Challenge.WalletAddress = testHTTPAddress(t, 99) }},
		{"changed amount", func(r *TransferRequest) { r.OwnerMandate.Challenge.AmountUWolo = "1000001" }},
		{"changed challenge", func(r *TransferRequest) { r.OwnerMandate.Challenge.ID = "12345678-1234-4123-8123-123456789abe" }},
		{"expired owner challenge", func(r *TransferRequest) {
			r.OwnerMandate.Challenge.ExpiresAtUTC = time.Unix(1800000000, 0).UTC().Format(time.RFC3339Nano)
		}},
		{"future owner challenge", func(r *TransferRequest) {
			r.OwnerMandate.Challenge.IssuedAtUTC = time.Unix(1800000001, 0).UTC().Format(time.RFC3339Nano)
		}},
		{"overlong owner challenge", func(r *TransferRequest) {
			r.OwnerMandate.Challenge.ExpiresAtUTC = time.Unix(1800000300, 0).UTC().Format(time.RFC3339Nano)
		}},
		{"malformed timestamp", func(r *TransferRequest) { r.OwnerMandate.Challenge.IssuedAtUTC = "yesterday" }},
		{"wrong key type", func(r *TransferRequest) { r.OwnerMandate.PubKey.Type = "ed25519" }},
		{"wrong wallet key", func(r *TransferRequest) {
			r.OwnerMandate.PubKey.Value = base64.StdEncoding.EncodeToString(sdksecp.GenPrivKeyFromSecret([]byte("different-isolated-owner")).PubKey().Bytes())
		}},
		{"noncanonical pubkey", func(r *TransferRequest) { r.OwnerMandate.PubKey.Value += "\n" }},
		{"malformed compressed curve point", func(r *TransferRequest) {
			r.OwnerMandate.PubKey.Value = base64.StdEncoding.EncodeToString(append([]byte{2}, make([]byte, 32)...))
		}},
		{"forged signature", func(r *TransferRequest) {
			r.OwnerMandate.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64))
		}},
		{"noncanonical signature", func(r *TransferRequest) { r.OwnerMandate.Signature += "\n" }},
		{"login signature", func(r *TransferRequest) {
			signature, _ := sdksecp.GenPrivKeyFromSecret([]byte("isolated-test-owner-consent-not-a-production-key")).Sign([]byte("I authorize login to aoe2war.com"))
			r.OwnerMandate.Signature = base64.StdEncoding.EncodeToString(signature)
		}},
		{"independent approval outlives owner consent", func(r *TransferRequest) { r.Approval.ExpiresAt = 1800000101 }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &engineTestBackend{}
			engine, _, policy := engineTestOpen(t, backend)
			r := engineTestWithdrawal(t)
			test.mutate(&r)
			// Even a valid independent reviewer cannot forge wallet consent.
			if r.OwnerMandate != nil && test.name != "unbound owner proof" {
				r.Approval.HoldDigest = WithdrawalHoldDigest(r.Approval.ReservationDigest, *r.OwnerMandate)
			}
			engineTestSignApproval(r.Approval, policy.Vault)
			if _, err := engine.Submit(t.Context(), r); err == nil {
				t.Fatal("withdrawal lacking exact owner consent reached durable admission")
			}
			if backend.signs.Load() != 0 || backend.broadcasts.Load() != 0 {
				t.Fatal("invalid owner consent reached a financial operation")
			}
			if _, err := engine.Lookup(r.OperationID); err == nil {
				t.Fatal("rejected owner consent created a durable financial obligation")
			}
		})
	}
}

func TestWithdrawalExpiryDuringSigningRetainsFenceWithoutBroadcastOrRetry(t *testing.T) {
	backend := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, backend)
	r := engineTestWithdrawal(t)
	backend.beforeSign = func(TransferRequest) { e.now = func() time.Time { return time.Unix(1800000100, 0) } }
	result, err := e.Submit(t.Context(), r)
	if err != nil || result.Status != "UNKNOWN" || result.Reason != "withdrawal_authority_expired_before_broadcast" || !result.DurableFenced || result.TxHash == "" {
		t.Fatalf("expired signed operation lost durable hold: %+v %v", result, err)
	}
	for n := 0; n < 3; n++ {
		if repeated, err := e.Submit(t.Context(), r); err != nil || repeated != result {
			t.Fatalf("uncertain signed operation changed on retry: %+v %v", repeated, err)
		}
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 0 {
		t.Fatal("expired signed withdrawal broadcast or re-signed")
	}
}

func TestWithdrawalOwnerFractionalTimestampAndHistoricalVerification(t *testing.T) {
	r := engineTestWithdrawal(t)
	issued := time.Unix(r.Approval.IssuedAt, 123000000).UTC()
	r.OwnerMandate.Challenge.IssuedAtUTC = issued.Format(time.RFC3339Nano)
	message, err := WithdrawalOwnerSignBytes(r.OwnerMandate.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	signature, err := sdksecp.GenPrivKeyFromSecret([]byte("isolated-test-owner-consent-not-a-production-key")).Sign(message)
	if err != nil {
		t.Fatal(err)
	}
	r.OwnerMandate.Signature = base64.StdEncoding.EncodeToString(signature)
	r.Approval.HoldDigest = WithdrawalHoldDigest(r.Approval.ReservationDigest, *r.OwnerMandate)
	engineTestSignApproval(r.Approval, r.Sender)
	if err := engineTestPolicy(t).verifyWithdrawal(r, issued); err != nil {
		t.Fatalf("valid HD fractional timestamp refused: %v", err)
	}
	if err := verifyOwnerWithdrawal(r, issued.Add(-time.Nanosecond)); err == nil {
		t.Fatal("future owner issue accepted")
	}
	if err := verifyOwnerWithdrawal(r, time.Unix(r.Approval.ExpiresAt, 0)); err == nil {
		t.Fatal("expired owner consent accepted")
	}
}

func TestBackendRechecksIndependentApprovalAfterAccountIOBeforeSigning(t *testing.T) {
	f := newBackendFixture(t)
	r := f.request
	r.Kind = "withdrawal"
	r.Reservation = nil
	r.OperationID = "satchel:withdrawal:a0000000-0000-4000-8000-000000000007"
	r.Memo = "aoe2war/satchel/withdraw/v1/a0000000-0000-4000-8000-000000000007"
	r.Approval = &WithdrawalApproval{WithdrawalID: "a0000000-0000-4000-8000-000000000007"}
	checks := 0
	f.b.cfg.WithdrawalVerifier = func(TransferRequest) error {
		checks++
		if checks > 1 {
			return ErrBackend
		}
		return nil
	}
	if _, err := f.b.Sign(t.Context(), r); err != ErrPreSignRefused || checks != 2 || f.signer.calls.Load() != 0 || f.broadcasts.Load() != 0 {
		t.Fatalf("expiry during account I/O reached signing: err=%v checks=%d signs=%d", err, checks, f.signer.calls.Load())
	}
}
