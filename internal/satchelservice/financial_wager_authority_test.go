package satchelservice

import (
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestFinancialVerifierLoadsDistinctWagerAuthority(t *testing.T) {
	c := testVerifierAuthority(t)
	raw, _ := json.Marshal(c)
	var fields map[string]any
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	fields["wager_approval_public_key_hex"] = hex.EncodeToString(engineTestPolicy(t).WagerApprovalKey)
	raw, _ = json.Marshal(fields)
	configured, err := DecodeFinancialProofVerifierConfig(raw)
	if err != nil {
		t.Fatalf("distinct wager authority could not be provisioned: %v", err)
	}
	policy, err := verifierPolicy(configured)
	if err != nil {
		t.Fatal(err)
	}
	request := engineTestWager(t, "7")
	if err = policy.validate(request, time.Unix(request.Reservation.IssuedAt, 0)); err != nil {
		t.Fatalf("genuine signed wager rejected: %v", err)
	}
}

func TestFinancialVerifierNeverSubstitutesWithdrawalAuthorityForWager(t *testing.T) {
	for _, which := range []string{"absent", "same_key", "malformed", "wrong_key"} {
		t.Run(which, func(t *testing.T) {
			c := testVerifierAuthority(t)
			raw, _ := json.Marshal(c)
			var fields map[string]any
			_ = json.Unmarshal(raw, &fields)
			if which != "absent" {
				fields["wager_approval_public_key_hex"] = map[string]string{"same_key": c.ApprovalPublicKeyHex, "malformed": "zz", "wrong_key": strings.Repeat("ab", 32)}[which]
			}
			raw, _ = json.Marshal(fields)
			configured, err := DecodeFinancialProofVerifierConfig(raw)
			if err != nil {
				return
			}
			policy, err := verifierPolicy(configured)
			request := engineTestWager(t, "7")
			if err == nil && policy.validate(request, time.Unix(request.Reservation.IssuedAt, 0)) == nil {
				t.Fatal("wrong role authorized wager")
			}
		})
	}
}
