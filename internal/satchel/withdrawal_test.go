package satchel

import (
	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
)

func withdrawalFixture(t *testing.T) (WithdrawalIntent, WithdrawalRecord) {
	i := WithdrawalIntent{"withdrawal-1", "owner-a", fixtureAddress(t, 1), fixtureAddress(t, 2), "1000000", "owner-authorized-withdrawal:nonce"}
	f, err := i.Fingerprint()
	if err != nil {
		t.Fatal(err)
	}
	return i, WithdrawalRecord{RequestID: i.RequestID, Fingerprint: f, HoldEvidenceDigest: strings.Repeat("A", 64), ScopedConsentDigest: strings.Repeat("B", 64), State: "held"}
}

func signFixture(t *testing.T, r *WithdrawalRecord) {
	i, _ := withdrawalFixture(t)
	_, o, _ := depositFixture(t)
	rewriteSend(t, &o, func(s *bank.MsgSend) { s.FromAddress = i.Vault; s.ToAddress = i.OwnerWallet })
	rewriteBody(t, &o, func(b *tx.TxBody) { b.Memo = i.Memo })
	r.SignedTx = o.TxBytes
	hash := sha256.Sum256(r.SignedTx)
	r.TxHash = hex.EncodeToString(hash[:])
}

func TestWithdrawalRecoveryNeverAuthorizesExecution(t *testing.T) {
	i, r := withdrawalFixture(t)
	missing, err := InspectWithdrawalRecovery(i, nil)
	if err != nil || missing.Action != "blocked_missing_durable_hold" {
		t.Fatal(missing, err)
	}
	held, err := InspectWithdrawalRecovery(i, &r)
	if err != nil || held.Action != "blocked_execution_unimplemented" {
		t.Fatal(held, err)
	}
	for _, state := range []string{"signed", "submitted", "uncertain"} {
		t.Run(state, func(t *testing.T) {
			i, r := withdrawalFixture(t)
			signFixture(t, &r)
			r.State = state
			first, err := InspectWithdrawalRecovery(i, &r)
			if err != nil || first.Action != "reconcile_only" || first.TxHash != strings.ToUpper(r.TxHash) {
				t.Fatal(first, err)
			}
			// Repeated crashes/timeouts keep exactly the same identity and hold.
			for n := 0; n < 3; n++ {
				again, err := InspectWithdrawalRecovery(i, &r)
				if err != nil || again != first || r.HoldEvidenceDigest == "" {
					t.Fatal("retry changed identity or released hold", again, err)
				}
			}
		})
	}
	signFixture(t, &r)
	r.State = "confirmed"
	r.ConfirmationDigest = strings.Repeat("C", 64)
	first, err := InspectWithdrawalRecovery(i, &r)
	if err != nil || first.Action != "replay_recorded_confirmation" {
		t.Fatal(first, err)
	}
	again, err := InspectWithdrawalRecovery(i, &r)
	if err != nil || again != first {
		t.Fatal("confirmation replay changed result")
	}
	if CurrentCapability().ExecutionReady() {
		t.Fatal("recovery fixture enabled transfers")
	}
}

func TestWithdrawalPayloadIdentityConflicts(t *testing.T) {
	for name, change := range map[string]func(*WithdrawalIntent){
		"request":   func(i *WithdrawalIntent) { i.RequestID = "withdrawal-2" },
		"owner":     func(i *WithdrawalIntent) { i.OwnerID = "owner-b" },
		"recipient": func(i *WithdrawalIntent) { i.OwnerWallet = fixtureAddress(t, 3) },
		"vault":     func(i *WithdrawalIntent) { i.Vault = fixtureAddress(t, 4) },
		"amount":    func(i *WithdrawalIntent) { i.AmountUWolo = "999" },
		"memo":      func(i *WithdrawalIntent) { i.Memo = "changed" },
	} {
		t.Run(name, func(t *testing.T) {
			i, r := withdrawalFixture(t)
			change(&i)
			if _, err := InspectWithdrawalRecovery(i, &r); err == nil || err.Error() != "withdrawal_idempotency_conflict" {
				t.Fatal("changed request did not conflict", err)
			}
		})
	}
}

func TestWithdrawalUnsafeOrAmbiguousRecordRefused(t *testing.T) {
	for name, change := range map[string]func(*WithdrawalRecord){
		"missing hold":                       func(r *WithdrawalRecord) { r.HoldEvidenceDigest = "" },
		"missing scoped consent":             func(r *WithdrawalRecord) { r.ScopedConsentDigest = "" },
		"signed without bytes":               func(r *WithdrawalRecord) { r.State = "signed" },
		"broadcast without durable identity": func(r *WithdrawalRecord) { r.State = "submitted" },
		"hash differs": func(r *WithdrawalRecord) {
			signFixture(t, r)
			r.State = "uncertain"
			r.TxHash = strings.Repeat("F", 64)
		},
		"confirmation missing": func(r *WithdrawalRecord) { signFixture(t, r); r.State = "confirmed" },
		"contradictory confirmation": func(r *WithdrawalRecord) {
			signFixture(t, r)
			r.State = "uncertain"
			r.ConfirmationDigest = strings.Repeat("D", 64)
		},
		"failed never confirms": func(r *WithdrawalRecord) { signFixture(t, r); r.State = "failed" },
		"cancel never releases": func(r *WithdrawalRecord) { r.State = "cancelled" },
		"unknown state":         func(r *WithdrawalRecord) { signFixture(t, r); r.State = "future-version" },
	} {
		t.Run(name, func(t *testing.T) {
			i, r := withdrawalFixture(t)
			change(&r)
			if _, err := InspectWithdrawalRecovery(i, &r); err == nil {
				t.Fatal("unsafe recovery accepted")
			}
		})
	}
}

func TestWithdrawalRejectsSharedCustodyAndInvalidIntent(t *testing.T) {
	for name, change := range map[string]func(*WithdrawalIntent){
		"invalid owner encoding":   func(i *WithdrawalIntent) { i.OwnerID = "\xff" },
		"invalid request encoding": func(i *WithdrawalIntent) { i.RequestID = "\xfe" },
		"invalid memo encoding":    func(i *WithdrawalIntent) { i.Memo = "\xff" },
		"shared escrow":            func(i *WithdrawalIntent) { i.Vault = "wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p" },
		"founder payout":           func(i *WithdrawalIntent) { i.Vault = "wolo1tg04m57e52evgzjkn9ruwwkz626pfv9qfv27wy" },
		"missing owner":            func(i *WithdrawalIntent) { i.OwnerID = "" },
		"recipient equals vault":   func(i *WithdrawalIntent) { i.OwnerWallet = i.Vault },
		"invalid amount":           func(i *WithdrawalIntent) { i.AmountUWolo = "0" },
		"unbound memo":             func(i *WithdrawalIntent) { i.Memo = "" },
	} {
		t.Run(name, func(t *testing.T) {
			i, _ := withdrawalFixture(t)
			change(&i)
			if _, err := i.Fingerprint(); err == nil {
				t.Fatal("unsafe withdrawal intent accepted")
			}
		})
	}
}

func TestWithdrawalRejectsWrongBytesEvenWithMatchingHash(t *testing.T) {
	for name, mutate := range map[string]func(*Observation){
		"recipient": func(o *Observation) { rewriteSend(t, o, func(s *bank.MsgSend) { s.ToAddress = fixtureAddress(t, 3) }) },
		"sender": func(o *Observation) {
			rewriteSend(t, o, func(s *bank.MsgSend) { s.FromAddress = fixtureAddress(t, 4) })
		},
		"amount": func(o *Observation) { rewriteSend(t, o, func(s *bank.MsgSend) { s.Amount[0].Amount = "999" }) },
		"denom":  func(o *Observation) { rewriteSend(t, o, func(s *bank.MsgSend) { s.Amount[0].Denom = "uother" }) },
		"memo":   func(o *Observation) { rewriteBody(t, o, func(b *tx.TxBody) { b.Memo = "different" }) },
		"message count": func(o *Observation) {
			rewriteBody(t, o, func(b *tx.TxBody) { b.Messages = append(b.Messages, b.Messages[0]) })
		},
	} {
		t.Run(name, func(t *testing.T) {
			i, r := withdrawalFixture(t)
			signFixture(t, &r)
			r.State = "submitted"
			o := Observation{TxBytes: r.SignedTx}
			mutate(&o)
			r.SignedTx = o.TxBytes
			r.TxHash = o.TxHash
			if _, err := InspectWithdrawalRecovery(i, &r); err == nil || err.Error() != "withdrawal_signed_payload_mismatch" {
				t.Fatal("changed bytes reused original hold", err)
			}
		})
	}
}
